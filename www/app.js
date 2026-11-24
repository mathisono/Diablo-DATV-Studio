'use strict';
const $ = id => document.getElementById(id);
const fields = ['modeoutput','modeinput','modulation','encoding','format','freqoutput','symbolrate','fec','explevel','plutopwr','limegain'];
const fecS = ['12','23','34','56','78'];
const fecS2 = ['14','13','12','35','23','34','56','89','91'];
let capabilities = {}, current = {};
let logInitialized = false;
function log(message) {
  const node = $('log');
  node.textContent = `${new Date().toLocaleTimeString()} ${message}\n` + node.textContent.slice(0, 10000);
}
async function api(path, method='GET', data) {
  const reply = await fetch(path, { method, headers: { 'Content-Type':'application/json', 'X-Portsdown-Control':'1' },
    body: data ? JSON.stringify(data) : undefined });
  const result = await reply.json();
  if (!reply.ok) throw Error(result.error || result.message || `HTTP ${reply.status}`);
  return result;
}
function choices(id, items, selected) {
  $(id).replaceChildren(...items.map(([value,label]) => {
    const option = document.createElement('option'); option.value=value; option.textContent=label; option.selected=value===selected; return option;
  }));
}
function refreshMode() {
  const cap = capabilities[$('modeoutput').value];
  choices('modulation', (cap?.modulation || []).map(mode => [mode,mode]), current.modulation);
  refreshFec();
}
function refreshFec() {
  const selected = $('fec').value || current.fec;
  choices('fec', ($('modulation').value==='S2QPSK' ? fecS2 : fecS).map(v => [v,v]), selected);
}
function fill(config, updateCurrent=true) {
  if (updateCurrent) current = config;
  choices('modeoutput', Object.entries(capabilities).map(([id,cap])=>[id,cap.label]), config.modeoutput);
  choices('modulation', (capabilities[config.modeoutput]?.modulation || []).map(mode => [mode,mode]), config.modulation);
  choices('modeinput', [
    ['CAMH264','Pi Camera'],['ANALOGCAM','NTSC composite'],['WEBCAMH264','Webcam'],
    ['CARDH264','Test card / HDMI'],['DESKTOP','Desktop'],['SRT','SRT input'],
    ['IPTSIN','IP transport stream'],['IPTSIN264','IPTS H.264'],['IPTSIN265','IPTS H.265']
  ], config.modeinput);
  choices('encoding', ['MPEG-2','H264','H265','IPTS in','IPTS in H264','IPTS in H265'].map(v=>[v,v]), config.encoding);
  choices('format', ['4:3','16:9','720p','1080p'].map(v=>[v,v]), config.format);
  choices('fec', (config.modulation==='S2QPSK' ? fecS2 : fecS).map(v => [v,v]), config.fec);
  for (const id of fields.filter(x => !['modeoutput','modeinput','modulation','encoding','format','fec'].includes(x)))
    $(id).value = config[id] ?? '';
}
async function reload() {
  const result = await api('/api/config'); capabilities = result.capabilities; fill(result.config);
  const state = await api('/api/state'); showState(state);
}
function showState(state) {
  $('connection').textContent = state.supervisor?.ok ? 'Supervisor connected' : 'Supervisor unavailable';
  const supervisorStatus = state.supervisor?.status || '';
  const supervisorBoard = /board=([^ ]+)/.exec(supervisorStatus)?.[1];
  const expectedBoard = state.board?.startsWith('DATVEXPRESS') ? 'express' : state.board === 'PLUTO' ? 'pluto' : state.board?.startsWith('LIME') ? 'lime' : null;
  const boardReady = expectedBoard && supervisorBoard === expectedBoard;
  $('tx-status').textContent = !boardReady && state.peer_role !== 'MASTER'
    ? `TX disabled: configured ${state.board} does not match supervisor ${supervisorBoard || 'unavailable'}.`
    : supervisorStatus || state.supervisor?.message || 'Unknown';
  $('video-status').textContent = state.video?.producer ? `MJPEG live · ${state.video.frames} frames` : 'Waiting for MJPEG source';
  $('video-placeholder').hidden = !!state.video?.producer;
  $('peer-status').textContent = `${state.peer_role || 'STANDALONE'} · ${state.peer?.connected ? 'linked' : 'not linked'}${state.peer?.config_ready ? ' · config ready' : ''}`;
  if (!logInitialized && state.logs) {
    $('log').textContent = state.logs.join('\n');
    logInitialized = true;
  }
  const remote = state.remote_preview_url;
  $('remote-preview-box').hidden = !remote;
  if (remote && $('remote-preview').src !== remote) $('remote-preview').src = remote;
  const locked = state.peer_role === 'SLAVE';
  $('tx-start').disabled = locked || (state.peer_role === 'MASTER' ? !state.peer?.config_ready : !boardReady || !state.supervisor?.ok);
  for (const id of ['rx-start','rx-stop']) $(id).disabled = locked;
  for (const id of fields) $(id).disabled = locked;
  $('settings').querySelector('button[type=submit]').disabled = locked;
  for (const button of $('presets').querySelectorAll('button')) button.disabled = locked;
}
async function command(path) {
  try { const result = await api(path,'POST'); log(`${path}: ${JSON.stringify(result)}`); showState(await api('/api/state')); }
  catch (error) { log(`${path}: ${error.message}`); }
}
for (const [id,path] of Object.entries({
  'tx-start':'/api/tx/start','tx-stop':'/api/tx/stop',
  'rx-start':'/api/rx/start','rx-stop':'/api/rx/stop'
})) $(id).addEventListener('click',()=>command(path));
$('modeoutput').addEventListener('change',refreshMode);
$('modulation').addEventListener('change',refreshFec);
$('settings').addEventListener('submit',async event => {
  event.preventDefault();
  const changed = Object.fromEntries(fields.map(id => [id,$(id).value]).filter(([id,value])=>value!=='' && value!==(current[id]??'')));
  try { await api('/api/config','POST',changed); log('Configuration saved'); await reload(); }
  catch (error) { log(`Save failed: ${error.message}`); }
});
for (let i=1;i<=4;i++) {
  const loadButton=document.createElement('button'); loadButton.textContent=`Load ${i}`;
  loadButton.onclick=async()=>{ try { fill(await api(`/api/presets/${i}`),false); log(`Preset ${i} loaded; press Save configuration to apply`); } catch(error) { log(error.message); } };
  const saveButton=document.createElement('button'); saveButton.textContent=`Save ${i}`; saveButton.className='save';
  saveButton.onclick=async()=>{ try { await api(`/api/presets/${i}`,'POST',Object.fromEntries(fields.map(id=>[id,$(id).value]))); log(`Preset ${i} saved on this Portsdown`); } catch(error) { log(error.message); } };
  $('presets').append(loadButton,saveButton);
}
const events=new EventSource('/api/events');
events.addEventListener('state', async event=>{log(`State: ${event.data}`); try {showState(await api('/api/state'));} catch {} });
events.addEventListener('config',()=>reload().catch(error=>log(error.message)));
events.addEventListener('peer', async event=>{ log(`Peer: ${event.data}`); try { showState(await api('/api/state')); } catch {} });
events.addEventListener('log', event=>{ try { log(JSON.parse(event.data).line); } catch {} });
events.onerror=()=>{ $('connection').textContent='Event link reconnecting'; };
reload().catch(error=>log(error.message));
window.addEventListener('load', () => { $('live-preview').src = '/api/video'; });
