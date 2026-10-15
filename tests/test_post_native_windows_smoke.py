"""Smoke admission/loader boundary doubles; no native DLL or GUI acceptance."""
import hashlib
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import runpy
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/post_native_windows_smoke.py'


class PostNativeSmokeTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def configure(self, version, *, failure=None):
        plugin = self.folder / '공개 plugin' / 'CaePostExit.dll'
        plugin.parent.mkdir(exist_ok=True)
        plugin.write_bytes(b'loader boundary fixture, not a DLL')
        calls = []
        def load(path, *, remote):
            calls.append((path, remote))
            if failure: raise failure
        package = ModuleType('paraview')
        package.simple = SimpleNamespace(GetParaViewVersion=lambda: version, LoadPlugin=load)
        self.enterContext(patch.dict(sys.modules, {'paraview': package}))
        self.enterContext(patch.object(sys, 'argv', [str(SCRIPT), '--plugin', str(plugin)]))
        return plugin, calls

    def test_tuple_version_reaches_loader_with_exact_plugin(self):
        plugin, calls = self.configure((6, 2))
        stream = StringIO()
        with redirect_stdout(stream):
            runpy.run_path(str(SCRIPT), run_name='__main__')
        receipt = json.loads(stream.getvalue())
        self.assertEqual(calls, [(str(plugin.resolve()), False)])
        self.assertEqual(receipt['sha256'], hashlib.sha256(plugin.read_bytes()).hexdigest())
        self.assertEqual((receipt['paraview'], receipt['plugin_load']), ('6.2', 'PASSED'))
        self.assertEqual(receipt['desktop_exit_acceptance'], 'NOT_RUN')

    def test_wrong_or_unknown_version_never_loads(self):
        for version in ((6, 1), (6, 3), None, (), '6.2', (6, 2, 0)):
            with self.subTest(version=version):
                _, calls = self.configure(version)
                with self.assertRaisesRegex(RuntimeError, 'exact ParaView 6.2'):
                    runpy.run_path(str(SCRIPT), run_name='__main__')
                self.assertEqual(calls, [])

    def test_load_failure_is_not_a_success_receipt(self):
        _, calls = self.configure((6, 2), failure=RuntimeError('plugin load failed'))
        stream = StringIO()
        with redirect_stdout(stream), self.assertRaisesRegex(RuntimeError, 'plugin load failed'):
            runpy.run_path(str(SCRIPT), run_name='__main__')
        self.assertEqual(len(calls), 1)
        self.assertEqual(stream.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
