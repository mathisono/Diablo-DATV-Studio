#!/usr/bin/env python3
"""Opt-in two-host HTTPS/shared-password peer test. Mock TX only; no media or RF.
Requires the current source and built C tools on both SSH hosts, their ucode
runtimes, and stunnel4. All credentials are temporary and never published.
"""
import argparse
import http.client
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shlex
import socket
import ssl
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('peer_test',Path(__file__).with_name('test-peer-two-host.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for role in ('master','slave'):
        for field in ('ssh','repo','runtime','address','stunnel'):p.add_argument('--'+role+'-'+field,required=True)
    p.add_argument('--local-stunnel',default='stunnel4')
    p.add_argument('--output',required=True)
    a=p.parse_args();password=secrets.token_urlsafe(32);remotes=[]
    report={'test':'two-host HTTPS + TLS-PSK peer; mock TX only, no RF/ASI',
            'date_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'checks':{}}
    with tempfile.TemporaryDirectory(prefix='diablo-access-peer-') as temp:
        root=Path(temp)
        try:
            for role in ('slave','master'):
                host=getattr(a,role+'_ssh');repo=getattr(a,role+'_repo')
                worker=repo+'/scripts/dev/test-peer-two-host.py'
                s=dict(role=role.upper(),repo=repo,runtime=getattr(a,role+'_runtime'),
                       host=a.slave_address,bind=getattr(a,role+'_address'),token='unused-legacy-token',
                       peer_port=28181,http_port=28180,ui_port=28180,secure=True,
                       https_port=28443,password=password,stunnel=getattr(a,role+'_stunnel'))
                remote=base.Remote(host,worker,s);remotes.append(remote)
                report[role]=remote.info
            slave,master=remotes
            base.until(lambda: master.state()['peer']['config_ready'] and master.state()['peer']['telemetry_fresh'])
            report['checks']['same_password_tls_config_and_telemetry']=True
            sessions={}
            def web(role,path='/api/state',method='GET',body=None,authenticated=True):
                address=getattr(a,role+'_address')
                c=http.client.HTTPSConnection(address,28443,context=sessions[role]['context'],timeout=6)
                h={'X-Portsdown-Control':'1','Content-Type':'application/json'}
                if authenticated and sessions[role].get('cookie'):h['Cookie']=sessions[role]['cookie']
                c.request(method,path,json.dumps(body) if body is not None else None,h)
                r=c.getresponse();result=(r.status,dict(r.getheaders()),r.read());c.close();return result
            for role,remote in [('slave',slave),('master',master)]:
                cert=root/(role+'.pem');cert.write_text(remote.request({'cmd':'certificate'})['pem'])
                sessions[role]={'context':ssl.create_default_context(cafile=str(cert))}
                assert web(role,authenticated=False)[0]==401
                assert web(role,'/api/video',authenticated=False)[0]==401
                assert web(role,'/api/tx/start','POST',authenticated=False)[0]==401
                t=time.monotonic();reply=web(role,'/api/auth/login','POST',{'password':password},False)
                assert reply[0]==200,reply[0]
                report['checks'][role+'_login_seconds']=round(time.monotonic()-t,3)
                sessions[role]['cookie']=reply[1]['Set-Cookie'].split(';')[0]
                assert web(role)[0]==200
                for port in (28180,28182,18181,18182):
                    with socket.socket() as c:
                        c.settimeout(.3);assert c.connect_ex((getattr(a,role+'_address'),port))!=0,port
            report['checks']['direct_https_login_both_hosts_and_no_plain_lan_control']=True
            assert web('slave','/api/tx/start','POST')[0]==403
            def start():
                assert web('master','/api/tx/start','POST')[0]==200
                base.until(lambda: master.state()['peer'].get('remote',{}).get('tx')=='running')
            def stopped():return 'tx=stopped' in slave.state()['supervisor']['status']
            start()
            for role in ('master','slave'):
                reply=web(role,'/api/auth/login','POST',{'password':password},False)
                assert reply[0]==200
                assert not stopped() and master.state()['peer']['telemetry_fresh']
            report['checks']['login_during_mock_tx_keeps_heartbeats_and_telemetry']=True
            assert web('slave','/api/tx/stop','POST')[0]==200
            base.until(lambda: stopped() and not master.state()['peer']['tx_requested'])
            report['checks']['authenticated_slave_estop_updates_master']=True
            start();began=time.monotonic();master.request({'cmd':'freeze'})
            base.until(stopped,4)
            report['checks']['heartbeat_loss_stops_mock_seconds']=round(time.monotonic()-began,3)
            master.request({'cmd':'resume'})
            base.until(lambda: master.state()['peer']['telemetry_fresh'] and not master.state()['peer']['tx_requested'])
            # A failed TLS password never reaches the occupied SLAVE controller.
            record=root/'record';subprocess.run([str(ROOT/'control/auth-store'),'create',str(record)],input=password,text=True,check=True)
            key=subprocess.check_output([str(ROOT/'control/auth-store'),'peer-key',str(record)],text=True).strip()
            def contender(psk,send_auth=False):
                keys=root/'client.psk';keys.write_text('diablo:'+psk+'\n');keys.chmod(0o600)
                with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
                cfg=root/'client.conf'
                cfg.write_text('foreground=yes\nsyslog=no\npid=\ndebug=emerg\n[peer]\nclient=yes\naccept=127.0.0.1:'+str(port)+'\nconnect='+a.slave_address+':28181\nPSKsecrets='+str(keys)+'\nPSKidentity=diablo\nciphers=PSK-AES256-GCM-SHA384\nsslVersionMin=TLSv1.2\nsslVersionMax=TLSv1.2\nTIMEOUTclose=0\n')
                process=subprocess.Popen([a.local_stunnel,str(cfg)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                client=None
                try:
                    def connect():
                        try:return socket.create_connection(('127.0.0.1',port),timeout=2)
                        except OSError:return None
                    client=base.until(connect);client.settimeout(3)
                    try:
                        client.sendall((json.dumps({'cmd':'auth','token':psk})+'\n').encode())
                        data=client.recv(4096)
                    except (ConnectionResetError,BrokenPipeError):data=b''
                    if send_auth:
                        assert b'auth_ok' in data
                        base.until(lambda: slave.state()['peer']['connected'])
                    else:assert not data
                finally:
                    if client:client.close()
                    process.terminate();process.wait(timeout=5)
            start()
            contender(secrets.token_hex(32))
            assert master.state()['peer']['connected'] and not stopped()
            report['checks']['wrong_password_cannot_displace_active_master']=True
            contender(key)
            assert master.state()['peer']['connected'] and not stopped()
            report['checks']['second_authorized_master_cannot_displace_active_master']=True
            began=time.monotonic();master.request({'cmd':'disconnect'})
            base.until(stopped,4)
            report['checks']['disconnect_stops_mock_seconds']=round(time.monotonic()-began,3)
            base.until(lambda:not slave.state()['peer']['connected'])
            contender(key,True)
            base.until(lambda:not slave.state()['peer']['connected'])
            master.request({'cmd':'reconnect'})
            base.until(lambda:master.state()['peer']['config_ready'] and master.state()['peer']['telemetry_fresh'])
            assert stopped();report['checks']['same_password_handover_and_reconnect_do_not_autostart']=True
            assert web('master')[0]==401  # restart invalidates old browser sessions
            reply=web('master','/api/auth/login','POST',{'password':password},False)
            assert reply[0]==200
            sessions['master']['cookie']=reply[1]['Set-Cookie'].split(';')[0]
            report['checks']['daemon_restart_invalidates_sessions']=True
            # Killing the TLS process also closes the control link and stops TX.
            start();master.request({'cmd':'drop_tls'});base.until(stopped,4)
            report['checks']['tls_transport_loss_stops_mock']=True
            report['result']='PASS'
        finally:
            report['cleanup']=[remote.stop() for remote in reversed(remotes)]
            raw=json.dumps(report,indent=2)+'\n';assert password not in raw
            Path(a.output).write_text(raw)
    print(json.dumps(report['checks'],indent=2));print(report.get('result','FAIL'))

if __name__=='__main__':main()
