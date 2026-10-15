"""Small presenter over the existing native launch/save and portable APIs.

Qt is imported only by Research confirmation dialogs. Native FreeCAD/ParaView
menus bind their own confirmation/launcher callbacks; their Qt is never mixed
with the Research runtime. This class owns no document, job or file authority.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import uuid


def _id():
    return 'C' + uuid.uuid4().hex


def _same(value, expected, message):
    if value != expected:
        raise ValueError(message)


def _summary(status, **values):
    return dict(status=status, **values)


def _confirm_first_save():
    from PySide6.QtWidgets import QMessageBox
    dialog = QMessageBox(QMessageBox.Icon.Question, '프로젝트 저장', '새 작업 사본으로 저장할까요?')
    save = dialog.addButton('새 작업 사본으로 저장', QMessageBox.ButtonRole.AcceptRole)
    cancel = dialog.addButton('취소', QMessageBox.ButtonRole.RejectRole)
    dialog.setDefaultButton(cancel)
    try:
        dialog.exec()
        return dialog.clickedButton() is save
    finally:
        dialog.deleteLater()


class NativeProjectActions:
    """One presenter's same-command recovery, using existing trusted adapters.

    ``local_context`` is N0's existing NativeOnlyContext, not a Client stand-in.
    The native menu supplies its current installation, launcher, real owner Save
    and native confirmation callbacks. It never imports another Qt binding.
    """
    def __init__(self, client=None, *, local_context=None, launch_context=None,
                 launcher=None, native_save=None, confirm_first_save=None,
                 review_copy=None, choose_destination=None):
        if (client is None) == (local_context is None):
            raise ValueError('현재 연구 연결 또는 독립 파일 연결 하나를 선택하세요.')
        self.client, self.local = client, local_context
        self.launch_context = launch_context
        self.launcher, self.native_save = launcher, native_save
        self.confirm_first_save = confirm_first_save
        self.review_copy, self.choose_destination = review_copy, choose_destination
        self._opens, self._saves = {}, {}
        self._copy = None

    def _view(self, open_id):
        if self.client is not None:
            return self.client.native_project_open_ticket(open_id)
        from caelab.portable_project_native import open_ticket_view
        return open_ticket_view(self.local, open_id)

    def open(self, request, *, command_id):
        request = deepcopy(request)
        if self.client is None and self.launcher is None and self.launch_context is None:
            raise ValueError('현재 native 프로그램의 기존 열기 동작을 연결하세요.')
        prior = self._opens.get(command_id)
        if prior is not None:
            _same(prior['request'], request, '같은 열기 요청의 저장본이나 대상이 변경되었습니다.')
            return self.check_open(prior['open_id'])
        if self.client is not None:
            prepared = self.client.native_project_prepare_open(request, command_id=command_id)
            open_id = prepared['open_id']
            if prepared.get('reuse_existing'):
                _same(prepared['request_reference'], request['reference'], '현재 작업 사본의 저장 기준이 다릅니다.')
                _same(prepared['target_id'], request['target_id'], '현재 작업 창이 선택한 대상과 다릅니다.')
                stamp = prepared['expected_stamp']
                activate_id = 'C' + sha256((command_id + ':activate').encode()).hexdigest()[:40]
                command = self.client.document_command(prepared['owner_document_id'], 'document.activate', {},
                    session_id=stamp['session_id'], expected_generation=stamp['generation'], command_id=activate_id)
                self._opens[command_id] = {'request': request, 'open_id': open_id}
                return {**prepared, 'activation_state': command.get('state')}
            if prepared['status'] == 'OPEN_UNCONFIRMED':
                return prepared
            view = self._view(open_id)
        else:
            from caelab.portable_project_native import prepare_open
            ticket = prepare_open(self.local, request, command_id=command_id)
            open_id = ticket.binding.open_id
            view = self._view(open_id)
        _same(view['reference'], request['reference'], '열 준비한 저장본이 선택한 원본과 다릅니다.')
        if view['status'] == 'PREPARED':
            _same(view['target_id'], request['target_id'], '열 준비한 작업 대상이 선택과 다릅니다.')
        self._opens[command_id] = {'request': request, 'open_id': open_id}
        if view['status'] in {'OPENED', 'PARTIAL_OPEN', 'OPEN_UNCONFIRMED', 'LAUNCHING', 'CLOSED'}:
            return self.check_open(open_id)
        if view['status'] != 'PREPARED':
            return view
        from caelab.portable_project_native import resume_open_ticket, claim_open_launch
        context, ticket = (resume_open_ticket(view['launch_config']) if self.client is not None else (self.local, ticket))
        claim = claim_open_launch(context, open_id)
        if claim.get('status') != 'LAUNCHING':
            return self.check_open(open_id)
        try:
            launch = self._launch(ticket)
        except Exception as error:
            return _summary('OPEN_UNCONFIRMED', open_id=open_id,
                message='열기 결과를 확인하지 못했습니다. 같은 요청으로 상태를 확인하세요.', diagnostic=str(error))
        checked = self.check_open(open_id)
        checked['launch'] = deepcopy(launch)
        return checked

    def _launch(self, ticket):
        if self.launcher is not None:
            return self.launcher(ticket)
        from .desktop import _pre, _post
        kind = ticket.verified_input.snapshot['native_kind']
        args = SimpleNamespace(project=None, input_path=None, input_id=None, job_id=None,
            research_source=None, measurement_result=None, curve_origin=None, report_image=None,
            executable=None, output=None, prepare_only=False, source=None, assembly=None,
            source_label=None, gmsh=None)
        call = _pre if kind == 'pre' else _post
        return call(self.client, args, _native_project_ticket=ticket,
                    _local_context=self.launch_context if self.client is None else None)

    def check_open(self, open_id):
        view = self._view(open_id)
        if view['status'] == 'CLOSED':
            return {**view, 'message': '열었던 창을 닫았습니다. 다시 열려면 열기 동작을 새로 선택하세요.'}
        if view['status'] in {'OPENED', 'PARTIAL_OPEN'}:
            return view
        return {**view, 'status': 'OPEN_UNCONFIRMED' if view['status'] == 'OPEN_UNCONFIRMED' else 'OPEN_PENDING',
            'message': '프로그램에서 저장본을 여는 중입니다. 실제 열림 확인이 필요합니다.'}

    def save(self, open_id, *, expected_stamp, expected_head, command_id):
        request = dict(open_id=open_id, expected_stamp=deepcopy(expected_stamp), expected_head=deepcopy(expected_head))
        pending = self._saves.get(command_id)
        if pending is not None:
            _same(pending['request'], request, '저장 확인 중 원 문서나 저장 기준이 변경되었습니다.')
            return self.check_save(command_id)
        view = self._view(open_id)
        if view['status'] not in {'OPENED', 'PARTIAL_OPEN'}:
            return _summary('OPEN_UNCONFIRMED', open_id=open_id,
                message='실제로 열린 문서를 확인한 뒤 저장하세요.')
        _same(expected_stamp['document_id'], view['owner_document_id'], '현재 저장 문서가 열린 작업과 다릅니다.')
        if view['target_id'] is None:
            if self.client is None and self.confirm_first_save is None:
                raise ValueError('현재 native 메뉴의 첫 저장 확인을 연결하세요.')
            confirm = self.confirm_first_save or _confirm_first_save
            if not confirm():
                return _summary('CANCELLED', open_id=open_id, message='저장을 취소했습니다. 현재 편집은 유지됩니다.')
        if self.client is not None:
            prepared = self.client.native_project_prepare_save(open_id, expected_stamp=expected_stamp,
                expected_head=expected_head, command_id=command_id)
        else:
            from caelab.native_project_inputs import prepare_target_save
            reservation = prepare_target_save(self.local, open_id, expected_stamp=expected_stamp,
                expected_head=expected_head, command_id=command_id)
            prepared = {name: deepcopy(getattr(reservation, name)) for name in
                ('save_id', 'save_command_id', 'open_id', 'owner_document_id', 'target_id', 'expected_head')}
        pending = {'request': request, 'prepared': prepared, 'submitted': False,
            'publication_command': 'C' + sha256((command_id + ':head').encode()).hexdigest()[:40]}
        if self.client is None:
            pending['reservation'] = reservation
        self._saves[command_id] = pending
        return self.check_save(command_id)

    def check_save(self, command_id):
        pending = self._saves[command_id]
        prepared, request = pending['prepared'], pending['request']
        if pending.get('terminal') is not None:
            return deepcopy(pending['terminal'])
        if self.client is None:
            if pending.get('witness') is None:
                if pending['submitted']:
                    return _summary('SAVE_UNCONFIRMED', message='실제 저장 완료를 먼저 확인하세요.')
                if not callable(self.native_save):
                    raise ValueError('현재 native 문서의 기존 저장 동작을 연결하세요.')
                pending['submitted'] = True
                pending['witness'] = self.native_save(pending['reservation'])
        else:
            if not pending['submitted']:
                # Mark before submission: loss of the reply is not permission to
                # call Save again. Recovery below uses the existing broker ID.
                pending['submitted'] = True
                try:
                    command = self.client.document_command(prepared['owner_document_id'], 'document.save', {},
                        session_id=request['expected_stamp']['session_id'],
                        expected_generation=request['expected_stamp']['generation'], command_id=prepared['save_command_id'])
                except Exception as error:
                    return _summary('SAVE_UNCONFIRMED', save_command_id=prepared['save_command_id'], diagnostic=str(error),
                        message='저장 결과를 확인하지 못했습니다. 같은 요청의 완료 상태를 다시 확인하세요.')
            else:
                try:
                    command = self.client.command_status(prepared['save_command_id'])
                except Exception as error:
                    return _summary('SAVE_UNCONFIRMED', save_command_id=prepared['save_command_id'], diagnostic=str(error),
                        message='저장 완료를 확인할 수 없습니다. 같은 요청의 상태를 다시 확인하세요.')
            state = command.get('state')
            if state in {'FAILED', 'CANCELLED'}:
                pending['terminal'] = _summary(state, save_command_id=prepared['save_command_id'],
                    message='저장을 완료하지 못했습니다. 현재 편집은 유지됩니다. 입력을 확인한 뒤 새로 저장하세요.',
                    diagnostic=command.get('error') or command.get('outcome'))
                return deepcopy(pending['terminal'])
            if state != 'SUCCEEDED':
                return _summary('SAVE_UNCONFIRMED' if state == 'INTERRUPTED' else 'SAVE_PENDING',
                    save_command_id=prepared['save_command_id'], message='저장 완료 확인이 필요합니다.')
        try:
            if self.client is not None:
                return self.client.native_project_save_head(prepared['target_id'], prepared['save_command_id'],
                    expected_head=prepared['expected_head'], command_id=pending['publication_command'], open_id=prepared['open_id'])
            from caelab.native_project_inputs import publish_head
            return publish_head(self.local, prepared['target_id'], pending['witness'],
                expected_head=prepared['expected_head'], command_id=pending['publication_command'],
                _target_save=pending['reservation'])
        except Exception as error:
            return _summary('SAVE_PUBLISHED_HEAD_PENDING', save_command_id=prepared['save_command_id'],
                target_id=prepared['target_id'], message='파일은 저장됐습니다. 연결 기록 갱신을 다시 확인하세요.', diagnostic=str(error))


def _presenter(value):
    if isinstance(value, NativeProjectActions):
        return value
    previous = getattr(value, '_native_project_actions', None)
    if previous is None:
        from caelab.native_project_inputs import NativeOnlyContext
        previous = (NativeProjectActions(local_context=value) if type(value) is NativeOnlyContext
                    else NativeProjectActions(value))
        value._native_project_actions = previous
    return previous


def open_native_project(client_or_local, request, *, command_id):
    """Prepare, launch once through the existing desktop opener, then read back."""
    return _presenter(client_or_local).open(request, command_id=command_id)


def _review_copy(inspection):
    from PySide6.QtWidgets import QDialog, QLabel, QTableWidget, QTableWidgetItem
    from .connection_window import CopyReviewDialog
    review = CopyReviewDialog(inspection)
    table = review.findChild(QTableWidget)
    note = review.findChild(QLabel)
    partial = any(row['snapshot']['validation']['closure'] != 'COMPLETE' or
                  row['snapshot']['format'] == 'pvsm' for row in inspection.get('native_inspections', []))
    note.setText('선택한 저장본과 필수 외부 파일을 포함합니다. 현재 프로그램 창은 변경하지 않습니다.' +
        ('\n일부 자료가 없거나 관리 프로젝트 저장이 필요합니다. 누락 표시를 그대로 보관합니다.' if partial else ''))
    for native in inspection.get('native_inspections', []):
        snapshot = native['snapshot']
        row = table.rowCount(); table.insertRow(row)
        values = ['FreeCAD 모델' if snapshot['native_kind'] == 'pre' else 'ParaView 분석',
                  '일부 자료 없음' if snapshot['validation']['closure'] != 'COMPLETE' else
                  '분석 프로젝트로 저장 필요' if snapshot['format'] == 'pvsm' else '저장 파일 전체', str(native['total_bytes'])]
        for column, text in enumerate(values):
            table.setItem(row, column, QTableWidgetItem(text))
    try:
        return review.exec() == QDialog.DialogCode.Accepted
    finally:
        review.close(); review.deleteLater()


def _choose_destination():
    from PySide6.QtWidgets import QFileDialog
    path, _ = QFileDialog.getSaveFileName(None, '새 작업 사본 폴더 이름', '',
        options=QFileDialog.Option.DontConfirmOverwrite)
    return path


def copy_from_native(client_or_local, saved_reference, *, linked_selections=()):
    """Existing inclusion review/destination and portable publication; no Save.

    Native-only menus provide their existing native Qt review/destination
    callbacks. Falling back to a different Qt binding inside native is refused.
    """
    presenter = _presenter(client_or_local)
    from caelab.native_project_contract import validate_native_reference
    reference = validate_native_reference(saved_reference)
    client = presenter.client
    review, destination = presenter.review_copy, presenter.choose_destination
    if client is None:
        if review is None or destination is None:
            raise ValueError('현재 native 메뉴의 포함 목록과 폴더 선택을 연결하세요.')
        from caelab.portable_project import inspect_copy
        from caelab.native_project_inputs import read_registered
        metadata = read_registered(presenter.local, reference)
        inspect = lambda selections: inspect_copy(presenter.local, selections)
    else:
        metadata = client.native_project_read(reference)
        inspect = client.portable_inspect
        review, destination = review or _review_copy, destination or _choose_destination
    partial = metadata['closure'] != 'COMPLETE' or metadata['format'] == 'pvsm'
    selections = [dict(native=reference, copy_intent='preserve_declared_partial' if partial else 'complete',
                       working_target=True), *deepcopy(linked_selections)]
    inspection = inspect(selections)
    if inspection['status'] != 'READY':
        return inspection
    if not review(deepcopy(inspection)):
        return _summary('CANCELLED', message='사본 작성을 취소했습니다.')
    selected = destination()
    if not selected:
        return _summary('CANCELLED', message='사본 폴더 선택을 취소했습니다.')
    presenter._copy = dict(inspection=inspection, destination=str(selected), approved=True,
                          command_id=_id(), session_id=inspection['service_session_id'])
    return retry_native_copy(presenter)


def retry_native_copy(client_or_local):
    presenter = _presenter(client_or_local)
    if presenter._copy is None:
        raise ValueError('재확인할 사본 작성 요청이 없습니다.')
    if presenter.client is not None:
        return presenter.client.portable_create(**deepcopy(presenter._copy))
    from caelab.portable_project import create_copy
    return create_copy(presenter.local, **deepcopy(presenter._copy))


def open_reference_native(window):
    """ReferenceWindow's existing worker, exact saved default, same-open retry."""
    from .expert_window import _Call
    from PySide6.QtCore import QThreadPool, Qt
    from caelab.storage import canonical_hash
    reference = deepcopy(window.reference)
    commands = getattr(window, '_native_project_open_commands', None)
    if commands is None:
        commands = window._native_project_open_commands = {}
    command_id = commands.setdefault(canonical_hash(reference), _id())
    request = dict(reference=reference, intent='saved', target_id=None, expected_head=None,
                   selection=None, allow_partial=False)
    window._busy = True
    window.message.setText('저장한 원본을 별도 창에서 여는 중…')
    window._actions()
    worker = _Call(lambda: open_native_project(window.client, request, command_id=command_id))
    window._workers.append(worker)
    def finished(value, error):
        if worker in window._workers:
            window._workers.remove(worker)
        window._busy = False
        if window._closed or window.reference != reference:
            return
        if error:
            window.message.setText('저장본을 열지 못했습니다. 같은 요청을 다시 확인하거나 진단 상세를 확인하세요.')
            window.message.setToolTip(str(error))
        elif value['status'] in {'OPENED', 'PARTIAL_OPEN'}:
            window.message.setText('저장본을 별도 창에서 열었습니다.' if value['status'] == 'OPENED' else
                                   '일부 자료가 없는 저장본을 열었습니다. 복구 안내를 확인하세요.')
        elif value['status'] == 'CLOSED':
            # Retire only the confirmed closed request. This callback never
            # opens anything; another explicit user click creates a fresh ID.
            if commands.get(canonical_hash(reference)) == command_id:
                commands.pop(canonical_hash(reference))
            window.message.setText('열었던 창을 닫았습니다. 다시 열려면 열기 버튼을 한 번 더 누르세요.')
        else:
            window.message.setText('열기 결과를 확인 중입니다. 같은 버튼으로 다시 확인하세요.')
        window._actions()
    worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
    QThreadPool.globalInstance().start(worker)
    return True
