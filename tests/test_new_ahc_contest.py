import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('new_contest',ROOT/'ahc-lab/new_contest.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
lab_spec=importlib.util.spec_from_file_location('lab',ROOT/'ahc-lab/lab.py')
lab=importlib.util.module_from_spec(lab_spec)
lab_spec.loader.exec_module(lab)


class NewContestTests(unittest.TestCase):
    def setUp(self):
        tmp=ROOT/'.test-tmp'; tmp.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=tmp,prefix='new-ahc-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'ahc-human').mkdir()
        (self.root/'ahc-human/main.rs').write_bytes(b'fn main() {}\r\n')
        (self.root/'ahc-lab').mkdir()
        # A minimal launcher destination also verifies relative paths from another cwd.
        (self.root/'ahc-lab/lab.py').write_text('import argparse\nargparse.ArgumentParser().parse_args()\n',encoding='utf-8')

    def test_portable_workspace_and_non_overwrite(self):
        target=module.create_contest(self.root,'ahc075')
        c=lab.load_config(target/'lab.json')
        self.assertEqual(c['source'],str(target/'main.rs'))
        self.assertEqual(c['inputs'],str(target/'inputs'))
        self.assertFalse(c['ready'])
        for name in ['tools','inputs','runs','submissions']:self.assertTrue((target/name).is_dir())
        self.assertEqual((target/'main.rs').read_bytes(),b'fn main() {}\r\n')
        (target/'main.rs').write_text('user changes',encoding='utf-8')
        with self.assertRaises(FileExistsError):module.create_contest(self.root,'ahc075')
        self.assertEqual((target/'main.rs').read_text(),'user changes')
        second=module.create_contest(self.root,'ahc076')
        self.assertNotEqual(target,second)
        self.assertEqual((target/'main.rs').read_text(),'user changes')

    def test_invalid_names_or_port_do_not_write(self):
        for name in ['../ahc075','AHC075','ahc7','ahc075/../../x','abc075']:
            with self.assertRaises(ValueError):module.create_contest(self.root,name)
        with self.assertRaises(ValueError):module.create_contest(self.root,'ahc075',70000)
        self.assertFalse((self.root/'contests').exists())

    @unittest.skipUnless(os.name=='nt','Windows launcher')
    def test_ascii_crlf_launcher(self):
        target=module.create_contest(self.root,'ahc075')
        launcher=target/'open-lab.cmd'
        data=launcher.read_bytes()
        self.assertTrue(data.isascii())
        self.assertIn(b'\r\n',data)
        # --help exits before attempting to start a server or open a browser.
        r=subprocess.run([os.environ['COMSPEC'],'/d','/c',str(launcher),'--help'],cwd=os.environ['TEMP'],capture_output=True,timeout=10)
        self.assertEqual(r.returncode,0,(r.stdout,r.stderr))
        self.assertIn(b'usage:',r.stdout)


if __name__=='__main__':unittest.main()
