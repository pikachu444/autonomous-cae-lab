"""Actual file registration and pure Post materialization; native checks separate."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import uuid
import xml.etree.ElementTree as ET

import pytest

from caelab.native_project_inputs import NativeOnlyContext, register_saved, verify_registered
from caelab.portable_project_native import prepare_open
from apps.desktop_post import portable_project
from test_native_post_dependencies import saved_project, write, state
from test_desktop_post_external import native
from test_desktop_post_bridge import bridge


def registered(root, project):
    context = NativeOnlyContext(root / 'workspace', approved_roots={'source': project.parent})
    receipt = register_saved(context, {'mode': 'selected_file', 'native_kind': 'post', 'root_id': 'source',
        'relative': project.name}, command_id='C' + uuid.uuid4().hex)
    return context, receipt['reference']


def ticket(context, reference, partial=False):
    return prepare_open(context, {'reference': reference, 'intent': 'saved', 'target_id': None,
        'expected_head': None, 'selection': None, 'allow_partial': partial}, command_id='C' + uuid.uuid4().hex)


def test_originals_unchanged_and_saved_paths_relocated_without_native_import(tmp_path):
    project, original = saved_project(tmp_path / 'source')
    original.update(service_url='http://old.invalid', desktop_python='old-python', repo_root='old-repo', origin_job_id='Jold')
    original['analysis']['objects']['Afilter']['history'][0].update(graph={'original': 'unchanged'}, bindings={'old': {'properties': {}, 'revision': 'unchanged'}})
    project.write_text(json.dumps(original), encoding='utf-8')
    before = {path: path.read_bytes() for path in project.parent.rglob('*') if path.is_file()}
    context, reference = registered(tmp_path, project)
    prepared = ticket(context, reference)
    derived = json.loads(Path(prepared.derived['project_path']).read_text(encoding='utf-8'))
    assert derived['title'] == Path(original['project_root']).name
    for key in ('service_url', 'desktop_python', 'repo_root', 'origin_job_id'): assert key not in derived
    assert derived['document_id'] != original['document_id']
    history = derived['analysis']['objects']['Afilter']['history'][0]
    assert history['graph'] == original['analysis']['objects']['Afilter']['history'][0]['graph']
    assert history['bindings'] == original['analysis']['objects']['Afilter']['history'][0]['bindings']
    assert history['retained_reader']['input_paths'] != [history['result_file']]
    assert all(path.read_bytes() == payload for path, payload in before.items())
    assert all(Path(path).is_relative_to(prepared.binding.working_root) for path in prepared.derived['member_paths'].values())
    # Same basename belongs to two exact namespaces, never a basename fallback.
    assert derived['sources']['A']['source_pins'][1]['path'] != derived['sources']['B']['entry_path']
    tree = ET.parse(Path(prepared.derived['project_path']).parent / derived['workspace_file'])
    assert all(value not in {str(path) for path in before} for value in
        [element.get('value') for prop in tree.getroot().iter('Property') if prop.get('name') == 'FileName' for element in prop.findall('Element')])


def test_registered_copy_opens_without_original_folder_and_detects_raw_tamper(tmp_path):
    project, _ = saved_project(tmp_path / 'source')
    context, reference = registered(tmp_path, project)
    moved = tmp_path / 'unavailable'
    project.parent.rename(moved)
    new_context = NativeOnlyContext(context.workspace, approved_roots={'copy': context.workspace})
    prepared = ticket(new_context, reference)
    assert Path(prepared.derived['project_path']).is_file()
    verified = verify_registered(new_context, reference)
    leaf = next(path for path in verified.member_paths.values() if path.suffix == '.vtu')
    leaf.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='CONTENT_CHANGED'):
        verify_registered(new_context, reference)


def test_converted_frd_original_is_packaged_and_relocated_with_the_result(tmp_path):
    project, document = saved_project(tmp_path / 'source')
    original_frd = write(project.parent / 'native' / 'user.frd', b'actual FRD bytes\x00\xff')
    from caelab.native_post_dependencies import file_pin
    document['sources']['A']['conversion'] = {
        'entry_path': document['sources']['A']['entry_path'], 'original_path': 'C:/user-model/calculation.frd',
        'retained_path': str(original_frd), 'source_pins': [file_pin(original_frd)],
        'summary': {'time_units': None}, 'execution_status': None}
    project.write_text(json.dumps(document), encoding='utf-8')
    context, reference = registered(tmp_path, project)
    project.parent.rename(tmp_path / 'original-unavailable')
    prepared = ticket(context, reference)
    derived = json.loads(Path(prepared.derived['project_path']).read_text(encoding='utf-8'))
    conversion = derived['sources']['A']['conversion']
    assert conversion['original_path'] == 'C:/user-model/calculation.frd'
    assert conversion['entry_path'] == derived['sources']['A']['entry_path']
    assert conversion['source_pins'][0]['path'] == conversion['retained_path']
    assert Path(conversion['retained_path']).is_relative_to(prepared.binding.working_root)
    assert Path(conversion['retained_path']).read_bytes() == b'actual FRD bytes\x00\xff'
    assert conversion['execution_status'] is None


def test_declared_partial_and_raw_pvsm_require_explicit_actions(tmp_path):
    project, document = saved_project(tmp_path / 'source')
    Path(document['sources']['B']['entry_path']).unlink()
    context, reference = registered(tmp_path, project)
    with pytest.raises(ValueError, match='declared missing'):
        ticket(context, reference)
    prepared = ticket(context, reference, partial=True)
    assert prepared.verified_input.snapshot['validation']['closure'] == 'DECLARED_PARTIAL'
    assert prepared.derived['status'] == 'PREPARED'
    raw = state(tmp_path / 'raw' / 'state.pvsm', [('Raw', 'XMLUnstructuredGridReader', [write(tmp_path / 'raw' / 'raw.vtu', b'raw')])])
    raw_context, raw_ref = registered(tmp_path / 'raw-registration', raw)
    admission = ticket(raw_context, raw_ref)
    assert admission.status == 'ADOPTION_REQUIRED' and admission.derived['status'] == 'MANAGED_SAVE_REQUIRED'
    with pytest.raises(ValueError, match='MANAGED_SAVE_REQUIRED'):
        portable_project.derive_project(admission.verified_input, admission.binding.working_root, binding=admission.binding)


def test_public_dict_cannot_install_owner_path_projection():
    with pytest.raises(ValueError, match='trusted open'):
        portable_project.validate_binding({'reference': {'kind': 'native_post'}})


def test_saved_imports_have_independent_live_identity_and_keep_source_bytes(tmp_path):
    project, document = saved_project(tmp_path / 'source')
    context, reference = registered(tmp_path, project)
    before = project.read_bytes()
    first, second = ticket(context, reference), ticket(context, reference)
    assert first.binding.owner_document_id != second.binding.owner_document_id
    assert document['document_id'] not in {first.binding.owner_document_id, second.binding.owner_document_id}
    assert first.binding.reference == second.binding.reference == reference
    assert first.binding.target_id is second.binding.target_id is None
    assert first.binding.materialization_root != second.binding.materialization_root
    assert project.read_bytes() == before


def test_partial_history_keeps_original_record_and_has_durable_asset_proof(tmp_path):
    from caelab.native_post_dependencies import post_project_files, history_asset_mapping
    project, document = saved_project(tmp_path / 'source')
    original = deepcopy(document['analysis']['objects']['Afilter']['history'][0])
    Path(original['result_file']).unlink()
    context, reference = registered(tmp_path, project)
    prepared = ticket(context, reference, partial=True)
    current = Path(prepared.derived['project_path'])
    derived = json.loads(current.read_text(encoding='utf-8'))
    assert derived['analysis']['objects']['Afilter']['history'][0] == original
    assert derived['native_history_availability']['histories'][0]['state'] == 'UNAVAILABLE_DECLARED'
    assets, proof = history_asset_mapping(derived, current)
    assert original['retained_reader']['files'][0]['path'] in assets
    assert original['result_file'] not in assets and proof['snapshot_sha256'] == prepared.verified_input.snapshot['snapshot_sha256']
    recollected = post_project_files(current, approved_roots=[prepared.binding.working_root], limits={})
    assert recollected['snapshot']['history_availability'][0]['record_sha256'] == portable_project.digest(original)
    assert recollected['snapshot']['validation']['closure'] == 'DECLARED_PARTIAL'
    next(iter(assets.values())).write_bytes(b'changed')
    with pytest.raises(ValueError, match='CONTENT_CHANGED'):
        history_asset_mapping(derived, current)


def test_registered_replacement_restores_exact_missing_pvd_occurrence(tmp_path):
    from caelab.native_post_dependencies import post_project_files
    from caelab.native_inputs import register_native_input
    project, document = saved_project(tmp_path / 'source')
    frame = Path(document['sources']['A']['source_pins'][1]['path'])
    replacement = write(tmp_path / 'replacement' / 'frame.vtu', frame.read_bytes())
    frame.unlink()
    inspection = post_project_files(project, approved_roots=[project.parent], limits={})
    missing = next(row for row in inspection['snapshot']['unavailable'] if row['locator']['codec'] == 'pvd_v1')
    context = NativeOnlyContext(tmp_path / 'workspace', approved_roots={'source': project.parent, 'replacement': replacement.parent})
    register_native_input(context.root, replacement.parent, replacement, 'DReplacement', root_id='replacement',
                          relative='frame.vtu', limit=1024 * 1024)
    declared = {**{key: missing[key] for key in ('parent_member', 'locator', 'expected_child')},
        'replacement_input_id': 'DReplacement', 'replacement_member': 'frame.vtu'}
    receipt = register_saved(context, {'mode': 'selected_file', 'native_kind': 'post', 'root_id': 'source', 'relative': project.name},
                             replacements=[declared], command_id='CExactReplacement')
    verified = verify_registered(context, receipt['reference'])
    assert verified.snapshot['validation']['closure'] == 'COMPLETE'
    assert not frame.exists()  # Registration never repaired the external original in place.
    assert any(row['original_location'] == str(frame) for row in verified.snapshot['logical_origins'])
    with pytest.raises(ValueError, match='original saved source evidence'):
        register_saved(context, {'mode': 'selected_file', 'native_kind': 'post', 'root_id': 'source', 'relative': project.name},
            replacements=[{**declared, 'expected_child': {**declared['expected_child'], 'relative': 'forged.vtu'}}], command_id='CForgedReplacement')


def test_existing_launcher_accepts_native_only_ticket_and_rejects_origins(tmp_path, monkeypatch):
    """Process creation is mocked; this asserts transport preparation, never OPENED."""
    from types import SimpleNamespace
    import sys
    from apps.research import desktop
    project, _ = saved_project(tmp_path / 'source')
    context, reference = registered(tmp_path, project)
    prepared = ticket(context, reference)
    captured = []
    monkeypatch.setattr(desktop, '_executable', lambda *args, **kwargs: Path(sys.executable))
    monkeypatch.setattr(desktop.subprocess, 'Popen', lambda command, **kwargs: captured.append((command, kwargs)) or SimpleNamespace(pid=12345))
    for key in ('CAE_POST_NATIVE_OPEN', 'CAE_POST_SERVICE_URL', 'CAE_POST_MEASUREMENT', 'CAE_POST_REPORT_ORIGIN', 'CAELAB_ORIGIN_JOB_ID'):
        monkeypatch.setenv(key, 'inherited-unrelated-context')
    local = {'repo_root': str(Path(desktop.__file__).resolve().parents[2]), 'python': sys.executable,
             'export_root': str(tmp_path / 'exports')}
    def arguments(**changes):
        return SimpleNamespace(**({'project': None, 'input_path': None, 'input_id': None, 'job_id': None,
            'research_source': None, 'measurement_result': None, 'curve_origin': None, 'report_image': None,
            'executable': None, 'output': None, 'prepare_only': False} | changes))
    response = desktop._post(None, arguments(), _native_project_ticket=prepared, _local_context=local)
    assert response['status'] == 'LAUNCHED' and response['project'] == prepared.derived['project_path']
    environment = captured[0][1]['env']
    assert environment['CAE_POST_NATIVE_OPEN'] == prepared.derived['launch_config']
    for key in ('CAE_POST_SERVICE_URL', 'CAE_POST_MEASUREMENT', 'CAE_POST_REPORT_ORIGIN', 'CAELAB_ORIGIN_JOB_ID'):
        assert key not in environment
    assert captured[0][0][2].endswith('apps\\desktop_post\\startup.py') or captured[0][0][2].endswith('apps/desktop_post/startup.py')
    with pytest.raises(ValueError, match='cannot share'):
        desktop._post(None, arguments(job_id='Jother'), _native_project_ticket=prepared, _local_context=local)
    with pytest.raises(ValueError, match='current local installation'):
        desktop._post(None, arguments(), _native_project_ticket=prepared, _local_context={**local, 'repo_root': str(tmp_path)})
    with pytest.raises(ValueError, match='verified native project'):
        desktop._post(None, arguments(), _local_context=local)
    assert len(captured) == 1


def test_native_only_entry_uses_existing_desktop_launcher(tmp_path, monkeypatch):
    from apps.research import desktop
    project, _ = saved_project(tmp_path / 'source')
    context, reference = registered(tmp_path, project)
    called = []
    monkeypatch.setattr(desktop, '_post', lambda client, arguments, **kwargs: called.append((client, arguments, kwargs)) or {'status': 'PREPARED'})
    result = portable_project.launch_prepared_project(context,
        {'reference': reference, 'intent': 'saved', 'target_id': None, 'expected_head': None, 'selection': None, 'allow_partial': False},
        command_id='C' + uuid.uuid4().hex, prepare_only=True)
    assert result['status'] == 'PREPARED' and called[0][0] is None
    assert called[0][2]['_native_project_ticket'].verified_input.full
    assert called[0][2]['_local_context']['repo_root'] == str(Path(portable_project.__file__).resolve().parents[2])


@pytest.mark.parametrize('failure', [None, 'reader', 'verification'])
def test_one_source_repair_updates_all_exact_reader_slots_atomically(native, tmp_path, monkeypatch, failure):
    import importlib
    from types import SimpleNamespace
    fake, commands, external = native
    repair = importlib.import_module('apps.desktop_post.source_repair')
    monkeypatch.setattr(repair, 'p', fake); monkeypatch.setattr(repair, 'external', external)
    old = write(tmp_path / 'old' / 'result.vtu', b'exact pinned bytes')
    new = write(tmp_path / 'registered' / 'result.vtu', old.read_bytes())
    unrelated = write(tmp_path / 'other' / 'result.vtu', b'other source')
    primary = fake.XMLUnstructuredGridReader(registrationName='Original', FileName=[str(old)])
    auxiliary = fake.XMLUnstructuredGridReader(registrationName='Auxiliary', FileName=[str(old), str(old)])
    sibling = fake.XMLUnstructuredGridReader(registrationName='Sibling', FileName=[str(unrelated)])
    for source in (primary, auxiliary, sibling): source.PointArrayStatus = ['q']
    source_record = {'reader_name': 'Original', 'reader_type': primary.GetXMLName(), 'entry_path': str(old),
                     'source_pins': external.pins([old])}
    readers = [{'reader_name': name, 'reader_type': source.GetXMLName(), 'input_paths': list(source.FileName)}
               for (name, _), source in fake.GetSources().items()]
    document = {'sources': {'Soriginal': source_record}, 'native_readers': readers,
                'native_reader_files': {str(old): external.sha(old), str(unrelated): external.sha(unrelated)},
                'analysis': {'version': 1, 'objects': {}}}
    original = deepcopy(document)
    owner = SimpleNamespace(project_document=document, workspace=None,
        native_properties=lambda source: ({'FileName': list(source.FileName), 'PointArrayStatus': list(source.PointArrayStatus)}, False))
    receipt = {'id': 'DReplacement', 'format': 'vtu', 'path': str(new), 'source_pins': external.pins([new])}
    actual_update = auxiliary.UpdatePipeline
    if failure == 'reader':
        auxiliary.UpdatePipeline = lambda: (_ for _ in ()).throw(RuntimeError('controlled reader failure')) if str(new) in auxiliary.FileName else actual_update()
    if failure == 'verification':
        monkeypatch.setattr(external, 'verify_readers', lambda doc: (_ for _ in ()).throw(RuntimeError('controlled verification failure')))
    if failure:
        with pytest.raises(RuntimeError, match='controlled'):
            repair.repair_source(owner, 'Soriginal', receipt['id'], receipt)
        assert document == original
        assert primary.FileName == [str(old)] and auxiliary.FileName == [str(old), str(old)]
    else:
        result = repair.repair_source(owner, 'Soriginal', receipt['id'], receipt)
        assert result['affected_readers'] == ['Auxiliary', 'Original']
        assert primary.FileName == [str(new)] and auxiliary.FileName == [str(new), str(new)]
        assert document['sources']['Soriginal']['entry_path'] == str(new)
    assert sibling.FileName == [str(unrelated)]
    assert primary.PointArrayStatus == auxiliary.PointArrayStatus == ['q']


@pytest.mark.parametrize('decision', [True, False])
def test_typed_partial_confirmation_uses_current_native_window_and_exact_missing_names(native, decision):
    import importlib
    from types import SimpleNamespace
    module = importlib.import_module('apps.desktop_post.bridge')
    dispatcher = object.__new__(module.GuiDispatch)
    dispatcher.owner = SimpleNamespace(assert_thread=lambda: None,
        workspace=SimpleNamespace(object=lambda ref: {'title': '보존한 변형'}))
    displayed = []
    def confirm(main, text):
        assert controls.in_action and main == 123
        displayed.append(text)
        return decision
    controls = SimpleNamespace(closed=False, in_action=False, main=123,
        platform=SimpleNamespace(confirm_save=confirm))
    dispatcher.native_controls = controls
    rows = [{'history': {'object_ref': 'Aexact'}, 'missing': [{'expected_child': {'relative': 'old/private/path/result.vtu'}}]}]
    assert dispatcher._confirm_partial_history_save(rows) is decision
    assert '보존한 변형: result.vtu' in displayed[0]
    assert 'old/private' not in displayed[0] and not controls.in_action


def test_native_property_observer_keeps_cas_during_transient_array_domain(native, monkeypatch):
    import importlib
    import threading
    module = importlib.import_module('apps.desktop_post.bridge')
    owner = object.__new__(module.Owner)
    owner.thread = threading.get_ident(); owner.closed = False; owner.modified_events = 0
    owner.generation = 7; owner._content = {}
    monkeypatch.setattr(module, 'proxy_id', lambda source: 'Sexact')
    monkeypatch.setattr(module, 'properties', lambda source: (_ for _ in ()).throw(ValueError('native domain is half written')))
    owner._modified(None)
    assert owner.modified_events == 1 and owner.generation == 8
    with pytest.raises(ValueError, match='half written'):
        module.properties(None)  # Normal strict property reads were not weakened.


@pytest.mark.parametrize('intent,head_generation,local_saved', [('saved', None, False), ('working', 0, False), ('working', 1, True)])
def test_portable_owner_local_save_markers_follow_verified_head_state(bridge, monkeypatch, intent, head_generation, local_saved):
    """Owner-state unit after the independently tested sealed-binding boundary."""
    from types import SimpleNamespace
    monkeypatch.setattr(portable_project, 'validate_binding', lambda value: value)
    bridge.doc.update(document_id='Dlocal', workspace_sha256='derived-path-only-hash', generation=4, view_generation=2)
    source_id = 'Dlocal' if local_saved else 'Dsource'
    reference = {'kind': 'native_post', 'document_id': source_id, 'saved_revision': 'Rsource'}
    binding = SimpleNamespace(intent=intent, target_id='Klocal' if intent == 'working' else None,
        open_id='Olocal', materialization_root=Path(bridge.doc['project_root'])/'working', reference=reference,
        expected_head=None if intent == 'saved' else {'generation': head_generation},
        verified_input=SimpleNamespace(snapshot={'source_document_id': source_id, 'native_revision': 'actual-native-save-hash'}))
    owner = bridge.module.Owner(_portable_binding=binding)
    assert owner.saved_revision == ('actual-native-save-hash' if local_saved else None)
    assert owner.saved_generation == (4 if local_saved else None)
    assert owner.saved_view_generation == (2 if local_saved else None)
    assert owner.descriptor()['dirty'] is not local_saved
    assert owner.source_reference == reference and owner.source_native_revision == 'actual-native-save-hash'


def test_successful_basis_publication_retires_new_history_projection_bypass(bridge, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from caelab.native_post_dependencies import history_key, digest, _verified_history_slots
    owner = bridge.module.Owner()
    graph = {'nodes': [{'label': 'R', 'type': 'XMLUnstructuredGridReader', 'properties': {'FileName': ['old.vtu'], 'ScaleFactor': .1}}], 'output_label': 'R'}
    graph['sha256'] = digest(graph)
    record = {'id': 'Vnew', 'recipe': {'source_ref': 'A'}, 'graph': graph,
              'bindings': {'A': {'revision': 'same-revision', 'properties': {'FileName': ['old.vtu']}, 'metadata': None}}}
    obj = {'id': 'B', 'kind': 'filter', 'history': [record]}
    key = history_key('B', record)
    basis = {'version': 1, 'history': key, 'bindings_sha256': digest(record['bindings']),
             'graph_sha256': digest(graph), 'retained_graph_sha256': None, 'slots': []}
    work = SimpleNamespace(owner=owner, document=owner.project_document, _new_history_keys={tuple(key.values())},
        prepare_for_save=lambda: False, describe=lambda: {}, prepare_save=lambda document, folder, **kwargs: document)
    owner.workspace = work
    monkeypatch.setattr(owner, "operations", lambda: bridge.module.OPERATIONS)
    def completed_native_save(path, document, **kwargs):
        output = tmp_path/'basis-save.json'
        output.write_text(json.dumps({**document, 'workspace_sha256': 'saved-native',
            'native_relocation_basis': {'version': 1, 'histories': [basis]}}), encoding='utf-8')
        return output
    monkeypatch.setattr(bridge.external, 'save_project', completed_native_save)
    owner.save_project()
    assert not portable_project._is_new_history(work, obj, record)
    owner.portable_binding = object()  # Isolate the lifetime check from native admission.
    work._refs = lambda kind, recipe: ['A']
    work._retained_dependencies = lambda saved, refs: {}
    actual = deepcopy(record['bindings']); actual['A']['properties']['FileName'] = ['same-bytes-new-location.vtu']
    work.source_stamps = lambda refs, revisions: deepcopy(actual)
    base_slot = {'reader_key': {'registration_name': 'R'}, 'reader_type': 'XMLUnstructuredGridReader',
        'file_property': 'FileName', 'value_shape': 'list', 'slot_count': 1, 'element_index': 0,
        'basis_value': 'old.vtu', 'current_value': 'same-bytes-new-location.vtu'}
    slots = [{**base_slot, 'site': 'binding', 'binding_ref': 'A', 'upstream': {'revision_sha256': 'same-revision'}},
             {**base_slot, 'site': 'graph'}]
    checked = []
    def current_native_proof(*args, **kwargs):
        checked.append(True)
        return _verified_history_slots(basis, slots, ('Sowner', 1, 1))
    monkeypatch.setattr(portable_project, 'verified_history_slots', current_native_proof)
    assert portable_project.compare_history_inputs(work, obj, record, mode='retained')['state'] == 'SAME'
    assert checked  # Saving B1 can no longer skip the path projection verifier.
    from caelab.native_post_dependencies import graph_on_source_basis
    def projected(graph_value):
        return graph_on_source_basis(graph_value, expected_graph=graph, history_basis=basis, verified_slots=current_native_proof())
    moved_graph = deepcopy(graph); moved_graph['nodes'][0]['properties']['FileName'] = ['same-bytes-new-location.vtu']
    assert projected(moved_graph) == graph
    moved_graph['nodes'][0]['properties']['ScaleFactor'] = .2
    assert projected(moved_graph) != graph


def _controlled_post_reservation(bridge, monkeypatch):
    """Current-owner native Save boundary; N0 seal/receipt checks have separate tests."""
    from types import SimpleNamespace
    import caelab.native_project_contract as contract
    import caelab.native_project_inputs as inputs
    owner = bridge.module.Owner()
    binding = SimpleNamespace(intent='working', target_id='Klocal', open_id='Olocal', reference={'kind': 'native_post'})
    owner.portable_binding = binding; owner.native_target_id = 'Klocal'; owner.native_project_context = object()
    target = SimpleNamespace(open_id=binding.open_id, owner_document_id=owner.document_id, source_reference=binding.reference,
        expected_stamp=portable_project._stamp(owner), native_save_root=owner.project_root/'saved', save_command_id='Csave')
    monkeypatch.setattr(contract, 'require_target_save', lambda value: value)
    failures = []
    monkeypatch.setattr(inputs, '_record_target_save_failure', lambda context, reservation, error, stage='native_save': failures.append(stage))
    def resume(context, identifier):
        if identifier != 'Cprepare': raise ValueError('forged preparation')
        return target
    monkeypatch.setattr(inputs, 'resume_target_save', resume)
    return owner, target, failures


@pytest.mark.parametrize('failure,expected', [('validation', ['before_save']), ('native', ['native_save']), ('published', []), ('returned', [])])
def test_save_failure_phase_closes_only_definite_current_reservation(bridge, monkeypatch, tmp_path, failure, expected):
    owner, target, failures = _controlled_post_reservation(bridge, monkeypatch)
    calls = []
    def native_save(path, document, **kwargs):
        calls.append(True)
        if failure == 'published':
            owner._native_save_attempt.update(phase='PUBLISHED', saved_file=str(tmp_path/'completed-native.json'))
            raise RuntimeError('notification failed after native publication')
        if failure == 'returned':
            output = tmp_path/'completed-native.json'; output.write_text('unreadable after return', encoding='utf-8')
            return output
        raise RuntimeError('definite native save failure')
    monkeypatch.setattr(bridge.external, 'save_project', native_save)
    if failure == 'validation': bridge.doc['document_id'] = 'Dforeign'
    with pytest.raises((ValueError, RuntimeError)):
        owner.save_project(_target_save=target)
    assert failures == expected
    assert len(calls) == (0 if failure == 'validation' else 1)
    if failure == 'published': assert owner._native_save_attempt['phase'] == 'PUBLISHED'
    if failure == 'returned': assert owner._native_save_attempt['phase'] == 'RETURNED'


@pytest.mark.parametrize('failure,closed', [('cas', True), ('busy', True), ('wrong_session', False), ('forged_wire', False), ('completed', False)])
def test_dispatch_pre_save_rejection_reconciles_only_authenticated_no_effect_reservation(bridge, monkeypatch, failure, closed):
    owner, target, failures = _controlled_post_reservation(bridge, monkeypatch)
    request = {'command_id': 'Csave', 'operation': 'document.save', 'document_id': owner.document_id,
        'session_id': owner.session_id, 'expected_generation': owner.generation + 1, 'arguments': {}, 'target': {},
        '_target_save': {'prepare_command_id': 'Cprepare', 'save_command_id': 'Csave', 'open_id': 'Olocal'}}
    if failure == 'busy':
        request['expected_generation'] = owner.generation
        bridge.source.props['PointArrays'].unchecked = ['unapplied']
    if failure == 'wrong_session': request['session_id'] = 'Sforeign'
    if failure == 'forged_wire': request['_target_save']['prepare_command_id'] = 'Cforged'
    if failure == 'completed': owner.native_completed_saves['Csave'] = object()
    result = owner.dispatch(request)
    assert result['status'] == 'FAILED'
    assert failures == (['before_save'] if closed else [])
    assert not bridge.saved  # This entire path has no native Save effect.


@pytest.mark.parametrize('failure', ['cas', 'native'])
def test_definite_failure_releases_real_journal_reservation_and_reuses_first_target(bridge, monkeypatch, tmp_path, failure):
    """Real sealed N0/journal boundaries; native file writer is controlled."""
    from caelab.native_project_inputs import prepare_target_save
    from caelab.portable_project_native import verify_opened, _native_open_readback
    source, _ = saved_project(tmp_path/'source')
    context, reference = registered(tmp_path/'registration', source)
    opened = ticket(context, reference)
    bridge.doc.update(document_id=opened.binding.owner_document_id, project_root=str(opened.binding.materialization_root))
    owner = bridge.module.Owner(_portable_binding=opened.binding)
    owner.native_project_context = context
    verify_opened(context, opened.binding.open_id, _native_open_readback({
        'open_id': opened.binding.open_id, 'reference': reference, 'target_id': None,
        'working_document_id': owner.document_id, 'context_session': opened.binding.context_session,
        'status': 'OPENED', 'native_owner_session': owner.session_id, 'native_kind': 'post'}))
    first = prepare_target_save(context, opened.binding.open_id, expected_stamp=portable_project._stamp(owner),
        expected_head=None, command_id='CFirstPrepare')
    attempts = []
    def native_failure(*args, **kwargs):
        attempts.append('failed')
        raise RuntimeError('definite synchronous writer failure')
    monkeypatch.setattr(bridge.external, 'save_project', native_failure)
    if failure == 'native':
        with pytest.raises(RuntimeError, match='synchronous'):
            portable_project.complete_save(owner, expected_stamp=first.expected_stamp, _target_save=first)
    else:
        result = owner.dispatch({'command_id': first.save_command_id, 'operation': 'document.save',
            'document_id': owner.document_id, 'session_id': owner.session_id, 'expected_generation': owner.generation+1,
            'arguments': {}, 'target': {}, '_target_save': {'prepare_command_id': 'CFirstPrepare',
                'save_command_id': first.save_command_id, 'open_id': opened.binding.open_id}})
        assert result['status'] == 'FAILED'
    journal = context.root/'native_project'/'target_saves'/'CFirstPrepare.json'
    assert json.loads(journal.read_text(encoding='utf-8'))['state'] == 'FAILED_CONFIRMED'
    second = prepare_target_save(context, opened.binding.open_id, expected_stamp=portable_project._stamp(owner),
        expected_head=None, command_id='CSecondPrepare')
    assert second.target_id == first.target_id and second.save_command_id != first.save_command_id
    def native_success(path, document, **kwargs):
        attempts.append('succeeded')
        output = second.native_save_root/'unit-saved.json'; output.parent.mkdir(parents=True)
        output.write_text(json.dumps({**document, 'workspace_sha256': 'controlled-native-saved'}), encoding='utf-8')
        return output
    monkeypatch.setattr(bridge.external, 'save_project', native_success)
    witness = portable_project.complete_save(owner, expected_stamp=second.expected_stamp, _target_save=second)
    assert witness.saved_file.is_file() and owner.native_target_id == first.target_id and not owner.descriptor()['dirty']
    assert attempts == (['failed', 'succeeded'] if failure == 'native' else ['succeeded'])


@pytest.mark.parametrize('prior', ['witness', 'returned'])
def test_repeated_stale_save_validation_never_releases_completed_or_unknown_reservation(bridge, monkeypatch, prior):
    owner, target, failures = _controlled_post_reservation(bridge, monkeypatch)
    if prior == 'witness': owner.native_completed_saves[target.save_command_id] = object()
    else: owner._native_save_attempt = {'command_id': target.save_command_id, 'phase': 'RETURNED'}
    owner.saved_revision = 'completed-before-retry'
    with pytest.raises(ValueError, match='STALE_DOCUMENT'):
        portable_project.complete_save(owner, expected_stamp=target.expected_stamp, _target_save=target)
    assert failures == [] and not bridge.saved


def test_partial_native_state_preserves_global_timekeeper_and_animation_cue(native, tmp_path):
    import importlib
    repair = importlib.import_module('apps.desktop_post.source_repair')
    a = write(tmp_path/'a.vtu', b'healthy'); b = tmp_path/'b.vtu'
    original = state(tmp_path/'original.pvsm', [('A','XMLUnstructuredGridReader',[a]),('B','XMLUnstructuredGridReader',[b])])
    tree = ET.parse(original); server = tree.getroot().find('ServerManagerState')
    keeper = ET.SubElement(server, 'Proxy', group='misc', type='TimeKeeper', id='30')
    prop = ET.SubElement(keeper,'Property',name='TimeSources',number_of_elements='2')
    for value in ('1','2'): ET.SubElement(prop,'Proxy',value=value)
    scene = ET.SubElement(server,'Proxy',group='animation',type='AnimationScene',id='31')
    for name,value in [('TimeKeeper','30'),('Cues','32')]:
        ET.SubElement(ET.SubElement(scene,'Property',name=name,number_of_elements='1'),'Proxy',value=value)
    cue = ET.SubElement(server,'Proxy',group='animation',type='TimeAnimationCue',id='32')
    ET.SubElement(ET.SubElement(cue,'Property',name='AnimatedProxy',number_of_elements='1'),'Proxy',value='30')
    for group,rows in [('timekeeper',[('30','TimeKeeper1')]),('animation',[('31','AnimationScene1'),('32','TimeAnimationCue1')])]:
        collection=ET.SubElement(server,'ProxyCollection',name=group)
        for identifier,name in rows: ET.SubElement(collection,'Item',id=identifier,name=name)
    tree.write(original,encoding='utf-8',xml_declaration=True)
    before=original.read_bytes()
    output=tmp_path/'available.pvsm'
    document={'sources':{'A':{'reader_name':'A'},'B':{'reader_name':'B'}},'analysis':{'objects':{}}}
    result=repair.partial_state(original,document,[{'source_ref':'B','reader_name':'B'}],output,retain_applied=True)
    server=ET.parse(output).getroot().find('ServerManagerState')
    assert server.find("Proxy[@id='30']") is not None
    assert server.find("Proxy[@id='32']") is not None
    assert [row.get('value') for row in server.findall("Proxy[@id='30']/Property[@name='TimeSources']/Proxy")] == ['1']
    assert server.find("Proxy[@id='31']/Property[@name='TimeKeeper']/Proxy").get('value')=='30'
    assert result['removed_source_names']==['B'] and original.read_bytes()==before


def _native_timing_state(path, *, link=None):
    root=ET.Element('ParaView');server=ET.SubElement(root,'ServerManagerState')
    keeper=ET.SubElement(server,'Proxy',id='30',group='misc',type='TimeKeeper')
    ET.SubElement(ET.SubElement(keeper,'Property',name='Time'), 'Element',index='0',value='1.25')
    scene=ET.SubElement(server,'Proxy',id='31',group='animation',type='AnimationScene')
    prop=ET.SubElement(scene,'Property',name='TimeKeeper',id='31.TimeKeeper')
    if link is not None:
        prop.set('number_of_elements','1');ET.SubElement(prop,'Proxy',value=link)
    ET.SubElement(ET.SubElement(scene,'Property',name='AnimationTime'), 'Element',index='0',value='1.25')
    ET.SubElement(scene,'Property',name='Cues')
    ET.SubElement(scene,'Property',name='ViewModules')
    for group,identifier,name in [('timekeeper','30','TimeKeeper1'),('animation','31','AnimationScene1')]:
        ET.SubElement(ET.SubElement(server,'ProxyCollection',name=group),'Item',id=identifier,name=name)
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
    return root


def test_gui_timekeeper_compatibility_changes_only_transient_empty_link(tmp_path):
    from caelab.native_post_dependencies import file_pin
    source=tmp_path/'path-only.pvsm';original=_native_timing_state(source);before=source.read_bytes()
    output,record=portable_project._gui_timekeeper_state(source,tmp_path/'gui-load.pvsm')
    assert source.read_bytes()==before and output!=source
    assert record['source']==file_pin(source) and record['loaded']==file_pin(output)
    assert record['edits']==[{'proxy_id':'31','property':'TimeKeeper','old_proxy_ids':[],'new_proxy_ids':['30']}]
    loaded=ET.parse(output).getroot()
    prop=loaded.find("ServerManagerState/Proxy[@id='31']/Property[@name='TimeKeeper']")
    assert prop.find('Proxy').get('value')=='30'
    prop.remove(prop.find('Proxy'));prop.attrib.pop('number_of_elements')
    assert ET.tostring(loaded)==ET.tostring(original)  # Cues/views/time and all other fields are unchanged.


def test_gui_timekeeper_valid_state_remains_byte_identical(tmp_path):
    source=tmp_path/'normal.pvsm';_native_timing_state(source,link='30');before=source.read_bytes()
    destination=tmp_path/'unused.pvsm'
    actual,record=portable_project._gui_timekeeper_state(source,destination)
    assert actual==source and record['edits']==[]
    assert source.read_bytes()==before and not destination.exists()


@pytest.mark.parametrize('fault',['wrong_target','ambiguous','missing_declaration'])
def test_gui_timekeeper_compatibility_rejects_unknown_native_target(tmp_path,fault):
    source=tmp_path/'invalid.pvsm';root=_native_timing_state(source,link='999' if fault=='wrong_target' else None)
    server=root.find('ServerManagerState')
    if fault=='ambiguous': ET.SubElement(server.find("ProxyCollection[@name='timekeeper']"),'Item',id='30',name='OtherKeeper')
    if fault=='missing_declaration': server.remove(server.find("ProxyCollection[@name='timekeeper']"))
    ET.ElementTree(root).write(source,encoding='utf-8',xml_declaration=True);before=source.read_bytes()
    with pytest.raises(ValueError,match='NATIVE_TIMEKEEPER_UNBOUND'):
        portable_project._gui_timekeeper_state(source,tmp_path/'rejected.pvsm')
    assert source.read_bytes()==before and not (tmp_path/'rejected.pvsm').exists()


def test_gui_legacy_timekeeper_is_loaded_before_animation_without_other_changes(tmp_path):
    source=tmp_path/'legacy.pvsm';original=_native_timing_state(source)
    server=original.find('ServerManagerState')
    keeper=server.find("ProxyCollection[@name='timekeeper']");server.remove(keeper);server.append(keeper)
    ET.ElementTree(original).write(source,encoding='utf-8',xml_declaration=True);before=source.read_bytes()
    output,record=portable_project._gui_timekeeper_state(source,tmp_path/'transient.pvsm')
    assert record['collection_order']=={'before':['animation','timekeeper'],'after':['timekeeper','animation']}
    actual=ET.parse(output).getroot();server=actual.find('ServerManagerState')
    prop=server.find("Proxy[@id='31']/Property[@name='TimeKeeper']");prop.remove(prop.find('Proxy'));prop.attrib.pop('number_of_elements')
    keeper=server.find("ProxyCollection[@name='timekeeper']");server.remove(keeper);server.append(keeper)
    assert ET.tostring(actual)==ET.tostring(original) and source.read_bytes()==before


def test_gui_bound_timekeeper_animation_first_changes_only_collection_order(tmp_path):
    source=tmp_path/'saved.pvsm';original=_native_timing_state(source,link='30')
    server=original.find('ServerManagerState')
    keeper=server.find("ProxyCollection[@name='timekeeper']");server.remove(keeper);server.append(keeper)
    ET.ElementTree(original).write(source,encoding='utf-8',xml_declaration=True);before=source.read_bytes()
    output,record=portable_project._gui_timekeeper_state(source,tmp_path/'transient.pvsm')
    assert record['edits']==[] and output!=source
    assert record['collection_order']=={'before':['animation','timekeeper'],'after':['timekeeper','animation']}
    actual=ET.parse(output).getroot();server=actual.find('ServerManagerState')
    keeper=server.find("ProxyCollection[@name='timekeeper']");server.remove(keeper);server.append(keeper)
    assert ET.tostring(actual)==ET.tostring(original) and source.read_bytes()==before


@pytest.mark.parametrize('fault',['duplicate_keeper','duplicate_animation'])
def test_gui_bound_timekeeper_rejects_ambiguous_singleton(tmp_path,fault):
    source=tmp_path/'ambiguous.pvsm';original=_native_timing_state(source,link='30')
    server=original.find('ServerManagerState')
    if fault=='duplicate_keeper': ET.SubElement(server,'Proxy',id='40',group='misc',type='TimeKeeper')
    else: ET.SubElement(server,'ProxyCollection',name='animation')
    ET.ElementTree(original).write(source,encoding='utf-8',xml_declaration=True);before=source.read_bytes()
    with pytest.raises(ValueError,match='NATIVE_TIMEKEEPER_UNBOUND'):
        portable_project._gui_timekeeper_state(source,tmp_path/'transient.pvsm')
    assert source.read_bytes()==before and not (tmp_path/'transient.pvsm').exists()
