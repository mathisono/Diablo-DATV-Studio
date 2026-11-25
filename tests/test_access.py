"""Real HTTPS/session tests, no RF or physical capture. Native runtime required."""
import http.client
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import ssl
import subprocess
import time
import unittest
import test_first_start as fixture

ROOT=Path(__file__).resolve().parents[1]

class AccessTest(unittest.TestCase):
    def setUp(self):
        if not os.environ.get('DIABLO_TEST_RUNTIME'):
            self.skipTest('Set DIABLO_TEST_RUNTIME')
        self.stunnel=os.environ.get('PORTSDOWN_STUNNEL') or shutil.which('stunnel4')
        if not self.stunnel:self.skipTest('stunnel4 needed')
        self.fixture=fixture.FirstStartTest();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.path
        self.password=secrets.token_urlsafe(24)
        secret=self.root/'password.txt';secret.write_text(self.password);secret.chmod(0o600)
        self.port=self.fixture.values['PORTSDOWN_HTTP_PORT']+60
        result=subprocess.run(['bash',str(ROOT/'scripts/setup-access.sh'),'--prefix',str(self.root),
            '--password-file',str(secret),'--host','127.0.0.1','--https-port',str(self.port),
            '--role','STANDALONE','--non-interactive'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        secret.unlink()
        with self.fixture.envfile.open('a') as f:
            f.write('export PORTSDOWN_STUNNEL='+shlex.quote(self.stunnel)+'\nexport PORTSDOWN_TLS_BIND=127.0.0.1\n')
        if self._testMethodName == 'test_session_expires_and_closes_events':
            with self.fixture.envfile.open('a') as f:f.write('export PORTSDOWN_SESSION_SECONDS=5\n')
        self.cert=next((self.root/'security').glob('cert-*/cert.pem'))
        self.context=ssl.create_default_context(cafile=str(self.cert))
        self.log=open(self.root/'launcher.log','w+')
        self.process=subprocess.Popen(['bash',str(ROOT/'scripts/run-diablo.sh'),str(self.fixture.envfile)],stdout=self.log,stderr=self.log)
        self.addCleanup(self.stop)
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            try:
                if self.request('GET','/')[0]==200:break
            except OSError:pass
            time.sleep(.1)
        else:
            self.log.flush();self.fail((self.root/'launcher.log').read_text())
    def stop(self):
        if self.process.poll() is None:self.process.terminate();self.process.wait(timeout=8)
        self.log.close()
    def request(self,method,path,body=None,cookie=None,origin=None):
        c=http.client.HTTPSConnection('127.0.0.1',self.port,context=self.context,timeout=4)
        headers={'X-Portsdown-Control':'1','Content-Type':'application/json'}
        if cookie:headers['Cookie']=cookie
        if origin:headers['Origin']=origin
        c.request(method,path,json.dumps(body) if body is not None else None,headers)
        r=c.getresponse();result=(r.status,dict(r.getheaders()),r.read());c.close();return result
    def login(self):
        r=self.request('POST','/api/auth/login',{'password':self.password})
        self.assertEqual(r[0],200,r[2]);return r[1]['Set-Cookie'].split(';')[0]
    def test_login_gate_cookie_logout_and_csrf(self):
        self.assertIn(b'Sign in',self.request('GET','/')[2])
        for path in ['/api/state','/api/config','/api/events','/api/video','/api/video/srt/1','/app.js']:
            self.assertEqual(self.request('GET',path)[0],401,path)
        for path in ['/api/tx/start','/api/tx/stop','/api/srt/1/enable']:
            self.assertEqual(self.request('POST',path,{})[0],401,path)
        self.assertEqual(self.request('POST','/api/auth/login',{'password':self.password},origin='https://attacker.invalid')[0],403)
        bad=self.request('POST','/api/auth/login',{'password':'wrong-password-123'})
        self.assertEqual(bad[0],401,bad[2])
        self.assertEqual(self.request('POST','/api/auth/login',{'password':self.password})[0],429)
        time.sleep(1.1)
        reply=self.request('POST','/api/auth/login',{'password':self.password})
        self.assertEqual(reply[0],200,reply[2]);header=reply[1]['Set-Cookie']
        for item in ['HttpOnly','Secure','SameSite=Strict']:self.assertIn(item,header)
        cookie=header.split(';')[0]
        self.assertEqual(self.request('GET','/api/state',cookie=cookie)[0],200)
        self.assertIn(b'id="settings"',self.request('GET','/',cookie=cookie)[2])
        self.assertEqual(self.request('POST','/api/config',{},cookie,origin='https://attacker.invalid')[0],403)
        # Open a continuous event stream, then invalidate it by logging out.
        stream=http.client.HTTPSConnection('127.0.0.1',self.port,context=self.context,timeout=3)
        stream.request('GET','/api/events',headers={'Cookie':cookie})
        response=stream.getresponse();self.assertEqual(response.status,200)
        video=http.client.HTTPSConnection('127.0.0.1',self.port,context=self.context,timeout=3)
        video.request('GET','/api/video/srt/1',headers={'Cookie':cookie})
        frames=video.getresponse();self.assertEqual(frames.status,200)
        self.assertIn('multipart/x-mixed-replace',frames.getheader('Content-Type'))
        self.assertEqual(self.request('POST','/api/auth/logout',{},cookie)[0],200)
        self.assertEqual(self.request('GET','/api/state',cookie=cookie)[0],401)
        self.assertLess(len(response.read()),100000);stream.close()
        self.assertLess(len(frames.read()),2000000);video.close()
        # Neither plaintext password nor session cookie enters logs/config.
        self.log.flush();self.assertNotIn(self.password,(self.root/'launcher.log').read_text())
        self.assertNotIn(self.password,self.fixture.envfile.read_text())
    def test_first_start_secure_verify_and_certificate_rerun(self):
        self.stop()
        before=self.cert.read_bytes()
        result=subprocess.run(['bash',str(ROOT/'scripts/first-start.sh'),'--configure-only',
            '--non-interactive','--prefix',str(self.root),'--callsign','N0CALL',
            '--service-name','Secure setup test','--advertise-ip','192.0.2.10'],
            env={**os.environ,'PORTSDOWN_STUNNEL':self.stunnel},capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('startup/API/shutdown check passed',result.stdout)
        self.assertIn('https://192.0.2.10:',result.stdout)
        # Host changed: new certificate, old file retained for rollback.
        self.assertEqual(self.cert.read_bytes(),before)
        count=len(list((self.root/'security').glob('cert-*')))
        again=subprocess.run(['bash',str(ROOT/'scripts/setup-access.sh'),'--prefix',str(self.root),
            '--non-interactive'],capture_output=True,text=True)
        self.assertEqual(again.returncode,0,again.stderr)
        self.assertEqual(len(list((self.root/'security').glob('cert-*'))),count)

    def test_session_expires_and_closes_events(self):
        cookie=self.login()
        stream=http.client.HTTPSConnection('127.0.0.1',self.port,context=self.context,timeout=8)
        stream.request('GET','/api/events',headers={'Cookie':cookie})
        response=stream.getresponse();self.assertEqual(response.status,200)
        started=time.monotonic();response.read();elapsed=time.monotonic()-started
        self.assertGreater(elapsed,3);self.assertLess(elapsed,7)
        stream.close()
        self.assertEqual(self.request('GET','/api/state',cookie=cookie)[0],401)

    def test_password_record_private_and_shared_peer_key(self):
        auth=next((self.root/'security').glob('access-*/password.conf'))
        self.assertEqual(auth.stat().st_mode&0o777,0o600)
        self.assertNotIn(self.password,auth.read_text())
        second=self.root/'second.conf'
        subprocess.run([str(ROOT/'control/auth-store'),'create',str(second)],input=self.password,text=True,check=True)
        def key(path):return subprocess.check_output([str(ROOT/'control/auth-store'),'peer-key',str(path)])
        self.assertEqual(key(auth),key(second))
        self.assertNotEqual(auth.read_text().split()[1:3],second.read_text().split()[1:3])
        second.chmod(0o644)
        self.assertNotEqual(subprocess.run([str(ROOT/'control/auth-store'),'verify',str(second)],input=self.password,text=True).returncode,0)

if __name__=='__main__':unittest.main()
