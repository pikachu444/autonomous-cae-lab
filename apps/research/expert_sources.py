"""Native local source selection on existing upload, KnowledgeStore and job APIs."""
from copy import deepcopy
import json
from pathlib import Path
import uuid

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from caelab.assist.knowledge import selected_source_refs

DATA = Qt.ItemDataRole.UserRole


def assist(client, operation, arguments=None):
    return client.request('/api/workbench/assist',
                          {'operation': operation, 'arguments': arguments or {}})


class SourcePreview(QWidget):
    """Readable exact archived segments; reference details stay on demand."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.payload = None
        layout = QVBoxLayout(self)
        self.title = QLabel('Select a source')
        layout.addWidget(self.title)
        line = QHBoxLayout()
        self.segment = QComboBox()
        self.segment.currentIndexChanged.connect(self.show_segment)
        self.details = QPushButton('Details…')
        self.details.clicked.connect(self.show_details)
        line.addWidget(self.segment, 1)
        line.addWidget(self.details)
        layout.addLayout(line)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setObjectName('sourceText')
        layout.addWidget(self.text, 1)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

    def set_payload(self, payload):
        self.payload = deepcopy(payload)
        self.title.setText(payload.get('title') or 'Archived source')
        scope = {'abstract_only': 'Abstract only', 'metadata_only': 'Bibliographic record only',
                 'fulltext': 'Extracted full text', 'access_unavailable': 'Source unavailable'}.get(payload.get('status'))
        if scope:
            self.title.setText(self.title.text() + ' — ' + scope)
        self.segment.blockSignals(True)
        self.segment.clear()
        for index, row in enumerate(payload.get('segments', [])):
            locator = row['locator']
            label = ('Page ' + str(locator['page']) if 'page' in locator else
                     locator.get('section') or 'Lines ' + str(locator.get('line_start', '')) +
                     '–' + str(locator.get('line_end', '')))
            self.segment.addItem(label or 'Segment ' + str(index + 1), index)
            self.segment.setItemData(index, json.dumps(locator, ensure_ascii=False), Qt.ItemDataRole.ToolTipRole)
        self.segment.blockSignals(False)
        failures = payload.get('failed_segments', [])
        self.notice.setText('\n'.join(('Page ' + str(row.get('page', '?')) + ': ' +
            str(row.get('reason', 'Extraction failed'))) for row in failures[:8]) +
            ('\nAdditional extraction failures are in Details.' if len(failures) > 8 else ''))
        if not payload.get('segments'):
            self.text.setPlainText('No readable text was extracted. OCR was not performed; choose a readable source.')
        else:
            self.show_segment()

    def show_segment(self, *_):
        if not self.payload:
            return
        index = self.segment.currentData()
        if type(index) is not int:
            return
        row = self.payload['segments'][index]
        content = row['text']
        self.text.setPlainText(content[:200_000] + ('\n[Preview limited to 200,000 characters in this segment.]'
                                                  if len(content) > 200_000 else ''))
        limits = row.get('limitations', [])
        self.text.setToolTip('\n'.join(limits))

    def show_error(self, message):
        self.payload = None
        self.title.setText('Source unavailable')
        self.segment.clear()
        self.text.setPlainText(str(message))
        self.notice.clear()

    def show_details(self):
        if self.payload:
            details = {key: deepcopy(value) for key, value in self.payload.items() if key != 'segments'}
            index = self.segment.currentData()
            if type(index) is int:
                row = self.payload['segments'][index]
                details['locator'] = row['locator']
                details['limitations'] = row.get('limitations', [])
            QMessageBox.information(self, 'Exact source', json.dumps(details, ensure_ascii=False, indent=2))


class SourceDialog(QDialog):
    """Import is explicit library work; selection changes only on Attach."""
    def __init__(self, client, context, *, collections=(), parent=None):
        super().__init__(parent)
        self.client = client
        self.references = None
        self.titles = {}
        self.records = {}
        self._workers = []
        self._busy = self._closed = False
        self._import_job = None
        self._upload = None
        self._import_request = None
        self._focus = None
        self._catalog = {}
        self._selection_error = None
        try:
            self.initial = selected_source_refs(context)
            self.legacy = []
        except ValueError as error:
            self.initial = []
            identifiers = context.get('selected_document_ids', [])
            self.legacy = [item for item in (identifiers if isinstance(identifiers, list) else [])
                           if isinstance(item, str)]
            self._selection_error = str(error)
        self.setWindowTitle('Research sources')
        self.resize(1050, 760)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.add_file = QPushButton('Add file…')
        self.add_file.clicked.connect(self.choose_file)
        self.collection = QComboBox()
        self.collection.setEditable(True)
        self.collection.addItems(list(dict.fromkeys(collections)) or ['research'])
        self.collection.setToolTip('Library collection; attaching does not authorize model transmission.')
        self.refresh = QPushButton('Refresh library')
        self.refresh.clicked.connect(self.load_library)
        top.addWidget(self.add_file)
        top.addWidget(QLabel('Collection'))
        top.addWidget(self.collection, 1)
        top.addWidget(self.refresh)
        self.retry_import = QPushButton('Resume import')
        self.retry_import.clicked.connect(self.resume_import)
        self.retry_import.hide()
        top.addWidget(self.retry_import)
        layout.addLayout(top)
        self.message = QLabel('Check the sources to attach. Existing revisions remain selected until explicitly changed.')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        column = QVBoxLayout(left)
        self.library = QTreeWidget()
        self.library.setHeaderLabels(['Source', 'Collection'])
        self.library.setObjectName('sourceLibrary')
        self.library.currentItemChanged.connect(self.preview_selected)
        column.addWidget(self.library, 1)
        self.version = QComboBox()
        self.version.currentIndexChanged.connect(self.change_version)
        column.addWidget(self.version)
        split.addWidget(left)
        self.preview = SourcePreview()
        split.addWidget(self.preview)
        split.setSizes([350, 700])
        layout.addWidget(split, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Attach selected sources')
        self.buttons.accepted.connect(self.verify_selection)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.poll = QTimer(self)
        self.poll.setInterval(250)
        self.poll.timeout.connect(self.poll_import)
        QTimer.singleShot(0, self.load_library)

    def _controls(self):
        idle = not self._busy and self._import_job is None
        for widget in (self.library, self.version, self.refresh, self.collection, self.add_file):
            widget.setEnabled(idle)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(idle)
        self.retry_import.setVisible(self._import_request is not None and self._import_job is None)
        self.retry_import.setEnabled(idle)

    def _call(self, function, accepted, *, rejected=None):
        if self._busy or self._closed:
            return False
        from .expert_window import _Call
        self._busy = True
        self._controls()
        worker = _Call(function)
        self._workers.append(worker)
        def finished(payload, error):
            self._workers.remove(worker)
            self._busy = False
            if self._closed:
                return
            if error:
                self.message.setText(str(error))
                if rejected:
                    rejected(error)
            else:
                try:
                    accepted(payload)
                except (ValueError, TypeError, KeyError, OSError) as failure:
                    self.message.setText(str(failure))
            self._controls()
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def selected(self):
        result = []
        for index in range(self.library.topLevelItemCount()):
            item = self.library.topLevelItem(index)
            if item.checkState(0) == Qt.CheckState.Checked:
                result.append(deepcopy(item.data(0, DATA)))
        return result

    def load_library(self):
        selected = self.selected() if self.library.topLevelItemCount() else deepcopy(self.initial)
        def loaded(payload):
            self._catalog = {doc['document_id']: doc for doc in payload['documents']}
            pinned = {ref['document_id']: ref for ref in selected}
            self.library.blockSignals(True)
            self.library.clear()
            rows = list(self._catalog)
            rows += [identifier for identifier in pinned if identifier not in self._catalog]
            chosen = None
            for identifier in rows:
                document = self._catalog.get(identifier, {})
                ref = pinned.get(identifier) or {'document_id': identifier, 'revision': document['latest_revision']}
                title = document.get('title') or 'Unavailable selected source'
                self.titles[identifier] = title
                item = QTreeWidgetItem([title, document.get('collection', 'Unavailable')])
                item.setData(0, DATA, deepcopy(ref))
                item.setToolTip(0, json.dumps(ref, ensure_ascii=False))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Checked if identifier in pinned else Qt.CheckState.Unchecked)
                self.library.addTopLevelItem(item)
                if identifier == self._focus:
                    chosen = item
            self.library.resizeColumnToContents(0)
            self.library.setCurrentItem(chosen or self.library.topLevelItem(0))
            self.library.blockSignals(False)
            if self._selection_error:
                self.message.setText(self._selection_error + '. Preview and check the sources explicitly.')
            QTimer.singleShot(0, self.preview_selected)
        return self._call(lambda: assist(self.client, 'knowledge.list'), loaded)

    def preview_selected(self, *_):
        item = self.library.currentItem()
        if item is None or self._busy:
            return
        reference = deepcopy(item.data(0, DATA))
        catalog = self._catalog.get(reference['document_id'], {})
        self.version.blockSignals(True)
        self.version.clear()
        self.version.addItem('Selected version', reference['revision'])
        latest = catalog.get('latest_revision')
        if latest and latest != reference['revision']:
            self.version.addItem('Current library version', latest)
        original = next((ref for ref in self.initial if ref['document_id'] == reference['document_id']), None)
        if original and original['revision'] not in {reference['revision'], latest}:
            self.version.addItem('Saved selection', original['revision'])
        self.version.setToolTip('Exact selected revision: ' + str(reference['revision']))
        self.version.blockSignals(False)
        def loaded(payload):
            current = self.library.currentItem()
            if current and current.data(0, DATA) == reference:
                self.preview.set_payload(payload)
                self.records[(reference['document_id'], reference['revision'])] = payload
        self.preview.show_error('Reading selected source…')
        return self._call(lambda: assist(self.client, 'knowledge.source', reference), loaded,
                          rejected=self.preview.show_error)

    def change_version(self, *_):
        item, revision = self.library.currentItem(), self.version.currentData()
        if item is None or type(revision) is not int or self._busy:
            return
        reference = dict(item.data(0, DATA), revision=revision)
        item.setData(0, DATA, reference)
        item.setToolTip(0, json.dumps(reference, ensure_ascii=False))
        self.preview_selected()

    def choose_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, 'Add research source', '',
            'Research sources (*.pdf *.md *.txt *.csv)')
        if filename:
            self.import_file(filename)

    def import_file(self, filename):
        collection = self.collection.currentText().strip()
        if not collection:
            self.message.setText('Choose a library collection.')
            return False
        path = Path(filename)
        if path.suffix.lower() not in {'.pdf', '.md', '.txt', '.csv'}:
            self.message.setText('Choose PDF, Markdown (.md), UTF-8 text or CSV.')
            return False
        self.message.setText('Importing ' + path.name + '…')
        self._import_request = self._upload = None
        request_id = 'source-' + uuid.uuid4().hex
        def upload_and_submit():
            with path.open('rb') as stream:
                data = stream.read(16 * 1024 * 1024 + 1)
            receipt = self.client.upload(path.name, data)
            self._upload = receipt  # Retained registered input even if submission reports an error.
            arguments = {'data_id': receipt['id'], 'collection': collection}
            self._import_request = (request_id, arguments)
            return self.client.submit('knowledge.ingest', arguments, request_id=request_id)
        def submitted(job):
            self._import_job = job['id']
            self.poll.start()
            self.message.setText('Extracting source text…')
        return self._call(upload_and_submit, submitted)

    def resume_import(self):
        if self._import_request is None:
            return False
        request_id, arguments = deepcopy(self._import_request)
        def submitted(job):
            self._import_job = job['id']
            self.poll.start()
        return self._call(lambda: self.client.submit('knowledge.ingest', arguments, request_id=request_id), submitted)

    def poll_import(self):
        if self._import_job is None or self._busy:
            return
        identifier = self._import_job
        def status(payload):
            state = payload['state']
            if state == 'SUCCEEDED':
                self.poll.stop()
                self._import_job = None
                def imported(result):
                    self._import_request = None
                    reference = {key: result[key] for key in ('document_id', 'revision')}
                    selected = self.selected()
                    selected = [ref for ref in selected if ref['document_id'] != reference['document_id']]
                    selected.append(reference)
                    self.initial = selected
                    # load_library normally preserves rows; reset only this dialog's selection table.
                    self.library.blockSignals(True)
                    self.library.clear()
                    self.library.blockSignals(False)
                    self._focus = reference['document_id']
                    self.message.setText('Imported. Read the extracted text, then Attach or Cancel.')
                    self.load_library()
                self._call(lambda: self.client.result(identifier), imported)
            elif state in {'FAILED', 'REJECTED', 'CANCELLED', 'INTERRUPTED'}:
                self.poll.stop()
                self._import_job = None
                self._import_request = None
                self.message.setText('Source import ' + state.lower() + ': ' + str(payload.get('error') or 'No readable result'))
            else:
                self.message.setText('Extracting source text: ' + state.lower())
        return self._call(lambda: self.client.status(identifier), status)

    def verify_selection(self):
        references = self.selected()
        def read():
            checked = selected_source_refs({'selected_sources': references})
            records = []
            for reference in checked:
                source = assist(self.client, 'knowledge.source', reference)
                if source.get('revision') != reference['revision'] or not source.get('segments'):
                    raise ValueError('Selected source has no readable text; inspect extraction or deselect it.')
                records.append(source)
            return records
        def verified(records):
            self.references = deepcopy(references)
            self.records = {(source['document_id'], source['revision']): source for source in records}
            self.accept()
        return self._call(read, verified)

    def done(self, result):
        self._closed = True
        self.poll.stop()
        for worker in self._workers:
            worker.abandon()
        super().done(result)
