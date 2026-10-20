"""Injected Qt controls against the bounded authoring owner; no native processes."""
from copy import deepcopy
import os
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6 import QtCore, QtWidgets

from caelab.storage import canonical_hash
from apps.desktop_pre.structural_transfer_panel import make_panel, _number
from test_structural_transfer_binding import authoring_case, _author_preview_apply


def panel_case(monkeypatch, metadata=None, catalog_error=False, empty_analysis=False, view_actions=(), offline=False, conditions=None):
    author, fem, state, captured, draft = authoring_case(monkeypatch, metadata)
    owner = fem.owner
    solver = SimpleNamespace(Name='Solver', Label='기존 CalculiX', TypeId='Fem::SolverCcxTools',
                             AnalysisType='static', GeometricalNonlinearity='linear')
    body = SimpleNamespace(Name='Solid', Label='적용 부품')
    support = SimpleNamespace(Name='TransferBoundary', Label='기존 지지면',
        TypeId='Fem::ConstraintFixed', References=[(body, ['Face1'])])
    analysis = fem._object({'object_id':'Analysis'}); analysis.Label = '정적 해석 1'
    analysis.Group = [solver] + ([support] if conditions is None else list(conditions))
    owner.document_id = 'Preceiver'; owner.session_id = 'Sreceiver'; owner.closed = False
    owner.fem = fem
    owner.doc = SimpleNamespace(Name='Receiver', Objects=[] if empty_analysis else [analysis])
    owner._object = lambda identifier: {'Analysis': analysis, 'Solver': solver,
        'Solid': body}[identifier]
    fem._object = lambda target: owner._object(target['object_id'])
    state['catalog_error'] = catalog_error; state['defer'] = False; state['callbacks'] = []
    def catalog():
        if state['catalog_error']: raise ValueError('원본 목록 읽기 실패')
        if 'catalog_rows' in state: return deepcopy(state['catalog_rows'])
        return [{'reference': deepcopy(draft['source_reference']), 'label': '보존한 변위 계산',
                 'static': None, 'read_status': 'NOT_READ'}]
    def source(reference):
        if state.get('source_error'):raise ValueError('보존 원본 읽기 실패')
        return fem.structural_displacement_source(reference)
    def request(key, function, accepted):
        result = function()
        if state['defer']: state['callbacks'].append(lambda: accepted(result))
        else: accepted(result)
    def submit(operation, arguments, target, on_done, owner):
        if state.get('submit_error'):
            on_done({'status': 'FAILED', 'error': {'message': '명시한 저장 실패'}})
            return {'queued': True}
        envelope = (fem.structural_displacement_source(arguments['draft']['source_reference'])
                    if operation.endswith(('_preview', '_apply')) else None)
        value = author.dispatch(fem, operation, arguments, target, source=envelope)
        on_done({'status': 'SUCCEEDED', 'result': value})
        return {'queued': True}
    connection = SimpleNamespace(QtWidgets=QtWidgets, QtCore=QtCore,
        client=SimpleNamespace(structural_displacement_sources=catalog,
            structural_displacement_source=source),
        request=request, submit_native=submit,
        open_structural_displacement_source=lambda ref: state.setdefault('opened', []).append(deepcopy(ref)),
        close_structural_transfer=lambda target: state.setdefault('closed', []).append(target.document_id))
    connection.structural_transfer_view_actions = lambda: list(view_actions)
    if offline:
        import threading
        from apps.desktop_pre.connection import Connection
        live = Connection.__new__(Connection)
        for key, value in vars(connection).items(): setattr(live, key, value)
        live.native_requests = {}; live.panels = {}
        live.owners = {owner.doc.Name: (owner, None, SimpleNamespace(stop=threading.Event(), registered=threading.Event()))}
        owner.generation = 0; owner.refresh = lambda: None
        def owner_dispatch(command):
            state.setdefault('local_operations', []).append(command['operation'])
            assert command['operation'] in ('pre.fem.displacement_read', 'pre.fem.displacement_save', 'pre.fem.displacement_remove')
            value = author.dispatch(fem, command['operation'], command['arguments'], command['target'])
            return dict(status='COMPLETED', command_id=command['command_id'], result=value)
        owner.dispatch = owner_dispatch
        live.submit_native = Connection.submit_native.__get__(live)
        connection = live
    monkeypatch.setattr(author, 'capture_selection', lambda f: deepcopy(draft['target']))
    panel = make_panel(connection, owner)
    return panel, author, fem, state, captured, draft


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def choose_source_and_boundary(panel, draft):
    panel.source.setCurrentIndex(1); panel._source_selected()
    panel.all_faces.click(); panel.use_selection.click()
    if draft.get('replace_condition_ids'):
        choose_replacement_rows(panel, draft['replace_condition_ids'])
    for key, field in panel.limits.items():
        field.setText(str(draft['definition'][key])); field.textEdited.emit(field.text())


