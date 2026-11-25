import * as fs from 'fs';
import * as socket from 'socket';
import * as uloop from 'uloop';
import * as config from 'config';
import * as super from 'super';
import * as video from 'video';
import * as peerctl from 'peer';
import * as presets from 'presets';

/* Persistent, loopback-only development server. Put authentication at a
 * reverse proxy before exposing this control API on a LAN. */
const dir = getenv('PORTSDOWN_DIR');
if (!dir || substr(dir, 0, 1) != '/') die('PORTSDOWN_DIR must be absolute');
const cfgpath = getenv('PORTSDOWN_CONFIG') ?? `${dir}/scripts/portsdown_config.txt`;
const store = getenv('PORTSDOWN_CONFIG_STORE') ?? `${dir}/control/config-store`;
const presetpath = getenv('PORTSDOWN_PRESETS_PATH') ?? '/var/lib/portsdown/presets.json';
const sockpath = getenv('PORTSDOWN_TX_SOCKET') ?? '/run/portsdown/tx.sock';
const port = +(getenv('PORTSDOWN_HTTP_PORT') ?? '8080');
const extra_host = getenv('PORTSDOWN_ALLOWED_HOST');
const peer_role = getenv('PORTSDOWN_PEER_ROLE') ?? 'STANDALONE';
if (port < 1024 || port > 65535) die('Invalid PORTSDOWN_HTTP_PORT');

let sessions = [];
let event_id = 0;
let last_status = '';
let logs = [];
let log_subscription = null;

function srt_state(status) {
  let slots = [];
  let base = +(getenv('PORTSDOWN_SRT_PORT_BASE') ?? '9101');
  let ts_base = +(getenv('PORTSDOWN_SRT_TS_PORT_BASE') ?? '12001');
  for (let slot = 1; slot <= 5; slot++) {
    let enabled = index(status ?? '', `srt${slot}=running`) >= 0;
    let preview = video.stats(slot);
    push(slots, { slot: slot, enabled: enabled, live: enabled && preview.producer,
      srt_port: base + slot - 1, ts_port: ts_base + slot - 1, preview: preview });
  }
  return slots;
}

const local_sources = { HDMI: 6, CAMH264: 7, IPTSIN: 8 };
let source_attempts = {};
function wants_source(cfg, source) {
  if (!cfg) return false;
  if ((cfg.source_layout ?? 'DIRECT') != 'MULTIVIEW')
    return cfg.modeinput == source ||
      (source == 'IPTSIN' && (cfg.modeinput == 'IPTSIN264' || cfg.modeinput == 'IPTSIN265'));
  for (let tile = 1; tile <= 4; tile++)
    if (cfg[`multiview_${tile}`] == source) return true;
  return false;
}

function source_state(cfg) {
  let result = {};
  for (let source, slot in local_sources)
    result[source] = { selected: wants_source(cfg, source), preview: video.stats(slot) };
  return result;
}

function sync_sources(cfg, status) {
  let can_run = index(status ?? '', 'tx=stopped') >= 0 &&
    index(status ?? '', 'rx=stopped') >= 0;
  for (let source, slot in local_sources) {
    let role = source == 'CAMH264' ? 'PICAM' : source == 'IPTSIN' ? 'IPTS' : 'HDMI';
    let wanted = wants_source(cfg, source);
    let key = source == 'CAMH264' ? 'picam' : source == 'IPTSIN' ? 'ipts' : 'hdmi';
    let running = index(status ?? '', `${key}=running`) >= 0;
    if (!wanted || !can_run) {
      if (running) super.request(sockpath, `STOP_${role}`);
    } else if (!running && getenv('PORTSDOWN_SOURCE_PREVIEW_EXEC') &&
               time() - (source_attempts[source] ?? 0) >= 5) {
      source_attempts[source] = time();
      super.request(sockpath, `START_${role}`);
    }
  }
}

