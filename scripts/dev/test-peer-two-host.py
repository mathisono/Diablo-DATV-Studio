#!/usr/bin/env python3
"""Isolated real-network peer acceptance with mock TX only; no hardware launchers.
Run --help. Worker is copied to SSH hosts, and token travels on SSH stdin only.
Python is a development-test dependency, not part of the deployed control plane.
"""
import argparse
import asyncio
import base64
import http.client
import json
import os
from pathlib import Path
import secrets
import select
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import time


def api(port, path='/api/state', method='GET', body=None):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
    conn.request(method, path, body=json.dumps(body) if body is not None else None,
                 headers={'X-Portsdown-Control': '1', 'Content-Type': 'application/json'})
    r = conn.getresponse()
    status, raw = r.status, r.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {'error': raw.decode(errors='replace')}
    conn.close()
    return {'code': status, 'data': data}


def until(check, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (OSError, http.client.HTTPException):
            pass
        time.sleep(.05)
    raise AssertionError('Timed out waiting for test condition')


def worker():
    spec = json.loads(sys.stdin.readline())
    repo, runtime = Path(spec['repo']), Path(spec['runtime'])
    procs = []
    for port in [spec['http_port'], 28200, *range(28210,28215), *range(28220,28225)]:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', port))
    # Ignore inherited operator control/credential settings completely.
    env = {k: v for k, v in os.environ.items() if not k.startswith(('PORTSDOWN_', 'DIABLO_'))}
    with tempfile.TemporaryDirectory(prefix='diablo-peer-acceptance-') as directory:
        root = Path(directory)
        cfg = root/'config.txt'
        cfg.write_text('modeoutput=DATVEXPRESS\nmodulation=S2QPSK\nmodeinput=CARDH264\nsource_layout=DIRECT\nfreqoutput=437\nsymbolrate=1000\nfec=12\nformat=720p\nencoding=H264\ncall=N0CALL\nservice_name=MOCK TX - NO RF initial\n')
        mock = root/'mock-tx'
        mock.write_text('#!/bin/sh\necho "MOCK TX ONLY - NO HARDWARE"\ntrap "exit 0" TERM\nwhile :; do sleep 1; done\n')
        mock.chmod(0o700)
        off = root/'safe-off'
        off.write_text('#!/bin/sh\necho off >> "$PORTSDOWN_OFF_LOG"\necho "MOCK SAFE-OFF ONLY"\n')
        off.chmod(0o700)
        control = root/'express-control'
        control.touch()  # Regular file, never /tmp/expc or a device.
        env.update(PORTSDOWN_DIR=str(repo), PORTSDOWN_CONFIG=str(cfg),
                   PORTSDOWN_CONFIG_STORE=str(repo/'control/config-store'),
                   PORTSDOWN_RUN_DIR=str(root/'run'), PORTSDOWN_TX_SOCKET=str(root/'run/tx.sock'),
                   PORTSDOWN_PRESETS_PATH=str(root/'presets.json'),
                   PORTSDOWN_IPCAM_CONFIG=str(root/'ipcam.conf'),
                   PORTSDOWN_BOARD='express', PORTSDOWN_TX_EXEC=str(mock),
                   PORTSDOWN_SAFE_OFF_EXEC=str(off), PORTSDOWN_EXPRESS_CTRL=str(control),
                   PORTSDOWN_OFF_LOG=str(root/'off.log'), PORTSDOWN_PEER_ROLE=spec['role'],
                   PORTSDOWN_PEER_TOKEN=spec['token'], PORTSDOWN_PEER_SRT_PORT='28900', PORTSDOWN_PEER_PORT=str(spec['peer_port']),
                   PORTSDOWN_PEER_HOST=spec['host'], PORTSDOWN_PEER_BIND=spec['bind'],
                   PORTSDOWN_HTTP_PORT=str(spec['http_port']),
                   PORTSDOWN_ALLOWED_HOST='127.0.0.1:'+str(spec['ui_port']),
                   PORTSDOWN_MJPEG_PORT='28200', PORTSDOWN_SRT_MJPEG_PORT_BASE='28210',
                   PORTSDOWN_SOURCE_MJPEG_PORT_BASE='28220',
                   PORTSDOWN_SRT_PORT_BASE='28300', PORTSDOWN_SRT_TS_PORT_BASE='28400',
                   LD_LIBRARY_PATH=str(runtime/'lib'))
        logs = open(root/'process.log', 'w+')
        def spawn(args):
            p = subprocess.Popen(args, env=env, stdout=logs, stderr=logs)
            procs.append(p)
            return p
        def daemon():
            return spawn([str(runtime/'bin/ucode'), '-L', str(runtime/'lib/ucode'),
                          '-L', str(repo/'control/ucode'), str(repo/'control/ucode/daemon.uc')])
        def emit(data):
            print(json.dumps(data), flush=True)
        try:
            supervisor = spawn([str(repo/'control/tx-super')])
            until(lambda: (root/'run/tx.sock').exists())
            control_process = daemon()
            until(lambda: api(spec['http_port'])['code'] == 200)
            emit({'ready': True, 'hostname': socket.gethostname(), 'arch': os.uname().machine,
                  'commit': subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()})
            for line in sys.stdin:
                req = json.loads(line)
                cmd = req['cmd']
                if cmd == 'api':
                    emit(api(spec['http_port'], req.get('path', '/api/state'), req.get('method', 'GET'), req.get('body')))
                elif cmd == 'freeze':
                    control_process.send_signal(signal.SIGSTOP); emit({'ok': True})
                elif cmd == 'resume':
                    control_process.send_signal(signal.SIGCONT); emit({'ok': True})
                elif cmd == 'disconnect':
                    control_process.terminate(); control_process.wait(timeout=4); emit({'ok': True})
                elif cmd == 'reconnect':
                    control_process = daemon()
                    until(lambda: api(spec['http_port'])['code'] == 200)
                    emit({'ok': True})
                elif cmd == 'media_receive':
                    capture = root/'received.ts'
                    media = spawn(['ffmpeg','-hide_banner','-nostdin','-loglevel','error',
                                   '-i','srt://0.0.0.0:28900?mode=listener&latency=200000',
                                   '-t','6','-map','0:v:0','-map','0:a:0','-c','copy','-y',str(capture)])
                    emit({'ok': True})
                elif cmd == 'media_send':
                    media = spawn(['ffmpeg','-hide_banner','-nostdin','-loglevel','error',
                                   '-re','-f','lavfi','-i','testsrc2=size=1280x720:rate=24',
                                   '-f','lavfi','-i','sine=frequency=1000:sample_rate=48000',
                                   '-t','10','-c:v','libx264','-threads','2','-preset','ultrafast',
                                   '-tune','zerolatency','-pix_fmt','yuv420p','-g','24',
                                   '-b:v','600k','-maxrate','600k','-bufsize','600k',
                                   '-c:a','aac','-b:a','48k','-ar','48000','-ac','2',
                                   '-metadata','service_provider=N0CALL',
                                   '-metadata','service_name=MASTER produced TS',
                                   '-muxrate','900000','-f','mpegts',
                                   'srt://'+spec['host']+':28900?mode=caller&latency=200000'])
                    emit({'ok': True})
                elif cmd == 'media_result':
                    media.wait(timeout=12)
                    probe = subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format',
                                                     '-of','json',str(root/'received.ts')],text=True)
                    emit({'exit_code':media.returncode,'probe':json.loads(probe)})
                elif cmd == 'evidence':
                    logs.flush()
                    emit({'off_count': len((root/'off.log').read_text().splitlines()),
                          'process_log': (root/'process.log').read_text()})
                elif cmd == 'stop':
                    break
                else:
                    raise ValueError('Unknown worker command')
        finally:
            for p in reversed(procs):
                if p.poll() is None:
                    p.send_signal(signal.SIGCONT)
                    p.terminate()
                    try:
                        p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        p.kill(); p.wait()
            logs.close()
        emit({'stopped': True, 'all_owned_processes_exited': all(p.poll() is not None for p in procs)})


