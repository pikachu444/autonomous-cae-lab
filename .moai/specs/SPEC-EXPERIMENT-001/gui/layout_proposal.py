"""Editable Qt layout proposal. Public synthetic values; no product service calls."""
import os
import sys
if '--show' not in sys.argv:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from html import escape
from pathlib import Path
from PySide6.QtCore import Qt, QSizeF, QRectF, qVersion
from PySide6.QtTest import QTest
from PySide6.QtGui import QAction, QFontDatabase, QTextDocument, QPixmap, QImage, QPainter
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QPushButton, QComboBox, QLineEdit, QPlainTextEdit, QListWidget,
    QListWidgetItem, QSplitter, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / 'pyproject.toml').is_file() and (parent / 'apps/research').is_dir())
sys.path.insert(0, str(ROOT))
from apps.research.appearance import apply_appearance, configure_plot_fonts
HERE = Path(__file__).resolve().parent
RAW = [0.1, 1.1, 2.1, 3.1, 5.4, 6.4]
CORRECTED = [2, 102, 202, 302, 532, 632]
STATES = ['사용 범위 내']*4 + ['교정 범위 밖', '센서 포화, 범위 밖']

def vertical():
    widget = QWidget(); layout = QVBoxLayout(widget)
    layout.setContentsMargins(10, 8, 10, 8); layout.setSpacing(8)
    return widget, layout

def row(*widgets):
    holder = QWidget(); layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    for widget in widgets: layout.addWidget(widget)
    return holder

def button(text, callback=None, primary=False):
    value = QPushButton(text)
    if primary: value.setProperty('appearanceRole', 'primary')
    if callback: value.clicked.connect(callback)
    return value

class Base(QMainWindow):
    def __init__(self, title):
        super().__init__(); self.setWindowTitle(title)
        files = self.menuBar().addMenu('파일(&F)')
        for text, shortcut in [('열기…', 'Ctrl+O'), ('저장', 'Ctrl+S'), ('내보내기…', 'Ctrl+Shift+E')]:
            action = QAction(text, self); action.setShortcut(shortcut)
            action.triggered.connect(lambda checked=False, name=text: self.statusBar().showMessage('시안: '+name+'의 제품 연결은 구현 인계 대상'))
            files.addAction(action)
        self.menuBar().addMenu('편집(&E)')
        self.statusBar().showMessage('설계 시안 — 공개 합성값, 제품 서비스 연결 없음')

