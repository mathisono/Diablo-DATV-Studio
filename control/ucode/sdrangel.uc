import * as fs from 'fs';

export function status(supervisor, cfg) {
  let line = supervisor?.status ?? '';
  let enabled = index(line, 'board=sdrangel ') >= 0;
  let path = getenv('PORTSDOWN_SDRANGEL_PROFILE');
  let dir = getenv('PORTSDOWN_RUN_DIR') ?? '/run/portsdown';
  let profile = null;
  if (enabled && path && substr(path, 0, 1) == '/') {
    try { profile = json(fs.readfile(path) ?? 'null'); } catch (e) { profile = null; }
  }
  let result = { enabled, profile_configured: type(profile) == 'object',
    tx_configured: type(profile?.tx?.[cfg?.modulation]) == 'object',
    rx_configured: type(profile?.rx) == 'object' };
  for (let role in ['tx', 'rx']) {
    result[role] = { state: 'unknown' };
    if (!enabled || !supervisor?.ok) continue;
    let pid = match(line, new RegExp(role + '_pid=([0-9]+)'));
    if (!pid) continue;
    if (+pid[1] == 0) { result[role] = { state: 'stopped' }; continue; }
    try {
      let data = json(fs.readfile(dir + '/sdrangel-' + role + '.json') ?? 'null');
      if (type(data) == 'object' && data.pid == +pid[1] &&
          type(data.updated) == 'int' && time() >= data.updated && time() - data.updated <= 4)
        result[role] = data;
    } catch (e) { /* Missing, stale or invalid telemetry remains unknown. */ }
  }
  return result;
}
