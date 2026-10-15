"""Native local source selection on existing upload, KnowledgeStore and job APIs."""
from copy import deepcopy
import json
import re
from html.parser import HTMLParser
from pathlib import Path
import uuid

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy, QSplitter,
    QStackedWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from caelab.assist.knowledge import selected_source_refs

DATA = Qt.ItemDataRole.UserRole


def _reading_markdown(text):
    """Typeset the bundled HTML image/version marks without loading resources."""
    from .readable_text import _code_ranges
    protected=_code_ranges(text)
    class ImageAlt(HTMLParser):
        alt=''
        def handle_starttag(self,tag,attrs):
            if tag=='img':self.alt=dict(attrs).get('alt') or ''
    def replace(match):
        if any(start<match.end() and end>match.start() for start,end in protected):return match.group()
        tag=match.group()
        if re.match(r'<img\b',tag,re.I):
            parsed=ImageAlt();parsed.feed(tag)
            alt=re.sub(r'([\\`*_{}\[\]<>()#!|])',r'\\\1',parsed.alt)
            return '['+(alt+' — ' if alt else '')+'그림 미포함]'
        return '\n' if re.match(r'<br\b',tag,re.I) else ''
    return re.sub(r'<(?:img\b[^>]*|/?small\s*|br\s*/?)>',replace,text,flags=re.I)


def assist(client, operation, arguments=None):
    return client.request('/api/workbench/assist',
                          {'operation': operation, 'arguments': arguments or {}})


