"""M4 native prepare -> cold edit/save -> new-process re-read on Windows.

Process ownership, hard timeout and descendant cleanup are delegated ONLY to the
repository's existing scripts/native_check.py. There is no M4 WindowsJob, Popen,
process-name kill, taskkill or second cleanup implementation.
"""
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback
import uuid

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
PHASES = ('prepare', 'cold-edit', 'cold-resaved')


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def shared_native_check():
    """Load the existing helper by exact file, avoiding our native_check name."""
    path = REPOSITORY / 'scripts/native_check.py'
    if not path.is_file():
        raise RuntimeError('기존 scripts/native_check.py가 있는 통합 작업 폴더에서 실행하세요.')
    name = '_caelab_m4_shared_native_check'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolves its defining module here
    spec.loader.exec_module(module)
    return module.run_native_check


@contextmanager
def owned_environment(path, token):
    # The shared runner intentionally inherits the invoking environment. This
    # standalone CLI runs phases serially; restore every entry even on timeout.
    values = {'CAELAB_M4_OWNED_TOKEN': token,
              'CAELAB_M4_OWNED_REQUEST': str(path),
              'CAELAB_M4_OWNED_PARENT_PID': str(os.getpid())}
    previous = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for key, value in previous.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value


def owned_request(path):
    """Fail before importing FreeCAD in an unowned or forwarded user process."""
    path = Path(path).resolve()
    request = json.loads(path.read_text(encoding='utf-8'))
    if (not request.get('token') or os.environ.get('CAELAB_M4_OWNED_TOKEN') != request['token']
            or os.environ.get('CAELAB_M4_OWNED_REQUEST') != str(path)):
        raise RuntimeError('Not an owned M4 test process; no document or application was closed.')
    parent = os.environ.get('CAELAB_M4_OWNED_PARENT_PID', '')
    if not parent.isdigit() or int(parent) != os.getppid():
        raise RuntimeError('The request belongs to a different process; no document was touched.')
    if request.get('phase') not in PHASES:
        raise ValueError('Unknown native check phase')
    return request


def owned_native_entry(path):
    request = owned_request(path)
    import FreeCAD as App
    import FreeCADGui as Gui
    if App.listDocuments():
        raise RuntimeError('Owned test must start with no open documents.')
    output = Path(request['output'])
    answer = {'state': 'RUNNING', 'pid': os.getpid(), 'phase': request['phase']}
    try:
        # The exact local example, not scripts/native_check.py or an installed
        # module with the same short name.
        spec = importlib.util.spec_from_file_location('_m4_native_workflow', HERE/'native_check.py')
        native = importlib.util.module_from_spec(spec); spec.loader.exec_module(native)
        from caelab import native_cad
        from apps.desktop_pre.projects import remember_open
        if request['phase'] == 'prepare':
            source = Path(request['source'])
            manifest, entry = native_cad.unpack_project(source, output/'source-working')
            doc = App.openDocument(str(entry)); remember_open(doc, manifest, source)
            selection = json.loads(Path(request['selection']).read_text(encoding='utf-8'))
            selection = selection.get('selection', selection)
            if set(selection) != {'assembly_id', 'calculation_id', 'frame'}:
                raise ValueError('Supply selected-frame.json or the retained receipt.json selection.')
            native.verify_selected(output/'p', **selection, with_mesh=True)
        elif request['phase'] == 'cold-edit':
            native.verify_cold(output/'p/edited.caepre', output/'p/native-check.json', edit=True)
        else:
            native.verify_cold(output/'p/cold-edited.caepre', output/'p/cold-edit-check.json',
                               receipt_name='cold-resaved-check.json')
        answer['state'] = 'PASS'
    except Exception as error:
        answer.update(state='FAILED', error=str(error), traceback=traceback.format_exc())
    finally:
        write_json(output/(request['phase']+'-owned-result.json'), answer)
        # Only this invocation's initially empty native process reaches here.
        # The shared runner enforces descendant cleanup if native close stalls.
        for name in list(App.listDocuments()): App.closeDocument(name)
        Gui.getMainWindow().close()


def run_phase(freecad, request, timeout):
    output = Path(request['output']); phase = request['phase']
    if phase not in PHASES: raise ValueError('Unknown native check phase')
    request_path = (output/(phase+'-owned-request.json')).resolve()
    write_json(request_path, request)
    macro = output/(phase+'.FCMacro')
    macro.write_text('import sys\n'
        +'sys.path.insert(0, '+repr(str(HERE))+')\n'
        +'sys.path.insert(0, '+repr(str(REPOSITORY))+')\n'
        +'import run_native_correction\n'
        +'run_native_correction.owned_native_entry('+repr(str(request_path))+')\n', encoding='utf-8')
    runner = shared_native_check()
    with owned_environment(request_path, request['token']):
        process = runner([str(freecad), str(macro)], output/(phase+'-process'),
                         timeout_seconds=timeout, cwd=str(output))
    # Job cleanup success, a normal root exit AND native checks must all agree.
    if (process.timed_out or process.exit_code != 0 or process.error
            or process.cleanup_error or process.cleanup != 'job_empty'):
        raise RuntimeError('Native process/cleanup did not complete: '+str(process.receipt))
    result = json.loads((output/(phase+'-owned-result.json')).read_text(encoding='utf-8'))
    if result.get('state') != 'PASS' or result.get('pid') != process.pid or result.get('phase') != phase:
        raise RuntimeError(str(result))
    return {**result, 'process_receipt': str(process.receipt), 'cleanup': process.cleanup}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freecad', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--retained-draft', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='Fresh short path, e.g. C:/cae/m4a3')
    parser.add_argument('--timeout', type=float, default=900.)
    args = parser.parse_args(argv)
    if os.name != 'nt': parser.error('Windows native only; use the separate pytest suite on Linux.')
    for path in (args.freecad, args.source, args.selection, args.retained_draft):
        if path is not None and not path.is_file(): parser.error('Missing input: '+str(path))
    if args.timeout <= 0: parser.error('Timeout must be positive')
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    originals = {str(path.resolve()): digest(path)
                 for path in (args.source, args.selection, args.retained_draft) if path}
    request = {'output': str(output), 'source': str(args.source.resolve()),
               'selection': str(args.selection.resolve())}
    result = {'state': 'RUNNING', 'input_hashes': originals, 'solver_execution': 'NOT_PERFORMED',
              'gui_workflow_acceptance': False, 'cleanup_provider': 'scripts/native_check.py'}
    try:
        for phase in PHASES:
            result[phase] = run_phase(args.freecad.resolve(),
                dict(request, phase=phase, token=uuid.uuid4().hex), args.timeout)
        if len({result[phase]['pid'] for phase in PHASES}) != len(PHASES):
            raise RuntimeError('Each cold check must have a distinct native process')
        result['state'] = 'PASS'
    except Exception as error:
        result.update(state='FAILED', error=str(error), traceback=traceback.format_exc())
    finally:
        result['inputs_unchanged'] = all(Path(path).is_file() and digest(path)==value
                                        for path, value in originals.items())
        if not result['inputs_unchanged']: result['state'] = 'FAILED'
        # Missing receipts are not fabricated into a successful cleanup claim.
        result['process_receipts'] = [str(output/(phase+'-process/native-check.json'))
            for phase in PHASES if (output/(phase+'-process/native-check.json')).is_file()]
        write_json(output/'native-owned-summary.json', result)
    return 0 if result['state']=='PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
