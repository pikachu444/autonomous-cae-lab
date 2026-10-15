"""Independent native Qt viewer of the sealed beam result, including failure logs.

Opening this viewer imports no FreeCAD, solver, AI account or execution owner.
It reads the same native files used by Runner/Post and cannot launch a solve.
"""
from pathlib import Path
import sys
from caelab.adapters.beam_fem import read_saved_run
from caelab.beam_results import channels, CHANNELS
from caelab.beam_model import validate_model
from .beam_visuals import curve_view,qt_gui

_WINDOWS=[]  # Keep modeless native windows alive, removed at close.


def open_result(W,C,folder=None,*,parent=None):
    if folder is None:
        filename,_=W.QFileDialog.getOpenFileName(parent,'빔 결과 열기','','빔 계산 기록 (beam_execution.json)')
        if not filename:return None
        folder=Path(filename).parent
    try:saved=read_saved_run(folder)
    except Exception as exc:
        W.QMessageBox.warning(parent,'결과를 열지 못했습니다',str(exc));return None
    if saved['model'] is not None and saved['model']['draft'].get('output',{}).get('mode')=='raw_stress':
        from .b13_result_window import open_beam_result
        return open_beam_result(W,C,folder,saved,parent=parent)
    G=qt_gui();window=W.QDialog(parent);window.setWindowTitle('빔 결과');window.resize(1080,740)
    window.setAttribute(C.Qt.WA_DeleteOnClose)
    layout=W.QVBoxLayout(window);receipt=saved['execution'];observed=saved['observed'];model=saved['model']
    status_names={'SUCCEEDED':'계산 완료','FAILED':'계산 실패',
                  'REJECTED':'계산하지 않음','CANCELLED':'취소됨'}
    status_text=status_names.get(receipt['execution_status'],receipt['execution_status'])
    if receipt.get('native_output_status')=='PARTIAL_FAILURE':status_text+=' · 부분 결과 검토 필요'
    diagnostic=receipt.get('saved_reader_error') or receipt.get('diagnostics',{}).get('reason','')
    if observed and observed.get('frames') and diagnostic and receipt['execution_status']=='FAILED':status_text='실패한 계산의 결과'
    banner=W.QLabel(status_text+'  |  공학적 승인 아님')
    banner.setWordWrap(True);layout.addWidget(banner)
    if diagnostic:
        text=('읽을 수 있는 결과를 표시합니다. 실패 원인은 계산 로그에서 확인하세요.'
              if observed and observed.get('frames') else '보존된 결과를 읽지 못했습니다. 계산 로그에서 원인을 확인하세요.')
        label=W.QLabel(text);label.setWordWrap(True);layout.addWidget(label)
    tabs=W.QTabWidget();layout.addWidget(tabs)
    fields=W.QWidget();fl=W.QVBoxLayout(fields);tabs.addTab(fields,'성분 결과')
    selectors=W.QHBoxLayout();step=W.QComboBox();component=W.QComboBox()
    step.setAccessibleName('결과 증분');component.setAccessibleName('물리 성분과 단위')
    selectors.addWidget(step);selectors.addWidget(component,1);fl.addLayout(selectors)
    for key,entry in CHANNELS.items():component.addItem(f'{entry[4]} [{entry[2]}]',key)
    frame_label=W.QLabel();frame_label.setWordWrap(True);fl.addWidget(frame_label)
    split=W.QSplitter(C.Qt.Vertical);fl.addWidget(split,1)
    table=W.QTableView();table.setSelectionBehavior(W.QAbstractItemView.SelectRows)
    table.setSelectionMode(W.QAbstractItemView.SingleSelection);table.setAlternatingRowColors(True)
    table.setSortingEnabled(False);table.setAccessibleName('원 빔 절점별 결과')
    curve=curve_view(W,C);split.addWidget(table);split.addWidget(curve);split.setSizes([280,260])
    class Model(C.QAbstractTableModel):
        def __init__(self):super().__init__();self.rows=[];self.unit=''
        def rowCount(self,parent=C.QModelIndex()):return 0 if parent.isValid() else len(self.rows)
        def columnCount(self,parent=C.QModelIndex()):return 0 if parent.isValid() else 3
        def data(self,index,role=C.Qt.DisplayRole):
            if not index.isValid():return None
            if role==C.Qt.DisplayRole:
                value=self.rows[index.row()][index.column()]
                return str(value) if index.column()==0 else f'{value:.9g}'
            if role==C.Qt.TextAlignmentRole:return int(C.Qt.AlignRight|C.Qt.AlignVCenter)
            return None
        def headerData(self,section,orientation,role=C.Qt.DisplayRole):
            if role!=C.Qt.DisplayRole:return None
            return ['원 절점','길이 [mm]',f'값 [{self.unit}]'][section] if orientation==C.Qt.Horizontal else str(section+1)
        def replace(self,rows,unit):
            self.beginResetModel();self.rows=rows;self.unit=unit;self.endResetModel()
    values=Model();table.setModel(values);table.horizontalHeader().setSectionResizeMode(W.QHeaderView.Stretch)
    def refresh(*_):
        if not observed or not observed['frames']:return
        fi=step.currentIndex()
        if fi<0:return
        key=component.currentData();ch=channels(observed['frames'][fi])[key]
        _,_,stations=validate_model(model)
        rows=[(n,stations[n],value) for n,value in ch['values'].items()];rows.sort(key=lambda r:r[1])
        values.replace(rows,ch['unit']);curve.set_values(rows,f"{ch['label']} [{ch['unit']}]")
        coord='전체 좌표계' if ch['frame']=='GLOBAL' else '단면 좌표계'
        extra=' / 절점힘이며 지지부 합반력이 아닙니다.' if key.startswith('RF_') else ''
        frame_label.setText(f'절점 결과 / {coord}{extra}')
        frame_label.setToolTip(f'원 출력의 저장 성분: {ch["source_component"]}')
    if observed:
        for frame in observed['frames']:
            s=frame['static'];step.addItem(f'단계 {s["step"]} / 증분 {s["increment"]} · 하중 {s["load_parameter"]:g}')
        step.setCurrentIndex(len(observed['frames'])-1)
    else:
        fl.insertWidget(0,W.QLabel('읽을 수 있는 완전한 결과 증분이 없습니다. 원 입력과 로그는 유지됩니다.'))
        step.setEnabled(False);component.setEnabled(False)
    step.currentIndexChanged.connect(refresh);component.currentIndexChanged.connect(refresh)
    curve.on_select=lambda row:table.selectRow(row)
    def selected(current,previous):
        if current.isValid():curve.selected=current.row();curve.update()
    table.selectionModel().currentRowChanged.connect(selected)
    native=W.QWidget();nl=W.QVBoxLayout(native);tabs.addTab(native,'원 조건')
    info=W.QPlainTextEdit();info.setReadOnly(True);nl.addWidget(info)
    if model:
        d=model['draft'];s=d['section'];a=model['axes']
        lines=[f'단면: 폭 {s["width_mm"]} × 높이 {s["height_mm"]} mm / 회전 {s["rotation_deg"]}°',
            f'재료: E {d["material"]["young_MPa"]} MPa, ν {d["material"]["poisson"]}',
            '단면 1축: '+str(a['local1']),'단면 2축: '+str(a['local2']),'길이 방향: '+str(a['tangent']),
            '','실제 CLOAD / BOUNDARY 입력:','']
        deck=Path(folder)/'solver'/'beam.inp'
        if not deck.exists():deck=Path(folder)/'frozen_input'/'beam.inp'
        if deck.exists():lines.append(deck.read_text(encoding='ascii'))
        info.setPlainText('\n'.join(lines))
    logs=W.QWidget();ll=W.QVBoxLayout(logs);tabs.addTab(logs,'계산 로그')
    log_choice=W.QComboBox();log_text=W.QPlainTextEdit();log_text.setReadOnly(True)
    ll.addWidget(log_choice);ll.addWidget(log_text)
    candidates=[]
    if diagnostic:
        log_choice.addItem('저장된 진단');candidates.append(None)
    for item in receipt.get('artifacts',[]):
        path=Path(folder)/item['relative']
        if path.suffix.lower() in ('.log','.txt','.sta','.cvg','.dat','.stdout','.stderr'):
            candidates.append(path);log_choice.addItem(path.name)
    def load_log(index):
        if 0<=index<len(candidates):
            if candidates[index] is None:
                log_text.setPlainText(str(diagnostic));return
            with candidates[index].open('rb') as stream:text=stream.read(2*1024**2)
            log_text.setPlainText(text.decode('utf-8',errors='replace'))
    log_choice.currentIndexChanged.connect(load_log);load_log(0)
    absent=W.QLabel('회전각·지지부 합반력·반력 모멘트는 이 출력 방식에서 제공하지 않습니다. 단면 모멘트와 구분합니다.')
    absent.setWordWrap(True);layout.addWidget(absent)
    buttons=W.QHBoxLayout();copy=W.QPushButton('계산 폴더 경로 복사');buttons.addWidget(copy)
    copy.clicked.connect(lambda:W.QApplication.clipboard().setText(str(Path(folder).absolute())))
    export=W.QPushButton('성분 표 저장…');buttons.addWidget(export)
    def export_table():
        import csv
        name,_=W.QFileDialog.getSaveFileName(window,'성분 표 저장','','CSV (*.csv)')
        if not name:return
        with open(name,'w',newline='',encoding='utf-8-sig') as f:
            writer=csv.writer(f);writer.writerow(['native_node_id','station_mm',str(component.currentData())+' ['+values.unit+']']);writer.writerows(values.rows)
    export.clicked.connect(export_table);export.setEnabled(bool(observed))
    close=W.QPushButton('닫기');buttons.addWidget(close);close.clicked.connect(window.close);layout.addLayout(buttons)
    refresh();_WINDOWS.append(window)
    window.destroyed.connect(lambda *_:_WINDOWS.remove(window) if window in _WINDOWS else None)
    window.show();return window


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='Open a saved beam run without FreeCAD/solver execution')
    parser.add_argument('folder',nargs='?');args=parser.parse_args(argv)
    try:
        from PySide6 import QtWidgets as W,QtCore as C
        research_qt=True
    except ImportError:
        research_qt=False
        from PySide import QtCore as C
        try:from PySide import QtWidgets as W
        except ImportError:from PySide import QtGui as W
    app=W.QApplication.instance() or W.QApplication(sys.argv[:1])
    if research_qt:
        from apps.research.appearance import apply_appearance
        apply_appearance(app)
    window=open_result(W,C,args.folder)
    if window is None:return 1
    return app.exec() if hasattr(app,'exec') else app.exec_()


if __name__=='__main__':raise SystemExit(main())
