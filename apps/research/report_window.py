"""Independent native report editor with frozen sources and real print pages."""
from copy import deepcopy
import argparse
import json
from pathlib import Path
import sys
import uuid

from PySide6.QtCore import QThreadPool, Qt, Slot, QTimer
from PySide6.QtGui import QAction, QKeySequence, QPageSize
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewWidget
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QSpinBox, QToolBar, QVBoxLayout, QWidget)

from caelab.report_document import default_draft, diagnostics
from caelab.storage import canonical_hash
from caelab.workbench_client import Client
from .data_window import _Read
from .appearance import apply_appearance, configure_plot_fonts
from .report_pages import compose, markdown, atomic_export, pdf_document, value_text
from .experiment_labels import REDUCTIONS


def section(title, *, text='', asset=None):
    return {'id': 'E'+uuid.uuid4().hex, 'title': title, 'text': text,
            'include': True, 'table': True, 'curve': True, 'asset': deepcopy(asset)}


class ReportWindow(QMainWindow):
    def __init__(self, client, *, document_id=None, reference=None, auto_open=True):
        super().__init__()
        self.client = client
        self.document = None
        self.draft = default_draft()
        self.assets = {}
        self._workers = []
        self._busy = self._closed = self._populating = False
        self._undo, self._redo = [], []
        self._pending = None
        self._initial_reference = deepcopy(reference)
        self._children = []
        self._edit_buffers = {}
        self._editing_section = None
        self._build_ui()
        if auto_open:
            self.open_document(document_id)

    def _build_ui(self):
        configure_plot_fonts()
        self.resize(1100, 780); self.setMinimumSize(850, 620)
        self.setWindowTitle('보고서')
        files = self.menuBar().addMenu('파일(&F)')
        edit = self.menuBar().addMenu('편집(&E)')
        source = self.menuBar().addMenu('자료(&S)')
        bar = QToolBar('보고서', self); bar.setMovable(False); self.addToolBar(bar)
        def action(label, callback, menu, shortcut=None, primary=False):
            a = QAction(label, self)
            if shortcut: a.setShortcut(shortcut)
            a.triggered.connect(callback); menu.addAction(a)
            if primary: bar.addAction(a)
            return a
        action('새 보고서', self.new_document, files, QKeySequence.New)
        action('열기…', self.choose_document, files, QKeySequence.Open)
        action('저장', self.save_document, files, QKeySequence.Save, True)
        action('PDF 내보내기…', lambda: self.export('pdf'), files, primary=True)
        action('Markdown 내보내기…', lambda: self.export('md'), files)
        action('닫기', self.close, files, QKeySequence.Close)
        action('실행 취소', self.undo, edit, QKeySequence.Undo, True)
        action('다시 실행', self.redo, edit, QKeySequence.Redo)
        action('설명 추가', lambda: self.append_section(section('설명')), edit)
        action('계산 결과 추가…', self.choose_result, source, primary=True)
        from .report_image_dialog import choose_image, edit_image
        action('3D 결과 이미지 추가…', lambda: choose_image(self), source)
        action('선택 이미지 교체…', lambda: choose_image(self, replace=True), source)
        action('이미지 표시와 크기…', lambda: edit_image(self), edit)
        action('저장된 연구 적용…', self.choose_study, source)
        action('문헌 추가…', self.choose_literature, source)
        action('원자료 열기', self.open_source, source)
        action('자료 다시 확인', self.read_assets, source)
        def candidate_diagnostics():
            from .numerical_candidate_evidence_report import show_candidate_diagnostics
            show_candidate_diagnostics(self)
        action('선택 결과 진단…', candidate_diagnostics, source)
        action('전송 다시 시도', self.retry, files)
        action('서버 저장 상태 확인…', self.reconcile, files)
        center = QWidget(); root = QVBoxLayout(center); self.setCentralWidget(center)
        self.title = QLineEdit(self.draft['title']); self.title.setPlaceholderText('보고서 제목')
        self.title.editingFinished.connect(self.edit_title); root.addWidget(self.title)
        splitter = QSplitter()
        left = QWidget(); outline = QVBoxLayout(left); outline.setContentsMargins(0,0,0,0)
        self.sections = QListWidget(); self.sections.currentRowChanged.connect(self.selected)
        self.sections.itemChanged.connect(self.include_section); outline.addWidget(self.sections, 1)
        row = QHBoxLayout()
        for label, fn in [('위로', lambda: self.move(-1)), ('아래로', lambda: self.move(1)), ('삭제', self.remove)]:
            button = QPushButton(label); button.clicked.connect(fn); row.addWidget(button)
        outline.addLayout(row)
        self.edit_button = QPushButton('선택 섹션 편집…'); self.edit_button.clicked.connect(self.edit_section)
        outline.addWidget(self.edit_button)
        self.printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        self.printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4)); self.printer.setFullPage(True)
        self.preview = QPrintPreviewWidget(self.printer)
        self.preview.paintRequested.connect(self.paint)
        pages = QWidget(); page_layout = QVBoxLayout(pages); page_layout.setContentsMargins(0,0,0,0)
        navigation = QHBoxLayout()
        for label, callback in [('원자료 열기', self.open_source),
                                ('이전 페이지', lambda: self.move_page(-1)),
                                ('다음 페이지', lambda: self.move_page(1))]:
            button = QPushButton(label); button.clicked.connect(callback); navigation.addWidget(button)
        self.page_fit = QComboBox()
        self.page_fit.addItems(['페이지 맞춤', '너비 맞춤'])
        self.page_fit.setToolTip('전체 페이지를 보거나 본문 너비를 확대합니다.')
        self.page_fit.currentIndexChanged.connect(self.fit_preview)
        navigation.addWidget(self.page_fit)
        self.page_label = QLabel(); navigation.addWidget(self.page_label)
        page_layout.addLayout(navigation); page_layout.addWidget(self.preview,1)
        self.preview.previewChanged.connect(self.update_page_label)
        from PySide6.QtWidgets import QGraphicsView
        view = self.preview.findChild(QGraphicsView)
        if view is not None:
            view.verticalScrollBar().valueChanged.connect(lambda _: QTimer.singleShot(0, self.update_page_label))
        splitter.addWidget(left); splitter.addWidget(pages)
        splitter.setStretchFactor(0,0); splitter.setStretchFactor(1,1); splitter.setSizes([215,850])
        root.addWidget(splitter,1)
        self.section_editor = QWidget()
        editor = QVBoxLayout(self.section_editor); editor.setContentsMargins(0,0,0,0)
        self.section_title = QLineEdit(); editor.addWidget(self.section_title)
        self.section_text = QPlainTextEdit(); self.section_text.setMaximumHeight(95); editor.addWidget(self.section_text)
        commands = QHBoxLayout()
        self.section_table = QCheckBox('표'); self.section_curve = QCheckBox('곡선')
        commands.addWidget(self.section_table); commands.addWidget(self.section_curve)
        for label,callback in [('설명 적용',self.apply_section),('수정 취소',self.cancel_section),('닫기',self.close_editor)]:
            button=QPushButton(label);button.clicked.connect(callback);commands.addWidget(button)
        editor.addLayout(commands);root.addWidget(self.section_editor);self.section_editor.hide()
        self.message = QLabel('자료를 추가하거나 설명을 작성하세요.'); self.message.setWordWrap(True)
        self.statusBar().addWidget(self.message,1)
        self._page = None

    def _call(self, function, accepted):
        if self._busy or self._closed:
            return False
        self._busy = True
        self._accepted = accepted
        worker = _Read(function); self._workers.append(worker)
        worker.signals.finished.connect(self._finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    @Slot(object, object)
    def _finished(self, value, error):
        sender = self.sender()
        self._workers = [w for w in self._workers if w.signals is not sender]
        self._busy = False
        if self._closed: return
        if error:
            self.message.setText('처리하지 못했습니다. 편집 내용은 유지됩니다. ' + str(error))
        else:
            callback = self._accepted
            callback(value)

    def open_document(self, identifier=None):
        return self._call(lambda: self.client.document_open(kind='report', document_id=identifier), self._opened)

    def _opened(self, document):
        self.document = document; self.draft = deepcopy(document['draft'])
        self._undo.clear(); self._redo.clear(); self._pending = None
        self._edit_buffers.clear(); self._editing_section = None; self.section_editor.hide()
        self.assets = {}; self._page = None; self.populate()
        if self._initial_reference:
            reference = self._initial_reference; self._initial_reference = None
            self.capture(reference, '선택한 결과')
        else:
            self.read_assets()

    def populate(self, selected=None):
        selected = self.sections.currentRow() if selected is None else selected
        self._populating = True
        self.title.setText(self.draft.get('title', ''))
        self.sections.clear()
        for row in self.draft.get('sections', []):
            item = QListWidgetItem(row.get('title', '섹션'))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if row.get('include') else Qt.CheckState.Unchecked)
            self.sections.addItem(item)
        if self.sections.count(): self.sections.setCurrentRow(max(0,min(selected,self.sections.count()-1)))
        self._populating = False
        self.render()
        self.selected()

    def changed(self, new):
        if new == self.draft: return
        self._undo.append(deepcopy(self.draft)); self._redo.clear()
        self.draft = deepcopy(new); self.populate()
        self.message.setText('편집 중 — 저장하면 이 구성이 보존됩니다.')

    def edit_title(self):
        if not self._populating:
            draft = deepcopy(self.draft); draft['title'] = self.title.text(); self.changed(draft)

    def selected(self, *_):
        self.edit_button.setEnabled(self.sections.currentRow() >= 0)
        if not self._populating and self.sections.currentRow() >= 0 and getattr(self, '_page', None):
            row = self.draft['sections'][self.sections.currentRow()]
            position = self._page.section_positions.get(row['id'])
            if position is not None:
                block = self._page.findBlock(position)
                rect = self._page.documentLayout().blockBoundingRect(block)
                page_size = self._page.pageSize()
                page_index = int(rect.top() // page_size.height())
                self.preview.setCurrentPage(1 + page_index)
                # Keep native print preview; move to the heading within its A4 page.
                from PySide6.QtCore import QRectF
                from PySide6.QtWidgets import QGraphicsView
                view = self.preview.findChild(QGraphicsView)
                if view is None or view.scene() is None:
                    return
                pages = sorted((item for item in view.scene().items() if item.parentItem() is None),
                               key=lambda item: item.sceneBoundingRect().top())
                if len(pages) != self.preview.pageCount() or not 0 <= page_index < len(pages):
                    return
                paper = self.printer.paperRect(QPrinter.Unit.DevicePixel)
                sx, sy = paper.width()/page_size.width(), paper.height()/page_size.height()
                heading = QRectF(rect.left()*sx, (rect.top()-page_index*page_size.height())*sy,
                                 rect.width()*sx, rect.height()*sy)
                view.ensureVisible(pages[page_index].mapRectToScene(heading), 24, 24)
                self.update_page_label()

    def update_page_label(self):
        self.page_label.setText(str(self.preview.currentPage())+' / '+str(self.preview.pageCount())+' 페이지')

    def move_page(self, delta):
        self.preview.setCurrentPage(max(1, min(self.preview.pageCount(), self.preview.currentPage()+delta)))
        self.update_page_label()

    def fit_preview(self, *_):
        if self.page_fit.currentIndex() == 0:
            self.preview.fitInView()
        else:
            self.preview.fitToWidth()
        self.update_page_label()

    def include_section(self, item):
        if self._populating: return
        draft = deepcopy(self.draft)
        draft['sections'][self.sections.row(item)]['include'] = item.checkState() == Qt.CheckState.Checked
        self.changed(draft)

    def append_section(self, row):
        draft = deepcopy(self.draft); draft['sections'].append(row); self.changed(draft)
        self.sections.setCurrentRow(len(draft['sections'])-1)

    def move(self, delta):
        i = self.sections.currentRow(); j = i+delta
        if i < 0 or not 0 <= j < len(self.draft['sections']): return
        draft = deepcopy(self.draft); draft['sections'][i],draft['sections'][j]=draft['sections'][j],draft['sections'][i]
        self.changed(draft); self.sections.setCurrentRow(j)

    def remove(self):
        i = self.sections.currentRow()
        if i >= 0:
            draft=deepcopy(self.draft); removed=draft['sections'].pop(i)
            self._edit_buffers.pop(removed['id'],None)
            if self._editing_section == removed['id']:
                self._editing_section=None; self.section_editor.hide()
            self.changed(draft)

    def remember_editor(self):
        if self._editing_section:
            value = {'title':self.section_title.text(),'text':self.section_text.toPlainText(),
                     'table':self.section_table.isChecked(),'curve':self.section_curve.isChecked()}
            row = next((s for s in self.draft['sections'] if s['id']==self._editing_section), None)
            if row and any(value[k] != row[k] for k in value):
                self._edit_buffers[self._editing_section] = value
            else:
                self._edit_buffers.pop(self._editing_section, None)

    def edit_section(self):
        i=self.sections.currentRow()
        if i<0:return
        self.remember_editor()
        row=self.draft['sections'][i]
        self._editing_section=row['id']
        value=self._edit_buffers.get(row['id'],row)
        self.section_title.setText(value['title']);self.section_text.setPlainText(value['text'])
        self.section_table.setChecked(value['table']);self.section_curve.setChecked(value['curve'])
        self.section_editor.show();self.section_text.setFocus()

    def apply_section(self):
        self.remember_editor()
        i=next((i for i,s in enumerate(self.draft['sections']) if s['id']==self._editing_section),None)
        if i is None or self._editing_section not in self._edit_buffers:return
        draft=deepcopy(self.draft);draft['sections'][i].update(self._edit_buffers[self._editing_section])
        self._edit_buffers.pop(self._editing_section,None);self.changed(draft)
        self.message.setText('선택 섹션에 설명을 적용했습니다.')

    def cancel_section(self):
        if not self._editing_section:return
        self._edit_buffers.pop(self._editing_section,None)
        row=next((s for s in self.draft['sections'] if s['id']==self._editing_section),None)
        if row:
            self.section_title.setText(row['title']);self.section_text.setPlainText(row['text'])
            self.section_table.setChecked(row['table']);self.section_curve.setChecked(row['curve'])

    def close_editor(self):
        self.remember_editor();self.section_editor.hide()

    def render(self):
        try:
            errors=diagnostics(self.draft)
            if errors: raise ValueError(errors[0]['message'])
            self._page=compose(self.draft,self.assets,self.font())
            self._page_stale=False
            self.preview.updatePreview()
            self.fit_preview()
        except Exception as error:
            self._page_stale=True
            self.message.setText('이전 미리보기를 유지합니다. 페이지를 만들 수 없습니다: '+str(error))

    def paint(self, printer):
        if self._page is not None:
            self._page.print_(printer)

    def read_assets(self):
        if not self.document: return False
        identifier=self.document['id']
        bindings=[s['asset'] for s in self.draft['sections'] if s.get('asset')]
        def read(receipt):
            if self.document['id']!=identifier: return
            from caelab.report_image import merge_read_assets
            self.assets = merge_read_assets(self.assets, receipt['assets']); self.render()
            bad=sum(a.get('source_status')!='AVAILABLE' for a in receipt['assets'])
            self.message.setText('원자료 확인 필요: '+str(bad)+'개' if bad else '고정한 자료를 읽었습니다.')
        return self._call(lambda:self.client.report_content(identifier,bindings),read)

    def capture(self, reference, title):
        if not self.document: return
        identifier=self.document['id']
        def captured(binding):
            if self.document['id']!=identifier:return
            self.append_section(section(title,asset=binding)); self.read_assets()
        return self._call(lambda:self.client.report_capture(identifier,deepcopy(reference)),captured)

    def command(self, operation, arguments, after=None):
        if not self.document or self._busy: return False
        if self._pending is None:
            self._pending=(deepcopy(self.document),operation,deepcopy(arguments),'C'+uuid.uuid4().hex,
                           deepcopy(self.draft),after)
        return self.retry()

    def retry(self):
        if not self._pending:return False
        doc,operation,args,command_id,submitted,after=self._pending
        def accepted(receipt):
            late=self.draft!=submitted
            self.document=receipt['document']; self._pending=None
            if not late:
                self.draft=deepcopy(self.document['draft']); self._undo.clear(); self._redo.clear(); self.populate()
            self.message.setText('이전 편집을 저장했습니다. 새 편집은 남아 있습니다.' if late else '저장했습니다.')
            if after and not late: QTimer.singleShot(0,after)
        return self._call(lambda:self.client.document_command(doc['id'],operation,args,session_id=doc['session_id'],
            expected_generation=doc['generation'],command_id=command_id),accepted)

    def reconcile(self):
        if not self.document or self._busy:return False
        identifier=self.document['id']
        def read(document):
            same=document['draft']==self.draft
            description=('서버에 같은 입력이 있습니다.' if same else
                         '서버 입력과 현재 편집이 다릅니다. 현재 편집은 그대로 남깁니다.')
            if QMessageBox.question(self,'저장 상태 확인',description+
                '\n확인한 버전에서 편집을 계속할까요? 저장은 다시 눌러야 적용됩니다.',
                QMessageBox.StandardButton.Ok|QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Ok:
                self.document=document;self._pending=None
                self.message.setText('서버 버전을 확인했습니다. 현재 편집은 유지됩니다.')
        return self._call(lambda:self.client.document_read(identifier),read)

    def save_document(self):
        self.edit_title()
        self.remember_editor()
        if self._edit_buffers:
            self.message.setText('설명 적용 또는 수정 취소로 섹션 편집을 마친 뒤 저장하세요.')
            return False
        if self._pending:return self.retry()
        if not self.document:return False
        if self.draft!=self.document['draft']:
            return self.command('report.update',{'draft':deepcopy(self.draft)},self.save_document)
        return self.command('document.save',{})

    def undo(self):
        if self._busy or self._pending:return
        self.remember_editor()
        if self._edit_buffers:
            self.message.setText('설명 적용 또는 수정 취소 후 실행 취소하세요. 미적용 설명은 유지됩니다.');return
        self._editing_section=None;self.section_editor.hide()
        if self._undo:
            self._redo.append(deepcopy(self.draft)); self.draft=self._undo.pop(); self.populate()
        elif self.document and self.document.get('can_undo'):
            self.command('document.undo',{},self.read_assets)

    def redo(self):
        if self._busy or self._pending:return
        self.remember_editor()
        if self._edit_buffers:
            self.message.setText('설명 적용 또는 수정 취소 후 다시 실행하세요. 미적용 설명은 유지됩니다.');return
        self._editing_section=None;self.section_editor.hide()
        if self._redo:
            self._undo.append(deepcopy(self.draft)); self.draft=self._redo.pop(); self.populate()
        elif self.document and self.document.get('can_redo'):
            self.command('document.redo',{},self.read_assets)

    def choose_document(self):
        if not self.can_leave():return
        def listed(payload):
            rows=[d for d in payload['documents'] if d.get('kind')=='report']
            labels=[str(i+1)+'. '+d['title'] for i,d in enumerate(rows)]
            label,ok=QInputDialog.getItem(self,'보고서 열기','보고서',labels,editable=False)
            if ok:self.open_document(rows[labels.index(label)]['id'])
        return self._call(self.client.documents,listed)

    def new_document(self):
        if self.can_leave():self.open_document()

    def choose_result(self):
        def listed(payload):
            rows=[d for d in payload['documents'] if d.get('runs')]
            labels=[str(i+1)+'. '+d['title'] for i,d in enumerate(rows)]
            if not rows:self.message.setText('원 프로그램에서 결과를 저장한 뒤 선택하세요.');return
            label,ok=QInputDialog.getItem(self,'결과 선택','문서',labels,editable=False)
            if not ok:return
            doc=rows[labels.index(label)]
            runs=[r for r in doc['runs'] if r.get('retention_complete') and r.get('retained_result')]
            names=['계산 '+str(i+1)+' — '+str(r.get('retained_state','UNKNOWN')) for i,r in enumerate(runs)]
            if not runs:self.message.setText('원 프로그램에서 결과를 저장하세요.');return
            name,ok=QInputDialog.getItem(self,'결과 선택','저장된 계산',names,editable=False)
            if not ok:return
            job=runs[names.index(name)]['job_id']
            self._call(lambda:(self.client.document_result_reference(doc['id'],job),
                              self.client.document_result_metadata(doc['id'],job)),
                       lambda pair:self._select_response(doc['title'],doc['id'],job,*pair))
        self._call(self.client.documents,listed)

    def _select_response(self,title,identifier,job,reference,metadata,candidate_ids=None):
        if metadata.get('candidate_count') and candidate_ids is None:
            def choose_candidate(result):
                from caelab.research_operations import result_metadata
                rows=result.get('candidates',result.get('predictions',[]))
                labels=[str(i+1)+'. '+', '.join(k+'='+value_text(v) for k,v in row.get('values',{}).items())+
                    ' / '+str(row.get('execution_status',row.get('prediction_status','UNKNOWN'))) for i,row in enumerate(rows)]
                label,ok=QInputDialog.getItem(self,'보고서에 넣을 후보','보존된 조건',labels,editable=False)
                if not ok:return
                row=rows[labels.index(label)]
                catalog=result_metadata({'responses':row.get('responses',{})})
                catalog['kind'] = result.get('kind')
                catalog['responses'] += [{**entry,'reduction_index':i} for i,entry in
                    enumerate(row.get('response_reductions',[]))]
                self._select_response(title,identifier,job,reference,catalog,[row['candidate_id']])
            self._call(lambda:self.client.document_result(identifier,job,selection={'metadata_only':True}),choose_candidate)
            return
        if metadata.get('kind') == 'fit' and candidate_ids:
            label, ok = QInputDialog.getItem(self, '계산 결과 확인', '보고서에 넣을 내용',
                ['요약만 넣기 (상세 결과 미포함)', '선택한 계산 결과 확인…'], editable=False)
            if not ok:
                return
            if label.startswith('요약'):
                self.capture({'kind':'result', **reference,
                    'selection':{'metadata_only':True, 'candidate_ids':candidate_ids}}, title)
                return
            from .numerical_candidate_detail_window import NumericalCandidateDetailWindow
            window = NumericalCandidateDetailWindow(self.client, document_id=identifier, job_id=job,
                candidate_id=candidate_ids[0], source=reference, parent=self)
            window.evidence_preserved.connect(lambda ref: self.capture(ref, title))
            self._children.append(window); window.show()
            return
        descriptors = list(metadata.get('responses', []))
        descriptors += [{'response':name, **row, 'native':True}
                        for name,row in metadata.get('native_channels',{}).items()]
        if not descriptors and metadata.get('kind') == 'fit':
            def fit_channels(result):
                catalog={'responses':[{'response':name,**{k:v for k,v in response.items()
                    if k in ('unit','component','location','kind')}}
                    for name,response in result.get('responses',{}).items()]}
                if not catalog['responses']:
                    self.capture({'kind':'result',**reference,'selection':{'metadata_only':True}},title)
                else:self._select_response(title,identifier,job,reference,catalog)
            self._call(lambda:self.client.document_result(identifier,job,selection={'rows':[0,256]}),fit_channels)
            return
        if not descriptors:
            selection={'metadata_only':True}
            if candidate_ids is not None:selection['candidate_ids']=candidate_ids
            self.capture({'kind':'result',**reference,'selection':selection},title);return
        labels=[str(i+1)+'. '+d['response']+' ['+str(d.get('unit','미확인'))+'] '+str(d.get('component',''))
                +' '+str(d.get('location',''))+
                (' / 저장된 '+REDUCTIONS.get(d.get('reduction'),str(d.get('reduction'))) if 'reduction_index' in d else '')
                for i,d in enumerate(descriptors)]
        label,ok=QInputDialog.getItem(self,'응답 선택','물리량 / 성분 / 위치',labels,editable=False)
        if not ok:return
        item=descriptors[labels.index(label)]
        if item.get('native'):
            def locations(payload):
                rows=payload['locations']
                names=[row['label'] for row in rows]
                choice,ok=QInputDialog.getItem(self,'측정 위치','실제 위치',names,editable=False)
                if ok:self._response_interval(title,reference,rows[names.index(choice)]['selector'])
            search,ok=QInputDialog.getText(self,'측정 위치','위치 찾기 (비우면 첫 128개)')
            if ok:self._call(lambda:self.client.document_response_locations(identifier,job,item['response'],search=search),locations)
        else:self._response_interval(title,reference,item['response'],candidate_ids=candidate_ids,
            reduction_index=item.get('reduction_index'))

    def _response_interval(self,title,reference,name,*,candidate_ids=None,reduction_index=None):
        from .report_selection import ReportSelectionDialog
        dialog=ReportSelectionDialog(self.client,reference,name,self,candidate_ids=candidate_ids,reduction_index=reduction_index)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.capture({'kind':'result',**reference,'selection':dialog.selection},title+' '+name)

    def choose_study(self):
        def listed(payload):
            rows=[d for d in payload['documents'] if d.get('kind')=='study' and d.get('saved_revision') and not d.get('dirty')]
            labels=[str(i+1)+'. '+d['title'] for i,d in enumerate(rows)]
            if not rows:self.message.setText('연구 기록을 먼저 저장하세요.');return
            label,ok=QInputDialog.getItem(self,'저장된 연구 적용','연구',labels,editable=False)
            if ok:self.use_study(rows[labels.index(label)])
        self._call(self.client.documents,listed)

    def use_study(self,study):
        self.remember_editor()
        if self._edit_buffers:
            self.message.setText('현재 섹션의 설명을 적용하거나 수정 취소한 뒤 다른 연구를 적용하세요.')
            return False
        if self.draft['sections'] and QMessageBox.question(self,'연구 적용',
            '현재 섹션을 선택한 저장 연구로 교체할까요? 실행 취소로 복구할 수 있습니다.',
            QMessageBox.StandardButton.Ok|QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Ok:return
        identifier=self.document['id']
        proposed_base=deepcopy(self.draft)
        reference={'kind':'document','document_kind':'study','document_id':study['id'],
            'saved_revision':study['saved_revision'],'input_revision':study['input_revision'],
            'input_sha256':canonical_hash(study['draft'])}
        def capture():
            rows=[section(study['title'],asset=self.client.report_capture(identifier,reference))]
            for item in study['draft']['evidence']:
                rows.append(section(item['label'],text=item['note'],
                    asset=self.client.report_capture(identifier,item['reference'])))
            return rows
        def accepted(rows):
            self.remember_editor()
            if self.draft != proposed_base or self._edit_buffers:
                self.message.setText('자료를 읽는 동안 보고서가 편집되었습니다. 현재 내용을 유지합니다. 연구 적용을 다시 선택하세요.')
                return
            self._editing_section=None;self.section_editor.hide()
            draft=deepcopy(self.draft);draft['sections']=rows;self.changed(draft);self.read_assets()
        self._call(capture,accepted)

    def choose_literature(self):
        from .experiment_sources import choose_knowledge
        choose_knowledge(self.client,self,lambda reference,title:self.capture(reference,title))

    def open_source(self):
        i=self.sections.currentRow()
        if i<0:return
        binding=self.draft['sections'][i].get('asset')
        if binding:
            if binding['reference'].get('kind') == 'post_image':
                from .report_image_dialog import show_origin
                show_origin(self, binding)
                return
            from .reference_window import ReferenceWindow
            window=ReferenceWindow(self.client,deepcopy(binding['reference']))
            self._children.append(window);window.show()

    def export(self,format):
        self.edit_title(); self.remember_editor()
        if self._busy:return
        if self._edit_buffers:
            self.message.setText('설명 적용 또는 수정 취소 후 내보내세요.'); return
        errors=diagnostics(self.draft)
        if errors:self.message.setText(errors[0]['message']);return
        unavailable=[s for s in self.draft['sections'] if s['include'] and s.get('asset')
            and self.assets.get(s['asset']['id'],{}).get('source_status')!='AVAILABLE']
        if unavailable and QMessageBox.question(self,'원자료 확인 필요',
            '확인되지 않은 섹션에 표시를 남겨 초안으로 내보낼까요?',
            QMessageBox.StandardButton.Ok|QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Ok:return
        path,_=QFileDialog.getSaveFileName(self,'보고서 내보내기','보고서.'+format,
                                         'PDF (*.pdf)' if format=='pdf' else 'Markdown (*.md)')
        if not path:return
        try:
            self.render()
            if self._page is None or getattr(self, '_page_stale', False):raise ValueError('페이지 오류를 먼저 고치세요. 이전 출력은 유지합니다.')
            if format=='pdf':atomic_export(path,lambda p:pdf_document(self._page,p))
            else:atomic_export(path,lambda p:p.write_text(markdown(self.draft,self.assets),encoding='utf-8'))
            self.message.setText('보고서를 내보냈습니다.')
        except Exception as error:self.message.setText('내보내지 못했습니다. 이전 파일은 유지됩니다. '+str(error))

    def can_leave(self):
        if self._busy or self._pending:return False
        self.remember_editor()
        dirty=bool(self._edit_buffers) or self.document and (self.document.get('dirty') or self.draft!=self.document['draft'])
        if dirty:
            return QMessageBox.question(self,'저장하지 않은 보고서','변경을 저장하지 않고 닫을까요?',
                QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Discard
        return True

    def closeEvent(self,event):
        if not self.can_leave():event.ignore();return
        self._closed=True
        for worker in self._workers:worker.abandon()
        super().closeEvent(event)


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--service',required=True);parser.add_argument('--document-id')
    args=parser.parse_args(argv)
    app=QApplication.instance() or QApplication(sys.argv[:1]);apply_appearance(app)
    window=ReportWindow(Client(args.service),document_id=args.document_id);window.show()
    return app.exec()


if __name__=='__main__':
    raise SystemExit(main())
