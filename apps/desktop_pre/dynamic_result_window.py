"""Read retained dynamic results in native Qt; opening never schedules a solve."""
from pathlib import Path
import json
import math
from caelab.dynamic_results import read_attempt, history, MEANINGS
from caelab.dynamic_result_store import frame_metadata
from .dynamic_panel import style, table, _item, _gui

_WINDOWS = set()

# Existing research-window surface/selection tokens, scoped to this native dialog.
_RESULT_STYLE = '''
QDialog#DynamicResult { background:#eef2f6; color:#1c2c3d; }
#DynamicResult QLabel#dynamicResultSummary { color:#152c45; font-size:15px; font-weight:600; }
#DynamicResult QLabel#dynamicQualification, #DynamicResult QLabel#dynamicCoordinateNote { color:#526174; }
#DynamicResult QTabWidget::pane { background:#ffffff; border:1px solid #ccd8e4; }
#DynamicResult QTabBar::tab { background:#e6edf4; color:#526174; padding:7px 10px;
    border:1px solid #ccd8e4; border-bottom:none; margin-right:3px; }
#DynamicResult QTabBar::tab:selected { background:#ffffff; color:#173c63;
    border-top:2px solid #2768a9; padding-top:6px; font-weight:600; }
#DynamicResult QTabBar::tab:hover:!selected { background:#dceafb; color:#163e68; }
#DynamicResult QTableWidget { background:#ffffff; alternate-background-color:#f4f7fb;
    color:#1c2c3d; border:1px solid #ccd8e4; gridline-color:#e2e8f0;
    selection-background-color:#dceafb; selection-color:#163e68; }
#DynamicResult QTableWidget:focus { border:2px solid #2768a9; }
#DynamicResult QTableWidget::item { padding:3px 4px; }
#DynamicResult QTableWidget::item:selected { background:#dceafb; color:#163e68; }
#DynamicResult QHeaderView::section { background:#e8eff6; color:#314a64; font-weight:600;
    padding:5px 7px; border:none; border-bottom:1px solid #c4d2e0; border-right:1px solid #d8e1eb; }
#DynamicResult QComboBox, #DynamicResult QPlainTextEdit { background:#ffffff; color:#1c2c3d;
    border:1px solid #b8c8d8; border-radius:3px; padding:3px 5px; }
#DynamicResult QComboBox:focus, #DynamicResult QPlainTextEdit:focus { border:2px solid #2768a9; padding:2px 4px; }
#DynamicResult QPushButton { background:#ffffff; color:#253b52; border:1px solid #bccbd9;
    border-radius:4px; padding:4px 9px; }
#DynamicResult QPushButton:hover { background:#eaf2fc; border-color:#7e9fbe; }
#DynamicResult QPushButton:pressed { background:#d3e4f7; border-color:#426c98; }
#DynamicResult QPushButton:focus { border:2px solid #2768a9; padding:3px 8px; }
#DynamicResult QPushButton:disabled, #DynamicResult QComboBox:disabled { background:#e9eef4;
    color:#778697; border-color:#d2dce7; }
'''


def physical_time_text(location):
    if location['procedure']=='static':return '해당 없음(정적)'
    return '결측' if location['physical_time_s'] is None else str(location['physical_time_s'])


EXECUTION_LABELS = {'SUCCEEDED':'계산 완료','FAILED':'계산 실패','CANCELLED':'계산 취소',
                    'REJECTED':'계산 거절','PARTIAL_FAILURE':'일부 계산 실패'}