def choose_replacement_rows(panel, identifiers, *, accept=True):
    failures = []
    def choose():
        dialog = QtWidgets.QApplication.activeModalWidget()
        try:
            assert dialog.objectName() == 'replacementConditionsDialog' and dialog.isVisible()
            table = dialog.findChild(QtWidgets.QTableWidget, 'replacementConditions')
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                item.setCheckState(QtCore.Qt.Checked if item.data(QtCore.Qt.UserRole) in identifiers else QtCore.Qt.Unchecked)
            buttons = dialog.findChild(QtWidgets.QDialogButtonBox)
            buttons.button(QtWidgets.QDialogButtonBox.Ok if accept else QtWidgets.QDialogButtonBox.Cancel).click()
        except BaseException as error:
            failures.append(error); dialog.reject()
    QtCore.QTimer.singleShot(0, choose)
    panel.choose_replacements.click()
    if failures: raise failures[0]


def test_explicit_source_selection_preview_cancel_and_apply_keep_native_zero_baseline(app, monkeypatch):
    panel, author, fem, state, captured, draft = panel_case(monkeypatch)
    try:
        assert state['source_reads'] == 0 and panel._static is None
        choose_source_and_boundary(panel, draft)
        panel.open_source.click()
        assert state['opened']==[draft['source_reference']]
        original = deepcopy(captured)
        panel.preview.click()
        assert panel.table.rowCount() == 34 and panel.apply.isEnabled()
        assert state['metadata'] == {} and state['transactions'] == 0
        panel.cancel.click()
        assert state['metadata'] == {} and not panel.apply.isEnabled()
        choose_source_and_boundary(panel, draft); panel.preview.click(); panel.apply.click()
        assert author.descriptor(fem)[0]['state'] == 'APPLIED'
        assert captured == original and len(captured['boundary_dofs']) == 102
        assert len(author.descriptor(fem)[0]['record']['accepted']['preview']['boundary_dofs']) == 102
        assert not panel.pending_changes()
    finally: panel.close(); panel.deleteLater(); app.processEvents()


def test_loaded_integer_typed_definition_and_cancel_do_not_rewrite_saved_recipe(app, monkeypatch):
    author, fem, state, _, draft = authoring_case(monkeypatch)
    draft['definition']['rotation'][0][0] = 1
    _author_preview_apply(author, fem, draft)
    saved = deepcopy(state['metadata'])
    panel, _, _, current, _, _ = panel_case(monkeypatch, saved)
    try:
        assert canonical_hash(panel.current_draft()) == canonical_hash(draft)
        assert type(panel.current_draft()['definition']['rotation'][0][0]) is int
        assert current['source_reads'] == 0 and not panel.pending_changes()
        assert '전역 좌표계' in panel.source_info.text() and '좌표 mm, 변위 mm' in panel.source_info.text()
        assert '하중 매개변수 1.0 [1] (초 아님)' in panel.source_info.text()
        field = panel.limits['distance_tolerance']; field.setText('1e'); field.textEdited.emit('1e')
        assert panel.pending_changes()
        panel.cancel.click()
        assert canonical_hash(panel.current_draft()) == canonical_hash(draft)
        assert current['metadata'] == saved and not panel.pending_changes()
    finally: panel.close(); panel.deleteLater(); app.processEvents()


