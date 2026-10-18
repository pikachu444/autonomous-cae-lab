"""Native retained fit-candidate inspector. All calculation requires one button.

This is a view of a Numerical owner, not another controller or editable Plan.
Closing it releases readers/timers, and does not cancel an owner calculation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import io
import json
import math
import sys
import uuid

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QThreadPool, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QHBoxLayout, QHeaderView, QLabel,
    QMainWindow, QPlainTextEdit, QPushButton, QSplitter, QTableView, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from caelab.numerical_candidate_detail import (
    COMMAND, TERMINAL, compare_candidate_details, plain, table_rows,
)
from caelab.workbench_client import Client
from .data_window import _Read
from .numerical_methods import STATE


STATES = {**STATE, 'RUNNING':'계산 중', 'QUEUED':'대기', 'UNKNOWN':'미확인',
          'INTERRUPTED':'중단', 'CLEANUP_PENDING':'종료 확인 필요'}
RETENTION = {'RETAINED':'보존됨', 'CURVE_ONLY':'곡선만 보존', 'NOT_RETAINED':'미보존',
             'PARTIAL_OUTPUT':'일부 출력', 'NOT_EVALUATED':'미평가',
             'NOT_RETAINED_BYTE_LIMIT':'보존 용량 초과', 'NOT_RETAINED_CANDIDATE_LIMIT':'보존 후보 수 초과'}
ROLES = {'fit':'피팅', 'holdout':'별도 확인'}


def display(value):
    if value is None:
        return '—'
    if isinstance(value, bool):
        return '포함' if value else '제외'
    if isinstance(value, float):
        return format(value, '.8g') if math.isfinite(value) else '—'
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    return str(value)


class DetailTableModel(QAbstractTableModel):
    """Read-only cells; the plot consumes these very same frozen rows."""
    COLUMNS = (
        ('source_row','원자료 행'),('sample_id','파생 표본'),('axis','시간/축'),('observation','관측 원값'),
        ('prediction','선택 후보 예측'),('raw_residual','원단위 잔차'),
        ('weighted_residual','가중·정규화 잔차'),('included','피팅 포함'),
        ('observation_mask','관측 유효'),('weight','가중치'),('scale','정규화 척도'),
        ('unit','단위'),('role','시험 역할'),('status','시험 상태'),
        ('retention','출력 보존'),('deformation_gradient','지정 변형 F'),
        ('actual_deformation_gradient','후보 수락 F'),('actual_J','후보 수락 J'),
        ('observation_state','관측 event 상태'),('prediction_state','예측 event 상태'),
    )
    COMPARE = (('comparison_prediction','비교 후보 예측'),('comparison_residual','비교 후보 정규화 잔차'))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows, self.columns = [], self.COLUMNS

    def replace(self, rows, comparison=None):
        self.beginResetModel()
        self.rows = deepcopy(rows)
        self.columns = self.COLUMNS + self.COMPARE if comparison is not None else self.COLUMNS
        if comparison is not None:
            for row, pair in zip(self.rows, comparison['rows']):
                row.update(comparison_prediction=pair['right_prediction'], comparison_residual=pair['right_residual'])
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        row = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            key = self.columns[index.column()][0]
            value = row.get(key)
            if key == 'sample_id':return '표본 '+str(index.row()+1) if value is not None else '—'
            if key == 'role':return ROLES.get(value, '미지정')
            if key == 'status':return STATES.get(value, '미확인')
            if key == 'retention':return RETENTION.get(value, '미확인')
            if key in {'observation_state','prediction_state'}:
                return {'OCCURRED':'발생','NOT_OBSERVED':'관측되지 않음','UNKNOWN':'미확인'}.get(value, '—')
            return display(value)
        if role == Qt.ItemDataRole.ToolTipRole:
            return json.dumps(row, ensure_ascii=False, indent=2, allow_nan=False)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation != Qt.Orientation.Horizontal:return str(section+1)
        key,label=self.columns[section]
        if self.rows and key=='axis' and self.rows[0].get('axis_name'):
            return str(self.rows[0]['axis_name'])+' ['+str(self.rows[0].get('axis_unit','?'))+']'
        if self.rows and key in {'observation','prediction','raw_residual','comparison_prediction'}:
            return label+' ['+str(self.rows[0].get('unit','?'))+']'
        return label

    def flags(self, index):
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable


class NumericalCandidateDetailWindow(QMainWindow):
    evidence_preserved = Signal(object)
    evidence_invalidated = Signal()

    def __init__(self, client, *, document_id, job_id, candidate_id, session_id=None,
                 source=None, parent=None, poll_interval=1000, auto_load=True, adopt_callback=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.client = client
        self.document_id, self.job_id = document_id, job_id
        self.session_id, self.source = session_id, deepcopy(source)
        self.candidate_id, self.attempt_job_id = candidate_id, None
        self.comparison_id = self.comparison_attempt = None
        self.view = self.comparison_view = None
        self._evidence_reference = None
        self._last_evidence_comparison = None
        self._report_windows = []
        self._adopt_callback = adopt_callback
        self._command_generation = None
        self._closed = self._populating = self._writing = self._stale_session = False
        self._serial, self._read_worker, self._write_worker = 0, None, None
        self._retired_workers = []
        self.setWindowTitle('후보 상세')
        self.resize(1320, 820)
        self._build()
        from .experiment_analysis_window import attach_candidate_diagnosis
        attach_candidate_diagnosis(self)
        self.timer = QTimer(self)
        self.timer.setInterval(max(100, poll_interval))
        self.timer.timeout.connect(self._poll)
        self.timer.start()
        if auto_load:
            self.refresh()

    def _build(self):
        from .appearance import apply_appearance, configure_plot_fonts
        apply_appearance(QApplication.instance());configure_plot_fonts()
        central = QWidget(self)
        layout = QVBoxLayout(central)
        actions = QHBoxLayout()
        self.read_button = QPushButton('다시 읽기')
        self.detail_button = QPushButton('미보존분 계산')
        self.cancel_button = QPushButton('상세 계산 취소')
        self.save_button = QPushButton('계획 저장')
        self.latest_button = QPushButton('최신 상세 선택')
        self.copy_button = QPushButton('표 복사')
        for button, slot in ((self.read_button,self.refresh),(self.detail_button,self.evaluate_missing),
            (self.cancel_button,self.cancel_attempt),(self.save_button,self.save_owner),
            (self.latest_button,self.select_latest),(self.copy_button,self.copy_table)):
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        evidence_actions = QHBoxLayout()
        self.evidence_purpose = QComboBox()
        self.evidence_purpose.addItem('성공 결과', 'success_judgment')
        self.evidence_purpose.addItem('실패·취소 진단', 'failure_diagnostic')
        self.evidence_purpose.currentIndexChanged.connect(self._purpose_changed)
        self.evidence_button = QPushButton('선택 결과 저장')
        self.evidence_button.setObjectName('preserveCandidateEvidence')
        self.evidence_button.clicked.connect(self.preserve_evidence)
        self.evidence_compare_button = QPushButton('선택 시험 비교')
        self.evidence_compare_button.clicked.connect(self.preserve_comparison)
        self.evidence_report_button = QPushButton('보고서 열기')
        self.evidence_report_button.clicked.connect(self.open_evidence_report)
        self.evidence_adopt_button = QPushButton('계수 채택…')
        self.evidence_adopt_button.clicked.connect(self.adopt_selected)
        self.evidence_adopt_button.setVisible(callable(self._adopt_callback))
        self.evidence_state = QLabel('')
        self.evidence_state.setWordWrap(True)
        for widget in (self.evidence_purpose, self.evidence_button, self.evidence_compare_button, self.evidence_report_button,self.evidence_adopt_button):
            evidence_actions.addWidget(widget)
        layout.addLayout(evidence_actions)
        layout.addWidget(self.evidence_state)
        selectors = QHBoxLayout()
        self.candidates = QComboBox(); self.attempts = QComboBox()
        self.compare_candidates = QComboBox(); self.compare_attempts = QComboBox()
        for label, widget in (('후보',self.candidates),('상세 실행',self.attempts),
                              ('비교 후보',self.compare_candidates),('비교 상세',self.compare_attempts)):
            selectors.addWidget(QLabel(label));selectors.addWidget(widget,1)
        self.candidates.currentIndexChanged.connect(self._select_candidate)
        self.attempts.currentIndexChanged.connect(self._select_attempt)
        self.compare_candidates.currentIndexChanged.connect(self._select_comparison)
        self.compare_attempts.currentIndexChanged.connect(self._select_comparison_attempt)
        layout.addLayout(selectors)
        self.identity = QLabel('원 실행을 읽는 중입니다.')
        self.identity.setWordWrap(True)
        self.identity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        layout.addWidget(self.identity);layout.addWidget(self.status)
        self.residual_summary=QLabel('')
        self.residual_summary.setWordWrap(True)
        self.residual_summary.setToolTip('원 피팅의 고정 포함 행과 가중치를 사용합니다. '
            '정규화 잔차 = (예측−관측) × sqrt(가중치/포함 행수) / 척도. '
            '표본별 가중치가 있으면 sqrt(표본 가중치)를 곱합니다. '
            '별도 확인 시험은 목적함수에 포함하지 않습니다.')
        layout.addWidget(self.residual_summary)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.trials = QTreeWidget()
        self.trials.setHeaderLabels(['시험','역할','상태','보존'])
        self.trials.setRootIsDecorated(False)
        self.trials.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.trials.currentItemChanged.connect(self._draw_trial)
        self.trials.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        splitter.addWidget(self.trials)
        self.tabs = QTabWidget()
        chart = QWidget(); chart_layout = QVBoxLayout(chart)
        self.curve_mode = QComboBox()
        self.curve_mode.addItems(['관측·예측','원단위 잔차','가중·정규화 잔차'])
        self.curve_mode.currentIndexChanged.connect(self._plot)
        self.figure = Figure(tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        chart_layout.addWidget(self.curve_mode)
        chart_layout.addWidget(NavigationToolbar2QT(self.canvas, self))
        chart_layout.addWidget(self.canvas,1)
        self.table = QTableView()
        self.model = DetailTableModel(self)
        self.table.setModel(self.model)
        self.table.setSortingEnabled(False) # source rows and plot order stay identical
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.selectionModel().selectionChanged.connect(self._row_selection_changed)
        self.canvas.mpl_connect('pick_event', self._point_picked)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setDefaultSectionSize(130)
        self.raw = QPlainTextEdit();self.raw.setReadOnly(True)
        self.tabs.addTab(chart,'곡선');self.tabs.addTab(self.table,'원값·잔차 표');self.tabs.addTab(self.raw,'원입력·출력·실패')
        self.tabs.currentChanged.connect(self._show_raw)
        splitter.addWidget(self.tabs);splitter.setStretchFactor(1,1)
        splitter.setSizes([260,1060])
        layout.addWidget(splitter,1)
        self.footer = QLabel()
        self.footer.setWordWrap(True)
        layout.addWidget(self.footer)
        self.setCentralWidget(central)
        self._buttons()

    def _retire_read(self):
        self._serial += 1
        if self._read_worker is not None:
            self._read_worker.abandon()
            self._retired_workers.append(self._read_worker)
            self._read_worker = None
        self._retired_workers = [w for w in self._retired_workers if not w.completed.is_set()]

    def _clear_evidence(self):
        self._evidence_reference = None
        self._last_evidence_comparison = None
        self.evidence_state.clear();self.evidence_state.setToolTip('')
        self.evidence_invalidated.emit()

    def _purpose_changed(self):
        self._clear_evidence()
        self._buttons()

    def _selection_changed(self):
        self._clear_evidence()
        self._command_generation = None
        self._retire_read()
        self.view = self.comparison_view = None
        self.model.replace([])
        self.figure.clear();self.canvas.draw_idle();self.raw.clear()
        self.residual_summary.clear()
        self.trials.clear();self.footer.clear()
        self.identity.setText('선택한 후보 상세를 읽는 중입니다.');self.identity.setToolTip('')
        self.status.clear();self.status.setToolTip('')
        self._buttons()
        self.refresh()

    def _select_candidate(self):
        if self._populating or self._writing:
            return
        self.candidate_id = self.candidates.currentData()
        self.attempt_job_id = None
        self._selection_changed()

    def _select_attempt(self):
        if self._populating or self._writing:
            return
        self.attempt_job_id = self.attempts.currentData()
        self._selection_changed()

    def _select_comparison(self):
        if self._populating or self._writing:
            return
        self.comparison_id = self.compare_candidates.currentData()
        self.comparison_attempt = None
        self._selection_changed()

    def _select_comparison_attempt(self):
        if self._populating or self._writing:
            return
        self.comparison_attempt = self.compare_attempts.currentData()
        self._selection_changed()

    def refresh(self):
        """Only retained owner/result/status reads. This method never submits."""
        if self._closed or self._writing or self._read_worker is not None or not self.candidate_id:
            return
        serial = self._serial
        candidate, attempt = self.candidate_id, self.attempt_job_id
        comparison, comparison_attempt = self.comparison_id, self.comparison_attempt
        source = deepcopy(self.source)
        def read():
            view = self.client.numerical_candidate_detail(self.document_id,self.job_id,candidate,
                attempt_job_id=attempt,source=source)
            other = (self.client.numerical_candidate_detail(self.document_id,self.job_id,comparison,
                attempt_job_id=comparison_attempt,source=view['source']) if comparison else None)
            return view, other
        worker = self._read_worker = _Read(read)
        worker.signals.finished.connect(lambda value,error:self._read_done(serial,worker,value,error))
        QThreadPool.globalInstance().start(worker)
        self._buttons()

    def _read_done(self, serial, worker, value, error):
        if self._closed or serial != self._serial or worker is not self._read_worker:
            return
        self._read_worker = None
        if error:
            self._clear_evidence()
            self.view = self.comparison_view = None
            self.model.replace([]);self.figure.clear();self.canvas.draw_idle();self.raw.clear()
            self.residual_summary.clear()
            self.trials.clear();self.footer.clear()
            self.identity.setText('선택한 결과를 표시할 수 없습니다.');self.identity.setToolTip('')
            self.status.setText('결과를 읽지 못했습니다. 다시 읽기를 누르세요.')
            self.status.setToolTip(str(error))
            self._buttons()
            return
        self.view, self.comparison_view = value
        if self.session_id is None:
            self.session_id = self.view['session_id']
        self._stale_session = self.view['session_id'] != self.session_id
        self._command_generation = self.view['generation']
        self.source = deepcopy(self.view['source'])
        self._populate()

    @staticmethod
    def _fill(combo, rows, current):
        combo.clear()
        for label, value in rows:
            combo.addItem(label,value)
            combo.setItemData(combo.count()-1,str(value) if value is not None else '',Qt.ItemDataRole.ToolTipRole)
        combo.setCurrentIndex(next((i for i in range(combo.count()) if combo.itemData(i)==current),-1))

    def _populate(self):
        view = self.view
        previous = self.trials.currentItem()
        previous_id = previous.data(0,Qt.ItemDataRole.UserRole) if previous else None
        self._populating = True
        try:
            candidates = [(f"후보 {i+1}: {STATES.get(c['execution_status'],'미확인')}",c['candidate_id']) for i,c in enumerate(view['candidates'])]
            self._fill(self.candidates,candidates,self.candidate_id)
            self._fill(self.compare_candidates,[('비교 없음',None),*candidates],self.comparison_id)
            self._fill(self.attempts,[('원계산 보존',None),*[(f"상세 {i+1}: {STATES.get(a['state'],'미확인')}",a['job_id'])
                                                       for i,a in enumerate(view['attempts'])]],self.attempt_job_id)
            other = self.comparison_view
            self._fill(self.compare_attempts,[('원계산 보존',None),*[(f"상세 {i+1}: {STATES.get(a['state'],'미확인')}",a['job_id'])
                for i,a in enumerate(other['attempts'])]] if other else [('비교 없음',None)],self.comparison_attempt)
            self.trials.clear()
            selected = None
            for i,trial in enumerate(view['trials']):
                experiment=next(e for e in view['fit_input']['inputs']['experiments'] if e['id']==trial['experiment_id'])
                observed=experiment['observations']
                name=experiment.get('title') or experiment.get('name') or f'시험 {i+1}'
                component=observed.get('component') or experiment.get('response')
                label=str(name)+(' / '+str(component) if component else '')
                item = QTreeWidgetItem([label,ROLES.get(trial['role'],'미지정'),STATES.get(trial['execution_status'],'미확인'),RETENTION.get(trial['retention'],'미확인')])
                item.setData(0,Qt.ItemDataRole.UserRole,trial['experiment_id'])
                diagnostic={key:trial.get(key) for key in ('experiment_id','role','execution_status','evaluation_status','retention')}
                for col in range(4):item.setToolTip(col,json.dumps(diagnostic,ensure_ascii=False,default=str))
                self.trials.addTopLevelItem(item)
                if trial['experiment_id']==previous_id:
                    selected=item
            self.trials.setCurrentItem(selected or self.trials.topLevelItem(0))
        finally:
            self._populating = False
        candidate=view['candidate']
        units={v['id']:v.get('unit','?') for v in view['fit_input']['inputs']['variables']}
        self.identity.setText('선택 계수: '+', '.join(str(name)+'='+display(value)+' '+str(units.get(name,'?'))
                                                  for name,value in candidate.get('values',{}).items()))
        self.identity.setToolTip(json.dumps({'source':self.source,'candidate_id':self.candidate_id,'attempt_job_id':self.attempt_job_id},ensure_ascii=False,indent=2))
        failure = candidate.get('failure_reason')
        blocked = view.get('detail_eval_blocked')
        note = {'SELECT_LATEST_ATTEMPT':'기존 상세 실행이 있습니다. 최신 상세를 선택한 뒤 미보존분만 평가하세요.',
                'ALL_DETAIL_RETAINED':'선택 실행의 상세가 모두 보존되어 있습니다.',
                'ACTIVE_OR_UNKNOWN_ATTEMPT':'진행 중이거나 상태 미확인인 상세 실행이 있습니다.'}.get(blocked,'')
        if self._stale_session:
            note = '연결이 변경되었습니다. 편집할 계획에서 이 상세 창을 다시 여세요.'
        self.status.setText('원 후보: '+STATES.get(candidate.get('execution_status'),'미확인')+' / 상세: '+
            (STATES.get(view.get('attempt_state'),'미확인') if view.get('attempt_state') else '원계산 보존')+
            (' / 실패 잔차 벌점 '+display(candidate['penalty_applied'])+' [1] (목적값 없음)' if 'penalty_applied' in candidate else '')+
            (' / 원계산 실패: 실행 기록을 확인하세요.' if failure else '')+(' / '+note if note else ''))
        self.status.setToolTip(json.dumps({'candidate':candidate,'attempt_state':view.get('attempt_state'),'blocked':blocked},ensure_ascii=False,default=str))
        self.save_button.setText('계획 저장 *' if view['dirty'] else '계획 저장')
        self._draw_trial();self._buttons()

    def _buttons(self):
        live = bool(self.view) and not self._writing and not self._stale_session
        self.detail_button.setEnabled(live and self.view['can_detail_eval'])
        self.save_button.setEnabled(live)
        self.latest_button.setEnabled(live and bool(self.view.get('latest_attempt_job_id'))
            and self.view['latest_attempt_job_id']!=self.attempt_job_id)
        self.cancel_button.setEnabled(live and self.attempt_job_id is not None
            and self.view.get('attempt_state') not in TERMINAL
            and self.view.get('attempt_state') not in {'UNKNOWN',None})
        self.read_button.setEnabled(not self._writing and self._read_worker is None)
        self.copy_button.setEnabled(bool(self.model.rows))
        from caelab.numerical_candidate_evidence import candidate_detail_readiness
        readiness = None
        compare_ready = False
        if live:
            try:
                readiness = candidate_detail_readiness(self.view, purpose=self.evidence_purpose.currentData())
                if self.comparison_view and self._trial_id():
                    compare_ready = all(candidate_detail_readiness(v, required_experiments=[self._trial_id()])['ready_to_preserve']
                                        for v in (self.view, self.comparison_view))
            except (ValueError, KeyError, TypeError) as error:
                self.evidence_state.setText('선택 결과를 확인하지 못했습니다. 다시 읽기를 누르세요.')
                self.evidence_state.setToolTip(str(error))
        self.evidence_button.setEnabled(live and bool(readiness and readiness['ready_to_preserve']))
        self.evidence_compare_button.setEnabled(live and compare_ready)
        self.evidence_report_button.setEnabled(live and bool(self._evidence_reference or readiness and readiness['ready_to_preserve']))
        self.evidence_adopt_button.setEnabled(live and callable(self._adopt_callback) and
            self.evidence_purpose.currentData()=='success_judgment' and bool(readiness and readiness['ready_to_preserve']))
        self.evidence_purpose.setEnabled(not self._writing)
        if readiness:
            if self._evidence_reference:
                note='선택 결과 저장됨 · 검증시험 합격·공학 승인은 별도입니다.'
            elif readiness['ready_to_preserve']:
                note='실패·취소 기록을 저장하거나 보고서로 여세요.' if readiness['purpose']=='failure_diagnostic' else '선택한 결과를 저장·비교하거나 보고서로 여세요.'
            else:
                codes={item['code'] for item in readiness['issues']}
                if 'SELECTED_ATTEMPT_NOT_SUCCEEDED' in codes:
                    note='선택한 상세 계산이 완료되지 않았습니다. 실행 상태를 확인하거나 실패·취소 진단을 선택하세요.'
                elif any(code.startswith('DETAIL_') for code in codes):
                    note='필수 시험 상세가 없습니다. 미보존분을 계산한 뒤 결과를 확인하세요.'
                elif 'ORIGINAL_CANDIDATE_NOT_SUCCEEDED' in codes:
                    note='성공 후보가 아닙니다. 실패·취소 진단에서 원 기록을 확인하세요.'
                else:note='선택 결과를 사용할 수 없습니다. 시험 상태와 필수 출력·단위를 확인하세요.'
            self.evidence_state.setText(note)
            self.evidence_state.setToolTip(json.dumps(readiness,ensure_ascii=False,indent=2))
        if (self._last_evidence_comparison is not None and
                self._last_evidence_comparison['experiment_id'] == self._trial_id()):
            self.evidence_state.setText('선택 시험의 비교 결과 저장됨 · 후보 순위·공학 승인은 별도입니다.')
        for widget in (self.candidates,self.attempts,self.compare_candidates,self.compare_attempts):
            widget.setEnabled(not self._writing)

    def _trial_id(self):
        item = self.trials.currentItem()
        return item.data(0,Qt.ItemDataRole.UserRole) if item else None

    def _draw_trial(self, *args):
        if self._populating or not self.view or not self._trial_id():
            return
        try:
            identifier = self._trial_id()
            rows = table_rows(self.view,identifier)
            comparison = (compare_candidate_details(self.view,self.comparison_view,identifier)
                          if self.comparison_view else None)
            self.model.replace(rows,comparison)
            included=[row for row in rows if row['included']]
            residuals=[row.get('weighted_residual') for row in included]
            available=bool(included) and all(type(value) in (int,float) and math.isfinite(value) for value in residuals)
            square_sum=sum(value*value for value in residuals) if available else None
            trial=rows[0] if rows else {}
            self.residual_summary.setText('포함 행 '+str(len(included))+'/'+str(len(rows))+
                ', 가중치 '+display(trial.get('weight'))+', 척도 '+display(trial.get('scale'))+' '+str(trial.get('unit',''))+
                '. '+('별도 확인 시험은 목적함수에서 제외합니다. ' if trial.get('role')=='holdout' else '')+
                ('가중·정규화 잔차 제곱합 '+display(square_sum)+' [1].'
                 if square_sum is not None and math.isfinite(square_sum) else '잔차는 미제공 상태입니다.'))
            for column,(key,_) in enumerate(self.model.columns):
                if key=='sample_id':self.table.setColumnHidden(column,not any(row.get('sample_id') is not None for row in rows))
            self._plot();self._show_raw();self._buttons()
        except (ValueError,KeyError,TypeError,IndexError) as error:
            self.model.replace([]);self.figure.clear();self.canvas.draw_idle();self.raw.clear();self.residual_summary.clear()
            self.status.setText('원입력과 표·곡선의 연결이 다릅니다. 원 실행을 다시 확인하세요.')
            self.status.setToolTip(str(error))

    def _plot(self, *args):
        self.figure.clear()
        if not self.view or not self.model.rows:
            self.canvas.draw_idle();return
        rows=self.model.rows
        axis=self.figure.add_subplot(111)
        x=[row.get('axis') if row.get('axis') is not None else i for i,row in enumerate(rows)]
        candidate=self.candidates.currentText().split(':')[0]
        def values(key):
            return [row.get(key) if isinstance(row.get(key),(float,int)) else float('nan') for row in rows]
        mode=self.curve_mode.currentIndex()
        experiment=next(e for e in self.view['fit_input']['inputs']['experiments'] if e['id']==self._trial_id())
        segments=experiment['observations'].get('segments') or [{'rows':[0,len(rows)]}]
        def plot_segments(data, style, label, **kwargs):
            for i,segment in enumerate(segments):
                first,last=segment['rows']
                line,=axis.plot(x[first:last],data[first:last],style,label=label if i==0 else None,picker=5,**kwargs)
                line._detail_rows=list(range(first,last))
        if mode==0:
            observed=values('observation')
            plot_segments([value if row['included'] else float('nan') for value,row in zip(observed,rows)],'o','포함한 관측 원값')
            plot_segments(values('prediction'),'.-',candidate+' 예측')
            if self.comparison_view:
                plot_segments(values('comparison_prediction'),'x--',self.compare_candidates.currentText().split(':')[0]+' 비교 예측')
            if any(not row['included'] for row in rows):
                plot_segments([value if not row['included'] else float('nan') for value,row in zip(observed,rows)],'x','제외한 관측 원값',color='#667588')
            axis.set_ylabel(rows[0]['unit'])
        else:
            key='raw_residual' if mode==1 else 'weighted_residual'
            plot_segments(values(key),'.-',candidate+' 잔차')
            if self.comparison_view:
                other=([b-a if b is not None and a is not None else float('nan')
                        for a,b in zip(values('observation'),values('comparison_prediction'))]
                       if mode==1 else values('comparison_residual'))
                plot_segments(other,'x--',self.compare_candidates.currentText().split(':')[0]+' 비교 잔차')
            axis.set_ylabel(rows[0]['unit'] if mode==1 else '가중·scale 정규화 잔차')
        axis.set_xlabel((str(rows[0].get('axis_name'))+' ['+str(rows[0].get('axis_unit'))+']')
                        if rows[0].get('axis_name') else '원 관측 순서')
        role=rows[0]['role']
        axis.set_title(candidate+' / '+self.trials.currentItem().text(0)+' / '+ROLES.get(role,'미지정')+(' (목적함수 제외)' if role=='holdout' else ''))
        selected=self.table.selectionModel().selectedRows()
        if selected:
            index=selected[0].row()
            key='prediction' if mode==0 else 'raw_residual' if mode==1 else 'weighted_residual'
            value=rows[index].get(key)
            if value is None and mode==0:value=rows[index].get('observation')
            if type(value) in (int,float) and math.isfinite(value):
                axis.plot([x[index]],[value],'o',markersize=11,markerfacecolor='none',markeredgecolor='crimson',markeredgewidth=2)
            self.footer.setText('선택 행 '+str(index+1)+' / '+('원자료 행 '+str(rows[index]['source_row']) if rows[index].get('source_row') is not None else '원자료 행 미지정'))
        else:self.footer.clear()
        axis.legend();axis.grid(True,alpha=.2)
        self.canvas.draw_idle()

    def _row_selection_changed(self, *_):
        if self.view and self.model.rows and not self._populating:self._plot()

    def _point_picked(self,event):
        indexes=getattr(event.artist,'_detail_rows',None)
        if indexes is not None and len(event.ind):
            self.table.selectRow(indexes[int(event.ind[0])])

    def _show_raw(self, *args):
        if self.tabs.currentIndex()!=2 or not self.view or not self._trial_id():
            return
        identifier=self._trial_id()
        experiment=next(e for e in self.view['fit_input']['inputs']['experiments'] if e['id']==identifier)
        trial=next(t for t in self.view['trials'] if t['experiment_id']==identifier)
        payload=dict(source=self.view['source'],candidate=self.view['candidate'],
            attempt_job_id=self.attempt_job_id,experiment=experiment,trial=trial,
            fit_input_sha256=self.view['fit_input']['inputs_sha256'])
        text=json.dumps(plain(payload),ensure_ascii=False,indent=2,allow_nan=False)
        if len(text)>1024*1024:
            text=text[:1024*1024]+'\n[화면 표시 1 MiB 한도. 원 출력은 기존 result reader/owner 저장에 전체 보존됩니다.]'
        self.raw.setPlainText(text)

    def _write(self, function, after):
        if self._closed or self._writing:
            return
        self._retire_read();self._writing=True;self._buttons()
        worker=self._write_worker=_Read(function)
        def done(value,error):
            if self._closed or worker is not self._write_worker:
                return
            self._writing=False;self._write_worker=None
            if error:
                self._clear_evidence();self._command_generation=None
                self.status.setText('명령 처리 결과를 확인하지 못했습니다. 다시 읽기로 실제 접수 여부를 확인하세요.')
                self.status.setToolTip(str(error))
                self.view=None;self._buttons()
                return
            after(value)
            self.refresh()
        worker.signals.finished.connect(done)
        QThreadPool.globalInstance().start(worker)

    def _owner_command(self, operation, arguments, command_id):
        document=self.client.document_read(self.document_id)
        if document['session_id']!=self.session_id:
            raise ValueError('Owner session changed; reopen this view')
        if self._command_generation is None or document['generation']!=self._command_generation:
            raise ValueError('Plan changed after this result was read; reread before saving or adopting')
        response=self.client.document_command(self.document_id,operation,arguments,
            session_id=self.session_id,expected_generation=self._command_generation,command_id=command_id)
        accepted=response.get('document',{})
        if accepted.get('id')==self.document_id and accepted.get('session_id')==self.session_id:
            self._command_generation=accepted['generation']
        return response

    def evaluate_missing(self):
        if not self.view or not self.view['can_detail_eval'] or self._stale_session:
            return
        args=dict(source=deepcopy(self.view['source']),candidate_id=self.candidate_id,
                  base_attempt_job_id=self.attempt_job_id)
        command_id='C'+uuid.uuid4().hex
        def accepted(value):
            self._clear_evidence()
            self.attempt_job_id=value['job']['id']
            self.status.setText('상세 계산을 접수했습니다.');self.status.setToolTip(self.attempt_job_id)
        self._write(lambda:self._owner_command(COMMAND,args,command_id),accepted)

    def cancel_attempt(self):
        if not self.cancel_button.isEnabled():
            return
        identifier=self.attempt_job_id
        self._write(lambda:self.client.cancel(identifier),lambda result:self.status.setText(
            '취소를 요청했습니다. 완료된 시험 출력은 보존합니다.'))

    def save_owner(self):
        if not self.save_button.isEnabled():
            return
        command_id='C'+uuid.uuid4().hex
        self._write(lambda:self._owner_command('document.save',{},command_id),
                    lambda result:self.status.setText('계획과 후보 상세를 저장했습니다.'))

    def preserve_evidence(self):
        if not self.evidence_button.isEnabled():
            return
        self._capture_selected()

    def _capture_selected(self, after=None):
        from caelab.numerical_candidate_evidence import CAPTURE
        arguments = dict(source=deepcopy(self.view['source']), candidate_id=self.candidate_id,
                         attempt_job_id=self.attempt_job_id, purpose=self.evidence_purpose.currentData())
        command_id = 'C' + uuid.uuid4().hex
        def preserved(response):
            self._evidence_reference = deepcopy(response['reference'])
            self.evidence_preserved.emit(deepcopy(response['reference']))
            if after:after(deepcopy(response['reference']))
        self._write(lambda: self._owner_command(CAPTURE, arguments, command_id), preserved)

    def preserve_comparison(self):
        if not self.evidence_compare_button.isEnabled():
            return
        from caelab.numerical_candidate_evidence import CAPTURE, COMPARE, SUCCESS
        experiment_id = self._trial_id()
        views = [deepcopy(self.view), deepcopy(self.comparison_view)]
        def compare():
            refs = []
            for view in views:
                response = self._owner_command(CAPTURE, dict(source=view['source'],
                    candidate_id=view['candidate']['candidate_id'], attempt_job_id=view['attempt_job_id'],
                    purpose=SUCCESS, required_experiments=[experiment_id]), 'C'+uuid.uuid4().hex)
                refs.append(response['reference'])
            return self._owner_command(COMPARE, dict(left=refs[0], right=refs[1],
                experiment_id=experiment_id), 'C'+uuid.uuid4().hex)
        def compared(response):
            self.evidence_state.setText('선택 시험의 비교 결과를 저장했습니다.')
            self._last_evidence_comparison = response['evidence']
        self._write(compare, compared)

    def open_evidence_report(self):
        if not self.evidence_report_button.isEnabled():
            return
        if self._evidence_reference is None:
            self._capture_selected(self._show_evidence_report)
        else:self._show_evidence_report(deepcopy(self._evidence_reference))

    def _show_evidence_report(self, reference):
        from .report_window import ReportWindow
        window = ReportWindow(self.client, reference=deepcopy(reference))
        self._report_windows.append(window)
        window.destroyed.connect(lambda: self._report_windows.remove(window) if window in self._report_windows else None)
        window.show()

    def adopt_selected(self):
        if not self.evidence_adopt_button.isEnabled():return
        if self._evidence_reference is None:
            self._capture_selected(self._adopt_callback)
        else:self._adopt_callback(deepcopy(self._evidence_reference))

    def select_latest(self):
        if self.view and self.view.get('latest_attempt_job_id'):
            self.attempt_job_id=self.view['latest_attempt_job_id']
            self._selection_changed()

    def copy_table(self):
        stream=io.StringIO(newline='')
        writer=csv.writer(stream,delimiter='\t')
        writer.writerow(['candidate_id','attempt_job_id',*[key for key,label in self.model.columns]])
        for row in self.model.rows:
            writer.writerow([row.get('candidate_id'),row.get('attempt_job_id'),
                             *[row.get(key) for key,label in self.model.columns]])
        QApplication.clipboard().setText(stream.getvalue())

    def _poll(self):
        self._retired_workers=[w for w in self._retired_workers if not w.completed.is_set()]
        if any(view and any(a['state'] not in TERMINAL for a in view['attempts'])
               for view in (self.view, self.comparison_view)):
            self.refresh()

    def closeEvent(self, event):
        # Matplotlib's queued singleShot can outlive WA_DeleteOnClose's canvas.
        self.canvas._draw_pending=False
        self._closed=True;self.timer.stop();self._retire_read()
        if self._write_worker is not None:
            self._write_worker.abandon()
            self._retired_workers.append(self._write_worker)
        event.accept()


def main(argv=None):
    parser=argparse.ArgumentParser(description='Native retained Numerical fit candidate inspector')
    parser.add_argument('--service',required=True)
    parser.add_argument('--document-id',required=True)
    parser.add_argument('--job-id',required=True)
    parser.add_argument('--candidate-id',required=True)
    args=parser.parse_args(argv)
    app=QApplication.instance() or QApplication(sys.argv)
    window=NumericalCandidateDetailWindow(Client(args.service),document_id=args.document_id,
        job_id=args.job_id,candidate_id=args.candidate_id)
    window.show()
    return app.exec()


if __name__=='__main__':
    raise SystemExit(main())
