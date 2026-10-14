"""Opt-in actual FreeCAD save/reopen/edit acceptance. No solver or result reader.

Run VerifyBeamReopen.FCMacro in a separate normal FreeCAD 1.1.4 process. Uses
existing Project/Owner/beam commands and installed mesh/section writers. Missing
runtime is not replaced. Failures and all previously frozen inputs are retained.
"""
from copy import deepcopy
import json
from pathlib import Path
import uuid

from caelab import native_cad
from caelab.storage import save_json
from apps.desktop_pre.beam_mesh_binding import REFERENCE_KEY, require_same_binding


def _check(condition, message):
    if not condition:
        raise AssertionError(message)


def _pins(folder):
    return {p.relative_to(folder).as_posix(): native_cad.sha(p)
            for p in sorted(folder.rglob('*')) if p.is_file()}


def run(root):
    import FreeCAD as App
    import FreeCADGui as Gui
    from apps.desktop_pre import cae_prep, beam_native, projects
    from apps.desktop_pre.bridge import Owner
    from examples.beam.beam_example import create
    from examples.beam.beam_native_acceptance import _command

    _check(list(map(str, App.Version()[:3])) == ['1', '1', '4'], 'FreeCAD 1.1.4 is required')
    if getattr(cae_prep, 'CONNECTION', None) is not None:
        raise RuntimeError('제품 연결이 없는 별도 FreeCAD에서 실행하세요. 열린 문서 소유자를 복제하지 않습니다.')
    root = Path(root).resolve() / ('beam-reopen-' + uuid.uuid4().hex[:12])
    root.mkdir(parents=True, exist_ok=False)
    report = {'kind': 'beam-native-reopen-acceptance', 'freecad_version': list(map(str, App.Version())),
              'native_kernel': True, 'native_writers': True, 'solver_executed': False,
              'gui_visual_acceptance': 'NOT_RUN', 'cases': {}, 'status': 'RUNNING'}
    output = root / 'beam_reopen_acceptance.json'

    def close(owner):
        name = owner.doc.Name
        owner.close()
        App.closeDocument(name)

    def reopen(path, exchange):
        # Same checked working-copy route used by the native model opener.
        manifest, entry = native_cad.unpack_project(path, root / ('open-' + uuid.uuid4().hex[:10]))
        doc = App.openDocument(str(entry)); doc.UndoMode = 1
        try:
            projects.remember_open(doc, manifest, path)
            return Owner(doc, exchange, App=App, Gui=Gui)
        except BaseException:
            projects.OPENED.pop(doc.Name, None)
            App.closeDocument(doc.Name)
            raise

    for case in ('moment_1', 'section_90'):
        owner = None; row = {'status': 'FAILED'}; snapshots = []
        try:
            exchange = root / case / 'exchange'
            owner, key = create(case, output_root=exchange, attach=False)
            reference = deepcopy(owner.beam._get(key))
            _check(REFERENCE_KEY in reference, 'Apply did not retain the original ordered mesh')
            _check(reference[REFERENCE_KEY]['nodes'][0]['id'] == 101, 'Sparse native example was changed')
            original = _command(owner, 'pre.beam.freeze', {'analysis_id': key})
            original_folder = (owner.export_root / original['snapshot_relative']).parent
            original_pins = _pins(original_folder); snapshots.append(str(original_folder))
            saved = owner.project.save(root / (case + '.caepre'))
            saved_hash = native_cad.sha(saved['path'])
            prior_session = owner.session_id; document_id = owner.document_id
            close(owner); owner = None
            owner = reopen(saved['path'], exchange)
            _check(owner.session_id != prior_session and owner.document_id == document_id, 'New owner identity mismatch')
            before = owner.read_metadata(); generation = owner.generation
            for _ in range(3):
                _check(owner.beam.inspect(key)['can_freeze'], 'Reopened unchanged beam is blocked')
            _check(owner.read_metadata() == before and owner.generation == generation, 'Inspect mutated native metadata')
            current_model, current_binding = beam_native.geometry(owner, owner.beam._get(key)['draft'])
            mapping = require_same_binding(reference, current_model, current_binding)
            _check(mapping['kind'] == 'RENUMBERED', 'Expected actual native sparse-to-dense compaction was not observed')
            _check(len(mapping['nodes']) == 21 and len(mapping['elements']) == 10, 'Incomplete exact correspondence')
            _check(current_model['end_node_ids'] == [1, 21], 'Unexpected native end labels; do not alter test to guess them')
            row.update(node_map=mapping['nodes'], element_map=mapping['elements'], initial_project=saved['path'])

            # Export immediately after reopen without an Apply. This must leave
            # the old reference in the editable document and use current IDs.
            exported = _command(owner, 'pre.beam.freeze', {'analysis_id': key})
            folder = (owner.export_root / exported['snapshot_relative']).parent; snapshots.append(str(folder))
            model = json.loads((folder / 'mesh.json').read_text(encoding='utf-8'))
            _check(model['nodes'] == current_model['nodes'] and model['elements'] == current_model['elements'], 'New deck model is not the live native mesh')
            _check(owner.beam._get(key) == reference, 'Freeze silently rewrote the saved reference')

            draft = deepcopy(reference['draft'])
            draft['section']['width_mm'] = '12'; draft['ends'][1]['moment_Nmm'][1] = '1250'
            _command(owner, 'pre.beam.apply', {'analysis_id': key, 'draft': draft})
            applied = deepcopy(owner.beam._get(key))
            _check(applied[REFERENCE_KEY]['nodes'] == current_model['nodes'], 'Explicit Apply did not capture current IDs')
            _check(owner.doc.getObject(draft['section']['object_id']).RectWidth.getValueAs('mm').Value == 12, 'Native width edit missing')
            _check(owner.doc.getObject(applied['end_object_ids'][1]).MomentY.getValueAs('N*mm').Value == 1250, 'Native moment edit/unit missing')
            _command(owner, 'document.undo', {})
            _check(owner.beam._get(key) == reference and owner.beam.inspect(key)['can_freeze'], 'Undo lost old reference')
            _command(owner, 'document.redo', {})
            _check(owner.beam._get(key) == applied and owner.beam.inspect(key)['can_freeze'], 'Redo lost current reference')
            exported = _command(owner, 'pre.beam.freeze', {'analysis_id': key})
            folder = (owner.export_root / exported['snapshot_relative']).parent; snapshots.append(str(folder))
            text = (folder / 'beam.inp').read_text(encoding='ascii')
            _check('\n12,20\n' in text and '\n21,5,1250\n' in text, 'New native-checked input missed edited section/moment')
            edited = owner.project.save(root / (case + '-edited.caepre'))
            close(owner); owner = None; owner = reopen(edited['path'], exchange)
            _check(owner.beam.inspect(key)['can_freeze'] and owner.beam._get(key)['draft'] == draft, 'Edited project did not reopen')
            _check(owner.doc.getObject(draft['section']['object_id']).RectWidth.getValueAs('mm').Value == 12, 'Reopened native width differs')
            _check(owner.doc.getObject(applied['end_object_ids'][1]).MomentY.getValueAs('N*mm').Value == 1250, 'Reopened native moment differs')

            invalid = deepcopy(draft); invalid['section']['width_mm'] = '1e'
            _command(owner, 'pre.beam.draft', {'analysis_id': key, 'draft': invalid})
            invalid_saved = owner.project.save(root / (case + '-invalid.caepre'))
            close(owner); owner = None; owner = reopen(invalid_saved['path'], exchange)
            _check(owner.beam._get(key)['draft']['section']['width_mm'] == '1e', 'Raw invalid draft lost')
            _check(not owner.beam.inspect(key)['can_freeze'], 'Invalid draft was accepted')
            _check(owner.doc.getObject(draft['section']['object_id']).RectWidth.getValueAs('mm').Value == 12, 'Invalid draft overwrote the native width')
            fixed = deepcopy(invalid); fixed['section']['width_mm'] = '14'
            _command(owner, 'pre.beam.apply', {'analysis_id': key, 'draft': fixed})
            _check(owner.beam.inspect(key)['can_freeze'], 'Explicit invalid-draft repair failed')

            # Real object remains in the document after Analysis removal.
            owner.doc.openTransaction('검사: 해석 끝 조건 제거')
            owner.doc.getObject(key).removeObject(owner.doc.getObject(applied['end_object_ids'][1]))
            owner.doc.recompute(); owner.doc.commitTransaction()
            _check(not owner.beam.inspect(key)['can_freeze'], 'Removed Analysis condition was accepted')
            _command(owner, 'document.undo', {})
            _check(owner.beam.inspect(key)['can_freeze'], 'Explicit Undo did not restore the condition')
            owner.doc.openTransaction('검사: 원형상 길이 변경')
            owner.doc.getObject(fixed['edge']['object']).setDatum(1, App.Units.Quantity('1100 mm'))
            owner.doc.recompute(); owner.doc.commitTransaction()
            _check(not owner.beam.inspect(key)['can_freeze'], 'Real shape change was treated as relabeling')
            _command(owner, 'document.undo', {})
            _check(owner.beam.inspect(key)['can_freeze'], 'Undo of shape change did not restore the reference')
            _check(_pins(original_folder) == original_pins and native_cad.sha(saved['path']) == saved_hash,
                   'Original frozen inputs/project changed')
            row.update(status='PASS', reopened_project=edited['path'], raw_invalid_project=invalid_saved['path'],
                       inspection_read_only=True, prior_inputs_unchanged=True, current_id_export=True)
        except Exception as error:
            row.update(error_type=type(error).__name__, message=str(error))
        finally:
            row['snapshots'] = snapshots
            if owner is not None:
                try: close(owner)
                except Exception as error: row.update(status='FAILED', cleanup_error=str(error))
            report['cases'][case] = row
            save_json(output, report)
    report['status'] = 'PASS' if all(row['status'] == 'PASS' for row in report['cases'].values()) else 'FAIL'
    save_json(output, report)
    return output