def test_invalid_draft_can_save_but_cannot_reuse_old_accepted_preview_for_apply(app, monkeypatch):
    author, fem, state, _, draft = authoring_case(monkeypatch)
    _author_preview_apply(author, fem, draft); saved = deepcopy(state['metadata'])
    panel, author, fem, current, captured, _ = panel_case(monkeypatch, saved)
    try:
        field = panel.limits['distance_tolerance']; field.setText('1e'); field.textEdited.emit('1e')
        panel.save.click()
        row = author.descriptor(fem)[0]
        assert row['state'] == 'UNAPPLIED' and row['record']['draft']['definition']['distance_tolerance'] == '1e'
        assert row['record']['accepted'] == saved['displacement_transfers']['Analysis']['accepted']
        assert not panel.apply.isEnabled()
        assert '이전 적용값' in panel.summary.text() and '현재 초안에는 미적용' in panel.summary.text()
        with pytest.raises(ValueError): author.accepted_definition(fem, 'Analysis', captured)
    finally: panel.close(); panel.deleteLater(); app.processEvents()


def test_late_source_response_for_another_session_cannot_replace_current_controls(app, monkeypatch):
    panel, _, fem, state, _, _ = panel_case(monkeypatch)
    try:
        state['defer'] = True; panel.source.setCurrentIndex(1); panel._source_selected()
        assert panel._source is None
        fem.owner.session_id = 'Snew'
        state['callbacks'].pop()()
        assert panel._source is None and panel._static is None and panel.faces.count() == 0
        assert state['metadata'] == {}
    finally: panel.close(); panel.deleteLater(); app.processEvents()


def test_source_catalog_failure_has_a_visible_retry_without_manufactured_static(app, monkeypatch):
    panel, _, _, state, _, _ = panel_case(monkeypatch, catalog_error=True)
    try:
        assert panel._analysis_id == 'Analysis' and panel.refresh_sources.isEnabled()
        assert state['source_reads'] == 0 and panel._static is None
        state['catalog_error'] = False; panel.refresh_sources.click()
        assert panel.source.count() == 2 and state['source_reads'] == 0 and panel._static is None
    finally: panel.close(); panel.deleteLater(); app.processEvents()


def test_partial_numeric_and_nonfinite_text_remain_saveable_json_text():
    assert _number('1e') == '1e'
    assert _number('nan') == 'nan'
    assert _number('inf') == 'inf'
    assert _number('30', True) == 30


def test_replacements_start_empty_and_modal_cancel_never_changes_native_or_draft(app, monkeypatch):
    panel, _, _, state, captured, draft = panel_case(monkeypatch)
    try:
        assert 'replace_condition_ids' not in panel.current_draft()
        assert '교체 안 함' in panel.replacement_summary.text()
        panel.use_selection.click(); before = deepcopy(panel.current_draft())
        original = deepcopy(captured)
        choose_replacement_rows(panel, ['TransferBoundary'], accept=False)
        assert panel.current_draft() == before and captured == original
        assert state['metadata'] == {} and state['transactions'] == 0
        choose_replacement_rows(panel, ['TransferBoundary'])
        assert panel.current_draft()['replace_condition_ids'] == ['TransferBoundary']
        assert '기존 지지면' in panel.replacement_summary.text()
        assert '0 변위' not in panel.scope.text()
        panel.cancel.click()
        assert 'replace_condition_ids' not in panel.current_draft()
        assert state['metadata'] == {} and captured == original
    finally: panel.close(); panel.deleteLater(); app.processEvents()


