"""Real CMD to Windows PowerShell fixtures, without service/install/native runs."""
import json
import os
from pathlib import Path
import subprocess

import pytest

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows CMD entry points')
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('tool,source_argument', [('Pre', '-Source'), ('Post', '-InputPath')])
def test_native_entry_preserves_arguments_exit_and_double_click_error(tmp_path, tool, source_argument):
    folder = tmp_path / '공학 도구 & 공백 경로'
    scripts = folder / 'scripts'
    scripts.mkdir(parents=True)
    wrapper = folder / f'Start-CAE-{tool}.cmd'
    wrapper.write_bytes((ROOT / wrapper.name).read_bytes())
    (scripts / f'start_cae_{tool.lower()}.ps1').write_text(
        "[CmdletBinding()]\n"
        "param([string]$Source,[string]$InputPath,[int]$Port,[switch]$PrepareOnly)\n"
        "$record = @{source=$Source;input_path=$InputPath;port=$Port;prepare_only=[bool]$PrepareOnly;"
        "poison_module_path=($env:PSModulePath -like '*CAELAB_TEST_POISON*')}\n"
        "[IO.File]::WriteAllText($env:CAE_NATIVE_TEST_RECEIPT,($record | ConvertTo-Json),[Text.Encoding]::UTF8)\n"
        "exit ([int]$env:CAE_NATIVE_TEST_EXIT)\n", encoding='utf-8-sig')
    receipt = tmp_path / 'receipt.json'
    env = os.environ.copy()
    env['PSModulePath'] = 'C:\\CAELAB_TEST_POISON'
    env['CAE_NATIVE_TEST_RECEIPT'] = str(receipt)
    source = str(tmp_path / '입력 자료 & 결과' / '한글 모델.inp')
    cmd = os.environ.get('COMSPEC', 'cmd.exe')
    for exit_code in (0, 7):
        env['CAE_NATIVE_TEST_EXIT'] = str(exit_code)
        for arguments in ([], [source_argument, source, '-Port', '9876', '-PrepareOnly']):
            result = subprocess.run([cmd, '/d', '/c', 'call', str(wrapper), *arguments],
                input='\n', capture_output=True, text=True, errors='replace', env=env, timeout=15)
            assert result.returncode == exit_code, result.stdout + result.stderr
            observed = json.loads(receipt.read_text(encoding='utf-8-sig'))
            assert not observed['poison_module_path']
            if arguments:
                assert observed['source' if tool=='Pre' else 'input_path'] == source
                assert observed['port'] == 9876 and observed['prepare_only'] is True
            else:
                assert observed['source'] == observed['input_path'] == ''
                assert observed['port'] == 0 and observed['prepare_only'] is False
            assert ('startup failed' in result.stdout) == (exit_code != 0)
            assert ('Press any key to close.' in result.stdout) == (exit_code != 0 and not arguments)
