/* Offline first-start edits use the same validation/atomic writer as the GUI. */
import * as config from 'config';
const path = getenv('PORTSDOWN_CONFIG');
const changes = {};
for (let key in ['call','service_name','modeinput','srt_source_slot','expresshdmidevice','expressaudiodevice','picam_index','ipts_input_port','ipts_bind_scope']) {
  let value = getenv(`DIABLO_SETUP_${key}`);
  if (value != null && (value != '' || key == 'expressaudiodevice')) changes[key] = value;
}
if (getenv('DIABLO_SETUP_RESET_LAYOUT') == '1') changes.source_layout = 'DIRECT';
let current = config.load(path);
if (!current) die('Cannot read installed config\n');
for (let key, value in changes) current[key] = value;
let error = config.validate(current);
if (error) die(`Setup configuration rejected: ${error}\n`);
if (getenv('DIABLO_SETUP_VALIDATE_ONLY') == '1') exit(0);
error = config.update(path, `${getenv('PORTSDOWN_DIR')}/control/config-store`, changes);
if (error) die(`Setup configuration not saved: ${error}\n`);
print('Initial source and station settings saved.\n');
