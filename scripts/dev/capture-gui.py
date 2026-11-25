#!/usr/bin/env python3
"""Capture real Diablo UI from isolated synthetic fixtures. No RF/cameras are opened.
Development dependencies: Chromium, FFmpeg, Python requests and websockets.
Set UCODE, UCODE_MODULE_DIR and LD_LIBRARY_PATH for the installed runtime.
"""
from pathlib import Path
import asyncio,base64,json,os,socket,subprocess,tempfile,time,threading,http.client
import requests,websockets,random
import http.client as http_client
ROOT=Path(__file__).resolve().parents[2]
UCODE=os.environ.get('UCODE', str(Path.home()/'.local/share/diablo-datv-studio/runtime/bin/ucode'))
MODULES=os.environ.get('UCODE_MODULE_DIR', str(Path.home()/'.local/share/diablo-datv-studio/runtime/lib/ucode'))
OUT=ROOT/'doc/images'
CASES=[('srt','diablo-srt.png'),('asi','diablo-asi.png'),('elgato','diablo-elgato-asi.png'),('multiview','diablo-multiview.png'),('ipcam','diablo-ipcam.png'),('mobile','diablo-mobile.png')]
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
async def capture(profile,url,out,case):
 active=profile/'DevToolsActivePort'
 for _ in range(100):
  if active.exists():break
  await asyncio.sleep(.1)
 debug=int(active.read_text().splitlines()[0])
 pages=requests.get(f'http://127.0.0.1:{debug}/json',timeout=3).json()
 wsurl=next(p['webSocketDebuggerUrl'] for p in pages if p['type']=='page')
 async with websockets.connect(wsurl,max_size=30_000_000) as ws:
  n=0
  async def call(method,params=None):
   nonlocal n
   n+=1;ident=n
   await ws.send(json.dumps({'id':ident,'method':method,'params':params or {}}))
   while True:
    item=json.loads(await ws.recv())
    if item.get('id')==ident:return item
  await call('Page.enable')
  await call('Emulation.setDeviceMetricsOverride',{'width':390 if case=='mobile' else 1280,'height':900 if case=='mobile' else 1000,'deviceScaleFactor':1,'mobile':case=='mobile'})
  await call('Page.navigate',{'url':url})
  await asyncio.sleep(2)
  state=await call('Runtime.evaluate',{'expression':"({title:document.title,cameras:document.querySelectorAll('.ipcam-card').length,srt:document.querySelectorAll('.srt-card').length,width:document.documentElement.scrollWidth,viewport:innerWidth,status:document.querySelector('#connection').textContent})",'returnByValue':True})
  state=state['result']['result']['value']
  assert state['title']=='Diablo DATV Studio' and state['cameras']==2 and state['srt']==5,state
  assert state['width']<=state['viewport'],state
  assert state['status']=='Supervisor connected',state
  metrics=await call('Page.getLayoutMetrics')
  size=metrics['result']['cssContentSize']
  result=await call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True,'clip':{'x':0,'y':0,'width':size['width'],'height':size['height'],'scale':1}})
  out.write_bytes(base64.b64decode(result['result']['data']))
def api(port_num,path,method='GET'):
 c=http_client.HTTPConnection('127.0.0.1',port_num,timeout=3)
 c.request(method,path,headers={'X-Portsdown-Control':'1','Content-Type':'application/json'})
 r=c.getresponse();data=r.read();c.close();return r.status,data
