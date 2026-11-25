import * as fs from 'fs';

/* Camera credentials are stored outside the legacy, often world-readable
 * portsdown_config.txt. config-store creates a new file mode 0600. */
export function load(path) {
  let result = { '1': '', '2': '' };
  let data = fs.readfile(path);
  if (data == null) return result;
  for (let line in split(data, '\n')) {
    let at = index(line, '=');
    if (at < 1) continue;
    let key = substr(line, 0, at);
    if (key == 'ipcam1' || key == 'ipcam2')
      result[substr(key, -1)] = substr(line, at + 1);
  }
  return result;
}

export function save(path, store, slot, url) {
  if (slot != '1' && slot != '2') return 'Invalid IP camera slot';
  if (type(url) != 'string' || length(url) > 1024 ||
      (url != '' && !match(url, /^rtsp:\/\/[^\/?#[:space:]]+(\/[^[:space:]]*)?$/)) ||
      match(url, /[[:cntrl:]]/))
    return 'Enter a valid rtsp:// camera URL (at most 1024 bytes)';
  let existing = fs.stat(path);
  if (existing && (existing.type != 'file' || (existing.mode & 077) != 0))
    return 'IP camera config must be a private file (mode 0600)';
  let cameras = load(path);
  cameras[slot] = url;
  let payload = `ipcam1=${cameras['1']}\nipcam2=${cameras['2']}\n`;
  let proc = fs.popen([store, path], 'w');
  if (!proc) return 'Cannot open private camera config writer';
  let count = proc.write(payload);
  let rc = proc.close();
  return count == length(payload) && rc == 0 ? null : 'Cannot save private camera config';
}
