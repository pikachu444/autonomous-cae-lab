"""Read/re-freeze the ORIGINAL FCStd in one newly owned FreeCAD 1.1.4 process.

No new specimen, no Apply, no save/repair/migration, no solver or source rebasing.
Actual result remains NOT_RUN until this tool runs inside a real FreeCAD process.
"""
from pathlib import Path
from copy import deepcopy
import hashlib
import json
import os
import sys
import traceback
from unittest.mock import patch


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def differences(old, new, trail=''):
    if type(old) is not type(new):
        return [{'path': trail, 'expected': old, 'actual': new}]
    if isinstance(old, dict):
        rows = []
        for key in sorted(set(old) | set(new)):
            if key not in old or key not in new:
                rows.append({'path': trail+'.'+key, 'expected': old.get(key), 'actual': new.get(key)})
            else:
                rows.extend(differences(old[key], new[key], trail+'.'+key))
        return rows
    if isinstance(old, list):
        if len(old) != len(new):
            return [{'path': trail, 'expected_length': len(old), 'actual_length': len(new)}]
        return [row for i, (a, b) in enumerate(zip(old, new)) for row in differences(a, b, trail+'['+str(i)+']')]
    return [] if old == new else [{'path': trail, 'expected': old, 'actual': new}]


def run():
    cfgpath, token = os.environ.get('CAELAB_LAW_C1_CONFIG'), os.environ.get('CAELAB_LAW_C1_TOKEN')
    if not cfgpath or not token:
        raise RuntimeError('Owned C1 configuration/token required; no native access/quit performed')
    cfg = json.loads(Path(cfgpath).read_text(encoding='utf-8'))
    if cfg.get('token') != token:
        raise RuntimeError('Wrong owned C1 process; no native access/quit performed')
    import FreeCAD as App
    import FreeCADGui as Gui
    if App.listDocuments():
        raise RuntimeError('Refusing an existing native process with open documents')
    output = Path(cfg['output']);output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'STARTING', 'stage': 'ORIGINAL_FCSTD_FRESH_OWNER_REFREEZE',
              'FreeCAD': 'ACTUAL', 'version': list(App.Version()), 'pid': os.getpid(),
              'FE_execution': 'NOT_RUN', 'Apply_calls': 0, 'native_save_calls': 0,
              'source_guard_io_attempts': [], 'cleanup': []}
    owner = None;opened = [];tripwire = None
    try:
        from caelab.storage import load_json, save_json, canonical_hash
        from caelab.law_native_identity import semantic_target, require_native_version
        from caelab import material_fe_transfer as transfer
        from apps.desktop_pre.bridge import Owner
        from apps.desktop_pre import law_native_material as native
        from tools.law_native.c1_tripwires import SourceGuardTripwire
        require_native_version(App.Version())
        assert sha(cfg['fcstd']) == cfg['fcstd_sha256'], 'Original FCStd hash mismatch'
        frozen = load_json(cfg['frozen']);original_hash = sha(cfg['frozen'])
        expected = frozen['simulation_draft']['settings']['source_receipt']
        doc = App.openDocument(cfg['fcstd']);opened = list(App.listDocuments())
        owner = Owner(doc, output/'exports', App=App, Gui=Gui)
        owner.assert_thread()
        assert owner.document_id == expected['applied_target']['document_id'], 'Persistent owner document ID differs'
        selection = deepcopy(expected['selection'])
        before = canonical_hash(owner.read_metadata());generation = owner.generation
        tripwire = SourceGuardTripwire(expected)
        with tripwire:
            assignment = native.read(owner.fem, selection)['assignment']
            assert assignment == expected, 'Stored assignment differs; no migration/rehash allowed'
            captured = native.capture(owner.fem, selection)
            save_json(output/'captured-native-target.json', captured)
            report['physical_differences'] = differences(semantic_target(expected['applied_target']), semantic_target(captured))
            def no_apply(*args, **kwargs):
                report['Apply_calls'] += 1
                raise AssertionError('Re-freeze must not Apply/re-sign')
            with patch.object(native, 'apply', no_apply):
                refrozen = native.freeze(owner.fem, selection)
            assert refrozen['simulation_draft'] == frozen['simulation_draft'], 'Exact law/mesh/protocol/receipt changed'
            assert owner.generation == generation and canonical_hash(owner.read_metadata()) == before
            assert sha(cfg['fcstd']) == cfg['fcstd_sha256'] and sha(cfg['frozen']) == original_hash
            save_json(output/'refrozen-simulation.json', refrozen)
            report.update(status='PASS', current_document_name=doc.Name,
                assignment_sha256=assignment['assignment_sha256'], review_sha256=assignment['review']['review_sha256'],
                source_sha256=assignment['review']['source']['snapshot_sha256'],
                simulation_draft_sha256=canonical_hash(refrozen['simulation_draft']),
                metadata_unchanged=True, original_fcstd_sha256=sha(cfg['fcstd']),
                previous_session=frozen['native_target']['session_id'], current_session=owner.session_id)
            assert report['previous_session'] != report['current_session']
    except BaseException as error:
        report.update(status='FAIL', error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
        traceback.print_exc()
    finally:
        if tripwire is not None:
            report['source_guard_io_attempts'] = tripwire.attempts
        if owner is not None:
            try:
                owner.close();report['cleanup'].append('OWNER_CLOSED')
            except BaseException as error:
                report['status'] = 'FAIL';report['cleanup'].append('OWNER_CLOSE_ERROR: '+str(error))
        # All these documents were opened only after the empty-process check.
        for name in list(App.listDocuments()):
            try:
                App.closeDocument(name);report['cleanup'].append('OWN_DOCUMENT_CLOSED: '+name)
            except BaseException as error:
                report['status'] = 'FAIL';report['cleanup'].append('DOCUMENT_CLOSE_ERROR: '+str(error))
        try:
            report['original_fcstd_unchanged'] = sha(cfg['fcstd']) == cfg['fcstd_sha256']
            if not report['original_fcstd_unchanged']: report['status'] = 'FAIL'
        except BaseException as error:
            report.update(status='FAIL', original_file_check_error=str(error))
        (output/'stage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        # Parent supervisor owns and finally closes/reaps this exact process tree.
        Gui.getMainWindow().close()
