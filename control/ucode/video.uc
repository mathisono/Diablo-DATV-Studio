import * as socket from 'socket';
import * as uloop from 'uloop';

const soi = '\xFF\xD8';
const eoi = '\xFF\xD9';
const max_frame = 128 * 1024;
let latest = null;
let producer = null;
let producer_handle = null;
let buffer = '';
let viewers = [];
let frames = 0;

export function stats() { return { frames: frames, producer: producer != null, viewers: length(viewers) }; }

function send_frame(peer, jpeg) {
  let packet = `--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ${length(jpeg)}\r\n\r\n${jpeg}\r\n`;
  return peer.send(packet, socket.MSG_DONTWAIT) == length(packet);
}

export function subscribe(peer) {
  if (length(viewers) >= 16) return false;
  if (latest != null && !send_frame(peer, latest)) { peer.close(); return false; }
  push(viewers, peer);
  return true;
}

function publish(jpeg) {
  latest = jpeg;
  frames++;
  let live = [];
  for (let viewer in viewers) {
    if (send_frame(viewer, jpeg)) push(live, viewer);
    else viewer.close();
  }
  viewers = live;
}

function consume(chunk) {
  buffer += chunk;
  while (true) {
    let begin = index(buffer, soi);
    if (begin < 0) { buffer = substr(buffer, -1) == '\xFF' ? '\xFF' : ''; return; }
    if (begin > 0) buffer = substr(buffer, begin);
    let end = index(buffer, eoi, 2);
    if (end < 0) {
      if (length(buffer) > max_frame) buffer = '';
      return;
    }
    let size = end + 2;
    if (size <= max_frame) publish(substr(buffer, 0, size));
    buffer = substr(buffer, size);
  }
}

export function start(port) {
  let server = socket.listen('127.0.0.1', port ?? 8082,
    { family: socket.AF_INET, socktype: socket.SOCK_STREAM }, 2, true);
  if (!server) return null;
  uloop.handle(server, () => {
    let next = server.accept(null, socket.SOCK_NONBLOCK | socket.SOCK_CLOEXEC);
    if (!next) return;
    if (producer_handle) producer_handle.delete();
    if (producer) producer.close();
    producer = next;
    buffer = '';
    producer_handle = uloop.handle(producer, () => {
      let chunk = producer.recv(32768, socket.MSG_DONTWAIT);
      if (!chunk) { producer_handle.delete(); producer.close(); producer = null; buffer = ''; return; }
      consume(chunk);
    }, uloop.ULOOP_READ);
  }, uloop.ULOOP_READ);
  return server;
}