function asi_file_status() {
  let path = getenv('PORTSDOWN_ASI_TS_FILE');
  if (!path) return { state: 'unconfigured' };
  if (substr(path, 0, 1) != '/') return { state: 'unknown' };
  let cfg = config.load(cfgpath);
  if (!cfg?.call || !cfg?.service_name) return { state: 'unconfigured' };
  /* Probe only on this separate status request, never on the 1 Hz state poll
   * or TX path. A slow or unreadable file must not block playout. */
  let proc = fs.popen(['timeout', '3s', 'ffprobe', '-v', 'error',
    '-show_entries', 'program=program_id:program_tags=service_provider,service_name',
    '-of', 'json', path], 'r');
  if (!proc) return { state: 'unknown' };
  let raw = proc.read(65536);
  let rc = proc.close();
  if (rc != 0 || !raw || length(raw) >= 65536) return { state: 'unknown' };
  let data;
  try { data = json(raw); } catch (e) { return { state: 'unknown' }; }
  if (type(data?.programs) != 'array' || length(data.programs) == 0)
    return { state: 'unknown' };
  for (let program in data.programs) {
    let provider = program.tags?.service_provider ?? '';
    let name = program.tags?.service_name ?? '';
    if (provider != cfg.call || name != cfg.service_name)
      return { state: 'mismatch', programs: length(data.programs),
        observed_provider: substr(provider, 0, 64), observed_name: substr(name, 0, 64) };
  }
  return { state: 'match', programs: length(data.programs) };
}

function emit(event, data) {
  let message = `id: ${++event_id}\nevent: ${event}\ndata: ${sprintf('%J', data)}\n\n`;
  let live = [];
  for (let peer in sessions) {
    /* Skip/drop slow clients; never queue stale control or video data. */
    if (peer.send(message, socket.MSG_DONTWAIT) == length(message)) push(live, peer);
    else peer.close();
  }
  sessions = live;
}

function response(peer, status, ctype, body, keep) {
  let packet = `HTTP/1.1 ${status}\r\nContent-Type: ${ctype}\r\n` +
    'Cache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n' +
    (keep ? '' : `Content-Length: ${length(body)}\r\nConnection: close\r\n`) +
    `\r\n${body}`;
  let sent = peer.send(packet, socket.MSG_DONTWAIT);
  if (!keep || sent != length(packet)) peer.close();
  return sent == length(packet);
}

