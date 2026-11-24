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
  if (method == 'GET' && path == '/api/state') {
    let result = super.request(sockpath, 'STATUS');
    let cfg = config.load(cfgpath);
    return response(peer, '200 OK', 'application/json', sprintf('%J', {
      supervisor: result, board: cfg?.modeoutput ?? 'unknown', modulation: cfg?.modulation ?? 'unknown',
      peer_role: peer_role, peer: peerctl.status(), logs: logs, video: video.stats(),
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
  if (method == 'GET' && path == '/api/events') {
    if (length(sessions) >= 16) return response(peer, '503 Service Unavailable', 'text/plain', 'Too many subscribers');
    if (response(peer, '200 OK', 'text/event-stream', ': connected\n\n', true)) push(sessions, peer);
    return;
  }
  if (method == 'GET' && path == '/api/video') {
    if (!response(peer, '200 OK', 'multipart/x-mixed-replace; boundary=frame', '', true)) return;
    video.subscribe(peer);
    return;
  }
  let files = { '/': ['index.html', 'text/html; charset=utf-8'],
    '/app.js': ['app.js', 'text/javascript; charset=utf-8'],
    '/style.css': ['style.css', 'text/css; charset=utf-8'],
    '/no-ip-input.svg': ['no-ip-input.svg', 'image/svg+xml'] };
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
  /* EventSource will reconnect if its peer has disappeared. */
  this.set(1000);
});

uloop.timer(15000, function() { emit('heartbeat', { alive: true }); this.set(15000); });

printf('portsdown-ucd listening on 127.0.0.1:%d\n', port);
uloop.run();
server.close();
uloop.done();
