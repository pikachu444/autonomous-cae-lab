"""Actual Report/Material/Data owners; native image is a labelled contract fixture.

No Qt/native/provider success is asserted. Tests exercise real copy/retention,
current owner commands and source-unavailable process boundaries separately.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from caelab.connection_graph import saved_reference
from caelab.evaluation import file_hash
from caelab.portable_project import (inspect_copy, create_copy, open_project,
    verify_project, MANIFEST, _asset_name)
from caelab.portable_project_io import PortableProjectError
from caelab.portable_project_report import MARKER, asset_name, navigation_name
from caelab.report_image import apply_binding, validate_content
from caelab.storage import canonical_hash, load_json, save_json
from caelab.workbench import Workbench
from examples.portable_connection_public import command, save, create_public_store
from report_image_fixture import fixture


def file_tree(folder):
    return {p.relative_to(folder).as_posix(): file_hash(p)
            for p in sorted(Path(folder).rglob('*')) if p.is_file()
            and p.relative_to(folder).as_posix() != 'workbench/controller.lock'}


@contextmanager
def store(path):
    wb = Workbench(path)
    try:
        yield wb
    finally:
        closed = wb.shutdown()
        assert closed['joined'] and not closed['pending']


def section(binding, identifier='Esource'):
    return {'id': identifier, 'title': '원 공학 입력', 'text': '원값은 판단과 별도로 보존합니다.',
            'include': True, 'table': True, 'curve': False, 'asset': deepcopy(binding)}


def sample(wb, root, *, image=False):
    material = save(wb, wb.document_open(kind='material', title='탄성 입력'))
    report = wb.document_open(kind='report')
    first = wb.report_capture(report['id'], saved_reference(material))
    # Noncanonical bytes deliberately expose accidental JSON reserialization.
    path = wb.report_documents._folder(report['id']) / asset_name(first)
    path.write_text(json.dumps(load_json(path), ensure_ascii=False, separators=(', ', ': ')) + '\n\n', encoding='utf-8')
    first_bytes = path.read_bytes()
    draft = deepcopy(report['draft']); draft['sections'] = [section(first)]
    report = save(wb, command(wb, report, 'report.update', {'draft': draft}))
    saved_before = report
    changed = deepcopy(material['draft']); changed['settings']['parameters']['E'] += 17
    material = save(wb, command(wb, material, 'material.update', {'draft': changed}))
    second = wb.report_capture(report['id'], saved_reference(material))
    draft = deepcopy(report['draft']); draft['sections'][0]['asset'] = second
    png, image_binding = None, None
    if image:
        scripted = fixture(root / 'original external Post')
        image_binding = wb.report_documents.capture_image(report['id'], scripted['command'])
        content = wb.report_documents.asset(report['id'], image_binding)['content']
        png = validate_content(content)
        draft = apply_binding(draft, image_binding, content)
    report = command(wb, report, 'report.update', {'draft': draft})
    return {'material': material, 'report': report, 'saved': saved_before, 'first': first,
            'second': second, 'first_bytes': first_bytes, 'png': png, 'image': image_binding}


def publish(wb, ids, target, *, policy='acknowledged', command_id='Ccopy'):
    plan = inspect_copy(wb, ids, draft_policy=policy)
    assert plan['status'] == 'READY', plan.get('issues')
    result = create_copy(wb, plan, target, approved=True, command_id=command_id, session_id=wb.session_id)
    return plan, result


def row_of(receipt, kind):
    return next(row for row in receipt['documents'] if row['kind'] == kind)


def report_assets(wb, report):
    return wb.report_content(report['id'], [row['asset'] for row in report['draft']['sections'] if row.get('asset')])['assets']


@contextmanager
def cold_guard(monkeypatch):
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(repr(args))
        raise AssertionError('cold read must not execute/capture/access an original native path')
    with monkeypatch.context() as patch:
        for name in ('submit', '_execute', 'assistance_call'):
            patch.setattr(Workbench, name, forbidden)
        from caelab import report_image
        patch.setattr(report_image, 'verify_origin', forbidden)
        yield calls
    assert calls == []


@pytest.mark.parametrize('policy', ['acknowledged', 'saved_only'])
def test_report_copy_edit_save_recopy_keeps_raw_A_and_original_owner(tmp_path, monkeypatch, policy):
    original, target, next_target = (tmp_path / name for name in ('원 보관소', '새 위치', '재복사'))
    with store(original) as wb:
        case = sample(wb, tmp_path, image=True)
        before = file_tree(original)
        plan, made = publish(wb, [case['report']['id'], case['material']['id']], target, policy=policy)
        assert file_tree(original) == before
        assert wb.portable_recovery_catalog([case['report']['id']])['archives'] == []
        old_report_raw = (wb.report_documents._folder(case['report']['id']) / 'revisions' /
                          case['saved']['saved_revision'] / 'document.json').read_bytes()
    shutil.rmtree(original); shutil.rmtree(tmp_path / 'original external Post')
    with cold_guard(monkeypatch) as calls:
        wb = open_project(target)
        try:
            rid = row_of(made, 'report')['document_id']
            report = wb.document_read(rid)
            expected = case['report'] if policy == 'acknowledged' else case['saved']
            assert report['draft']['title'] == expected['draft']['title']
            assert report['draft']['sections'][0]['asset']['id'] == expected['draft']['sections'][0]['asset']['id']
            contents = report_assets(wb, report)
            assert contents[0]['source_status'] == 'AVAILABLE'
            assert contents[0]['reference']['document_id'] == case['material']['id']
            assert contents[0]['navigation_reference']['document_id'] == row_of(made, 'material')['document_id']
            if policy == 'acknowledged':
                assert contents[1]['source_status'] == 'UNAVAILABLE'
                assert contents[1]['navigation_reference'] is None
                assert validate_content(contents[1]['content']) == case['png']
            original_saved = target / 'portable/originals' / case['saved']['id'] / case['saved']['saved_revision']
            assert (original_saved / 'document.json').read_bytes() == old_report_raw
            assert (original_saved / asset_name(case['first'])).read_bytes() == case['first_bytes']
            draft = deepcopy(report['draft']); draft['title'] = '현재 사본에서 고친 제목'
            draft['sections'][0]['text'] = '현재 판단: UNKNOWN, 다음 작업은 미실행'
            report = command(wb, report, 'report.update', {'draft': draft})
            undone = command(wb, report, 'document.undo')
            assert undone['draft'] != draft
            report = save(wb, command(wb, undone, 'document.redo'))
            assert report['draft'] == draft
            assert report['runs'] == [] and wb.manager.list() == []
            _, made2 = publish(wb, [row['document_id'] for row in made['documents']], next_target, command_id='Crecopy')
        finally:
            assert wb.shutdown()['joined']
        shutil.rmtree(target)
        wb = open_project(next_target)
        try:
            report = wb.document_read(row_of(made2, 'report')['document_id'])
            assert report['draft']['title'] == '현재 사본에서 고친 제목'
            assert report_assets(wb, report)[0]['source_status'] == 'AVAILABLE'
            folder = wb.report_documents._folder(report['id']) / 'revisions' / report['saved_revision']
            blobs = [p.read_bytes() for p in (folder / 'portable_execution/report_archive').glob('*.json')]
            assert old_report_raw in blobs
            assert case['first_bytes'] in blobs
            assert (folder / asset_name(case['first'])).read_bytes() == case['first_bytes']
            assert not calls
        finally:
            assert wb.shutdown()['joined']


def test_actual_data_result_selected_rows_remain_current_source_and_frozen_values(tmp_path, monkeypatch):
    original, target = tmp_path / 'original', tmp_path / 'copy'
    wb, records = create_public_store(original)
    try:
        data = records['data']; report = wb.document_open(kind='report')
        ref = {'kind': 'result', **wb.document_result_reference(data['id'], records['success_job']['id'])}
        ref['selection'] = {'responses': ['stress'], 'rows': [1, 3]}
        binding = wb.report_capture(report['id'], ref)
        frozen = wb.report_documents.asset(report['id'], binding)
        draft = deepcopy(report['draft']); draft['sections'] = [section(binding)]
        report = save(wb, command(wb, report, 'report.update', {'draft': draft}))
        _, made = publish(wb, [report['id'], data['id']], target)
    finally:
        assert wb.shutdown()['joined']
    shutil.rmtree(original)
    with cold_guard(monkeypatch):
        wb = open_project(target)
        try:
            report = wb.document_read(row_of(made, 'report')['document_id'])
            retained = report_assets(wb, report)[0]
            assert retained['source_status'] == 'AVAILABLE'
            assert retained['content'] == frozen['content']
            assert retained['reference'] == ref
            response = retained['content']['result']['responses']['stress']
            assert response['unit'] == 'MPa' and response['component'] == 'xx'
            copied_data = wb.document_read(row_of(made, 'data')['document_id'])
            assert {row['retained_state'] for row in copied_data['runs']} == {'SUCCEEDED', 'FAILED'}
            assert not wb.manager.list()
        finally:
            assert wb.shutdown()['joined']


def test_standalone_report_never_looks_up_unselected_source(tmp_path, monkeypatch):
    with store(tmp_path / 'source') as wb:
        case = sample(wb, tmp_path)
        _, made = publish(wb, [case['report']['id']], tmp_path / 'copy')
    shutil.rmtree(tmp_path / 'source')
    wb = open_project(tmp_path / 'copy')
    try:
        report = wb.document_read(row_of(made, 'report')['document_id'])
        def forbidden(*args, **kwargs): raise AssertionError('unselected owner lookup')
        monkeypatch.setattr(wb.report_documents, 'resolve_reference', forbidden)
        content = report_assets(wb, report)[0]
        assert content['snapshot_status'] == 'AVAILABLE'
        assert content['source_status'] == 'UNAVAILABLE' and content['navigation_reference'] is None
        assert content['reference']['document_id'] == case['material']['id']
        save(wb, report)
    finally:
        assert wb.shutdown()['joined']


def test_new_capture_after_copy_is_new_asset_not_old_hash_rewrite(tmp_path):
    with store(tmp_path / 'source') as wb:
        case = sample(wb, tmp_path)
        _, made = publish(wb, [case['report']['id'], case['material']['id']], tmp_path / 'copy')
    shutil.rmtree(tmp_path / 'source')
    wb = open_project(tmp_path / 'copy')
    try:
        report = wb.document_read(row_of(made, 'report')['document_id'])
        before = wb.report_documents.asset(report['id'], report['draft']['sections'][0]['asset'])
        material = wb.document_read(row_of(made, 'material')['document_id'])
        draft = deepcopy(material['draft']); draft['settings']['parameters']['E'] += 3
        material = save(wb, command(wb, material, 'material.update', {'draft': draft}))
        new = wb.report_capture(report['id'], saved_reference(material))
        assert new['id'] != case['second']['id']
        draft = deepcopy(report['draft']); draft['sections'].append(section(new, 'Enew'))
        report = save(wb, command(wb, report, 'report.update', {'draft': draft}))
        assert report_assets(wb, report)[0]['content'] == before['content']
        _, made2 = publish(wb, [row['document_id'] for row in made['documents']], tmp_path / 'again')
    finally:
        assert wb.shutdown()['joined']
    shutil.rmtree(tmp_path / 'copy')
    wb = open_project(tmp_path / 'again')
    try:
        report = wb.document_read(row_of(made2, 'report')['document_id'])
        assert [row['source_status'] for row in report_assets(wb, report)] == ['AVAILABLE', 'AVAILABLE']
    finally:
        assert wb.shutdown()['joined']


@pytest.mark.parametrize('field', ['document_id', 'input_sha256', 'saved_revision'])
def test_unproved_reference_edit_cannot_save_or_replace_old_asset(tmp_path, field):
    with store(tmp_path / 'source') as wb:
        case = sample(wb, tmp_path)
        _, made = publish(wb, [case['report']['id'], case['material']['id']], tmp_path / 'copy')
    wb = open_project(tmp_path / 'copy')
    try:
        report = wb.document_read(row_of(made, 'report')['document_id'])
        pointer = wb.report_documents._folder(report['id']) / 'document.json'
        before = pointer.read_bytes()
        bad = deepcopy(report['draft']); ref = bad['sections'][0]['asset']['reference']
        ref[field] = '0' * 64 if field == 'input_sha256' else ('Mother' if field == 'document_id' else 'Rother')
        report = command(wb, report, 'report.update', {'draft': bad})
        assert report_assets(wb, report)[0]['source_status'] == 'SNAPSHOT_UNAVAILABLE'
        with pytest.raises(ValueError): save(wb, report)
        assert pointer.read_bytes() == before
        assert wb.document_read(report['id'])['draft'] == bad
        assert inspect_copy(wb, [row['document_id'] for row in made['documents']])['status'] == 'BLOCKED'
    finally:
        assert wb.shutdown()['joined']


@pytest.mark.parametrize('fault', ['missing', 'changed'])
def test_history_only_A_is_required_before_publication(tmp_path, fault):
    with store(tmp_path / 'source') as wb:
        case = sample(wb, tmp_path)
        path = wb.report_documents._folder(case['report']['id']) / asset_name(case['first'])
        if fault == 'missing':
            path.unlink()
            saved = wb.report_documents._folder(case['saved']['id']) / 'revisions' / case['saved']['saved_revision'] / asset_name(case['first'])
            saved.unlink()
        else:
            path.write_bytes(b'{}')
        before = file_tree(tmp_path / 'source')
        plan = inspect_copy(wb, [case['report']['id'], case['material']['id']])
        assert plan['status'] == 'BLOCKED'
        assert file_tree(tmp_path / 'source') == before
        assert not (tmp_path / 'copy').exists()


def test_origin_archive_other_asset_tamper_blocks_save_and_keeps_current_buffer(tmp_path):
    with store(tmp_path / 'source') as wb:
        case = sample(wb, tmp_path)
        _, made = publish(wb, [case['report']['id']], tmp_path / 'copy')
    wb = open_project(tmp_path / 'copy')
    try:
        report = wb.document_read(row_of(made, 'report')['document_id'])
        root = wb.report_documents._folder(report['id'])
        before = (root / 'document.json').read_bytes()
        # The original first A is only in the historical owner archive of the
        # current second A; copying it with a newly computed hash is forbidden.
        proof = load_json(root / report[MARKER][case['second']['id']]['file'])
        archive = load_json(root / proof['origin']['owner_archive']['file'])
        raw = next(row for row in archive['files'] if row['path'] == asset_name(case['first']))
        (root / raw['original']['file']).write_bytes(b'{}')
        draft = deepcopy(report['draft']); draft['title'] = '저장 실패해도 유지할 본문'
        report = command(wb, report, 'report.update', {'draft': draft})
        with pytest.raises(ValueError): save(wb, report)
        assert (root / 'document.json').read_bytes() == before
        assert wb.document_read(report['id'])['draft'] == draft
    finally:
        assert wb.shutdown()['joined']


def test_same_command_lost_response_and_current_edits_are_not_rolled_back(tmp_path):
    with store(tmp_path / 'source') as wb:
        case = sample(wb, tmp_path)
        plan, made = publish(wb, [case['report']['id']], tmp_path / 'copy')
        copied = open_project(tmp_path / 'copy')
        try:
            report = copied.document_read(row_of(made, 'report')['document_id'])
            draft = deepcopy(report['draft']); draft['title'] = '응답 확인 전 새 편집'
            save(copied, command(copied, report, 'report.update', {'draft': draft}))
            before = file_tree(tmp_path / 'copy')
            response = create_copy(wb, plan, tmp_path / 'copy', approved=True, command_id='Ccopy', session_id=wb.session_id)
            assert response['status'] == 'ALREADY_CREATED' and file_tree(tmp_path / 'copy') == before
            assert copied.document_read(report['id'])['draft'] == draft
            with pytest.raises(FileExistsError):
                create_copy(wb, plan, tmp_path / 'copy', approved=True, command_id='Cdifferent', session_id=wb.session_id)
        finally:
            assert copied.shutdown()['joined']


def test_review_stale_after_owner_edit_has_no_copy_side_effect(tmp_path):
    with store(tmp_path / 'source') as wb:
        case = sample(wb, tmp_path)
        plan = inspect_copy(wb, [case['report']['id']])
        draft = deepcopy(case['report']['draft']); draft['title'] = '다른 창 입력'
        current = command(wb, case['report'], 'report.update', {'draft': draft})
        before = file_tree(tmp_path / 'source')
        with pytest.raises(PortableProjectError, match='바뀌었습니다'):
            create_copy(wb, plan, tmp_path / 'copy', approved=True, command_id='Cstale', session_id=wb.session_id)
        assert file_tree(tmp_path / 'source') == before and not (tmp_path / 'copy').exists()
        assert wb.document_read(current['id'])['draft'] == draft


def test_publish_failure_never_leaves_a_complete_marker(tmp_path, monkeypatch):
    with store(tmp_path / 'source') as wb:
        case = sample(wb, tmp_path)
        plan = inspect_copy(wb, [case['report']['id']])
        before = file_tree(tmp_path / 'source')
        original = Path.rename
        def refused(path, destination):
            if Path(destination) == tmp_path / 'copy' / MANIFEST:
                raise OSError('controlled publication failure before last manifest')
            return original(path, destination)
        monkeypatch.setattr(Path, 'rename', refused)
        with pytest.raises(OSError, match='controlled publication'):
            create_copy(wb, plan, tmp_path / 'copy', approved=True, command_id='Cfailure', session_id=wb.session_id)
        assert not (tmp_path / 'copy' / MANIFEST).exists()
        assert (tmp_path / 'copy' / '.incomplete.json').exists()
        assert verify_project(tmp_path / 'copy')['status'] == 'BLOCKED'
        assert file_tree(tmp_path / 'source') == before
        assert not list(tmp_path.glob('.caelab-copy-*'))


@pytest.mark.parametrize('policy', ['saved_only', 'acknowledged'])
def test_invalid_authored_text_is_not_scanned_or_rewritten(tmp_path, policy):
    with store(tmp_path / 'source') as wb:
        raw = {'title': '', 'sections': [], 'engineering_release': 'NOT_RELEASED',
               'unrecognized_authored_input': {'document_id': 'Mother', 'path': r'Z:\\외부\\자료', 'text': '1e-'}}
        report = save(wb, wb.document_open(kind='report', draft=raw))
        assert report['diagnostics']
        _, made = publish(wb, [report['id']], tmp_path / 'copy', policy=policy)
    shutil.rmtree(tmp_path / 'source')
    wb = open_project(tmp_path / 'copy')
    try:
        doc = wb.document_read(row_of(made, 'report')['document_id'])
        assert doc['draft'] == raw
        assert save(wb, doc)['draft'] == raw
    finally:
        assert wb.shutdown()['joined']


def test_never_saved_report_uses_existing_working_owner_not_fake_saved_head(tmp_path):
    with store(tmp_path / 'source') as wb:
        report = wb.document_open(kind='report')
        assert report['saved_revision'] is None
        _, made = publish(wb, [report['id']], tmp_path / 'copy')
    wb = open_project(tmp_path / 'copy')
    try:
        doc = wb.document_read(row_of(made, 'report')['document_id'])
        assert doc['saved_revision'] is None
        assert save(wb, doc)['saved_revision']
    finally:
        assert wb.shutdown()['joined']


def test_literature_is_not_republished_without_the_pending_scope_contract(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from apps.research.portable_research_report import export_checked
    from test_portable_study_report_export import window
    with store(tmp_path / 'source') as wb:
        report = wb.document_open(kind='report')
        source = {'status': 'AVAILABLE', 'document_id': 'paper', 'revision': 1, 'segments': [{'text': 'scoped source'}], 'sha256': 'a' * 64}
        ref = {'kind': 'knowledge', 'document_id': 'paper', 'revision': 1, 'locator': {'segment_id': '0'},
               'source_sha256': 'a' * 64, 'content_sha256': canonical_hash(source)}
        wb.report_documents.resolve_reference = lambda r: {'kind': 'knowledge', 'source': deepcopy(source)}
        binding = wb.report_capture(report['id'], ref)
        draft = deepcopy(report['draft']); draft['sections'] = [section(binding)]
        report = save(wb, command(wb, report, 'report.update', {'draft': draft}))
        before = file_tree(tmp_path / 'source')
        plan = inspect_copy(wb, [report['id']])
        assert plan['status'] == 'BLOCKED'
        assert any(row['code'] == 'KNOWLEDGE_ACCESS_DENIED' for row in plan['issues']), plan['issues']
        destination = tmp_path / 'copy'
        with pytest.raises(ValueError):
            create_copy(wb, plan, destination, approved=True, command_id='Cdenied', session_id=wb.session_id)
        assert not destination.exists()

        # Exercise the menu's real Markdown exporter and current owner read;
        # only the file picker and scheduling are controlled, not publication.
        output = tmp_path / 'summary.md'; output.write_text('KEEP OLD OUTPUT', encoding='utf-8')
        monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(output), 'Markdown (*.md)'))
        host = window(wb, report); host.client = wb; host._pending = None
        def call(read, accepted):
            accepted(read())
            return True
        host._call = call
        assert export_checked(host, 'md')
        assert output.read_text(encoding='utf-8') == 'KEEP OLD OUTPUT'
        assert host.assets[binding['id']]['snapshot_status'] == 'SCOPE_REQUIRED'
        assert 'content' not in host.assets[binding['id']]

        host.draft['sections'][0]['include'] = False
        summary = '원문을 제외한 사용자 작성 요약입니다.'
        host.draft['sections'].append({'id': 'Esummary', 'title': '작성 요약', 'text': summary,
            'include': True, 'table': False, 'curve': False})
        assert export_checked(host, 'md')
        exported = output.read_text(encoding='utf-8')
        assert summary in exported and 'scoped source' not in exported
        assert ref['document_id'] not in exported
        assert wb.document_read(report['id'])['draft'] == report['draft']
        assert file_tree(tmp_path / 'source') == before


@pytest.mark.parametrize('name,kind', [('assets/A' + 'a' * 64 + '.json', 'material'),
    ('assets/.env', 'report'), ('assets/A' + 'a' * 64 + '.exe', 'report'),
    ('assets/../operator.json', 'report'), ('assets\\A' + 'a' * 64 + '.json', 'report')])
def test_narrow_report_asset_allowlist_does_not_extend_other_owners(name, kind):
    with pytest.raises((ValueError, PortableProjectError)):
        _asset_name(name, kind)


def test_text_only_report_preserves_original_owner_across_save_and_recopy(tmp_path):
    with store(tmp_path / 'plain_source') as wb:
        report = save(wb, wb.document_open(kind='report'))
        path = wb.report_documents._folder(report['id']) / 'revisions' / report['saved_revision'] / 'document.json'
        old_raw = path.read_bytes()
        _, first = publish(wb, [report['id']], tmp_path / 'first_plain')
    shutil.rmtree(tmp_path / 'plain_source')
    wb = open_project(tmp_path / 'first_plain')
    try:
        report = wb.document_read(row_of(first, 'report')['document_id'])
        draft = deepcopy(report['draft']); draft['title'] = '자료 없는 본문도 편집 가능'
        report = save(wb, command(wb, report, 'report.update', {'draft': draft}))
        source_before_recopy = (wb.report_documents._folder(report['id']) / 'revisions' / report['saved_revision'] / 'document.json').read_bytes()
        _, second = publish(wb, [report['id']], tmp_path / 'second_plain')
    finally:
        assert wb.shutdown()['joined']
    shutil.rmtree(tmp_path / 'first_plain')
    wb = open_project(tmp_path / 'second_plain')
    try:
        report = save(wb, wb.document_read(row_of(second, 'report')['document_id']))
        assert report['draft']['title'] == draft['title'] and report['draft']['sections'] == []
        root = wb.report_documents._folder(report['id']) / 'revisions' / report['saved_revision']
        blobs = [p.read_bytes() for p in (root / 'portable_execution/report_archive').glob('*.json')]
        assert old_raw in blobs and source_before_recopy in blobs
    finally:
        assert wb.shutdown()['joined']


@pytest.mark.parametrize('fault', ['missing', 'changed'])
def test_copied_image_loss_does_not_publish_or_discard_current_text(tmp_path, fault):
    with store(tmp_path / 'image_source') as wb:
        case = sample(wb, tmp_path, image=True)
        _, receipt = publish(wb, [case['report']['id']], tmp_path / 'image_copy')
    shutil.rmtree(tmp_path / 'image_source')
    shutil.rmtree(tmp_path / 'original external Post')
    wb = open_project(tmp_path / 'image_copy')
    try:
        report = wb.document_read(row_of(receipt, 'report')['document_id'])
        root = wb.report_documents._folder(report['id'])
        image_path = root / asset_name(case['image'])
        raw = image_path.read_bytes()
        pointer = (root / 'document.json').read_bytes()
        if fault == 'missing': image_path.unlink()
        else: image_path.write_bytes(b'{}')
        try:
            draft = deepcopy(report['draft']); draft['sections'][0]['text'] = '실패해도 보존할 현재 본문'
            report = command(wb, report, 'report.update', {'draft': draft})
            read = report_assets(wb, report)
            assert read[-1]['source_status'] == 'SNAPSHOT_UNAVAILABLE' and 'content' not in read[-1]
            assert read[0]['snapshot_status'] == 'AVAILABLE'
            with pytest.raises(ValueError): save(wb, report)
            assert wb.document_read(report['id'])['draft'] == draft
            assert (root / 'document.json').read_bytes() == pointer
            assert verify_project(tmp_path / 'image_copy')['status'] == 'BLOCKED'
        finally:
            image_path.write_bytes(raw)
        assert verify_project(tmp_path / 'image_copy')['status'] == 'READY'
        save(wb, report)
    finally:
        assert wb.shutdown()['joined']


def test_report_archive_closure_keeps_existing_total_size_gate(tmp_path, monkeypatch):
    from caelab import portable_project
    with store(tmp_path / 'limit_source') as wb:
        case = sample(wb, tmp_path)
        monkeypatch.setattr(portable_project, 'MAX_BYTES', 1)
        before = file_tree(tmp_path / 'limit_source')
        plan = inspect_copy(wb, [case['report']['id']])
        assert plan['status'] == 'BLOCKED' and any(row['code'] == 'SIZE_LIMIT' for row in plan['issues'])
        assert file_tree(tmp_path / 'limit_source') == before
