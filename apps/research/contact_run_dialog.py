"""Read retained increment attempts and exact input curves; no evaluation or replay."""
from copy import deepcopy
import math
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QTableWidget,
    QTableWidgetItem,QSplitter,QWidget,QPushButton,QAbstractItemView,QTabWidget,QFileDialog)
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
        self.history = deepcopy(result.get('convergence_history') or {})
        self.rows=deepcopy((result.get('increment_history') or {}).get('rows',[]))
        self.append_unconfirmed()
        self.attempts.setRowCount(len(self.rows))
        for i,r in enumerate(self.rows):
            values=self.attempt_values(r)
            for j,v in enumerate(values):
                item=QTableWidgetItem(str(v)); item.setToolTip(r['raw']); self.attempts.setItem(i,j,item)
        self.attempts.resizeColumnsToContents()
        header_font = self.attempts.horizontalHeader().font()
        header_font.setBold(True)
        metrics = QFontMetrics(header_font)
        self.attempts.setColumnWidth(4, max(self.attempts.columnWidth(4),
            max(metrics.horizontalAdvance(line) for line in label.splitlines()) + 24))
        self.attempts.horizontalHeader().setStretchLastSection(True)
        self.attempts.setMinimumHeight(120)
        self.attempts.setMaximumHeight(min(230, max(100, self.attempts.horizontalHeader().height()+len(self.rows)*30+8)))
        layout.addWidget(self.attempts)
        history = result.get('increment_history') or {}
        self.summary = QLabel()
        rejected = history.get('rejected_attempt_count')
        cutbacks = history.get('observed_cutbacks')
        self.summary.setText('거절 시도: '+(str(rejected) if rejected is not None else '미기록')+
            ' / 관측 증분 축소: '+(str(len(cutbacks)) if cutbacks is not None else '미기록')+
            (' / 반복 기록 연결됨' if self.history.get('rows') else ' / 반복 기록 없음'))
        self.summary.setWordWrap(True)
        self.summary.setToolTip('증분 크기의 감소가 두 연속 시도에 실제 기록된 경우만 집계합니다. 실행 경과시간은 Runner의 작업 시각이며 이 표의 좌표가 아닙니다.')
        layout.addWidget(self.summary)
        self.views = QTabWidget()
        from .convergence_view import ConvergenceView
        self.convergence = ConvergenceView(self.history)
        self.views.addTab(self.convergence, '반복 수렴')
        self.input_page = QWidget()
        input_layout = QVBoxLayout(self.input_page)
        self.views.addTab(self.input_page, '입력 조건')
        layout.addWidget(self.views,1)
        self.condition=QComboBox(); input_layout.addWidget(self.condition)
        split=QSplitter(Qt.Orientation.Horizontal)
        self.points=QTableWidget(0,2); self.points.setMinimumWidth(0)
        self.points.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        split.addWidget(self.points)
        from .appearance import configure_plot_fonts
        configure_plot_fonts()
        self.figure=Figure(layout='constrained'); self.canvas=FigureCanvasQTAgg(self.figure); split.addWidget(self.canvas)
        split.setSizes([250,750]); input_layout.addWidget(split,1)
        self.canvas.setMinimumSize(0,160)
        self.message=QLabel(); self.message.setWordWrap(True); layout.addWidget(self.message)
        row=QHBoxLayout()
        source=QPushButton('조건 수정…'); source.clicked.connect(self.open_saved); row.addWidget(source)
        post=QPushButton('저장된 결과 열기'); post.clicked.connect(self.open_post); row.addWidget(post)
        row.addStretch(); close=QPushButton('닫기'); close.clicked.connect(self.accept); row.addWidget(close)
        layout.addLayout(row)
        self.logs_button=QPushButton('보존 로그 읽기…')
        self.logs_button.setToolTip('반복 기록이 없는 이전 계산의 contact_execution.json을 선택합니다. 원 로그의 기록된 해시를 확인하고 읽기만 합니다.')
        self.logs_button.clicked.connect(self.open_logs)
        input_layout.addWidget(self.logs_button)
        self.attempts.itemSelectionChanged.connect(self.select_step)
        self.condition.currentIndexChanged.connect(self.draw)
        if self.rows: self.attempts.selectRow(len(self.rows)-1)
        else:
            self.message.setText((result.get('diagnostics') or {}).get('reason','증분 기록이 없습니다. 원 입력은 그대로 열 수 있습니다.'))
            self.select_step()
        self.restore_selection()
    def select_step(self):
        i=self.attempts.currentRow()
        step=self.rows[i]['step'] if 0<=i<len(self.rows) else 1
        self.convergence.select_attempt(tuple(self.rows[i][k] for k in ('step','increment','attempt')) if 0<=i<len(self.rows) else None)
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
            self.message.setText(('수렴한 증분입니다.' if r['converged'] else
                ('STA 판정이 없는 시도입니다. 마지막 반복을 수렴으로 추정하지 않습니다.' if r['converged'] is None else
                 '거절 시도입니다. 단계 진행값은 시작값이며 실패 구간을 보간하지 않습니다.')))
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
            from .desktop import open_native_input
            nav=self.runner.client.job_navigation(self.job_id)
            identifier=nav.get('retained_design_input_id')
            if not identifier: raise ValueError('계산에 사용한 편집 가능 입력이 없습니다')
            native=self.runner.client.native_input(identifier)
            if native.get('id')!=identifier or native.get('kind')!='frozen_contact' or not native.get('editable_path'):
                raise ValueError('이 계산의 보존 입력이 아닙니다')
            return open_native_input(self.runner.client,identifier,source_label='계산 조건 수정')
        self.runner._request('contact-source:'+self.job_id,work,
            lambda value,ticket:self.message.setText('계산 당시의 입력을 새 설계로 열었습니다. 해당 단계를 선택해 수정하고 새로 실행하세요.'),
            failed=lambda error:self.message.setText(str(error)),
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

    @staticmethod
    def attempt_values(r):
        return [r['step_location']['label'],r['increment'],r['attempt'],r['iterations'],
                format(r['total'],'.10g') if r.get('total') is not None else '미기록',
                format(r['increment_size'],'.8g') if r.get('increment_size') is not None else '미기록',
                '판정 미기록' if r['converged'] is None else ('수렴' if r['converged'] else '거절')]

    def append_unconfirmed(self):
        known={(r['step'],r['increment'],r['attempt']) for r in self.rows}
        extra={}
        for r in self.history.get('rows',[]):
            key=r['step'],r['increment'],r['attempt']
            if key in known: continue
            extra[key]=max(extra.get(key,0),r['iteration'])
        program=self.setup.get('program') or {}
        for (step,inc,att),count in sorted(extra.items()):
            steps=program.get('steps',[])
            label=steps[step-1].get('label','단계 '+str(step)) if 1<=step<=len(steps) else '단계 '+str(step)
            self.rows.append({'step':step,'increment':inc,'attempt':att,'iterations':count,'total':None,
                'increment_size':None,'converged':None,'raw':'CVG/stdout에 기록됨; STA 판정 없음',
                'step_location':{'label':label}})
        self.rows.sort(key=lambda r:(r['step'],r['increment'],r['attempt']))

    def preferences_key(self):
        import hashlib
        identity=self.job_id+'|'+str(self.setup.get('snapshot_id',''))
        return 'selection/'+hashlib.sha256(identity.encode('utf-8')).hexdigest()

    def restore_selection(self):
        import json
        try:
            value=json.loads(QSettings(QSettings.defaultFormat(),QSettings.UserScope,'AutonomousCAELab','ConvergenceMonitor').value(self.preferences_key(),'{}'))
            key=value.get('attempt')
            for i,row in enumerate(self.rows):
                if [row[k] for k in ('step','increment','attempt')]==key:
                    self.attempts.selectRow(i);break
            self.convergence.metric.setCurrentIndex(max(0,min(int(value.get('metric',0)),self.convergence.metric.count()-1)))
            self.views.setCurrentIndex(max(0,min(int(value.get('tab',0)),self.views.count()-1)))
            self.convergence.tables.setCurrentIndex(max(0,min(int(value.get('detail',0)),3)))
            self.convergence.log_scale.setChecked(value.get('log') is True)
            self.convergence.criterion.setChecked(value.get('criterion') is True)
            iteration=value.get('iteration')
            for i,row in enumerate(self.convergence.rows):
                if row['iteration']==iteration:
                    from .convergence_view import PAGE_SIZE
                    self.convergence.offset=(i//PAGE_SIZE)*PAGE_SIZE
                    self.convergence.refresh_table()
                    self.convergence.ratios.selectRow(i%PAGE_SIZE)
                    break
        except (ValueError,TypeError,OverflowError):
            pass  # Invalid UI preference never changes calculation records.

    def closeEvent(self, event):
        self.save_selection()
        super().closeEvent(event)

    def done(self, result):
        self.save_selection()
        super().done(result)

    def save_selection(self):
        import json
        i=self.attempts.currentRow()
        j=self.convergence.offset+self.convergence.ratios.currentRow()
        iteration=self.convergence.rows[j]['iteration'] if 0<=j<len(self.convergence.rows) else None
        value={'iteration':iteration,'detail':self.convergence.tables.currentIndex(),
               'log':self.convergence.log_scale.isChecked(),'criterion':self.convergence.criterion.isChecked(),
               'attempt':[self.rows[i][k] for k in ('step','increment','attempt')] if 0<=i<len(self.rows) else None,
               'metric':self.convergence.metric.currentIndex(),'tab':self.views.currentIndex()}
        settings=QSettings(QSettings.defaultFormat(),QSettings.UserScope,'AutonomousCAELab','ConvergenceMonitor')
        settings.setValue(self.preferences_key(),json.dumps(value));settings.sync()

    def open_logs(self):
        from pathlib import Path
        filename,_=QFileDialog.getOpenFileName(self,'이 계산의 보존 기록','','계산 기록 (contact_execution.json)')
        if not filename: return
        def work():
            from caelab.calculix_convergence import reopen_convergence, MAX_BYTES
            from caelab.adapters.frozen_fem import _read
            import json
            record_data=_read(Path(filename),MAX_BYTES)
            record=json.loads(record_data)
            if (not self.setup.get('snapshot_id') or
                    record.get('executed_setup',{}).get('snapshot_id')!=self.setup['snapshot_id']):
                raise ValueError('선택한 계산의 보존 입력이 아닙니다.')
            # Same snapshot can be run more than once: require the exact retained
            # raw-file pins as well, not merely equal model identity.
            pins=lambda obj:{r['relative']:r for r in obj.get('artifacts',[])
                             if r['relative'] in ('solver/contact.cvg','solver/ccx_contact.stdout.log')}
            if not pins(self.result) or pins(record)!=pins(self.result):
                raise ValueError('이 시도의 보존 로그를 확인할 수 없습니다. 다른 시도와 섞지 않습니다.')
            return reopen_convergence(Path(filename).parent,record_data=record_data)
        def done(value,ticket):
            selected=self.attempts.currentRow()
            selected_key=tuple(self.rows[selected][k] for k in ('step','increment','attempt')) if 0<=selected<len(self.rows) else None
            self.attempts.blockSignals(True)
            self.history=value
            self.convergence.set_history(value)
            self.append_unconfirmed()
            self.attempts.setRowCount(len(self.rows))
            for i,r in enumerate(self.rows):
                for j,v in enumerate(self.attempt_values(r)):
                    self.attempts.setItem(i,j,QTableWidgetItem(str(v)))
            for i,r in enumerate(self.rows):
                if tuple(r[k] for k in ('step','increment','attempt'))==selected_key:
                    self.attempts.selectRow(i);break
            self.attempts.blockSignals(False)
            self.select_step()
            self.views.setCurrentIndex(0)
            self.summary.setText('보존 로그에서 반복 기록을 읽었습니다. 이전 계산과 원파일은 변경하지 않았습니다.')
        self.runner._request('contact-logs:'+self.job_id,work,done,relevant=lambda:self.isVisible())
