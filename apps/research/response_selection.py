"""Exact declared response choices shared by research pickers, not an evaluator."""
from copy import deepcopy


def response_choices(metadata, *, limit=None):
    """Physical channels first; native locations are a separately paged choice."""
    choices, seen = [], set()
    def add(selector, descriptor, label):
        if not isinstance(selector, str) or not selector or selector in seen or (limit is not None and len(choices) >= limit):
            return
        seen.add(selector)
        choices.append({'selector': selector, 'label': label + ' [' + str(descriptor.get('unit', '?')) + ']',
                        'definition': deepcopy(descriptor)})
    for descriptor in metadata.get('responses', []):
        if isinstance(descriptor, dict) and descriptor.get('kind') in ('scalar', 'series'):
            add(descriptor.get('response'), descriptor, str(descriptor.get('response')))
    for name, descriptor in metadata.get('native_channels', {}).items():
        if not isinstance(descriptor, dict):
            continue
        if descriptor.get('requires_location') or descriptor.get('selectors') or descriptor.get('node_ids'):
            count = descriptor.get('selector_count', len(descriptor.get('selectors', descriptor.get('node_ids', []))))
            choices.append({'selector': None, 'channel': name, 'requires_location': True,
                'label': str(name) + ' · ' + str(count) + ' exact locations [' + str(descriptor.get('unit', '?')) + ']',
                'definition': deepcopy(descriptor)})
        else:
            add(descriptor.get('source', {}).get('selector'), descriptor, str(name))
    return choices


def choose_location(parent, client, document_id, job_id, choice, *, relevant=lambda: True):
    """Real paged native-location picker; dialogs never evaluate or infer IDs."""
    if not choice.get('requires_location'):
        return choice
    from PySide6.QtCore import Qt, QThreadPool, QTimer
    from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
        QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout)
    from .pde_window import _Read
    if not callable(getattr(client, 'document_response_locations', None)):
        raise ValueError('This service does not provide paged retained native locations')
    class Locations(QDialog):
        def __init__(self):
            super().__init__(parent)
            self.setWindowTitle('Exact location — ' + choice['channel'])
            self.resize(680, 520)
            self._closed, self._busy, self._serial = False, False, 0
            self._pending = None
            self.start, self.next_start, self.selected = 0, None, None
            layout = QVBoxLayout(self)
            self.search = QLineEdit(); self.search.setPlaceholderText('Search retained node/Gauss ID or label; no nearest-position guess')
            layout.addWidget(self.search)
            self.items = QListWidget(); self.items.setObjectName('nativeLocationPage'); layout.addWidget(self.items, 1)
            self.message = QLabel(); self.message.setWordWrap(True); layout.addWidget(self.message)
            row = QHBoxLayout()
            self.previous, self.next, self.retry = QPushButton('Previous page'), QPushButton('Next page'), QPushButton('Read / retry page')
            for widget in (self.previous, self.next, self.retry): row.addWidget(widget)
            layout.addLayout(row)
            self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Use exact retained location')
            layout.addWidget(self.buttons)
            self.buttons.accepted.connect(self.accept_choice); self.buttons.rejected.connect(self.reject)
            self.items.itemSelectionChanged.connect(self.actions)
            self.items.itemDoubleClicked.connect(lambda _: self.accept_choice())
            self.search.textEdited.connect(lambda _: self.load(0))
            self.previous.clicked.connect(lambda: self.load(max(0, self.start - 128)))
            self.next.clicked.connect(lambda: self.load(self.next_start) if self.next_start is not None else None)
            self.retry.clicked.connect(lambda: self.load(self.start))
            self.finished.connect(lambda _: setattr(self, '_closed', True))
            QTimer.singleShot(0, lambda: self.load(0))
            self.actions()
        def actions(self):
            active = not self._closed and relevant()
            self.previous.setEnabled(active and not self._busy and self.start > 0)
            self.next.setEnabled(active and not self._busy and self.next_start is not None)
            self.retry.setEnabled(active and not self._busy)
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(active and not self._busy and bool(self.items.selectedItems()))
        def load(self, start):
            if self._closed or not relevant(): return
            self._serial += 1
            request = (self._serial, start, self.search.text())
            if self._busy:
                self._pending = request
                return
            self.send(request)
        def send(self, request):
            serial, start, query = request
            self._busy = True; self.items.clear(); self.actions()
            worker = self._worker = _Read(lambda: client.document_response_locations(document_id, job_id,
                choice['channel'], start=start, count=128, search=query))
            def finished(payload, error):
                self._busy = False
                if self._closed: return
                if relevant() and serial == self._serial:
                    if error:
                        self.message.setText('Read failed; no model executed. ' + str(error))
                    elif (payload.get('document_id'), payload.get('job_id'), payload.get('channel'), payload.get('start')) != (document_id, job_id, choice['channel'], start):
                        self.message.setText('Location reply belongs to another result or page. Refresh the source.')
                    else:
                        self.start, self.next_start = start, payload['next_start']
                        for entry in payload['locations']:
                            item = QListWidgetItem(entry['label'] + ' · ' + entry['selector'])
                            item.setData(Qt.ItemDataRole.UserRole, entry['selector']); self.items.addItem(item)
                        self.message.setText(str(payload['matched_count']) + ' matching locations of ' + str(payload['total_count']) +
                            '; showing ' + str(start) + '–' + str(start + len(payload['locations'])))
                elif not relevant():
                    self.message.setText('Source document/job changed; reopen the location selector.')
                self.actions()
                pending, self._pending = self._pending, None
                if pending and relevant(): self.send(pending)
            worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
            QThreadPool.globalInstance().start(worker)
        def accept_choice(self):
            if not self._busy and relevant() and self.items.selectedItems():
                self.selected = self.items.selectedItems()[0].data(Qt.ItemDataRole.UserRole)
                self.accept()
    dialog = Locations()
    if dialog.exec() == QDialog.DialogCode.Accepted and relevant() and dialog.selected:
        return {**deepcopy(choice), 'selector': dialog.selected, 'requires_location': False}
    return None