class Calibration(Base):
    def __init__(self):
        super().__init__('측정 교정 시안')
        content, layout = vertical(); self.setCentralWidget(content)
        channel = QComboBox(); channel.addItems(['힘 채널', '변위 채널'])
        layout.addWidget(row(QLabel('합성 하중 기록.csv'), channel, button('파일 열기…')))
        self.splitter = QSplitter(); layout.addWidget(self.splitter, 1)
        readings, readings_layout = vertical()
        readings_layout.addWidget(QLabel('같은 원행의 교정 전후'))
        figure = Figure(figsize=(7, 4), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(figure)
        upper, lower = figure.subplots(2, 1, sharex=True)
        upper.plot(range(6), RAW, 'o-', color='#596e87', label='원값')
        upper.set_ylabel('전압 [V]'); upper.grid(alpha=.15)
        lower.plot(range(4), CORRECTED[:4], 'o-', color='#215fc6', label='교정값 (범위 내)')
        lower.plot([3,4,5], CORRECTED[3:], '--', color='#ad432d', alpha=.6)
        lower.scatter([4], [CORRECTED[4]], facecolors='none', edgecolors='#ad432d', s=65, label='범위 밖')
        lower.scatter([5], [CORRECTED[5]], marker='x', color='#ad432d', s=55, label='센서 포화')
        lower.legend(loc='upper left', frameon=False, fontsize=9)
        lower.set_ylabel('힘 [N]'); lower.set_xlabel('관측 시각 [s]'); lower.grid(alpha=.15)
        self.values = QTableWidget(6, 5)
        self.values.setHorizontalHeaderLabels(['원본 행', '시각 [s]', '원값 [V]', '교정값 [N]', '교정 상태'])
        self.values.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.values.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for r in range(6):
            state = STATES[r]
            for c, value in enumerate([r+1, r, RAW[r], CORRECTED[r], state]):
                self.values.setItem(r, c, QTableWidgetItem(str(value)))
        self.values.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.values.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        plots = QSplitter(Qt.Orientation.Vertical); plots.addWidget(self.canvas); plots.addWidget(self.values)
        readings_layout.addWidget(plots, 1); plots.setSizes([350, 190])
        self.splitter.addWidget(readings)
        editor, editor_layout = vertical(); editor.setMaximumWidth(340); editor.setMinimumWidth(280)
        editor_layout.addWidget(QLabel('선택 채널의 교정'))
        self.source = QLineEdit('공개 선형 교정표 — 시안'); self.source.setReadOnly(True)
        editor_layout.addWidget(self.source)
        self.formula = QLabel('힘 = 100 × (전압 − 0.1) + 2'); self.formula.setWordWrap(True)
        editor_layout.addWidget(self.formula)
        form = QFormLayout(); self.fields = {}
        for name, value in [('입력 영점 [V]', '0.1'), ('계수 [N/V]', '100'), ('출력 오프셋 [N]', '2'),
                            ('교정식 최소 [V]', '0.1'), ('교정식 최대 [V]', '5.1'),
                            ('센서 최소 [V]', '0'), ('센서 최대 [V]', '6.2')]:
            field = self.fields[name] = QLineEdit(value); form.addRow(name, field)
            field.textEdited.connect(self.edited)
        editor_layout.addLayout(form)
        self.state = QLabel('표시 값은 시안 교정식에 따른 합성 예시입니다.'); self.state.setWordWrap(True)
        editor_layout.addWidget(self.state)
        self.compare = button('교정 적용', self.compare_clicked, True)
        editor_layout.addWidget(self.compare)
        editor_layout.addWidget(button('교정 자료 상세…', lambda: self.state.setText('시안: 유효기간과 제공 불확실성은 상세에서 편집. 미제공은 미확인.')))
        editor_layout.addStretch(1)
        editor_layout.addWidget(button('자료 저장', lambda: self.state.setText('시안: 원자료·교정 선택·관측 시각을 함께 저장할 제품 명령 연결 필요')))
        self.splitter.addWidget(editor); self.splitter.setSizes([780, 300])

    def edited(self):
        self.state.setText('변경 사항 미적용. 표와 그림은 이전 교정입니다.')

    def compare_clicked(self):
        self.state.setText('시안: 교정 계산·범위 판정은 기존 Data 명령에 연결해야 합니다. 편집값을 보존합니다.')

class Report(Base):
    def __init__(self):
        super().__init__('연구 보고서 시안')
        self.sections_data = [
            {'title':'시험 목적', 'text':'힘 채널의 교정 전후와 사용 범위를 비교한다.', 'source':'합성 하중 기록.csv'},
            {'title':'측정값', 'text':'교정 범위 밖과 센서 포화를 구분해 보관한다.', 'source':'페이지 배치용 합성 힘 채널, 0~35 s, 원본 행 1~36'},
            {'title':'판단과 다음 시험', 'text':'교정 전후 예시이며 실제 장비 및 재료의 검증은 수행하지 않았다.', 'source':'사용자 판단 — 시안'},
            {'title':'누락 자료 예시', 'text':'원자료를 찾을 수 없다. 이전 본문은 유지한다.', 'source':'원자료 없음'}]
        self.editor_buffer = {}; self.editing_index = None
        content, layout = vertical(); self.setCentralWidget(content)
        self.title = QLineEdit('힘 채널 교정 검토'); self.title.setAccessibleName('보고서 제목')
        self.title.textEdited.connect(self.rebuild)
        layout.addWidget(row(QLabel('보고서 제목'), self.title, button('내보내기…', lambda: self.statusBar().showMessage('시안: PDF/Markdown 출력은 제품 연결 필요'), True)))
        self.outer = QSplitter(); layout.addWidget(self.outer, 1)
        nav, nav_layout = vertical(); nav.setMinimumWidth(190); nav.setMaximumWidth(260)
        nav_layout.addWidget(QLabel('포함할 섹션'))
        self.sections = QListWidget()
        for data in self.sections_data:
            item = QListWidgetItem(data['title']); item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked if data['source']=='원자료 없음' else Qt.CheckState.Checked); self.sections.addItem(item)
        nav_layout.addWidget(self.sections, 1)
        nav_layout.addWidget(row(button('추가…'), button('위로', lambda: self.move(-1)), button('아래로', lambda: self.move(1))))
        self.sections.currentRowChanged.connect(self.selected); self.sections.itemChanged.connect(self.rebuild)
        self.outer.addWidget(nav)
        self.workspace = QSplitter(); self.outer.addWidget(self.workspace)
        page, page_layout = vertical()
        self.context = QLabel('측정값'); self.context.setWordWrap(True)
        page_layout.addWidget(row(self.context, button('원자료 열기', self.open_source), button('설명 편집', self.open_editor)))
        self.page_number = QLabel(); self.page_number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_layout.addWidget(row(button('이전 페이지', lambda: self.turn(-1)), self.page_number, button('다음 페이지', lambda: self.turn(1))))
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(False)
        self.sheet = QLabel(); self.sheet.setStyleSheet('background:white'); self.scroll.setWidget(self.sheet)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        page_layout.addWidget(self.scroll, 1); self.workspace.addWidget(page)
        self.editor, editor_layout = vertical(); self.editor.setMinimumWidth(260)
        self.editor_title = QLabel(); editor_layout.addWidget(self.editor_title)
        self.text = QPlainTextEdit(); editor_layout.addWidget(self.text, 1)
        self.text.textChanged.connect(self.keep_buffer)
        editor_layout.addWidget(row(button('설명 적용', self.apply_text, True), button('수정 취소', self.cancel_text), button('닫기', self.close_editor)))
        self.workspace.addWidget(self.editor); self.editor.hide()
        self.warning = QLabel(); self.warning.setWordWrap(True); self.warning.setStyleSheet('color:#9b3c26;')
        layout.addWidget(self.warning)
        self.page_index = 0; self.sections.setCurrentRow(1); self.rebuild()
        self.outer.setSizes([205, 875])

    def selected(self, index):
        if index < 0: return
        self.context.setText(self.sections_data[index]['source'])
        if self.editor.isVisible(): self.open_editor()
        if hasattr(self, 'document'):
            cursor = self.document.find(self.sections_data[index]['title'])
            if not cursor.isNull():
                y = self.document.documentLayout().blockBoundingRect(cursor.block()).top()
                self.page_index = int(y/842); self.turn(0)
                self.scroll.verticalScrollBar().setValue(int(y % 842)-15)

    def open_source(self):
        data = self.sections_data[self.sections.currentRow()]
        self.statusBar().showMessage('원자료 없음 — 이 섹션의 이전 본문 유지' if data['source']=='원자료 없음' else '시안: 저장 당시 선택을 ReferenceWindow로 열기 — '+data['source'])

    def open_editor(self):
        index = self.sections.currentRow(); self.editing_index = index
        self.editor_title.setText(self.sections_data[index]['title']+' 설명')
        self.text.blockSignals(True); self.text.setPlainText(self.editor_buffer.get(index, self.sections_data[index]['text'])); self.text.blockSignals(False)
        self.adapt(); self.editor.show()
        self.workspace.setSizes([540,160] if self.width() < 1200 else [650,290])

    def keep_buffer(self):
        if self.editing_index is not None: self.editor_buffer[self.editing_index] = self.text.toPlainText()

    def apply_text(self):
        index = self.editing_index
        self.sections_data[index]['text'] = self.text.toPlainText(); self.editor_buffer.pop(index, None)
        self.rebuild(); self.statusBar().showMessage('시안 본문에 적용됨 — 제품 저장은 별도 명령')

    def close_editor(self): self.editor.hide()

    def cancel_text(self):
        index = self.editing_index; self.editor_buffer.pop(index, None)
        self.text.blockSignals(True); self.text.setPlainText(self.sections_data[index]['text']); self.text.blockSignals(False)
        self.statusBar().showMessage('선택 섹션의 마지막 적용 설명으로 복원했습니다. 다른 섹션은 유지합니다.')

    def move(self, delta):
        index = self.sections.currentRow(); target = index+delta
        if not 0 <= target < len(self.sections_data): return
        if self.editor_buffer:
            self.statusBar().showMessage('시안: 설명 편집 중 순서 이동을 보류. 적용 후 이동하세요.'); return
        value = self.sections_data.pop(index); self.sections_data.insert(target, value)
        item = self.sections.takeItem(index); self.sections.insertItem(target, item); self.sections.setCurrentRow(target); self.rebuild()

    def rebuild(self, *_):
        self.document = QTextDocument(); self.document.setDefaultFont(self.font())
        self.document.setPageSize(QSizeF(595, 842)); self.document.setDocumentMargin(36)
        html = '<style>h1{font-size:21pt}h2{font-size:15pt}td,th{padding:5px;font-size:10pt}p{font-size:11pt}</style><h1>'+escape(self.title.text())+'</h1>'
        for i, data in enumerate(self.sections_data):
            if self.sections.item(i).checkState() != Qt.CheckState.Checked: continue
            html += '<h2>'+escape(data['title'])+'</h2><p>'+escape(data['text'])+'</p>'
            if data['title']=='측정값':
                html += '<table border="1" cellspacing="0" width="100%"><thead><tr><th>원본 행</th><th>시각 [s]</th><th>원값 [V]</th><th>교정값 [N]</th><th>교정 상태</th></tr></thead>'
                for r in range(36):
                    html += '<tr>'+''.join('<td>'+str(value)+'</td>' for value in [r+1, r, RAW[r%6], CORRECTED[r%6], STATES[r%6]])+'</tr>'
                html += '</table><p>페이지 나눔 확인용 반복 합성 행입니다. 실제 원자료가 아닙니다.</p>'
        self.document.setHtml(html); self.turn(0)
        missing = [data['title'] for i,data in enumerate(self.sections_data)
                   if data['source']=='원자료 없음' and self.sections.item(i).checkState()==Qt.CheckState.Checked]
        self.warning.setText('원자료 없음: '+', '.join(missing)+' — 기존 본문은 보존합니다.' if missing else '')
        self.warning.setVisible(bool(missing))

    def turn(self, delta):
        pages = max(1, self.document.pageCount()); self.page_index = max(0,min(pages-1,self.page_index+delta))
        image = QImage(595, 842, QImage.Format.Format_ARGB32); image.fill(Qt.GlobalColor.white)
        painter = QPainter(image); painter.translate(0,-self.page_index*842)
        self.document.drawContents(painter, QRectF(0,self.page_index*842,595,842)); painter.end()
        self.sheet.setPixmap(QPixmap.fromImage(image)); self.sheet.resize(595,842)
        self.page_number.setText(f'{self.page_index+1} / {pages} 페이지')

    def adapt(self):
        if self.editor.isVisible(): return
        small = self.width() < 1200
        self.workspace.setOrientation(Qt.Orientation.Vertical if small else Qt.Orientation.Horizontal)
        self.editor.setMaximumHeight(165 if small else 16777215)
        if self.editor.isVisible(): self.workspace.setSizes([540,160] if small else [650,290])

    def resizeEvent(self, event): super().resizeEvent(event); self.adapt()

