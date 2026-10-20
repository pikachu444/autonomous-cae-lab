"""Actual Qt + local HTTP/upload/archive; no model, solver or native host is run."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import time
import threading

import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFileDialog
from PySide6.QtTest import QTest

from apps.lab.service import LabService
from apps.research.expert_window import ExpertWindow, connect_desktop_actions
from apps.research.expert_sources import SourceDialog
from caelab.workbench_client import Client
from test_lab_server import running


def wait(app, predicate, detail=lambda: ''):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('Source action did not settle: ' + detail())



def drain_closed(app, *views):
    """Finish only these views' existing workers before their HTTP service exits."""
    workers, late_refreshes = [], []
    for view in views:
        if view is None:
            continue
        if isinstance(view, ExpertWindow):
            QTimer.singleShot(0, lambda view=view: late_refreshes.append(view.refresh_registry()))
            view._allow_close = True
            view.close()
            child = getattr(view, '_source_dialog', None)
            if child:
                workers.extend(child._workers)
        else:
            view.reject()
        workers.extend(view._workers)
    wait(app, lambda: all(worker.completed.is_set() for worker in workers))
    app.processEvents()
    assert all(result is False for result in late_refreshes)
    assert all(view._closed for view in views if view is not None)

@pytest.mark.parametrize('attach', [False, True])
@pytest.mark.parametrize('suffix', ['.md', '.log'])
def test_native_file_choice_import_preview_cancel_or_attach_and_reopen(attach, suffix, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / ('공개 연구 자료'+suffix)
    path.write_text('# Measured observation\nPublic fixture: beam displacement 0.2294 mm.', encoding='utf-8')
    chosen = []
    def choose(*args, **kwargs):
        assert '*'+suffix in args[-1]
        # Initial library reads are complete: the next request is binary upload.
        client.token = 'EXPIRED_TEST_TOKEN'
        chosen.append(True)
        return str(path), 'Research sources'
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', choose)
    with running(LabService(tmp_path / 'store')) as transport:
        wb = transport.server.workbench
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        window = ExpertWindow(client, poll_interval=20)
        reopened = None
        observed = []
        original_exec = SourceDialog.exec
        def drive_dialog(dialog):
            deadline = time.monotonic() + 10
            def tick():
                ready = (not dialog._busy and dialog._import_job is None and
                         dialog.preview.payload is not None and dialog.preview.payload.get('segments'))
                if ready:
                    observed.append(dialog.preview.text.toPlainText())
                    button = QDialogButtonBox.StandardButton.Ok if attach else QDialogButtonBox.StandardButton.Cancel
                    QTest.mouseClick(dialog.buttons.button(button), Qt.MouseButton.LeftButton)
                elif time.monotonic() >= deadline:
                    observed.append('TIMEOUT: ' + dialog.message.text())
                    dialog.reject()
                else:
                    QTimer.singleShot(20, tick)
            QTimer.singleShot(20, tick)
            return original_exec(dialog)
        monkeypatch.setattr(SourceDialog, 'exec', drive_dialog)
        try:
            window.show()
            wait(app, lambda: window.document is not None and not window._busy)
            window.timer.stop()
            wait(app, lambda: not window._busy)
            window.question.setPlainText('Keep this independent research question')
            before = deepcopy(window.edited_draft())
            window.choose_sources(add_file=True)
            wait(app, lambda: not window._busy, lambda: window.message.text())
            assert chosen == [True]
            assert len(observed) == 1 and '0.2294 mm' in observed[0], observed
            library = wb.assistance_call('knowledge.list', {})['documents']
            assert len(library) == 1 and library[0]['title'] == path.name
            jobs = wb.manager.list()
            assert len(jobs) == 1 and jobs[0]['operation'] == 'knowledge.ingest'
            if not attach:
                assert window.edited_draft() == before
                assert 'selected_sources' not in wb.document_read(window.document['id'])['draft']['context']
                return
            expected = [{'document_id': library[0]['document_id'], 'revision': 1}]
            assert window.edited_draft()['context']['selected_sources'] == expected
            assert window.question.toPlainText() == before['composer']['text']
            assert window.edited_draft()['composer']['evidence'] == before['composer']['evidence']
            assert not window.edited_draft()['context'].get('transmission_scope', {}).get('source_refs')
            assert window.selected_sources.item(0).text() == path.name
            window.save_document()
            wait(app, lambda: not window._busy and not window.local_dirty)
            identifier = window.document['id']
            window.selected_sources.setCurrentRow(0)
            window.remove_source()
            window.apply_inputs()
            wait(app, lambda: not window._busy and not window.local_dirty)
            window.command('document.undo')
            wait(app, lambda: not window._busy and window.edited_draft()['context']['selected_sources'] == expected)
            window.command('document.redo')
            wait(app, lambda: not window._busy and not window.edited_draft()['context']['selected_sources'])
            window.command('document.undo')
            wait(app, lambda: not window._busy and window.edited_draft()['context']['selected_sources'] == expected)
            window.intervene()
            wait(app, lambda: not window._busy and bool(window.document['turns']))
            assert window.document['turns'][-1]['author'] == 'user'
            window.save_document()
            wait(app, lambda: not window._busy and not window.local_dirty)
            window._allow_close = True
            window.close()
            reopened = ExpertWindow(client, document_id=identifier, poll_interval=0)
            reopened.show()
            wait(app, lambda: reopened.document is not None and not reopened._busy)
            assert reopened.edited_draft()['context']['selected_sources'] == expected
            # An immediate foreground read must not lose deferred title resolution.
            reopened.selected_sources.setCurrentRow(0)
            reopened.read_selected_source()
            wait(app, lambda: not reopened._busy and reopened.selected_sources.item(0).text() == path.name,
                 lambda: reopened.message.text())
            assert reopened.selected_sources.currentRow() == 0
            assert reopened.question.toPlainText() == before['composer']['text']
            selected_item = reopened.selected_sources.currentItem()
            polls = []
            original_read = client.document_read
            def count_read(identifier):
                result = original_read(identifier)
                polls.append(identifier)
                return result
            monkeypatch.setattr(client, 'document_read', count_read)
            reopened.timer.start(20)
            wait(app, lambda: len(polls) >= 2 and not reopened._busy)
            assert reopened.selected_sources.currentItem() is selected_item
            assert reopened.source_open.isEnabled() and reopened.source_remove.isEnabled()
            QTest.mouseClick(reopened.source_open, Qt.MouseButton.LeftButton)
            wait(app, lambda: not reopened._busy and reopened.source_preview.payload is not None)
            assert reopened.source_preview.payload['title'] == path.name
            citation = dict(expected[0], locator=reopened.source_preview.payload['segments'][0]['locator'])
            assert reopened.selected_sources.currentItem() is selected_item
            QTest.mouseClick(reopened.source_remove, Qt.MouseButton.LeftButton)
            assert reopened.edited_draft()['context']['selected_sources'] == []
            assert reopened.local_dirty and reopened.source_preview.payload is None
            assert wb.document_read(identifier)['draft']['context']['selected_sources'] == expected
            # Explicit historical reading is allowed after a local deselection;
            # polling keeps that view, while an owner switch clears it.
            connect_desktop_actions(reopened, client)
            reopened.open_reference(citation)
            wait(app, lambda: not reopened._busy and reopened.source_preview.payload is not None)
            previous_polls = len(polls)
            wait(app, lambda: len(polls) >= previous_polls + 2 and not reopened._busy)
            assert reopened.source_preview.payload['title'] == path.name
            reopened.open_document(title='Other question')
            wait(app, lambda: not reopened._busy and reopened.document['id'] != identifier)
            assert reopened.source_preview.payload is None
            assert '0.2294' not in reopened.source_preview.text.toPlainText()
            assert reopened.selected_sources.count() == 0
            assert len(wb.manager.list()) == 1
        finally:
            drain_closed(app, window, reopened)


def test_library_keeps_old_revision_until_explicit_change(tmp_path):
    app = QApplication.instance() or QApplication([])
    with running(LabService(tmp_path / 'store')) as transport:
        wb = transport.server.workbench
        archive = wb.assistance().knowledge
        one = wb.upload('observation.md', b'# Original\nOLD-OBSERVATION')
        first = archive.ingest(wb.input_path(one['id']), 'research', workspace_id=wb.workspace_id)
        two = wb.upload('observation.md', b'# Revised\nNEW-OBSERVATION')
        archive.ingest(wb.input_path(two['id']), 'research', workspace_id=wb.workspace_id,
                       document_id=first['document_id'])
        context = {'selected_sources': [{'document_id': first['document_id'], 'revision': 1}]}
        original = deepcopy(context)
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        dialog = SourceDialog(client, context)
        dialog.show()
        try:
            wait(app, lambda: dialog.preview.payload is not None and not dialog._busy)
            assert 'OLD-OBSERVATION' in dialog.preview.text.toPlainText()
            dialog.version.setCurrentIndex(dialog.version.findData(2))
            wait(app, lambda: not dialog._busy and dialog.preview.payload and dialog.preview.payload['revision'] == 2)
            assert 'NEW-OBSERVATION' in dialog.preview.text.toPlainText()
            dialog.version.setCurrentIndex(dialog.version.findData(1))
            wait(app, lambda: not dialog._busy and dialog.preview.payload and dialog.preview.payload['revision'] == 1)
            started, release = threading.Event(), threading.Event()
            callbacks = []
            def late_failure():
                started.set()
                release.wait(5)
                raise OSError('Explicit late-request failure test double')
            dialog._call(late_failure, lambda value: callbacks.append(value),
                         rejected=lambda error: callbacks.append(error))
            wait(app, started.is_set)
            QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel), Qt.MouseButton.LeftButton)
            release.set()
            assert context == original and dialog.references is None
            drain_closed(app, dialog)
            assert callbacks == []
        finally:
            if 'release' in locals():
                release.set()
            drain_closed(app, dialog)


