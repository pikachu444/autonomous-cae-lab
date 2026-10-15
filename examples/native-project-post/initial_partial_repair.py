"""F4: initially absent pinned source -> live exact repair -> Save/head -> cold.

Run only after correction adoption, through scripts/native_check.py. This file
is a prepared acceptance driver; creating it does not claim native execution.
"""
from copy import deepcopy
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

from native_roundtrip import REPO, grid, write_json, tracked_open


def setup(root):
    from paraview import simple as p
    from apps.desktop_post import external, bridge, commands
    from apps.desktop_post.workspace import source_revision
    from caelab.native_project_inputs import NativeOnlyContext, register_saved, verify_registered
    original = root/'original'; original.mkdir(parents=True)
    a, b = original/'A'/'frame.vtu', original/'B'/'frame.vtu'
    grid(a, .1); grid(b, 2.)
    external.open_result(a, original/'project')
    owner = bridge.Owner(); commands.set_save_owner(owner)
    try:
        _, record = external.admit_result(b)
        record.update(source_ref='B', source_revision=source_revision(record))
        owner.project_document['sources']['B'] = record
        a0 = owner.workspace.edit_filter(draft={'source_ref': 'result', 'filter': 'WarpByVector',
            'settings': {'association': 'POINTS', 'array': 'U', 'scale_factor': .1}}, title='기존 변형')
        ref_a = a0.get('id') or a0['object_ref']
        owner.workspace.validate(object_ref=ref_a); owner.workspace.apply(object_ref=ref_a, show=False)
        owner.save_project()
        applied = owner.workspace.applied(owner.workspace.object(ref_a))
        for proxy in reversed(owner.workspace.bundles[applied['id']]['proxies']): p.Delete(proxy)
        owner.close(); commands.clear_save_owner(owner)
        owner = bridge.Owner(); commands.set_save_owner(owner)
        applied = owner.workspace.applied(owner.workspace.object(ref_a))
        assert owner.workspace.bundles[applied['id']]['retained_only']
        _, shared = external.admit_result(Path(applied['retained_reader']['input_paths'][0]))
        shared.update(source_ref='Shared', source_revision=source_revision(shared))
        owner.project_document['sources']['Shared'] = shared
        project = owner.save_project()
        source_bytes = project.read_bytes()
        seed = root/'replacement-seed'/'frame.vtu'; seed.parent.mkdir()
        shutil.copyfile(b, seed)
        b.rename(b.with_suffix('.missing'))
        context = NativeOnlyContext(root/'registration', approved_roots={'original': original})
        registered = register_saved(context, {'mode': 'selected_file', 'native_kind': 'post', 'root_id': 'original',
            'relative': project.relative_to(original).as_posix()}, command_id='C'+uuid.uuid4().hex)
        verified = verify_registered(context, registered['reference'])
        assert not any(row['original_location'] == str(b) for row in verified.snapshot['logical_origins'])
        assert verified.snapshot['unavailable'] and verified.snapshot['validation']['closure'] == 'DECLARED_PARTIAL'
        assert project.read_bytes() == source_bytes
        write_json(root/'expected.json', {'source_reference': registered['reference'], 'old_source': str(b),
            'source_snapshot_sha256': verified.snapshot['snapshot_sha256'],
            'missing': deepcopy(verified.snapshot['unavailable']), 'source_project_sha256': external.sha(project),
            'analysis_a': ref_a, 'analysis_a_original': [{key: row[key] for key in ('id','recipe','graph','bindings')} for row in owner.workspace.object(ref_a)['history']],
            'analysis': deepcopy(owner.project_document.get('analysis', {}))})
    finally:
        owner.close(); commands.clear_save_owner(owner)


