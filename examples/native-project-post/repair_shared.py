"""One selected source, shared auxiliary/retained readers, atomic location repair."""
from copy import deepcopy
import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid

from native_roundtrip import REPO, write_json, tracked_open


def setup(root, original):
    from paraview import simple as p
    from apps.desktop_post import commands, bridge, external
    from apps.desktop_post.workspace import source_revision
    from caelab.native_project_inputs import NativeOnlyContext, register_saved
    expected = json.loads((original / 'expected.json').read_text(encoding='utf-8'))
    os.environ['CAE_POST_PROJECT'] = expected['project']
    commands.restore_workspace()
    owner = bridge.Owner(); commands.set_save_owner(owner)
    try:
        a = owner.workspace.applied(owner.workspace.object(expected['analysis_a']))
        entry = Path(a['retained_reader']['input_paths'][0])
        shared, record = external.admit_result(entry)
        record.update(source_ref='Shared', source_revision=source_revision(record))
        owner.project_document['sources']['Shared'] = record
        auxiliary = p.XMLUnstructuredGridReader(registrationName='Shared auxiliary', FileName=[str(entry), str(entry)])
        auxiliary.UpdatePipeline()
        saved = owner.save_project()
        context = NativeOnlyContext(root / 'registration', approved_roots={'original': original / 'original'})
        admitted = register_saved(context, {'mode': 'selected_file', 'native_kind': 'post', 'root_id': 'original',
            'relative': saved.relative_to(original / 'original').as_posix()}, command_id='C' + uuid.uuid4().hex)
        write_json(root / 'expected.json', {'reference': admitted['reference'], 'history_a': expected['analysis_a'],
            'history_b': expected['analysis_b'], 'source_ref': 'Shared', 'retained_name': a['retained_source_name']})
    finally:
        owner.close(); commands.clear_save_owner(owner)


def repair(root):
    from paraview import simple as p
    from apps.desktop_post import portable_project as post, commands, external, source_repair
    from caelab.native_project_inputs import NativeOnlyContext
    from caelab.portable_project_native import prepare_open, verify_opened
    from caelab.native_inputs import register_native_input
    expected = json.loads((root / 'expected.json').read_text(encoding='utf-8'))
    context = NativeOnlyContext(root / 'registration', approved_roots={})
    ticket = prepare_open(context, {'reference': expected['reference'], 'intent': 'saved', 'target_id': None,
        'expected_head': None, 'selection': None, 'allow_partial': False}, command_id='C' + uuid.uuid4().hex)
    opened, effects = tracked_open(lambda: post.restore_bound_project(ticket.verified_input, ticket.binding))
    verify_opened(context, ticket.binding.open_id, opened['readback'])
    owner = opened['owner']; owner.native_project_context = context; work = owner.workspace
    try:
        old = deepcopy(owner.project_document); source = old['sources'][expected['source_ref']]
        entry = Path(source['entry_path'])
        registered = register_native_input(context.root, entry.parent, entry, 'D' + uuid.uuid4().hex,
            root_id='current-verified-materialization', relative=entry.name, limit=1024 * 1024)
        receipt = {**registered, 'path': str(context.root / registered['file']),
            'source_pins': [{'path': str(context.root / item['file']), **{key: item[key] for key in ('bytes', 'sha256')}}
                            for item in registered['files']]}
        names = {source['reader_name'], expected['retained_name'], 'Shared auxiliary'}
        before = {name: list(map(str, external.reader_input_files(p.FindSource(name)))) for name in names}
        raw_cores = {obj['id']: [{key: row[key] for key in ('id', 'recipe', 'graph', 'bindings')} for row in obj['history']]
                     for obj in work.state['objects'].values()}
        real_verify = external.verify_readers
        def fail_after_actual_change(doc):
            real_verify(doc)
            assert all(str(receipt['path']) in list(map(str, external.reader_input_files(p.FindSource(name)))) for name in names)
            raise RuntimeError('CONTROLLED_POST_APPLY_VERIFICATION_FAILURE')
        external.verify_readers = fail_after_actual_change
        try:
            try: work.repair_source(source_ref=expected['source_ref'], input_id=receipt['id'], receipt=receipt)
            except RuntimeError as error: assert str(error) == 'CONTROLLED_POST_APPLY_VERIFICATION_FAILURE'
            else: raise AssertionError('Expected a verification failure after all native readers changed')
        finally:
            external.verify_readers = real_verify
        assert owner.project_document == old
        assert {name: list(map(str, external.reader_input_files(p.FindSource(name)))) for name in names} == before
        result = work.repair_source(source_ref=expected['source_ref'], input_id=receipt['id'], receipt=receipt)
        assert names <= set(result['affected_readers'])
        assert len(external.reader_input_files(p.FindSource('Shared auxiliary'))) == 2
        for ref in (expected['history_a'], expected['history_b']): work._bundle(work.object(ref))
        assert {obj['id']: [{key: row[key] for key in ('id', 'recipe', 'graph', 'bindings')} for row in obj['history']]
                for obj in work.state['objects'].values()} == raw_cores
        saved = post.save_current_project(owner, confirm_first_save=lambda: True)
        assert saved.is_file() and owner.native_target_head['generation'] == 1
        write_json(root / 'repair-readback.json', {'status': 'SHARED_READER_REPAIR_SAVED',
            'affected_readers': result['affected_readers'], 'affected_histories': result['affected_histories'],
            'all_slots_preserved': True, 'rollback_all_readers_and_document': True, 'history_cores_unchanged': True,
            'native_save_head_generation': 1, 'open_effects': effects})
    finally:
        owner.close(); commands.clear_save_owner(owner)


def run(root, original, pvpython):
    script = str(Path(__file__).resolve())
    subprocess.run([pvpython, script, 'setup', '--root', str(root), '--original', str(original)], cwd=REPO, check=True, timeout=120)
    held = original / 'original-repair-check-unavailable'
    (original / 'original').rename(held)
    try:
        subprocess.run([pvpython, script, 'repair', '--root', str(root)], cwd=REPO, check=True, timeout=120)
    finally:
        held.rename(original / 'original')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('phase', choices=['run', 'setup', 'repair'])
    parser.add_argument('--root', type=Path, required=True); parser.add_argument('--original', type=Path)
    parser.add_argument('--pvpython'); args = parser.parse_args(); args.root.mkdir(parents=True, exist_ok=True)
    if args.phase == 'run': run(args.root.resolve(), args.original.resolve(), args.pvpython)
    elif args.phase == 'setup': setup(args.root.resolve(), args.original.resolve())
    else: repair(args.root.resolve())
