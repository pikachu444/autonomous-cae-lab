"""Small host adapters; all writes use the existing local-draft/owner contracts."""
from copy import deepcopy
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog, QMessageBox, QDialogButtonBox
from caelab.storage import canonical_hash
from caelab.finite_measure_input import mapping, recipe, verify_import


def _token(window):
    doc=window.document or {}
    return (doc.get('id'),doc.get('session_id'),doc.get('generation'),window._source_id,
            canonical_hash(window.edited_draft(commit=False)))


def _ready(window):
    return bool(window.document and (not window._busy or getattr(window,'_accepting',False)) and not window.conflict and not window._view_error)


def install_data_actions(window, menu):
    for title,method in [('유한변형 시험 설정…',edit_columns),('응력과 변형률 변환 추가…',stage_recipe)]:
        action=QAction(title,window);action.triggered.connect(lambda checked=False,fn=method:fn(window));menu.addAction(action)


def edit_columns(window):
    if not _ready(window):return False
    preview=(window._preview or {}).get('table_preview')
    if not preview or not window._preview_key or window._preview_key[:2]!=(window.document['id'],window._source_id):
        window.message.setText('현재 CSV의 원본 미리보기를 먼저 읽으세요.');return False
    from .finite_measure_dialog import FiniteColumnsDialog
    before=window.edited_draft();token=_token(window)
    pending=getattr(window,'_finite_pending_config',None)
    config=pending['config'] if pending and pending['owner']==(window.document['id'],window._source_id) else before.get('finite_measure')
    dialog=FiniteColumnsDialog(preview,config,window)
    if dialog.exec()!=QDialog.DialogCode.Accepted:return False
    if not _ready(window) or _token(window)!=token:
        # Retain the exact user draft for an explicit retry, never overwrite a new target.
        window._finite_pending_config={'config':deepcopy(dialog.result_config),'owner':(token[0],token[3])}
        window.message.setText('현재 자료가 바뀌어 적용하지 않았습니다. 편집값은 창의 재시도 초안으로 보존했습니다.');return False
    config=dialog.result_config
    if before['mapping']['columns'] and QMessageBox.question(window,'시험 열 반영',
        '선택한 시험 열로 가져오기 설정을 바꿉니다. 원자료와 보존 결과는 변경하지 않습니다. 계속할까요?',
        QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return False
    # A second modal may have processed late owner reads. Recheck before apply.
    if not _ready(window) or _token(window)!=token:
        window._finite_pending_config={'config':deepcopy(config),'owner':(token[0],token[3])};window.message.setText('현재 자료가 바뀌어 반영하지 않았습니다.');return False
    window._finite_pending_config=None
    before['finite_measure']=deepcopy(config)
    before['mapping']=mapping(config,delimiter=preview.get('delimiter',','),skip_header=preview.get('skip_rows',1))
    if before.get('processing'):
        try:before['processing']['recipe']=recipe(config,before['processing']['recipe'])
        except (ValueError,TypeError,KeyError):
            pass  # The raw draft is saveable; current-preview consistency blocks old definitions.
    window._show_document({**window.document,'draft':before});window.local_dirty=True;window._update_actions()
    window.message.setText('시험 설정을 초안에 반영했습니다. 설정 적용 → 가져오기 후 편집 메뉴에서 응력과 변형률 변환을 추가하세요.');return True


def stage_recipe(window):
    if not _ready(window):return False
    if window.local_dirty:
        window.message.setText('설정 적용을 누르고 원본을 가져온 뒤 변환을 추가하세요.');return False
    try:
        source=deepcopy(window.selected_source());draft=window.edited_draft();config=deepcopy(draft['finite_measure'])
        proposed=recipe(config,draft.get('processing',{}).get('recipe'));token=_token(window)
    except (ValueError,KeyError,TypeError) as error:
        window.message.setText('편집 메뉴에서 유한변형 시험 설정을 먼저 여세요. '+str(error));return False
    def received(result):
        if not _ready(window) or _token(window)!=token:
            window.message.setText('읽는 동안 현재 자료가 바뀌었습니다. 현재 문서에서 다시 연결하세요.');return
        try:verify_import(config,result,delimiter=draft['mapping']['delimiter'],skip_header=draft['mapping']['skip_header'])
        except (ValueError,TypeError,KeyError) as error:window.message.setText(str(error));return
        draft['processing']={'source':{k:source[k] for k in ('document_id','job_id','input_revision','input_sha256')},'recipe':proposed}
        window._working_draft=deepcopy(draft);window._edited()
        window.message.setText('응력과 변형률 변환을 처리 단계에 추가했습니다. 설정 적용 → 처리 미리보기에서 원행과 무효 이유를 확인한 뒤 처리 결과 보존을 누르세요.')
    return window._call(lambda:window.client.document_result(source['document_id'],source['job_id']),received)


def add_audit_button(dialog,buttons):
    result=dialog.processing_result
    if not any(ch.get('metadata',{}).get('extensions',{}).get('finite_measure') for ch in result.get('channels',{}).values()):return
    from .finite_measure_dialog import FiniteAuditDialog
    button=buttons.addButton('변환값과 원행 확인…',QDialogButtonBox.ButtonRole.ActionRole)
    button.clicked.connect(lambda:FiniteAuditDialog(result,dialog).exec())


def install_material_action(window,menu):
    action=QAction('공칭응력을 진응력으로 보기…',window);menu.addAction(action)
    def show():
        jobs=window._selected_jobs()
        if len(jobs)!=1 or jobs[0] not in window._result_cache:
            window.message.setText('보존 결과 하나를 선택하고 결과 읽기를 완료하세요. 새 계산은 시작하지 않습니다.');return
        from .finite_measure_dialog import FinitePredictionDialog
        FinitePredictionDialog(window._result_cache[jobs[0]],window).exec()
    action.triggered.connect(show)


def copy_trial_extensions(experiment,value):
    """Preserve unrelated typed extensions; only replace this explicit selection."""
    extensions=deepcopy(experiment.get('extensions',{}))
    extensions.pop('finite_measure',None)
    extensions.update(deepcopy(value.get('extensions',{})))
    if extensions:experiment['extensions']=extensions
    else:experiment.pop('extensions',None)
