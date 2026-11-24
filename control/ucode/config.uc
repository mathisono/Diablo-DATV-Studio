import * as fs from 'fs';

/* Only expose settings for which this development branch has a known route. */
export const capabilities = {
  DATVEXPRESS: { label: 'DATV-Express', modulation: ['DVB-S', 'S2QPSK'],
    min_mhz: 100, max_mhz: 3000, min_ksym: 100, max_ksym: 10000 },
  DATVEXPRESS_S2: { label: 'DATV-Express S2 experimental', modulation: ['S2QPSK'],
    min_mhz: 100, max_mhz: 3000, min_ksym: 100, max_ksym: 10000 },
  PLUTO: { label: 'ADALM Pluto (legacy path)', modulation: ['DVB-S', 'S2QPSK'],
    min_mhz: 325, max_mhz: 3800, min_ksym: 100, max_ksym: 5000 },
  LIMEMINI: { label: 'LimeSDR Mini (legacy path)', modulation: ['DVB-S', 'S2QPSK'],
    min_mhz: 30, max_mhz: 3500, min_ksym: 100, max_ksym: 5000 },
  DEKTEC_ASI: { label: 'DekTec DTA-2145 ASI', modulation: ['ASI'],
    transport: 'asi' }
};

const fec_s = ['12', '23', '34', '56', '78'];
const fec_s2 = ['14', '13', '12', '35', '23', '34', '56', '89', '91'];
const sources = ['CAMH264','ANALOGCAM','WEBCAMH264','CARDH264','DESKTOP','SRT',
  'IPTSIN','IPTSIN264','IPTSIN265'];
const formats = ['4:3','16:9','720p','1080p'];
const encoders = ['MPEG-2','H264','H265','IPTS in','IPTS in H264','IPTS in H265'];
const mutable = ['modeoutput', 'modeinput', 'modulation', 'freqoutput', 'symbolrate',
  'fec', 'format', 'encoding', 'explevel', 'plutopwr', 'limegain', 'streamurl', 'streamkey',
  'asi_device', 'asi_channel', 'asi_bitrate'];

export function load(path) {
  let raw = fs.readfile(path);
  if (raw == null) return null;
  let cfg = {};
  for (let line in split(raw, '\n')) {
    if (!line || substr(line, 0, 1) == '#') continue;
    let at = index(line, '=');
    if (at < 1) continue;
    cfg[trim(substr(line, 0, at))] = trim(substr(line, at + 1));
  }
  return cfg;
}

export function validate(cfg) {
  let cap = capabilities[cfg.modeoutput];
  if (!cap) return 'unsupported output board';
  if (cap.transport == 'asi') {
    if (cfg.modulation != 'ASI') return 'ASI output requires ASI mode';
    if (!match(cfg.asi_device ?? '', /^[0-9]{1,2}$/) || +cfg.asi_device > 15)
      return 'ASI device index outside 0-15';
    if (!match(cfg.asi_channel ?? '', /^[0-9]{1,2}$/) || +cfg.asi_channel > 15)
      return 'ASI channel index outside 0-15';
    if (!match(cfg.asi_bitrate ?? '', /^[0-9]+$/) || +cfg.asi_bitrate < 100000 || +cfg.asi_bitrate > 214000000)
      return 'ASI transport bitrate outside 100000-214000000 bit/s';
  } else {
    let mod = cfg.modulation == 'S2QPSK' ? 'S2QPSK' :
      cfg.modulation == 'DVB-S' || cfg.modulation == 'QPSK' ? 'DVB-S' : null;
    if (!mod || index(cap.modulation, mod) < 0) return 'unsupported modulation for board';
    let mhz = +cfg.freqoutput, sr = +cfg.symbolrate;
    if (!match(cfg.freqoutput, /^[0-9]+(\.[0-9]+)?$/) || mhz < cap.min_mhz || mhz > cap.max_mhz) return 'frequency outside board range';
    if (!match(cfg.symbolrate, /^[0-9]+$/) || sr < cap.min_ksym || sr > cap.max_ksym) return 'symbol rate outside board range';
    if (index(mod == 'S2QPSK' ? fec_s2 : fec_s, cfg.fec) < 0) return 'unsupported FEC';
  }
  if (cfg.modeinput != null && index(sources, cfg.modeinput) < 0) return 'unsupported source';
  if (cfg.format != null && index(formats, cfg.format) < 0) return 'unsupported format';
  if (cfg.encoding != null && index(encoders, cfg.encoding) < 0) return 'unsupported encoder';
  if (cfg.explevel != null && (!match(cfg.explevel, /^[0-9]+$/) || +cfg.explevel > 44)) return 'Express level outside 0-44';
  if (cfg.plutopwr != null && (!match(cfg.plutopwr, /^[0-9]+$/) || +cfg.plutopwr > 71)) return 'Pluto attenuation outside 0-71';
  if (cfg.limegain != null && (!match(cfg.limegain, /^[0-9]+$/) || +cfg.limegain > 100)) return 'Lime gain outside 0-100';
  return null;
}

export function update(path, store, changes) {
  if (type(changes) != 'object') return 'JSON object required';
  let cfg = load(path);
  if (!cfg) return 'cannot read configuration';
  for (let k, v in changes) {
    if (index(mutable, k) < 0 || type(v) != 'string' && type(v) != 'number') return `unsupported field: ${k}`;
    let value = '' + v;
    if (index(value, '\n') >= 0 || index(value, '\r') >= 0 || length(value) > 256)
      return `invalid value: ${k}`;
    cfg[k] = value;
  }
  let error = validate(cfg);
  if (error) return error;
  /* Keep comments, unknown keys, and ordering in the legacy config file. */
  let data = '', seen = {};
  let original = fs.readfile(path);
  if (original == null) return 'cannot reread configuration';
  let lines = split(original, '\n');
  for (let i, line in lines) {
    if (i == length(lines) - 1 && line == '') break;
    let at = index(line, '=');
    let key = at > 0 ? trim(substr(line, 0, at)) : null;
    if (key != null && changes[key] != null) {
      data += `${key}=${cfg[key]}\n`; seen[key] = true;
    } else data += line + '\n';
  }
  for (let k, v in changes) if (!seen[k]) data += `${k}=${cfg[k]}\n`;
  let proc = fs.popen([store, path], 'w');
  if (!proc) return 'cannot start atomic config writer';
  let wrote = proc.write(data);
  let rc = proc.close();
  return wrote == length(data) && rc == 0 ? null : 'atomic config write failed';
}
