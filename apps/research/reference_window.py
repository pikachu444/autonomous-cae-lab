"""Read one exact saved reference without replacing its editable owner."""
import argparse
from copy import deepcopy
import json
import sys

from PySide6.QtCore import QThreadPool, Qt, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHeaderView, QLabel,
    QMainWindow, QPlainTextEdit, QPushButton, QSizePolicy, QToolBar, QVBoxLayout, QWidget)

from caelab.workbench_client import Client
from .appearance import apply_appearance, configure_plot_fonts
from .expert_window import _Call
from .reference_content import ReferenceContent


_TOOLS = {'material': '재료', 'pde': 'PDE', 'simulation': '해석',
          'evaluation': '계산 절차', 'study': '연구', 'data': '데이터',
          'numerical': '수치 연구', 'expert': '전문가 대화'}


class ReferenceWindow(QMainWindow):
    def __init__(self, client, reference):
        super().__init__()
        self.client, self.reference = client, deepcopy(reference)
        self._workers, self._busy, self._closed = [], False, False
        self.value, self._error = None, None
        self._candidate_windows = []
        self.resize(1100, 780)
        self.setMinimumSize(720, 500)
        self.setWindowTitle(self._kind_title())
        files = self.menuBar().addMenu('파일(&F)')
        self.open_action = QAction(self._owner_label(), self)
        self.open_action.triggered.connect(self.open_owner)
        files.addAction(self.open_action)
        close = QAction('닫기', self, shortcut=QKeySequence.Close)
        close.triggered.connect(self.close)
        files.addAction(close)
        view = self.menuBar().addMenu('보기(&V)')
        self.retry_action = QAction('다시 읽기', self, shortcut=QKeySequence.Refresh)
        self.retry_action.triggered.connect(self.retry)
        view.addAction(self.retry_action)
        details = QAction('진단 상세…', self)
        details.triggered.connect(self.show_details)
        view.addAction(details)
        bar = QToolBar('자료 읽기', self)
        bar.setMovable(False)
        self.addToolBar(bar)
        bar.addAction(self.retry_action)
        self.open_button = QPushButton(self._owner_label())
        self.open_button.setProperty('appearanceRole', 'primary')
        self.open_button.setToolTip('저장된 내용을 덮어쓰지 않고 원 프로그램의 현재 문서를 엽니다.'
            if self.reference.get('kind') != 'result' else '이 결과가 속한 계산의 실행 기록을 엽니다.')
        if self.reference.get('kind') == 'numerical_candidate_evidence':
            self.open_button.setToolTip('보고서에 저장된 후보와 상세 실행을 그대로 선택합니다. 열기는 계산하지 않습니다.')
        if self.reference.get('kind') in {'native_pre', 'native_post'}:
            self.open_button.setToolTip('선택한 저장본을 별도 창에서 엽니다. 현재 편집은 유지됩니다.')
        self.open_button.clicked.connect(self.open_owner)
        bar.addWidget(self.open_button)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        context = QLabel('열람 전용')
        context.setProperty('appearanceRole', 'muted')
        bar.addWidget(context)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 12, 16, 12)
        configure_plot_fonts()
        self.content = ReferenceContent()
        self.content.title.setProperty('appearanceRole', 'title')
        header = self.content.values.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.content.response_requested.connect(self.read_response)
        self.content.saved_reference_requested.connect(self.open_saved_reference)
        layout.addWidget(self.content, 1)
        self.setCentralWidget(root)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.statusBar().addWidget(self.message, 1)
        self._read(self.reference)

    def _kind_title(self):
        if self.reference.get('kind') == 'document':
            return {'study': '연구 질문', 'pde': 'PDE 모델', 'material': '재료 모델',
                    'simulation': '해석 모델', 'evaluation': '계산 절차',
                    'numerical': '계산 계획', 'data': '시험 자료'}.get(
                        self.reference.get('document_kind'), '저장된 문서')
        return {'result': '계산 결과', 'expert_turn': '전문가 답변',
                'numerical_candidate_evidence': '선택 후보 결과'}.get(
            self.reference.get('kind'), '저장된 자료')

    def _owner_label(self):
        if self.reference.get('kind') in {'native_pre', 'native_post'}:
            return '저장한 모델 열기' if self.reference['kind'] == 'native_pre' else '저장한 분석 열기'
        if self.reference.get('kind') == 'numerical_candidate_evidence':
            return '선택 후보 상세 열기'
        if self.reference.get('kind') == 'result':
            return '실행 기록에서 열기'
        kind = ('expert' if self.reference.get('kind') == 'expert_turn'
                else self.reference.get('document_kind'))
        return _TOOLS.get(kind, '원 프로그램') + '에서 열기'

    def _actions(self):
        available = bool(not self._error and self.value and self.value.get('status') == 'AVAILABLE')
        self.retry_action.setEnabled(not self._busy and not self._closed)
        self.content.read.setEnabled(not self._busy and not self._closed)
        self.open_button.setEnabled(available and self.reference.get('kind') != 'knowledge' and not self._busy and not self._closed)
        self.open_action.setEnabled(self.open_button.isEnabled())

    def _read(self, reference):
        if self._busy or self._closed:
            return False
        self.reference = deepcopy(reference)
        self._busy, self.value, self._error = True, None, None
        if not self._has_saved_candidate_view():
            self.content.clear('저장된 내용을 읽고 있습니다…')
        self.content.title.setText(self._kind_title())
        self.message.setText('읽는 중…')
        self._actions()
        client, frozen = self.client, deepcopy(self.reference)
        worker = _Call(lambda: client.research_reference(frozen))
        self._workers.append(worker)
        worker.signals.finished.connect(self._finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    @Slot(object, object)
    def _finished(self, value, error):
        sender = self.sender()
        self._workers = [worker for worker in self._workers if worker.signals is not sender]
        self._busy = False
        if not self._closed:
            self.received(value, error)

    def retry(self):
        return self._read(self.reference)

    def _has_saved_candidate_view(self):
        payload=self.content.payload or {}
        return (self.reference.get('kind')=='numerical_candidate_evidence'
            and payload.get('kind')=='numerical_candidate_evidence'
            and payload.get('status')=='AVAILABLE' and payload.get('reference')==self.reference)

    def closeEvent(self, event):
        from shiboken6 import isValid
        for window in list(self._candidate_windows):
            if isValid(window) and not window.close():
                event.ignore()
                return
        self._closed = True
        for worker in self._workers:
            worker.abandon()
            worker.signals.finished.disconnect(self._finished)
        self._workers.clear()
        super().closeEvent(event)

    def received(self, value, error):
        self._error = error
        self.value = deepcopy(value) if isinstance(value, dict) else None
        if error or not self.value or self.value.get('status') != 'AVAILABLE':
            if self._has_saved_candidate_view():
                self.message.setText('원자료를 다시 확인하지 못했습니다. 마지막으로 읽은 저장 내용을 표시합니다. 다시 읽기를 누르세요.')
            else:
                self.content.clear('서비스 연결과 저장된 자료를 확인한 뒤 다시 읽으세요.\n'
                                   '자세한 오류는 보기 메뉴의 진단 상세에서 확인할 수 있습니다.')
                self.content.title.setText(self._kind_title())
                self.message.setText('자료를 읽지 못했습니다. 다시 읽기를 누르세요.')
        else:
            self.content.set_payload(self.value, label=self._kind_title())
            self.message.setText('저장된 내용을 읽었습니다.')
        # One diagnostic entry here; the shared presenter stays unchanged.
        self.content.details.hide()
        self._actions()

    def read_response(self, name):
        if self._busy or self._closed or self.reference.get('kind') != 'result' or not name:
            return
        reference = deepcopy(self.reference)
        reference.pop('response', None)
        reference['selection'] = {'responses': [name], 'rows': [0, 256]}
        return self._read(reference)

    def show_details(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('자료 진단 상세')
        dialog.resize(850, 600)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(json.dumps({'reference': self.reference, 'payload': self.value,
                                         'error': self._error}, ensure_ascii=False, indent=2))
        text.setReadOnly(True)
        layout.addWidget(text)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()

    def open_saved_reference(self, reference):
        if self._busy or self._closed or not self.value or self.value.get('status') != 'AVAILABLE':
            return False
        window = ReferenceWindow(self.client, reference)
        self._candidate_windows.append(window)
        window.show()
        return window

    def open_owner(self):
        if self._busy or self._closed or not self.open_button.isEnabled():
            return False
        if self.reference.get('kind') in {'native_pre', 'native_post'}:
            from .native_project_actions import open_reference_native
            return open_reference_native(self)
        from .desktop import launch_tool
        reference = deepcopy(self.reference)
        try:
            if reference['kind'] == 'numerical_candidate_evidence':
                from caelab.numerical_candidate_evidence import validate_evidence_reference
                from .numerical_candidate_detail_window import NumericalCandidateDetailWindow
                validate_evidence_reference(reference)
                if (self.value.get('kind')!='numerical_candidate_evidence'
                        or self.value.get('reference')!=reference):
                    raise ValueError('선택한 후보와 저장된 참조가 다릅니다.')
                # Freeze the selected attempt BEFORE the first retained read.
                window=NumericalCandidateDetailWindow(self.client,
                    document_id=reference['source']['document_id'],
                    job_id=reference['source']['job_id'],candidate_id=reference['candidate_id'],
                    source=deepcopy(reference['source']),parent=self,auto_load=False)
                window.attempt_job_id=reference['attempt_job_id']
                window.evidence_purpose.setCurrentIndex(window.evidence_purpose.findData(reference['purpose']))
                self._candidate_windows.append(window)
                window.destroyed.connect(lambda:self._candidate_windows.remove(window)
                    if window in self._candidate_windows else None)
                window.show();window.refresh()
                self.message.setText('선택 후보 상세를 열었습니다. 저장한 보고 내용은 유지됩니다. 추가 계산은 상세 창에서 명시적으로 실행하세요.')
                return True
            if reference['kind'] == 'result':
                launch_tool(self.client, 'runner', job_id=reference['job_id'])
            else:
                kind = 'expert' if reference['kind'] == 'expert_turn' else reference['document_kind']
                identifier = reference.get('discussion_id', reference.get('document_id'))
                launch_tool(self.client, kind, document_id=identifier)
        except Exception as error:
            self._error = str(error)
            self.message.setText('원 프로그램을 열지 못했습니다. 다시 열거나 진단 상세를 확인하세요.')
            return False
        self.message.setText('원 프로그램을 여는 요청을 보냈습니다.')
        return True


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--service', required=True)
    parser.add_argument('--reference', required=True)
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_appearance(app)
    window = ReferenceWindow(Client(args.service), json.loads(args.reference))
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
