import * as socket from 'socket';
import * as uloop from 'uloop';
import * as config from 'config';
import * as super from 'super';

let role = 'STANDALONE';
let token = null;
let host = null;
let port = 8181;
let cfgpath = null;
let store = null;
let sockpath = null;
let link = null;
let link_handle = null;
let authenticated = false;
let cfg_acked = false;
let tx_active = false;
let missed_hb = 0;
let pending = '';
let remote_state = null;
let remote_missed = 0;
let request_id = 0;
let applied_request = 0;
let state_reason = 'idle';
let on_event = () => {};

export function status() {
  return { role: role, connected: link != null && authenticated,
    config_ready: cfg_acked, tx_requested: tx_active, missed_heartbeats: missed_hb,
    remote: remote_state, telemetry_fresh: role == 'MASTER' && authenticated && remote_state != null && remote_missed < 3 };
}

function send(message) {
  if (!link) return false;
  let data = sprintf('%J', message) + '\n';
  if (link.send(data, socket.MSG_DONTWAIT) == length(data)) return true;
  disconnect(); return false;
}

function disconnect() {
  if (link_handle) { link_handle.delete(); link_handle = null; }
  if (link) { link.close(); link = null; }
  authenticated = false; cfg_acked = false; pending = ''; missed_hb = 0;
  remote_state = null; remote_missed = 0;
  if (role == 'SLAVE') {
    super.request(sockpath, 'STOP_TX');
  }
  tx_active = false;
  on_event(status());
}

/* Authoritative process state, not RF measurements. Polling also catches a
 * local E-Stop or child exit that did not originate on the peer connection. */
export function refresh_state(reason) {
  if (role != 'SLAVE') return;
  let result = super.request(sockpath, 'STATUS');
  let running = result.ok && index(result.status ?? '', 'tx=running') >= 0;
  if (reason) state_reason = reason;
  else if (tx_active && !running) state_reason = result.ok ? 'TX stopped or exited locally' : 'supervisor unavailable';
  tx_active = running;
  if (authenticated) send({ cmd: 'state', request_id: applied_request,
    supervisor_ok: !!result.ok, tx: result.ok ? (running ? 'running' : 'stopped') : 'unknown',
    status: result.status ?? '', reason: state_reason });
  on_event(status());
}

function cfg_subset() {
  let cfg = config.load(cfgpath);
  if (!cfg) return null;
  /* The MASTER owns production. Never mirror its capture/mixer selection
   * onto the remote transmitter: the only SLAVE source is IPTS over SRT. */
  let keys = ['modeoutput','modulation','freqoutput','symbolrate','fec',
    'format','explevel','plutopwr','limegain',
    'asi_device','asi_channel','asi_bitrate','call','service_name'];
  let values = {};
  for (let key in keys) if (cfg[key] != null) values[key] = cfg[key];
  values.modeinput = 'IPTSIN';
  values.source_layout = 'DIRECT';
  values.encoding = 'IPTS in';
  values.iptransport = 'srt';
  return values;
}

export function push_config() {
  if (role != 'MASTER' || !authenticated) return false;
  let data = cfg_subset();
  if (!data) return false;
  cfg_acked = false;
  return send({ cmd: 'cfg', data: data });
}

export function set_tx(on) {
  if (role != 'MASTER' || !authenticated || (on && (!cfg_acked || !remote_state?.supervisor_ok || remote_missed >= 3))) return false;
  if (on && !send({ cmd: 'hb' })) return false;
  if (!send({ cmd: 'tx', state: on ? 1 : 0, id: ++request_id })) return false;
  tx_active = on;
  on_event(status());
  return true;
}

