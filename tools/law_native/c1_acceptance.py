"""Bounded C1 native re-freeze -> one exact FE job -> separate-process cold read.

Without --fcstd/--freecad, native re-freeze is explicitly NOT_RUN. All processes
are supervised by the EXISTING owned_check (finally closes its exact tree).
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import secrets
import sys
from owned_check import run

ROOT = Path(__file__).resolve().parents[2]
FCSTD_SHA = '7af4c7ca8ddb1d183e150b7fd7c3170839b85d2613ab4a4a9df946dac8297d8b'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frozen', required=True);p.add_argument('--output', required=True)
    p.add_argument('--freecad');p.add_argument('--fcstd')
    p.add_argument('--fcstd-sha256', default=FCSTD_SHA)
    a = p.parse_args()
    frozen, out = Path(a.frozen).resolve(), Path(a.output).resolve()
    if not frozen.is_file(): p.error('Actual frozen input file is required')
    if bool(a.freecad) != bool(a.fcstd): p.error('Supply both --freecad and --fcstd, or neither')
    out.mkdir(parents=True, exist_ok=False)
    raw = frozen.read_bytes();(out/'original-frozen-simulation.json').write_bytes(raw)
    summary = {'status': 'STARTING', 'original_input_sha256': hashlib.sha256(raw).hexdigest(),
               'native_refreeze': 'NOT_RUN', 'FE': 'NOT_RUN', 'cold': 'NOT_RUN',
               'Windows': 'ACTUAL' if sys.platform == 'win32' else 'NOT_RUN', 'processes': []}
    code = 1
    try:
        if a.freecad:
            exe, fcstd = Path(a.freecad).resolve(), Path(a.fcstd).resolve()
            if not exe.is_file() or not fcstd.is_file():
                raise FileNotFoundError('Explicit actual FreeCAD executable and original FCStd are required')
            if hashlib.sha256(fcstd.read_bytes()).hexdigest() != a.fcstd_sha256:
                raise ValueError('FCStd differs from the explicitly supplied original hash; no regenerated substitute')
            token = secrets.token_hex(24)
            config = {'repo': str(ROOT), 'token': token, 'fcstd': str(fcstd), 'frozen': str(frozen),
                      'fcstd_sha256': a.fcstd_sha256, 'output': str(out/'native')}
            config_path = out/'native-config.json';config_path.write_text(json.dumps(config), encoding='utf-8')
            names = ('CAELAB_LAW_C1_CONFIG', 'CAELAB_LAW_C1_TOKEN')
            old = {key: os.environ.get(key) for key in names}
            try:
                os.environ.update(CAELAB_LAW_C1_CONFIG=str(config_path), CAELAB_LAW_C1_TOKEN=token)
                status = run([str(exe), str(ROOT/'tools/law_native/c1_refreeze.FCMacro')], out/'native-process', 90)
            finally:
                for key, value in old.items():
                    if value is None: os.environ.pop(key, None)
                    else: os.environ[key] = value
            summary['processes'].append(read(out/'native-process/receipt.json'))
            native = read(out/'native/stage.json') if (out/'native/stage.json').is_file() else {'status': 'MISSING'}
            summary['native'] = native
            if status != 0 or native['status'] != 'PASS': raise RuntimeError('Actual same-FCStd re-freeze failed')
            frozen = out/'native/refrozen-simulation.json'
            if read(frozen)['simulation_draft'] != json.loads(raw)['simulation_draft']:
                raise AssertionError('Re-freeze changed the exact law/mesh/protocol/source receipt')
            summary['native_refreeze'] = 'PASS'
        for stage in ('run', 'cold'):
            args = ['--frozen', str(frozen)] if stage == 'run' else ['--previous', str(out/'run')]
            status = run([sys.executable, str(ROOT/'tools/law_native/c1_simulation.py'), '--stage', stage,
                          '--output', str(out/stage), *args], out/(stage+'-process'), 240 if stage == 'run' else 45)
            summary['processes'].append(read(out/(stage+'-process')/'receipt.json'))
            receipt = read(out/stage/'stage.json') if (out/stage/'stage.json').is_file() else {'status': 'MISSING'}
            summary[stage+'_receipt'] = receipt
            if status != 0 or receipt['status'] != 'PASS': raise RuntimeError(stage + ' did not pass; original failure retained')
            summary['FE' if stage == 'run' else 'cold'] = 'PASS'
        summary['status'] = 'PASS' if a.freecad else 'PARTIAL_ACCEPTANCE_NATIVE_NOT_RUN'
        code = 0
    except BaseException as error:
        summary.update(status='FAIL', error_type=type(error).__name__, error=str(error))
    finally:
        summary['original_input_unchanged'] = hashlib.sha256(Path(a.frozen).read_bytes()).hexdigest() == summary['original_input_sha256']
        if not summary['original_input_unchanged']: summary['status'] = 'FAIL';code = 1
        (out/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('status', 'native_refreeze', 'FE', 'cold', 'Windows')}, ensure_ascii=False))
    return code


if __name__ == '__main__': raise SystemExit(main())
