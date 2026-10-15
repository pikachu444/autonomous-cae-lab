"""C1 actual files/owners/CAS; no GUI/native/physics success implied by these tests."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from caelab.connection_graph import SnapshotReader, build_graph
from caelab.connection_graph_edit import (target_selection, source_selection, preview_edit, apply_edit,
                                         catalog, read_impact)
from caelab.connection_graph_view import (RELATIVE, read_view, save_view, merge_bindings,
    store_scope, validate_state)
from caelab.evaluation import file_hash
from caelab.portable_project import inspect_copy, create_copy, open_project, verify_project, MANIFEST, _asset_name
from caelab.portable_project_drafts import WORKING, snapshot_bytes
from caelab.portable_project_io import PortableProjectError, extract_archive
from caelab.storage import canonical_hash, load_json, save_json
from caelab.workbench import Workbench
from examples.portable_connection_public import create_public_store, command, save
from examples.portable_connection_c1_public import dirty_fixture


@pytest.fixture
def original(tmp_path):
    wb, docs = create_public_store(tmp_path / '원본 자료')
    try: yield wb, docs
    finally: wb.shutdown()


def tree(folder):
    # Windows byte-range lock is the ONE runtime exception. Every other byte is hashed.
    runtime_lock = folder / 'workbench/controller.lock'
    return {p.relative_to(folder).as_posix():
            (('runtime-lock', p.stat().st_size, p.stat().st_mtime_ns) if p == runtime_lock else file_hash(p))
            for p in folder.rglob('*') if p.is_file()}


def domain_tree(wb):
    return tree(wb.root / 'documents')


def selected(docs):
    return [docs[k]['id'] for k in ('data', 'material', 'plan', 'second_plan')]


def copy(wb, docs, destination, policy='acknowledged', command_id='Cc1copy'):
    plan = inspect_copy(wb, selected(docs), draft_policy=policy)
    assert plan['status'] == 'READY', plan
    return create_copy(wb, plan, destination, approved=True, command_id=command_id, session_id=wb.session_id)


def edit(wb, target, port, action, source=None, command_id='Cc1edit'):
    proposal = preview_edit(wb, target_selection(wb, target), port, action, source)
    return proposal, apply_edit(wb, proposal, confirmed=True, command_id=command_id)


def test_cold_deleted_source_undo_units_failure_layout_in_new_process(tmp_path):
    run = subprocess.run([sys.executable, '-m', 'examples.portable_connection_c1_public',
        '--output', str(tmp_path / '공개 자료')], capture_output=True, text=True, encoding='utf-8', timeout=90)
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result['original_store_deleted'] and result['separate_process']
    assert result['owner_edit_undo_save'] and result['history_generation_preserved']
    assert result['verification_after_edit'] == 'READY' and result['jobs_on_reopen'] == 0
    assert result['states'] == ['FAILED', 'FAILED', 'SUCCEEDED', 'SUCCEEDED']


def test_ack_snapshot_history_original_bytes_missing_new_source_and_saved_only(tmp_path):
    wb, docs = dirty_fixture(tmp_path / '새 원자료')
    try:
        before = tree(wb.workspace)
        plan = inspect_copy(wb, selected(docs))
        assert plan['status'] == 'READY' and plan['draft_policy'] == 'acknowledged'
        assert tree(wb.workspace) == before
        target = tmp_path / '사본'; copy(wb, docs, target)
        for row in plan['files']:
            archived = target / 'portable/originals' / row['document_id'] / row['saved_revision'] / row['asset']
            assert file_hash(archived) == row['sha256']
            if row.get('origin') != 'acknowledged_snapshot':
                assert archived.read_bytes() == (wb.workspace / row['path']).read_bytes()
        for d in selected(docs):
            assert (target / 'portable/originals' / d / WORKING / 'document.json').read_bytes() == snapshot_bytes(SnapshotReader(wb).current(d))
        # Missing only the new acknowledged Data input must NOT silently exclude draft.
        dataid = docs['data']['draft']['data_id']
        source = wb.root / 'inputs' / dataid / 'source.csv'
        raw = source.read_bytes(); source.unlink()
        blocked = inspect_copy(wb, selected(docs))
        assert blocked['status'] == 'BLOCKED'
        issue = next(i for i in blocked['issues'] if i['code'] == 'DRAFT_SOURCE_MISSING')
        assert dataid in issue['location'] and '저장본만' in issue['recovery']
        assert inspect_copy(wb, selected(docs), draft_policy='saved_only')['status'] == 'READY'
        destination = tmp_path / '거절 사본'
        with pytest.raises(PortableProjectError):
            create_copy(wb, plan, destination, approved=True, command_id='Cmissing', session_id=wb.session_id)
        assert not destination.exists()
        source.write_bytes(raw)
        assert inspect_copy(wb, selected(docs))['status'] == 'READY'
    finally: wb.shutdown()


def test_draft_only_no_saved_head_cold_owner_resume_and_redo(tmp_path):
    wb = Workbench(tmp_path / '미저장 원본')
    try:
        doc = wb.document_open(kind='material', title='아직 저장하지 않은 재료')
        first = deepcopy(doc['draft']); first['settings']['parameters']['E'] += 1
        doc = command(wb, doc, 'material.update', {'draft': first})
        second = deepcopy(first); second['settings']['parameters']['E'] += 1
        doc = command(wb, doc, 'material.update', {'draft': second})
        doc = command(wb, doc, 'document.undo')
        assert doc['can_redo'] and doc['saved_revision'] is None
        plan = inspect_copy(wb, [doc['id']]); assert plan['status'] == 'READY'
        receipt = create_copy(wb, plan, tmp_path / 'draft only', approved=True, command_id='Cnew', session_id=wb.session_id)
    finally: wb.shutdown()
    shutil.rmtree(wb.workspace)
    reopened = open_project(tmp_path / 'draft only')
    try:
        local = reopened.document_read(receipt['documents'][0]['document_id'])
        assert local['saved_revision'] is None and local['draft'] == first and local['dirty'] and local['can_redo']
        local = command(reopened, local, 'document.redo'); assert local['draft'] == second
        local = save(reopened, local); assert not local['dirty']
    finally: reopened.shutdown()
    assert verify_project(tmp_path / 'draft only')['status'] == 'READY'


def test_ack_rejects_unrelated_selected_saved_base(original):
    wb, docs = original
    old = docs['material']['saved_revision']
    draft = deepcopy(docs['material']['draft']); draft['settings']['parameters']['E'] += 8
    saved = save(wb, command(wb, docs['material'], 'material.update', {'draft': draft}))
    selection = [{'document_id': saved['id'], 'saved_revision': old}]
    assert inspect_copy(wb, selection)['issues'][0]['code'] == 'DRAFT_BASE_MISMATCH'
    assert inspect_copy(wb, selection, draft_policy='saved_only')['status'] == 'READY'


def test_inspection_rejects_ack_history_race_without_any_destination(original, tmp_path):
    wb, docs = original
    plan = inspect_copy(wb, selected(docs))
    # A source owner history change even without new generation is part of the pin.
    owner = wb.material_documents
    owner._documents[docs['material']['id']]['_redo'].append({'unknown': '1e'})
    destination = tmp_path / 'race'
    with pytest.raises(PortableProjectError):
        create_copy(wb, plan, destination, approved=True, command_id='Crace', session_id=wb.session_id)
    assert not destination.exists()


def test_local_engineering_filenames_and_inventory_confirmation(original, tmp_path):
    for name in ('sources/Dtest/source.key', 'sources/Dtest/source.pem', 'results/Jtest/config.toml', 'inputs/Jtest.json'):
        assert _asset_name(name) == name
    for name in ('results/Jtest/.env', 'results/Jtest/id_rsa', 'results/Jtest/credentials.json'):
        with pytest.raises(PortableProjectError, match='인증'): _asset_name(name)
    wb, docs = original
    with pytest.raises(ValueError, match='목록'):
        create_copy(wb, inspect_copy(wb, selected(docs)), tmp_path / 'no', approved=False,
                    command_id='Cno', session_id=wb.session_id)


def test_actual_raw_zip_spelling_rejected_before_destination(tmp_path):
    archive = tmp_path / 'raw.zip'
    info = zipfile.ZipInfo('normal')
    info.filename = 'folder\\file'  # Constructor normalizes on Windows; set AFTER constructor.
    with zipfile.ZipFile(archive, 'w') as writer: writer.writestr(info, b'raw')
    with zipfile.ZipFile(archive) as reader:
        assert reader.infolist()[0].orig_filename == 'folder\\file'
    destination = tmp_path / 'not published'
    with pytest.raises((ValueError, PortableProjectError)): extract_archive(archive, destination)
    assert not destination.exists()


def test_normalized_windows_zip_alias_is_still_checked(monkeypatch, tmp_path):
    info = zipfile.ZipInfo('folder/file'); info.orig_filename = 'folder\\file'
    class Archive:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def infolist(self): return [info]
    monkeypatch.setattr(zipfile, 'ZipFile', lambda *a, **kw: Archive())
    target = tmp_path / 'never'
    with pytest.raises((ValueError, PortableProjectError)): extract_archive(tmp_path / 'x.zip', target)
    assert not target.exists()


def test_legal_add_preview_cancel_repair_unlink_owner_undo_and_exact_saved(original):
    wb, docs = original
    planid = docs['plan']['id']; original_base = docs['plan']['saved_revision']
    saved_bytes = tree(wb.numerical_documents._folder(planid) / 'revisions')
    _, unlinked = edit(wb, planid, 'material', 'unlink', command_id='Cunlink')
    assert unlinked['document']['draft']['material'] is None
    target, source = target_selection(wb, planid), source_selection(wb, docs['material']['id'])
    before = tree(wb.workspace)
    proposal = preview_edit(wb, target, 'material', 'add', source)
    assert not proposal['impact']['domain_values_changed'] and not proposal['impact']['execution_requested']
    assert proposal['impact']['saved_reference']['document_id'] == docs['material']['id']
    with pytest.raises(ValueError, match='확인'): apply_edit(wb, proposal, confirmed=False, command_id='Ccancel')
    assert before == tree(wb.workspace), 'Preview/cancel must not persist even a receipt'
    result = apply_edit(wb, proposal, confirmed=True, command_id='Cadd')
    assert result['status'] == 'APPLIED'
    assert result['document']['saved_revision'] == original_base
    assert tree(wb.numerical_documents._folder(planid) / 'revisions') == saved_bytes
    assert apply_edit(wb, proposal, confirmed=True, command_id='Cadd')['status'] == 'ALREADY_APPLIED'
    assert len(wb.manager.list()) == 2  # Only the original two CSV imports.
    material = docs['material']; draft = deepcopy(material['draft']); draft['settings']['parameters']['E'] += 2
    material = command(wb, material, 'material.update', {'draft': draft})
    graph = build_graph(wb)
    node = next(n for n in graph['nodes'] if n['node_type'] == 'reference' and n['consumer_id'] == planid and n['path'] == ['draft', 'material'])
    assert node['status'] == 'INPUT_CHANGED'
    source = source_selection(wb, material['id'], basis='acknowledged')
    _, result = edit(wb, planid, 'material', 'repair', source, command_id='Crepair')
    newer = next(n for n in build_graph(wb)['nodes'] if n['key'] == node['key'])
    assert newer['status'] == 'ACKNOWLEDGED' and newer['exact_reference'] is None
    impact = read_impact(wb, planid, 'material')
    assert impact['impact']['current_reference'] != impact['impact']['saved_reference']
    undone = command(wb, result['document'], 'document.undo')
    assert undone['draft']['material']['draft'] != material['draft']
    assert tree(wb.numerical_documents._folder(planid) / 'revisions') == saved_bytes


@pytest.mark.parametrize('side', ['target', 'source'])
def test_stale_generation_retains_choice_and_can_explicitly_repreview(original, side):
    wb, docs = original
    planid, materialid = docs['plan']['id'], docs['material']['id']
    proposal = preview_edit(wb, target_selection(wb, planid), 'material', 'repair', source_selection(wb, materialid))
    untouched = deepcopy(proposal)
    doc = wb.document_read(planid if side == 'target' else materialid)
    draft = deepcopy(doc['draft'])
    if side == 'target': draft['seed'] += 1
    else: draft['settings']['parameters']['E'] += 1
    command(wb, doc, wb._document_owner(doc['id']).update_operation, {'draft': draft})
    before = tree(wb.workspace)
    with pytest.raises(PortableProjectError) as error: apply_edit(wb, proposal, confirmed=True, command_id='Cstale')
    assert error.value.issues[0].code == ('STALE_TARGET' if side == 'target' else 'STALE_SOURCE')
    assert tree(wb.workspace) == before and proposal == untouched
    fresh = preview_edit(wb, target_selection(wb, planid), proposal['port'], 'repair', source_selection(wb, materialid))
    assert apply_edit(wb, fresh, confirmed=True, command_id='Cfresh')['status'] in {'APPLIED', 'NO_CHANGE'}


def test_cross_store_clone_ids_and_old_session_cannot_alias(original, tmp_path):
    wb, docs = original
    target, source = target_selection(wb, docs['plan']['id']), source_selection(wb, docs['material']['id'])
    clone = tmp_path / 'same ids different store'
    shutil.copytree(wb.workspace, clone, ignore=shutil.ignore_patterns('controller.lock', 'service.json'))
    other = Workbench(clone)
    try:
        before = tree(other.workspace)
        with pytest.raises(ValueError, match='다른 보관소'):
            preview_edit(other, target, 'material', 'repair', source)
        own_target = target_selection(other, docs['plan']['id'])
        with pytest.raises(ValueError, match='다른 보관소'):
            preview_edit(other, own_target, 'material', 'repair', source)
        assert tree(other.workspace) == before
    finally: other.shutdown()


@pytest.mark.parametrize('change', ['kind', 'input', 'revision', 'result', 'job'])
def test_wrong_typed_identity_is_refused_without_change(original, change):
    wb, docs = original
    if change in {'result', 'job'}:
        source = source_selection(wb, docs['data']['id'], basis='result', job_id=docs['success_job']['id'], response='stress')
        source['result_sha256' if change == 'result' else 'job_id'] = '0' * 64 if change == 'result' else docs['failure_job']['id']
        port = 'experiment/Epublic'
    else:
        source = source_selection(wb, docs['material']['id'])
        source[{'kind': 'document_kind', 'input': 'input_revision', 'revision': 'saved_revision'}[change]] = {'kind':'data','input':'Iwrong','revision':'Rwrong'}[change]
        port = 'material'
    before = tree(wb.workspace)
    with pytest.raises((ValueError, OSError, KeyError)):
        preview_edit(wb, target_selection(wb, docs['plan']['id']), port, 'repair', source)
    assert before == tree(wb.workspace)


def test_observation_units_no_implicit_conversion_and_unsupported_relation(original):
    wb, docs = original
    source = source_selection(wb, docs['data']['id'], basis='result', job_id=docs['success_job']['id'], response='stress')
    proposal = preview_edit(wb, target_selection(wb, docs['plan']['id']), 'experiment/Epublic', 'repair', source)
    assert proposal['impact']['unit_or_field_mapping_applied'] is False
    plan = deepcopy(docs['plan']['draft']); plan['material']['draft']['settings']['stress_unit'] = 'Pa'
    command(wb, docs['plan'], 'numerical.update', {'draft': plan})
    before = tree(wb.workspace)
    with pytest.raises(ValueError, match='unit'):
        preview_edit(wb, target_selection(wb, docs['plan']['id']), 'experiment/Epublic', 'repair', source)
    with pytest.raises(ValueError, match='지원하지 않는'):
        preview_edit(wb, target_selection(wb, docs['material']['id']), 'invented-physics', 'add', source)
    assert tree(wb.workspace) == before


def test_graph_list_action_contract_exact_ref_and_view_state_do_not_edit_domain(original):
    wb, docs = original
    before = tree(wb.workspace)
    graph = build_graph(wb)
    listing = catalog(wb, docs['plan']['id'])
    assert tree(wb.workspace) == before
    assert {'material', 'experiment/Epublic'} <= {p['port'] for p in listing['ports']}
    relation = next(n for n in graph['nodes'] if n['node_type'] == 'reference' and n['consumer_id'] == docs['plan']['id'])
    assert set(relation['actions']) == {'select', 'cancel', 'open_owner', 'open_saved_reference', 'impact', 'add', 'repair', 'unlink'}
    assert relation['actions']['open_saved_reference']['reference'] == relation['exact_reference']
    assert relation['actions']['repair']['command'] == relation['actions']['unlink']['command'] == 'connection_preview'
    assert relation['actions']['repair']['target_id'] == docs['plan']['id']
    domain = domain_tree(wb)
    view = read_view(wb); state, keys = merge_bindings(graph, view['state'])
    key = keys[relation['key']]; state['selected'] = key; state['positions'][key] = [90., 80.]
    state['checked_documents'] = [docs['plan']['id']]; state['filter'] = '계획'
    receipt = save_view(wb, state, scope=view['scope'], expected_revision=view['revision'],
                        expected_sha256=view['state_sha256'], command_id='Cview')
    assert receipt['revision'] == 1 and domain_tree(wb) == domain
    assert save_view(wb, state, scope=view['scope'], expected_revision=view['revision'],
        expected_sha256=view['state_sha256'], command_id='Cview')['status'] == 'ALREADY_SAVED'
    with pytest.raises(PortableProjectError) as error:
        save_view(wb, state, scope=view['scope'], expected_revision=view['revision'],
            expected_sha256=view['state_sha256'], command_id='Cotherwindow')
    assert error.value.issues[0].code == 'STALE_VIEW'
    assert state['selected'] == key and read_view(wb)['state'] == state


def test_view_and_exact_relation_survive_new_process_and_move(original, tmp_path):
    wb, docs = original
    edit(wb, docs['plan']['id'], 'material', 'unlink', command_id='Cu')
    edit(wb, docs['plan']['id'], 'material', 'add', source_selection(wb, docs['material']['id']), command_id='Ca')
    graph = build_graph(wb); view = read_view(wb); state, keys = merge_bindings(graph, view['state'])
    key = keys['document/' + docs['plan']['id']]
    state['positions'][key] = [17., 49.]; state['selected'] = key
    state['checked_documents'] = selected(docs)
    save_view(wb, state, scope=view['scope'], expected_revision=view['revision'], expected_sha256=view['state_sha256'], command_id='Cv')
    copy(wb, docs, tmp_path / '복사 배치')
    moved = tmp_path / '다른 한글 공백'; (tmp_path / '복사 배치').rename(moved)
    wb.shutdown(); shutil.rmtree(wb.workspace)
    code = '''
import sys
from caelab.portable_project import open_project
from caelab.connection_graph import build_graph
from caelab.connection_graph_view import read_view, merge_bindings
wb=open_project(sys.argv[1])
try:
    graph=build_graph(wb); view=read_view(wb)
    state, keys=merge_bindings(graph,view['state'])
    assert state['positions'][state['selected']]==[17.,49.]
    assert state['selected'] in keys.values()
    row=next(r for r in graph['nodes'] if r['node_type']=='reference' and r['path']==['draft','material'])
    assert row['exact_reference']
    assert wb.research_reference(row['exact_reference'])['document']['kind']=='material'
    assert not wb.manager.list() and wb._assistance is None
finally: wb.shutdown()
'''
    result = subprocess.run([sys.executable, '-c', code, str(moved)], text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('bad', ['binary', 'path', 'nan', 'unknown-key', 'huge-filter'])
def test_project_view_rejects_untrusted_data_without_domain_write(original, bad):
    wb, docs = original
    view = read_view(wb); state, keys = merge_bindings(build_graph(wb), view['state'])
    key = next(iter(keys.values()))
    if bad == 'binary': state['panel'] = 'restoreState:BASE64'
    if bad == 'path': state['bindings'][0]['anchor']['file'] = '../../user/settings'
    if bad == 'nan': state['positions'][key] = [float('nan'), 0.]
    if bad == 'unknown-key': state['positions']['Vunknown'] = [1., 2.]
    if bad == 'huge-filter': state['filter'] = 'x' * 201
    before = tree(wb.workspace)
    with pytest.raises(ValueError): save_view(wb, state, scope=view['scope'], expected_revision=view['revision'], expected_sha256=view['state_sha256'], command_id='Cbad')
    assert tree(wb.workspace) == before


def test_busy_owner_refusal_releases_locks_and_keeps_original_selection(original):
    import threading
    wb,docs=original
    target=target_selection(wb,docs['plan']['id']);source=source_selection(wb,docs['material']['id'])
    held,release=threading.Event(),threading.Event()
    def owner_busy():
        with wb.numerical_documents._lock(docs['plan']['id']):
            held.set();assert release.wait(5)
    thread=threading.Thread(target=owner_busy);thread.start();assert held.wait(3)
    try:
        with pytest.raises(PortableProjectError) as error:
            preview_edit(wb,target,'material','repair',source)
        assert error.value.issues[0].code=='OWNER_BUSY'
    finally: release.set();thread.join(5)
    assert not thread.is_alive()
    assert preview_edit(wb,target,'material','repair',source)['source']==source


def test_ack_containers_never_become_fake_saved_revisions(tmp_path):
    from caelab.connection_graph import is_acknowledged_container
    wb, docs = dirty_fixture(tmp_path / '초안 원본')
    try:
        receipt=copy(wb,docs,tmp_path/'초안 사본')
    finally: wb.shutdown()
    shutil.rmtree(wb.workspace)
    copied=open_project(tmp_path/'초안 사본')
    try:
        mapping={r['source_document_id']:r for r in receipt['documents']}
        material=mapping[docs['material']['id']]; planid=mapping[docs['plan']['id']]['document_id']
        graph=build_graph(copied)
        ref=next(r for r in graph['nodes'] if r['node_type']=='reference' and r['consumer_id']==planid and r['path']==['draft','material'])
        assert ref['status']=='ACKNOWLEDGED' and ref['exact_reference'] is None
        available=catalog(copied,planid)
        saved={r['selection']['saved_revision'] for r in available['sources'] if r['selection']['basis']=='saved' and r['selection']['document_id']==material['document_id']}
        assert material['acknowledged_revision'] not in saved and material['saved_revision'] in saved
        with pytest.raises(ValueError,match='컨테이너'):
            source_selection(copied,material['document_id'],saved_revision=material['acknowledged_revision'])
        bad=inspect_copy(copied,[{'document_id':material['document_id'],'saved_revision':material['acknowledged_revision']}],draft_policy='saved_only')
        assert bad['status']=='BLOCKED' and bad['issues'][0]['code']=='SNAPSHOT_NOT_SAVED'
        new=save(copied,copied.document_read(material['document_id']))
        assert not is_acknowledged_container(SnapshotReader(copied).revision(new['id'],new['saved_revision']))
        assert source_selection(copied,new['id'])['saved_revision']==new['saved_revision']
    finally: copied.shutdown()


def test_intermediate_ack_material_binding_in_plan_undo_has_exact_owner_proof(original,tmp_path):
    from caelab.numerical_document import material_reference
    from caelab.portable_project_drafts import HISTORY
    wb,docs=original
    for delta in (11.,22.):
        draft=deepcopy(docs['material']['draft']);draft['settings']['parameters']['E']+=delta
        docs['material']=command(wb,docs['material'],'material.update',{'draft':draft})
        plan=deepcopy(docs['plan']['draft']);plan['material']=material_reference(docs['material'])
        docs['plan']=command(wb,docs['plan'],'numerical.update',{'draft':plan})
        if delta==11.: intermediate=deepcopy(plan['material'])
    before=tree(wb.workspace)
    inventory=inspect_copy(wb,selected(docs))
    assert inventory['status']=='READY',inventory
    assert any(r['saved_revision'].startswith(HISTORY) for r in inventory['revisions'])
    destination=tmp_path/'이력 이동';receipt=copy(wb,docs,destination)
    assert tree(wb.workspace)==before
    assert list((destination/'portable/originals').rglob('owner-receipt.json'))
    assert not list((destination/'workbench/documents').glob('*/commands/*.json'))
    wb.shutdown();shutil.rmtree(wb.workspace)
    copied=open_project(destination)
    try:
        mapping={r['source_document_id']:r['document_id'] for r in receipt['documents']}
        plan=copied.document_read(mapping[docs['plan']['id']])
        undone=command(copied,plan,'document.undo')
        assert undone['draft']['material']['draft']==intermediate['draft']
        assert undone['draft']['material']['generation']==intermediate['generation']
        node=next(r for r in build_graph(copied)['nodes'] if r['node_type']=='reference' and r['consumer_id']==plan['id'] and r['path']==['draft','material'])
        assert node['status']=='INPUT_CHANGED' and node['exact_reference'] is None and node['working_reference']
        redone=command(copied,undone,'document.redo');assert redone['draft']==plan['draft']
        second=inspect_copy(copied,[r['document_id'] for r in receipt['documents']])
        assert second['status']=='READY',second
        assert not copied.manager.list()
    finally:copied.shutdown()


@pytest.mark.parametrize('port', ['source', 'model_source'])
def test_request_document_ports_use_exact_existing_owner_contract(original, port):
    from caelab.numerical_document import request_draft
    wb, docs = original
    target = wb.document_open(kind='numerical', title='기존 request 참조 슬롯', draft=request_draft())
    target = save(wb, target)
    saved_base = target['saved_revision']
    source = source_selection(wb, docs['material']['id'])
    job_ids = [r['id'] for r in wb.manager.list()]
    before = tree(wb.workspace)
    proposal = preview_edit(wb, target_selection(wb, target['id']), port, 'add', source)
    assert tree(wb.workspace) == before
    assert proposal['impact']['domain_values_changed'] is False
    accepted = apply_edit(wb, proposal, confirmed=True, command_id='Crequest_' + port)['document']
    ref = accepted['draft'][port]
    assert set(ref) == {'document_id', 'kind', 'saved_revision', 'input_revision', 'input_sha256'}
    assert ref['document_id'] == docs['material']['id'] and ref['saved_revision'] == docs['material']['saved_revision']
    assert accepted['draft']['request'] == target['draft']['request']
    assert accepted['saved_revision'] == saved_base and accepted['dirty']
    undone = command(wb, accepted, 'document.undo')
    assert undone['draft'] == target['draft']
    assert [r['id'] for r in wb.manager.list()] == job_ids and wb._assistance is None


def test_existing_evaluation_stage_reference_unlink_add_preserves_stage_and_values(original):
    from caelab.evaluation_definition import default_draft, document_reference
    wb, docs = original
    draft = default_draft()
    draft['stages'] = [{'id': 'Fexisting', 'name': '원 owner가 선언한 단계',
                        'source': document_reference(docs['material'])}]
    target = save(wb, wb.document_open(kind='evaluation', title='단계 참조 검사', draft=draft))
    before_saved = tree(wb._document_owner(target['id'])._folder(target['id']) / 'revisions')
    count = len(wb.manager.list())
    listing = catalog(wb, target['id'])
    assert [row['port'] for row in listing['ports']] == ['stage/Fexisting']
    removed = edit(wb, target['id'], 'stage/Fexisting', 'unlink', command_id='Cstage_unlink')[1]['document']
    assert removed['draft']['stages'][0]['source'] is None
    assert removed['diagnostics']  # Unbound is an editable invalid state, not an approval.
    restored = edit(wb, target['id'], 'stage/Fexisting', 'add', source_selection(wb, docs['material']['id']),
                    command_id='Cstage_add')[1]['document']
    assert restored['draft'] == target['draft']
    assert tree(wb._document_owner(target['id'])._folder(target['id']) / 'revisions') == before_saved
    assert len(wb.manager.list()) == count and wb._assistance is None