def test_unselected_overlap_is_rejected_then_explicit_choice_recovers_same_draft(app, monkeypatch):
    panel, _, _, state, captured, draft = panel_case(monkeypatch)
    try:
        choose_source_and_boundary(panel, draft)
        choose_replacement_rows(panel, [])
        original = deepcopy(captured); before = deepcopy(panel.current_draft())
        panel.preview.click()
        assert panel._preview is None and not panel.apply.isEnabled()
        assert panel.message.text() and panel.current_draft() == before
        assert state['metadata'] == {} and captured == original
        choose_replacement_rows(panel, ['TransferBoundary'])
        panel.preview.click()
        assert panel.apply.isEnabled() and panel.table.rowCount() == 34
        panel.apply.click()
        assert state['metadata']['displacement_transfers']['Analysis']['draft']['replace_condition_ids'] == ['TransferBoundary']
        assert captured == original
    finally: panel.close(); panel.deleteLater(); app.processEvents()


@pytest.mark.parametrize('identifiers', [[], ['OldCondition'], ['OldCondition', 'TransferBoundary']])
def test_loaded_optional_replacements_preserve_unknown_ids_order_and_nochange(app, monkeypatch, identifiers):
    panel, _, _, state, _, _ = panel_case(monkeypatch)
    try:
        panel.use_selection.click()
        draft = panel.current_draft(); draft['replace_condition_ids'] = deepcopy(identifiers)
        draft['definition']['distance_tolerance'] = '1e'
        panel._load(draft); panel._enabled()
        before = deepcopy(panel.current_draft())
        choose_replacement_rows(panel, identifiers)
        assert panel.current_draft() == before and not panel.pending_changes()
        assert panel.limits['distance_tolerance'].text() == '1e'
        assert state['metadata'] == {} and state['transactions'] == 0
        panel.components[0].click(); panel.cancel.click()
        assert panel.current_draft() == before
    finally: panel.close(); panel.deleteLater(); app.processEvents()


def test_saved_malformed_replacement_draft_is_not_silently_normalized(app, monkeypatch):
    panel, _, _, state, _, _ = panel_case(monkeypatch)
    try:
        draft = panel.current_draft(); draft['replace_condition_ids'] = [['unsupported']]
        panel._load(draft); panel._enabled()
        assert panel.current_draft() == draft and not panel.choose_replacements.isEnabled()
        assert state['metadata'] == {} and not panel.pending_changes()
    finally: panel.close(); panel.deleteLater(); app.processEvents()


def test_static_frames_are_distinct_explicit_choices_without_source_or_array_read(app, monkeypatch):
    panel, _, _, state, _, draft = panel_case(monkeypatch)
    try:
        ref = deepcopy(draft['source_reference'])
        rows = []
        for frame, step, increment, load in [('frame-a', 2, 3, .25), ('frame-b', 2, 7, .75)]:
            rows.append({'label': '사용자 지붕 / 계산 2', 'reference': dict(ref, frame_id=frame),
                         'static': dict(step=step, increment=increment, load_parameter=load)})
        state['catalog_rows'] = rows
        assert panel.refresh_context()
        assert '단계 2, 증분 3, λ 0.25' in panel.source.itemText(1)
        assert '단계 2, 증분 7, λ 0.75' in panel.source.itemText(2)
        assert panel.source.currentData() is None and state['source_reads'] == 0
        panel.source.setCurrentIndex(2)
        assert panel.current_draft()['source_reference'] == rows[1]['reference']
        assert panel._static is None and state['source_reads'] == 0
        assert '물리 시간이 아닙니다' in panel.source.itemData(2, QtCore.Qt.ToolTipRole)
    finally: panel.close(); panel.deleteLater(); app.processEvents()


def test_legacy_reference_keeps_its_own_label_when_frame_catalog_changes(app, monkeypatch):
    panel, _, _, state, _, draft = panel_case(monkeypatch)
    try:
        panel.source.setCurrentIndex(1); previous_label = panel.source.currentText()
        legacy_reference = deepcopy(panel.source.currentData())
        panel.save.click()
        before = deepcopy(panel.current_draft())
        state['catalog_rows'] = [{'reference': dict(legacy_reference, frame_id='new-frame'),
                                 'label': '다른 새 결과',
                                 'static': dict(step=3, increment=9, load_parameter=.7)}]
        assert panel.refresh_context()
        assert panel.source.currentData() == legacy_reference
        assert panel.source.currentText() == previous_label
        assert panel.current_draft() == before and state['source_reads'] == 0
        assert '다른 새 결과' in panel.source.itemText(1)
    finally: panel.close(); panel.deleteLater(); app.processEvents()