function api(peer, method, path, body) {
  if (method == 'GET' && path == '/api/asi/file-status')
    return response(peer, '200 OK', 'application/json', sprintf('%J', asi_file_status()));
  if (method == 'GET' && path == '/api/state') {
    let result = super.request(sockpath, 'STATUS');
    let cfg = config.load(cfgpath);
    return response(peer, '200 OK', 'application/json', sprintf('%J', {
      supervisor: result, board: cfg?.modeoutput ?? 'unknown', modulation: cfg?.modulation ?? 'unknown',
      peer_role: peer_role, peer: peerctl.status(), logs: logs, video: video.stats(),
      srt: srt_state(result.status), sources: source_state(cfg),
      source_preview_available: !!getenv('PORTSDOWN_SOURCE_PREVIEW_EXEC'),
      source_ts_available: !!getenv('PORTSDOWN_SOURCE_TS_EXEC'),
      remote_preview_url: peer_role == 'MASTER' ? getenv('PORTSDOWN_SLAVE_PREVIEW_URL') : null
    }));
  }
  if (method == 'GET' && path == '/api/config') {
    let cfg = config.load(cfgpath);
    if (!cfg) return response(peer, '503 Service Unavailable', 'application/json', '{"error":"config unavailable"}');
    cfg.streamkey = cfg.streamkey ? '(configured)' : '';
    return response(peer, '200 OK', 'application/json', sprintf('%J', { config: cfg, capabilities: config.capabilities }));
  }
  if (method == 'POST' && path == '/api/config') {
    if (peer_role == 'SLAVE') return response(peer, '403 Forbidden', 'application/json', '{"error":"slave configuration is master-controlled"}');
    let running = super.request(sockpath, 'STATUS').status ?? '';
    if (index(running, 'tx=running') >= 0 || index(running, 'rx=running') >= 0 || peerctl.status().tx_requested)
      return response(peer, '409 Conflict', 'application/json', '{"error":"stop TX/RX before changing configuration"}');
    let changes = json(body);
    if (type(changes) != 'object') return response(peer, '400 Bad Request', 'application/json', '{"error":"JSON object required"}');
    let error = config.update(cfgpath, store, changes);
    if (error) return response(peer, '400 Bad Request', 'application/json', sprintf('%J', { error: error }));
    if (index(running, 'source_ts=running') >= 0)
      super.request(sockpath, 'STOP_SOURCE_TS');
    if (changes.call != null || changes.service_name != null) {
      /* SRT slots capture service metadata at process start. Restart only
       * enabled listeners so no stale provider/name remains on TS output. */
      for (let slot = 1; slot <= 5; slot++) {
        if (index(running, `srt${slot}=running`) < 0) continue;
        let stopped = super.request(sockpath, `STOP_SRT${slot}`);
        let started = stopped.ok ? super.request(sockpath, `START_SRT${slot}`) : stopped;
        if (!started.ok)
          return response(peer, '503 Service Unavailable', 'application/json',
            sprintf('%J', { error: `Configuration saved but SRT ${slot} restart failed: ${started.message}` }));
      }
    }
    if (changes.expresshdmidevice != null)
      super.request(sockpath, 'STOP_HDMI');
    if (changes.picam_index != null)
      super.request(sockpath, 'STOP_PICAM');
    if (changes.ipts_input_port != null || changes.ipts_bind_scope != null)
      super.request(sockpath, 'STOP_IPTS');
    if (changes.modeinput != null || changes.source_layout != null ||
        changes.multiview_1 != null || changes.multiview_2 != null ||
        changes.multiview_3 != null || changes.multiview_4 != null ||
        changes.expresshdmidevice != null || changes.picam_index != null ||
        changes.ipts_input_port != null || changes.ipts_bind_scope != null)
      source_attempts = {};
    if (changes.modeinput != null || changes.expresshdmidevice != null) {
      /* The standby FFmpeg process reads the saved capture source at launch. */
      super.request(sockpath, 'STOP_PREVIEW');
      super.request(sockpath, 'START_PREVIEW');
    }
    emit('config', { changed: true });
    if (peer_role == 'MASTER') peerctl.push_config();
    return response(peer, '200 OK', 'application/json', '{"ok":true}');
  }
  if (match(path, /^\/api\/presets\/[1-4]$/)) {
    let slot = substr(path, -1);
    if (method == 'GET') {
      let data = presets.load(presetpath)[slot];
      return data ? response(peer, '200 OK', 'application/json', sprintf('%J', data)) :
        response(peer, '404 Not Found', 'application/json', '{"error":"preset empty"}');
    }
    if (method == 'POST') {
      if (peer_role == 'SLAVE') return response(peer, '403 Forbidden', 'application/json', '{"error":"slave UI is read-only"}');
      let error = presets.save(presetpath, store, slot, json(body));
      return error ? response(peer, '400 Bad Request', 'application/json', sprintf('%J', { error: error })) :
        response(peer, '200 OK', 'application/json', '{"ok":true}');
    }
  }
  let commands = {
    '/api/tx/start': 'START_TX', '/api/tx/stop': 'STOP_TX',
    '/api/rx/start': 'START_RX', '/api/rx/stop': 'STOP_RX'
  };
  if (method == 'POST' && commands[path]) {
    if (peer_role == 'SLAVE' && path != '/api/tx/stop')
      return response(peer, '403 Forbidden', 'application/json', '{"error":"slave UI is read-only except E-Stop"}');
    let route = config.load(cfgpath);
    if (path == '/api/tx/start' &&
        (route?.source_layout == 'MULTIVIEW' ||
         route?.source_layout == 'DIRECT' && route?.modeinput == 'SRT'))
      return response(peer, '409 Conflict', 'application/json',
        '{"error":"selected source TS output is separate; RF TX route is not integrated"}');
    let result;
    if (peer_role == 'MASTER' && path == '/api/tx/start')
      result = peerctl.set_tx(true) ? { ok: true, message: 'remote TX requested' } : { ok: false, message: 'peer unavailable or config not acknowledged' };
    else if (peer_role == 'MASTER' && path == '/api/tx/stop') {
      let remote = peerctl.set_tx(false);
      super.request(sockpath, 'STOP_TX');
      result = { ok: remote, message: remote ? 'remote stop requested' : 'peer unreachable; remote dead-man stop pending' };
    } else result = super.request(sockpath, commands[path]);
    emit('state', { command: commands[path], result: result });
    return response(peer, result.ok ? '200 OK' : '503 Service Unavailable', 'application/json', sprintf('%J', result));
  }
  if (method == 'GET' && path == '/api/srt') {
    let result = super.request(sockpath, 'STATUS');
    return response(peer, result.ok ? '200 OK' : '503 Service Unavailable', 'application/json',
      sprintf('%J', { slots: srt_state(result.status) }));
  }
  if (method == 'POST' && match(path, /^\/api\/srt\/[1-5]\/(enable|disable)$/)) {
    if (peer_role == 'SLAVE') return response(peer, '403 Forbidden', 'application/json', '{"error":"slave UI is read-only"}');
    let slot = substr(path, 9, 1);
    let enabled = substr(path, 11) == 'enable';
    let result = super.request(sockpath, `${enabled ? 'START' : 'STOP'}_SRT${slot}`);
    emit('state', { command: `${enabled ? 'START' : 'STOP'}_SRT${slot}`, result: result });
    return response(peer, result.ok ? '200 OK' : '503 Service Unavailable', 'application/json', sprintf('%J', result));
  }
  if (method == 'POST' && match(path, /^\/api\/source-ts\/(start|stop)$/)) {
    if (peer_role == 'SLAVE') return response(peer, '403 Forbidden', 'application/json', '{"error":"slave UI is read-only"}');
    let start = path == '/api/source-ts/start';
    let cfg = config.load(cfgpath);
    if (start && cfg?.source_layout != 'MULTIVIEW' &&
        !(cfg?.source_layout == 'DIRECT' && cfg?.modeinput == 'SRT'))
      return response(peer, '409 Conflict', 'application/json', '{"error":"save Direct SRT or Multiview output source first"}');
    if (start && cfg?.source_layout == 'DIRECT') {
      let slot = cfg.srt_source_slot ?? '1';
      let armed = super.request(sockpath, `START_SRT${slot}`);
      if (!armed.ok) return response(peer, '503 Service Unavailable', 'application/json', sprintf('%J', armed));
    }
    let result = super.request(sockpath, start ? 'START_SOURCE_TS' : 'STOP_SOURCE_TS');
    emit('state', { command: start ? 'START_SOURCE_TS' : 'STOP_SOURCE_TS', result: result });
    return response(peer, result.ok ? '200 OK' : '503 Service Unavailable', 'application/json', sprintf('%J', result));
  }
  if (method == 'GET' && path == '/api/events') {
    if (length(sessions) >= 16) return response(peer, '503 Service Unavailable', 'text/plain', 'Too many subscribers');
    if (response(peer, '200 OK', 'text/event-stream', ': connected\n\n', true)) push(sessions, peer);
    return;
  }
  if (method == 'GET' && path == '/api/video') {
    if (!response(peer, '200 OK', 'multipart/x-mixed-replace; boundary=frame', '', true)) return;
    if (!video.subscribe(peer, 0)) peer.close();
    return;
  }
  if (method == 'GET' && match(path, /^\/api\/video\/srt\/[1-5]$/)) {
    if (!response(peer, '200 OK', 'multipart/x-mixed-replace; boundary=frame', '', true)) return;
    if (!video.subscribe(peer, +substr(path, -1))) peer.close();
    return;
  }
  if (method == 'GET' && match(path, /^\/api\/video\/source\/(hdmi|camera|ipts)$/)) {
    let source = substr(path, 18);
    let slot = source == 'hdmi' ? 6 : source == 'camera' ? 7 : 8;
    if (!response(peer, '200 OK', 'multipart/x-mixed-replace; boundary=frame', '', true)) return;
    if (!video.subscribe(peer, slot)) peer.close();
    return;
  }
  if (method == 'GET' && match(path, /^\/no-srt-input-[1-5]\.jpg$/)) {
    let file = fs.readfile(`${dir}/www${path}`);
    return file == null ? response(peer, '404 Not Found', 'text/plain', 'Missing file') :
      response(peer, '200 OK', 'image/jpeg', file);
  }
  if (method == 'GET' && (match(path, /^\/no-(hdmi|picam|ipts)-input\.jpg$/) || path == '/test-card.jpg')) {
    let file = fs.readfile(`${dir}/www${path}`);
    return file == null ? response(peer, '404 Not Found', 'text/plain', 'Missing file') :
      response(peer, '200 OK', 'image/jpeg', file);
  }
  let files = { '/': ['index.html', 'text/html; charset=utf-8'],
    '/app.js': ['app.js', 'text/javascript; charset=utf-8'],
    '/style.css': ['style.css', 'text/css; charset=utf-8'],
    '/no-ip-input.svg': ['no-ip-input.svg', 'image/svg+xml'],
    '/no-hdmi-input.svg': ['no-hdmi-input.svg', 'image/svg+xml'] };
  if (method == 'GET' && files[path]) {
    let file = fs.readfile(`${dir}/www/${files[path][0]}`);
    return file == null ? response(peer, '404 Not Found', 'text/plain', 'Missing file') :
      response(peer, '200 OK', files[path][1], file);
  }
  response(peer, '404 Not Found', 'text/plain', 'Not found');
}