class Remote:
    def __init__(self, host, script, spec):
        self.host = host
        self.p = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', host,
                                   'python3 -u '+shlex.quote(script)+' --worker'],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.info = self.request(spec)
        assert self.info.get('ready'), self.info

    def request(self, data):
        self.p.stdin.write(json.dumps(data)+'\n'); self.p.stdin.flush()
        if not select.select([self.p.stdout], [], [], 15)[0]:
            raise RuntimeError('Remote worker response timeout')
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError('Remote worker exited')
        return json.loads(line)

    def api(self, path='/api/state', method='GET', body=None):
        return self.request(dict(cmd='api', path=path, method=method, body=body))

    def state(self):
        return self.api()['data']

    def stop(self):
        if self.p.poll() is None:
            result = self.request({'cmd': 'stop'})
            self.p.stdin.close(); self.p.wait(timeout=8)
            assert result.get('all_owned_processes_exited'), result
            return result
        raise RuntimeError('Worker unexpectedly exited')


async def screenshot(url, path, expected, slave=False):
    import requests
    import websockets
    with tempfile.TemporaryDirectory(prefix='diablo-peer-chromium-') as profile:
        chrome = subprocess.Popen(['chromium', '--headless', '--no-sandbox', '--disable-gpu',
                                   '--remote-allow-origins=*', '--remote-debugging-port=0',
                                   '--user-data-dir='+profile, 'about:blank'],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            active = Path(profile)/'DevToolsActivePort'
            until(active.exists)
            port = int(active.read_text().splitlines()[0])
            pages = requests.get(f'http://127.0.0.1:{port}/json', timeout=3).json()
            wsurl = next(p['webSocketDebuggerUrl'] for p in pages if p['type'] == 'page')
            async with websockets.connect(wsurl, max_size=30_000_000) as ws:
                serial = 0
                async def call(method, params=None):
                    nonlocal serial
                    serial += 1
                    await ws.send(json.dumps(dict(id=serial, method=method, params=params or {})))
                    while True:
                        result = json.loads(await ws.recv())
                        if result.get('id') == serial:
                            assert 'error' not in result, result
                            return result['result']
                await call('Page.enable')
                await call('Emulation.setDeviceMetricsOverride', dict(width=1440,height=1050,deviceScaleFactor=1,mobile=False))
                await call('Page.navigate', {'url': url})
                await asyncio.sleep(2)
                dom = await call('Runtime.evaluate', {'expression': '''({peer:document.querySelector('#peer-status').textContent,tx:document.querySelector('#tx-status').textContent,locked:document.querySelector('#modeoutput').disabled,stopEnabled:!document.querySelector('#tx-stop').disabled,text:document.body.innerText})''', 'returnByValue': True})
                state = dom['result']['value']
                assert expected in state['peer'], state['peer']
                assert state['locked'] == slave and state['stopEnabled'], state
                assert 'MOCK TX - NO RF' in state['text'] or 'MOCK TX - NO RF' in (await call('Runtime.evaluate', {'expression': "document.querySelector('#service_name').value", 'returnByValue': True}))['result']['value']
                shot = await call('Page.captureScreenshot', {'format':'png','captureBeyondViewport':False})
                path.write_bytes(base64.b64decode(shot['data']))
                return {k:v for k,v in state.items() if k != 'text'}
        finally:
            chrome.terminate(); chrome.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    for name in ('master-ssh','slave-ssh','master-repo','slave-repo','master-runtime','slave-runtime','slave-address','output'):
        parser.add_argument('--'+name)
    parser.add_argument('--peer-port', type=int, default=28181)
    parser.add_argument('--http-port', type=int, default=28180)
    args = parser.parse_args()
    if args.worker:
        worker(); return
    assert all(getattr(args,n.replace('-','_')) for n in ('master-ssh','slave-ssh','master-repo','slave-repo','master-runtime','slave-runtime','slave-address','output')), 'Required: all host/repo/runtime/address/output options'
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(32)
    remotes, tunnels, remote_scripts = [], [], []
    report = {'date_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'test':'real two-host TCP control and finite MASTER-produced SRT TS; mock TX/safe-off only; no hardware', 'checks':{}, 'screenshots':{}}
    try:
        for role in ('slave','master'):
            host = getattr(args, role+'_ssh')
            destination = subprocess.check_output(['ssh', host, 'mktemp /tmp/diablo-peer-worker.XXXXXX.py'], text=True).strip()
            remote_scripts.append((host,destination))
            subprocess.run(['scp','-q',__file__,host+':'+destination],check=True)
            spec = dict(role=role.upper(),repo=getattr(args,role+'_repo'),runtime=getattr(args,role+'_runtime'),
                        host=args.slave_address,bind=args.slave_address if role=='slave' else '127.0.0.1',
                        token=token,peer_port=args.peer_port,http_port=args.http_port,
                        ui_port=29182 if role=='slave' else 29180)
            remote = Remote(host,destination,spec); remotes.append(remote)
            report[role] = remote.info
        slave, master = remotes
        until(lambda: master.state()['peer']['config_ready'])
        report['checks']['authenticated_config_ready'] = True
        for path, body in [('/api/config',{'service_name':'disallowed'}),('/api/tx/start',None),('/api/srt/1/enable',None)]:
            assert slave.api(path,'POST',body)['code'] == 403
        report['checks']['slave_write_start_srt_lock'] = True
        assert master.api('/api/config','POST',{'service_name':'MOCK TX - NO RF'})['code'] == 200
        until(lambda: master.state()['peer']['config_ready'])
        assert slave.api('/api/config')['data']['config']['service_name'] == 'MOCK TX - NO RF'
        received = slave.api('/api/config')['data']['config']
        assert received['modeinput'] == 'IPTSIN' and received['iptransport'] == 'srt'
        assert received['encoding'] == 'IPTS in' and received['source_layout'] == 'DIRECT'
        assert master.api('/api/config')['data']['config']['modeinput'] == 'CARDH264'
        report['checks']['master_source_stays_local_slave_ipts_srt_only'] = True
        report['checks']['configuration_sync'] = True
        slave.request({'cmd':'media_receive'})
        master.request({'cmd':'media_send'})
        media_result = slave.request({'cmd':'media_result'})
        assert media_result['exit_code'] == 0, media_result
        streams = media_result['probe']['streams']
        assert any(x['codec_name']=='h264' and x.get('width')==1280 and x.get('height')==720 for x in streams)
        assert any(x['codec_name']=='aac' for x in streams)
        report['media'] = media_result
        report['checks']['master_720p_h264_aac_ts_over_srt_received_copy'] = True
        def start():
            assert master.api('/api/tx/start','POST')['code'] == 200
            until(lambda: 'tx=running' in slave.state()['supervisor']['status'])
            assert 'tx=stopped' in master.state()['supervisor']['status']
        def stopped():
            return 'tx=stopped' in slave.state()['supervisor']['status']
        start()
        # Both UIs remain loopback-only, viewed through independent SSH tunnels.
        for host, local in [(args.master_ssh,29180),(args.slave_ssh,29182)]:
            p = subprocess.Popen(['ssh','-N','-o','ExitOnForwardFailure=yes','-L',f'127.0.0.1:{local}:127.0.0.1:{args.http_port}',host],stderr=subprocess.PIPE)
            tunnels.append(p)
            until(lambda: api(local)['code']==200)
        async def snap(name, port, expected, locked):
            report['screenshots'][name] = await screenshot(f'http://127.0.0.1:{port}/',out/(name+'.png'),expected,locked)
        asyncio.run(snap('diablo-peer-master-linked',29180,'MASTER · linked',False))
        asyncio.run(snap('diablo-peer-slave-linked',29182,'SLAVE · linked',True))
        assert master.api('/api/tx/stop','POST')['code'] == 200
        until(stopped)
        report['checks']['remote_start_stop'] = True
        start()
        assert slave.api('/api/tx/stop','POST')['code'] == 200
        until(stopped)
        report['checks']['slave_estop'] = True
        report['known_limit_master_after_local_estop'] = master.state()['peer']
        master.api('/api/tx/stop','POST')  # Clear outstanding request before next trial.
        start()
        began = time.monotonic()
        master.request({'cmd':'freeze'})  # TCP remains open; no heartbeats.
        until(stopped, 3)
        report['checks']['heartbeat_loss_stop_seconds'] = round(time.monotonic()-began,3)
        report['watchdog_state'] = slave.state()
        asyncio.run(snap('diablo-peer-slave-watchdog',29182,'SLAVE · linked',True))
        master.request({'cmd':'resume'})
        until(lambda: not master.state()['peer']['tx_requested'])
        assert stopped()
        report['checks']['resume_does_not_restart_tx'] = True
        start()
        began = time.monotonic()
        master.request({'cmd':'disconnect'})
        until(stopped, 3)
        report['checks']['disconnect_stop_seconds'] = round(time.monotonic()-began,3)
        until(lambda: not slave.state()['peer']['connected'])
        report['disconnect_state'] = slave.state()
        asyncio.run(snap('diablo-peer-slave-link-loss',29182,'SLAVE · not linked',True))
        master.request({'cmd':'reconnect'})
        until(lambda: master.state()['peer']['config_ready'])
        assert stopped()
        report['checks']['reconnect_does_not_restart_tx'] = True
        start()
        master.api('/api/tx/stop','POST'); until(stopped)
        report['checks']['explicit_restart_after_reconnect'] = True
        report['slave_evidence'] = slave.request({'cmd':'evidence'})
        report['result'] = 'PASS'
    finally:
        report['cleanup'] = []
        for remote in reversed(remotes):
            report['cleanup'].append(remote.stop())
        for p in tunnels:
            p.terminate(); p.wait(timeout=5)
        for host,script in remote_scripts:
            subprocess.run(['ssh',host,'rm -- '+shlex.quote(script)],check=True)
        data = json.dumps(report,indent=2)+'\n'
        assert token not in data
        (out/'peer-two-host-results.json').write_text(data)
    print(json.dumps(report['checks'],indent=2),flush=True)
    print('PASS; owned processes stopped; evidence: '+str(out),flush=True)


if __name__ == '__main__':
    main()
