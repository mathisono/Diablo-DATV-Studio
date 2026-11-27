import * as fs from 'fs';
import * as uloop from 'uloop';
let job = null;

let path = null, helper = null, clients = {}, next_attempt = 0, failures = 0;
let lifetime = +(getenv('PORTSDOWN_SESSION_SECONDS') ?? '28800');
if (lifetime < 5 || lifetime > 28800) die('Session lifetime must be 5–28800 seconds');
export function enabled() { return path != null; }
export function start(file, executable) {
  if (!file) return;
  path = file; helper = executable;
  let proc = fs.popen([helper, 'peer-key', path], 'r');
  let key = proc ? trim(proc.read(256) ?? '') : '';
  if (!proc || proc.close() != 0 || !match(key, /^[0-9a-f]{64}$/))
    die('Invalid private shared-password record; run first-start setup');
}
function discard(id) {
  for (let socket in clients[id]?.streams ?? []) socket.close();
  delete clients[id];
}
export function expire() {
  for (let id, client in clients) if (client.until <= time()) discard(id);
}
export function identity(cookie) {
  expire();
  for (let item in split(cookie ?? '', ';')) {
    let pair = split(trim(item), '=');
    if (pair[0] == 'diablo_session' && clients[pair[1]]) return pair[1];
  }
  return null;
}
export function retain(id, socket) {
  if (!id) return true;
  let entry = clients[id];
  if (!entry) return false;
  entry.streams = filter(entry.streams, s => s.fileno() != null);
  if (length(entry.streams) >= 64) return false;
  push(entry.streams, socket);return true;
}
export function logout(id) { if (id) discard(id); }
function session() {
  if (length(clients) >= 32) return { status: '503 Service Unavailable', error: 'Too many signed-in sessions' };
  let random = fs.open('/dev/urandom', 'r');
  let raw = random ? random.read(32) : null;
  if (random) random.close();
  if (!raw || length(raw) != 32) return { status: '503 Service Unavailable', error: 'Login unavailable' };
  let id = '';
  for (let i = 0; i < length(raw); i++) id += sprintf('%02x', ord(substr(raw, i, 1)));
  clients[id] = { until: time() + lifetime, streams: [] };
  return { status: '200 OK', cookie: `diablo_session=${id}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${lifetime}` };
}

/* PBKDF2 is deliberately expensive. Run it outside the control event loop;
 * one bounded worker prevents login attempts from stalling peer heartbeats. */
export function login(password, reply) {
  expire();
  if (job || time() < next_attempt)
    return reply({ status: '429 Too Many Requests', error: 'Please wait before trying again' });
  next_attempt = time() + 1;
  if (type(password) != 'string' || length(password) < 8 || length(password) > 128)
    return reply({ status: '401 Unauthorized', error: 'Incorrect password' });
  let finished = false;
  let timer = uloop.timer(10000, () => {
    if (finished) return;
    finished = true;
    if (job) job.kill();
    job = null;
    reply({ status: '503 Service Unavailable', error: 'Login timed out' });
  });
  job = uloop.task(() => {
    let proc = fs.popen([helper, 'verify', path], 'w');
    if (!proc) return false;
    let written = proc.write(password);
    let rc = proc.close();
    return written == length(password) && rc == 0;
  }, (ok) => {
    if (finished) return;
    finished = true; timer.cancel(); job = null;
    if (!ok) {
      failures++;
      next_attempt = time() + (failures >= 5 ? 30 : 1);
      return reply({ status: '401 Unauthorized', error: 'Incorrect password' });
    }
    failures = 0;
    reply(session());
  });
  password = null;
  if (!job) {
    finished = true; timer.cancel();
    reply({ status: '503 Service Unavailable', error: 'Login unavailable' });
  }
}
