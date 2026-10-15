"""Real tiny Python workers; no numerical solver or provider is used."""
import json
import os
from pathlib import Path
import sys

from caelab.adapters.fenicsx_rectangle import _run_process


def check_worker(output, working_directory=None):
    output.mkdir(parents=True)
    marker = output / 'observed-cwd.txt'
    command = [sys.executable, '-I', '-c',
        'import os,sys; from pathlib import Path; Path(sys.argv[1]).write_text(os.getcwd(),encoding="utf-8")',
        str(marker.resolve())]
    _run_process(command, output, os.environ.copy(), 10, working_directory=working_directory)
    receipt = json.loads((output / 'execution.json').read_text(encoding='utf-8'))
    assert receipt['status'] == 'COMPLETED' and receipt['return_code'] == 0
    return Path(marker.read_text(encoding='utf-8')).resolve()


def test_explicit_short_cwd_keeps_long_native_output(tmp_path):
    output = tmp_path
    while len(str(output)) < 280:
        output = output / ('nested-' + 'x' * 45)
    directory = Path(sys.executable).resolve().parent
    assert check_worker(output, directory) == directory


def test_legacy_default_remains_native_output_directory(tmp_path):
    output = tmp_path / 'native'
    assert check_worker(output) == output.resolve()