if __name__ == '__main__':
    app = QApplication([])
    for name in ['segoeui.ttf','malgun.ttf']: QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
    apply_appearance(app); configure_plot_fonts()
    calibration, report = Calibration(), Report()
    if '--show' in sys.argv:
        for window in (calibration, report): window.resize(1100,780); window.show()
        sys.exit(app.exec())
    receipt = {'scope':'Editable native Qt design proposal only; public synthetic fixtures, no product owner', 'qt':qVersion(), 'solver_runs':0,'provider_calls':0,'images':[]}
    for name, window in [('calibration',calibration),('report',report)]:
        for size,label in [((1440,900),'wide'),((1100,780),'small')]:
            window.resize(*size); window.show(); app.processEvents()
            path = HERE/(name+'-'+label+'.png'); window.grab().save(str(path))
            receipt['images'].append({'path':str(path),'requested':list(size),'actual':[window.width(),window.height()]})
    report.open_editor(); report.text.setPlainText('아직 적용하지 않은 설명'); report.close_editor(); report.open_editor()
    assert report.text.toPlainText() == '아직 적용하지 않은 설명'
    report.text.setPlainText('아직 적용하지 않은 설명'); app.processEvents(); report.grab().save(str(HERE/'report-editing-small.png'))
    calibration.activateWindow(); app.processEvents()
    coefficient = calibration.fields['계수 [N/V]']; coefficient.setFocus(); coefficient.selectAll(); QTest.keyClicks(coefficient,'1e'); app.processEvents()
    assert coefficient.text() == '1e' and coefficient.hasFocus()
    receipt['partial_numeric_buffer_preserved'] = True
    calibration.grab().save(str(HERE/'calibration-unapplied-small.png'))
    report.turn(1); app.processEvents(); report.grab().save(str(HERE/'report-second-page-small.png'))
    report.close_editor(); report.sections.item(3).setCheckState(Qt.CheckState.Checked); report.sections.setCurrentRow(3); app.processEvents()
    assert report.warning.isVisible() and '누락 자료 예시' in report.warning.text()
    report.grab().save(str(HERE/'report-missing-source-small.png'))
    report.sections.setCurrentRow(1); report.open_editor(); report.text.setPlainText('버릴 설명'); report.cancel_text()
    assert report.text.toPlainText() == report.sections_data[1]['text'] and 1 not in report.editor_buffer
    assert '교정 범위 밖' in report.document.toPlainText() and '센서 포화' in report.document.toPlainText()
    receipt['cancel_restores_applied_section'] = True; receipt['report_retains_calibration_states'] = True
    receipt['editor_buffer_survives_close'] = True; receipt['report_page_count'] = report.document.pageCount()
    (HERE/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    calibration.close(); report.close()
