"""Read retained increment attempts and exact input curves; no evaluation or replay."""
from copy import deepcopy
import math
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QTableWidget,
    QTableWidgetItem,QSplitter,QWidget,QPushButton,QAbstractItemView)
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

class ContactRunDialog(QDialog):
    def __init__(self, runner, job_id, result):
        super().__init__(runner)
        self.runner,self.job_id,self.result=runner,job_id,deepcopy(result)
        self.setWindowTitle('계산 단계'); self.resize(1100,780)
        layout=QVBoxLayout(self)
        status=result.get('execution_status')
        heading=QLabel({'SUCCEEDED':'계산 완료','FAILED':'계산 실패','CANCELLED':'계산 취소'}.get(status,str(status)))
        layout.addWidget(heading)
        self.setup=result.get('executed_setup') or {}
        axis=self.setup.get('axis',{'unit':'1'})
        label='물리시간\n[s]' if axis['unit']=='s' else '누적 단계 진행값\n[1]'
        self.attempts=QTableWidget(0,7)
        self.attempts.setHorizontalHeaderLabels(['단계','증분','시도','반복',label,'증분 크기','상태'])
        self.attempts.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.attempts.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.rows=(result.get('increment_history') or {}).get('rows',[])
        self.attempts.setRowCount(len(self.rows))
        for i,r in enumerate(self.rows):
            values=[r['step_location']['label'],r['increment'],r['attempt'],r['iterations'],
                    format(r['total'],'.10g'),format(r['increment_size'],'.8g') if r.get('increment_size') is not None else '미기록','수렴' if r['converged'] else '미수렴']
            for j,v in enumerate(values):
                item=QTableWidgetItem(str(v)); item.setToolTip(r['raw']); self.attempts.setItem(i,j,item)
        self.attempts.resizeColumnsToContents()
        header_font = self.attempts.horizontalHeader().font()
        header_font.setBold(True)
        metrics = QFontMetrics(header_font)
        self.attempts.setColumnWidth(4, max(self.attempts.columnWidth(4),
            max(metrics.horizontalAdvance(line) for line in label.splitlines()) + 24))
        self.attempts.horizontalHeader().setStretchLastSection(True)
        self.attempts.setMaximumHeight(min(230, max(100, self.attempts.horizontalHeader().height()+len(self.rows)*30+8)))
        layout.addWidget(self.attempts)
        history = result.get('increment_history') or {}
        self.summary = QLabel()
        rejected = history.get('rejected_attempt_count')
        cutbacks = history.get('observed_cutbacks')
        self.summary.setText('거절 시도: '+(str(rejected) if rejected is not None else '미기록')+
            ' / 관측 증분 축소: '+(str(len(cutbacks)) if cutbacks is not None else '미기록')+
            ' / 잔차: STA에 없음')
        self.summary.setWordWrap(True)
        self.summary.setToolTip('증분 크기의 감소가 두 연속 시도에 실제 기록된 경우만 집계합니다. 실행 경과시간은 Runner의 작업 시각이며 이 표의 좌표가 아닙니다.')
        layout.addWidget(self.summary)
        self.condition=QComboBox(); layout.addWidget(self.condition)
        split=QSplitter(Qt.Orientation.Horizontal)
        self.points=QTableWidget(0,2); self.points.setMinimumWidth(250)
        self.points.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        split.addWidget(self.points)
        from .appearance import configure_plot_fonts
        configure_plot_fonts()
        self.figure=Figure(layout='constrained'); self.canvas=FigureCanvasQTAgg(self.figure); split.addWidget(self.canvas)
        split.setSizes([250,750]); layout.addWidget(split,1)
        self.message=QLabel(); self.message.setWordWrap(True); layout.addWidget(self.message)
        row=QHBoxLayout()
        source=QPushButton('이 계산의 조건 수정…'); source.clicked.connect(self.open_saved); row.addWidget(source)
        post=QPushButton('저장된 결과 열기'); post.clicked.connect(self.open_post); row.addWidget(post)
        row.addStretch(); close=QPushButton('닫기'); close.clicked.connect(self.accept); row.addWidget(close)
        layout.addLayout(row)
        self.attempts.itemSelectionChanged.connect(self.select_step)
        self.condition.currentIndexChanged.connect(self.draw)
        if self.rows: self.attempts.selectRow(len(self.rows)-1)
        else:
            self.message.setText((result.get('diagnostics') or {}).get('reason','증분 기록이 없습니다. 원 입력은 그대로 열 수 있습니다.'))
            self.select_step()
    def select_step(self):
        i=self.attempts.currentRow()
        step=self.rows[i]['step'] if 0<=i<len(self.rows) else 1
        program=self.setup.get('program') or {}
        rows=program.get('steps',[])
        self.condition.blockSignals(True); self.condition.clear()
        names={r['object_id']:r['label'] for r in self.setup.get('conditions',[])}
        if 1<=step<=len(rows):
            for c in rows[step-1]['curves']:
                component='하중' if c['component']==0 else '변위 '+'XYZ'[c['component']-1]
                self.condition.addItem(names.get(c['condition_id'],'조건')+' / '+component+' ['+c['unit']+']',c)
        for material in self.setup.get('materials', []):
            if material.get('law') == 'j2_isotropic_hardening':
                curve = material['plasticity']
                self.condition.addItem(material.get('body_id', '물체')+' / J2 경화 곡선',
                    {'kind':'material', 'unit':curve['stress_unit'], 'strain_unit':curve['strain_unit'],
                     'points':[[row[1],row[0]] for row in curve['yield_points']]})
        self.condition.blockSignals(False); self.draw()
        if 0<=i<len(self.rows):
            r=self.rows[i]
            self.message.setText(('수렴한 증분입니다.' if r['converged'] else '미수렴 시도입니다. 표의 좌표는 시도 시작값이며 실패값을 보간하지 않습니다.')+
                ' 선택 단계의 조건을 보존 입력에서 읽었습니다. 조건이 실패 원인이라고 자동 판정하지 않습니다.')
    def draw(self,*_):
        c=self.condition.currentData()
        self.figure.clear(); ax=self.figure.add_subplot(111)
        points=c.get('points',[]) if c else []
        mode=c.get('mode','curve') if c else 'curve'
        if mode!='curve': points=[]
        self.points.setRowCount(len(points))
        unit=c.get('unit','') if c else ''
        material = c is not None and c.get('kind') == 'material'
        axis=('등가 소성변형률 ['+c['strain_unit']+']') if material else ('단계 시간 [s]' if self.setup.get('axis',{}).get('unit')=='s' else '단계 진행값 [1]')
        ordinate=('진응력' if material else '조건값')+' ['+unit+']'
        self.points.setHorizontalHeaderLabels([axis.replace(' [','\n['),ordinate.replace(' [','\n[')])
        for index,caption in enumerate((axis,ordinate)):
            self.points.horizontalHeaderItem(index).setToolTip(caption)
        for i,p in enumerate(points):
            for j,v in enumerate(p): self.points.setItem(i,j,QTableWidgetItem(format(float(v),'.10g')))
        self.points.resizeColumnsToContents()
        self.points.horizontalHeader().setStretchLastSection(True)
        if points: ax.plot([float(p[0]) for p in points],[float(p[1]) for p in points],marker='o')
        else: ax.text(.5,.5,{'hold':'이전 단계 끝값 유지','release':'조건 해제'}.get(mode,'곡선 없음'),ha='center',transform=ax.transAxes)
        ax.set_xlabel(axis); ax.set_ylabel(ordinate); ax.grid(alpha=.2)
        # Re-layout after native Qt resize; do not clip units or crowd tick labels.
        ax.xaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=3))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=6, min_n_ticks=3))
        self.canvas.draw_idle()
    def open_saved(self):
        def work():
            from .desktop import _spawn
            nav=self.runner.client.job_navigation(self.job_id)
            identifier=nav.get('retained_design_input_id')
            if not identifier: raise ValueError('계산에 사용한 편집 가능 입력이 없습니다')
            native=self.runner.client.native_input(identifier)
            if native.get('id')!=identifier or native.get('kind')!='frozen_contact' or not native.get('editable_path'):
                raise ValueError('이 계산의 보존 입력이 아닙니다')
            return _spawn(self.runner.client,['pre','--source',native['editable_path'],'--source-label','계산 조건 수정'])
        self.runner._request('contact-source:'+self.job_id,work,
            lambda value,ticket:self.message.setText('계산 당시의 입력을 새 설계로 열었습니다. 해당 단계를 선택해 수정하고 새로 실행하세요.'),
            relevant=lambda:self.isVisible())
    def open_post(self):
        def work():
            from .desktop import launch_post
            nav=self.runner.client.job_navigation(self.job_id)
            entry=nav.get('post_input') or {}
            if not entry.get('id'): raise ValueError('수렴한 결과가 등록되지 않았습니다')
            return launch_post(self.runner.client,entry['id'],job_id=self.job_id)
        self.runner._request('contact-post:'+self.job_id,work,
            lambda value,ticket:self.message.setText('보존된 결과를 열었습니다. 새 계산은 없습니다.'),
            relevant=lambda:self.isVisible())
