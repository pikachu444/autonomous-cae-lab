"""Retained curve comparison on the original domain owner, without evaluation."""
from __future__ import annotations

from copy import deepcopy
import json
import math
import uuid

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QLabel, QHeaderView,
    QMainWindow, QPushButton, QPlainTextEdit, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QSizePolicy)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from .pde_window import _Read
from .response_selection import response_choices, choose_location

KINDS = {'data', 'material', 'pde', 'simulation'}


def _matches(binding, source):
    return isinstance(binding, dict) and all(binding.get(key) == value for key, value in source.items())


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


class CurveComparisonWindow(QMainWindow):
    """Fixed exact source A; B is chosen from actual retained result catalogs.

    ``relevant`` optionally guards the originating editor's owner/job selection.
    The window does not open a solver or apply an input edit. Saving publishes
    the comparisons through A's existing document owner.
    """
    def __init__(self, client, *, source, relevant=None, parent=None):
        super().__init__(parent)
        if (not isinstance(source, dict) or not {'document_id', 'job_id', 'response'} <= set(source)
                or set(source) - {'document_id', 'job_id', 'response', 'input_revision', 'input_sha256'}):
            raise ValueError('Choose an exact source document, retained job and response')
        self.client, self.source = client, deepcopy(source)
        self._parent_relevant = relevant
        self.document = None
        self._session = None
        self._busy = self._accepting = self._closed = False
        self._queue, self._worker = [], None
        self._serial = 0
        self._comparison = None
        self._save_request = None
        self._document_names, self._run_names = {}, {}
        self._build()
        QTimer.singleShot(0, self.refresh)

    def _build(self):
        from .appearance import configure_plot_fonts
        configure_plot_fonts()
        self.setWindowTitle('곡선 비교')
        self.resize(1320, 900)
        root = QWidget(); layout = QVBoxLayout(root)
        self.source_label = QLabel('기준 곡선을 읽고 있습니다.')
        self.source_label.setTextFormat(Qt.TextFormat.PlainText)
        self.source_label.setProperty('appearanceRole', 'section')
        self.source_label.setWordWrap(True); layout.addWidget(self.source_label)
        row = QHBoxLayout()
        self.documents = QComboBox(); self.documents.setObjectName('comparison_document_b')
        self.jobs = QComboBox(); self.jobs.setObjectName('comparison_job_b')
        self.responses = QComboBox(); self.responses.setObjectName('comparison_response_b')
        for label, widget in [('새 비교 자료', self.documents), ('계산 결과', self.jobs), ('물리량', self.responses)]:
            widget.setMinimumContentsLength(12)
            widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            row.addWidget(QLabel(label)); row.addWidget(widget, 1)
        self.location_button = QPushButton('위치 선택…')
        self.location_button.clicked.connect(self.choose_response_location)
        row.addWidget(self.location_button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.refresh_button = QPushButton('자료 새로 고침')
        self.compare_button = QPushButton('곡선 비교')
        self.compare_button.setProperty('appearanceRole', 'primary')
        self.save_button = QPushButton('비교 저장')
        self.save_button.setToolTip('기준 곡선의 문서에 비교 결과를 저장합니다.')
        self.retry_save = QPushButton('저장 다시 확인'); self.retry_save.hide()
        for button in (self.refresh_button, self.compare_button, self.save_button, self.retry_save):
            row.addWidget(button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.saved = QComboBox(); self.saved.setObjectName('retained_comparisons')
        self.saved.setMinimumContentsLength(12)
        self.saved.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.saved.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        row.addWidget(QLabel('비교 기록')); row.addWidget(self.saved, 1)
        self.start = QSpinBox(); self.start.setRange(0, 2_000_000_000); self.start.setObjectName('comparison_page_start')
        self.count = QSpinBox(); self.count.setRange(1, 4096); self.count.setValue(512)
        self.count.setObjectName('comparison_page_count')
        self.page_button = QPushButton('행 보기')
        self.previous = QPushButton('이전'); self.next = QPushButton('다음')
        for label, widget in [('시작 행', self.start), ('표시 행 수', self.count)]:
            row.addWidget(QLabel(label)); row.addWidget(widget)
        for button in (self.previous, self.next, self.page_button): row.addWidget(button)
        layout.addLayout(row)
        self.summary = QLabel('비교할 곡선을 선택하세요.')
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True); layout.addWidget(self.summary)
        self.details_button = QPushButton('기술 상세')
        self.details_button.setCheckable(True)
        self.details_button.setFlat(True)
        layout.addWidget(self.details_button, alignment=Qt.AlignmentFlag.AlignRight)
        self.detail = QPlainTextEdit(); self.detail.setReadOnly(True); self.detail.setMaximumHeight(160)
        self.detail.setPlainText(json.dumps({'source': self.source}, ensure_ascii=False, indent=2))
        self.detail.hide(); layout.addWidget(self.detail)
        self.details_button.toggled.connect(self.detail.setVisible)
        split = QSplitter(Qt.Orientation.Vertical)
        figure = Figure(constrained_layout=True); self.axes = figure.add_subplot(111)
        self.canvas = FigureCanvasQTAgg(figure); split.addWidget(self.canvas)
        self.values = QTableWidget(0, 7)
        self.values.setHorizontalHeaderLabels(['비교 행', '원본 행', '좌표', '기준 값', '비교 값 (축 정렬)', '비교 가능', '차이 (B − A)'])
        self.values.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.values.setAlternatingRowColors(True)
        self.values.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        split.addWidget(self.values); split.setSizes([420, 240]); layout.addWidget(split, 1)
        self.message = QLabel('기준 곡선을 읽고 있습니다.'); self.message.setWordWrap(True); layout.addWidget(self.message)
        self.setCentralWidget(root)
        self.refresh_button.clicked.connect(self.refresh)
        self.documents.currentIndexChanged.connect(self._document_selected)
        self.jobs.currentIndexChanged.connect(self._job_selected)
        self.responses.currentIndexChanged.connect(self._selection_changed)
        self.saved.currentIndexChanged.connect(self._comparison_selected)
        self.compare_button.clicked.connect(self.compare)
        self.save_button.clicked.connect(self.save)
        self.retry_save.clicked.connect(self.retry_save_receipt)
        self.page_button.clicked.connect(self.read_page)
        self.previous.clicked.connect(lambda: self._move_page(-1))
        self.next.clicked.connect(lambda: self._move_page(1))
        self._actions()

    def _valid(self):
        return not self._closed and (self._parent_relevant is None or self._parent_relevant())

    def _key(self):
        return (self._session, self._serial, self.documents.currentData(), self.jobs.currentData(), self.responses.currentData())

    def _actions(self):
        available = not self._busy and self._valid()
        for widget in (self.documents, self.jobs, self.responses, self.saved, self.start, self.count, self.refresh_button):
            widget.setEnabled(available)
        self.compare_button.setEnabled(available and self.document is not None and self.responses.currentData() is not None and self._save_request is None)
        choice = self.responses.currentData(Qt.ItemDataRole.UserRole + 1)
        self.location_button.setEnabled(available and isinstance(choice, dict) and choice.get('requires_location', False))
        self.save_button.setEnabled(available and self.document is not None and self._save_request is None)
        self.retry_save.setVisible(self._save_request is not None)
        self.retry_save.setEnabled(available and self._save_request is not None)
        for button in (self.page_button, self.previous, self.next):
            button.setEnabled(available and self.saved.currentData() is not None)

    def _call(self, function, accepted, *, relevant=None):
        if self._busy:
            if self._accepting:
                self._queue.append((function, accepted, relevant)); return True
            self.message.setText('자료를 읽고 있습니다. 조회가 끝난 뒤 다시 시도하세요.'); return False
        if not self._valid():
            self.message.setText('원래 창의 자료 선택이 바뀌었습니다. 현재 결과에서 비교 창을 다시 여세요.'); return False
        if relevant is not None and not relevant(): return False
        self._busy = True; self._actions()
        worker = self._worker = _Read(function)
        def finished(value, error):
            self._accepting = True
            try:
                if self._valid() and (relevant is None or relevant()):
                    if error: self.message.setText('처리하지 못했습니다. 선택과 기존 자료는 유지됩니다. ' + error)
                    else: accepted(value)
            finally:
                self._accepting = False; self._busy = False; self._worker = None
            self._actions()
            if self._queue:
                request = self._queue.pop(0)
                self._call(request[0], request[1], relevant=request[2])
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker); return True

    def _accept_owner(self, document):
        if document.get('id') != self.source['document_id'] or document.get('kind') not in KINDS:
            self.message.setText('Comparison receipt belongs to a different domain owner.'); return False
        if self._session is not None and document.get('session_id') != self._session:
            self.message.setText('Source A session changed. Reopen the owner; unresolved receipts are retained.'); return False
        run = next((r for r in document.get('runs', []) if r['job_id'] == self.source['job_id']), None)
        if run is None or any(key in self.source and run.get(key) != self.source[key] for key in ('input_revision', 'input_sha256')):
            self.message.setText('Exact source A run no longer matches this comparison window.'); return False
        self._session = document['session_id']; self.document = deepcopy(document)
        self._remember_document(document)
        self.source_label.setText('기준 곡선: ' + self._source_name(self.source))
        self.source_label.setToolTip(json.dumps(self.source, ensure_ascii=False, indent=2))
        selected = self.saved.currentData()
        self.saved.blockSignals(True); self.saved.clear()
        for item in document.get('comparisons', []):
            binding = item.get('binding', {})
            if not _matches(binding.get('source'), self.source): continue
            b = binding.get('prediction_source', {})
            state = '저장됨' if item.get('retained_revision') else '미저장'
            self.saved.addItem(f"비교 {self.saved.count()+1}: {self._source_name(b)} ({state})", item['id'])
            self.saved.setItemData(self.saved.count()-1, json.dumps(binding, ensure_ascii=False, indent=2), Qt.ItemDataRole.ToolTipRole)
        index = self.saved.findData(selected)
        if index >= 0: self.saved.setCurrentIndex(index)
        self.saved.blockSignals(False)
        return True

    def _remember_document(self, document):
        identifier = document['id']
        self._document_names[identifier] = document.get('title') or '이름 없는 자료'
        for index, run in enumerate(document.get('runs', []), 1):
            self._run_names[(identifier, run['job_id'])] = f'결과 {index}'

    def _source_name(self, source):
        identifier, job = source.get('document_id'), source.get('job_id')
        name = self._document_names.get(identifier, '보관 자료')
        run = self._run_names.get((identifier, job), '보관 결과')
        return f"{name} / {run} / {source.get('response', '물리량')}"

    def refresh(self):
        key = self._key()
        selected_b = (self.documents.currentData(), self.jobs.currentData(), self.responses.currentData())
        selected_choice = deepcopy(self.responses.currentData(Qt.ItemDataRole.UserRole + 1))
        def accepted(payload):
            document, listing = payload
            for row in listing['documents']:
                self._remember_document(row)
            if not self._accept_owner(document): return
            selected = self.documents.currentData()
            self.documents.blockSignals(True); self.documents.clear()
            for row in listing['documents']:
                if row.get('kind') in KINDS:
                    self.documents.addItem(row.get('title') or '이름 없는 자료', row['id'])
                    self.documents.setItemData(self.documents.count()-1, row['id'], Qt.ItemDataRole.ToolTipRole)
            index = self.documents.findData(selected)
            if index >= 0: self.documents.setCurrentIndex(index)
            elif selected is not None: self.documents.setCurrentIndex(-1)
            self.documents.blockSignals(False)
            if selected is not None and index < 0:
                self._document_selected()
                self.message.setText('The explicitly selected B document is no longer available. Select a retained source again.')
                return
            self.message.setText('비교 자료와 물리량을 선택한 뒤 곡선 비교를 누르세요.')
            # Reopen A's retained view before checking B so an old comparison
            # cannot overwrite a later refusal of a changed B identity.
            if self.saved.currentData() is not None: self.read_page()
            self._document_selected(prefer_job=selected_b[1] if self.documents.currentData() == selected_b[0] else None,
                                    prefer_response=selected_b[2] if self.documents.currentData() == selected_b[0] else None,
                                    prefer_choice=selected_choice if self.documents.currentData() == selected_b[0] else None)
        return self._call(lambda: (self.client.document_read(self.source['document_id']), self.client.documents()), accepted, relevant=lambda: self._key() == key)

    def _selection_changed(self, *_):
        self._serial += 1; self._actions()

    def _document_selected(self, *_, prefer_job=None, prefer_response=None, prefer_choice=None):
        self._selection_changed(); identifier = self.documents.currentData()
        self.jobs.blockSignals(True); self.jobs.clear(); self.jobs.blockSignals(False)
        self.responses.blockSignals(True); self.responses.clear(); self.responses.blockSignals(False)
        if identifier is None: return
        key = self._key()
        def accepted(document):
            if document.get('id') != identifier or document.get('session_id') != self._session:
                self.message.setText('B document identity/session changed; refresh sources.'); return
            self._remember_document(document)
            self.jobs.blockSignals(True)
            for run in document.get('runs', []):
                # The result metadata performs the final actual-status check.
                self.jobs.addItem(self._run_names[(identifier, run['job_id'])], run['job_id'])
                self.jobs.setItemData(self.jobs.count()-1, run['job_id'] + '\n' + run.get('input_revision', ''), Qt.ItemDataRole.ToolTipRole)
                self.jobs.setItemData(self.jobs.count()-1, {'document_id': identifier,
                    'session_id': document['session_id'], 'job_id': run['job_id'],
                    **{name: run.get(name) for name in ('input_revision', 'input_sha256')}}, Qt.ItemDataRole.UserRole + 1)
            index = self.jobs.findData(prefer_job)
            if index >= 0: self.jobs.setCurrentIndex(index)
            elif prefer_job is not None:
                self.jobs.setCurrentIndex(-1)
                self.message.setText('The explicitly selected B job is no longer available. Select a retained result again.')
            self.jobs.blockSignals(False)
            self._job_selected(prefer_response=prefer_response, prefer_choice=prefer_choice)
        self._call(lambda: self.client.document_read(identifier), accepted, relevant=lambda: self._key() == key)

    def _job_selected(self, *_, prefer_response=None, prefer_choice=None):
        self._selection_changed()
        self.responses.blockSignals(True); self.responses.clear(); self.responses.blockSignals(False)
        document, job = self.documents.currentData(), self.jobs.currentData()
        if document is None or job is None: return
        key = self._key()
        def accepted(metadata):
            if metadata.get('execution_counts', {}).get('SUCCEEDED', 0) != 1 or metadata.get('execution_counts', {}).get('PREDICTED', 0):
                self.message.setText('B must be an actual successful retained evaluation.'); return
            self.responses.blockSignals(True)
            for choice in response_choices(metadata):
                if choice['definition'].get('kind', 'series') == 'series':
                    self.responses.addItem(choice['label'], choice['selector'])
                    self.responses.setItemData(self.responses.count()-1, choice, Qt.ItemDataRole.UserRole + 1)
            index = self.responses.findData(prefer_response)
            if index >= 0: self.responses.setCurrentIndex(index)
            elif prefer_response is not None:
                # Exact native locations are not flattened into the channel
                # catalog. Revalidate the previous location before selecting it.
                self.responses.setCurrentIndex(-1)
            self.responses.blockSignals(False); self._selection_changed()
            if prefer_response is not None and index < 0:
                self._restore_location(prefer_response, prefer_choice)
            if not self.responses.count(): self.message.setText('This retained result advertises no selectable curve.')
        self._call(lambda: self.client.document_result_metadata(document, job), accepted, relevant=lambda: self._key() == key)

    def _add_location(self, selected):
        selected = deepcopy(selected)
        selected['_retained_input'] = deepcopy(self.jobs.currentData(Qt.ItemDataRole.UserRole + 1))
        self.responses.addItem(selected['selector'] + ' [' + selected['definition'].get('unit', '?') + ']', selected['selector'])
        self.responses.setItemData(self.responses.count()-1, selected, Qt.ItemDataRole.UserRole + 1)
        self.responses.setCurrentIndex(self.responses.count()-1)

    def _restore_location(self, selector, previous):
        if not isinstance(previous, dict) or not previous.get('channel'):
            self.message.setText('The selected B response is no longer advertised. Select a retained response again.'); return
        choice = None
        for index in range(self.responses.count()):
            item = self.responses.itemData(index, Qt.ItemDataRole.UserRole + 1)
            if isinstance(item, dict) and item.get('channel') == previous['channel']:
                choice = item
                break
        binding = self.jobs.currentData(Qt.ItemDataRole.UserRole + 1)
        if (choice is None or previous.get('_retained_input') != binding
                or choice['definition'] != previous.get('definition')):
            self.message.setText('B input or response identity changed. Select the exact retained location again.'); return
        key = self._key(); document, job = self.documents.currentData(), self.jobs.currentData()
        def locate():
            start = 0
            while True:
                page = self.client.document_response_locations(document, job, choice['channel'], start=start, count=128, search=selector)
                if ((page.get('document_id'), page.get('job_id'), page.get('channel'), page.get('start'))
                        != (document, job, choice['channel'], start)
                        or page.get('source') != choice['definition'].get('source', {})):
                    raise ValueError('Location reply identity differs from the selected retained result')
                if any(row.get('selector') == selector for row in page['locations']):
                    return {**choice, 'selector': selector, 'requires_location': False}
                following = page.get('next_start')
                if following is None: return None
                if type(following) is not int or following <= start:
                    raise ValueError('Invalid retained location page sequence')
                start = following
        def accepted(selected):
            if selected is None:
                self.message.setText('The exact B location is no longer available. Select a retained location again.')
            else:
                self._add_location(selected)
        self._call(locate, accepted, relevant=lambda: self._key() == key)

    def choose_response_location(self):
        choice = self.responses.currentData(Qt.ItemDataRole.UserRole + 1)
        if not isinstance(choice, dict) or not choice.get('requires_location') or self._busy: return
        key = self._key()
        try:
            selected = choose_location(self, self.client, self.documents.currentData(), self.jobs.currentData(),
                                       choice, relevant=lambda: self._valid() and self._key() == key)
            if selected is not None and self._key() == key:
                self._add_location(selected)
        except (ValueError, TypeError, KeyError) as error:
            self.message.setText(str(error))

    def compare(self):
        if self._save_request is not None: return
        b = dict(document_id=self.documents.currentData(), job_id=self.jobs.currentData(), response=self.responses.currentData())
        if any(value is None for value in b.values()): return
        key = self._key(); source = deepcopy(self.source)
        def accepted(payload):
            if not _matches(payload.get('binding', {}).get('source'), source) or not _matches(payload.get('binding', {}).get('prediction_source'), b):
                self.message.setText('Comparison reply identity differs from the explicitly selected curves.'); return
            self._display(payload)
            def owner_read(document):
                if self._accept_owner(document):
                    self.saved.blockSignals(True); self.saved.setCurrentIndex(self.saved.findData(payload['id'])); self.saved.blockSignals(False)
                    self.message.setText('비교 결과를 만들었습니다. 비교 저장을 눌러 기준 자료와 함께 저장하세요.')
                    self.start.setValue(0); self.read_page()
            self._call(lambda: self.client.document_read(source['document_id']), owner_read, relevant=lambda: self._key() == key)
        session = self._session
        def retained_compare():
            if self.client.document_read(source['document_id']).get('session_id') != session:
                raise ValueError('Source A session changed; reopen before comparing')
            return self.client.document_compare(source, b)
        return self._call(retained_compare, accepted, relevant=lambda: self._key() == key)

    def _comparison_selected(self, *_):
        self.start.setValue(0); self.read_page()

    def _move_page(self, direction):
        self.start.setValue(max(0, self.start.value() + direction * self.count.value())); self.read_page()

    def read_page(self):
        identifier = self.saved.currentData()
        if identifier is None: return
        start, count = self.start.value(), self.count.value(); session = self._session
        def accepted(payload):
            if payload.get('id') != identifier or not _matches(payload.get('binding', {}).get('source'), self.source):
                self.message.setText('Stored comparison identity differs from source A.'); return
            self._display(payload)
        def retained_page():
            if self.client.document_read(self.source['document_id']).get('session_id') != session:
                raise ValueError('Source A session changed; reopen before reading its comparison')
            return self.client.document_comparison(self.source['document_id'], identifier, start=start, count=count)
        return self._call(retained_page, accepted,
            relevant=lambda: self._session == session and self.saved.currentData() == identifier and (self.start.value(), self.count.value()) == (start, count))

    def _display(self, payload):
        comparison = payload['comparison']; observation = comparison['observation']; page = payload['page']
        axes = observation.get('axes', [])
        if observation.get('kind') != 'series' or len(axes) != 1:
            self.message.setText('Stored comparison does not contain one declared curve axis.'); return
        a, b, mask = observation['value'], comparison['prediction'], comparison['mask']
        x = axes[0]['values']; size = len(a)
        if not (len(x) == len(b) == len(mask) == size <= 4096 and size == page['count']):
            self.message.setText('Invalid or unbounded comparison page; previous view preserved.'); return
        rows = comparison.get('observation_source_rows') or observation.get('source_rows', [])
        if rows and len(rows) != size:
            self.message.setText('Original row identity does not match the comparison page.'); return
        a_mask = observation.get('mask', [True] * size)
        if len(a_mask) != size:
            self.message.setText('Original A validity mask does not match the comparison page; previous view preserved.'); return
        self._comparison = deepcopy(payload)
        unit = str(comparison.get('unit', observation.get('unit', '')))
        rmse = comparison.get('rmse')
        error = format(rmse, '.6g') if _number(rmse) else '계산 안 됨'
        shown = (f"표시 행 {page['start']}–{page['start'] + size - 1}" if size else
                 '표시할 행이 없습니다. 시작 행을 바꾸세요.')
        self.summary.setText('표시 중인 비교: ' + self._source_name(payload['binding'].get('prediction_source', {})) +
            f"\nRMSE {error} {unit}    비교 가능 {comparison.get('count', '?')}개    {shown}")
        self.detail.setPlainText(json.dumps({'comparison_id': payload['id'], 'binding': payload['binding'],
            'method': comparison.get('method'), 'alignment_policy': comparison.get('alignment_policy'),
            'unit': comparison.get('unit'), 'rmse': comparison.get('rmse'), 'count': comparison.get('count'),
            'A_declarations': {k: observation[k] for k in ('component', 'location', 'measure', 'frame') if k in observation},
            'B_declarations': comparison.get('prediction_metadata', {}), 'page': page}, ensure_ascii=False, indent=2))
        self.values.setRowCount(size)
        for i in range(size):
            delta = b[i] - a[i] if mask[i] and _number(a[i]) and _number(b[i]) else None
            entries = [page['start'] + i, rows[i] if rows else None, x[i], a[i], b[i], bool(mask[i]), delta]
            for column, value in enumerate(entries):
                text = ('—' if value is None else ('가능' if value else '제외') if column == 5 else
                        format(value, '.8g') if _number(value) else str(value))
                item = QTableWidgetItem(text)
                item.setToolTip(str(value) if value is not None else '값 없음')
                self.values.setItem(i, column, item)
        self.axes.clear()
        segments = comparison.get('observation_segments') or observation.get('segments') or [{'rows': [page['start'], page['start'] + size]}]
        for series, values, valid, color in [('기준 곡선 A', a, a_mask, 'C0'), ('기준축에 맞춘 B', b, mask, 'C1')]:
            labelled = False
            for segment in segments:
                low, high = segment['rows']; low = max(0, low - page['start']); high = min(size, high - page['start'])
                if low >= high: continue
                y = [values[i] if i < len(valid) and valid[i] and _number(values[i]) else math.nan for i in range(low, high)]
                self.axes.plot(x[low:high], y, marker='.', color=color, label=None if labelled else series)
                labelled = True
        self.axes.set_xlabel(str(axes[0].get('name', '?')) + ' [' + str(axes[0].get('unit', '?')) + ']')
        self.axes.set_ylabel('[' + str(observation.get('unit', '?')) + ']')
        if self.axes.lines: self.axes.legend()
        self.axes.grid(True, alpha=.2); self.canvas.draw_idle()
        self.message.setText(f"전체 {page['total']}행 중 {size}행을 표시합니다. 차이는 비교 가능한 표본에서만 계산합니다.")

    def save(self):
        if self._save_request is not None: return
        session = self._session
        def accepted(document):
            if not self._accept_owner(document) or document['session_id'] != session: return
            self._save_request = dict(identifier=self.source['document_id'], operation='document.save', arguments={},
                session_id=session, expected_generation=document['generation'], command_id='C' + uuid.uuid4().hex)
            self._send_save()
        return self._call(lambda: self.client.document_read(self.source['document_id']), accepted)

    def _send_save(self):
        request = deepcopy(self._save_request)
        def accepted(receipt):
            if receipt.get('command_id') != request['command_id'] or not self._accept_owner(receipt.get('document', {})):
                self.message.setText('Save receipt identity is unconfirmed. The exact pending request is retained.'); return
            self._save_request = None
            self.message.setText('기준 자료에 비교를 저장했습니다. 다시 열면 계산 없이 같은 곡선을 읽습니다.')
        return self._call(lambda: self.client.document_command(**request), accepted)

    def retry_save_receipt(self):
        if self._save_request is None: return
        request = deepcopy(self._save_request)
        def accepted(document):
            if document.get('session_id') != request['session_id'] or document.get('id') != request['identifier']:
                self.message.setText('Save receipt remains unresolved after an owner/session change. No rebased Save was submitted.'); return
            self._send_save()
        return self._call(lambda: self.client.document_read(request['identifier']), accepted)

    def closeEvent(self, event):
        self._closed = True; self._queue.clear(); super().closeEvent(event)