@pytest.mark.parametrize('procedure,steps,geometry,expected', [
    ('static', [{}], 'linear', '정적 구조 해석 / CalculiX'),
    ('dynamic', [{}], 'linear', '동적 구조 해석 / CalculiX (가져오기 미지원)'),
    ('mixed', [{'procedure': 'static'}, {'procedure': 'dynamic'}], 'linear', '정적/동적 혼합 구조 해석'),
    ('static', [{}, {}], 'linear', '정적 구조 해석, 여러 단계'),
    ('static', [{}], 'nonlinear', '비선형 정적 구조 해석'),
    ('static', [{'procedure': 'dynamic'}], 'linear', '확인 필요'),
])
def test_analysis_name_never_substitutes_for_native_procedure(app, monkeypatch, procedure, steps, geometry, expected):
    panel, _, fem, state, _, _ = panel_case(monkeypatch)
    try:
        analysis = fem.owner._object('Analysis'); analysis.Label = '내 열전달 연구 이름'
        fem.owner._object('Solver').GeometricalNonlinearity = geometry
        state['metadata']['contact_programs'] = [{'analysis_id': 'Analysis',
            'draft': {'procedure': procedure, 'steps': deepcopy(steps)}}]
        before = deepcopy(state['metadata']); draft = deepcopy(panel.current_draft())
        panel._populate_analyses()
        assert panel.analysis.currentText() == analysis.Label
        assert expected in panel.analysis_kind.text()
        assert '열전달' not in panel.analysis_kind.text()
        assert state['metadata'] == before and panel.current_draft() == draft
        assert state['source_reads'] == 0
    finally: panel.close(); panel.deleteLater(); app.processEvents()


def test_dynamic_program_wins_over_static_solver_and_unreadable_metadata_stays_unknown(app, monkeypatch):
    panel, _, fem, state, _, _ = panel_case(monkeypatch)
    try:
        state['metadata']['dynamic_programs'] = {'Analysis': {'draft': {'program': {
            'procedure': 'dynamic', 'steps': [{}]}}}}
        panel._enabled()
        assert '동적 구조 해석' in panel.analysis_kind.text() and '미지원' in panel.analysis_kind.text()
        state['metadata']['dynamic_programs'] = {'Analysis': {'draft': {}}}
        panel._enabled()
        assert panel.analysis_kind.text() == '종류: 해석 설정 확인 필요'
        assert '정적 구조' not in panel.analysis_kind.text()
        state['metadata'] = {}
        fem.owner._object('Solver').AnalysisType = 'frequency'; panel._enabled()
        assert '고유진동 해석' in panel.analysis_kind.text() and '미지원' in panel.analysis_kind.text()
        del fem.owner._object('Solver').AnalysisType; panel._enabled()
        assert panel.analysis_kind.text() == '종류: 해석 설정 확인 필요'
        assert state['source_reads'] == 0 and state['transactions'] == 0
    finally: panel.close(); panel.deleteLater(); app.processEvents()


def test_failed_reread_does_not_rewrite_a_saved_definition_or_leave_old_arrays_active(app,monkeypatch):
    author,fem,state,_,draft=authoring_case(monkeypatch)
    _author_preview_apply(author,fem,draft);saved=deepcopy(state['metadata'])
    panel,_,_,current,_,_=panel_case(monkeypatch,saved)
    try:
        current['source_error']=True;panel.read_source.click()
        assert canonical_hash(panel.current_draft())==canonical_hash(draft)
        assert not panel.pending_changes() and panel._source is None and not panel.all_faces.isEnabled()
        assert '확인하지 못했습니다' in panel.source_info.text() and current['metadata']==saved
        current['source_error']=False;panel.read_source.click()
        assert panel._source is not None and not panel.pending_changes()
    finally:panel.close();panel.deleteLater();app.processEvents()


