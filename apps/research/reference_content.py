"""Read-only presentation of the existing exact research-reference payload."""
from copy import deepcopy
from html import escape
import json
import math

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QSplitter, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from .runner_window import readonly_table, table_row, text_value
from .discussion_view import turn_text, author_label
from .law_native_labels import response_label


def pde_input_html(draft):
    """Read the resolved saved input only; never consult its current owner."""
    from .pde_window import display, setting_label
    settings = draft.get('settings')
    if not isinstance(settings, dict):
        return None
    sections = {'states': '상태', 'parameters': '계수', 'time': '시간', 'solver': '계산 설정',
        'domain': '영역', 'space': '함수 공간', 'mesh': '메시', 'forms': '약형식',
        'boundaries': '경계 조건', 'initial': '초기 조건', 'field': '장',
        'reference': '독립 기준식', 'validation': '기준 검사', 'problem': '방정식'}
    rows = []
    def visit(value, path=(), context=()):
        if isinstance(value, dict):
            for key, item in value.items():
                group = context + (sections.get(key, str(key)),) if not path else context
                visit(item, path + (key,), group)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                name = item.get('label') or item.get('name') if isinstance(item, dict) else None
                visit(item, path + (index,), context + (str(name or index + 1),))
        else:
            caption = ' / '.join(context + (setting_label(('settings',) + path),))
            text = '미제공' if value is None else display(value)
            rows.append('<tr><td>' + escape(caption) + '</td><td>' + escape(text) + '</td></tr>')
    visit(settings)
    return ('<p>선택한 저장본의 입력입니다. 현재 편집 중인 모델과 별도로 읽습니다.</p>'
        '<table width="100%" cellpadding="5"><tr><th align="left">항목</th>'
        '<th align="left">저장된 값</th></tr>' + ''.join(rows) + '</table>')


def evaluation_input_html(draft):
    """Describe only the resolved definition; stage links retain exact revisions."""
    stages = draft.get('stages', [])
    names = {row['id']: row['name'] for row in stages}
    text = ['<p>선택한 저장본의 계산 절차입니다. 현재 편집 중인 모델과 별도로 읽습니다.</p>', '<h3>계산 단계</h3><ol>']
    kinds = {'pde': 'PDE', 'material': '재료', 'simulation': '해석'}
    for index, row in enumerate(stages):
        kind = kinds.get(row['source']['kind'], '분야')
        text.append('<li>' + escape(row['name']) + ' — <a href="saved-stage:' + str(index) + '">' + kind + ' 저장 입력 열기</a></li>')
    text.append('</ol>')
    def table(title, headers, rows):
        if rows:
            text.extend(['<h3>' + title + '</h3><table width="100%" cellpadding="5"><tr>',
                ''.join('<th align="left">' + escape(header) + '</th>' for header in headers), '</tr>'])
            for row in rows:
                text.append('<tr>' + ''.join('<td>' + escape(str(value)) + '</td>' for value in row) + '</tr>')
            text.append('</table>')
    from caelab.evaluation_shared_inputs import targets
    table('입력 연결', ['입력', '단계 입력', '단위', '저장값'], [
        [row.get('label', row['id']), ', '.join(names.get(target['stage'], target['stage']) + ' / ' + target['input_id']
            for target in targets(row)), row['unit'], row.get('value', '단계 저장본에서 확인')]
        for row in draft.get('bindings', [])])
    table('결과', ['이름', '단계', '응답', '단위'], [
        [row['id'], names.get(row['stage'], row['stage']), row['response'], row['unit']]
        for row in draft.get('responses', [])])
    iteration = draft.get('iteration', {})
    text.append('<p>' + ('반복 계산: 최대 ' + str(iteration.get('maximum')) + '회' if iteration.get('enabled') else '순차 계산') + '</p>')
    table('반복 수렴 기준', ['단계', '응답', '단위', '절대 한계', '상대 한계', '기준 크기'], [
        [names.get(row['stage'], row['stage']), row['response'], row['unit'], row['absolute'], row['relative'], row['scale']]
        for row in iteration.get('checks', [])])
    return ''.join(text)


