"""Run the bounded existing Material observation acceptance in an owned Job."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCES=('apps/research/material_window.py','apps/research/result_return.py',
         'apps/research/desktop.py','tests/test_material_observation_owner_ui.py',
         'tests/check_material_observation_owner_windows.py','scripts/native_check.py')


def source_pins():
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();source=args.source.resolve()
    assert source.is_dir() and source!=out and not source.is_relative_to(out) and not out.is_relative_to(source)
    assert out.is_relative_to(ROOT/'_workspace') and not out.exists()
    out.mkdir(parents=True)
    pins=source_pins()
    (out/'manifest-initial.json').write_text(json.dumps(dict(source=str(source),python=sys.executable,
        source_pins=pins,scope='Existing saved B75 observation only; no new physics/import/fit/provider.'),
        ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    environment=dict(os.environ,QT_QPA_PLATFORM='windows',CAELAB_OBSERVATION_SOURCE=str(source),
                     CAELAB_OBSERVATION_CAPTURE=str(out/'capture'),PYTHONUTF8='1')
    command=[sys.executable,'-X','utf8',str(ROOT/'scripts/native_check.py'),'--timeout','240',
        '--output-dir',str(out/'process'),'--',sys.executable,'-X','utf8','-m','pytest',
        str(ROOT/'tests/test_material_observation_owner_ui.py'),'-q','-s','--basetemp',str(out/'owned-pytest')]
    completed=subprocess.run(command,cwd=ROOT,env=environment,check=False)
    assert pins==source_pins(),'Pinned product/check source changed during acceptance'
    return completed.returncode


if __name__=='__main__':raise SystemExit(main())