def test_failed_reread_and_retry_preserve_unsaved_explicit_source_faces(app,monkeypatch):
    panel,_,_,state,_,draft=panel_case(monkeypatch)
    try:
        choose_source_and_boundary(panel,draft);before=deepcopy(panel.current_draft())
        state['source_error']=True;panel.read_source.click()
        assert panel.current_draft()==before and panel._source is None
        state['source_error']=False;panel.read_source.click()
        assert panel.current_draft()==before and panel._source is not None
    finally:panel.close();panel.deleteLater();app.processEvents()


def test_clean_refresh_discovers_a_native_analysis_and_its_added_solver(app,monkeypatch):
    panel,_,fem,_,_,_=panel_case(monkeypatch,empty_analysis=True)
    try:
        assert panel.analysis.count()==1 and panel._analysis_id is None
        analysis=fem.owner._object('Analysis');fem.owner.doc.Objects.append(analysis)
        panel.refresh_sources.click()
        assert panel._analysis_id=='Analysis' and panel.solver.currentData()=='Solver'
        analysis.Group.append(SimpleNamespace(Name='Solver2',Label='다른 기존 솔버',TypeId='Fem::SolverCcxTools'))
        assert panel.refresh_context() and panel.solver.count()==2
        assert panel._analysis_id=='Analysis' and not panel.pending_changes()
    finally:panel.close();panel.deleteLater();app.processEvents()


def test_refresh_never_replaces_dirty_or_busy_native_authoring_controls(app,monkeypatch):
    panel,_,fem,state,_,_=panel_case(monkeypatch)
    try:
        field=panel.limits['distance_tolerance'];field.setText('1e');field.textEdited.emit('1e')
        before=deepcopy(panel.current_draft());reads=state['source_reads']
        fem.owner._object('Analysis').Group.append(SimpleNamespace(Name='Solver2',Label='새 솔버',TypeId='Fem::SolverCcxTools'))
        panel.refresh_sources.click()
        assert panel.current_draft()==before and panel.solver.count()==1 and state['source_reads']==reads
        panel.cancel.click();panel._busy=True
        assert not panel.refresh_context() and panel.solver.count()==1
        panel._busy=False
        assert panel.refresh_context() and panel.solver.count()==2
    finally:panel.close();panel.deleteLater();app.processEvents()