class ReferenceContent(QWidget):
    response_requested = Signal(str)
    saved_reference_requested = Signal(object)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.payload = None
        self._rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel('자료·계산 결과')
        self.title.setWordWrap(True)
        font = self.title.font(); font.setBold(True); self.title.setFont(font)
        layout.addWidget(self.title)
        choices = QHBoxLayout()
        self.channel = QComboBox(); self.channel.setObjectName('evidenceChannel')
        self.channel.currentIndexChanged.connect(self._draw_result)
        self.read = QPushButton('결과 읽기')
        self.read.clicked.connect(lambda: self.response_requested.emit(str(self.channel.currentData())))
        self.candidate = QComboBox(); self.candidate.setObjectName('evidenceCandidate')
        self.candidate.currentIndexChanged.connect(self._draw_result)
        choices.addWidget(self.channel, 2); choices.addWidget(self.read)
        choices.addWidget(self.candidate, 1)
        self.details = QPushButton('진단 상세…')
        self.details.clicked.connect(self.show_details)
        choices.addWidget(self.details)
        layout.addLayout(choices)
        self.body = QTextBrowser()
        self.body.setObjectName('evidenceBody')
        self.body.setOpenExternalLinks(False)
        self.body.setOpenLinks(False)
        self.body.anchorClicked.connect(self._open_saved_stage)
        self.body.setMinimumHeight(120)
        self.result_views = QTabWidget()
        self.figure = Figure(figsize=(6, 3), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(111)
        self.values = readonly_table(['위치', '값', '단위', '사용 여부'])
        self.values.setObjectName('evidenceValues')
        self.result_views.addTab(self.canvas, '그래프')
        self.result_views.addTab(self.values, '표')
        layout.addWidget(self.body, 1)
        layout.addWidget(self.result_views, 2)
        self.clear('읽을 자료나 계산 결과를 선택하세요.')

    def clear(self, message=''):
        self.payload = None
        self.details.hide()
        self.title.setText('자료·계산 결과')
        self.body.setPlainText(message)
        self.body.show()
        for widget in (self.channel, self.read, self.candidate, self.result_views):
            widget.hide()
        self.values.setRowCount(0)
        self.axes.clear()
        self.canvas.draw_idle()

    def set_payload(self, payload, *, label='자료·계산 결과'):
        self.clear()
        self.payload = deepcopy(payload)
        self.details.show()
        self.title.setText(label)
        if payload.get('status') != 'AVAILABLE':
            self.body.setPlainText(str(payload.get('message') or '자료를 읽을 수 없습니다.'))
            return
        kind = payload.get('kind')
        analysis = kind == 'result' and (payload.get('result') or {}).get('kind') in {
            'experiment_uncertainty', 'experiment_identification'}
        if kind == 'numerical_candidate_evidence' or analysis:
            # Reuse the Report renderer on the exact resolved saved snapshot.
            # This is presentation only: no current owner, evaluator or command.
            from .report_pages import compose
            draft={'title':'보존한 시험 분석' if analysis else '보고서에 저장한 계산', 'sections':[{
                'id':'Eview','title':'시험 분석 결과' if analysis else '선택 후보 결과','text':'',
                'include':True,'table':True,'curve':True,'asset':{'id':'Aview'}}]}
            document=compose(draft,{'Aview':{'source_status':'AVAILABLE',
                'content':payload}},self.body.font())
            if analysis:
                document.setDocumentMargin(6)
                cursor=QTextCursor(document)
                # The host already names this source. Remove only compose's
                # three generated heading/text blocks, keeping result content.
                cursor.setPosition(document.findBlockByNumber(3).position(),
                    QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
            document.setParent(self.body)
            previous=getattr(self,'_candidate_document',None)
            self.body.setDocument(document)
            self._candidate_document=document
            if previous is not None:previous.deleteLater()
            self._fit_analysis_document()
            return
        if kind == 'comparison':
            from .report_pages import blocks,value_text
            lines=[]
            for block,value in blocks(payload):
                if block=='paragraph':lines.append(value)
                elif block=='table':
                    headers,rows=value
                    lines.append(' | '.join(headers))
                    lines.extend(' | '.join(value_text(v) for v in row) for row in rows)
            self.body.setPlainText('\n'.join(lines)); return
        if kind in {'native_pre', 'native_post'}:
            from .report_pages import blocks
            self.title.setText('FreeCAD 모델 저장본' if kind == 'native_pre' else 'ParaView 결과 저장본')
            self.body.setPlainText('\n'.join(value for block, value in blocks(payload) if block == 'paragraph'))
            return
        if kind == 'knowledge':
            source = payload['source']
            self.title.setText(source.get('title', label))
            from .portable_research_actions import source_description
            self.body.setPlainText(source_description(payload))
            return
        if kind == 'expert_turn':
            turn = payload['turn']
            self.title.setText(author_label(turn) + ' — ' + str((turn.get('topic') or {}).get('title', label)))
            self.body.setPlainText(turn_text(turn))
            return
        if kind == 'document':
            document = payload['document']
            self.title.setText(document.get('title', label))
            draft = document.get('draft', {})
            if document.get('kind') == 'pde' and isinstance(draft, dict):
                html = pde_input_html(draft)
                if html is not None:
                    self.body.setHtml(html)
                    return
            if document.get('kind') == 'evaluation' and isinstance(draft, dict):
                self.body.setHtml(evaluation_input_html(draft))
                return
            texts = []
            for key in ('question', 'purpose', 'description', 'notes'):
                if isinstance(draft.get(key), str) and draft[key]:
                    texts.append(draft[key])
            if isinstance(draft.get('composer'), dict) and draft['composer'].get('text'):
                texts.append(draft['composer']['text'])
            self.body.setPlainText('\n\n'.join(texts) or '원래 프로그램에서 저장된 모델을 열어 확인하세요.')
            return
        if kind == 'job':
            job = payload.get('job') or {}
            self.title.setText('계산 상태')
            self.body.setPlainText(str(job.get('state', job.get('status', 'UNKNOWN'))) +
                '\n' + str(job.get('operation', '')) + '\n' + str(job.get('error') or ''))
            return
        if kind != 'result':
            self.body.setPlainText('이 자료는 원래 프로그램에서 열어 확인하세요.')
            return
        metadata = payload.get('metadata') or {}
        def caption(name):return response_label(name,payload.get('result') or {}) or name
        selection=(payload.get('reference') or {}).get('selection')
        if isinstance(selection,dict) and selection.get('schema')=='caelab.impact-history-selection/1':
            # The saved selection owns its channel and transformed unit.
            metadata={}
        self.channel.blockSignals(True)
        self.channel.clear()
        for item in metadata.get('responses', []):
            name = item.get('response')
            if name:
                self.channel.addItem(caption(name) + ' [' + str(item.get('unit', '단위 미확인')) + ']', name)
        for name, item in metadata.get('native_channels', {}).items():
            if not item.get('requires_location') and self.channel.findData(name) < 0:
                self.channel.addItem(caption(name) + ' [' + str(item.get('unit', '단위 미확인')) + ']', name)
        result = payload.get('result') or {}
        self._result = result
        self._rows = result.get('candidates', result.get('predictions', []))
        for row in ([result] + self._rows):
            for name, response in (row.get('responses') or {}).items():
                if self.channel.findData(name) < 0:
                    self.channel.addItem(caption(name) + ' [' + str(response.get('unit', '단위 미확인')) + ']', name)
        available = (self._rows[0].get('responses') or {}) if self._rows else (result.get('responses') or {})
        if available:
            self.channel.setCurrentIndex(self.channel.findData(next(iter(available))))
        self.channel.blockSignals(False)
        self.channel.setVisible(self.channel.count() > 0)
        self.read.setVisible(self.channel.count() > 0)
        self.candidate.blockSignals(True)
        self.candidate.clear()
        for index, row in enumerate(self._rows):
            self.candidate.addItem('후보 ' + str(index + 1) + ' — ' +
                {'SUCCEEDED': '계산 완료', 'FAILED': '계산 실패', 'CANCELLED': '취소', 'UNKNOWN': '미확인'}.get(
                    row.get('execution_status', row.get('prediction_status', 'UNKNOWN')),
                    str(row.get('execution_status', row.get('prediction_status', 'UNKNOWN')))), index)
        self.candidate.blockSignals(False)
        self.candidate.setVisible(bool(self._rows))
        self._draw_result()

    def _open_saved_stage(self, url):
        payload = self.payload or {}
        document = payload.get('document', {})
        if payload.get('status') != 'AVAILABLE' or document.get('kind') != 'evaluation' or url.scheme() != 'saved-stage':
            return
        index = url.path()
        stages = document.get('draft', {}).get('stages', [])
        if not index.isdecimal() or int(index) >= len(stages):
            return
        source = stages[int(index)]['source']
        from caelab.evaluation_definition import check_reference
        check_reference(source)
        self.saved_reference_requested.emit(dict(kind='document', document_kind=source['kind'],
            **{key: source[key] for key in ('document_id', 'saved_revision', 'input_revision', 'input_sha256')}))

    def _fit_analysis_document(self):
        payload=self.payload or {}
        if payload.get('kind')=='result' and (payload.get('result') or {}).get('kind') in {
                'experiment_uncertainty','experiment_identification'}:
            self.body.document().setTextWidth(max(240,self.body.viewport().width()-8))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        QTimer.singleShot(0,self._fit_analysis_document)

    def _draw_result(self, *_):
        if not self.payload or self.payload.get('kind') != 'result':
            return
        source = self._rows[max(0, self.candidate.currentIndex())] if self._rows else self._result
        responses = source.get('responses') or {}
        if not responses and source.get('response_reductions'):
            from .experiment_labels import REDUCTIONS
            reductions=source['response_reductions']
            self.values.setRowCount(len(reductions))
            for index,row in enumerate(reductions):
                table_row(self.values,index,[row['response']+' / '+
                    REDUCTIONS.get(row.get('reduction'),str(row.get('reduction'))),
                    text_value(row.get('value')),row.get('unit','미확인'),
                    '보존된 축약값'])
            self.body.setPlainText('선택 후보에 저장된 축약값입니다. 원 곡선은 이 선택에 포함되지 않습니다.')
            self.body.show();self.result_views.show();self.result_views.setCurrentWidget(self.values)
            return
        if not responses:
            reason = source.get('failure_reason') or source.get('error') or '계산 결과에서 읽을 값을 선택하세요.'
            self.body.setPlainText(str(reason))
            self.body.show(); self.result_views.hide()
            return
        # A previously selected exact response remains the displayed response.
        name = self.channel.currentData()
        if name not in responses:
            self.values.setRowCount(0)
            self.axes.clear()
            self.canvas.draw_idle()
            self.title.setText(str(name or '계산 결과'))
            self.body.setPlainText('선택한 값은 아직 읽지 않았습니다. 결과 읽기 또는 원래 프로그램에서 여세요.')
            self.body.show(); self.result_views.hide()
            return
        response = responses[name]
        caption=response_label(name,source) or name
        unit = str(response.get('unit', '단위 미확인'))
        labels = [str(response['component'])] if isinstance(response.get('component'), (str, int, float)) else []
        # Frame/measure identifiers remain exact in Details. They are not titles.
        location = response.get('location')
        if isinstance(location, str):
            labels.append(location)
        elif isinstance(location, dict) and isinstance(location.get('label'), str):
            labels.append(location['label'])
        self.title.setText(caption + ' [' + unit + ']' + (' — ' + ' / '.join(labels) if labels and caption==name else ''))
        self.result_views.show()
        self.values.setRowCount(0)
        self.axes.clear()
        value = response.get('value')
        if response.get('kind') == 'scalar':
            self.values.setRowCount(1)
            table_row(self.values, 0, ['계산값', text_value(value), unit,
                '유효하지 않음' if response.get('valid') is False else ''])
            self.body.setPlainText(text_value(value) + ' ' + unit)
            self.body.show()
            self.result_views.setCurrentWidget(self.values)
            return
        axes = response.get('axes') or []
        if (response.get('kind') != 'series' or not isinstance(value, list) or len(axes) != 1
                or not isinstance(axes[0].get('values'), list) or len(axes[0]['values']) != len(value)):
            self.body.setPlainText('이 결과는 위치를 선택해야 합니다. 원래 결과 창에서 여세요.')
            self.body.show(); self.result_views.hide()
            return
        axis, mask = axes[0], response.get('mask')
        if mask is not None and (not isinstance(mask, list) or len(mask) != len(value)
                                 or any(type(item) is not bool for item in mask)):
            self.body.setPlainText('저장된 유효성 정보가 올바르지 않아 그래프를 그릴 수 없습니다. 원래 결과를 확인하세요.')
            self.body.show(); self.result_views.hide()
            return
        self.values.setRowCount(len(value))
        plotted_x, plotted_y = [], []
        breaks=set()
        covered=None
        segments=response.get('segments')
        if segments is not None:
            covered=set()
            for segment in segments:
                bounds=segment.get('rows') if isinstance(segment,dict) else None
                if (not isinstance(bounds,list) or len(bounds)!=2
                        or any(type(v) is not int for v in bounds) or not 0<=bounds[0]<bounds[1]<=len(value)):
                    self.body.setPlainText('저장된 연속 구간이 올바르지 않습니다. 원 결과를 확인하세요.')
                    self.body.show();self.result_views.hide();return
                if bounds[0]:breaks.add(bounds[0])
                covered.update(range(*bounds))
        published=response.get('source_rows',[])
        raw=response.get('raw_samples',{})
        raw_rows=raw.get('source_rows',[])
        raw_lookup=({row:i for i,row in enumerate(raw_rows)}
                    if isinstance(raw_rows,list) and all(type(row) is int for row in raw_rows) else {})
        for index, (x, y) in enumerate(zip(axis['values'], value)):
            included = mask[index] if mask is not None else None
            if covered is not None and index not in covered:included=False
            source_row=published[index] if len(published)==len(value) else None
            raw_index=raw_lookup.get(source_row)
            if raw_index is not None:
                for key in ('quality_valid','calculation_valid'):
                    flags=raw.get(key,[])
                    if len(flags)==len(raw_rows) and flags[raw_index] is False:included=False
                gaps=raw.get('gap_before',[])
                if len(gaps)==len(raw_rows) and gaps[raw_index]:breaks.add(index)
            if index and len(published)==len(value) and published[index]!=published[index-1]+1:breaks.add(index)
            table_row(self.values, index, [text_value(x) + ' ' + str(axis.get('unit', '')),
                text_value(y), unit, included if included is not None else '미지정'])
            finite = (type(x) in (int, float) and type(y) in (int, float)
                      and math.isfinite(x) and math.isfinite(y))
            if index in breaks and index:
                plotted_x.append(math.nan);plotted_y.append(math.nan)
            plotted_x.append(x if finite else math.nan)
            plotted_y.append(y if finite and included is not False and response.get('valid') is not False else math.nan)
        self.axes.plot(plotted_x, plotted_y, marker='o', markersize=3)
        self.axes.set_xlabel(str(axis.get('name', '위치')) + ' [' + str(axis.get('unit', '단위 미확인')) + ']')
        self.axes.set_ylabel(caption + ' [' + unit + ']')
        self.axes.grid(True, alpha=.2)
        self.canvas.draw_idle()
        self.body.setPlainText('누락되거나 제외된 값은 그래프에서 끊어 표시합니다.' if
            any(not math.isfinite(item) for item in plotted_y) else '')
        self.body.setVisible(bool(self.body.toPlainText()))
        self.result_views.setCurrentWidget(self.canvas)


    def show_details(self):
        if self.payload is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('계산·자료 진단 상세')
        dialog.resize(760, 560)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(json.dumps(self.payload, ensure_ascii=False, indent=2))
        text.setReadOnly(True)
        layout.addWidget(text)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()
