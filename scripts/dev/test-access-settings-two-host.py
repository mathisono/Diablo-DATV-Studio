#!/usr/bin/env python3
"""Opt-in two-host web role/password setup with managed restart, mock TX only.
Uses private temporary configs and generated passwords. No RF/ASI/media output.
"""
import argparse
import http.client
import importlib.util
import json
from pathlib import Path
import secrets
import ssl
import tempfile
import time
spec=importlib.util.spec_from_file_location('peer_test',Path(__file__).with_name('test-peer-two-host.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for role in ('master','slave'):
        for field in ('ssh','repo','runtime','address','stunnel'):p.add_argument('--'+role+'-'+field,required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args();password=secrets.token_urlsafe(32);remotes={};sessions={}
    report={'test':'GUI access endpoints + managed restart, two hosts, MOCK TX ONLY; no RF/ASI',
            'date_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'checks':{}}
    with tempfile.TemporaryDirectory(prefix='diablo-web-settings-') as tmp:
        try:
            for role in ('slave','master'):
                repo=getattr(a,role+'_repo')
                settings=dict(role='STANDALONE',repo=repo,runtime=getattr(a,role+'_runtime'),
                    host=a.slave_address,bind=getattr(a,role+'_address'),token='unused',
                    peer_port=28181,http_port=28180,ui_port=28180,secure=True,managed=True,
                    https_port=28443,password=password,stunnel=getattr(a,role+'_stunnel'))
                r=base.Remote(getattr(a,role+'_ssh'),repo+'/scripts/dev/test-peer-two-host.py',settings)
                remotes[role]=r;report[role]=r.info
                cert=Path(tmp)/(role+'.pem');cert.write_text(r.request({'cmd':'certificate'})['pem'])
                sessions[role]={'context':ssl.create_default_context(cafile=str(cert))}
            def web(role,path='/api/state',body=None,auth=True):
                c=http.client.HTTPSConnection(getattr(a,role+'_address'),28443,context=sessions[role]['context'],timeout=12)
                headers={'X-Portsdown-Control':'1','Content-Type':'application/json'}
                if auth and sessions[role].get('cookie'):headers['Cookie']=sessions[role]['cookie']
                c.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,headers)
                r=c.getresponse();out=(r.status,dict(r.getheaders()),r.read());c.close();return out
            def login(role,pw):
                r=web(role,'/api/auth/login',{'password':pw},False);assert r[0]==200,r[0]
                sessions[role]['cookie']=r[1]['Set-Cookie'].split(';')[0]
            def apply(role,new_role,host='',pw='',login_pw=None):
                r=web(role,'/api/access',{'role':new_role,'slave_host':host,'new_password':pw})
                assert r[0]==200,(role,r[0],r[2])
                base.until(lambda:web(role)[0]==401,15)
                login(role,login_pw or password)
                state=json.loads(web(role)[2]);assert state['peer_role']==new_role
                assert 'tx=stopped' in state['supervisor']['status']
            def linked():
                s=remotes['master'].state()['peer'];return s['config_ready'] and s['telemetry_fresh']
            for role in remotes:
                assert web(role,'/api/access',auth=False)[0]==401
                login(role,password)
                assert json.loads(web(role,'/api/access/password',{})[2])['password']==password
            apply('slave','SLAVE');apply('master','MASTER',a.slave_address)
            base.until(linked,15)
            report['checks']['web_pairing_standalone_to_slave_and_master']=True
            assert web('master','/api/tx/start',{})[0]==200
            base.until(lambda:remotes['master'].state()['peer'].get('remote',{}).get('tx')=='running')
            for role in remotes:
                r=web(role,'/api/access',{'role':'STANDALONE','slave_host':''})
                assert r[0]==409,r[0]
            assert web('slave','/api/tx/stop',{})[0]==200
            base.until(lambda:not remotes['master'].state()['peer']['tx_requested'])
            report['checks']['active_mock_tx_blocks_access_changes_and_estop_updates_master']=True
            new_password=secrets.token_urlsafe(32)
            apply('slave','SLAVE',pw=new_password,login_pw=new_password)
            base.until(lambda:not remotes['master'].state()['peer']['connected'])
            assert web('slave','/api/auth/login',{'password':password},False)[0]==401
            apply('master','MASTER',a.slave_address,pw=new_password,login_pw=new_password)
            base.until(linked,15)
            assert 'tx=stopped' in remotes['slave'].state()['supervisor']['status']
            report['checks']['password_rotation_disconnects_then_matching_peers_reconnect_without_tx']=True
            for role in remotes:
                assert json.loads(web(role,'/api/access/password',{})[2])['password']==new_password
            apply('master','STANDALONE',login_pw=new_password)
            base.until(lambda:not remotes['slave'].state()['peer']['connected'])
            assert 'tx=stopped' in remotes['slave'].state()['supervisor']['status']
            report['checks']['web_standalone_releases_slave']=True
            for remote in remotes.values():
                log=remote.request({'cmd':'evidence'})['process_log']
                assert password not in log and new_password not in log
            report['checks']['no_plaintext_passwords_in_process_logs']=True
            report['result']='PASS'
        finally:
            report['cleanup']=[r.stop() for r in reversed(list(remotes.values()))]
            text=json.dumps(report,indent=2)+'\n';assert password not in text
            Path(a.output).write_text(text)
    print(json.dumps(report['checks'],indent=2));print(report.get('result','FAIL'))

if __name__=='__main__':main()