def test_blank_pdf_preview_reports_extraction_and_blocks_attach(tmp_path):
    from pypdf import PdfWriter
    app = QApplication.instance() or QApplication([])
    path = tmp_path / 'blank.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(path)
    with running(LabService(tmp_path / 'store')) as transport:
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        dialog = SourceDialog(client, {})
        dialog.show()
        try:
            wait(app, lambda: not dialog._busy)
            dialog.import_file(path)
            wait(app, lambda: dialog.preview.payload is not None and not dialog._busy and dialog._import_job is None,
                 lambda: dialog.message.text())
            assert not dialog.preview.payload['segments']
            assert 'OCR' in dialog.preview.notice.text()
            dialog.verify_selection()
            wait(app, lambda: not dialog._busy)
            assert dialog.references is None and '읽을 수 있는 본문이 없습니다' in dialog.message.text()
            assert all(job['operation'] == 'knowledge.ingest' for job in transport.server.workbench.manager.list())
        finally:
            drain_closed(app, dialog)


def test_file_question_snapshots_rerun_in_origin_discussion(tmp_path, monkeypatch):
    from apps.research.selection_discussion import open_file_discussion
    from apps.research.expert_sources import assist
    launches = []
    monkeypatch.setattr('apps.research.desktop.launch_tool',
        lambda client, tool, **arguments: launches.append((tool, arguments)) or {'launched': True})
    path = tmp_path / 'solver.log'
    path.write_text('ITERATION 4 RESIDUAL 0.17\n', encoding='utf-8')
    with running(LabService(tmp_path / 'store')) as transport:
        wb = transport.server.workbench
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        runtime = wb.assistance().experts
        runtime.definitions = {identifier: {'id': identifier, 'collections': [identifier, 'shared-project']}
                               for identifier in ('materials', 'testing')}
        first = open_file_discussion(client, [path])
        document = first['document']
        draft = deepcopy(document['draft'])
        draft['composer']['text'] = 'Unsent: preserve the measured density.'
        draft['context']['constraints'] = ['Keep the existing material law']
        draft['context']['failure_reasons'] = ['Contact increment did not converge']
        changed = client.document_command(document['id'], 'expert.update', {'draft': draft},
            session_id=document['session_id'], expected_generation=document['generation'])['document']
        path.write_text('ITERATION 5 RESIDUAL 0.12\n', encoding='utf-8')
        second = open_file_discussion(client, [path], discussion_id=document['id'])
        assert second['document_id'] == first['document_id']
        assert second['executed'] is False
        current = second['document']['draft']
        assert current['composer'] == changed['draft']['composer']
        assert current['context']['constraints'] == draft['context']['constraints']
        assert current['context']['failure_reasons'] == draft['context']['failure_reasons']
        old = document['draft']['context']['selected_sources'][0]
        assert assist(client, 'knowledge.source', old)['collection'] == 'shared-project'
        for role in runtime.definitions.values():
            allowed, _ = runtime._knowledge_context(current['context'], wb.workspace_id, role['collections'])
            assert allowed['selected_sources'] == current['context']['selected_sources']
        assert current['context']['transmission_scope'] == document['draft']['context']['transmission_scope']
        selected = current['context']['selected_sources']
        assert len(selected) == 2 and selected[0] == old and selected[1]['document_id'] != old['document_id']
        assert 'RESIDUAL 0.17' in assist(client, 'knowledge.source', old)['segments'][0]['text']
        assert 'RESIDUAL 0.12' in assist(client, 'knowledge.source', selected[1])['segments'][0]['text']
        assert launches == [('expert', {'document_id': document['id']})] * 2
        assert all(job['operation'] == 'knowledge.ingest' for job in wb.manager.list())
        assert wb.document_read(document['id'])['draft'] == current


