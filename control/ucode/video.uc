import * as socket from 'socket';
import * as uloop from 'uloop';

const soi = '\xFF\xD8';
const eoi = '\xFF\xD9';
const max_frame = 128 * 1024;
let channels = {};

function channel(slot) { return channels[slot ?? 0]; }

export function stats(slot) {
  let c = channel(slot);
  if (!c) return { frames: 0, producer: false, viewers: 0 };
  /* A connected but stalled encoder must not look like live video. */
  return { frames: c.frames, producer: c.producer != null && c.last_frame > 0 && time() - c.last_frame < 3,
    viewers: length(c.viewers) };
}

function send_frame(peer, jpeg) {
  let packet = `--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ${length(jpeg)}\r\n\r\n${jpeg}\r\n`;
  return peer.send(packet, socket.MSG_DONTWAIT) == length(packet);
}

export function subscribe(peer, slot) {
  let c = channel(slot);
  if (!c || length(c.viewers) >= 16) return false;
  let first = stats(slot).producer ? c.latest : c.enabled ? c.fallback : null;
  if (first != null && !send_frame(peer, first)) { peer.close(); return false; }
  push(c.viewers, peer);
  return true;
}

export function set_fallback(slot, jpeg) {
  let c = channel(slot);
  if (!c || !jpeg || length(jpeg) > max_frame || index(jpeg, soi) != 0 || index(jpeg, eoi) < 0) return false;
  c.fallback = jpeg;
  return true;
}

/* Called once per second. Idle cards never update live-video timestamps. */
export function tick(slot, enabled) {
  let c = channel(slot);
  if (!c) return;
  c.enabled = enabled;
  if (!enabled || stats(slot).producer || !c.fallback) return;
  let live = [];
  for (let viewer in c.viewers) {
    if (send_frame(viewer, c.fallback)) push(live, viewer);
    else viewer.close();
  }
  c.viewers = live;
}

function publish(c, jpeg) {
  c.latest = jpeg;
  c.frames++;
  c.last_frame = time();
  let live = [];
  for (let viewer in c.viewers) {
    if (send_frame(viewer, jpeg)) push(live, viewer);
    else viewer.close();
  }
  c.viewers = live;
}

function consume(c, chunk) {
  c.buffer += chunk;
  while (true) {
    let begin = index(c.buffer, soi);
    if (begin < 0) { c.buffer = substr(c.buffer, -1) == '\xFF' ? '\xFF' : ''; return; }
    if (begin > 0) c.buffer = substr(c.buffer, begin);
    let end = index(c.buffer, eoi, 2);
    if (end < 0) {
      if (length(c.buffer) > max_frame) c.buffer = '';
      return;
    }
    let size = end + 2;
    if (size <= max_frame) publish(c, substr(c.buffer, 0, size));
    c.buffer = substr(c.buffer, size);
  }
}

export function start(port, slot) {
  slot ??= 0;
  if (channel(slot)) return null;
  let server = socket.listen('127.0.0.1', port ?? 8082,
    { family: socket.AF_INET, socktype: socket.SOCK_STREAM }, 2, true);
  if (!server) return null;
  let c = { latest: null, producer: null, producer_handle: null, buffer: '', viewers: [], frames: 0,
    last_frame: 0, enabled: false, fallback: null };
  channels[slot] = c;
  uloop.handle(server, () => {
    let next = server.accept(null, socket.SOCK_NONBLOCK | socket.SOCK_CLOEXEC);
    if (!next) return;
    if (c.producer_handle) c.producer_handle.delete();
    if (c.producer) c.producer.close();
    c.producer = next;
    c.buffer = '';
    c.latest = null;
    c.last_frame = 0;
    c.producer_handle = uloop.handle(c.producer, () => {
      let chunk = c.producer.recv(32768, socket.MSG_DONTWAIT);
      if (!chunk) {
        c.producer_handle.delete(); c.producer.close(); c.producer = null;
        c.buffer = ''; c.latest = null; c.last_frame = 0; return;
      }
      consume(c, chunk);
    }, uloop.ULOOP_READ);
  }, uloop.ULOOP_READ);
  return server;
}
