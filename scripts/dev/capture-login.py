#!/usr/bin/env python3
"""Capture actual HTTPS login and verify browser sign-in/out using a private fixture.
Needs DIABLO_TEST_RUNTIME, PORTSDOWN_STUNNEL and Chromium + Python dev libraries.
No capture source, transmitter, ASI or personal password is used.
"""
import asyncio
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import requests
import websockets
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from test_access import AccessTest

async def run():
    test=AccessTest('test_login_gate_cookie_logout_and_csrf')
    try:
        test.setUp()
        public=subprocess.check_output(['openssl','x509','-in',str(test.cert),'-pubkey','-noout'])
        der=subprocess.check_output(['openssl','pkey','-pubin','-outform','DER'],input=public)
        import hashlib
        pin=base64.b64encode(hashlib.sha256(der).digest()).decode()
        with tempfile.TemporaryDirectory(prefix='diablo-login-browser-') as profile:
            chrome=subprocess.Popen(['chromium','--headless','--no-sandbox','--disable-gpu',
                '--remote-allow-origins=*','--remote-debugging-port=0','--user-data-dir='+profile,
                '--ignore-certificate-errors-spki-list='+pin,'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                active=Path(profile)/'DevToolsActivePort'
                for _ in range(100):
                    if active.exists():break
                    await asyncio.sleep(.05)
                port=int(active.read_text().splitlines()[0])
                pages=requests.get(f'http://127.0.0.1:{port}/json',timeout=3).json()
                async with websockets.connect(next(p['webSocketDebuggerUrl'] for p in pages if p['type']=='page'),max_size=15_000_000) as ws:
                    serial=0
                    async def call(method,params=None):
                        nonlocal serial
                        serial+=1
                        await ws.send(json.dumps(dict(id=serial,method=method,params=params or {})))
                        while True:
                            r=json.loads(await ws.recv())
                            if r.get('id')==serial:
                                assert 'error' not in r,r
                                return r['result']
                    async def value(expr):
                        r=await call('Runtime.evaluate',{'expression':expr,'returnByValue':True});return r['result'].get('value')
                    await call('Page.enable')
                    await call('Emulation.setDeviceMetricsOverride',dict(width=1200,height=800,deviceScaleFactor=1,mobile=False))
                    await call('Page.navigate',{'url':f'https://127.0.0.1:{test.port}/'})
                    await asyncio.sleep(1)
                    assert await value("!!document.querySelector('#login')")
                    shot=await call('Page.captureScreenshot',{'format':'png'})
                    (ROOT/'doc/images/diablo-login.png').write_bytes(base64.b64decode(shot['data']))
                    await value("document.querySelector('#password').value="+json.dumps(test.password)+"; document.querySelector('#login').requestSubmit(); true")
                    for _ in range(60):
                        await asyncio.sleep(.1)
                        if await value("!!document.querySelector('#settings')"):break
                    else:raise AssertionError('Browser sign-in did not reach dashboard')
                    assert await value("!document.cookie.includes('diablo_session')")
                    await value("document.querySelector('#sign-out').click(); true")
                    for _ in range(40):
                        await asyncio.sleep(.1)
                        if await value("!!document.querySelector('#login')"):break
                    else:raise AssertionError('Browser sign-out did not return to login')
                    print('PASS: real Chromium HTTPS login, protected dashboard, HttpOnly cookie, logout; empty-password screenshot saved')
            finally:
                chrome.terminate();chrome.wait(timeout=5)
    finally:test.doCleanups()

if __name__=='__main__':asyncio.run(run())