@pytest.mark.parametrize('evidence_kind',['regression','local'])
def test_calculix_file_bundle_attaches_without_repeating_companion_text(tmp_path,monkeypatch,evidence_kind):
    import json
    import shutil
    from pathlib import Path
    from apps.research.selection_discussion import open_file_discussion
    from caelab.discussion_document import default_draft
    if evidence_kind=='local':
        folder=os.environ.get('CAELAB_CALCULIX_EVIDENCE_DIR')
        if not folder:pytest.skip('No selected local CalculiX evidence directory')
        candidates=[path for path in Path(folder).glob('*.inp')
            if all(path.with_suffix(ext).is_file() for ext in ('.sta','.cvg','.dat','.frd'))]
        assert len(candidates)==1
        source=candidates[0]
    else:
        folder=tmp_path/'evidence';folder.mkdir()
        source=folder/'observation.inp'
        fixtures=Path(__file__).parent/'fixtures'
        for ext in ('.inp','.sta','.cvg'):
            shutil.copyfile(fixtures/'ns1_convergence_0548ee0'/('contact'+ext),source.with_suffix(ext))
        shutil.copyfile(fixtures/'calculix_221_structural_family'/'family.frd',source.with_suffix('.frd'))
        source.with_suffix('.dat').write_bytes(b'Explicit test-only retained diagnostic\n'*500)
    paths=[source.with_suffix(ext) for ext in ('.inp','.sta','.cvg','.dat','.frd')]
    monkeypatch.setattr('apps.research.desktop.launch_tool',lambda *args,**kwargs:{'launched':True})
    with running(LabService(tmp_path/'store')) as transport:
        wb=transport.server.workbench
        client=Client('http://127.0.0.1:'+str(transport.server.server_port))
        draft=default_draft()
        draft['composer']['text']='Keep the original unsent question'
        draft['context']={'constraints':['Preserve the material law and mesh'],
            'engineering_context':{'model':{'model_state':'saved_model','materials':[{'name':'Original material'}]}}}
        original=wb.document_open(kind='expert',draft=draft)
        receipt=open_file_discussion(client,paths,discussion_id=original['id'])
        saved=client.document_read(original['id'])
        assert receipt['document']['id']==original['id']
        context=saved['draft']['context'];observed=context['engineering_context']
        assert saved['draft']['composer']==draft['composer']
        assert context['constraints']==draft['context']['constraints']
        assert context['engineering_context_history']==[draft['context']['engineering_context']]
        assert [row['source']['path'] for row in observed['sources']]==list(map(str,paths))
        assert len(observed['logs'])==3 and len(observed['convergence'])==1
        assert observed['sources'][0]['model']['model_state']=='calculation_input'
        assert observed['sources'][-1]['result']['frames']
        assert observed['state'] is None
        assert len(context['selected_sources'])==4
        assert len(json.dumps(saved['draft'],allow_nan=False).encode())<=96*1024
        assert all(job['operation']=='knowledge.ingest' for job in wb.manager.list())


