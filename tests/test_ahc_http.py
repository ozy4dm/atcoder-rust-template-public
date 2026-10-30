"""Browser-independent HTTP integration; no external Python packages required."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

urlopen = build_opener(ProxyHandler({})).open

ROOT=Path(__file__).resolve().parent.parent


class HttpTests(unittest.TestCase):
    def test_local_api_saved_source_and_access_checks(self):
        tmp_root=ROOT/'.test-tmp';tmp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=tmp_root,prefix='http-') as tmp:
            root=Path(tmp);(root/'inputs').mkdir()
            for i in range(10):(root/'inputs'/f'{i:04d}.txt').write_text(f'{i}\n')
            source=root/'main.py';source.write_text('import sys\nprint(int(sys.stdin.read()))\n')
            judge=root/'judge.py';judge.write_text('import pathlib,sys\nprint("Score = "+pathlib.Path(sys.argv[1]).read_text().strip())\n')
            config=root/'lab.json';config.write_text(json.dumps({'name':'test','root':'.','source':'main.py','inputs':'inputs','runs':'runs','direction':'max','mode':'offline','solver_command':['{python}','{solver}'],'judge_command':['{python}',str(judge),'{output}'],'timeout_seconds':3,'workers':1}),encoding='utf-8')
            flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
            with (root/'server.stderr').open('wb') as stderr:
                server=subprocess.Popen([sys.executable,'-X','utf8',str(ROOT/'ahc-lab/lab.py'),'serve','--config',str(config),'--port','0'],stdout=subprocess.PIPE,stderr=stderr,text=True,encoding='utf-8',**flags)
                try:
                    lines=queue.Queue()
                    threading.Thread(target=lambda:lines.put(server.stdout.readline()),daemon=True).start()
                    url=lines.get(timeout=10).strip().removeprefix('AHC Lab: ')
                    self.assertTrue(url.startswith('http://127.0.0.1:'))
                    def get(path):
                        with urlopen(url+path,timeout=5) as r:return r.read()
                    state=json.loads(get('/api/state'));token=state['token']
                    def post(path,body,authorized=True):
                        headers={'Content-Type':'application/json'}
                        if authorized:headers['X-Lab-Token']=token
                        with urlopen(Request(url+path,json.dumps(body).encode(),headers,method='POST'),timeout=5) as r:return json.load(r)
                    with self.assertRaises(HTTPError) as e:post('/api/freeze',{},False)
                    self.assertEqual(e.exception.code,403)
                    e.exception.close()
                    with self.assertRaises(HTTPError) as e:urlopen(Request(url+'/api/state',headers={'Host':'external.invalid'}),timeout=5)
                    self.assertEqual(e.exception.code,403)
                    e.exception.close()
                    saved=post('/api/freeze',{'label':'<test>'})
                    original=source.read_bytes();source.write_text('print(999)\n')
                    post('/api/run',{'count':10,'submission':saved['filename']})
                    deadline=time.monotonic()+30
                    while time.monotonic()<deadline:
                        state=json.loads(get('/api/state'))
                        if state.get('active',{}).get('state') in ('完了','エラー'):break
                        time.sleep(.1)
                    self.assertEqual(state['active']['state'],'完了')
                    self.assertEqual(state['runs'][0]['summary']['score_sum'],45)
                    self.assertEqual(source.read_text(),'print(999)\n')
                    self.assertEqual(get('/api/submission?file='+saved['filename']),original)
                    with self.assertRaises(HTTPError) as e:get('/api/submission?file=..%2Fmain.py')
                    self.assertEqual(e.exception.code,404)
                    e.exception.close()
                    self.assertEqual(len(state['submissions'][0]['matching_runs']),1)
                    self.assertIn(b'<html',get('/'))
                finally:
                    server.terminate();server.wait(timeout=10)
                    server.stdout.close()


if __name__=='__main__':unittest.main()
