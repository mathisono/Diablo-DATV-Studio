#!/usr/bin/env python3
"""Real Pi camera/SRT and mock-only peer-control acceptance. No RF/ASI output.
Camera must already be free; this harness never stops/restarts another service.
Python is a development dependency only. Camera images stay in temporary storage.
"""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time

spec = importlib.util.spec_from_file_location('peer_test', Path(__file__).with_name('test-peer-two-host.py'))
peer_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(peer_test)
api, until, Remote = peer_test.api, peer_test.until, peer_test.Remote


def worker():
    spec = json.loads(sys.stdin.readline())
    repo, runtime = Path(spec['repo']), Path(spec['runtime'])
    processes, grouped = [], set()
    env = {k:v for k,v in os.environ.items() if not k.startswith(('PORTSDOWN_', 'DIABLO_'))}
    with tempfile.TemporaryDirectory(prefix='diablo-real-picam-') as temp:
        root = Path(temp)
        camera_host = spec['camera_host']
        source = 'CAMH264' if camera_host else 'SRT'
        cfg = root / 'config.txt'
        cfg.write_text((repo/'control/diablo-config.example').read_text().replace('modeoutput=DATVEXPRESS_S2','modeoutput=DATVEXPRESS').replace('modeinput=SRT',f'modeinput={source}') + '\ncall=K1TEST\nservice_name=Real Pi camera test - NO RF\n')
        mock = root/'mock-tx'
        mock.write_text('#!/bin/sh\necho "MOCK TX - NO HARDWARE"\nexec sleep 180\n')
        mock.chmod(0o700)
        off = root/'safe-off'
        off.write_text('#!/bin/sh\necho "MOCK SAFE OFF"\n')
        off.chmod(0o700)
        (root/'express-control').touch()
        env.update(PORTSDOWN_DIR=str(repo), PORTSDOWN_CONFIG=str(cfg),
                   PORTSDOWN_RUN_DIR=str(root/'run'), PORTSDOWN_TX_SOCKET=str(root/'run/tx.sock'),
                   PORTSDOWN_CONFIG_STORE=str(repo/'control/config-store'),
                   PORTSDOWN_PRESETS_PATH=str(root/'presets.json'), PORTSDOWN_IPCAM_CONFIG=str(root/'cameras.conf'),
                   PORTSDOWN_PEER_ROLE=spec['role'], PORTSDOWN_PEER_TOKEN=spec['token'],
                   PORTSDOWN_PEER_HOST=spec['host'], PORTSDOWN_PEER_BIND=spec['host'] if spec['role']=='SLAVE' else '127.0.0.1',
                   PORTSDOWN_PEER_PORT='28181', PORTSDOWN_PEER_SRT_PORT='28900',
                   PORTSDOWN_BOARD='none' if spec['role']=='STANDALONE' else 'express',
                   PORTSDOWN_TX_EXEC='' if spec['role']=='STANDALONE' else str(mock),
                   PORTSDOWN_SAFE_OFF_EXEC='' if spec['role']=='STANDALONE' else str(off),
                   PORTSDOWN_EXPRESS_CTRL=str(root/'express-control'),
                   PORTSDOWN_HTTP_PORT='28180', PORTSDOWN_ALLOWED_HOST='127.0.0.1:'+str(spec['ui_port']), PORTSDOWN_MJPEG_PORT='28200',
                   PORTSDOWN_SRT_MJPEG_PORT_BASE='28210', PORTSDOWN_SOURCE_MJPEG_PORT_BASE='28220',
                   PORTSDOWN_SRT_PORT_BASE='28300', PORTSDOWN_SRT_TS_PORT_BASE='28400',
                   PORTSDOWN_SRT_EXEC=str(repo/'control/srt-slot.sh'),
                   LD_LIBRARY_PATH=str(runtime/'lib'))
        logs = open(root/'process.log', 'w+')
        def spawn(args, group=False):
            p = subprocess.Popen(args, env=env, stdout=logs, stderr=logs, start_new_session=group)
            processes.append(p)
            if group: grouped.add(p.pid)
            return p
        def stop(p, sig=signal.SIGTERM):
            if p.pid in grouped:
                try: os.killpg(p.pid, signal.SIGCONT); os.killpg(p.pid, sig)
                except ProcessLookupError: pass
            elif p.poll() is None:
                p.send_signal(signal.SIGCONT); p.send_signal(sig)
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if p.pid in grouped:
                    try: os.killpg(p.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                else: p.kill()
                p.wait(timeout=2)
        def emit(value): print(json.dumps(value), flush=True)
        def daemon():
            return spawn([str(runtime/'bin/ucode'), '-L',str(runtime/'lib/ucode'), '-L',str(repo/'control/ucode'),str(repo/'control/ucode/daemon.uc')])
        try:
            supervisor = spawn([str(repo/'control/tx-super')])
            until(lambda:(root/'run/tx.sock').exists())
            control = daemon()
            until(lambda:api(28180)['code']==200)
            emit({'ready':True,'host':socket.gethostname(),'arch':os.uname().machine,
                  'commit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()})
            sender = receiver = None
            for line in sys.stdin:
                request=json.loads(line); cmd=request['cmd']
                if cmd=='api': emit(api(28180,request.get('path','/api/state'),request.get('method','GET'),request.get('body')))
                elif cmd=='receive':
                    capture=root/'received.ts'
                    if spec['role']=='SLAVE': url='srt://0.0.0.0:28900?mode=listener&latency=200000'
                    else: url='udp://127.0.0.1:28400?fifo_size=1000000&overrun_nonfatal=1'
                    args=['ffmpeg','-hide_banner','-nostdin','-loglevel','warning','-i',url,
                          '-map','0:v:0','-map','0:a:0?','-c','copy','-y','-f','mpegts',str(capture)]
                    if spec['role']=='SLAVE':
                        args += ['-map','0:v:0','-vf','fps=5,scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2',
                                 '-an','-c:v','mjpeg','-threads:v','1','-q:v','10','-f','mjpeg','tcp://127.0.0.1:28222']
                    receiver=spawn(args,True); emit({'ok':True})
                elif cmd=='camera_start':
                    assert camera_host
                    port=28900 if spec['role']=='MASTER' else 28300
                    sender=spawn(['bash',str(repo/'scripts/capture_ts_ffmpeg.sh'),'--source','rpicam','--video-encoder','software',
                                  '--codec','h264','--size','1280x720','--fps','24','--video-bitrate','800000','--muxrate','1200000',
                                  '--audio-device','testtone','--audio-bitrate','48000','--service-provider','K1TEST',
                                  '--service-name','Real Pi camera test - NO RF','--duration','60',
                                  '--preview-tcp','127.0.0.1:28221','--output',f'srt://{spec["host"]}:{port}?mode=caller&latency=200000'],True)
                    emit({'ok':True})
                elif cmd=='camera_stop':
                    stop(sender); emit({'stopped':sender.poll() is not None})
                elif cmd=='media_result':
                    stop(receiver,signal.SIGINT)
                    probe=subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_programs','-show_format','-of','json',str(root/'received.ts')],text=True,timeout=5)
                    data=json.loads(probe); data.get('format',{}).pop('filename',None)
                    decode=subprocess.run(['ffmpeg','-v','error','-i',str(root/'received.ts'),'-map','0:v:0','-frames:v','24','-f','null','-'],capture_output=True,text=True,timeout=8)
                    emit({'probe':data,'decode_24_frames_exit':decode.returncode,'decode_errors':decode.stderr[-2000:]})
                elif cmd=='frame':
                    path=request['path']; conn=peer_test.http.client.HTTPConnection('127.0.0.1',28180,timeout=3)
                    conn.request('GET',path); response=conn.getresponse(); raw=b''
                    assert response.status == 200, response.status
                    deadline=time.monotonic()+5
                    while b'\xff\xd9' not in raw and len(raw)<200000:
                        chunk=response.read(1024)
                        assert chunk and time.monotonic()<deadline, 'Incomplete preview frame'
                        raw+=chunk
                    conn.close(); start=raw.find(b'\xff\xd8'); end=raw.find(b'\xff\xd9',start)
                    assert start>=0 and end>start
                    jpg=raw[start:end+2]; (root/'preview.jpg').write_bytes(jpg)
                    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=width,height','-of','json',str(root/'preview.jpg')],text=True))
                    emit({'sha256':hashlib.sha256(jpg).hexdigest(),'bytes':len(jpg),'probe':probe})
                elif cmd=='freeze': control.send_signal(signal.SIGSTOP); emit({'ok':True})
                elif cmd=='resume': control.send_signal(signal.SIGCONT); emit({'ok':True})
                elif cmd=='disconnect': stop(control); emit({'ok':True})
                elif cmd=='reconnect': control=daemon(); until(lambda:api(28180)['code']==200); emit({'ok':True})
                elif cmd=='evidence':
                    logs.flush(); emit({'log':(root/'process.log').read_text()[-16000:]})
                elif cmd=='stop': break
                else: raise ValueError(cmd)
        finally:
            for p in reversed(processes): stop(p)
            logs.close()
        emit({'stopped':True,'all_owned_processes_exited':all(p.poll() is not None for p in processes)})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',action='store_true')
    for key in ('master-ssh','slave-ssh','master-repo','slave-repo','master-runtime','slave-runtime','slave-address','output'):
        parser.add_argument('--'+key)
    args=parser.parse_args()
    if args.worker: worker(); return
    assert all(getattr(args,k.replace('-','_')) for k in ('master-ssh','slave-ssh','master-repo','slave-repo','master-runtime','slave-runtime','slave-address','output'))
    output=Path(args.output); output.mkdir(parents=True,exist_ok=True)
    report={'date_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'camera':'IMX708, actual rpicam capture',
            'audio':'synthetic 1 kHz test tone, NOT a camera microphone','hardware_tx':'mock only; no RF or ASI','stages':{}}
    token=secrets.token_hex(32)
    for stage in ('standalone','peer'):
        remotes=[]; tunnels=[]; results={'checks':{},'screenshots':{}}
        report['stages'][stage]=results
        try:
            for side in ('slave','master'):
                host=getattr(args,side+'_ssh'); repo=getattr(args,side+'_repo')
                dest=repo+'/scripts/dev/test-picam-srt-two-host.py'
                subprocess.run(['scp','-q',__file__,host+':'+dest],check=True)
                spec=dict(repo=repo,runtime=getattr(args,side+'_runtime'),role=side.upper() if stage=='peer' else 'STANDALONE',
                          camera_host=side=='master',host=args.slave_address,token=token,ui_port=29180 if side=='master' else 29182)
                remote=Remote(host,dest,spec); remotes.append(remote); results[side]=remote.info
            slave,master=remotes
            for host,port in [(args.master_ssh,29180),(args.slave_ssh,29182)]:
                tunnel=subprocess.Popen(['ssh','-N','-o','ExitOnForwardFailure=yes','-L',f'127.0.0.1:{port}:127.0.0.1:28180',host])
                tunnels.append(tunnel)
                until(lambda:api(port)['code']==200)
            def snap(name,side,expected,masked=True):
                results['screenshots'][name]=asyncio.run(peer_test.screenshot(
                    'http://127.0.0.1:'+str(29180 if side=='master' else 29182)+'/',
                    output/(name+'.png'),expected,stage=='peer' and side=='slave',
                    preview_mask=masked,marker='Real Pi camera test - NO RF'))
            if stage=='standalone': assert slave.api('/api/srt/1/enable','POST')['code']==200
            else:
                until(lambda:master.state()['peer']['config_ready'] and master.state()['peer']['telemetry_fresh'])
                config=slave.api('/api/config')['data']['config']
                assert config['modeinput']=='IPTSIN' and config['iptransport']=='srt' and config['encoding']=='IPTS in'
                assert master.api('/api/config')['data']['config']['modeinput']=='CAMH264'
                results['checks']['camera_local_slave_ipts_srt_only']=True
            slave.request({'cmd':'receive'}); master.request({'cmd':'camera_start'})
            until(lambda:master.state()['sources']['CAMH264']['preview']['producer'],12)
            def live():
                state=slave.state()
                return state['srt'][0]['live'] if stage=='standalone' else state['sources']['IPTSIN']['preview']['producer']
            until(live,12)
            results['checks']['actual_camera_and_received_preview_live']=True
            results['preview']=slave.request({'cmd':'frame','path':'/api/video/srt/1' if stage=='standalone' else '/api/video/source/ipts'})
            assert results['preview']['probe']['streams'][0]=={'width':320,'height':240}
            if stage=='standalone': snap('diablo-picam-srt-live','slave','STANDALONE')
            if stage=='peer':
                def start():
                    assert master.api('/api/tx/start','POST')['code']==200
                    until(lambda:master.state()['peer']['remote']['tx']=='running')
                    assert 'tx=stopped' in master.state()['supervisor']['status']
                def stopped(): return 'tx=stopped' in slave.state()['supervisor']['status']
                start(); assert live(); results['checks']['camera_live_during_remote_mock_tx']=True
                snap('diablo-picam-master-live','master','MASTER · linked')
                snap('diablo-picam-slave-live','slave','SLAVE · linked')
                assert slave.api('/api/tx/stop','POST')['code']==200
                until(lambda:stopped() and not master.state()['peer']['tx_requested'])
                results['checks']['local_estop_acknowledged']=True
                snap('diablo-picam-master-estop','master','MASTER · linked')
                start(); began=time.monotonic(); master.request({'cmd':'freeze'}); until(stopped,3)
                results['checks']['heartbeat_loss_stop_seconds']=round(time.monotonic()-began,3)
                master.request({'cmd':'resume'}); until(lambda:not master.state()['peer']['tx_requested'])
                assert stopped(); results['checks']['resume_no_auto_restart']=True
                start(); began=time.monotonic(); master.request({'cmd':'disconnect'}); until(stopped,3)
                results['checks']['disconnect_stop_seconds']=round(time.monotonic()-began,3)
                master.request({'cmd':'reconnect'}); until(lambda:master.state()['peer']['config_ready'] and master.state()['peer']['telemetry_fresh'])
                assert stopped(); results['checks']['reconnect_no_auto_restart']=True
            time.sleep(4)
            master.request({'cmd':'camera_stop'}); until(lambda:not live(),8)
            results['checks']['camera_stop_removes_live_preview']=True
            results['media']=slave.request({'cmd':'media_result'})
            streams=results['media']['probe']['streams']
            assert any(s['codec_name']=='h264' and s.get('width')==1280 and s.get('height')==720 and s.get('r_frame_rate')=='24/1' for s in streams)
            assert any(s['codec_name']=='aac' for s in streams)
            assert results['media']['decode_24_frames_exit']==0 and not results['media']['decode_errors']
            results['checks']['received_720p24_h264_aac_decodes']=True
            if stage=='standalone':
                frame=slave.request({'cmd':'frame','path':'/api/video/srt/1'})
                assert frame['sha256']!=results['preview']['sha256']
                assert frame['sha256']==hashlib.sha256((Path(__file__).resolve().parents[2]/'www/no-srt-input-1.jpg').read_bytes()).hexdigest()
                results['checks']['loss_exact_waiting_frame']=True
                snap('diablo-picam-srt-waiting','slave','STANDALONE',False)
                master.request({'cmd':'camera_start'}); until(live,12)
                results['checks']['camera_reconnect_recovers']=True
                master.request({'cmd':'camera_stop'}); until(lambda:not live(),8)
                assert slave.api('/api/srt/1/disable','POST')['code']==200
            results['result']='PASS'
        finally:
            results['cleanup']=[]
            for remote in reversed(remotes):
                try:
                    results.setdefault('logs',[]).append(remote.request({'cmd':'evidence'}))
                except Exception as exc: results.setdefault('evidence_errors',[]).append(str(exc))
                try: results['cleanup'].append(remote.stop())
                except Exception as exc:
                    results['cleanup'].append({'error':str(exc)})
                    remote.p.stdin.close()
            for tunnel in tunnels:
                tunnel.terminate(); tunnel.wait(timeout=5)
            data=json.dumps(report,indent=2)+'\n'; assert token not in data
            (output/'results.json').write_text(data)
        print(stage+': PASS',flush=True)
    print('PASS; report '+str(output/'results.json'),flush=True)


if __name__=='__main__': main()