def test_task_steps_keep_source_and_target_context_and_primary_action_visible(app, monkeypatch):
    """Injected-owner layout check; it is not a native FreeCAD workflow receipt."""
    from apps.research.appearance import apply_appearance
    apply_appearance(app)
    panel, _, _, state, _, draft = panel_case(monkeypatch)
    try:
        panel.resize(420, 650); panel.show(); app.processEvents()
        assert [panel.steps.tabText(i) for i in range(3)] == ['원본 결과', '적용할 면', '변위 확인']
        assert panel.steps.currentIndex() == 0 and panel.next_step.isVisible()
        assert not panel.next_step.isEnabled() and not panel.apply.isVisible()
        choose_source_and_boundary(panel, draft)
        assert panel.next_step.isEnabled()
        panel.next_step.click(); assert panel.steps.currentIndex() == 1
        assert '원본:' in panel.task_state.text() and '적용면:' in panel.task_state.text()
        assert panel.use_selection.isVisible() and panel.highlight.isVisible()
        assert not panel.advanced.isVisible() and not panel.faces.isVisible()
        for width in (420, 360):
            panel.resize(width, 650); app.processEvents()
            assert panel.height() <= 650
            assert panel.target_info.height() - 20 >= 2 * panel.target_info.fontMetrics().lineSpacing()
            target_bottom = panel.target_info.mapTo(panel, panel.target_info.rect().bottomRight()).y()
            assert target_bottom < panel.components[0].mapTo(panel, QtCore.QPoint()).y()
            assert panel.target_scroll.viewport().rect().contains(
                panel.target_info.mapTo(panel.target_scroll.viewport(), panel.target_info.rect().bottomRight()))
            assert panel.choose_replacements.mapTo(panel, panel.choose_replacements.rect().bottomRight()).y() < panel.preview.mapTo(panel, QtCore.QPoint()).y()
            assert panel.close_button.mapTo(panel, panel.close_button.rect().bottomRight()).y() < panel.height()
        from PySide6.QtTest import QTest
        panel.activateWindow(); panel.raise_(); panel.receiver_frame.setFocus()
        QTest.qWait(20); assert panel.receiver_frame.hasFocus()
        QTest.keyClick(panel.receiver_frame, QtCore.Qt.Key_Tab)
        app.processEvents()
        assert panel.advanced_button.hasFocus()
        assert panel.target_scroll.viewport().rect().contains(
            panel.advanced_button.mapTo(panel.target_scroll.viewport(), panel.advanced_button.rect().bottomRight()))
        before = deepcopy(panel.current_draft()); panel.preview.click()
        assert panel.steps.currentIndex() == 2 and panel.apply.isVisible() and panel.apply.isEnabled()
        assert panel.table.rowCount() == 34 and all(panel.table.isColumnHidden(c) for c in (1, 2, 3))
        assert not any(panel.table.isColumnHidden(c) for c in (0, 4, 5, 6, 7))
        assert '102' not in panel.summary.text() and '34' in panel.summary.text()
        for width in (420, 360):
            panel.resize(width, 650); app.processEvents()
            assert panel.width() <= 430
            assert panel.apply.mapTo(panel, QtCore.QPoint(0, 0)).x() >= 0
            assert panel.apply.mapTo(panel, panel.apply.rect().bottomRight()).x() < panel.width()
            assert panel.current_draft() == before
            directory = os.environ.get('CAELAB_TRANSFER_TASK_FIXTURE_RENDERS')
            if directory:
                from pathlib import Path
                folder = Path(directory); folder.mkdir(parents=True, exist_ok=True)
                for page in range(3):
                    panel.steps.setCurrentIndex(page); app.processEvents()
                    assert panel.grab().save(str(folder / ('qt-fixture-page' + str(page) + '-' + str(width) + '.png')))
        assert state['metadata'] == {} and state['transactions'] == 0
    finally: panel.close(); panel.deleteLater(); app.processEvents()


def test_mapping_settings_cancel_restores_exact_text_and_confirm_keeps_invalid_draft(app, monkeypatch):
    panel, _, _, state, _, draft = panel_case(monkeypatch)
    failures = []
    try:
        choose_source_and_boundary(panel, draft); panel.preview.click()
        before = deepcopy(panel.current_draft()); previous = deepcopy(panel._preview)
        def cancel_settings():
            try:
                assert panel.settings_dialog.isVisible()
                field = panel.limits['distance_tolerance']; field.setText('1e'); field.textEdited.emit('1e')
                panel.settings_dialog.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Cancel).click()
            except BaseException as error:
                failures.append(error); panel.settings_dialog.reject()
        QtCore.QTimer.singleShot(20, cancel_settings); panel.advanced_button.click()
        assert not failures and panel.current_draft() == before and panel._preview == previous
        assert panel.apply.isEnabled()
        def confirm_settings():
            field = panel.limits['distance_tolerance']; field.setText('1e'); field.textEdited.emit('1e')
            panel.settings_dialog.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Ok).click()
        QtCore.QTimer.singleShot(20, confirm_settings); panel.advanced_button.click()
        assert panel.current_draft()['definition']['distance_tolerance'] == '1e'
        assert not panel.apply.isEnabled() and state['metadata'] == {} and state['transactions'] == 0
    finally: panel.close(); panel.deleteLater(); app.processEvents()


