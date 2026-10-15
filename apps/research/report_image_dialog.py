"""Scoped Qt image selection; ReportWindow remains the draft/Undo/save owner."""
from copy import deepcopy
import json
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QThreadPool, QTimer, Qt, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QVBoxLayout, QWidget)

from caelab.report_image import apply_binding, caption, image_options, validate_content
from .data_window import _Read
from .report_image_connection import CaptureSession, candidates
from .report_image_pages import availability_message


class ImageView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        self.meaning = QLabel(); self.meaning.setWordWrap(True); root.addWidget(self.meaning)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.picture = QLabel('아직 적용할 이미지가 없습니다.')
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setMinimumSize(1, 1)
        self.picture.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.scroll.setWidget(self.picture); root.addWidget(self.scroll, 1)
        self.scroll.viewport().installEventFilter(self)
        self.source = QLabel(); self.source.setWordWrap(True); root.addWidget(self.source)
        self.details = QPlainTextEdit(); self.details.setReadOnly(True); self.details.hide()
        toggle = QPushButton('진단 정보 표시/숨기기')
        toggle.clicked.connect(lambda: self.details.setVisible(not self.details.isVisible()))
        root.addWidget(toggle); root.addWidget(self.details)
        self.asset = None
        self._image = None

    def eventFilter(self, watched, event):
        if watched is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self.fit_image()
        return super().eventFilter(watched, event)

    def fit_image(self):
        if self._image is None:
            return
        available = self.scroll.viewport().size()
        if available.width() > 2 and available.height() > 2:
            self.picture.setPixmap(QPixmap.fromImage(self._image).scaled(
                available.width() - 2, available.height() - 2,
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def set_asset(self, asset):
        content = asset['content']
        data = validate_content(content, asset['reference'])
        image = QImage.fromData(QByteArray(data), 'PNG')
        if image.isNull():
            raise ValueError('보존 PNG를 실제 이미지로 표시하지 못했습니다.')
        snapshot = content['snapshot']
        self.meaning.setText(caption(snapshot))
        # The source bytes remain untouched; only this dialog's preview is fitted.
        self._image = image
        self.fit_image()
        warning = availability_message(asset)
        files = ', '.join(Path(row['entry_path']).name for row in snapshot['sources'].values())
        self.source.setText((warning + '\n' if warning else '') + '원입력: ' + files +
                           '\n현재 Post 선택과 무관한 저장 이미지입니다.')
        self.details.setPlainText(json.dumps({'reference': asset['reference'],
            'snapshot': snapshot, 'source_status': asset.get('source_status'),
            'message': asset.get('message')}, ensure_ascii=False, indent=2))
        self.asset = deepcopy(asset)


class ReportImageDialog(QDialog):
    def __init__(self, client, report_id, parent=None):
        super().__init__(parent)
        self.client, self.report_id = client, report_id
        self.session = None
        self.choice = None
        self._workers = []
        self._closed = False
        self.setWindowTitle('보고서에 넣을 3D 결과 이미지'); self.resize(880, 750)
        root = QVBoxLayout(self)
        hint = QLabel('Post에서 적용 결과와 정확한 프레임을 저장한 뒤 필드·성분·카메라를 정하세요. '
                      '캡처는 계산을 실행하지 않으며, 아래 이미지 확인 후에만 보고서에 반영합니다.')
        hint.setWordWrap(True); root.addWidget(hint)
        line = QHBoxLayout(); self.targets = QComboBox(); line.addWidget(self.targets, 1)
        self.refresh = QPushButton('Post 목록 다시 읽기'); self.refresh.clicked.connect(self.load)
        line.addWidget(self.refresh); root.addLayout(line)
        line = QHBoxLayout()
        self.capture = QPushButton('선택한 결과 캡처'); self.capture.clicked.connect(self.start)
        self.recover = QPushButton('같은 요청 상태 확인'); self.recover.clicked.connect(self.poll)
        self.recover.setEnabled(False)
        line.addWidget(self.capture); line.addWidget(self.recover); root.addLayout(line)
        self.view = ImageView(); root.addWidget(self.view, 1)
        self.message = QLabel(); self.message.setWordWrap(True); root.addWidget(self.message)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('이 이미지 적용')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('적용하지 않고 닫기')
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        self.timer = QTimer(self); self.timer.setInterval(500); self.timer.timeout.connect(self.poll)
        self.load()

    def _call(self, function, accepted):
        if self._closed or self._workers:
            return False
        self._accepted = accepted
        worker = _Read(function); self._workers.append(worker)
        worker.signals.finished.connect(self.finished_read, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    @Slot(object, object)
    def finished_read(self, value, error):
        self._workers.clear()
        if self._closed:
            return
        if error:
            self.timer.stop()
            self.message.setText('적용하지 않았습니다. 기존 보고서는 유지됩니다. ' + str(error))
            self.recover.setEnabled(self.session is not None and self.session.stage != 'NEW')
            self.refresh.setEnabled(self.session is None or self.session.stage == 'NEW')
            return
        try:
            self._accepted(value)
        except Exception as exc:
            self.timer.stop()
            self.message.setText('적용하지 않았습니다. ' + str(exc))
            self.refresh.setEnabled(True)
            self.recover.setEnabled(self.session is not None and self.session.stage != 'NEW')

    def load(self):
        if self._workers:
            return
        if self.session is not None:
            self.session.abandon()
        self.session = self.choice = None
        self.targets.setEnabled(True); self.capture.setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        def received(receipt):
            self.targets.clear()
            for candidate in candidates(receipt['documents']):
                self.targets.addItem(candidate['label'], candidate)
            self.capture.setEnabled(self.targets.count() > 0)
            self.refresh.setEnabled(True)
            self.message.setText('정확한 결과를 선택하고 캡처하세요.' if self.targets.count() else
                '연결된 Post의 적용 3D 결과가 없습니다. native Post에서 적용·표시·저장을 마치세요.')
        self._call(self.client.documents, received)

    def start(self):
        if self._workers:
            return
        candidate = self.targets.currentData()
        if candidate is None:
            return
        if self.session is not None:
            self.session.abandon()
        self.session = CaptureSession(self.client, self.report_id, candidate)
        self.choice = None
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.capture.setEnabled(False); self.targets.setEnabled(False); self.refresh.setEnabled(False)
        self.message.setText('현재 Post owner에 캡처를 요청했습니다. 보고서에는 아직 적용하지 않았습니다.')
        self._call(self.session.submit, self.command_received)

    def command_received(self, command):
        state = command['state']
        if state == 'SUCCEEDED':
            self.timer.stop(); self.recover.setEnabled(False)
            self._call(self.session.retain, self.retained)
        elif state in {'QUEUED', 'RUNNING'}:
            self.message.setText('캡처 대기 중' if state == 'QUEUED' else
                'native 캡처 처리 중 — 닫기는 보고서 적용만 취소하며 실제 중단 확인을 뜻하지 않습니다.')
            self.recover.setEnabled(True); self.timer.start()
        else:
            self.timer.stop(); self.refresh.setEnabled(True)
            self.message.setText('캡처 실패 또는 처리 여부 미확인. 기존 이미지·본문·판단은 유지됩니다. '
                                '목록을 다시 읽은 뒤 새 캡처를 명시적으로 요청하세요.')

    def poll(self):
        if self.session is not None and not self._workers:
            self._call(self.session.poll, self.command_received)

    def retained(self, result):
        binding, asset = result
        self.view.set_asset(asset)
        self.choice = deepcopy((binding, asset))
        self.refresh.setEnabled(True)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        self.message.setText('이 PNG와 표시 조건을 적용합니다. 취소하면 현재 보고서는 바뀌지 않습니다.')

    def accept(self):
        if self.choice is not None and not self._workers:
            super().accept()

    def done(self, result):
        self._closed = True; self.timer.stop()
        if self.session is not None:
            self.session.abandon()
        for worker in self._workers:
            worker.abandon()
        super().done(result)


def choose_image(window, *, replace=False):
    if window._busy or window._pending or not window.document:
        window.message.setText('현재 저장/요청을 마친 뒤 이미지를 선택하세요.'); return
    window.remember_editor()
    if window._edit_buffers:
        window.message.setText('설명 적용 또는 수정 취소 후 이미지를 선택하세요.'); return
    index = window.sections.currentRow()
    expected = deepcopy(window.draft['sections'][index]) if replace and index >= 0 else None
    if replace and (expected is None or (expected.get('asset') or {}).get('reference', {}).get('kind') != 'post_image'):
        window.message.setText('교체할 3D 이미지 섹션을 선택하세요.'); return
    report_id = window.document['id']
    dialog = ReportImageDialog(window.client, report_id, window)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return
    if window._closed or not window.document or window.document['id'] != report_id:
        return
    window.remember_editor()
    if window._edit_buffers:
        window.message.setText('캡처 중 작성된 설명을 유지했습니다. 이미지는 아직 적용하지 않았습니다.'); return
    binding, asset = dialog.choice
    try:
        updated = apply_binding(window.draft, binding, asset['content'],
            section_id=expected['id'] if expected else None, expected_section=expected)
    except (ValueError, KeyError, TypeError) as exc:
        window.message.setText(str(exc)); return
    window.assets[binding['id']] = deepcopy(asset)
    window.changed(updated)  # Reuses the existing local Undo and durable report owner.


def edit_image(window):
    i = window.sections.currentRow()
    if i < 0 or window._busy or window._pending or not window.document:
        return
    window.remember_editor()
    if window._edit_buffers:
        window.message.setText('설명 적용 또는 수정 취소 후 이미지 크기를 바꾸세요.'); return
    row = window.draft['sections'][i]
    if (row.get('asset') or {}).get('reference', {}).get('kind') != 'post_image':
        window.message.setText('크기를 바꿀 이미지 섹션을 선택하세요.'); return
    expected, identifier = deepcopy(row), window.document['id']
    options = image_options(row)
    dialog = QDialog(window); dialog.setWindowTitle('이미지 표시와 크기')
    form = QFormLayout(dialog); show = QCheckBox('이미지 표시'); show.setChecked(options['show'])
    size = QSpinBox(); size.setRange(10, 100); size.setSuffix(' %'); size.setValue(options['width_percent'])
    form.addRow(show); form.addRow('페이지 너비 (종횡비 유지)', size)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
    if dialog.exec() != QDialog.DialogCode.Accepted or not window.document or window.document['id'] != identifier:
        return
    window.remember_editor()
    if window._closed or window._edit_buffers:
        window.message.setText('새로 작성한 설명을 유지했습니다. 크기는 아직 적용하지 않았습니다.'); return
    updated = deepcopy(window.draft)
    matches = [item for item in updated['sections'] if item['id'] == expected['id']]
    if len(matches) != 1 or matches[0] != expected:
        window.message.setText('선택 섹션이 바뀌어 기존 편집을 유지했습니다.'); return
    matches[0]['image'] = {'show': show.isChecked(), 'width_percent': size.value()}
    window.changed(updated)


def show_origin(window, binding):
    from .report_image_origin_dialog import show_origin as open_original
    return open_original(window, binding)
