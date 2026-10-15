"""Real owners and real file imports; native physics is intentionally not mocked as success."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile

import pytest

from caelab.connection_graph import SnapshotReader
from caelab.evaluation import file_hash
from caelab.portable_project import (MANIFEST, create_copy, inspect_copy, open_project,
                                    verify_project, repair_asset, extract_project)
from caelab.portable_project_io import PortableProjectError, extract_archive, relative_name
from caelab.storage import canonical_hash, load_json, save_json
from examples.portable_connection_public import create_public_store, command, save, wait


@pytest.fixture
def original(tmp_path):
    wb, docs = create_public_store(tmp_path / '공개 원본')
    try:
        yield wb, docs
    finally:
        wb.shutdown()


def selected(docs):
    return [docs[k]['id'] for k in ('data', 'material', 'plan', 'second_plan')]


def create(wb, docs, folder, command_id='Ccopy', *, draft_policy='acknowledged'):
    plan = inspect_copy(wb, selected(docs), draft_policy=draft_policy)
    assert plan['status'] == 'READY', plan
    return create_copy(wb, plan, folder, approved=True, command_id=command_id, session_id=wb.session_id)


def tree_hash(folder):
    runtime_lock = folder / 'workbench' / 'controller.lock'
    return {p.relative_to(folder).as_posix():
            (('runtime-lock', p.stat().st_size, p.stat().st_mtime_ns) if p == runtime_lock else file_hash(p))
            for p in folder.rglob('*') if p.is_file()}


def test_real_original_deleted_cold_process_moved_edit_resave(tmp_path):
    output = tmp_path / '공개 재현'
    completed = subprocess.run([sys.executable, '-m', 'examples.portable_connection_public', '--output', str(output)],
                               capture_output=True, text=True, check=True, timeout=90)
    evidence = json.loads(completed.stdout)
    assert evidence['original_store_deleted'] and evidence['edited_and_saved']
    assert evidence['states'] == ['FAILED', 'SUCCEEDED']
    assert evidence['verification_after_edit'] == 'READY'
    moved = output / '두 번째 한글 이동 폴더'
    Path(evidence['moved_workspace']).rename(moved)
    code = '''
from caelab.portable_project import open_project, verify_project
from caelab.storage import canonical_hash
from pathlib import Path
import sys
wb=open_project(sys.argv[1])
try:
    assert wb._assistance is None
    docs=wb.documents()['documents']
    data=next(d for d in docs if d['kind']=='data')
    assert wb.document_source_preview(data['id'])['retained'] is True
    assert data['draft']['test_metadata']['protocol']=='사본 편집 후 저장'
    assert verify_project(sys.argv[1])['status']=='READY'
finally: wb.shutdown()
'''
    subprocess.run([sys.executable, '-c', code, str(moved)], capture_output=True, text=True, check=True, timeout=60)


def test_manifest_original_bytes_new_typed_ids_no_original_queue(original, tmp_path):
    wb, docs = original
    target = tmp_path / '복사본'
    plan = inspect_copy(wb, selected(docs))
    before = tree_hash(wb.workspace)
    receipt = create(wb, docs, target)
    assert tree_hash(wb.workspace) == before
    manifest = load_json(target / MANIFEST)
    mapping = {r['source_document_id']: r['document_id'] for r in receipt['documents']}
    assert not set(mapping) & set(mapping.values())
    for row in plan['files']:
        original_path = wb.workspace / row['path']
        archived = target / 'portable' / 'originals' / row['document_id'] / row['saved_revision'] / row['asset']
        if row.get('origin') == 'acknowledged_snapshot':
            assert file_hash(archived) == row['sha256']
            assert archived.stat().st_size == row['bytes']
        else:
            assert original_path.read_bytes() == archived.read_bytes()
    assert not list((target / 'workbench').glob('jobs/*.json'))
    assert not list((target / 'workbench').glob('documents/*/commands/*'))
    copied = open_project(target)
    try:
        local = copied.document_read(mapping[docs['plan']['id']])
        assert local['draft']['material']['document_id'] == mapping[docs['material']['id']]
        assert local['draft']['experiments'][0]['source']['document_id'] == mapping[docs['data']['id']]
        assert local['draft']['material']['input_revision'] != docs['material']['input_revision']
        # The real numerical owner can resolve copied Material/Data, no original store.
        prepared = copied.numerical_documents.job_arguments(local['draft'])
        assert prepared['experiments'][0]['observations']['value'] == [0., 1.2, 2.4]
        data = copied.document_read(mapping[docs['data']['id']])
        assert data['draft']['test_metadata']['temperature'] == 'UNKNOWN'
        assert copied._assistance is None
        original_result = wb.document_result(docs['data']['id'], docs['success_job']['id'])
        assert copied.document_result(data['id'], docs['success_job']['id']) == original_result
        assert copied.desktop.job_record(docs['failure_job']['id'])['error'] == docs['failure_job']['error']
        assert data['runs'][0]['portable_origin']['input_revision'] == docs['data']['runs'][0]['input_revision']
    finally:
        copied.shutdown()


def test_copied_data_can_import_again_without_original_registry(original, tmp_path):
    wb, docs = original
    target = tmp_path / '작업 사본'
    create(wb, docs, target)
    wb.shutdown()
    shutil.rmtree(wb.workspace)
    copied = open_project(target)
    try:
        data = next(d for d in copied.documents()['documents'] if d['kind'] == 'data')
        assert not (copied.root / 'inputs' / data['draft']['data_id']).exists()
        result = copied.document_command(data['id'], 'data.import', {},
                    session_id=copied.session_id, expected_generation=data['generation'])
        assert wait(copied, result['job']['id'])['state'] == 'SUCCEEDED'
        data = save(copied, copied.document_read(data['id']))
        assert len(data['runs']) == 3
        assert copied.document_result(data['id'], result['job']['id'])['responses']['stress']['value'] == [0., 1.2, 2.4]
    finally:
        copied.shutdown()
    assert verify_project(target)['status'] == 'READY'


def test_idempotent_response_loss_does_not_overwrite(original, tmp_path):
    wb, docs = original
    target = tmp_path / '사본'
    plan = inspect_copy(wb, selected(docs))
    options = dict(approved=True, command_id='Csame', session_id=wb.session_id)
    first = create_copy(wb, plan, target, **options)
    before = tree_hash(target)
    second = create_copy(wb, plan, target, **options)
    assert second['status'] == 'ALREADY_CREATED'
    assert first['project_id'] == second['project_id']
    assert tree_hash(target) == before
    with pytest.raises(FileExistsError):
        create_copy(wb, plan, target, **{**options, 'command_id': 'Cdifferent'})
    assert tree_hash(target) == before


def test_existing_empty_folder_and_nested_destination_refused(original, tmp_path):
    wb, docs = original
    target = tmp_path / '기존 비어 있는 폴더'; target.mkdir()
    with pytest.raises(FileExistsError):
        create(wb, docs, target)
    with pytest.raises(ValueError, match='겹치지'):
        create(wb, docs, wb.workspace / 'inside')
    assert list(target.iterdir()) == []


def test_stale_generation_session_and_inspection_rejected(original, tmp_path):
    wb, docs = original
    plan = inspect_copy(wb, selected(docs))
    with pytest.raises(ValueError, match='서비스'):
        create_copy(wb, plan, tmp_path / 'old_session', approved=True, command_id='C1', session_id='Sold')
    changed = deepcopy(plan); changed['files'][0]['bytes'] += 1
    with pytest.raises(ValueError, match='목록'):
        create_copy(wb, changed, tmp_path / 'edited', approved=True, command_id='C2', session_id=wb.session_id)
    draft = deepcopy(docs['material']['draft']); draft['settings']['parameters']['E'] += 20
    command(wb, docs['material'], 'material.update', {'draft': draft})
    with pytest.raises(PortableProjectError) as failure:
        create_copy(wb, plan, tmp_path / 'stale', approved=True, command_id='C3', session_id=wb.session_id)
    assert failure.value.issues[0].code == 'STALE_INSPECTION'
    assert not (tmp_path / 'stale').exists()


def test_explicit_approval_missing_dependencies_and_unsaved_document(original, tmp_path):
    wb, docs = original
    with pytest.raises(ValueError, match='확인'):
        create_copy(wb, inspect_copy(wb, selected(docs)), tmp_path / 'unapproved',
                    approved=False, command_id='C1', session_id=wb.session_id)
    before = tree_hash(wb.workspace)
    plan = inspect_copy(wb, [docs['plan']['id']])
    assert plan['status'] == 'BLOCKED'
    assert 'DOCUMENT_NOT_SELECTED' in {i['code'] for i in plan['issues']}
    assert tree_hash(wb.workspace) == before
    unsaved = wb.document_open(kind='material', title='미저장')
    result = inspect_copy(wb, [unsaved['id']], draft_policy='saved_only')
    assert result['status'] == 'BLOCKED' and result['issues'][0]['code'] == 'SAVE_REQUIRED'


def test_unsaved_current_excluded_and_old_bound_input_retained(original, tmp_path):
    wb, docs = original
    draft = deepcopy(docs['material']['draft']); draft['settings']['parameters']['E'] += 30
    updated = command(wb, docs['material'], 'material.update', {'draft': draft})
    plan = inspect_copy(wb, selected(docs), draft_policy='saved_only')
    assert any(w['code'] == 'UNSAVED_DRAFT_EXCLUDED' for w in plan['warnings'])
    first = tmp_path / '저장본만'; create(wb, docs, first, draft_policy='saved_only')
    copied = open_project(first)
    try:
        material = next(d for d in copied.documents()['documents'] if d['kind'] == 'material')
        assert material['draft'] == docs['material']['draft']
    finally:
        copied.shutdown()
    save(wb, updated)
    second = tmp_path / '이전 참조 포함'; create(wb, docs, second, 'Cnext')
    copied = open_project(second)
    try:
        nodes = copied.connection_graph()['nodes']
        exact = next(n for n in nodes if n['node_type'] == 'reference' and n['status'] == 'INPUT_CHANGED')
        old = copied.research_reference(exact['exact_reference'])
        assert old['document']['draft']['settings']['parameters']['E'] == docs['material']['draft']['settings']['parameters']['E']
        current = copied.document_read(exact['owner_id'])
        assert current['draft']['settings']['parameters']['E'] == draft['settings']['parameters']['E']
    finally:
        copied.shutdown()


def test_unknown_extensions_preserved_not_id_heuristics(original, tmp_path):
    wb, docs = original
    owner = wb.data_documents
    extension = {'document_id': docs['material']['id'], 'opaque_notes': 'UNKNOWN',
                 'units': {'mystery': None}, 'nested': ['UNSPECIFIED']}
    owner._documents[docs['data']['id']]['unrecognized_future_field'] = deepcopy(extension)
    data = save(wb, wb.document_read(docs['data']['id']))
    target = tmp_path / 'unknown 보존'; create(wb, docs, target)
    copied = open_project(target)
    try:
        local = next(d for d in copied.documents()['documents'] if d['kind'] == 'data')
        assert local['unrecognized_future_field'] == extension
    finally:
        copied.shutdown()


def test_nearby_files_and_operator_configuration_not_collected(original, tmp_path):
    wb, docs = original
    sentinel = b'PUBLIC_TEST_SENTINEL_NOT_A_REAL_SECRET'
    (wb.workspace / '.env').write_bytes(sentinel)
    (wb.root / 'operator.json').write_bytes(sentinel)
    (wb.workspace / 'unselected-company-placeholder.txt').write_bytes(sentinel)
    target = tmp_path / '선택 자료만'; create(wb, docs, target)
    assert all(sentinel not in p.read_bytes() for p in target.rglob('*') if p.is_file())
    assert not (target / '.env').exists()


def test_missing_raw_source_exact_location_and_no_destination(original, tmp_path):
    wb, docs = original
    doc = SnapshotReader(wb).current(docs['data']['id'])
    source, _ = wb.data_documents._retained_source(doc, doc['draft']['data_id'])
    source.unlink()
    inspection = inspect_copy(wb, selected(docs))
    assert inspection['status'] == 'BLOCKED'
    assert any(i['location'] == str(source) and i['recovery'] for i in inspection['issues'])
    with pytest.raises(ValueError):
        create_copy(wb, inspection, tmp_path / '실패사본', approved=True, command_id='C1', session_id=wb.session_id)
    assert not (tmp_path / '실패사본').exists()


def test_missing_and_changed_asset_explicit_same_byte_repair(original, tmp_path):
    wb, docs = original
    target = tmp_path / '복구사본'; create(wb, docs, target)
    manifest = load_json(target / MANIFEST)
    row = next(r for r in manifest['files'] if r['path'].startswith('workbench/') and r['path'].endswith('source.csv'))
    source = target / row['path']
    replacement = tmp_path / '정확한 원자료.csv'; replacement.write_bytes(source.read_bytes())
    source.unlink()
    check = verify_project(target)
    assert check['status'] == 'BLOCKED'
    assert any(i['location'] == str(source) and i['code'] == 'MISSING_ASSET' for i in check['issues'])
    with pytest.raises(PortableProjectError):
        open_project(target)
    wrong = tmp_path / '다른자료.csv'; wrong.write_bytes(b'different')
    with pytest.raises(PortableProjectError):
        repair_asset(target, row['path'], wrong, approved=True)
    assert not source.exists()
    assert repair_asset(target, row['path'], replacement, approved=True)['status'] == 'REPAIRED'
    assert verify_project(target)['status'] == 'READY'
    assert repair_asset(target, row['path'], replacement, approved=True)['status'] == 'ALREADY_PRESENT'
    source.write_bytes(b'CHANGED_BYTES_KEPT_IN_QUARANTINE')
    assert verify_project(target)['status'] == 'BLOCKED'
    receipt = repair_asset(target, row['path'], replacement, approved=True)
    assert receipt['quarantined'] is True
    assert any(p.read_bytes() == b'CHANGED_BYTES_KEPT_IN_QUARANTINE'
               for p in (target / 'portable' / 'repair-history').rglob('changed-file'))
    assert verify_project(target)['status'] == 'READY'


def test_publication_failure_preserves_visible_incomplete_copy(original, tmp_path, monkeypatch):
    wb, docs = original
    target = tmp_path / '발행 실패'
    original_rename = Path.rename
    def fail_publish(self, destination):
        if self.name == 'portable' and self.parent.name.startswith('.caelab-copy-'):
            raise OSError('injected disk publication failure')
        return original_rename(self, destination)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'rename', fail_publish)
        with pytest.raises(OSError):
            create(wb, docs, target)
    assert (target / '.incomplete.json').is_file()
    assert verify_project(target)['status'] == 'BLOCKED'
    assert not list(tmp_path.glob('.caelab-copy-*'))
    with pytest.raises(FileExistsError):
        create(wb, docs, target)
    assert wb.document_source_preview(docs['data']['id'])['retained']


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'C:/drive', r'folder\file', 'file:ads',
                                 'a/../../b', './file', 'a//b', 'NUL.txt', 'aux', 'name.', 'name ',
                                 'a/CON/b', '\x00bad'])
def test_unsafe_portable_paths_refused(name):
    with pytest.raises(PortableProjectError):
        relative_name(name)


@pytest.mark.parametrize('names', [['../escape'], ['/absolute'], ['x', 'x/y'], ['A.json', 'a.json'],
                                  [r'folder\file'], ['C:drive'], ['good', 'good']])
def test_unsafe_zip_preflight_creates_nothing(tmp_path, names):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for name in names:
            info = zipfile.ZipInfo(name)
            # Win32 ZipInfo normalizes constructor backslashes. Retain the
            # actual hostile member spelling in the written archive.
            info.filename = name
            z.writestr(info, 'content')
    target = tmp_path / 'new'
    with pytest.raises(PortableProjectError):
        extract_archive(archive, target)
    assert not target.exists()
    assert not (tmp_path / 'escape').exists()


def test_zip_symlink_and_destination_link_refused(tmp_path):
    archive = tmp_path / 'link.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        info = zipfile.ZipInfo('link'); info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(info, '../outside')
    with pytest.raises(PortableProjectError):
        extract_archive(archive, tmp_path / 'new')
    real = tmp_path / 'real'; real.mkdir()
    link = tmp_path / 'alias'
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip('OS does not permit symlink creation for this account')
    with pytest.raises(PortableProjectError):
        extract_archive(archive, link / 'new')


def test_legitimate_archive_reopens_without_original(original, tmp_path):
    wb, docs = original
    target = tmp_path / '사본'; create(wb, docs, target)
    archive = tmp_path / '사본.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for path in target.rglob('*'):
            if path.is_file(): z.write(path, path.relative_to(target).as_posix())
    extracted = tmp_path / '새 경로 압축 해제'
    assert extract_project(archive, extracted)['status'] == 'READY'
    wb.shutdown(); shutil.rmtree(wb.workspace); shutil.rmtree(target)
    copied = open_project(extracted)
    try:
        assert len(copied.documents()['documents']) == 4
        assert copied._assistance is None
    finally:
        copied.shutdown()


@pytest.mark.parametrize('bad', ['.', 'a*', 'a?', '<a>', 'a|b', 'a"b'])
def test_windows_invalid_names_on_all_platforms(bad):
    with pytest.raises(PortableProjectError):
        relative_name(bad)


def test_archive_parent_case_alias_refused_before_creation(tmp_path):
    path = tmp_path / 'ambiguous.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('Data/one', b'1')
        archive.writestr('data/two', b'2')
    with pytest.raises(PortableProjectError):
        extract_archive(path, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_retained_comparison_rewrites_bindings_but_preserves_curves_and_original_bytes(original, tmp_path):
    wb, docs = original
    data = docs['data']
    run = next(r for r in data['runs'] if r.get('retained_result'))
    result = wb.document_result(data['id'], run['job_id'])
    channel = next(iter(result['responses']))
    reference = {'document_id': data['id'], 'job_id': run['job_id'], 'response': channel}
    compared = wb.document_compare(reference, reference)
    docs['data'] = save(wb, wb.document_read(data['id']))
    folder = tmp_path / '비교 포함'
    created = create(wb, docs, folder)
    copied_id = next(r['document_id'] for r in created['documents'] if r['source_document_id'] == data['id'])
    wb.shutdown(); shutil.rmtree(wb.workspace)
    copied = open_project(folder)
    try:
        local = copied.data_documents.comparison(copied_id, compared['id'])
        assert local['comparison'] == compared['comparison']
        assert local['binding']['source']['document_id'] == copied_id
        assert local['binding']['prediction_source']['document_id'] == copied_id
        graph = copied.connection_graph([copied_id])
        assert not any(n['status'] == 'BROKEN' for n in graph['nodes'])
        save(copied, copied.document_read(copied_id))
        assert copied.data_documents.comparison(copied_id, compared['id']) == local
    finally:
        copied.shutdown()
    assert verify_project(folder)['status'] == 'READY'


def test_input_only_material_binding_does_not_invent_saved_revision(original):
    wb, docs = original
    save(wb, docs['material'])
    graph = wb.connection_graph([docs['plan']['id']])
    node = next(n for n in graph['nodes'] if n['node_type'] == 'reference' and n['owner_kind'] == 'material')
    assert node['status'] == 'AVAILABLE'
    assert node['diagnostic']['basis'] == 'input_identity'
    assert 'saved_revision' not in node['diagnostic']['reference']


def test_no_calculation_provider_or_input_registration_on_cold_open(original, tmp_path, monkeypatch):
    from caelab.workbench import Workbench
    wb, docs = original
    folder = tmp_path / 'no execution'
    create(wb, docs, folder)
    wb.shutdown(); shutil.rmtree(wb.workspace)
    def forbidden(*args, **kwargs):
        raise AssertionError('Opening must not execute, plan, ask a provider, or register source input')
    for method in ('submit', '_execute', 'upload', 'assistance_call', '_store_input'):
        monkeypatch.setattr(Workbench, method, forbidden)
    copied = open_project(folder)
    try:
        assert not copied.manager.list()
        assert not any(n['status'] == 'BROKEN' for n in copied.connection_graph()['nodes'])
    finally:
        copied.shutdown()


def test_unpinned_legacy_job_detected_in_current_and_undo_contract():
    from caelab.portable_project import _unpinned_job_inputs
    raw = {'kind': 'numerical', 'draft': {'mode': 'request', 'request': {'inputs': {'training_job': 'Jlegacy'}}},
           '_undo': [{'mode': 'request', 'request': {'inputs': {'job_id': 'Jold'}}}],
           'unknown': {'job_id': 'Junrelated'}}
    assert list(_unpinned_job_inputs(raw)) == ['draft/request/inputs/training_job', '_undo/0/request/inputs/job_id']


def test_copies_from_one_store_have_disjoint_document_ids(original, tmp_path):
    wb, docs = original
    a = create(wb, docs, tmp_path / 'A', 'Ca')
    b = create(wb, docs, tmp_path / 'B', 'Cb')
    a_ids = {r['document_id'] for r in a['documents']}
    b_ids = {r['document_id'] for r in b['documents']}
    assert not a_ids & b_ids and not a_ids & set(selected(docs))
    wa, wb2 = open_project(tmp_path / 'A'), open_project(tmp_path / 'B')
    try:
        assert a_ids == set(SnapshotReader(wa).identities())
        assert wa.session_id != wb2.session_id
        with pytest.raises((ValueError, FileNotFoundError)):
            wa.document_read(next(iter(b_ids)))
    finally:
        wa.shutdown(); wb2.shutdown()


def test_concurrent_identical_request_publishes_once(original, tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import caelab.portable_project as module
    wb, docs = original
    plan = inspect_copy(wb, selected(docs))
    folder = tmp_path / '동시 요청'
    started, release = threading.Event(), threading.Event()
    original_copy = module.copy_verified
    first = True
    def blocking(*args, **kwargs):
        nonlocal first
        if first:
            first = False; started.set()
            assert release.wait(5)
        return original_copy(*args, **kwargs)
    monkeypatch.setattr(module, 'copy_verified', blocking)
    def run():
        return create_copy(wb, plan, folder, approved=True, command_id='Cconcurrent', session_id=wb.session_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(run)
        assert started.wait(3)
        b = pool.submit(run)
        release.set()
        receipts = [a.result(timeout=10), b.result(timeout=10)]
    assert {r['status'] for r in receipts} == {'CREATED', 'ALREADY_CREATED'}
    assert len({r['project_id'] for r in receipts}) == 1
    assert verify_project(folder)['status'] == 'READY'


def test_unmanifested_controller_directory_link_blocks_open_before_external_read(original, tmp_path):
    wb, docs = original
    folder = tmp_path / '작업 사본'
    create(wb, docs, folder)
    outside = tmp_path / '외부 자료'; outside.mkdir()
    (outside / 'secret.json').write_text('DO NOT READ', encoding='utf-8')
    try:
        (folder / 'workbench' / 'jobs').symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip('This platform does not grant symlink creation: ' + str(error))
    assert verify_project(folder)['status'] == 'BLOCKED'
    with pytest.raises(PortableProjectError):
        open_project(folder)
    assert not (folder / 'workbench' / 'controller.lock').exists()


def test_raw_registered_input_request_blocks_portable_success(original):
    from caelab.numerical_document import request_draft
    wb, docs = original
    draft = request_draft({'purpose': '명시 등록 파일 확인', 'operation': 'evaluate',
        'inputs': {'backend': 'files.table', 'settings': {'data_id': docs['data']['draft']['data_id']}},
        'budget': {'evaluations': 1}})
    document = save(wb, wb.document_open(kind='numerical', draft=draft))
    result = inspect_copy(wb, [document['id'], docs['data']['id']])
    assert result['status'] == 'BLOCKED'
    assert any(i['code'] == 'EXTERNAL_INPUT_CONTRACT' for i in result['issues'])