uloop.init();
if (peer_role == 'SLAVE' && index(super.request(sockpath, 'STATUS').status ?? '', 'peer=slave') < 0)
  die('Slave mode requires tx-super PORTSDOWN_PEER_ROLE=SLAVE');
if (!peerctl.start({ role: peer_role, token: getenv('PORTSDOWN_PEER_TOKEN'),
  host: getenv('PORTSDOWN_PEER_HOST'), bind: getenv('PORTSDOWN_PEER_BIND'),
  port: +(getenv('PORTSDOWN_PEER_PORT') ?? '8181'),
  config: cfgpath, store: store, socket: sockpath },
  (state) => emit('peer', state))) die('Invalid peer configuration');
let video_server = video.start(+(getenv('PORTSDOWN_MJPEG_PORT') ?? '8082'));
if (!video_server) die('Cannot bind loopback MJPEG ingest port');
let srt_preview_base = +(getenv('PORTSDOWN_SRT_MJPEG_PORT_BASE') ?? '8083');
let srt_input_base = +(getenv('PORTSDOWN_SRT_PORT_BASE') ?? '9101');
let srt_ts_base = +(getenv('PORTSDOWN_SRT_TS_PORT_BASE') ?? '12001');
if (srt_preview_base < 1024 || srt_preview_base > 65531 ||
    srt_input_base < 1024 || srt_input_base > 65531 ||
    srt_ts_base < 1024 || srt_ts_base > 65531) die('Invalid SRT port base');
