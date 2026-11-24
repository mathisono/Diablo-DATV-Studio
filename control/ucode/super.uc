import * as socket from 'socket';
import * as uloop from 'uloop';

export function request(path, command) {
  let peer = socket.connect({ path: path }, null, null, 1000);
  if (!peer) return { ok: false, message: 'supervisor unavailable' };
  if (peer.send(command + '\n') == null) { peer.close(); return { ok: false, message: 'supervisor write failed' }; }
  let text = '';
  for (let i = 0; i < 8; i++) {
    let chunk = peer.recv(2048);
    if (!chunk) break;
    text += chunk;
    for (let line in split(text, '\n')) {
      if (substr(line, 0, 3) == 'OK\n' || line == 'OK') { peer.close(); return { ok: true }; }
      if (substr(line, 0, 4) == 'ERR ') { peer.close(); return { ok: false, message: substr(line, 4) }; }
      if (substr(line, 0, 7) == 'STATUS ') { peer.close(); return { ok: true, status: line }; }
    }
  }
  peer.close();
  return { ok: false, message: 'supervisor did not respond' };
}

export function subscribe(path, on_line) {
  let peer = socket.connect({ path: path }, null, null, 1000);
  if (!peer) return null;
  let pending = '';
  let handle;
  handle = uloop.handle(peer, () => {
    let chunk = peer.recv(4096, socket.MSG_DONTWAIT);
    if (!chunk) { handle.delete(); peer.close(); return; }
    pending += chunk;
    if (length(pending) > 8192) pending = '';
    let pos;
    while ((pos = index(pending, '\n')) >= 0) {
      on_line(substr(pending, 0, pos));
      pending = substr(pending, pos + 1);
    }
  }, uloop.ULOOP_READ);
  return { socket: peer, handle: handle };
}
