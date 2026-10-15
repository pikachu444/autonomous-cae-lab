"""Explicit missing-history preservation through the existing native Save path."""
from copy import deepcopy
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from native_roundtrip import create, tracked_open, write_json, REPO


def setup(root):
    from paraview import simple as p
    from apps.desktop_post import bridge, commands
    from caelab.native_project_inputs import NativeOnlyContext, register_saved
    create(root)
    expected = json.loads((root / 'expected.json').read_text(encoding='utf-8'))
    owner = bridge.Owner(); commands.set_save_owner(owner)
    ref = expected['analysis_b']; record = owner.workspace.applied(owner.workspace.object(ref))
    for proxy in reversed(owner.workspace.bundles[record['id']]['proxies']): p.Delete(proxy)
    owner.close(); commands.clear_save_owner(owner)
    owner = bridge.Owner(); commands.set_save_owner(owner)
    project = owner.save_project()
    record = deepcopy(json.loads(project.read_text(encoding='utf-8'))['analysis']['objects'][ref]['history'][0])
    assert record['retained_reader']['input_paths'] != [record['result_file']]
    missing = Path(record['result_file']); assert missing.is_relative_to(root / 'original')
    missing.unlink()
    context = NativeOnlyContext(root / 'partial-registration', approved_roots={'source': root / 'original'})
    receipt = register_saved(context, {'mode': 'selected_file', 'native_kind': 'post', 'root_id': 'source',
        'relative': project.relative_to(root / 'original').as_posix()}, command_id='C' + uuid.uuid4().hex)
    write_json(root / 'partial-expected.json', {'reference': receipt['reference'], 'object_ref': ref, 'history': record,
        'healthy': expected['analysis_a']})
    owner.close(); commands.clear_save_owner(owner)