let srt_servers = [];
for (let slot = 1; slot <= 5; slot++) {
  let listener = video.start(srt_preview_base + slot - 1, slot);
  if (!listener) die(`Cannot bind SRT preview ingest port for slot ${slot}`);
  if (!video.set_fallback(slot, fs.readfile(`${dir}/www/no-srt-input-${slot}.jpg`)))
    die(`Missing SRT test card for slot ${slot}`);
  push(srt_servers, listener);
}
let source_preview_base = +(getenv('PORTSDOWN_SOURCE_MJPEG_PORT_BASE') ??
  ('' + (+(getenv('PORTSDOWN_MJPEG_PORT') ?? '8082') + 6)));
if (source_preview_base < 1024 || source_preview_base > 65533)
  die('Invalid source preview port base');
for (let source, slot in local_sources) {
  if (!video.start(source_preview_base + slot - 6, slot))
    die(`Cannot bind ${source} preview ingest port`);
  let card = source == 'HDMI' ? 'hdmi' : source == 'CAMH264' ? 'picam' : 'ipts';
  if (!video.set_fallback(slot, fs.readfile(`${dir}/www/no-${card}-input.jpg`)))
    die(`Missing ${source} preview test card`);
}
/* tx-super may have started its standby preview before the MJPEG listener
 * existed, causing FFmpeg's first TCP connect to fail. Retry now. */
super.request(sockpath, 'START_PREVIEW');
if (getenv('PORTSDOWN_PREVIEW_EXEC')) uloop.timer(2000, function() {
  let state = super.request(sockpath, 'STATUS').status ?? '';
  if (index(state, 'tx=stopped') >= 0 && index(state, 'rx=stopped') >= 0 &&
      index(state, 'preview=stopped') >= 0) super.request(sockpath, 'START_PREVIEW');
  this.set(2000);
});
let server = socket.listen('127.0.0.1', port, { family: socket.AF_INET, socktype: socket.SOCK_STREAM }, 32, true);
if (!server) die(`Cannot bind loopback HTTP port ${port}`);