def test_workbench_sources_require_existing_common_role_collection_before_upload(tmp_path, monkeypatch):
    from apps.research.selection_discussion import open_file_discussion
    from apps.research.expert_sources import source_collection
    path = tmp_path / 'solver.log'
    path.write_text('Actual solver diagnostic\n', encoding='utf-8')
    with running(LabService(tmp_path / 'store')) as transport:
        wb = transport.server.workbench
        runtime = wb.assistance().experts
        runtime.definitions = {identifier: {'id': identifier, 'collections': [identifier]}
                               for identifier in ('materials', 'testing')}
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        uploaded = []
        monkeypatch.setattr(client, 'upload', lambda *args: uploaded.append(args))
        with pytest.raises(ValueError, match='함께 읽을 보관함'):
            open_file_discussion(client, [path])
        assert uploaded == [] and wb.manager.list() == []
        assert runtime.definitions['materials']['collections'] == ['materials']
        from caelab.discussion_document import default_draft
        draft = default_draft()
        draft['participants'] = ['materials']
        doc = wb.document_open(kind='expert', draft=draft)
        assert source_collection(client, doc['id']) == 'materials'


def test_live_unsaved_model_question_does_not_require_file_or_ingestion(tmp_path, monkeypatch):
    from apps.research.selection_discussion import open_file_discussion
    monkeypatch.setattr('apps.research.desktop.launch_tool', lambda *args, **kwargs: {'launched': True})
    with running(LabService(tmp_path / 'store')) as transport:
        wb = transport.server.workbench
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        receipt = open_file_discussion(client, [], selection={
            'model_snapshot': {'kind': 'native-structural-model', 'materials': [{'name': 'User material'}]},
            'scope': {'objects': ['SelectedBody'], 'subelements': ['Face2']}})
        context = receipt['document']['draft']['context']['engineering_context']
        assert context['source']['path'] is None
        assert context['model']['model_state'] == 'current_editing_model'
        assert context['source']['scope']['subelements'] == ['Face2']
        assert wb.manager.list() == []