def repair_and_save(root):
    from paraview import simple as p
    from apps.desktop_post import portable_project as post, external, commands
    from caelab.native_project_inputs import NativeOnlyContext, verify_registered
    from caelab.portable_project_native import prepare_open, verify_opened
    from caelab.native_inputs import register_native_input
    from caelab import portable_project as portable
    from caelab.native_post_dependencies import history_key
    expected_path = root/('expected-corrected.json' if (root/'expected-corrected.json').exists() else 'expected.json')
    expected = json.loads(expected_path.read_text(encoding='utf-8'))
    context = NativeOnlyContext(root/'registration', approved_roots={})
    ticket = prepare_open(context, {'reference': expected['source_reference'], 'intent': 'saved', 'target_id': None,
        'expected_head': None, 'selection': None, 'allow_partial': True}, command_id='C'+uuid.uuid4().hex)
    opened, effects = tracked_open(lambda: post.restore_bound_project(ticket.verified_input, ticket.binding, allow_partial=True))
    verify_opened(context, ticket.binding.open_id, opened['readback'])
    owner = opened['owner']; owner.native_project_context = context
    try:
        assert opened['status'] == 'PARTIAL_OPEN' and owner.saved_revision is None and owner.descriptor()['dirty']
        write_json(root/'before-repair-debug.json', {'issues': owner.workspace.restore_issues, 'bundles': list(owner.workspace.bundles), 'sources': [name for name,_ in p.GetSources()]})
        healthy = owner.project_document['sources']['result']['reader_name']
        assert p.FindSource(healthy) is not None
        assert p.FindSource(owner.project_document['sources']['B']['reader_name']) is None
        seed = root/'replacement-seed'/'frame.vtu'
        registered = register_native_input(context.root, seed.parent, seed, 'D'+uuid.uuid4().hex,
            root_id='explicit-replacement', relative=seed.name, limit=1024*1024)
        receipt = {**registered, 'path': str(context.root/registered['file']),
            'source_pins': [{'path': str(context.root/row['file']), **{key: row[key] for key in ('bytes', 'sha256')}} for row in registered['files']]}
        result = owner.workspace.repair_source(source_ref='B', input_id=receipt['id'], receipt=receipt)
        assert result['content_changed'] is False and result['retained_branches_recomputed'] is False
        work = owner.workspace
        write_json(root/'restore-debug.json', {'issues': work.restore_issues, 'bundles': list(work.bundles), 'sources': [name for name,_ in p.GetSources()]})
        created = work.edit_filter(draft={'source_ref': expected['analysis_a'], 'filter': 'WarpByVector',
            'settings': {'association': 'POINTS', 'array': 'U', 'scale_factor': .3}}, title='추가 변형')
        ref_b = created.get('id') or created['object_ref']
        work.validate(object_ref=ref_b); work.apply(object_ref=ref_b, show=False)
        record_b = work.applied(work.object(ref_b))
        frozen = deepcopy({key: record_b[key] for key in ('id', 'recipe', 'graph', 'bindings')})
        assert tuple(history_key(ref_b, record_b).values()) in work._new_history_keys
        saved = post.save_current_project(owner, confirm_first_save=lambda: True)
        assert tuple(history_key(ref_b, record_b).values()) not in work._new_history_keys
        assert saved.is_file() and owner.native_target_head['generation'] == 1 and not owner.descriptor()['dirty']
        actual = verify_registered(context, owner.native_target_head['reference'])
        assert actual.snapshot['validation']['closure'] == 'COMPLETE'
        # Same-session repair AFTER the new B1 basis was published. Shared
        # points to A0's retained bytes; the repair updates A0 and B1's readers.
        shared_path = Path(work.document['sources']['Shared']['entry_path'])
        moved = register_native_input(context.root, shared_path.parent, shared_path, 'D'+uuid.uuid4().hex,
            root_id='current-retained', relative=shared_path.name, limit=1024*1024)
        moved_receipt = {**moved, 'path': str(context.root/moved['file']),
            'source_pins': [{'path': str(context.root/row['file']), **{key: row[key] for key in ('bytes', 'sha256')}} for row in moved['files']]}
        repair = work.repair_source(source_ref='Shared', input_id=moved_receipt['id'], receipt=moved_receipt)
        assert {expected['analysis_a'], ref_b} <= {row[0] for row in repair['affected_histories']}
        work._verify_record(work.object(ref_b), record_b, work.bundles[record_b['id']])
        assert post.compare_history_inputs(work, work.object(ref_b), record_b, mode='retained')['state'] == 'SAME'
        bundle = work.bundles[record_b['id']]
        native_filter = next(proxy for proxy in bundle['proxies'] if proxy.GetXMLName() == 'WarpVector')
        prior_scale = float(native_filter.ScaleFactor)
        native_filter.ScaleFactor = prior_scale + .1
        try:
            try: work._verify_record(work.object(ref_b), record_b, bundle)
            except ValueError as error: assert str(error).startswith('PIPELINE_CHANGED:')
            else: raise AssertionError('Physical filter change was not detected')
        finally:
            native_filter.ScaleFactor = prior_scale
        work._verify_record(work.object(ref_b), record_b, bundle)
        assert {key: record_b[key] for key in frozen} == frozen
        assert [{key: row[key] for key in ('id','recipe','graph','bindings')} for row in work.object(expected['analysis_a'])['history']] == expected['analysis_a_original']
        saved = post.save_current_project(owner)
        assert owner.native_target_head['generation'] == 2
        write_json(root/'saved-inventory.json', {'cores': {ref: [{key: row[key] for key in ('id','recipe','graph','bindings')} for row in obj['history']] for ref,obj in work.state['objects'].items()}, 'analysis_b': ref_b})
        original = verify_registered(context, expected['source_reference'])
        assert original.snapshot['snapshot_sha256'] == expected['source_snapshot_sha256']
        assert original.snapshot['unavailable'] == expected['missing']
        inspection = portable.inspect_copy(context, [{'native': owner.native_target_head['reference'],
            'copy_intent': 'complete', 'working_target': True}])
        portable.create_copy(context, inspection, root/'copy', approved=True,
            command_id='C'+uuid.uuid4().hex, session_id=context.session_id)
        write_json(root/'repair-readback.json', {'status': 'INITIAL_PARTIAL_REPAIRED_NATIVE_SAVED',
            'head': owner.native_target_head, 'initial_member_absent': True, 'original_missing_unchanged': True,
            'old_source_path_absent': not Path(expected['old_source']).exists(), 'open_effects': effects,
            'new_history_marker_retired': True, 'same_session_retained_repair': repair,
            'frozen_history_unchanged': True, 'physical_filter_change_detected': True})
    finally:
        owner.close(); commands.clear_save_owner(owner)