uloop.handle(server, () => {
  let peer = server.accept(null, socket.SOCK_NONBLOCK | socket.SOCK_CLOEXEC);
  if (!peer) return;
  let input = '';
  let handle;
  handle = uloop.handle(peer, () => {
    let chunk = peer.recv(4096, socket.MSG_DONTWAIT);
    if (!chunk) { handle.delete(); peer.close(); return; }
    input += chunk;
    if (length(input) > 16384) { handle.delete(); response(peer, '413 Content Too Large', 'text/plain', 'Too large'); return; }
    let end = index(input, '\r\n\r\n');
    if (end < 0) return;
    let lines = split(substr(input, 0, end), '\r\n');
    let first = split(lines[0], ' ');
    if (length(first) != 3 || first[2] != 'HTTP/1.1' && first[2] != 'HTTP/1.0') {
      handle.delete(); response(peer, '400 Bad Request', 'text/plain', 'Bad request'); return;
    }
    let size = 0;
    let host = null, control_header = null;
    for (let line in lines) {
      let colon = index(line, ':');
      if (colon < 1) continue;
      let name = lc(trim(substr(line, 0, colon)));
      let value = trim(substr(line, colon + 1));
      if (name == 'content-length') size = +value;
      if (name == 'host') host = value;
      if (name == 'x-portsdown-control') control_header = value;
    }
    if (host != `127.0.0.1:${port}` && host != `localhost:${port}` &&
        (!extra_host || host != extra_host)) {
      handle.delete(); response(peer, '421 Misdirected Request', 'text/plain', 'Untrusted Host'); return;
    }
    if (first[0] == 'POST' && control_header != '1') {
      handle.delete(); response(peer, '403 Forbidden', 'text/plain', 'Control header required'); return;
    }
    if (size < 0 || size > 8192 || (first[0] == 'POST' && first[1] == '/api/config' && size == 0)) {
      handle.delete(); response(peer, '400 Bad Request', 'text/plain', 'Invalid body length'); return;
    }
    if (length(input) < end + 4 + size) return;
    handle.delete();
    api(peer, first[0], first[1], substr(input, end + 4, size));
  }, uloop.ULOOP_READ);
}, uloop.ULOOP_READ);

uloop.timer(1000, function() {
  let result = super.request(sockpath, 'STATUS');
  let state = result.status ?? result.message;
  let cfg = config.load(cfgpath);
  sync_sources(cfg, result.status);
  if (state != last_status) { last_status = state; emit('state', result); }
  if (!log_subscription || !log_subscription.handle.fileno()) {
    log_subscription = super.subscribe(sockpath, (line) => {
      if (substr(line, 0, 4) == 'LOG ') {
        push(logs, line);
        if (length(logs) > 30) shift(logs);
        emit('log', { line: line });
      } else if (substr(line, 0, 6) == 'STATE ') emit('state', { status: line });
    });
  }
  this.set(1000);
});

/* Waiting cards are paced at 5 fps, matching the MJPEG compositor input. */
uloop.timer(200, function() {
  let cfg = config.load(cfgpath);
  let result = super.request(sockpath, 'STATUS');
  for (let slot in srt_state(result.status)) {
    let source = `SRT${slot.slot}`;
    let selected = cfg?.source_layout == 'MULTIVIEW' ?
      cfg.multiview_1 == source || cfg.multiview_2 == source ||
      cfg.multiview_3 == source || cfg.multiview_4 == source :
      cfg?.modeinput == 'SRT' && (cfg.srt_source_slot ?? '1') == '' + slot.slot;
    video.tick(slot.slot, slot.enabled || selected);
  }
  for (let source, slot in local_sources)
    video.tick(slot, wants_source(cfg, source));
  this.set(200);
});

uloop.timer(15000, function() { emit('heartbeat', { alive: true }); this.set(15000); });

printf('portsdown-ucd listening on 127.0.0.1:%d\n', port);
uloop.run();
server.close();
uloop.done();