for case,name in CASES:
 with tempfile.TemporaryDirectory(prefix=f'portsdown-shot-{case}-') as tmp:
  temp=Path(tmp);cfg=temp/'config.txt';run=temp/'run';stop=threading.Event()
  base='modeoutput=DATVEXPRESS\nmodulation=S2QPSK\nmodeinput=SRT\nsource_layout=DIRECT\nsrt_source_slot=3\nencoding=H264\nformat=720p\nfreqoutput=437\nsymbolrate=333\nfec=12\ncall=K6SOE\nservice_name=Preview Demo\n'
  if case=='asi':
   base='modeoutput=DEKTEC_ASI\nmodulation=ASI\nmodeinput=SRT\nsource_layout=DIRECT\nsrt_source_slot=2\nencoding=H264\nformat=720p\nasi_device=0\nasi_channel=0\nasi_bitrate=3071588\ncall=K6SOE\nservice_name=New DATV\n'
  if case=='elgato':
   base='modeoutput=DEKTEC_ASI\nmodulation=ASI\nmodeinput=HDMI\nsource_layout=DIRECT\nexpresshdmidevice=/dev/video2\nexpressaudiodevice=hw:1,0\nencoding=H264\nformat=720p\nasi_device=0\nasi_channel=0\nasi_bitrate=3071588\n'
  if case in ('multiview','ipcam'):
   base='modeoutput=DATVEXPRESS\nmodulation=S2QPSK\nmodeinput=SRT\nsource_layout=MULTIVIEW\nsrt_source_slot=1\nmultiview_1=HDMI\nmultiview_2=CAMH264\nmultiview_3=IPTSIN\nmultiview_4=SRT1\nexpresshdmidevice=/dev/video2\npicam_index=0\nipts_input_port=10000\nipts_bind_scope=LAN\nencoding=H264\nformat=720p\nfreqoutput=437\nsymbolrate=333\nfec=12\ncall=K6SOE\nservice_name=Multiview Demo\n'
  if case=='ipcam':
   base=base.replace('multiview_1=HDMI','multiview_1=IPCAM1').replace('multiview_2=CAMH264','multiview_2=IPCAM2')
  cfg.write_text(base)
  if case=='ipcam':
   (temp/'ip-cameras.conf').write_text('ipcam1=rtsp://192.0.2.20/demo1\nipcam2=rtsp://192.0.2.21/demo2\n')
   (temp/'ip-cameras.conf').chmod(0o600)
  tsfile=temp/'synthetic.ts'
  if case=='asi':
   subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=320x240:rate=5','-t','1','-c:v','mpeg2video','-metadata','service_provider=KG6MDW','-metadata','service_name=Trevor','-f','mpegts',str(tsfile)],check=True)
  base_port=random.randint(20000,45000)
  http,mjpeg,srt,srtts,srtmjpeg=[base_port,base_port+1,base_port+20,base_port+30,base_port+40]
  fake=temp/'fake-source';fake.write_text('#!/bin/sh\nwhile :; do sleep 30; done\n');fake.chmod(0o755)
  env=os.environ|{'PORTSDOWN_DIR':str(ROOT),'PORTSDOWN_CONFIG':str(cfg),'PORTSDOWN_RUN_DIR':str(run),'PORTSDOWN_BOARD':'none','PORTSDOWN_TX_SOCKET':str(run/'tx.sock'),'PORTSDOWN_HTTP_PORT':str(http),'PORTSDOWN_MJPEG_PORT':str(mjpeg),'PORTSDOWN_SRT_PORT_BASE':str(srt),'PORTSDOWN_SRT_TS_PORT_BASE':str(srtts),'PORTSDOWN_SRT_MJPEG_PORT_BASE':str(srtmjpeg),'PORTSDOWN_SRT_EXEC':str(fake),'PORTSDOWN_SOURCE_PREVIEW_EXEC':str(fake),'PORTSDOWN_SOURCE_TS_EXEC':str(ROOT/'control/source-ts.sh'),'PORTSDOWN_ASI_TS_FILE':str(tsfile),'PORTSDOWN_SRT_ADVERTISE_HOST':'192.0.2.10','PORTSDOWN_IPCAM_CONFIG':str(temp/'ip-cameras.conf'),'PORTSDOWN_PRESETS_PATH':str(temp/'presets.json')}
  super=subprocess.Popen([str(ROOT/'control/tx-super')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  daemon=chrome=None
  try:
   for _ in range(100):
    if (run/'tx.sock').exists():break
    time.sleep(.05)
   daemon=subprocess.Popen([UCODE,'-L',MODULES,'-L',str(ROOT/'control/ucode'),str(ROOT/'control/ucode/daemon.uc')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
   for _ in range(100):
    try:
     if api(http,'/api/config')[0]==200:break
    except OSError:time.sleep(.05)
   else:raise RuntimeError('daemon unavailable')
   if case in ('srt','asi'):
    for n in range(1,6):api(http,f'/api/srt/{n}/enable','POST')
   if case=='multiview':api(http,'/api/srt/1/enable','POST')
   frame=temp/'live.jpg'
   subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=640x480:rate=5','-vf',"scale=320:240,drawtext=text='SYNTHETIC PREVIEW':fontcolor=white:fontsize=20:box=1:boxcolor=black@0.8:x=(w-text_w)/2:y=(h-text_h)/2",'-frames:v','1','-y',str(frame)],check=True)
   feeders=[]
   ports=[mjpeg+6,mjpeg+8,srtmjpeg] if case=='multiview' else [mjpeg+6] if case=='elgato' else [mjpeg+9,mjpeg+10] if case=='ipcam' else []
   def feed(p):
    try:
     with socket.create_connection(('127.0.0.1',p),timeout=3) as conn:
      data=frame.read_bytes()
      while not stop.is_set():conn.sendall(data);stop.wait(.2)
    except OSError:pass
   for p in ports:
    th=threading.Thread(target=feed,args=(p,),daemon=True);th.start();feeders.append(th)
   chrome_dir=temp/'chrome';chrome=subprocess.Popen(['chromium','--headless','--no-sandbox','--disable-gpu','--remote-allow-origins=*','--remote-debugging-port=0',f'--user-data-dir={chrome_dir}','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   asyncio.run(capture(chrome_dir,f'http://127.0.0.1:{http}/',OUT/name,case))
   print(OUT/name,flush=True)
  finally:
   stop.set()
   for proc in (chrome,daemon,super):
    if proc and proc.poll() is None:
     proc.terminate()
     try:proc.wait(timeout=3)
     except subprocess.TimeoutExpired:proc.kill();proc.wait()
   if daemon and daemon.stderr:daemon.stderr.close()