class SourcePreview(QWidget):
    """Readable exact archived segments; reference details stay on demand."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.payload = None
        self._markdown = False
        layout = QVBoxLayout(self)
        self.title = QLabel('문헌을 선택하세요.')
        self.title.setWordWrap(True)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.title.setProperty('appearanceRole', 'section')
        layout.addWidget(self.title)
        line = QHBoxLayout()
        self.segment = QComboBox()
        self.segment.currentIndexChanged.connect(self.show_segment)
        self.details = QPushButton('진단 상세…')
        self.details.clicked.connect(self.show_details)
        self.raw = QPushButton('원문 보기')
        self.raw.setCheckable(True)
        self.raw.setToolTip('현재 구간의 보관된 텍스트를 정확히 표시합니다.')
        self.raw.toggled.connect(self.show_segment)
        self.raw.hide()
        line.addWidget(self.segment, 1)
        line.addWidget(self.raw)
        line.addWidget(self.details)
        layout.addLayout(line)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setObjectName('sourceText')
        from .readable_text import ReadingBrowser
        self.reading = ReadingBrowser()
        self.reading.setOpenLinks(False)
        self.reading.setOpenExternalLinks(False)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.text)
        self.pages.addWidget(self.reading)
        layout.addWidget(self.pages, 1)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

    def set_payload(self, payload):
        self.payload = deepcopy(payload)
        from .expert_library_pack import official_markdown
        self._markdown = official_markdown(payload)
        self.raw.setVisible(self._markdown)
        self.raw.blockSignals(True)
        self.raw.setChecked(False)
        self.raw.blockSignals(False)
        self.pages.setCurrentWidget(self.text)
        self.title.setText(payload.get('title') or '보관된 문헌')
        scope = {'abstract_only': '초록만 제공', 'metadata_only': '서지 정보만 제공',
                 'fulltext': '추출한 본문', 'access_unavailable': '원문을 읽을 수 없음'}.get(payload.get('status'))
        if scope:
            self.title.setText(self.title.text() + ' — ' + scope)
        self.segment.blockSignals(True)
        self.segment.clear()
        for index, row in enumerate(payload.get('segments', [])):
            locator = row['locator']
            section = locator.get('section') or ''
            if '<' in section or '>' in section:
                section = ''
            label = ('쪽 ' + str(locator['page']) if 'page' in locator else
                     section or '줄 ' + str(locator.get('line_start', '')) +
                     '–' + str(locator.get('line_end', '')))
            self.segment.addItem(label or '본문 ' + str(index + 1), index)
            self.segment.setItemData(index, json.dumps(locator, ensure_ascii=False), Qt.ItemDataRole.ToolTipRole)
        self.segment.blockSignals(False)
        failures = payload.get('failed_segments', [])
        self.notice.setText('\n'.join(('쪽 ' + str(row.get('page', '?')) + ': ' +
            str(row.get('reason', '본문 추출 실패'))) for row in failures[:8]) +
            ('\n나머지 추출 오류는 진단 상세에서 확인하세요.' if len(failures) > 8 else ''))
        if not payload.get('segments'):
            self.text.setPlainText('읽을 수 있는 본문이 없습니다. OCR은 수행하지 않았습니다. 텍스트가 있는 원문을 선택하세요.')
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
        self.text.setPlainText(content[:200_000] + ('\n[이 본문은 200,000자까지 표시합니다.]'
                                                  if len(content) > 200_000 else ''))
        if self._markdown and not self.raw.isChecked():
            from .readable_text import show_markdown
            show_markdown(self.reading, _reading_markdown(content[:200_000]))
            self.pages.setCurrentWidget(self.reading)
        else:self.pages.setCurrentWidget(self.text)
        limits = row.get('limitations', [])
        self.text.setToolTip('\n'.join(limits))
        self.reading.setToolTip('\n'.join(limits))

    def show_error(self, message):
        self.payload = None
        self.raw.hide()
        self.pages.setCurrentWidget(self.text)
        self.title.setText('원문을 읽을 수 없음')
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
            QMessageBox.information(self, '문헌 진단 상세', json.dumps(details, ensure_ascii=False, indent=2))


class SourceDialog(QDialog):
    """Import is explicit library work; selection changes only on Attach."""
    def __init__(self, client, context, *, collections=(), role_id=None, parent=None):
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
        self._role_collections=set(collections)
        self._scope_role_id=role_id
        self._context=deepcopy(context)
        self._connection_status=None
        try:
            self.initial = selected_source_refs(context)
            self.legacy = []
        except ValueError as error:
            self.initial = []
            identifiers = context.get('selected_document_ids', [])
            self.legacy = [item for item in (identifiers if isinstance(identifiers, list) else [])
                           if isinstance(item, str)]
            self._selection_error = str(error)
        self.setWindowTitle('연구 문헌')
        self.resize(1050, 760)
        self.setMinimumSize(720, 500)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.add_file = QPushButton('파일 가져오기…')
        self.add_file.clicked.connect(self.choose_file)
        self.official = QPushButton('공식 자료 가져오기…')
        self.official.clicked.connect(self.choose_official)
        self.collection = QComboBox()
        self.collection.setEditable(True)
        from .expert_library_pack import collection_label
        for name in list(dict.fromkeys(collections)) or ['research']:
            self.collection.addItem(collection_label(name),name)
        self.collection.setToolTip('문헌 보관함입니다. 연구에 연결하는 동작은 모델 전송을 허용하지 않습니다.')
        self.refresh = QPushButton('목록 새로 고침')
        self.refresh.clicked.connect(self.load_library)
        top.addWidget(self.add_file)
        top.addWidget(self.official)
        top.addWidget(QLabel('보관함'))
        top.addWidget(self.collection, 1)
        top.addWidget(self.refresh)
        self.retry_import = QPushButton('가져오기 재시도')
        self.retry_import.clicked.connect(self.resume_import)
        self.retry_import.hide()
        top.addWidget(self.retry_import)
        layout.addLayout(top)
        self.message = QLabel('연결할 문헌을 체크하세요. 보관된 원문은 직접 다시 선택하기 전까지 유지됩니다.')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        scope=QHBoxLayout()
        self.readiness=QLabel('문헌 선택은 외부 전송 허용과 별개입니다.')
        self.readiness.setWordWrap(True);scope.addWidget(self.readiness,1)
        self.settings=QPushButton('연결 설정…');self.settings.clicked.connect(self.open_settings)
        scope.addWidget(self.settings);layout.addLayout(scope)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        column = QVBoxLayout(left)
        self.library = QTreeWidget()
        self.library.setHeaderLabels(['문헌', '보관함'])
        self.library.setObjectName('sourceLibrary')
        self.library.setMinimumWidth(220)
        self.library.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.library.header().setStretchLastSection(False)
        self.library.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.library.currentItemChanged.connect(self.preview_selected)
        self.library.itemChanged.connect(self.update_readiness)
        column.addWidget(self.library, 1)
        self.version = QComboBox()
        self.version.currentIndexChanged.connect(self.change_version)
        column.addWidget(self.version)
        split.addWidget(left)
        self.preview = SourcePreview()
        split.addWidget(self.preview)
        split.setChildrenCollapsible(False)
        split.setStretchFactor(1, 1)
        split.setSizes([350, 700])
        layout.addWidget(split, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('선택한 문헌 연결')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.accepted.connect(self.verify_selection)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.poll = QTimer(self)
        self.poll.setInterval(250)
        self.poll.timeout.connect(self.poll_import)
        QTimer.singleShot(0, self.load_library)

    def _controls(self):
        idle = not self._busy and self._import_job is None
        for widget in (self.library, self.version, self.refresh, self.collection, self.add_file,self.official,self.settings):
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

    def update_readiness(self,*_):
        missing=[self._catalog.get(ref['document_id'],{}).get('collection') for ref in self.selected()]
        missing=list(dict.fromkeys(name for name in missing if name and name not in self._role_collections))
        if missing:
            from .expert_library_pack import collection_label
            self.readiness.setText('담당자의 검토 범위를 확인하세요: '+', '.join(collection_label(name) for name in missing)+'. 연결 설정에서 변경할 수 있습니다.')
        elif self._connection_status=='NOT_CONFIGURED':
            self.readiness.setText('문헌은 읽을 수 있습니다. 연구 시작 전 연결 설정에서 모델을 선택하세요.')
        elif any(ref not in self._context.get('transmission_scope',{}).get('source_refs',[]) for ref in self.selected()):
            self.readiness.setText('아직 전송을 허용하지 않은 문헌입니다. 연결한 뒤 토론의 전송 설정에서 허용하세요.')
        else:self.readiness.setText('선택 자료와 전송 허용은 별개입니다. 자료 반입은 권한을 늘리지 않습니다.')

    def choose_official(self):
        from .expert_library_pack import OfficialDocumentsDialog
        dialog=OfficialDocumentsDialog(self.client,self)
        try:
            accepted=dialog.exec()==QDialog.DialogCode.Accepted
            if accepted:
                existing=self.selected()
                self.initial=list({ref['document_id']:ref for ref in [*existing,*dialog.references]}.values())
                self.library.clear()
                if dialog.references:self._focus=dialog.references[0]['document_id']
        finally:dialog.close();dialog.deleteLater()
        if not self._closed:self.load_library()

    def open_settings(self):
        from .expert_connection_dialog import ConnectionDialog
        dialog=ConnectionDialog(self.client,self)
        try:dialog.exec()
        finally:dialog.close();dialog.deleteLater()
        ancestor=self.parent()
        while ancestor is not None:
            if callable(getattr(ancestor,'refresh_registry',None)):
                ancestor.refresh_registry();break
            ancestor=ancestor.parent()
        def refreshed(value):
            value,self._connection_status=value
            roles=value.get('experts',[])
            self._role_collections={name for role in roles
                if self._scope_role_id is None or role['id']==self._scope_role_id
                for name in role.get('collections',[])}
            self.update_readiness()
        def read_settings():
            roles=assist(self.client,'experts.list')
            return roles,self.client.expert_connection().get('configuration')
        if not self._closed:self._call(read_settings,refreshed)

    def load_library(self):
        selected = self.selected() if self.library.topLevelItemCount() else deepcopy(self.initial)
        def read():
            library=assist(self.client,'knowledge.list')
            try:configuration=self.client.expert_connection().get('configuration')
            except Exception:configuration=None
            return library,configuration
        def loaded(payload):
            payload,self._connection_status=payload
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
                title = document.get('title') or '읽을 수 없는 선택 문헌'
                self.titles[identifier] = title
                from .expert_library_pack import collection_label
                item = QTreeWidgetItem([title, collection_label(document.get('collection', '없음'))])
                item.setData(0, DATA, deepcopy(ref))
                item.setToolTip(0, title)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Checked if identifier in pinned else Qt.CheckState.Unchecked)
                self.library.addTopLevelItem(item)
                if identifier == self._focus:
                    chosen = item
            self.library.setCurrentItem(chosen or self.library.topLevelItem(0))
            self.library.blockSignals(False)
            self.update_readiness()
            if self._selection_error:
                self.message.setText(self._selection_error + '. 원문을 읽고 연결할 문헌을 직접 선택하세요.')
            QTimer.singleShot(0, self.preview_selected)
        return self._call(read, loaded)

    def preview_selected(self, *_):
        item = self.library.currentItem()
        if item is None or self._busy:
            return
        reference = deepcopy(item.data(0, DATA))
        catalog = self._catalog.get(reference['document_id'], {})
        self.version.blockSignals(True)
        self.version.clear()
        self.version.addItem('선택한 원문', reference['revision'])
        latest = catalog.get('latest_revision')
        if latest and latest != reference['revision']:
            self.version.addItem('보관함의 최신 원문', latest)
        original = next((ref for ref in self.initial if ref['document_id'] == reference['document_id']), None)
        if original and original['revision'] not in {reference['revision'], latest}:
            self.version.addItem('이전에 연결한 원문', original['revision'])
        self.version.setToolTip('선택한 원문의 개정: ' + str(reference['revision']))
        self.version.blockSignals(False)
        def loaded(payload):
            current = self.library.currentItem()
            if current and current.data(0, DATA) == reference:
                self.preview.set_payload(payload)
                self.records[(reference['document_id'], reference['revision'])] = payload
        self.preview.show_error('선택한 원문을 읽는 중…')
        return self._call(lambda: assist(self.client, 'knowledge.source', reference), loaded,
                          rejected=self.preview.show_error)

    def change_version(self, *_):
        item, revision = self.library.currentItem(), self.version.currentData()
        if item is None or type(revision) is not int or self._busy:
            return
        reference = dict(item.data(0, DATA), revision=revision)
        item.setData(0, DATA, reference)
        item.setToolTip(0, self.titles.get(reference['document_id'], '문헌'))
        self.preview_selected()

    def choose_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, '연구 문헌 가져오기', '',
            '연구 문헌 (*.pdf *.md *.txt *.csv)')
        if filename:
            self.import_file(filename)

    def import_file(self, filename):
        collection = self.collection.currentText().strip()
        if self.collection.currentIndex()>=0 and collection==self.collection.itemText(self.collection.currentIndex()):
            collection=self.collection.currentData()
        if not collection:
            self.message.setText('보관함 이름을 입력하세요.')
            return False
        path = Path(filename)
        if path.suffix.lower() not in {'.pdf', '.md', '.txt', '.csv'}:
            self.message.setText('PDF, Markdown(.md), UTF-8 텍스트 또는 CSV를 선택하세요.')
            return False
        self.message.setText('가져오는 중: ' + path.name + '…')
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
            self.message.setText('본문을 추출하는 중…')
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
                    self.message.setText('가져왔습니다. 추출한 본문을 읽고 문헌을 연결하거나 취소하세요.')
                    self.load_library()
                self._call(lambda: self.client.result(identifier), imported)
            elif state in {'FAILED', 'REJECTED', 'CANCELLED', 'INTERRUPTED'}:
                self.poll.stop()
                self._import_job = None
                self._import_request = None
                self.message.setText('문헌 가져오기 ' + state.lower() + ': ' + str(payload.get('error') or '읽을 수 있는 본문 없음'))
            else:
                self.message.setText('본문 추출 중: ' + state.lower())
        return self._call(lambda: self.client.status(identifier), status)

    def verify_selection(self):
        references = self.selected()
        def read():
            checked = selected_source_refs({'selected_sources': references})
            records = []
            for reference in checked:
                source = assist(self.client, 'knowledge.source', reference)
                if source.get('revision') != reference['revision'] or not source.get('segments'):
                    raise ValueError('선택한 원문에 읽을 수 있는 본문이 없습니다. 추출 상태를 확인하거나 선택을 해제하세요.')
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
