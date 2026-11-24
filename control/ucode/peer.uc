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
let on_event = () => {};

export function status() {
  return { role: role, connected: link != null && authenticated,
    config_ready: cfg_acked, tx_requested: tx_active, missed_heartbeats: missed_hb };
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
  if (role == 'SLAVE') {
    super.request(sockpath, 'STOP_TX');
  }
  tx_active = false;
  on_event(status());
}

function cfg_subset() {
  let cfg = config.load(cfgpath);
  if (!cfg) return null;
  let keys = ['modeoutput','modeinput','modulation','freqoutput','symbolrate','fec',
    'format','encoding','explevel','plutopwr','limegain',
    'asi_device','asi_channel','asi_bitrate'];
  let values = {};
  for (let key in keys) if (cfg[key] != null) values[key] = cfg[key];
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
  if (role != 'MASTER' || !authenticated || (on && !cfg_acked)) return false;
  if (on && !send({ cmd: 'hb' })) return false;
  if (!send({ cmd: 'tx', state: on ? 1 : 0 })) return false;
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
      authenticated = true; send({ cmd: 'auth_ok' }); on_event(status());
    } else if (role == 'MASTER' && message.cmd == 'auth_ok') {
      authenticated = true; push_config(); on_event(status());
    } else disconnect();
    return;
  }
  if (role == 'MASTER') {
    if (message.cmd == 'cfg_ok') { cfg_acked = true; on_event(status()); }
    if (message.cmd == 'fault') { tx_active = false; on_event(status()); }
    return;
  }
  if (message.cmd == 'cfg') {
    if (tx_active) { send({ cmd: 'fault', reason: 'stop TX before configuration update' }); return; }
    let error = config.update(cfgpath, store, message.data);
    cfg_acked = !error;
    send(error ? { cmd: 'fault', reason: error } : { cmd: 'cfg_ok' });
    on_event(status());
  } else if (message.cmd == 'hb') {
    missed_hb = 0;
    super.request(sockpath, 'PEER_HB');
  } else if (message.cmd == 'tx') {
    if (message.state == 1 && cfg_acked && missed_hb < 3) {
      let result = super.request(sockpath, 'START_TX');
      tx_active = result.ok;
      if (!result.ok) send({ cmd: 'fault', reason: result.message });
    } else {
      super.request(sockpath, 'STOP_TX'); tx_active = false;
    }
    on_event(status());
  }
}

function attach(peer) {
  if (link) disconnect();
  link = peer;
  link.setopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, true);
  pending = ''; authenticated = false; cfg_acked = false; tx_active = false;
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
        on_event(status());
      }
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
      if (link && tx_active && authenticated) send({ cmd: 'hb' });
      this.set(500);
    });
  }
  return true;
}
