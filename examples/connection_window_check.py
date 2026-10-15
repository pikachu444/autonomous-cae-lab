"""Run real Qt checks, or explicitly report that Qt could not be executed."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'engineering_release': 'NOT_RELEASED', 'native_windows_verified': False,
              'requested_sizes': [[1200, 780], [820, 600]]}
    if importlib.util.find_spec('PySide6') is None:
        report.update(status='BLOCKED', reason='PySide6 is not installed; Qt event/visual tests were not executed.',
                      captures_created=False)
        code = 2
    else:
        env = dict(os.environ, QT_QPA_PLATFORM=os.environ.get('QT_QPA_PLATFORM', 'offscreen'),
                   QT_CAPTURE_DIR=str(args.output.resolve()))
        process = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-ra', 'tests/test_connection_window_qt.py'],
                                 cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True,
                                 text=True, encoding='utf-8', timeout=120)
        (args.output / 'qt-test.log').write_text(process.stdout + process.stderr, encoding='utf-8')
        report.update(status='PASSED' if process.returncode == 0 else 'FAILED',
                      captures_created=bool(list(args.output.glob('*.png'))))
        code = process.returncode
    (args.output / 'qt-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