ROW_LABELS = {'step_output_boundary':'단계의 첫·마지막 출력',
    'static_step_no_physical_time':'정적 단계에는 물리시간 없음',
    'missing_or_nonfinite_native_velocity_sample':'속도 출력 누락 또는 비유한 값',
    'unrepresentable_time_spacing':'계산할 수 없는 출력 시간 간격',
    'nonfinite_derived_value':'파생값이 유한하지 않음','missing_node':'절점 출력 누락',
    'native_channel_not_recorded':'요청 채널 출력 누락',
    'element_or_integration_point_not_recorded':'요소 또는 적분점 출력 누락',
    'native_block_not_recorded':'원 출력 블록 누락','nonfinite_native_value':'원 출력값이 유한하지 않음',
    'restrained_DOF_reaction':'구속 자유도의 반력',
    'native_nodal_force_not_a_reaction':'비구속 자유도의 절점력'}


def open_result(W, C, *, parent=None, attempt=None, on_restart=None, on_post=None):
    if attempt is None:
        chosen = W.QFileDialog.getOpenFileName(parent, '보존된 동해석 결과', '', '계산 기록 (contact_execution.json)')[0]
        if not chosen: return None
        attempt = Path(chosen).parent
    attempt = Path(attempt).absolute()
    record=json.loads((attempt/'contact_execution.json').read_text(encoding='utf-8'))
    if not record.get('dynamic_result'):
        return open_failure(W,C,attempt,record,parent=parent,on_restart=on_restart)
    data = read_attempt(attempt)  # strict retained hashes; no process launch
    G = _gui()

    class Plot(W.QWidget):
        def __init__(self):
            super().__init__(); self.rows = []; self.setMinimumHeight(155)
            self.setAccessibleName('물리시간 곡선. 결측과 단계 경계에서는 선을 잇지 않습니다.')
        def paintEvent(self, event):
            painter = G.QPainter(self); painter.setPen(self.palette().text().color())
            rect = self.rect().adjusted(65,15,-18,-35); painter.drawRect(rect)
            values = [r for r in self.rows if r['value'] is not None and math.isfinite(r['value'])]
            if not values:
                painter.drawText(rect, C.Qt.AlignCenter, '기록된 물리시간 값이 없습니다.'); return
            lo, hi = min(r['time_s'] for r in values), max(r['time_s'] for r in values)
            bottom, top = min(r['value'] for r in values), max(r['value'] for r in values)
            span_t, span_y = hi-lo or 1., top-bottom or 1.
            painter.drawText(4,rect.top()+12,format(top,'.5g')); painter.drawText(4,rect.bottom(),format(bottom,'.5g'))
            painter.drawText(rect.left(),self.height()-10,format(lo,'.6g')+' s')
            painter.drawText(max(rect.left(),rect.right()-85),self.height()-10,format(hi,'.6g')+' s')
            painter.setPen(G.QPen(self.palette().highlight().color(), 2))
            previous = None
            for row in self.rows:
                if row['value'] is None or not math.isfinite(row['value']): previous = None; continue
                point = C.QPointF(rect.left()+(row['time_s']-lo)/span_t*rect.width(),
                    rect.bottom()-(row['value']-bottom)/span_y*rect.height())
                if previous is not None and previous[0] == row['step_id']: painter.drawLine(previous[1],point)
                painter.drawEllipse(point,2,2); previous = row['step_id'],point

    class Window(W.QDialog):
        def __init__(self):
            super().__init__(parent); self.setWindowTitle('동해석 — 보존 결과'); self.resize(980,740)
            style(self,'DynamicResult'); self.setAttribute(C.Qt.WA_DeleteOnClose)
            self.setStyleSheet(self.styleSheet()+_RESULT_STYLE)
            layout=W.QVBoxLayout(self)
            note=W.QLabel(f"{EXECUTION_LABELS.get(data['execution_status'],'계산 상태 확인 필요')} / 수렴 출력 {len(data['frames'])}개")
            note.setObjectName('dynamicResultSummary')
            note.setToolTip(f"원 실행 상태: {data['execution_status']}\n공학 승인: UNKNOWN / NOT_RELEASED\n보존 결과 위치: {attempt}")
            note.setWordWrap(True); note.setTextInteractionFlags(C.Qt.TextSelectableByMouse);layout.addWidget(note)
            qualification=W.QLabel('공학적 승인은 확인되지 않았습니다.');qualification.setObjectName('dynamicQualification')
            layout.addWidget(qualification)
            tabs=W.QTabWidget();layout.addWidget(tabs,1)
            page=W.QWidget();p=W.QVBoxLayout(page);grid=W.QGridLayout();p.addLayout(grid)
            self.quantity=W.QComboBox();self.node=W.QComboBox();self.element=W.QComboBox();self.component=W.QComboBox();self.ip=W.QComboBox();self.step=W.QComboBox()
            for key in ('DISP','VELO','A_DERIVED','FORC','ELKE','ELSE','ENER','ENER_NODAL'):
                self.quantity.addItem(MEANINGS[key]['label']+' ['+MEANINGS[key]['unit']+']',key)
            for r in data['nodes']:self.node.addItem(f"{r['body_id']} / 원 절점 {r['native_node_id']}",(r['body_id'],r['native_node_id']))
            self.element.addItem('원 구조 요소 전체 합 (ENER 제외)',None)
            for r in data['elements']:self.element.addItem(f"{r['body_id']} / 원 요소 {r['native_element_id']} / 입력 {r['element_id']}",r['element_id'])
            for i,label in enumerate('XYZ',1):self.component.addItem(label,i)
            for i in range(1,5):self.ip.addItem(str(i),i)
            self.step.addItem('동적 단계 전체',None)
            for r in data['stages']:
                if r['procedure']=='dynamic':self.step.addItem(str(r['index'])+': '+r['label'],r['id'])
            for i,(label,widget) in enumerate([('결과',self.quantity),('원 절점',self.node),('전역 DOF',self.component),('요소',self.element),('적분점',self.ip),('단계',self.step)]):
                grid.addWidget(W.QLabel(label),i//2,(i%2)*2);grid.addWidget(widget,i//2,(i%2)*2+1)
            self.meaning=W.QLabel();self.meaning.setWordWrap(True);p.addWidget(self.meaning)
            self.plot=Plot();p.addWidget(self.plot,1)
            self.values=table(W,['물리시간 [s]','단계 번호','원본 증분','전체 좌표','값','결측 / 힘 해석'])
            p.addWidget(self.values,1);tabs.addTab(page,'물리시간 결과')
            native=W.QWidget();nl=W.QVBoxLayout(native)
            n=W.QLabel('출력을 선택하면 좌표와 시간의 정의를 확인할 수 있습니다.')
            n.setWordWrap(True);nl.addWidget(n)
            frame_table=self.frame_table=table(W,['단계','절차','원본 증분','전체 좌표','단계 좌표','물리시간 [s]','기록 채널'])
            metadata=frame_metadata(data)
            frame_table.horizontalHeaderItem(3).setToolTip('솔버가 기록한 누적 좌표입니다. 정적 가상좌표가 포함될 수 있어 물리시간과 구별합니다. 프로그램 실행시간이 아닙니다.')
            frame_table.horizontalHeaderItem(4).setToolTip('단계 시작부터의 좌표입니다. 정적 단계는 [1], 동적 단계는 [s]입니다.')
            frame_table.horizontalHeaderItem(5).setToolTip('동적 단계의 누적 실제 시간 [s]입니다. 정적 단계에는 해당하지 않습니다.')
            for i,f in enumerate(metadata):
                frame_table.insertRow(i);loc=f['location']
                unit='s' if loc['procedure']=='dynamic' else '1'
                coordinate=loc['native_step_coordinate_derived']
                for j,v in enumerate([loc['label'],'동적' if loc['procedure']=='dynamic' else '정적',f['native']['increment'],loc['native_global_coordinate'],
                        '결측' if coordinate is None else str(coordinate)+' ['+unit+']',physical_time_text(loc),', '.join(f['field_names'])]):
                    item=_item(W,C,'결측' if v is None else v,False)
                    if j in (3,4,5):item.setToolTip(frame_table.horizontalHeaderItem(j).toolTip()+'\n원값: '+repr([loc['native_global_coordinate'],coordinate,loc['physical_time_s']][j-3]))
                    frame_table.setItem(i,j,item)
            nl.addWidget(frame_table,1)
            self.coordinate_note=W.QLabel();self.coordinate_note.setObjectName('dynamicCoordinateNote')
            self.coordinate_note.setWordWrap(True);nl.addWidget(self.coordinate_note)
            def selected_coordinate(row,*_):
                if row<0:return
                loc=metadata[row]['location']
                self.coordinate_note.setText(loc['label']+': '+(
                    '정적 단계 좌표 [1]는 해석 진행용 가상좌표입니다. 물리시간은 해당되지 않습니다.' if loc['procedure']=='static' else
                    '단계 좌표 [s]는 이 단계의 시간이며, 물리시간 [s]는 동적 단계의 누적 시간입니다.'))
            frame_table.currentCellChanged.connect(selected_coordinate)
            if metadata:frame_table.setCurrentCell(0,0)
            tabs.addTab(native,'단계 / 원 시각')
            for label,file in [('원 입력','solver/contact.inp'),('수렴 기록','solver/contact.sta'),('원 에너지 출력','solver/contact.dat')]:
                text=W.QPlainTextEdit();text.setReadOnly(True);text.setLineWrapMode(W.QPlainTextEdit.NoWrap)
                path=attempt/file
                # Viewing a very large DAT must not stall Qt. Original file remains intact.
                raw=path.open('rb').read(2_000_001) if path.is_file() else b''
                text.setPlainText(raw[:2_000_000].decode('ascii',errors='replace')+('\n[표시만 2 MB로 제한. 원파일은 보존됨.]' if len(raw)>2_000_000 else ''))
                tabs.addTab(text,label)
            bar=W.QHBoxLayout();layout.addLayout(bar)
            restart=W.QPushButton('실제 저장점에서 이어가기…');restart.setEnabled(on_restart is not None);bar.addWidget(restart)
            def resume():
                try:on_restart(attempt)
                except Exception as exc:W.QMessageBox.warning(self,'재시작 차단',str(exc))
            restart.clicked.connect(resume)
            post=W.QPushButton('계산 목록에서 후처리 열기');post.setEnabled(on_post is not None);bar.addWidget(post)
            def open_post():
                try:on_post(attempt)
                except Exception as exc:W.QMessageBox.warning(self,'후처리 열기 실패',str(exc))
            if on_post is not None:post.clicked.connect(open_post)
            close=W.QPushButton('닫기');bar.addStretch();bar.addWidget(close);close.clicked.connect(self.close)
            for widget in (self.quantity,self.node,self.element,self.component,self.ip,self.step):widget.currentIndexChanged.connect(self.update_values)
            self.update_values()
        def update_values(self,*unused):
            q=self.quantity.currentData();nodal=q in ('DISP','VELO','A_DERIVED','FORC','ENER_NODAL')
            self.node.setEnabled(nodal);self.component.setEnabled(nodal and q!='ENER_NODAL')
            self.element.setEnabled(not nodal);self.ip.setEnabled(q=='ENER')
            if q=='ENER' and self.element.currentData() is None:
                self.element.blockSignals(True);self.element.setCurrentIndex(1);self.element.blockSignals(False)
            selected=self.node.currentData()
            try:
                curve=history(data,q,body_id=selected[0] if selected else None,native_node_id=selected[1] if selected else None,
                    component=1 if q=='ENER_NODAL' else self.component.currentData(),element_id=self.element.currentData(),
                    integration_point=self.ip.currentData(),step_id=self.step.currentData())
                self.meaning.setText(curve['meaning'].get('note','원 구조 요소 범위. 외부일·접촉 에너지를 포함한 수지는 아닙니다.' if not nodal else '원 절점 값. 공간 평균하지 않습니다.'))
                self.values.setRowCount(len(curve['rows']))
                for i,r in enumerate(curve['rows']):
                    reason=r['missing_reason'] or r['force_interpretation'] or ''
                    for j,v in enumerate([format(r['time_s'],'.12g'),r['native']['step'],r['native']['increment'],r['native']['load_parameter'],
                        '결측' if r['value'] is None else format(r['value'],'.12g'),ROW_LABELS.get(reason,reason)]):
                        item=_item(W,C,v,False)
                        if j==0:item.setToolTip(repr(r['time_s']))
                        if j==5:item.setToolTip(reason)
                        self.values.setItem(i,j,item)
                self.plot.rows=curve['rows'];self.plot.update()
            except (ValueError,KeyError,TypeError) as exc:
                self.meaning.setText(str(exc));self.values.setRowCount(0);self.plot.rows=[];self.plot.update()
    window=Window();_WINDOWS.add(window)
    window.destroyed.connect(lambda *_:_WINDOWS.discard(window));window.show();return window


def open_failure(W,C,attempt,record,*,parent=None,on_restart=None):
    """No admitted field prefix: retain diagnostics/raw inputs, never synthesize U."""
    import hashlib
    attempt=Path(attempt)
    pins={r['relative']:r for r in record.get('artifacts',[])}
    dialog=W.QDialog(parent);dialog.setWindowTitle('동해석 실패 — 원 입력과 진단');dialog.resize(850,650)
    dialog.setAttribute(C.Qt.WA_DeleteOnClose);layout=W.QVBoxLayout(dialog)
    style(dialog,'DynamicFailure')
    note=W.QLabel(EXECUTION_LABELS.get(record.get('execution_status'),'계산 상태 확인 필요')+' / 읽을 수 있는 수렴 결과가 없습니다.\n결측을 0으로 표시하지 않습니다.')
    note.setObjectName('dynamicResultSummary');note.setToolTip('원 실행 상태: '+str(record.get('execution_status','UNKNOWN'))+'\n보존 결과 위치: '+str(attempt))
    note.setWordWrap(True);layout.addWidget(note)
    tabs=W.QTabWidget();layout.addWidget(tabs,1)
    messages=W.QPlainTextEdit();messages.setReadOnly(True)
    messages.setPlainText('\n\n'.join(str(k)+': '+str(v) for k,v in record.get('diagnostics',{}).items()))
    tabs.addTab(messages,'실패 진단')
    for title,relative in [('원 입력','solver/contact.inp'),('수렴 기록','solver/contact.sta'),('원 에너지 출력','solver/contact.dat')]:
        path=attempt/relative
        if not path.is_file():continue
        from caelab.adapters.frozen_fem import _read
        raw=_read(path);pin=pins.get(relative,{})
        if len(raw)!=pin.get('bytes') or hashlib.sha256(raw).hexdigest()!=pin.get('sha256'):
            raise ValueError('보존 원파일이 계산 기록과 다릅니다: '+relative)
        view=W.QPlainTextEdit();view.setReadOnly(True);view.setLineWrapMode(W.QPlainTextEdit.NoWrap)
        view.setPlainText(raw[:2_000_000].decode('ascii',errors='replace')+('\n[화면 표시 제한. 원파일 보존.]' if len(raw)>2_000_000 else ''))
        tabs.addTab(view,title)
    bar=W.QHBoxLayout();layout.addLayout(bar)
    resume=W.QPushButton('실제 저장점 확인…');resume.setEnabled(on_restart is not None);bar.addWidget(resume)
    def restart():
        try:on_restart(attempt)
        except Exception as exc:W.QMessageBox.warning(dialog,'재시작 차단',str(exc))
    resume.clicked.connect(restart)
    close=W.QPushButton('닫기');close.clicked.connect(dialog.close);bar.addStretch();bar.addWidget(close)
    _WINDOWS.add(dialog);dialog.destroyed.connect(lambda *_:_WINDOWS.discard(dialog));dialog.show();return dialog
