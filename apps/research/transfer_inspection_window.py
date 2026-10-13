"""Exact saved transfer inspection; independent window, no owner mutation."""
import argparse
from copy import deepcopy
import sys
from PySide6.QtCore import Qt,QThreadPool
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
    QPushButton,QSplitter,QWidget,QTableWidget,QTableWidgetItem,QHeaderView)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from .pde_window import _Read
from .appearance import configure_plot_fonts

_ACTIVE_READS=set()


class TransferInspectionWindow(QDialog):
    def __init__(self,client,document_id,job_id,transfer_id=None,iteration=None,parent=None):
        super().__init__(parent);configure_plot_fonts()
        self.client=client;self.document_id=document_id;self.job_id=job_id
        self._closed=False;self._serial=0;self._rows=[];self._start=0
        self.setWindowTitle('전달값 확인');self.resize(1100,780)
        layout=QVBoxLayout(self);header=QHBoxLayout()
        self.selector=QComboBox();self.selector.currentIndexChanged.connect(self._selected)
        header.addWidget(QLabel('전달 / 반복'));header.addWidget(self.selector,1);layout.addLayout(header)
        self.status=QLabel('보존된 전달을 읽는 중…');self.status.setWordWrap(True);layout.addWidget(self.status)
        splitter=QSplitter(Qt.Orientation.Vertical);layout.addWidget(splitter,1)
        self.figure=Figure(constrained_layout=True);self.canvas=FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(240);splitter.addWidget(self.canvas)
        self.canvas.mpl_connect('pick_event',self._pick)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(['절점','좌표','공급값','수신값','차이','필수','수신'])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._plot);splitter.addWidget(self.table);splitter.setSizes([420,240])
        paging=QHBoxLayout();self.previous=QPushButton('이전 행');self.next=QPushButton('다음 행');self.page=QLabel()
        self.previous.clicked.connect(lambda:self._page(-256));self.next.clicked.connect(lambda:self._page(256))
        paging.addWidget(self.previous);paging.addWidget(self.next);paging.addWidget(self.page);paging.addStretch();layout.addLayout(paging)
        self.residual=QLabel();self.residual.setWordWrap(True);layout.addWidget(self.residual)
        self._initial=(transfer_id,iteration)
        self._read(lambda:client.evaluation_transfer(document_id,job_id),self._catalog)

    def _read(self,function,accepted):
        self._serial+=1;serial=self._serial
        work=_Read(function);_ACTIVE_READS.add(work)
        def done(value,error):
            _ACTIVE_READS.discard(work)
            if self._closed or serial!=self._serial:return
            if error:self.status.setText(str(error));return
            accepted(value)
        work.signals.finished.connect(done,Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(work)

    def _catalog(self,payload):
        self.selector.blockSignals(True);self.selector.clear()
        for row in payload['transfers']:
            self.selector.addItem(row['source_name']+' → '+row['target_name']+' / '+str(row['iteration']+1),
                                  (row['id'],row['iteration']))
        desired=self.selector.findData(self._initial)
        if desired>=0:self.selector.setCurrentIndex(desired)
        self.selector.blockSignals(False)
        checks=[c for row in payload['iterations'] for c in row['checks']]
        self.residual.setText('\n'.join(f"반복 {c['iteration']+1}: 잔차 {self._value(c.get('observed'))} / 한계 {self._value(c.get('limit'))} [{c['unit']}]" for c in checks[-3:]))
        if not self.selector.count():
            self.status.setText(payload['diagnostics'].get('reason') or '기록된 전달이 없습니다. 단계 실행 상태를 확인하세요.')
        else:self._selected()

    @staticmethod
    def _value(value):
        return '—' if value is None else format(value,'.7g') if type(value) in (int,float) else str(value)

    def _selected(self,*_):
        self._start=0;self._load()
    def _page(self,offset):
        self._start=max(0,self._start+offset);self._load()
    def _load(self):
        selection=self.selector.currentData()
        if not selection:return
        self.table.setRowCount(0);self._rows=[];self.figure.clear();self.canvas.draw_idle()
        self.status.setText('선택한 전달값을 읽는 중…')
        start=self._start
        self._read(lambda:self.client.evaluation_transfer(self.document_id,self.job_id,*selection,start=start),self._show)

    def _show(self,data):
        self._data=deepcopy(data);self._rows=data['rows'];self.table.setRowCount(len(self._rows))
        unit=data['metadata'].get('unit','?');space=data['metadata'].get('coordinate_units','?')
        self.table.setHorizontalHeaderLabels(['절점','좌표 ['+space+']','공급 ['+unit+']','수신 ['+unit+']','차이 ['+unit+']','필수','수신'])
        for i,row in enumerate(self._rows):
            values=[row['node'],', '.join(self._value(x) for x in row['coordinates']),row['supplied'],row['received'],row['difference'],'예','있음' if row['available'] else '없음']
            for j,value in enumerate(values):self.table.setItem(i,j,QTableWidgetItem(self._value(value)))
        self.status.setText(data['unavailable'] or ('공급값과 수신값 일치' if data['exact_values_match'] else '불일치: '+', '.join(data['metadata_differences'] or ['값'])))
        states={'SUCCEEDED':'완료','FAILED':'실패','CANCELLED':'취소','REJECTED':'거절','RUNNING':'실행 중'}
        target=data['target_attempt']['state']
        self.status.setText('수신 계산 '+states.get(target,target)+' / '+self.status.text())
        self.status.setToolTip(str(data['metadata']))
        self.page.setText(f"{data['start']+1}–{data['start']+data['count']} / {data['total']}")
        self.previous.setEnabled(data['start']>0);self.next.setEnabled(data['start']+data['count']<data['total'])
        if data.get('reference_temperature') is not None:self.status.setText(self.status.text()+' / 구조 기준온도 '+self._value(data['reference_temperature'])+' K')
        self._plot()

    def _plot(self):
        self.figure.clear();ax=self.figure.add_subplot(111)
        rows=[r for r in self._rows if type(r['supplied']) in (int,float)]
        if rows:
            x=[r['node'] for r in rows]
            ax.plot(x,[r['supplied'] for r in rows],label='공급',marker='.',linewidth=1,picker=5)
            ax.plot(x,[r['received'] if type(r['received']) in (int,float) else float('nan') for r in rows],
                    label='수신',linestyle='--',linewidth=1)
            selected=self.table.currentRow()
            if 0<=selected<len(self._rows):
                row=self._rows[selected]
                ax.scatter([row['node']],[row['supplied']],s=65,facecolors='none',edgecolors='#dc2626')
            ax.set_xlabel('보존 절점 번호');ax.set_ylabel(self._data['metadata'].get('unit',''));ax.legend()
        else:ax.text(.5,.5,'표시할 스칼라 전달값 없음',ha='center',transform=ax.transAxes)
        self.canvas.draw_idle()

    def _pick(self,event):
        if not len(event.ind):return
        points=[i for i,row in enumerate(self._rows) if type(row['supplied']) in (int,float)]
        index=int(event.ind[0])
        if index<len(points):self.table.selectRow(points[index])

    def closeEvent(self,event):
        self._closed=True;self._serial+=1;super().closeEvent(event)


def open_transfer_inspection(client,document_id,job_id,*,parent=None):
    window=TransferInspectionWindow(client,document_id,job_id,parent=parent)
    window.show()
    return window


def main(argv=None):
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--service',required=True);parser.add_argument('--document-id',required=True);parser.add_argument('--job-id',required=True)
    args=parser.parse_args(argv)
    from caelab.workbench_client import Client
    app=QApplication.instance() or QApplication(sys.argv[:1])
    window=TransferInspectionWindow(Client(args.service),args.document_id,args.job_id);window.show()
    return app.exec()


if __name__=='__main__':raise SystemExit(main())