def cold(root, save, typed=False):
    from apps.desktop_post import portable_project as post, commands
    from caelab.native_project_inputs import NativeOnlyContext
    from caelab.portable_project_native import prepare_open, verify_opened
    from caelab import portable_project as portable
    expected = json.loads((root / 'partial-expected.json').read_text(encoding='utf-8'))
    workspace = root / ('partial-registration' if save else 'partial-copy')
    context = NativeOnlyContext(workspace, approved_roots={}) if save else portable.open_project(workspace)
    reference = expected['reference'] if save else portable.verify_project(workspace)['native_inputs'][0]['reference']
    ticket = prepare_open(context, {'reference': reference, 'intent': 'saved', 'target_id': None,
        'expected_head': None, 'selection': None, 'allow_partial': True}, command_id='C' + uuid.uuid4().hex)
    opened, effects = tracked_open(lambda: post.restore_bound_project(ticket.verified_input, ticket.binding, allow_partial=True))
    verify_opened(context, ticket.binding.open_id, opened['readback'])
    owner = opened['owner']; owner.native_project_context = context; work = owner.workspace
    try:
        assert opened['status'] == 'PARTIAL_OPEN'
        obj = work.object(expected['object_ref']); assert obj['history'][0] == expected['history']
        assert expected['history']['id'] not in work.bundles
        work._bundle(work.object(expected['healthy']))
        if save:
            try: post.prepare_history_save(owner, expected_stamp=post.saved_offer(owner)['stamp'])
            except ValueError as error: assert str(error).startswith('MISSING_HISTORY_DEPENDENCY')
            else: raise AssertionError('Partial history preservation was not confirmed')
            if typed:
                from caelab.native_project_inputs import prepare_target_save, publish_head
                calls = {'native_save': 0, 'confirmation': 0}
                actual_save = owner.save_project
                def counted_save(**kwargs):
                    calls['native_save'] += 1
                    return actual_save(**kwargs)
                owner.save_project = counted_save
                def execute():
                    stamp = post.saved_offer(owner)['stamp']
                    prepare_command = 'C' + uuid.uuid4().hex
                    reservation = prepare_target_save(context, ticket.binding.open_id, expected_stamp=stamp,
                        expected_head=None, command_id=prepare_command)
                    result = owner.dispatch({'command_id': reservation.save_command_id, 'document_id': owner.document_id,
                        'session_id': owner.session_id, 'expected_generation': owner.generation,
                        'operation': 'document.save', 'arguments': {}, 'target': {}, '_target_save': {
                            'prepare_command_id': prepare_command, 'save_command_id': reservation.save_command_id,
                            'open_id': ticket.binding.open_id}})
                    return result, reservation
                declined, _ = execute()
                assert declined['status'] == 'FAILED' and 'HISTORY_CONFIRMATION_REQUIRED' in declined['error']['message'], declined
                owner._confirm_partial_history_save = lambda rows: False
                cancelled, _ = execute()
                assert cancelled['status'] == 'FAILED' and 'USER_CANCELLED' in cancelled['error']['message'], cancelled
                assert calls['native_save'] == 0
                def confirm(rows):
                    calls['confirmation'] += 1
                    assert rows[0]['history']['revision_id'] == expected['history']['id']
                    return True  # Controlled native GUI-decision seam; OS clicking is not claimed.
                owner._confirm_partial_history_save = confirm
                completed, reservation = execute()
                assert completed['status'] == 'COMPLETED', completed
                assert calls == {'native_save': 1, 'confirmation': 1}, calls
                witness = owner.native_completed_saves[reservation.save_command_id]
                published = publish_head(context, reservation.target_id, witness, expected_head=None,
                    command_id='C' + uuid.uuid4().hex, _target_save=reservation)
                owner.native_target_head = {'generation': 1, 'reference': published['reference']}
                saved = Path(completed['result']['project'])
                write_json(root / 'partial-typed-save-readback.json', {'status': 'TYPED_PARTIAL_SAVE_CONFIRMED',
                    'no_gui_and_cancel_save_calls': 0, 'confirmed_native_save_calls': calls['native_save'],
                    'confirmation_calls': calls['confirmation'], 'public_arguments': {}, 'private_wire_fields': 3,
                    'consent_evidence': 'controlled current-native-owner callback; OS GUI clicking NOT_RUN'})
            else:
                saved = post.save_current_project(owner, confirm_first_save=lambda: True, confirm_partial=lambda rows: True)
            document = json.loads(saved.read_text(encoding='utf-8'))
            assert document['analysis']['objects'][obj['id']]['history'][0] == expected['history']
            inspection = portable.inspect_copy(context, [{'native': owner.native_target_head['reference'],
                'copy_intent': 'preserve_declared_partial', 'working_target': False}])
            portable.create_copy(context, inspection, root / ('partial-copy-typed' if typed else 'partial-copy'), approved=True,
                command_id='C' + uuid.uuid4().hex, session_id=context.session_id)
        write_json(root / ('partial-save-readback.json' if save else 'partial-cold-readback.json'),
            {'status': 'UNAVAILABLE_HISTORY_PRESERVED', 'record_unchanged': True, 'fake_reader_created': False,
             'healthy_history_verified': True, 'open_effects': effects})
    finally:
        owner.close(); commands.clear_save_owner(owner)


def run(root, pvpython):
    script = str(Path(__file__).resolve())
    def invoke(phase): subprocess.run([pvpython, script, phase, '--root', str(root)], cwd=REPO, check=True, timeout=120)
    if not (root / 'partial-expected.json').is_file():
        invoke('setup')
    held = []
    try:
        (root / 'original').rename(root / 'original-unavailable'); held.append('original')
        invoke('save')
        (root / 'partial-registration').rename(root / 'partial-registration-unavailable'); held.append('partial-registration')
        invoke('cold')
    finally:
        for name in reversed(held):
            (root / (name + '-unavailable')).rename(root / name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('phase', choices=['run', 'setup', 'save', 'cold', 'typed-save'])
    parser.add_argument('--root', type=Path, required=True); parser.add_argument('--pvpython')
    arguments = parser.parse_args(); root = arguments.root.resolve(); root.mkdir(parents=True, exist_ok=True)
    if arguments.phase == 'run': run(root, arguments.pvpython)
    elif arguments.phase == 'setup': setup(root)
    else: cold(root, arguments.phase in ('save', 'typed-save'), typed=arguments.phase == 'typed-save')
