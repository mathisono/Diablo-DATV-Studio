import * as fs from 'fs';
import * as config from 'config';

export function load(path) {
  let data = fs.readfile(path);
  if (!data) return {};
  let saved = json(data);
  return type(saved) == 'object' ? saved : {};
}

export function save(path, store, slot, values) {
  if (!match(slot, /^[1-4]$/) || type(values) != 'object') return 'invalid preset';
  let allowed = ['modeoutput','modeinput','modulation','freqoutput','symbolrate','fec',
    'format','encoding','explevel','plutopwr','limegain',
    'asi_device','asi_channel','asi_bitrate'];
  let clean = {};
  for (let key, value in values) {
    if (index(allowed, key) < 0 || type(value) != 'string' && type(value) != 'number') return `unsupported field: ${key}`;
    clean[key] = '' + value;
  }
  let error = config.validate(clean);
  if (error) return error;
  let saved = load(path);
  saved[slot] = clean;
  let data = sprintf('%J\n', saved);
  let proc = fs.popen([store, path], 'w');
  if (!proc) return 'cannot start atomic preset writer';
  let wrote = proc.write(data);
  let rc = proc.close();
  return wrote == length(data) && rc == 0 ? null : 'preset write failed';
}
