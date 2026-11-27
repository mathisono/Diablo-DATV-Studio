'use strict';
const $ = id => document.getElementById(id);
const fields = ['modeoutput','modeinput','source_layout','srt_source_slot','multiview_1','multiview_2','multiview_3','multiview_4','ipts_input_port','ipts_bind_scope','picam_index','modulation','encoding','format','freqoutput','symbolrate','fec','explevel','plutopwr','limegain','asi_device','asi_channel','asi_bitrate','expresshdmidevice','expressaudiodevice','call','service_name'];
const fecS = ['12','23','34','56','78'];
const fecS2 = ['14','13','12','35','23','34','56','89','91'];
let capabilities = {}, current = {};
let logInitialized = false;
let srtLocked = false;
let lastState = null;
let accessApplying = false;
let ipcamConfigured = {1:false, 2:false};
const multiviewOptions = [
  ['HDMI','USB HDMI capture'],['CAMH264','Pi Camera'],['IPTSIN','IPTS (UDP TS)'],
  ['IPCAM1','IP CAM 1 (RTSP)'],['IPCAM2','IP CAM 2 (RTSP)'],
  ...[1,2,3,4,5].map(n=>[`SRT${n}`,`SRT encoder ${n}`]),['CARDH264','Test card']
];
const previewSources = {
  HDMI: ['/api/video/source/hdmi','/no-hdmi-input.jpg'],
  CAMH264: ['/api/video/source/camera','/no-picam-input.jpg'],
  IPTSIN: ['/api/video/source/ipts','/no-ipts-input.jpg'],
  IPTSIN264: ['/api/video/source/ipts','/no-ipts-input.jpg'],
  IPTSIN265: ['/api/video/source/ipts','/no-ipts-input.jpg']
  ,IPCAM1: ['/api/video/source/ipcam1','/no-ipcam1-input.jpg']
  ,IPCAM2: ['/api/video/source/ipcam2','/no-ipcam2-input.jpg']
};
function log(message) {
  const node = $('log');
  node.textContent = `${new Date().toLocaleTimeString()} ${message}\n` + node.textContent.slice(0, 10000);
}
async function api(path, method='GET', data) {
  const reply = await fetch(path, { method, headers: { 'Content-Type':'application/json', 'X-Portsdown-Control':'1' },
    body: data ? JSON.stringify(data) : undefined });
  if (reply.status === 401) { if (!accessApplying) location.replace('/'); throw Error('Sign in required'); }
  const result = await reply.json();
  if (!reply.ok) throw Error(result.error || result.message || `HTTP ${reply.status}`);
  return result;
}
async function refreshIpCamStatus() {
  try {
    ipcamConfigured = (await api('/api/ipcam')).configured;
    if (lastState) showIpCam(lastState);
  } catch { for (let n=1;n<=2;n++) $('ipcam-status-'+n).textContent = 'Camera configuration unavailable'; }
}
function showIpCam(state) {
  for (let n=1;n<=2;n++) {
    const configured = !!ipcamConfigured[String(n)];
    const live = configured && !!state.sources?.[`IPCAM${n}`]?.preview?.producer;
    const image = $(`ipcam-live-${n}`);
    if (configured && !image.getAttribute('src')) image.src = `/api/video/source/ipcam${n}`;
    if (!configured && image.getAttribute('src')) image.removeAttribute('src');
    $(`ipcam-placeholder-${n}`).hidden = live;
    $(`ipcam-status-${n}`).textContent = !configured ? `IP CAM ${n} not configured` :
      live ? `IP CAM ${n} · live preview · URL hidden` : `IP CAM ${n} · awaiting video · URL hidden`;
    $(`ipcam-restart-${n}`).disabled = state.peer_role === 'SLAVE' || !configured;
  }
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
    refreshAsiFileStatus();
  }
  refreshSourceFields();
}
async function refreshAsiFileStatus() {
  if ($('modeoutput').value !== 'DEKTEC_ASI') return;
  const flag = $('asi-file-status');
  try {
    const info = await api('/api/asi/file-status');
    flag.classList.toggle('warning', info.state === 'mismatch');
    if (info.state === 'match') flag.textContent = `ASI file service metadata matches saved settings (${info.programs} service${info.programs === 1 ? '' : 's'}).`;
    else if (info.state === 'mismatch') flag.textContent = `ASI file metadata differs: provider “${info.observed_provider || '(missing)'}”, service “${info.observed_name || '(missing)'}”. Playout is allowed; configured labels will be applied when possible.`;
    else if (info.state === 'unconfigured') flag.textContent = 'No ASI file or service labels configured. Playout is not blocked by metadata.';
    else flag.textContent = 'ASI file metadata could not be checked. Playout is not blocked by metadata.';
  } catch { flag.textContent = 'ASI file metadata status unavailable. Playout is not blocked by metadata.'; }
}
function refreshSourceFields() {
  const multi = $('source_layout').value === 'MULTIVIEW';
  const selected = [1,2,3,4].map(n=>$(`multiview_${n}`).value);
  const hdmi = multi ? selected.includes('HDMI') : $('modeinput').value === 'HDMI';
  const picam = multi ? selected.includes('CAMH264') : $('modeinput').value === 'CAMH264';
  const ipts = multi ? selected.includes('IPTSIN') : $('modeinput').value.startsWith('IPTSIN');
  $('srt-details').open = multi ? selected.some(s=>s.startsWith('SRT')) : $('modeinput').value === 'SRT';
  for (const el of document.querySelectorAll('.direct-only')) el.hidden = multi;
  for (const el of document.querySelectorAll('.srt-direct-only')) el.hidden = multi || $('modeinput').value !== 'SRT';
  $('direct-preview').hidden = multi;
  $('multiview-preview').hidden = !multi;
  $('multiview-preview').classList.toggle('wide',['16:9','720p','1080p'].includes($('format').value));
  $('multiview-selectors').hidden = !multi;
  $('source-ts-controls').hidden = !multi && !['SRT','IPCAM1','IPCAM2'].includes($('modeinput').value);
  for (const el of document.querySelectorAll('.hdmi-only')) el.hidden = !hdmi;
  for (const el of document.querySelectorAll('.picam-only')) el.hidden = !picam;
  for (const el of document.querySelectorAll('.ipts-only')) el.hidden = !ipts;
  $('expresshdmidevice').required = hdmi;
  const route = $('route-summary');
  route.hidden = !(hdmi && $('modeoutput').value === 'DEKTEC_ASI');
  const codec = $('encoding').value === 'H264' ? 'H.264' : $('encoding').value;
  route.textContent = multi ? `HDMI is one multiview tile. The current low-rate composite TS is a local monitor source, not yet a live ${codec} → DekTec ASI transmitter route.` :
    `USB HDMI capture → ${codec} MPEG-TS → DekTec ASI → external modulator (configuration example; live ASI capture is not integrated yet).`;
  if (lastState) updatePreview(lastState);
}
function fill(config, updateCurrent=true) {
  if (updateCurrent) current = config;
  choices('modeoutput', Object.entries(capabilities).map(([id,cap])=>[id,cap.label]), config.modeoutput);
  choices('modulation', (capabilities[config.modeoutput]?.modulation || []).map(mode => [mode,mode]), config.modulation);
  choices('source_layout', [['DIRECT','One video input'],['MULTIVIEW','Four-source multiview']], config.source_layout || 'DIRECT');
  choices('modeinput', [
    ['CAMH264','Pi Camera'],['ANALOGCAM','NTSC composite'],['WEBCAMH264','Webcam'],
    ['CARDH264','Test card'],['HDMI','USB HDMI capture'],['DESKTOP','Desktop'],['SRT','SRT input'],
    ['IPCAM1','IP CAM 1 (RTSP)'],['IPCAM2','IP CAM 2 (RTSP)'],
    ['IPTSIN','IP transport stream'],['IPTSIN264','IPTS H.264'],['IPTSIN265','IPTS H.265']
  ], config.modeinput);
  choices('srt_source_slot', [1,2,3,4,5].map(n=>[String(n),`SRT encoder ${n}`]), config.srt_source_slot || '1');
  for (let n=1;n<=4;n++) choices(`multiview_${n}`,multiviewOptions,config[`multiview_${n}`] || `SRT${n}`);
  choices('ipts_bind_scope', [['LOCAL','Loopback only'],['LAN','LAN interfaces']],config.ipts_bind_scope || 'LOCAL');
  choices('encoding', ['MPEG-2','H264','H265','IPTS in','IPTS in H264','IPTS in H265'].map(v=>[v,v]), config.encoding);
  choices('format', ['4:3','16:9','720p','1080p'].map(v=>[v,v]), config.format);
  choices('fec', (config.modulation==='ASI' ? [] : config.modulation==='S2QPSK' ? fecS2 : fecS).map(v => [v,v]), config.fec);
  for (const id of fields.filter(x => !['modeoutput','modeinput','source_layout','srt_source_slot','multiview_1','multiview_2','multiview_3','multiview_4','ipts_bind_scope','modulation','encoding','format','fec'].includes(x)))
    $(id).value = config[id] ?? '';
  if (!$('ipts_input_port').value) $('ipts_input_port').value = '10000';
  if (!$('picam_index').value) $('picam_index').value = '0';
  if (!/^[A-Z0-9/]{3,20}$/.test($('call').value) || !/[0-9]/.test($('call').value))
    $('call').value = ''; // Old generic values such as BATC are not a station callsign.
  refreshBoardFields();
}
async function reload() {
  const result = await api('/api/config'); capabilities = result.capabilities; fill(result.config);
  await refreshIpCamStatus();
  const state = await api('/api/state'); showState(state);
}
function previewFor(source, state) {
  if (source?.startsWith('SRT')) {
    const slot=Number(source.slice(3));
    return {url:`/api/video/srt/${slot}`, card:`/no-srt-input-${slot}.jpg`,
      live:!!state.srt?.find(item=>item.slot===slot)?.live, label:`SRT encoder ${slot}`};
  }
  if (source === 'CARDH264') return {url:null,card:'/test-card.jpg',live:false,label:'Test card'};
  const mapped=previewSources[source];
  if (mapped) {
    const key=source.startsWith('IPTS')?'IPTSIN':source;
    const legacyHdmi=key==='HDMI' && !state.source_preview_available;
    return {url:legacyHdmi?'/api/video':mapped[0],card:mapped[1],
      live:legacyHdmi?!!state.video?.producer:!!state.sources?.[key]?.preview?.producer,
      label:key==='CAMH264'?'Pi Camera':key==='IPTSIN'?'IPTS':key==='IPCAM1'?'IP CAM 1':key==='IPCAM2'?'IP CAM 2':'HDMI'};
  }
  return {url:'/api/video',card:'/no-ip-input.svg',live:!!state.video?.producer,label:source||'Direct'};
}
function setImage(image, url) {
  if (!url) { image.removeAttribute('src'); return; }
  if (image.getAttribute('src') !== url) image.setAttribute('src',url);
}
function updatePreview(state) {
  if ($('source_layout').value === 'MULTIVIEW') {
    let live=0;
    for (let n=1;n<=4;n++) {
      const source=$(`multiview_${n}`).value;
      const info=previewFor(source,state);
      setImage($(`mv-image-${n}`),info.url);
      setImage($(`mv-placeholder-${n}`),info.card);
      $(`mv-placeholder-${n}`).hidden=info.live;
      if (info.live) live++;
    }
    $('video-status').textContent=`Multiview · ${live}/4 live sources · waiting cards for unavailable inputs`;
  } else {
    const source=$('modeinput').value==='SRT'?`SRT${$('srt_source_slot').value}`:$('modeinput').value;
    const info=previewFor(source,state);
    setImage($('live-preview'),info.url);
    setImage($('video-placeholder'),info.card);
    $('video-placeholder').hidden=info.live;
    $('video-status').textContent=info.live?`${info.label} preview live`:`Waiting for ${info.label}`;
  }
}
function showState(state) {
  lastState = state;
  $('connection').textContent = state.supervisor?.ok ? 'Supervisor connected' : 'Supervisor unavailable';
  const supervisorStatus = state.supervisor?.status || '';
  const supervisorBoard = /board=([^ ]+)/.exec(supervisorStatus)?.[1];
  const expectedBoard = state.board?.startsWith('DATVEXPRESS') ? 'express' : state.board === 'PLUTO' ? 'pluto' : state.board?.startsWith('LIME') ? 'lime' : state.board === 'DEKTEC_ASI' ? 'dektec_asi' : null;
  const boardReady = expectedBoard && supervisorBoard === expectedBoard;
  const localRoute = current.source_layout === 'MULTIVIEW' ||
    (current.source_layout === 'DIRECT' && ['SRT','IPCAM1','IPCAM2'].includes(current.modeinput));
  $('tx-status').textContent = localRoute && state.peer_role !== 'MASTER'
    ? 'RF TX unavailable for this source route; local MPEG-TS output is separate.'
    : !boardReady && state.peer_role !== 'MASTER'
    ? `TX disabled: configured ${state.board} does not match supervisor ${supervisorBoard || 'unavailable'}.`
    : supervisorStatus || state.supervisor?.message || 'Unknown';
  if (state.peer_role === 'MASTER') {
    const telemetry = state.peer?.remote;
    $('tx-status').textContent = !state.peer?.telemetry_fresh
      ? 'SLAVE telemetry unavailable — remote TX state UNKNOWN; do not assume RF is off.'
      : `SLAVE TX process: ${telemetry.tx.toUpperCase()} · ${telemetry.reason || 'status received'}${state.peer.tx_requested && telemetry.tx !== 'running' ? ' · START request awaiting confirmation' : ''}. Process status is not an RF measurement.`;
  }
  updatePreview(state);
  showIpCam(state);
  $('peer-status').textContent = `${state.peer_role || 'STANDALONE'} · ${state.peer?.connected ? 'linked' : 'not linked'}${state.peer?.config_ready ? ' · config ready' : ''}`;
  if (!logInitialized && state.logs) {
    $('log').textContent = state.logs.join('\n');
    logInitialized = true;
  }
  const remote = state.remote_preview_url;
  $('remote-preview-box').hidden = !remote;
  if (remote && $('remote-preview').src !== remote) $('remote-preview').src = remote;
  const locked = state.peer_role === 'SLAVE';
  if (locked) {
    choices('modeinput', [['IPTSIN','IPTS over SRT (from MASTER)']], 'IPTSIN');
    choices('source_layout', [['DIRECT','MASTER-produced transport stream']], 'DIRECT');
    choices('encoding', [['IPTS in','IPTS pass-through (no re-encode)']], 'IPTS in');
    for (const el of document.querySelectorAll('.ipts-only')) el.hidden = true;
    $('peer-status').textContent += ` · IPTS over SRT · UDP port ${state.peer_input?.port || 9000}`;
  }
  const monitorRunning = /source_ts=running/.test(supervisorStatus);
  const outputSelected = current.source_layout === 'MULTIVIEW' ||
    (current.source_layout === 'DIRECT' && ['SRT','IPCAM1','IPCAM2'].includes(current.modeinput));
  const selectedSrt = state.srt?.find(item=>item.slot===Number(current.srt_source_slot||'1'));
  $('source-ts-status').textContent = !state.source_ts_available ? 'Local TS launcher not configured' :
    monitorRunning ? `Local MPEG-TS output running${current.source_layout === 'DIRECT' ? current.modeinput === 'SRT' ? ` · SRT encoder ${current.srt_source_slot||'1'} selected` : ` · ${current.modeinput} selected` : ' · four-tile multiview'}` :
    current.source_layout === 'DIRECT' && current.modeinput === 'SRT' && selectedSrt ? `SRT encoder ${selectedSrt.slot} selected · input UDP ${selectedSrt.ts_port} · output starts on request` :
    current.source_layout === 'DIRECT' && current.modeinput?.startsWith('IPCAM') ? `${current.modeinput} selected · output starts on request` : 'Local MPEG-TS output stopped';
  $('source-ts-start').disabled = locked || !outputSelected || !state.source_ts_available || monitorRunning;
  $('source-ts-stop').disabled = locked || !monitorRunning;
  $('tx-start').disabled = locked || (localRoute && state.peer_role !== 'MASTER') || (state.peer_role === 'MASTER' ? (!state.peer?.config_ready || !state.peer?.telemetry_fresh || !state.peer?.remote?.supervisor_ok) : !boardReady || !state.supervisor?.ok);
  for (const id of ['rx-start','rx-stop']) $(id).disabled = locked;
  for (const id of fields) $(id).disabled = locked;
  for (let n=1;n<=2;n++) for (const action of ['url','save']) $(`ipcam-${action}-${n}`).disabled = locked;
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
    const link = $(`srt-url-${n}`);
    link.textContent = slot.caller_url || 'LAN address unavailable';
    if (slot.caller_url) link.href = slot.caller_url;
    else link.removeAttribute('href');
    $(`srt-copy-${n}`).disabled = !slot.caller_url;
    $(`srt-meta-${n}`).textContent = `Live TS output: UDP 127.0.0.1:${slot.ts_port}`;
  }
}
for (let n=1;n<=5;n++) {
  const card=document.createElement('article');
  card.className='srt-card';
  card.innerHTML=`<h3>SRT input ${n}</h3><div class="preview"><img id="srt-live-${n}" alt="Live SRT input ${n} preview"><img id="srt-placeholder-${n}" class="placeholder" src="/no-srt-input-${n}.jpg" alt="NO SRT INPUT ${n} test pattern"></div><p id="srt-status-${n}" class="status" role="status">Disabled</p><p class="meta">Caller URL: <a id="srt-url-${n}"></a></p><p id="srt-meta-${n}" class="meta"></p><button id="srt-copy-${n}" type="button">Copy caller URL</button><button id="srt-toggle-${n}" type="button">Enable listener</button>`;
  $('srt-slots').append(card);
  $(`srt-copy-${n}`).addEventListener('click', async () => {
    try { await navigator.clipboard.writeText($(`srt-url-${n}`).textContent); log(`SRT ${n} caller URL copied`); }
    catch { log(`SRT ${n}: clipboard unavailable; select the displayed URL to copy it`); }
  });
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
  'rx-start':'/api/rx/start','rx-stop':'/api/rx/stop',
  'source-ts-start':'/api/source-ts/start','source-ts-stop':'/api/source-ts/stop'
})) $(id).addEventListener('click',()=>command(path));
$('modeoutput').addEventListener('change',refreshMode);
$('modeinput').addEventListener('change',refreshSourceFields);
$('source_layout').addEventListener('change',refreshSourceFields);
$('srt_source_slot').addEventListener('change',()=>{ if(lastState) updatePreview(lastState); });
for (let n=1;n<=4;n++) $(`multiview_${n}`).addEventListener('change',refreshSourceFields);
$('call').addEventListener('input', () => {
  $('call').value = $('call').value.toUpperCase();
  $('call').setCustomValidity($('call').value==='N0CALL' ? 'Enter your own callsign; N0CALL is not accepted' : '');
});
$('service_name').addEventListener('input', () => {
  $('service_name').setCustomValidity(new TextEncoder().encode($('service_name').value).length > 64
    ? 'Service name is too long; please shorten it' : '');
});
$('encoding').addEventListener('change',refreshSourceFields);
$('format').addEventListener('change',refreshSourceFields);
$('modulation').addEventListener('change',refreshFec);
$('settings').addEventListener('submit',async event => {
  event.preventDefault();
  $('call').value = $('call').value.trim().toUpperCase();
  $('call').setCustomValidity($('call').value==='N0CALL' ? 'Enter your own callsign; N0CALL is not accepted' : '');
  $('service_name').value = $('service_name').value.trim();
  $('service_name').dispatchEvent(new Event('input'));
  if (!$('settings').reportValidity()) return;
  const changed = Object.fromEntries(fields.map(id => [id,$(id).value]).filter(([id,value])=>(value!=='' || id==='expressaudiodevice') && value!==(current[id]??'')));
  try { await api('/api/config','POST',changed); log('Configuration saved'); await reload(); }
  catch (error) { log(`Save failed: ${error.message}`); }
});
for (let n=1;n<=2;n++) {
  $(`ipcam-save-${n}`).addEventListener('click', async () => {
    const input=$(`ipcam-url-${n}`);
    try {
      const parsed=new URL(input.value.trim());
      if (parsed.protocol !== 'rtsp:' || !parsed.hostname) throw Error('Enter an rtsp:// URL');
      await api('/api/ipcam','POST',{slot:n,url:parsed.href});
      input.value='';
      await refreshIpCamStatus();
      log(`IP CAM ${n} configuration saved`);
    } catch(error) { log(`IP CAM ${n}: ${error.message}`); }
  });
  $(`ipcam-url-${n}`).addEventListener('keydown', event => {
    if (event.key === 'Enter') { event.preventDefault(); $(`ipcam-save-${n}`).click(); }
  });
  $(`ipcam-restart-${n}`).addEventListener('click', async () => {
    try {
      await api(`/api/ipcam/${n}/restart`,'POST');
      log(`IP CAM ${n} preview restarted`);
      showState(await api('/api/state'));
    } catch(error) { log(`IP CAM ${n}: ${error.message}`); }
  });
}
for (let i=1;i<=4;i++) {
  const loadButton=document.createElement('button'); loadButton.textContent=`Load ${i}`;
  loadButton.onclick=async()=>{ try { fill(await api(`/api/presets/${i}`),false); log(`Preset ${i} loaded; press Save configuration to apply`); } catch(error) { log(error.message); } };
  const saveButton=document.createElement('button'); saveButton.textContent=`Save ${i}`; saveButton.className='save';
  saveButton.onclick=async()=>{ try { await api(`/api/presets/${i}`,'POST',Object.fromEntries(fields.map(id=>[id,$(id).value]))); log(`Preset ${i} saved on this system`); } catch(error) { log(error.message); } };
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
setInterval(async () => { try { showState(await api('/api/state')); } catch {} }, 1000);
setInterval(refreshAsiFileStatus, 10000);

document.querySelector('#sign-out').addEventListener('click', async () => {
  try { await api('/api/auth/logout','POST'); } finally { location.replace('/'); }
});

const accessDialog=$('access-dialog');
let revealTimer;
function hideSavedPassword() {
  clearTimeout(revealTimer);
  $('access-saved-password').value='';
  $('access-saved-password').type='password';
  $('access-reveal').textContent='Show saved password';
}
function resetAccessSecrets() {
  hideSavedPassword();
  for (const id of ['access-new-password','access-confirm-password']) { $(id).value='';$(id).type='password'; }
  $('access-show-new').checked=false;
}
function accessRoleChanged() {
  $('access-host-label').hidden=$('access-role').value!=='MASTER';
  $('access-host').required=$('access-role').value==='MASTER';
}
$('access-role').addEventListener('change',accessRoleChanged);
$('access-open').addEventListener('click',async()=>{
  resetAccessSecrets();$('access-message').textContent='Loading…';accessDialog.showModal();
  try {
    const data=await api('/api/access');
    $('access-role').value=data.role;$('access-host').value=data.slave_host;accessRoleChanged();
    $('access-apply').disabled=!data.available||data.busy;
    $('access-reveal').disabled=!data.available||data.busy;
    $('access-message').textContent=data.available?'': 'Run First Start once to enable password-protected access.';
  } catch(error) {$('access-message').textContent=error.message;$('access-apply').disabled=true;}
});
$('access-close').addEventListener('click',()=>accessDialog.close());
accessDialog.addEventListener('close',resetAccessSecrets);
accessDialog.addEventListener('cancel',event=>{if(accessApplying)event.preventDefault();});
$('access-reveal').addEventListener('click',async()=>{
  if ($('access-saved-password').value) {hideSavedPassword();return;}
  try {
    const data=await api('/api/access/password','POST',{});
    if (!accessDialog.open) return;
    $('access-saved-password').type='text';$('access-saved-password').value=data.password;
    $('access-reveal').textContent='Hide saved password';
    revealTimer=setTimeout(hideSavedPassword,30000);
  } catch(error) {$('access-message').textContent=error.message;}
});
document.addEventListener('visibilitychange',()=>{if(document.hidden)hideSavedPassword();});
$('access-show-new').addEventListener('change',()=>{
  for(const id of ['access-new-password','access-confirm-password'])$(id).type=$('access-show-new').checked?'text':'password';
});
$('access-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const password=$('access-new-password').value;
  if(password!==$('access-confirm-password').value) {$('access-message').textContent='New passwords do not match.';return;}
  const bytes=new TextEncoder().encode(password).length;
  if(password && (bytes<8 || bytes>128 || /[\0\r\n]/.test(password))) {$('access-message').textContent='New password is too short, too long, or contains a line break.';return;}
  accessApplying=true;hideSavedPassword();
  $('access-apply').disabled=true;$('access-close').disabled=true;$('access-reveal').disabled=true;
  $('access-message').textContent='Saving access settings…';
  try {
    await api('/api/access','POST',{role:$('access-role').value,slave_host:$('access-host').value.trim(),new_password:password});
    resetAccessSecrets();events.close();
    $('access-message').textContent='Saved. Reconnecting… Sign in again when the login page opens.';
    await new Promise(resolve=>setTimeout(resolve,1500));
    for(let attempt=0;attempt<30;attempt++) {
      try {
        const check=await fetch('/api/state',{cache:'no-store',signal:AbortSignal.timeout(2000)});
        if(check.status===401) {location.replace('/');return;}
      } catch {}
      await new Promise(resolve=>setTimeout(resolve,500));
    }
    $('access-message').textContent='Settings saved. Reopen this HTTPS address to sign in; check the Diablo terminal if it stays unavailable.';
  } catch(error) {
    accessApplying=false;$('access-message').textContent=error.message;
    $('access-apply').disabled=false;$('access-close').disabled=false;$('access-reveal').disabled=false;
  }
});
