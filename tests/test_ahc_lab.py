"""Integration checks for score validity, reproducibility and local-run isolation."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('ahc_lab', ROOT / 'ahc-lab/lab.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class LabTests(unittest.TestCase):
    def setUp(self):
        tmp_root = ROOT / '.test-tmp'
        tmp_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='ahc-lab-', dir=tmp_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'inputs').mkdir()
        for i in range(100):
            (self.root / 'inputs' / f'{i:04d}.txt').write_text(f'{i}\n', encoding='utf-8')
        (self.root / 'solver.py').write_text('import sys\nprint(int(sys.stdin.read()) * 2)\n', encoding='utf-8')
        (self.root / 'judge.py').write_text('import sys,pathlib\ns=pathlib.Path(sys.argv[2]).read_text().strip()\nprint("Score = " + s)\n', encoding='utf-8')
        self.c = {'name':'test','root':'.','source':'solver.py','inputs':'inputs','runs':'runs',
                  'direction':'max','mode':'offline','solver_command':['{python}','{solver}'],
                  'judge_command':['{python}','{root}/judge.py','{input}','{output}'],
                  'timeout_seconds':3,'judge_timeout_seconds':3,'workers':2,
                  'features':[{'name':'N','line':0,'token':0,'bins':[30,70]}]}
        self.config = self.root / 'config.json'
        self.write_config()

    def write_config(self):
        self.config.write_text(json.dumps(self.c), encoding='utf-8')

    def run_lab(self, count=10):
        runner = lab.Lab(self.config)
        rid = runner.start(count, 'テスト')
        deadline = time.monotonic()+30
        while runner.lock.locked() and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertFalse(runner.lock.locked())
        return next(r for r in runner.list_runs() if r['id']==rid)

    def test_fixed_subset_and_not_enough_inputs(self):
        c = lab.load_config(self.config)
        ten = lab.select_cases(c,10)
        hundred = lab.select_cases(c,100)
        self.assertEqual([p.stem for p in ten], [f'{i:04d}' for i in range(0,100,10)])
        self.assertTrue(set(ten)<=set(hundred))
        with self.assertRaises(ValueError): lab.select_cases(c,101)

    def test_real_process_pipeline_and_snapshot_and_comparison(self):
        a = self.run_lab()
        self.assertEqual(a['state'],'complete')
        self.assertEqual(a['summary']['valid'],10)
        self.assertEqual(a['summary']['score_sum'],900)
        self.assertEqual(a['rows'][0]['score'],0)  # Valid zero stays valid.
        first_hash=a['source_sha256']
        (self.root/'solver.py').write_text('import sys\nprint(int(sys.stdin.read()) * 3)\n',encoding='utf-8')
        b=self.run_lab()
        comp=lab.compare(b,a)
        self.assertTrue(comp['compatible'], (comp, a.get('error'), b.get('error'), a.get('tool_hashes'), b.get('tool_hashes')))
        self.assertEqual(comp['wins'],9)
        self.assertEqual(comp['ties'],1)
        self.assertEqual(comp['delta_sum'],450)
        self.assertEqual(lab.digest(self.root/'runs'/a['id']/'source.py'),first_hash)
        self.assertNotEqual(first_hash,b['source_sha256'])
        b['direction']='min'
        self.assertEqual(lab.compare(b,a)['losses'],9)
        b['evaluator_signature']='different'
        self.assertFalse(lab.compare(b,a)['compatible'])

    def test_error_plus_zero_is_not_valid_and_missing_score(self):
        out=self.root/'out'; err=self.root/'err'
        err.write_text('',encoding='utf-8')
        out.write_text('illegal placement\nScore = 0\n',encoding='utf-8')
        self.assertEqual(lab.parse_score(self.c,out,err)[1],'judge_error')
        out.write_text('Score = 0\n',encoding='utf-8')
        self.assertEqual(lab.parse_score(self.c,out,err)[:2],(0,'ok'))
        out.write_text('',encoding='utf-8')
        self.assertEqual(lab.parse_score(self.c,out,err)[1],'score_missing')
        out.write_text('Score = 1\nScore = 2\n',encoding='utf-8')
        self.assertEqual(lab.parse_score(self.c,out,err)[1],'score_missing')

    def test_failed_process_and_invalid_score_never_become_zero(self):
        (self.root/'solver.py').write_text('raise RuntimeError("test crash")\n',encoding='utf-8')
        r=self.run_lab(1)
        self.assertEqual(r['rows'][0]['status'],'process_error')
        self.assertIsNone(r['rows'][0]['score'])
        self.assertIsNone(r['summary']['score_sum'])
        (self.root/'solver.py').write_text('print("anything")\n',encoding='utf-8')
        (self.root/'judge.py').write_text('print("bad output\\nScore = 0")\n',encoding='utf-8')
        r=self.run_lab(1)
        self.assertEqual(r['rows'][0]['status'],'judge_error')
        self.assertIsNone(r['rows'][0]['score'])

    def test_timeout_terminates_child_tree(self):
        child_marker=self.root/'child-finished.txt'
        code=f'import time,pathlib; time.sleep(1.5); pathlib.Path({str(child_marker)!r}).write_text("finished")'
        parent=self.root/'parent.py'
        parent.write_text(f'import subprocess,sys,time\nsubprocess.Popen([sys.executable,"-c",{code!r}])\ntime.sleep(20)\n',encoding='utf-8')
        result=lab.run_process([sys.executable,str(parent)],self.root,None,self.root/'stdout',self.root/'stderr',.25,threading.Event())
        self.assertEqual(result['status'],'timeout')
        time.sleep(1.6)
        self.assertFalse(child_marker.exists(),'timed-out child must be terminated')

    def test_cancel_and_exclusive_run(self):
        (self.root/'solver.py').write_text('import time\ntime.sleep(20)\n',encoding='utf-8')
        runner=lab.Lab(self.config)
        runner.start(10,'cancel')
        with self.assertRaises(ValueError): runner.start(10,'second')
        runner.cancel.set()
        deadline=time.monotonic()+10
        while runner.lock.locked() and time.monotonic()<deadline:time.sleep(.02)
        self.assertFalse(runner.lock.locked())
        self.assertEqual(runner.list_runs()[0]['state'],'cancelled')

    def test_interactive_tester_is_the_process_receiving_hidden_input(self):
        # Fake interactive protocol: tester sees full input; solver sees only "visible".
        (self.root/'solver.py').write_text('import sys\ns=sys.stdin.read()\nassert s=="visible"\nprint("answer")\n',encoding='utf-8')
        (self.root/'tester.py').write_text('import subprocess,sys\nhidden=sys.stdin.read()\np=subprocess.run(sys.argv[1:],input="visible",text=True,capture_output=True)\nassert p.returncode==0,p.stderr\nprint(p.stdout,end="")\nprint("Score = "+hidden.strip(),file=sys.stderr)\n',encoding='utf-8')
        self.c['mode']='interactive'
        self.c.pop('judge_command')
        self.c['tester_command']=['{python}','{root}/tester.py','{solver_args}']
        self.write_config()
        r=self.run_lab(1)
        self.assertEqual(r['rows'][0]['status'],'ok')
        self.assertEqual(r['rows'][0]['score'],0)

    def test_input_identity_and_feature_boundaries(self):
        a=self.run_lab(1)
        f,w=lab.features(lab.load_config(self.config),self.root/'inputs/0030.txt')
        self.assertEqual(f['N']['index'],1)
        self.assertEqual(w,[])
        (self.root/'inputs/0000.txt').write_text('1\n',encoding='utf-8')
        b=self.run_lab(1)
        self.assertFalse(lab.compare(b,a)['compatible'])
        # Same names and values must not imply same identity when hashes differ.

    def test_custom_features_and_missing_values(self):
        c=lab.load_config(self.config)
        c['features']=[{'name':'density','key':'density','bins':[.2,.5]}]
        fs,warnings=lab.features(c,self.root/'inputs/0000.txt',{'density':.35})
        self.assertEqual(fs['density']['index'],1)
        self.assertEqual(warnings,[])
        fs,warnings=lab.features(c,self.root/'inputs/0000.txt',{})
        self.assertEqual(fs['density']['group'],'取得不可')
        self.assertEqual(len(warnings),1)

    def test_unreleased_contest_config_opens_but_cannot_run(self):
        self.c.update(ready=False, direction=None, mode=None, judge_command=[],
                      setup_message='問題公開後に設定してください')
        self.write_config()
        c=lab.load_config(self.config)
        self.assertFalse(c['ready'])
        runner=lab.Lab(self.config)
        with self.assertRaisesRegex(ValueError,'問題公開後'):
            runner.start(10,'should not start')
        self.assertFalse(runner.lock.locked())
        self.assertFalse((self.root/'runs').exists())

    def test_freeze_preserves_bytes_and_keeps_main_as_working_source(self):
        runner=lab.Lab(self.config)
        original=b'print("first")\r\n'
        (self.root/'solver.py').write_bytes(original)
        a=runner.freeze('first version')
        self.assertEqual(a['filename'],'submission-001.py')
        self.assertEqual(Path(a['path']).read_bytes(),original)
        (self.root/'solver.py').write_bytes(b'print("second")\n')
        b=lab.Lab(self.config).freeze('second version')
        self.assertEqual(b['filename'],'submission-002.py')
        self.assertEqual(Path(a['path']).read_bytes(),original)
        self.assertEqual((self.root/'solver.py').read_bytes(),b'print("second")\n')
        self.assertTrue(all(r['intact'] for r in runner.list_submissions()))
        Path(a['path']).write_bytes(b'edited later')
        self.assertFalse(next(r for r in runner.list_submissions() if r['number']==1)['intact'])

    def test_concurrent_freezes_do_not_overwrite_or_reuse_numbers(self):
        import concurrent.futures
        runner=lab.Lab(self.config)
        runner.submission_dir().mkdir()
        existing=runner.submission_dir()/'submission-010.py'
        existing.write_bytes(b'old saved code')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            records=list(pool.map(lambda i: lab.Lab(self.config).freeze(str(i)),range(6)))
        self.assertEqual(sorted(r['number'] for r in records),list(range(11,17)))
        self.assertEqual(existing.read_bytes(),b'old saved code')
        self.assertEqual(len(runner.list_submissions()),6)

    def test_freeze_only_links_tests_with_the_same_source(self):
        run=self.run_lab(1)
        runner=lab.Lab(self.config)
        self.assertEqual(runner.freeze()['matching_runs'][0]['id'],run['id'])
        (self.root/'solver.py').write_text('print("changed")',encoding='utf-8')
        self.assertEqual(runner.freeze()['matching_runs'],[])
        self.c.update(ready=False,direction=None,mode=None)
        self.write_config()
        self.assertEqual(runner.freeze()['number'],3)

    def test_run_frozen_source_does_not_change_main_or_configuration(self):
        runner=lab.Lab(self.config)
        saved=runner.freeze('baseline')
        changed=b'import sys\nprint(999)\n'
        (self.root/'solver.py').write_bytes(changed)
        original_config=self.config.read_bytes()
        rid=runner.start(1,'test saved',saved['filename'])
        deadline=time.monotonic()+20
        while runner.lock.locked() and time.monotonic()<deadline:time.sleep(.02)
        self.assertFalse(runner.lock.locked())
        result=next(r for r in runner.list_runs() if r['id']==rid)
        self.assertEqual(result['summary']['score_sum'],0)
        self.assertEqual(result['source_sha256'],saved['sha256'])
        self.assertEqual((self.root/'solver.py').read_bytes(),changed)
        self.assertEqual(self.config.read_bytes(),original_config)
        self.assertEqual(runner.list_submissions()[0]['matching_runs'][0]['id'],rid)
        Path(saved['path']).write_bytes(b'print(123)\n')
        with self.assertRaisesRegex(ValueError,'保存後'):
            runner.start(1,'tampered',saved['filename'])

    def test_invalid_config_and_malformed_or_oversize_score(self):
        original=copy.deepcopy(self.c)
        for key,value in [('ready','false'),('workers',1.5),('score_pattern','no capture'),('judge_ignore_patterns','.*')]:
            self.c=copy.deepcopy(original);self.c[key]=value;self.write_config()
            with self.assertRaises(ValueError):lab.load_config(self.config)
        out=self.root/'out';err=self.root/'err';err.write_text('')
        for text,status in [('Score = 1.2.3','score_missing'),('Score = 9007199254740993','score_out_of_range')]:
            out.write_text(text,encoding='utf-8')
            self.assertEqual(lab.parse_score(original,out,err)[1],status)

    def test_freeze_numbers_are_unique_across_extensions(self):
        import concurrent.futures
        other=copy.deepcopy(self.c);other['source']='other.rs'
        (self.root/'other.rs').write_text('fn main() {}',encoding='utf-8')
        other_config=self.root/'other.json';other_config.write_text(json.dumps(other),encoding='utf-8')
        def freeze(i):return lab.Lab(self.config if i%2 else other_config).freeze()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            records=list(pool.map(freeze,range(8)))
        self.assertEqual(sorted(r['number'] for r in records),list(range(1,9)))


if __name__=='__main__':
    unittest.main()