function handle_line(line) {
  if (length(line) > 4096) { disconnect(); return; }
  let message = json(line);
  if (type(message) != 'object') { disconnect(); return; }
  if (!authenticated) {
    if (role == 'SLAVE' && message.cmd == 'auth' && message.token == token) {
      authenticated = true; send({ cmd: 'auth_ok' }); refresh_state('connected');
    } else if (role == 'MASTER' && message.cmd == 'auth_ok') {
      authenticated = true; push_config(); on_event(status());
    } else disconnect();
    return;
  }
  if (role == 'MASTER') {
    if (message.cmd == 'cfg_ok') { cfg_acked = true; on_event(status()); }
    if (message.cmd == 'fault') { tx_active = false; on_event(status()); }
    if (message.cmd == 'state') {
      if (type(message.request_id) != 'int' || message.request_id < 0 ||
          message.request_id > request_id || index(['running','stopped','unknown'], message.tx) < 0 ||
          type(message.supervisor_ok) != 'bool') { disconnect(); return; }
      remote_state = { tx: message.tx, supervisor_ok: message.supervisor_ok,
        status: substr(message.status ?? '', 0, 1024),
        reason: substr(message.reason ?? '', 0, 256), request_id: message.request_id };
      remote_missed = 0;
      /* An older stopped snapshot must not cancel a newer START in flight. */
      if (message.request_id == request_id && message.tx != 'running') tx_active = false;
      on_event(status());
    }
    return;
  }
  if (message.cmd == 'cfg') {
    if (tx_active) { send({ cmd: 'fault', reason: 'stop TX before configuration update' }); return; }
    if (message.data?.modeinput != 'IPTSIN' || message.data?.source_layout != 'DIRECT' ||
        message.data?.encoding != 'IPTS in' || message.data?.iptransport != 'srt') {
      cfg_acked = false;
      send({ cmd: 'fault', reason: 'SLAVE accepts only IPTS over SRT from MASTER' });
      return;
    }
    let error = config.update(cfgpath, store, message.data);
    if (!error) {
      /* Producers and the selected TS route read configuration at start. */
      super.request(sockpath, 'STOP_SOURCE_TS');
      super.request(sockpath, 'STOP_HDMI');
      super.request(sockpath, 'STOP_PICAM');
      super.request(sockpath, 'STOP_IPTS');
      super.request(sockpath, 'STOP_IPCAM1');
      super.request(sockpath, 'STOP_IPCAM2');
    }
    if (!error && (message.data.call != null || message.data.service_name != null)) {
      let running = super.request(sockpath, 'STATUS').status ?? '';
      for (let slot = 1; slot <= 5; slot++) {
        if (index(running, `srt${slot}=running`) < 0) continue;
        let stopped = super.request(sockpath, `STOP_SRT${slot}`);
        let started = stopped.ok ? super.request(sockpath, `START_SRT${slot}`) : stopped;
        if (!started.ok) { error = `SRT ${slot} restart failed after configuration save`; break; }
      }
    }
    cfg_acked = !error;
    send(error ? { cmd: 'fault', reason: error } : { cmd: 'cfg_ok' });
    refresh_state(error ? error : 'configuration accepted');
  } else if (message.cmd == 'hb') {
    missed_hb = 0;
    super.request(sockpath, 'PEER_HB');
  } else if (message.cmd == 'tx') {
    if (type(message.id) != 'int' || message.id <= applied_request) {
      send({ cmd: 'fault', reason: 'invalid or repeated TX request id' }); return;
    }
    applied_request = message.id;
    if (message.state == 1 && cfg_acked && missed_hb < 3) {
      let result = super.request(sockpath, 'START_TX');
      tx_active = result.ok;
      if (!result.ok) send({ cmd: 'fault', reason: result.message });
    } else {
      super.request(sockpath, 'STOP_TX'); tx_active = false;
    }
    refresh_state(message.state == 1 ? 'TX start processed' : 'MASTER stop');
  }
}

function attach(peer) {
  if (link) disconnect();
  link = peer;
  link.setopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, true);
  pending = ''; authenticated = false; cfg_acked = false; tx_active = false;
  request_id = 0; applied_request = 0; remote_state = null; remote_missed = 0;
  link_handle = uloop.handle(link, () => {
    let chunk = link.recv(4096, socket.MSG_DONTWAIT);
    if (!chunk) { disconnect(); return; }
    pending += chunk;
    if (length(pending) > 8192) { disconnect(); return; }
    let at;
    while ((at = index(pending, '\n')) >= 0) {
      let line = substr(pending, 0, at);
      pending = substr(pending, at + 1);
      handle_line(line);
      if (!link) return;
    }
  }, uloop.ULOOP_READ);
}

export function start(settings, notify) {
  role = settings.role;
  on_event = notify;
  if (role == 'STANDALONE') return true;
  if (role != 'MASTER' && role != 'SLAVE') return false;
  token = settings.token; host = settings.host; port = settings.port ?? 8181;
  cfgpath = settings.config; store = settings.store; sockpath = settings.socket;
  if (!token || length(token) < 16) return false;
  if (role == 'SLAVE') {
    let server = socket.listen(settings.bind ?? '127.0.0.1', port,
      { family: socket.AF_INET, socktype: socket.SOCK_STREAM }, 2, true);
    if (!server) return false;
    uloop.handle(server, () => {
      let client = server.accept(null, socket.SOCK_NONBLOCK | socket.SOCK_CLOEXEC);
      if (client) attach(client);
    }, uloop.ULOOP_READ);
    uloop.timer(500, function() {
      if (tx_active && ++missed_hb >= 3) {
        super.request(sockpath, 'STOP_TX');
        tx_active = false;
        send({ cmd: 'fault', reason: 'heartbeat timeout' });
        state_reason = 'heartbeat timeout';
      }
      refresh_state();
      this.set(500);
    });
  } else {
    if (!host) return false;
    uloop.timer(100, function() {
      if (!link) {
        let client = socket.connect(host, port,
          { family: socket.AF_INET, socktype: socket.SOCK_STREAM }, 1000);
        if (client) { attach(client); send({ cmd: 'auth', token: token }); }
      }
      if (link && authenticated && ++remote_missed >= 3) {
        /* Missing return telemetry is not a confirmed stopped transmitter.
         * Drop the link/heartbeats; SLAVE's independent watchdog must stop it. */
        disconnect();
      }
      if (link && tx_active && authenticated) send({ cmd: 'hb' });
      this.set(500);
    });
  }
  return true;
}