def cold(root):
    from paraview import simple as p
    from apps.desktop_post import portable_project as post, external, commands
    from caelab import portable_project as portable
    from caelab.portable_project_native import prepare_open, verify_opened
    expected_path = root/('expected-corrected.json' if (root/'expected-corrected.json').exists() else 'expected.json')
    expected = json.loads(expected_path.read_text(encoding='utf-8'))
    context = portable.open_project(root/'copy')
    manifest = portable.verify_project(root/'copy')
    target = manifest['native_projects'][0]
    head = json.loads((root/'copy'/target['head_file']).read_text(encoding='utf-8'))
    ticket = prepare_open(context, {'reference': head['reference'], 'intent': 'working', 'target_id': target['target_id'],
        'expected_head': {'generation': head['head_generation'], 'reference': head['reference']}, 'selection': None,
        'allow_partial': False}, command_id='C'+uuid.uuid4().hex)
    opened, effects = tracked_open(lambda: post.restore_bound_project(ticket.verified_input, ticket.binding))
    verify_opened(context, ticket.binding.open_id, opened['readback'])
    owner = opened['owner']
    try:
        assert opened['status'] == 'OPENED' and not Path(expected['old_source']).exists()
        for source in owner.project_document['sources'].values():
            reader = p.FindSource(source['reader_name']); reader.UpdatePipeline()
            assert all(path.is_file() and path.is_relative_to(ticket.binding.materialization_root)
                       for path in external.reader_input_files(reader))
        inventory = json.loads((root/'saved-inventory.json').read_text(encoding='utf-8'))
        assert {ref: [{key: row[key] for key in ('id','recipe','graph','bindings')} for row in obj['history']] for ref,obj in owner.workspace.state['objects'].items()} == inventory['cores']
        for ref in (expected['analysis_a'], inventory['analysis_b']): owner.workspace._bundle(owner.workspace.object(ref))
        assert owner.saved_revision is None and owner.descriptor()['dirty']  # A copied DERIVED_BASE has no local Save.
        write_json(root/'cold-readback.json', {'status': 'REPAIRED_CURRENT_HEAD_COLD_OPENED',
            'old_source_absent': True, 'first_registration_absent': not (root/'registration').exists(),
            'history_inventory_unchanged': True, 'local_derived_unsaved': True, 'open_effects': effects})
    finally:
        owner.close(); commands.clear_save_owner(owner)


def run(root, pvpython):
    script = str(Path(__file__).resolve())
    def invoke(phase): subprocess.run([pvpython, script, phase, '--root', str(root)], cwd=REPO, check=True, timeout=120)
    if not (root/'expected.json').exists(): invoke('setup')
    held = []
    try:
        (root/'original').rename(root/'original-unavailable'); held.append('original')
        invoke('repair')
        (root/'registration').rename(root/'registration-unavailable'); held.append('registration')
        invoke('cold')
    finally:
        for name in reversed(held): (root/(name+'-unavailable')).rename(root/name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('phase', choices=['run','setup','repair','cold'])
    parser.add_argument('--root', type=Path, required=True); parser.add_argument('--pvpython'); args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    if args.phase == 'run': run(args.root.resolve(), args.pvpython)
    elif args.phase == 'setup': setup(args.root.resolve())
    elif args.phase == 'repair': repair_and_save(args.root.resolve())
    else: cold(args.root.resolve())
