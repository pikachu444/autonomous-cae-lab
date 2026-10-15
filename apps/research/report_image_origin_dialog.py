"""Read retained image separately from verified original Post activation.

The dialog never changes a Report draft or dispatches captures/calculations.
Closing it abandons signal delivery, not an already launched native process.
"""
from copy import deepcopy
import json

from PySide6.QtCore import QThreadPool, Qt, Slot
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout

from .data_window import _Read
from .report_image_origin import OriginSession


class ReportImageOriginDialog(QDialog):
    def __init__(self, client, report_id, binding, asset, parent=None):
        super().__init__(parent)
        # Reuse Sol's ImageView as installed, including its viewport-fit patch.
        from .report_image_dialog import ImageView
        self.setWindowTitle('그림과 원자료')
        self.resize(880, 760)
        self.session = OriginSession(client, report_id, binding)
        self._workers = []
        self._closed = False
        root = QVBoxLayout(self)
        heading = QLabel('보고서에 저장한 그림입니다. 원값과 처리조건은 ParaView에서 확인할 수 있습니다.')
        heading.setWordWrap(True); root.addWidget(heading)
        self.view = ImageView(self); self.view.set_asset(deepcopy(asset)); root.addWidget(self.view, 1)
        hint = QLabel('이 그림의 저장된 원자료를 확인한 뒤 ParaView에서 엽니다. '
                      '현재 창의 편집과 선택을 덮지 않으며, 과거 카메라를 자동 복원하지 않습니다.')
        hint.setWordWrap(True); root.addWidget(hint)
        self.open_button = QPushButton('ParaView에서 열기')
        self.open_button.clicked.connect(self.open_original); root.addWidget(self.open_button)
        self.poll_button = QPushButton('다시 확인')
        self.poll_button.clicked.connect(self.poll); self.poll_button.setEnabled(False)
        root.addWidget(self.poll_button)
        self.message = QLabel('아직 원자료를 열지 않았습니다.')
        self.message.setWordWrap(True); self.message.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('보고서로 돌아가기')
        buttons.rejected.connect(self.reject); root.addWidget(buttons)

    def _call(self, function):
        if self._workers or self._closed:
            return
        self.open_button.setEnabled(False); self.poll_button.setEnabled(False)
        worker = _Read(function); self._workers.append(worker)
        worker.signals.finished.connect(self.finished_read, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def open_original(self):
        self.message.setText('저장한 원자료를 확인하고 ParaView를 여는 중입니다.')
        self._call(self.session.open)

    def poll(self):
        self._call(self.session.poll)

    @Slot(object, object)
    def finished_read(self, value, error):
        self._workers.clear()
        if self._closed:
            return
        self.poll_button.setEnabled(self.session.started)
        if self.session.verification:
            self.view.details.appendPlainText('원자료 열기 진단\n' +
                json.dumps(self.session.verification, ensure_ascii=False, indent=2))
        if error:
            self.message.setText('원자료 열기를 확인하지 못했습니다. 보고서 그림·본문·판단은 그대로입니다. '
                                 + str(error) + '\n확정된 파일/연결 오류를 복구한 뒤 이 창을 닫고 새로 요청하세요. '
                                 '실행 여부가 미확인이면 다시 확인을 누르세요.')
            return
        self.message.setText(str(value.get('message', '실제 native 상태를 확인하지 못했습니다.')))
        if value.get('status') in ('SOURCE_OPENED', 'SOURCE_VERIFIED'):
            self.message.setText(self.message.text() + '\n원 Post의 선택된 pipeline에서 Properties를 읽고, '
                                 'native Spreadsheet View로 원값을 확인하세요. 보고서와 원창의 편집은 별개입니다.')

    def done(self, result):
        self._closed = True
        for worker in self._workers:
            worker.abandon()
        super().done(result)


def show_origin(window, binding):
    asset = window.assets.get(binding['id'])
    if not asset or 'content' not in asset or not window.document:
        window.message.setText('보존 이미지를 읽지 못했습니다. 자료 다시 확인을 사용하세요.')
        return
    try:
        dialog = ReportImageOriginDialog(window.client, window.document['id'], binding, asset, window)
    except (ValueError, KeyError, TypeError) as error:
        window.message.setText(str(error)); return
    dialog.exec()