@pytest.mark.parametrize('choice', ['continue', 'discard', 'save', 'save_fail', 'busy'])
def test_task_close_keeps_pending_input_until_explicit_discard_or_acknowledged_save(app, monkeypatch, choice):
    panel, author, fem, state, captured, draft = panel_case(monkeypatch)
    try:
        panel.show(); choose_source_and_boundary(panel, draft)
        field = panel.limits['distance_tolerance']; field.setText('1e'); field.textEdited.emit('1e')
        before = deepcopy(panel.current_draft()); baseline = deepcopy(captured)
        if choice == 'busy':
            panel._busy = True; assert panel.request_close() is False
            assert panel.current_draft() == before and not state.get('closed')
            return
        state['submit_error'] = choice == 'save_fail'
        label = {'continue': '계속 편집', 'discard': '편집 취소 후 닫기',
                 'save': '초안 저장 후 닫기', 'save_fail': '초안 저장 후 닫기'}[choice]
        def respond():
            box = next(w for w in app.topLevelWidgets() if isinstance(w, QtWidgets.QMessageBox) and w.isVisible())
            next(b for b in box.buttons() if b.text() == label).click()
        QtCore.QTimer.singleShot(20, respond); panel.request_close()
        if choice in ('continue', 'save_fail'):
            assert panel.current_draft() == before and not state.get('closed') and state['metadata'] == {}
        else:
            assert state['closed'] == ['Preceiver'] and not panel.pending_changes()
            if choice == 'save':
                saved = author.descriptor(fem)[0]
                assert saved['state'] == 'UNAPPLIED' and saved['record']['draft'] == before
            else: assert state['metadata'] == {}
        assert captured == baseline
    finally: panel._busy = False; panel.close(); panel.deleteLater(); app.processEvents()


def test_native_model_visibility_action_is_reused_without_a_second_toggle(app, monkeypatch):
    from PySide6.QtGui import QAction
    action = QAction('모형 트리 보기'); action.setCheckable(True); action.setChecked(True)
    toggled = []; action.toggled.connect(toggled.append)
    panel, _, _, state, _, _ = panel_case(monkeypatch, view_actions=[('모형 트리 보기', action)])
    try:
        assert action in panel.more_button.menu().actions()
        action.trigger()
        assert toggled == [False] and not action.isChecked()
        assert state['metadata'] == {} and state['transactions'] == 0
    finally: panel.close(); panel.deleteLater(); app.processEvents()


def test_offline_raw_save_and_close_use_actual_connection_without_preview_or_apply(app, monkeypatch):
    """Real Connection routing with the existing domain-owner seam; no broker or native app."""
    panel, author, fem, state, captured, _ = panel_case(monkeypatch, offline=True)
    try:
        panel.show(); app.processEvents()
        source = deepcopy(state['source']); baseline = deepcopy(captured)
        field = panel.limits['distance_tolerance']; field.setText('1e'); field.textEdited.emit('1e')
        raw = deepcopy(panel.current_draft())
        for operation in ('preview', 'apply'):
            panel._operation(operation)
            assert not panel._busy and panel.current_draft() == raw and not panel.apply.isEnabled()
        assert state['local_operations'] == ['pre.fem.displacement_read']
        def save_and_close():
            dialog = next(w for w in app.topLevelWidgets() if isinstance(w, QtWidgets.QMessageBox) and w.isVisible())
            next(b for b in dialog.buttons() if b.text() == '초안 저장 후 닫기').click()
        QtCore.QTimer.singleShot(20, save_and_close); panel.request_close()
        saved = author.descriptor(fem)[0]
        assert state['local_operations'] == ['pre.fem.displacement_read', 'pre.fem.displacement_save']
        assert saved['state'] == 'UNAPPLIED' and saved['record']['draft'] == raw
        assert saved['record']['draft']['definition']['distance_tolerance'] == '1e'
        assert not panel.pending_changes() and state['closed'] == ['Preceiver']
        assert captured == baseline and state['source'] == source and state['source_reads'] == 0
    finally: panel.close(); panel.deleteLater(); app.processEvents()
