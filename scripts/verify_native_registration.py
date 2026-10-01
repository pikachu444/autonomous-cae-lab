"""P1.2b actual native preparation, partial publication and process recovery.

Use a fresh store and the existing pinned FREECAD_CMD. Faults belong only to
this acceptance program; CAD probing, binding and generation remain real.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import traceback

import cadquery as cq

from caelab import Lab
from caelab import registration_transaction as transaction
from caelab.storage import check_id
from scripts.verify_native_edits import (
    inventory, near, sha, write, LENGTH_TOLERANCE_MM, VOLUME_TOLERANCE_MM3,
)


REPO = Path(__file__).resolve().parents[1]
BACKEND = 'fixture.freecad'
FIXTURE_PIN = '3e48bf6138f495299f45b1af254bfb4aaff307b8'
LENGTH = 'ImportedBox|property|Length'
WIDTH = 'ImportedBox|property|Width'
ENGINEERING_UNKNOWN = {
    'domain_clearance', 'manufacturability', 'machine_interface',
    'static_strength', 'physical_load_test', 'fatigue_durability',
}
REFERENCE = {
    'source_defaults': {'length': 12, 'width': 10, 'height': 8,
                        'bounds_mm': [12, 10, 8], 'volume_mm3': 960},
    'length_binding': {'parameter_id': 'length', 'native_path': LENGTH, 'bounds': [10, 24]},
    'width_binding': {'parameter_id': 'width', 'native_path': WIDTH, 'bounds': [8, 15]},
    'before': {'values': {'length': 18}, 'bounds_mm': [18, 10, 8], 'volume_mm3': 1440},
    'after': {'values': {'length': 18, 'width': 12}, 'bounds_mm': [18, 12, 8], 'volume_mm3': 1728},
    'length_absolute_tolerance_mm': LENGTH_TOLERANCE_MM,
    'volume_absolute_tolerance_mm3': VOLUME_TOLERANCE_MM3,
    'publication_order': ['native', 'registry_history/0002.json', 'current_registry'],
    'fault_cases': [
        {'case': 'native-before-write', 'native': 'before', 'history0002': 'absent', 'current_registry': 'before'},
        {'case': 'history-before-write', 'native': 'after', 'history0002': 'absent', 'current_registry': 'before'},
        {'case': 'registry-before-write', 'native': 'after', 'history0002': 'after', 'current_registry': 'before'},
        {'case': 'exit-after-native', 'exit_code': 91, 'native': 'after', 'history0002': 'absent', 'current_registry': 'before'},
        {'case': 'error-after-real-prepare', 'injection': 'AFTER successful real private prepare',
         'native': 'before', 'history0002': 'absent', 'current_registry': 'before', 'journal': 'ABORTED'},
    ],
    'engineering_unknown': sorted(ENGINEERING_UNKNOWN),
    'engineering_decision': 'NOT_RELEASED', 'solver_status': 'NOT_RUN',
}
LIMITS = [
    'Synthetic editable Part::Box only; this is not corporate CAD or human GUI edit qualification.',
    'Injected I/O failures and child process exit are qualified separately from power loss and disk loss.',
    'A noncooperating GUI write between a final comparison and replacement is not excluded or qualified.',
    'The adapter-error case is injected AFTER successful actual prepare; neither FreeCAD save is fault-injected.',
    'Foreign/tampered journal and target cases belong to the separate source regressions, not this native run.',
    'No LLM, OpenScience tool-loop, solver, strength, physical or engineering release claim.',
]


def utc():
    return datetime.now(timezone.utc).isoformat()


def file_record(path, root):
    return {'path': path.relative_to(root).as_posix(), 'size_bytes': path.stat().st_size, 'sha256': sha(path)}


def source_identity():
    def git(*args, cwd=REPO):
        return subprocess.check_output(['git', *args], cwd=cwd, text=True, timeout=30).strip()
    return {'source_commit': git('rev-parse', 'HEAD'),
            'source_dirty': bool(git('status', '--porcelain')),
            'fixture_commit': git('rev-parse', 'HEAD', cwd=REPO / 'plugins/fixture_design/upstream'),
            'fixture_dirty': bool(git('status', '--porcelain', cwd=REPO / 'plugins/fixture_design/upstream'))}


def runtime_identity():
    command = Path(os.environ['FREECAD_CMD']).resolve()
    assert command.is_file(), 'The existing FREECAD_CMD executable must exist'
    packages = {}
    for name in ('cadquery', 'cadquery-ocp', 'numpy'):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    result = {'python': platform.python_version(), 'platform': platform.platform(), 'packages': packages,
              'python_executable': {'path': str(Path(sys.executable).resolve()), 'sha256': sha(Path(sys.executable).resolve())},
              'freecad_command': {'path': str(command), 'sha256': sha(command)},
              'source_files': {name: sha(REPO / name) for name in (
                  'scripts/verify_native_registration.py', 'scripts/verify_native_edits.py',
                  'scripts/native_edit_fixture_worker.py', 'caelab/engine.py', 'caelab/contracts.py',
                  'caelab/registration_transaction.py', 'caelab/adapters/fixture_freecad.py',
                  'caelab/adapters/native_bridge.py', 'caelab/adapters/freecad_parameter_worker.py',
                  'caelab/adapters/freecad_parameters.py', 'plugins/fixture_design/upstream/fixturelab/freecad_worker.py')}}
    if os.environ.get('FREECAD_APPIMAGE'):
        image = Path(os.environ['FREECAD_APPIMAGE']).resolve()
        assert image.is_file(), 'The declared FreeCAD AppImage must exist'
        result['freecad_appimage'] = {'path': str(image), 'sha256': sha(image)}
    return result


def exception_record(error):
    return {'type': type(error).__name__, 'error': str(error), 'traceback': traceback.format_exc()}


def retain_output(folder, stdout, stderr):
    for name, value in (('stdout.txt', stdout), ('stderr.txt', stderr)):
        if isinstance(value, bytes):
            value = value.decode('utf-8', errors='replace')
        (folder / name).write_text(value or '', encoding='utf-8')


class Acceptance:
    def __init__(self, store, run_id, preserve_stores):
        if store.exists():
            raise FileExistsError('Use a fresh store; do not overwrite any earlier acceptance')
        store.mkdir(parents=True)
        self.store, self.run_id = store, run_id
        self.study = 'S-' + run_id
        self.receipt = store / 'native_registration_acceptance.json'
        self.immutable_experiments = {}
        self.preserved = []
        self.preserve_stores = preserve_stores
        self.fixture_index = 0
        self.record = {'schema': 1, 'phase': 'P1.2b', 'run_id': run_id, 'study_id': self.study,
                       'outcome': 'RUNNING', 'started_utc': utc(), 'reference': REFERENCE,
                       'limitations': LIMITS, 'cases': [], 'preserved_stores': self.preserved}
        write(store / 'predeclared-reference.json', REFERENCE)
        self.record['predeclared_reference_sha256'] = sha(store / 'predeclared-reference.json')
        self.save()

    def save(self):
        write(self.receipt, self.record)

    def fixture(self, action, document):
        self.fixture_index += 1
        folder = self.store / 'fixture-ops' / f'{self.fixture_index:02d}-{action}'
        request, result = folder / 'request.json', folder / 'result.json'
        write(request, {'action': action, 'document': str(document)})
        env = {**os.environ, 'FIXTURE_FREECAD_REQUEST': str(request), 'FIXTURE_FREECAD_RESULT': str(result),
               'CAELAB_NATIVE_EDIT_REPO': str(REPO)}
        try:
            executed = subprocess.run([self.record['runtime']['freecad_command']['path'],
                                       str(REPO / 'scripts/native_edit_fixture_worker.py')],
                                      env=env, capture_output=True, text=True, timeout=150)
        except subprocess.TimeoutExpired as error:
            retain_output(folder, error.stdout, error.stderr)
            write(folder / 'error.json', exception_record(error))
            raise
        retain_output(folder, executed.stdout, executed.stderr)
        write(folder / 'process.json', {'returncode': executed.returncode, 'timeout_seconds': 150})
        answer = json.loads(result.read_text())
        assert executed.returncode == 0 and answer['ok'], ('Actual fixture operation failed', answer)
        return answer['result']

    def register_width(self, lab):
        return lab.register_parameter(self.study, BACKEND, self.model, WIDTH, 'width', 'Box width', 8, 15)

    def transaction_ids(self):
        root = self.store / 'registration_transactions'
        return {path.name for path in root.iterdir() if path.is_dir()} if root.exists() else set()

    def new_transaction(self, previous):
        added = self.transaction_ids() - previous
        assert len(added) == 1, ('Expected one actual registration transaction', added)
        return self.store / 'registration_transactions' / next(iter(added))

    def public_state(self):
        return {'native': file_record(self.native, self.store), 'registry': file_record(self.registry_path, self.store),
                'registry_history': inventory(self.history), 'experiments': inventory(self.store / 'experiments'),
                'ledger': inventory(self.store / 'ledger')}

    def snapshot(self, folder):
        folder.mkdir(parents=True, exist_ok=False)
        state = self.public_state()
        write(folder / 'public-inventory.json', state)
        images = folder / 'images'
        images.mkdir()
        shutil.copy2(self.native, images / 'editable.FCStd')
        shutil.copy2(self.registry_path, images / 'parameters.json')
        shutil.copytree(self.history, images / 'registry_history')
        shutil.copytree(self.store / 'ledger', images / 'ledger')
        return state

    def journal_snapshot(self, folder, destination):
        destination.mkdir(parents=True, exist_ok=False)
        shutil.copy2(folder / 'journal.json', destination / 'journal.json')
        if (folder / 'pending').exists():
            shutil.copy2(folder / 'pending', destination / 'pending')
        value = json.loads((folder / 'journal.json').read_bytes())
        write(destination / 'transaction-inventory.json', inventory(folder))
        return {'transaction_id': folder.name, 'folder': folder.relative_to(self.store).as_posix(),
                'journal_sha256': sha(folder / 'journal.json'), 'pending': (folder / 'pending').exists(),
                'journal': value, 'retained_private_stage': (folder / 'work/native').relative_to(self.store).as_posix()}

    def new_case(self, number, name, category):
        folder = self.store / 'acceptance-cases' / f'{number:02d}-{name}'
        folder.mkdir(parents=True, exist_ok=False)
        item = {'case': name, 'category': category, 'outcome': 'RUNNING',
                'folder': folder.relative_to(self.store).as_posix(),
                'before': self.snapshot(folder / 'before'),
                'original_experiment_images': 'baseline/experiments'}
        assert item['before'] == self.baseline, 'Every fault must start on the identical Length-only baseline'
        self.record['cases'].append(item)
        self.save()
        return folder, item

    def expected_exception(self, call, error_type, marker, folder):
        try:
            call()
        except BaseException as error:
            raw = exception_record(error)
            write(folder / 'raw-exception.json', raw)
            assert type(error) is error_type and str(error) == marker, ('Unrelated failure is not acceptance', raw, marker)
            return raw
        raise AssertionError('Expected failure was not raised: ' + marker)

    def assert_immutable_experiments(self, lab):
        for experiment, frozen in self.immutable_experiments.items():
            root = self.store / 'experiments' / experiment
            assert inventory(root) == frozen['files'], ('Immutable experiment changed', experiment)
            assert sha(self.store / 'ledger' / f'{experiment}.json') == frozen['ledger_sha256']
            inspected = lab.inspect_experiment(experiment)
            assert inspected['cad_revision'] == frozen['cad_revision']
            assert inspected['decision'] == 'NOT_RELEASED' and inspected['solver_status'] == 'NOT_RUN'

    def assert_length_only_baseline(self):
        fresh = Lab(self.store)
        assert self.public_state() == self.baseline, 'Recovery did not restore exact original public bytes'
        registry = fresh.registry(self.study)
        assert registry['revision'] == 1 and [entry['parameter_id'] for entry in registry['entries']] == ['length']
        info = fresh.inspect_native_model(self.model)
        assert info['source_sha256'] == self.baseline['native']['sha256']
        assert [entry['key'] for entry in info['parameters']] == [LENGTH]
        assert [entry['name'] for entry in info['parameters']] == ['length']
        candidates = fresh.discover_parameters(BACKEND, self.model)
        paths = [candidate['native']['path'] for candidate in candidates]
        assert len(paths) == len(set(paths)) and WIDTH in paths
        self.assert_immutable_experiments(fresh)

    def assert_partial_publication(self, case_name, folder, item):
        value = item['transaction_before_recovery']['journal']
        assert value['state'] == 'PREPARED' and item['transaction_before_recovery']['pending']
        expected_targets = [self.native, self.history / '0002.json', self.registry_path]
        rows = value['files']
        assert [row['target'] for row in rows] == [target.relative_to(self.store).as_posix() for target in expected_targets]
        assert rows[0]['before'] == self.baseline['native']['sha256'] and rows[0]['after'] != rows[0]['before']
        assert rows[1]['before'] is None and rows[2]['before'] == self.baseline['registry']['sha256']
        assert rows[1]['after'] == rows[2]['after']
        images = []
        for index, row in enumerate(rows):
            image = {'target': row['target'], 'before_sha256': row['before'], 'after_sha256': row['after']}
            for kind in ('before', 'after'):
                path = folder / kind / f'{index:04d}.bin'
                if row[kind] is None:
                    assert not path.exists()
                else:
                    assert path.is_file() and sha(path) == row[kind] and path.stat().st_size == row[kind + '_size']
                    image[kind + '_image'] = path.relative_to(self.store).as_posix()
            images.append(image)
        item['images'] = images
        prepared_registry = json.loads((folder / 'after/0002.bin').read_bytes())
        assert prepared_registry['revision'] == 2
        assert [entry['parameter_id'] for entry in prepared_registry['entries']] == ['length', 'width']
        assert all(entry['source_sha256'] == rows[0]['after'] for entry in prepared_registry['entries'])
        stage_result = json.loads((folder / 'work/native/inspect-after/result.json').read_bytes())
        assert stage_result['ok'] and stage_result['result']['source_sha256'] == rows[0]['after']
        assert sha(folder / 'work/native/editable.FCStd') == rows[0]['after']
        assert [entry['key'] for entry in stage_result['result']['parameters']] == [LENGTH, WIDTH]
        native_hash = rows[0]['before'] if case_name == 'native-before-write' else rows[0]['after']
        assert sha(self.native) == native_hash
        assert sha(self.registry_path) == rows[2]['before']
        history_image = self.history / '0002.json'
        if case_name == 'registry-before-write':
            assert history_image.is_file() and sha(history_image) == rows[1]['after']
            assert inventory(self.history) == self.baseline['registry_history'] + [
                {'path': '0002.json', 'size_bytes': rows[1]['after_size'], 'sha256': rows[1]['after']}]
        else:
            assert not history_image.exists() and inventory(self.history) == self.baseline['registry_history']
        assert inventory(self.store / 'experiments') == self.baseline['experiments']
        assert inventory(self.store / 'ledger') == self.baseline['ledger']
        item['expected_partial_state_verified'] = True

    def assert_pending_consumers_blocked(self, folder, item):
        fresh = Lab(self.store)
        blocked_id = check_id('E-' + self.run_id + '-blocked-' + item['case'])
        calls = [('registry', lambda: fresh.registry(self.study)),
                 ('discovery', lambda: fresh.discover_parameters(BACKEND, self.model)),
                 ('registration', lambda: self.register_width(fresh)),
                 ('experiment', lambda: fresh.run_experiment(study_id=self.study, experiment_id=blocked_id,
                                                            backend=BACKEND, model=self.model, values={'length': 18}))]
        refusals = []
        before_transactions = self.transaction_ids()
        for name, call in calls:
            try:
                call()
            except ValueError as error:
                raw = exception_record(error)
                write(folder / 'blocked' / f'{name}.json', raw)
                assert str(error).startswith('REGISTRATION_RECOVERY_REQUIRED:'), ('Unrelated refusal', name, raw)
                refusals.append({'operation': name, 'reason': str(error)})
            else:
                raise AssertionError('Pending registration reached consumer: ' + name)
        assert self.transaction_ids() == before_transactions
        assert not (self.store / 'experiments' / blocked_id).exists()
        assert not (self.store / 'ledger' / f'{blocked_id}.json').exists()
        assert inventory(self.store / 'experiments') == self.baseline['experiments']
        assert inventory(self.store / 'ledger') == self.baseline['ledger']
        self.assert_immutable_experiments(fresh)
        item['pending_refusals'] = refusals
        item['blocked_experiment_id'] = blocked_id
        item['old_experiment_usable_while_pending'] = True

    def child(self, mode, folder, label, expected_code=0):
        log = folder / label
        log.mkdir(parents=True, exist_ok=False)
        result = log / 'result.json'
        command = [sys.executable, '-m', 'scripts.verify_native_registration', '--store', str(self.store),
                   '--run-id', self.run_id, '--_child', mode, '--_study', self.study, '--_model', self.model,
                   '--_case-root', str(folder), '--_child-result', str(result)]
        limit = 420 if mode == 'exit-after-native' else 90
        write(log / 'command.json', {'argv': command, 'timeout_seconds': limit, 'expected_exit_code': expected_code})
        try:
            process = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=limit)
        except subprocess.TimeoutExpired as error:
            retain_output(log, error.stdout, error.stderr)
            write(log / 'error.json', exception_record(error))
            raise
        retain_output(log, process.stdout, process.stderr)
        write(log / 'process.json', {'returncode': process.returncode, 'parent_pid': os.getpid()})
        assert process.returncode == expected_code, ('Unexpected real child exit', mode, process.returncode, process.stderr)
        if expected_code:
            return {'returncode': process.returncode, 'logs': log.relative_to(self.store).as_posix()}
        answer = json.loads(result.read_bytes())
        assert answer['ok'] and answer['pid'] != os.getpid()
        return answer

    def recover_twice(self, folder, item, transaction_folder, aborted=False):
        stage_before = inventory(transaction_folder / 'work')
        first = self.child('recover', folder, 'recovery-first')
        result = first['result']
        if aborted:
            assert result['status'] == 'NO_PENDING_TRANSACTION' and result['transactions'] == []
        else:
            assert result['status'] == 'RECOVERED' and result['transactions'] == [
                {'transaction_id': transaction_folder.name, 'status': 'ROLLED_BACK'}]
        self.assert_length_only_baseline()
        second = self.child('recover', folder, 'recovery-second')
        assert second['result']['status'] == 'NO_PENDING_TRANSACTION' and second['result']['transactions'] == []
        assert first['pid'] != second['pid']
        assert inventory(transaction_folder / 'work') == stage_before, 'Recovery changed retained private stage evidence'
        item['recovery_processes'] = [first, second]
        item['transaction_after_recovery'] = self.journal_snapshot(transaction_folder, folder / 'transaction-after-recovery')
        assert item['transaction_after_recovery']['journal']['state'] == ('ABORTED' if aborted else 'ROLLED_BACK')
        assert not item['transaction_after_recovery']['pending']
        item['after_recovery'] = self.snapshot(folder / 'after-recovery')
        assert item['after_recovery'] == self.baseline
        item['outcome'] = 'PASS_ACTUAL_PRIVATE_PREPARE_ABORT' if aborted else 'PASS_ACTUAL_PUBLICATION_FAILURE_AND_PROCESS_RECOVERY'
        self.save()
        print(json.dumps({'case': item['case'], 'outcome': item['outcome']}), flush=True)

    def publication_failure(self, number, name, target):
        folder, item = self.new_case(number, name, 'PUBLICATION_IO_FAILURE_BEFORE_WRITE')
        previous = self.transaction_ids()
        original = transaction._atomic_bytes
        marker = 'EXPECTED_' + name.upper().replace('-', '_')
        faults = []

        def fail_once(path, data):
            if Path(path).resolve() == target:
                faults.append({'target': target.relative_to(self.store).as_posix(),
                               'target_sha256_before_write': sha(target) if target.is_file() else None,
                               'proposed_sha256': hashlib.sha256(data).hexdigest(), 'timing': 'BEFORE_WRITE'})
                write(folder / 'injected-faults.json', faults)
                raise OSError(marker)
            return original(path, data)

        transaction._atomic_bytes = fail_once
        try:
            item['raw_exception'] = self.expected_exception(lambda: self.register_width(self.lab), OSError, marker, folder)
        finally:
            transaction._atomic_bytes = original
        assert len(faults) == 1, ('The specific publication fault must occur exactly once', faults)
        item['faults'] = faults
        published = self.new_transaction(previous)
        item['transaction_before_recovery'] = self.journal_snapshot(published, folder / 'transaction-before-recovery')
        self.assert_partial_publication(name, published, item)
        item['after_fault'] = self.snapshot(folder / 'after-fault')
        self.assert_pending_consumers_blocked(folder, item)
        self.save()
        self.recover_twice(folder, item, published)

    def hard_exit(self):
        folder, item = self.new_case(4, 'exit-after-native', 'REAL_CHILD_EXIT_AFTER_NATIVE_PUBLICATION')
        previous = self.transaction_ids()
        item['exit_process'] = self.child('exit-after-native', folder, 'exit-process', expected_code=91)
        fault = json.loads((folder / 'child-native-publication.json').read_bytes())
        assert fault['fault_count'] == 1 and fault['exit_code'] == 91
        assert fault['target'] == self.native.relative_to(self.store).as_posix()
        assert fault['before_sha256'] == self.baseline['native']['sha256']
        assert fault['after_sha256'] == sha(self.native) != fault['before_sha256']
        item['faults'] = [fault]
        published = self.new_transaction(previous)
        item['transaction_before_recovery'] = self.journal_snapshot(published, folder / 'transaction-before-recovery')
        self.assert_partial_publication('exit-after-native', published, item)
        item['after_fault'] = self.snapshot(folder / 'after-fault')
        self.assert_pending_consumers_blocked(folder, item)
        self.save()
        self.recover_twice(folder, item, published)

    def preparation_error(self):
        folder, item = self.new_case(5, 'error-after-real-prepare', 'INJECTED_ERROR_AFTER_SUCCESSFUL_ACTUAL_PREPARE')
        previous = self.transaction_ids()
        adapter = self.lab.adapters[BACKEND]
        original = adapter.prepare_bind
        prepared = []

        def actual_prepare_then_error(*args, **kwargs):
            revision = original(*args, **kwargs)
            assert sha(revision.prepared) == revision.after_sha256 != revision.before_sha256
            prepared.append({'target': revision.target.relative_to(self.store).as_posix(),
                             'prepared': revision.prepared.relative_to(self.store).as_posix(),
                             'before_sha256': revision.before_sha256, 'after_sha256': revision.after_sha256})
            write(folder / 'successful-real-prepare.json', prepared)
            raise RuntimeError('EXPECTED_PREPARE_FAILURE')

        adapter.prepare_bind = actual_prepare_then_error
        try:
            item['raw_exception'] = self.expected_exception(lambda: self.register_width(self.lab), RuntimeError,
                                                           'EXPECTED_PREPARE_FAILURE', folder)
        finally:
            adapter.prepare_bind = original
        assert len(prepared) == 1
        published = self.new_transaction(previous)
        item['transaction_before_recovery'] = self.journal_snapshot(published, folder / 'transaction-before-recovery')
        journal = item['transaction_before_recovery']['journal']
        assert journal['state'] == 'ABORTED' and journal['files'] == []
        assert not item['transaction_before_recovery']['pending']
        assert self.public_state() == self.baseline
        assert prepared[0]['before_sha256'] == self.baseline['native']['sha256']
        staged = self.store / prepared[0]['prepared']
        assert staged.is_file() and sha(staged) == prepared[0]['after_sha256']
        actual = json.loads((published / 'work/native/inspect-after/result.json').read_bytes())
        assert actual['ok'] and [entry['key'] for entry in actual['result']['parameters']] == [LENGTH, WIDTH]
        item['successful_actual_prepare'] = prepared[0]
        item['after_fault'] = self.snapshot(folder / 'after-fault')
        self.assert_length_only_baseline()
        self.save()
        self.recover_twice(folder, item, published, aborted=True)

    def result(self, name):
        reference = REFERENCE[name]
        experiment = check_id('E-' + self.run_id + '-' + name)
        observed = self.lab.run_experiment(study_id=self.study, experiment_id=experiment, backend=BACKEND,
                                           model=self.model, values=reference['values'])
        assert observed['status'] == 'COMPLETED_REVIEW_REQUIRED' and observed['decision'] == 'NOT_RELEASED'
        assert observed['solver_status'] == 'NOT_RUN' and observed['cad_revision']
        assert observed['metrics']['cad_bounds']['unit'] == 'mm' and observed['metrics']['cad_volume']['unit'] == 'mm^3'
        assert len(observed['metrics']['cad_bounds']['value']) == 3
        for value, expected in zip(observed['metrics']['cad_bounds']['value'], reference['bounds_mm']):
            near(value, expected, LENGTH_TOLERANCE_MM)
        near(observed['metrics']['cad_volume']['value'], reference['volume_mm3'], VOLUME_TOLERANCE_MM3)
        engineering = [item for item in observed['validations'] if item['type'] in ENGINEERING_UNKNOWN]
        assert len(engineering) == 6 and {item['type'] for item in engineering} == ENGINEERING_UNKNOWN
        assert all(item['status'] == 'UNKNOWN' and item['blocking'] for item in engineering)
        cad = self.store / 'experiments' / experiment / 'cad'
        native = self.fixture('describe', cad / 'editable.FCStd')
        shape = cq.importers.importStep(str(cad / 'native.step')).val()
        bounds = shape.BoundingBox()
        step = {'bounds_mm': [bounds.xlen, bounds.ylen, bounds.zlen], 'volume_mm3': shape.Volume()}
        assert len(native['bounds_mm']) == 3
        for representation in (native, step):
            for value, expected in zip(representation['bounds_mm'], reference['bounds_mm']):
                near(value, expected, LENGTH_TOLERANCE_MM)
            near(representation['volume_mm3'], reference['volume_mm3'], VOLUME_TOLERANCE_MM3)
        core = {'bounds_mm': observed['metrics']['cad_bounds']['value'],
                'volume_mm3': observed['metrics']['cad_volume']['value']}
        for left, right in ((core, native), (core, step), (native, step)):
            for a, b in zip(left['bounds_mm'], right['bounds_mm']):
                near(a, b, LENGTH_TOLERANCE_MM)
            near(left['volume_mm3'], right['volume_mm3'], VOLUME_TOLERANCE_MM3)
        item = {'case': 'experiment-' + name, 'outcome': 'PASS_ANALYTICAL_CORE_NATIVE_AND_STEP',
                'experiment_id': experiment, 'cad_revision': observed['cad_revision'],
                'metrics': observed['metrics'], 'native': native, 'step': step,
                'engineering_unknown': sorted(ENGINEERING_UNKNOWN), 'decision': observed['decision'],
                'solver_status': observed['solver_status']}
        self.record['cases'].append(item)
        self.immutable_experiments[experiment] = {'files': inventory(self.store / 'experiments' / experiment),
                                                'ledger_sha256': sha(self.store / 'ledger' / f'{experiment}.json'),
                                                'cad_revision': observed['cad_revision']}
        write(self.store / 'immutable-experiments.json', self.immutable_experiments)
        self.save()
        print(json.dumps({'case': item['case'], 'outcome': item['outcome']}), flush=True)
        return observed

    def successful_width(self):
        previous = self.transaction_ids()
        entry = self.register_width(self.lab)
        registry = self.lab.registry(self.study)
        source_sha = sha(self.native)
        assert registry['revision'] == 2 and [item['parameter_id'] for item in registry['entries']] == ['length', 'width']
        assert entry['source_sha256'] == source_sha != self.baseline['native']['sha256']
        assert all(item['source_sha256'] == source_sha for item in registry['entries'])
        assert [(item['current_value'], item['lower_bound'], item['upper_bound']) for item in registry['entries']] == [
            (12, 10, 24), (10, 8, 15)]
        assert sorted(path.name for path in self.history.iterdir()) == ['0000.json', '0001.json', '0002.json']
        assert (self.history / '0002.json').read_bytes() == self.registry_path.read_bytes()
        assert inventory(self.history)[:2] == self.baseline['registry_history']
        native = self.lab.inspect_native_model(self.model)
        assert native['source_sha256'] == source_sha
        assert [(item['key'], item['name'], item['value'], item['min'], item['max']) for item in native['parameters']] == [
            (LENGTH, 'length', 12, 10, 24), (WIDTH, 'width', 10, 8, 15)]
        published = self.new_transaction(previous)
        folder = self.store / 'successful-width'
        folder.mkdir()
        journal = self.journal_snapshot(published, folder / 'transaction')
        assert journal['journal']['state'] == 'COMMITTED' and not journal['pending']
        assert len(journal['journal']['files']) == 3
        assert all(sha(self.store / row['target']) == row['after'] for row in journal['journal']['files'])
        before_duplicate = self.snapshot(folder / 'before-duplicate')
        before_transactions = self.transaction_ids()
        raw = self.expected_exception(lambda: self.register_width(self.lab), ValueError,
                                      'Parameter ID or native CAD mapping already registered', folder)
        assert self.public_state() == before_duplicate and self.transaction_ids() == before_transactions
        self.assert_immutable_experiments(self.lab)
        self.record['cases'].append({'case': 'ordinary-width-registration-and-duplicate-refusal',
                                     'outcome': 'PASS_DUPLICATE_FREE_ACTUAL_NATIVE_CORE_PUBLICATION',
                                     'entry': entry, 'registry': registry, 'source_sha256': source_sha,
                                     'transaction': journal, 'duplicate_raw_exception': raw,
                                     'public_bytes_unchanged_after_duplicate': True})
        self.save()

    def run(self):
        try:
            check_id(self.study)
            for name in ('before', 'after', *[item['case'] for item in REFERENCE['fault_cases']]):
                check_id('E-' + self.run_id + ('-blocked-' if name not in ('before', 'after') else '-') + name)
            for index, original in enumerate(self.preserve_stores, 1):
                original = original.resolve()
                assert original.is_dir(), ('Preserved store is missing', str(original))
                assert not self.store.is_relative_to(original) and not original.is_relative_to(self.store), 'Stores must not overlap'
                frozen = inventory(original)
                write(self.store / 'preserved-store-inventories' / f'{index:02d}-before.json', frozen)
                self.preserved.append({'store': str(original), 'before': frozen})
            self.record['source_before'] = source_identity()
            source = self.record['source_before']
            assert not source['source_dirty'] and not source['fixture_dirty'], 'Commit/freeze clean source before actual acceptance'
            assert source['fixture_commit'] == FIXTURE_PIN, 'The exact tested fixture pin is required'
            self.record['runtime'] = runtime_identity()
            self.save()
            self.lab = Lab(self.store)
            self.lab.create_study(self.study, 'Recoverable real native registration',
                                  'Can interrupted registration preserve one editable native/Core revision?',
                                  'Private binding and verified before/after images restore exact original bytes.',
                                  'Compare analytical geometry and qualify bounded process/I/O recovery.')
            source_document = self.store / 'inputs' / 'imported-box.FCStd'
            source_document.parent.mkdir()
            original = self.fixture('box_new', source_document)
            assert original['bounds_mm'] == REFERENCE['source_defaults']['bounds_mm']
            near(original['volume_mm3'], 960, VOLUME_TOLERANCE_MM3)
            self.record['freecad_version'] = original['freecad_version']
            self.model = self.lab.import_native_model(source_document)['design']
            self.record['model'] = self.model
            self.native = self.store / 'native_designs' / self.model / 'editable.FCStd'
            self.registry_path = self.store / 'studies' / self.study / 'parameters.json'
            self.history = self.registry_path.parent / 'registry_history'
            self.lab.register_parameter(self.study, BACKEND, self.model, LENGTH, 'length', 'Box length', 10, 24)
            before = self.result('before')
            self.baseline = self.snapshot(self.store / 'baseline')
            shutil.copytree(self.store / 'experiments', self.store / 'baseline/experiments')
            self.record['baseline'] = self.baseline
            self.save()
            self.assert_length_only_baseline()
            self.publication_failure(1, 'native-before-write', self.native)
            self.publication_failure(2, 'history-before-write', self.history / '0002.json')
            self.publication_failure(3, 'registry-before-write', self.registry_path)
            self.hard_exit()
            self.preparation_error()
            self.successful_width()
            after = self.result('after')
            assert after['cad_revision'] != before['cad_revision']
            assert before['registry_revision'] == 1 and after['registry_revision'] == 2
            self.assert_immutable_experiments(Lab(self.store))
            self.record.update(outcome='PASS_ACTUAL_NATIVE_REGISTRATION_PUBLICATION_AND_PROCESS_RECOVERY',
                               failure_cases=5, publication_recovery_cases=4, private_abort_cases=1,
                               analytical_experiments=2, duplicate_refusals=1,
                               engineering_decision='NOT_RELEASED', solver_status='NOT_RUN',
                               immutable_experiments=self.immutable_experiments,
                               all_original_experiment_files_ledger_threads_and_revisions_unchanged=True)
        except BaseException as error:
            self.record.update(outcome='FAIL', **exception_record(error))
            if self.record['cases'] and self.record['cases'][-1]['outcome'] == 'RUNNING':
                self.record['cases'][-1]['outcome'] = 'FAIL'
            raise
        finally:
            checks_errors = []

            def final_check(name, call):
                try:
                    call()
                except BaseException as error:
                    checks_errors.append(error)
                    self.record.setdefault('final_check_errors', []).append({'check': name, **exception_record(error)})
                    self.record['outcome'] = 'FAIL'

            def check_source():
                self.record['source_after'] = source_identity()
                if 'source_before' in self.record:
                    assert self.record['source_after'] == self.record['source_before'], 'Source identity or cleanliness changed'

            def check_runtime():
                if 'runtime' in self.record:
                    assert runtime_identity() == self.record['runtime'], 'Runtime/source bytes changed during acceptance'

            def check_reference():
                assert sha(self.store / 'predeclared-reference.json') == self.record['predeclared_reference_sha256']

            final_check('source', check_source)
            final_check('runtime', check_runtime)
            final_check('predeclared-reference', check_reference)
            for index, preserved in enumerate(self.preserved, 1):
                def check_preserved():
                    preserved['after'] = inventory(Path(preserved['store']))
                    write(self.store / 'preserved-store-inventories' / f'{index:02d}-after.json', preserved['after'])
                    assert preserved['after'] == preserved['before'], ('Original preserved store changed', preserved['store'])
                    preserved['all_original_files_unchanged'] = True
                final_check('preserved-store-' + str(index), check_preserved)
            self.record['completed_utc'] = utc()
            self.save()
            if checks_errors and sys.exc_info()[0] is None:
                raise checks_errors[0]
        print(json.dumps({'outcome': self.record['outcome'], 'cases': len(self.record['cases']),
                          'store': str(self.store), 'receipt': str(self.receipt)}), flush=True)


def child_mode(args):
    """Private subprocess protocol of this acceptance script, not a Lab fault API."""
    store, folder, result_path = args.store.resolve(), args._case_root.resolve(), args._child_result.resolve()
    assert folder.is_relative_to(store / 'acceptance-cases') and result_path.is_relative_to(folder)
    assert not result_path.exists(), 'Preserve every previous child response'
    parent = json.loads((store / 'native_registration_acceptance.json').read_bytes())
    assert parent['outcome'] == 'RUNNING' and parent['study_id'] == args._study and parent['model'] == args._model
    assert parent['run_id'] == args.run_id
    source = source_identity()
    assert source == parent['source_before'] and source['fixture_commit'] == FIXTURE_PIN
    lab = Lab(store)
    original = transaction._atomic_bytes
    try:
        if args._child == 'recover':
            result = lab.recover_registration(args._study)
            write(result_path, {'ok': True, 'pid': os.getpid(), 'source': source, 'result': result})
            return
        native = store / 'native_designs' / args._model / 'editable.FCStd'
        before = sha(native)
        faults = 0

        def publish_native_then_exit(path, data):
            nonlocal faults
            original(path, data)
            if Path(path).resolve() == native:
                faults += 1
                event = {'fault_count': faults, 'target': native.relative_to(store).as_posix(),
                         'before_sha256': before, 'after_sha256': sha(native), 'exit_code': 91,
                         'pid': os.getpid(), 'timing': 'AFTER_REAL_NATIVE_PUBLICATION'}
                write(folder / 'child-native-publication.json', event)
                print(json.dumps(event), flush=True)
                os._exit(91)

        transaction._atomic_bytes = publish_native_then_exit
        lab.register_parameter(args._study, BACKEND, args._model, WIDTH, 'width', 'Box width', 8, 15)
        raise AssertionError('Actual native publication did not reach the exit91 fault')
    except BaseException as error:
        write(result_path, {'ok': False, 'pid': os.getpid(), **exception_record(error)})
        raise
    finally:
        transaction._atomic_bytes = original


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', type=Path, required=True)
    parser.add_argument('--run-id', default='native-registration')
    parser.add_argument('--preserve-store', type=Path, action='append', default=[])
    parser.add_argument('--_child', choices=('exit-after-native', 'recover'), help=argparse.SUPPRESS)
    parser.add_argument('--_study', help=argparse.SUPPRESS)
    parser.add_argument('--_model', help=argparse.SUPPRESS)
    parser.add_argument('--_case-root', dest='_case_root', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--_child-result', dest='_child_result', type=Path, help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    if arguments._child:
        child_mode(arguments)
    else:
        Acceptance(arguments.store.resolve(), arguments.run_id, arguments.preserve_store).run()