def test_unconfigured_research_can_archive_files_without_model_or_role_grants(tmp_path, monkeypatch):
    from apps.research.selection_discussion import open_file_discussion
    from apps.research.expert_sources import assist
    monkeypatch.setattr('apps.research.desktop.launch_tool', lambda *args, **kwargs: {'launched': True})
    path = tmp_path / 'unassigned.log'
    path.write_text('Retained local observation\n', encoding='utf-8')
    with running(LabService(tmp_path / 'store')) as transport:
        wb = transport.server.workbench
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        receipt = open_file_discussion(client, [path])
        draft = receipt['document']['draft']
        assert draft['participants'] == []
        source = assist(client, 'knowledge.source', draft['context']['selected_sources'][0])
        assert source['collection'] == 'research'
        assert source['segments'][0]['text'] == path.read_bytes().decode('utf-8')
        assert not draft['context']['transmission_scope'].get('source_refs')
        assert all(job['operation'] == 'knowledge.ingest' for job in wb.manager.list())


def test_source_role_scope_notice_preserves_existing_grants(tmp_path):
    app = QApplication.instance() or QApplication([])
    with running(LabService(tmp_path / 'store')) as transport:
        wb = transport.server.workbench
        wb.assistance().experts.definitions = {'selected': {'id': 'selected', 'label': '선택 담당자',
            'collections': ['permitted'], 'tools': []}}
        upload = wb.upload('original.log', b'Actual archived diagnostic\n')
        source = wb.assistance().knowledge.ingest(wb.input_path(upload['id']), 'different', workspace_id=wb.workspace_id)
        from caelab.discussion_document import default_draft
        draft = default_draft()
        draft['participants'] = ['selected']
        draft['context']['selected_sources'] = [{key: source[key] for key in ('document_id', 'revision')}]
        draft['context']['transmission_scope'] = {'source_refs': []}
        doc = wb.document_open(kind='expert', draft=draft)
        client = Client('http://127.0.0.1:' + str(transport.server.server_port))
        window = ExpertWindow(client, document_id=doc['id'], poll_interval=0)
        try:
            window.show()
            wait(app, lambda: not window._busy and bool(window._registry) and bool(window._source_collections))
            assert '선택 담당자' in window.source_scope_notice.text()
            assert not window.source_scope_notice.isHidden()
            assert window.edited_draft()['context']['transmission_scope'] == {'source_refs': []}
            assert wb.assistance().experts.definitions['selected']['collections'] == ['permitted']
        finally:
            drain_closed(app, window)


def test_native_question_cli_reads_utf8_selection_and_origin(monkeypatch, capsys):
    import io
    import json
    from apps.research import selection_discussion
    selected = {'path': 'C:/models/사용자.FCStd', 'scope': {'objects': ['고체'], 'faces': ['Face2']}}
    state = {'model': {'original_path': selected['path'], 'saved_path': selected['path']}}
    calls = []
    client = object()
    monkeypatch.setattr('caelab.workbench_client.Client', lambda url: client)
    monkeypatch.setattr('sys.stdin', io.TextIOWrapper(io.BytesIO(json.dumps(selected, ensure_ascii=False).encode('utf-8'))))
    monkeypatch.setattr(selection_discussion, 'open_file_discussion',
        lambda *args, **kwargs: calls.append((args, kwargs)) or {'document_id': 'Xorigin'})
    selection_discussion.main(['--service', 'http://127.0.0.1:8765', '--selection-stdin',
        '--workbench', json.dumps(state), '--discussion', 'Xorigin', selected['path']])
    assert calls == [((client, [selected['path']], 'Xorigin'), {'selection': selected, 'workbench': state})]
    assert json.loads(capsys.readouterr().out) == {'document_id': 'Xorigin', 'executed': False}
