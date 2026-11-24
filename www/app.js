'use strict';
const $ = id => document.getElementById(id);
const fields = ['modeoutput','modeinput','modulation','encoding','format','freqoutput','symbolrate','fec','explevel','plutopwr','limegain','asi_device','asi_channel','asi_bitrate','expresshdmidevice','expressaudiodevice'];
const fecS = ['12','23','34','56','78'];
const fecS2 = ['14','13','12','35','23','34','56','89','91'];
let capabilities = {}, current = {};
let logInitialized = false;
let srtLocked = false;
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
  refreshBoardFields();
}
function refreshFec() {
  const selected = $('fec').value || current.fec;
  choices('fec', ($('modulation').value==='ASI' ? [] : $('modulation').value==='S2QPSK' ? fecS2 : fecS).map(v => [v,v]), selected);
}
function refreshBoardFields() {
  const board = $('modeoutput').value;
  const asi = board === 'DEKTEC_ASI';
  for (const el of document.querySelectorAll('.asi-only')) el.hidden = !asi;
  for (const el of document.querySelectorAll('.rf-only')) el.hidden = asi;
  for (const el of document.querySelectorAll('.express-only')) el.hidden = !board.startsWith('DATVEXPRESS');
  for (const el of document.querySelectorAll('.pluto-only')) el.hidden = board !== 'PLUTO';
  for (const el of document.querySelectorAll('.lime-only')) el.hidden = !board.startsWith('LIME');
  $('modulation-label').textContent = asi ? 'Transport output' : 'Modulation';
  for (const id of ['freqoutput','symbolrate']) $(id).required = !asi;
  for (const id of ['asi_device','asi_channel','asi_bitrate']) $(id).required = asi;
  if (asi) {
    for (const [id,value] of Object.entries({asi_device:'0',asi_channel:'0',asi_bitrate:'3071588'}))
      if (!$(id).value) $(id).value = value;
  }
  refreshSourceFields();
}
function refreshSourceFields() {
  const hdmi = $('modeinput').value === 'HDMI';
  $('srt-details').open = $('modeinput').value === 'SRT';
  for (const el of document.querySelectorAll('.hdmi-only')) el.hidden = !hdmi;
  $('expresshdmidevice').required = hdmi;
  const route = $('route-summary');
  route.hidden = !(hdmi && $('modeoutput').value === 'DEKTEC_ASI');
  const codec = $('encoding').value === 'H264' ? 'H.264' : $('encoding').value;
  route.textContent = `Elgato HDMI → ${codec} MPEG-TS → DekTec ASI → external modulator (configuration example; live ASI capture is not integrated yet).`;
  const placeholder = $('video-placeholder');
  placeholder.src = hdmi ? '/no-hdmi-input.svg' : '/no-ip-input.svg';
  placeholder.alt = hdmi ? 'NO HDMI INPUT' : 'NO IP INPUT';
}
function fill(config, updateCurrent=true) {
  if (updateCurrent) current = config;
  choices('modeoutput', Object.entries(capabilities).map(([id,cap])=>[id,cap.label]), config.modeoutput);
  choices('modulation', (capabilities[config.modeoutput]?.modulation || []).map(mode => [mode,mode]), config.modulation);
  choices('modeinput', [
    ['CAMH264','Pi Camera'],['ANALOGCAM','NTSC composite'],['WEBCAMH264','Webcam'],
    ['CARDH264','Test card'],['HDMI','Elgato HDMI'],['DESKTOP','Desktop'],['SRT','SRT input'],
    ['IPTSIN','IP transport stream'],['IPTSIN264','IPTS H.264'],['IPTSIN265','IPTS H.265']
  ], config.modeinput);
  choices('encoding', ['MPEG-2','H264','H265','IPTS in','IPTS in H264','IPTS in H265'].map(v=>[v,v]), config.encoding);
  choices('format', ['4:3','16:9','720p','1080p'].map(v=>[v,v]), config.format);
  choices('fec', (config.modulation==='ASI' ? [] : config.modulation==='S2QPSK' ? fecS2 : fecS).map(v => [v,v]), config.fec);
  for (const id of fields.filter(x => !['modeoutput','modeinput','modulation','encoding','format','fec'].includes(x)))
    $(id).value = config[id] ?? '';
  refreshBoardFields();
}
async function reload() {
  const result = await api('/api/config'); capabilities = result.capabilities; fill(result.config);
  const state = await api('/api/state'); showState(state);
}
function showState(state) {
  $('connection').textContent = state.supervisor?.ok ? 'Supervisor connected' : 'Supervisor unavailable';
  const supervisorStatus = state.supervisor?.status || '';
  const supervisorBoard = /board=([^ ]+)/.exec(supervisorStatus)?.[1];
  const expectedBoard = state.board?.startsWith('DATVEXPRESS') ? 'express' : state.board === 'PLUTO' ? 'pluto' : state.board?.startsWith('LIME') ? 'lime' : state.board === 'DEKTEC_ASI' ? 'dektec_asi' : null;
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
  srtLocked = locked;
  if (state.srt) showSrt(state.srt);
}
function showSrt(slots) {
  for (const slot of slots) {
    const n = slot.slot;
    const button = $(`srt-toggle-${n}`);
    const live = $(`srt-live-${n}`);
    const placeholder = $(`srt-placeholder-${n}`);
    const status = $(`srt-status-${n}`);
    const endpoint = `/api/video/srt/${n}`;
    button.textContent = slot.enabled ? 'Disable listener' : 'Enable listener';
    button.disabled = srtLocked;
    button.dataset.enabled = slot.enabled ? '1' : '0';
    if (slot.enabled && !live.getAttribute('src')) live.src = endpoint;
    if (!slot.enabled && live.getAttribute('src')) live.removeAttribute('src');
    placeholder.hidden = !!slot.live;
    status.textContent = !slot.enabled ? 'Disabled' : slot.live ? 'Live SRT video' : 'Enabled · awaiting video';
    $(`srt-meta-${n}`).textContent = `SRT UDP ${slot.srt_port} → live TS UDP 127.0.0.1:${slot.ts_port}`;
  }
}
for (let n=1;n<=5;n++) {
  const card=document.createElement('article');
  card.className='srt-card';
  card.innerHTML=`<h3>SRT input ${n}</h3><div class="preview"><img id="srt-live-${n}" alt="Live SRT input ${n} preview"><img id="srt-placeholder-${n}" class="placeholder" src="/no-srt-input-${n}.jpg" alt="NO SRT INPUT ${n} test pattern"></div><p id="srt-status-${n}" class="status" role="status">Disabled</p><p id="srt-meta-${n}" class="meta"></p><button id="srt-toggle-${n}" type="button">Enable listener</button>`;
  $('srt-slots').append(card);
  $(`srt-toggle-${n}`).addEventListener('click', async () => {
    const action=$(`srt-toggle-${n}`).dataset.enabled==='1'?'disable':'enable';
    try { await api(`/api/srt/${n}/${action}`,'POST'); showSrt((await api('/api/srt')).slots); }
    catch(error) { log(`SRT ${n}: ${error.message}`); }
  });
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
$('modeinput').addEventListener('change',refreshSourceFields);
$('encoding').addEventListener('change',refreshSourceFields);
$('modulation').addEventListener('change',refreshFec);
$('settings').addEventListener('submit',async event => {
  event.preventDefault();
  const changed = Object.fromEntries(fields.map(id => [id,$(id).value]).filter(([id,value])=>(value!=='' || id==='expressaudiodevice') && value!==(current[id]??'')));
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
setInterval(async () => { try { showSrt((await api('/api/srt')).slots); } catch {} }, 1000);
