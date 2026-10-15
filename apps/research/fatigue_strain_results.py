"""Retained plane -> cycle -> original row viewer; no evaluation on selection."""
from __future__ import annotations

from copy import deepcopy
import json

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea, QFormLayout,
    QTabWidget, QVBoxLayout, QWidget, QSizePolicy)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from caelab.fatigue_strain import select_result
from caelab.storage import canonical_hash
from .appearance import configure_plot_fonts
from .fatigue_strain_dialog import location_label

REASONS = {
    'ZERO_OR_NEGATIVE_AMPLITUDE_NO_LIFE_CLAIM': '변형률 진폭이 0이므로 피로 수명을 계산하지 않음',
    'SWT_NON_TENSILE_CYCLE_OUTSIDE_MODEL': 'cycle의 최대 정상응력이 인장(양수)이 아님',
    'STRAIN_AMPLITUDE_OUTSIDE_CALIBRATION': '변형률 진폭이 명시 교정 범위 밖',
    'SWT_MAX_STRESS_OUTSIDE_CALIBRATION': 'cycle 최대응력이 명시 교정 범위 밖',
    'TEMPERATURE_OUTSIDE_CALIBRATION': '평가 온도가 명시 교정 범위 밖',
    'NO_ROOT_IN_CALIBRATED_CYCLE_RANGE_NO_EXTRAPOLATION': '교정 수명 구간 안에 양의 root가 없음',
    'ROOT_DID_NOT_CONVERGE': '양의 root의 구간폭 또는 잔차가 수렴하지 않음',
    'FINITE_HISTORY_ONLY_NO_REPEATING_BLOCK_ASSUMPTION': '유한 이력만 평가함 — 반복 블록을 가정하지 않음',
    'SIMULTANEOUS_TENSOR_BLOCK_BOUNDARY_MISMATCH': '동시 tensor의 블록 시작·끝 값이 맞지 않음',
    'CYCLIC_STATE_NOT_CONFIRMED_STABILIZED': '안정된 cyclic 이력 상태가 확인되지 않음',
    'PROJECTED_BLOCK_NOT_CLOSED_AT_GLOBAL_STRAIN_EXTREMUM': '현재 블록은 정상변형률 극값에서 닫히지 않음',
    'UNPAIRED_RESIDUAL_HALF_CYCLE': '서로 반대 방향의 residual half-cycle 대응이 없음',
    'RESIDUAL_SWT_MAX_MISMATCH': '대응하는 residual half-cycle의 최대 정상응력이 다름',
    'UNKNOWN_OR_NONPOSITIVE_BLOCK_DAMAGE': '블록 전체 damage가 미정 또는 양수가 아님',
    'UNSUPPORTED_MEAN_STRESS_MODEL': '지원되지 않는 평균응력 모델',
    'NONFINITE_OR_UNDERFLOW_TARGET': '피로 식의 목표값이 유한한 양수가 아님',
    'INVALID_POSITIVE_ROOT_BRACKET': '양의 root 구간이 수치적으로 유효하지 않음',
    'NONFINITE_REVERSALS': '반전 횟수가 유한하지 않음',
    'NONFINITE_REPEATING_LIFE': '반복 수명의 유한값을 계산할 수 없음',
    'EXPLICIT_IDENTICAL_STABILIZED_BLOCK_LINEAR_MINER_D1': '동일한 안정 블록의 명시 반복과 선형 Miner D=1 가정',
    'INCOMPLETE_PLANE_SEARCH_NO_GLOBAL_ASSESSMENT': '면 탐색이 끝나지 않아 전체 판단은 미정',
    'EXPLICIT_REPEATING_BLOCK_ASSUMPTIONS': '명시한 동일 안정 블록의 반복 가정',
}


def number(value):
    return '미정' if value is None else format(value, '.8g') if type(value) in (int, float) else str(value)


def reason(value):
    if not value:
        return '계산됨'
    if str(value).startswith('INVALID_OR_MISSING_CALIBRATION:'):
        return '교정자료 또는 숫자 입력 오류 — '+str(value).split(':',1)[1].strip()
    return '; '.join(REASONS.get(part.strip(), '미정: '+part.strip()) for part in str(value).split(';'))


class _PagedTable(QWidget):
    """Small view-only paging helper; keeps original record indices intact."""
    def __init__(self, headers, parent=None, name=''):
        super().__init__(parent)
        self.rows, self.page, self.size = [], 0, 256
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.table=QTableWidget(0,len(headers));self.table.setHorizontalHeaderLabels(headers)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
        self.table.setObjectName(name);self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table,1)
        nav=QHBoxLayout();self.previous=QPushButton('앞 페이지');self.following=QPushButton('다음 페이지');self.count=QLabel()
        self.previous.clicked.connect(lambda:self.move(-1));self.following.clicked.connect(lambda:self.move(1))
        for item in (self.previous,self.following,self.count):nav.addWidget(item)
        nav.addStretch();layout.addLayout(nav)
        self.changed=None;self.table.itemSelectionChanged.connect(self._selected)

    def set_rows(self,rows,select=None):
        self.rows=list(rows);self.page=select//self.size if select is not None else 0
        self.populate()
        if select is not None and 0<=select<len(self.rows):self.table.selectRow(select%self.size)

    def populate(self):
        start=self.page*self.size;part=self.rows[start:start+self.size]
        self.table.blockSignals(True);self.table.clearSelection();self.table.setCurrentCell(-1,-1);self.table.clearContents();self.table.setRowCount(len(part))
        for i,row in enumerate(part):
            for j,value in enumerate(row):
                item=QTableWidgetItem(number(value));item.setToolTip(number(value))
                item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable);self.table.setItem(i,j,item)
        self.table.blockSignals(False)
        self.previous.setEnabled(self.page>0);self.following.setEnabled(start+self.size<len(self.rows))
        self.count.setText(f'{start+1 if part else 0}–{start+len(part)} / {len(self.rows)}')

    def move(self,delta):
        self.page+=delta;self.populate()
        if self.table.rowCount():self.table.selectRow(0)

    def _selected(self):
        if self.table.currentRow()>=0 and self.changed:self.changed(self.page*self.size+self.table.currentRow())

    def resizeEvent(self,event):
        super().resizeEvent(event)
        QTimer.singleShot(0,self._keep_selection_visible)

    def _keep_selection_visible(self):
        item=self.table.currentItem()
        if item:self.table.scrollToItem(item)


class StrainFatigueResults(QDialog):
    def __init__(self,result,job_id=None,selection=None,parent=None):
        super().__init__(parent);configure_plot_fonts()
        self.result=result;self.job_id=job_id;self.plane=None;self.cycle=None;self.source_row=None
        self.setWindowTitle('변형률 피로 결과');self.resize(1180,870);self.setMinimumSize(720,560)
        layout=QVBoxLayout(self);self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.planes=result.get('planes',[])
        self.plane_table=_PagedTable(['면 번호','모델 기준 법선 n','선정 구분','εn 범위 [1]',
            '최대 cycle SWT [MPa]','유한 이력 D','알려진 부분 D','미정 cycle 수'],name='fatiguePlaneRows')
        self.tabs.addTab(self.plane_table,'면 탐색')
        page=QWidget();content=QVBoxLayout(page);self.tabs.addTab(page,'이력과 사이클')
        self.plane_detail=QLabel();self.plane_detail.setWordWrap(True);content.addWidget(self.plane_detail)
        self.figure=Figure(layout='constrained');self.canvas=FigureCanvasQTAgg(self.figure);self.canvas.setMinimumHeight(180)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
        content.addWidget(self.canvas,1)
        self.cycle_table=_PagedTable(['cycle','εa [1]','σn,max [MPa]','횟수','Nf [cycles]',
            'D 증가','원 시작행','원 끝행','판정'],name='fatigueStrainCycleRows')
        content.addWidget(self.cycle_table,1)
        rows_page=QWidget();rows_layout=QVBoxLayout(rows_page);self.tabs.addTab(rows_page,'사이클 원행')
        self.cycle_detail=QLabel();self.cycle_detail.setWordWrap(True);self.cycle_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rows_layout.addWidget(self.cycle_detail)
        self.row_table=_PagedTable(['원행','원 sample','물리 시간 [s]','εn [1]','σn [MPa]','membership / peak'],name='fatigueTensorSourceRows')
        rows_layout.addWidget(self.row_table,1)
        self.selected_row_label=QLabel();self.selected_row_label.setWordWrap(True);rows_layout.addWidget(self.selected_row_label)
        self.damage_figure=Figure(layout='constrained');self.damage_canvas=FigureCanvasQTAgg(self.damage_figure)
        self.damage_canvas.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
        self.tabs.addTab(self.damage_canvas,'부분 누적 곡선')
        original_page=QWidget();original_layout=QVBoxLayout(original_page)
        self.tabs.addTab(original_page,'원 텐서와 교정')
        self.raw_label=QLabel('원행을 선택하면 실제 공급된 tensor 성분과 원 단위를 보여 줍니다.');self.raw_label.setWordWrap(True)
        original_layout.addWidget(self.raw_label)
        self.raw_table=QTableWidget(0,6);self.raw_table.setHorizontalHeaderLabels(['원 물리량','성분','공급 원값','원 단위','변환값','계산 단위'])
        self.raw_table.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
        self.raw_table.setObjectName('fatigueOriginalTensorValues');self.raw_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        original_layout.addWidget(self.raw_table,1)
        scroll=QScrollArea();scroll.setWidgetResizable(True);calpage=QWidget();calform=QFormLayout(calpage);scroll.setWidget(calpage)
        original_layout.addWidget(scroll,1)
        diagnostic=result.get('diagnostics',{});cal=diagnostic.get('calibration',{})
        labels=[('reference','교정 출처'),('conditions','교정 시험 조건'),('failure_definition','실패 정의'),
            ('E','E'),('sigma_f','σf′'),('epsilon_f','εf′'),('b','b'),('c','c'),
            ('stress_unit','응력 교정 단위'),('strain_unit','변형률 교정 단위'),
            ('cycles_min','교정 최소 Nf [cycles]'),('cycles_max','교정 최대 Nf [cycles]'),
            ('strain_amplitude_min','교정 최소 total εa'),('strain_amplitude_max','교정 최대 total εa'),
            ('max_stress_min','교정 최소 σmax'),('max_stress_max','교정 최대 σmax'),
            ('temperature_min_k','교정 최소 온도 [K]'),('temperature_max_k','교정 최대 온도 [K]')]
        for key,label in labels:
            item=QLabel(number(cal.get(key)));item.setWordWrap(True);calform.addRow(label,item)
        for label,value in [('평가 온도 [K]',diagnostic.get('assumed_temperature_k')),
                            ('실제 이력의 시험/구성식 출처',diagnostic.get('constitutive_source')),
                            ('식 버전',diagnostic.get('equation_version')),
                            ('원 고정 component 기준계',result.get('tensor_admission',{}).get('frame')),
                            ('외부 sensor/world 연결',diagnostic.get('sensor_world_alignment'))]:
            item=QLabel(number(value));item.setWordWrap(True);calform.addRow(label,item)
        diagnostics=QPlainTextEdit();diagnostics.setReadOnly(True)
        diagnostics.setPlainText(json.dumps({'diagnostics':result.get('diagnostics'),
            'tensor_admission':result.get('tensor_admission')},ensure_ascii=False,indent=2))
        self.tabs.addTab(diagnostics,'선택적 진단 원문')
        self.message=QLabel('면·cycle·원행 선택은 계산하지 않습니다. 원결과는 변경하지 않습니다.');self.message.setWordWrap(True);layout.addWidget(self.message)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText('닫기')
        self.remember=self.buttons.addButton('선택을 현재 초안에 반영',QDialogButtonBox.ButtonRole.AcceptRole)
        self.remember.setEnabled(bool(job_id and self.planes));self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.plane_table.changed=self._plane_selected;self.cycle_table.changed=self._cycle_selected;self.row_table.changed=self._row_selected
        d=result.get('diagnostics',{});convergence=d.get('search_convergence',{})
        convergence_label={'NOT_ESTABLISHED_SINGLE_GRID':'단일 격자 — 수렴 미확인',
            'WITHIN_DECLARED_RANGE_CHANGE':'선언한 최대 range 변화 허용치 이내',
            'REFINEMENT_NOT_CONVERGED':'최대 range 변화가 허용치 밖'}
        method_label=('CP-SWT 최대 정상변형률 범위 면' if result.get('model_name','').startswith('CP-SWT') else
            '단축 SWT' if result.get('model_name','').startswith('Uniaxial SWT') else '단축 전체 변형률 CMB')
        self.summary.setText('평가 방법: '+method_label+'\n'+
            ('면 탐색 완료' if d.get('complete_plane_search') else '탐색 미완료 — 전체 damage/life 미정')+
            ' / '+convergence_label.get(convergence.get('status'),str(convergence.get('status','')))+
            '\n유한 이력 손상 D와 동일 블록 반복 수명을 구분합니다.')
        if d.get('plane_search_failure'):
            self.summary.setText(self.summary.text()+'\n면 탐색 실패 — '+d['plane_search_failure']['message'])
        if result.get('execution_status')=='CANCELLED':
            self.summary.setText(self.summary.text()+'\n실행 취소를 확인했습니다. 완료된 면만 보존하며 전체 판단은 미정입니다.')
        plane_rows=[]
        for p in self.planes:
            flags=[]
            if p['plane_id'] in result.get('critical_plane_ids',[]):flags.append('최대 εn 범위 · 채택')
            if p['plane_id'] in result.get('diagnostic_max_swt_plane_ids',[]):flags.append('최대 SWT · 진단')
            if p['plane_id'] in result.get('diagnostic_max_damage_plane_ids',[]):flags.append('알려진 최대 D · 진단')
            plane_rows.append([p['plane_id'],', '.join(number(v) for v in p['normal_model']),'; '.join(flags),
                p['normal_strain_range'],p['max_cycle_swt_mpa'],p['miner_damage'],p['admitted_partial_damage'],p['unknown_cycle_count']])
        restore=selection if isinstance(selection,dict) and selection.get('job_id')==job_id and selection.get('result_sha256')==canonical_hash(result) else None
        selected_id=restore.get('plane_id') if restore else result.get('display_plane_id')
        plane_index=next((i for i,p in enumerate(self.planes) if p['plane_id']==selected_id),0)
        self.plane_table.set_rows(plane_rows,plane_index if self.planes else None)
        if restore and self.plane:
            cycle_index=next((i for i,c in enumerate(self.plane['cycles']) if c['cycle']==restore.get('cycle')),None)
            if cycle_index is not None:
                self.cycle_table.set_rows(self.cycle_table.rows,cycle_index)
                if restore.get('source_row') in self.cycle['member_source_rows']:
                    self.row_table.set_rows(self.row_table.rows,self.cycle['member_source_rows'].index(restore['source_row']))
            elif restore.get('source_row') in self.plane['history']['source_rows']:
                self.row_table.set_rows(self.row_table.rows,self.plane['history']['source_rows'].index(restore['source_row']))
        if not self.planes:self.message.setText('보존된 완료 면이 없습니다. 원 실행 상태와 진단을 확인하세요. 결과를 성공으로 바꾸지 않습니다.')

    def selected(self):
        if self.plane is None or not self.job_id:raise ValueError('보존된 면과 job을 먼저 선택하세요')
        return select_result(self.result,job_id=self.job_id,plane_id=self.plane['plane_id'],
            cycle=self.cycle['cycle'] if self.cycle else None,source_row=self.source_row)

    def _plane_selected(self,index):
        self.plane=self.planes[index];self.cycle=None;self.source_row=None;p=self.plane
        repeat=p['repeating_block'];location=location_label(p['location'])
        self.plane_detail.setText('면 '+str(p['plane_id'])+' / '+location+'\n원행 기준: '+({'retained_sample_index':'보존 표본 index (원 파일 행 번호 아님)','physical_line':'원 파일 행'}.get(p['history']['row_kind'],p['history']['row_kind']))+'\n'+
            '유한 이력 D = '+number(p['miner_damage'])+' / 교정 범위 안의 알려진 부분 D = '+number(p['admitted_partial_damage'])+
            '\n반복 가정의 D=1 (블록 등가): '+number(repeat['blocks_to_D1'])+' blocks, '+number(repeat['seconds_to_D1'])+' s — '+reason(repeat['reason']))
        self.cycle_table.set_rows([[c['cycle'],c['amplitude'],c['sigma_max_mpa'],c['count'],c['calibrated_cycles'],
            c['damage'],c['start_source_row'],c['end_source_row'],reason(c['reason'])] for c in p['cycles']])
        self._show_rows();self._draw()

    def _cycle_selected(self,index):
        self.cycle=self.plane['cycles'][index];self.source_row=None;self._show_rows();self._draw()

    def _show_rows(self):
        p,c=self.plane,self.cycle;h=p['history']
        self.member_indices=c['member_indices'] if c else list(range(len(h['time_s'])))
        peak=c['sigma_max_indices'] if c else []
        self.row_table.set_rows([[h['source_rows'][i],h['sample_ids'][i],h['time_s'][i],h['strain'][i],
            h['stress_mpa'][i] if h['stress_mpa'] is not None else None,
            ('cycle 내 σmax' if i in peak else 'cycle 원 표본' if c else '원 이력')]
            for i in self.member_indices])
        self.selected_row_label.setText('원행을 선택하면 원 sample·물리 시간·정확한 위치를 확인할 수 있습니다.')
        self.raw_table.setRowCount(0);self.raw_label.setText('원행을 선택하면 실제 공급 tensor 값을 읽습니다. 재계산하지 않습니다.')
        if not c:
            self.cycle_detail.setText('선택 면의 전체 원 이력입니다. cycle을 선택하면 중첩 제거 후 membership과 closure를 확인합니다.');return
        r=c['root']
        self.cycle_detail.setText('cycle '+str(c['cycle'])+' / '+location_label(p['location'])+'\n'+
            'reversal pair: 원행 '+str(c['start_source_row'])+' → '+str(c['end_source_row'])+
            ' / '+('관측 half branch (0.5 cycle)' if c['count']==.5 else '복귀 가지를 포함한 닫힌 loop')+
            '\nclosure 원행: '+number(c['closure_source_row'])+' / closure 시간 bracket [s]: '+str(c.get('closure_time_bracket_s'))+
            '\n동시 σn,max = '+number(c['sigma_max_mpa'])+' MPa / peak 원행: '+str(c['sigma_max_source_rows'])+
            '\nNf = '+number(r.get('Nf_cycles'))+' cycles / 2Nf = '+number(r.get('reversals'))+' reversals / '+reason(c['reason'])+
            '\nroot 초기 bracket [cycles]: '+str(r.get('bracket_initial_cycles'))+' / 최종 bracket: '+str(r.get('bracket_final_cycles'))+' / 상대잔차: '+number(r.get('relative_residual'))+
            ' / 반복: '+number(r.get('iterations'))+'\n탄성 항: '+number(r.get('elastic_term'))+' / 소성 항: '+number(r.get('plastic_term'))+' ['+r.get('rhs_unit','')+']\n허용치: 구간폭 '+number(r.get('root_options',{}).get('relative_tolerance'))+' / 상대잔차 '+number(r.get('root_options',{}).get('residual_relative_tolerance'))+'\n'+
            '표본 사이의 peak는 만들지 않습니다. reversal 시작:끝 slice가 아니라 아래 membership의 원 표본을 사용합니다.')

    def _row_selected(self,index):
        i=self.member_indices[index];h=self.plane['history'];self.source_row=h['source_rows'][i]
        self.selected_row_label.setText(location_label(self.plane['location'])+' / 원행 '+str(self.source_row)+
            ' / sample '+str(h['sample_ids'][i])+' / 시간 '+number(h['time_s'][i])+' s / εn '+number(h['strain'][i])+
            ' [1] / σn '+number(h['stress_mpa'][i] if h['stress_mpa'] is not None else None)+' MPa')
        bundle=self.result['source_bundle'];channels=bundle['source']['channels'];raw_rows=[]
        admission=self.result['tensor_admission']['channels']
        for role,components in admission.items():
            for component,metadata in components.items():
                response=bundle['responses'][channels[role][component]];value=response['value'][i]
                raw_rows.append(['total strain' if role=='strain' else 'Cauchy stress',component,
                    value,response['unit'],value*metadata['factor_to_internal'],metadata['unit']])
        self.raw_label.setText(self.selected_row_label.text()+'\n원값은 실제 공급 채널이며 다른 성분을 0으로 채우지 않았습니다.')
        self.raw_table.setRowCount(len(raw_rows))
        for row,values in enumerate(raw_rows):
            for col,value in enumerate(values):
                item=QTableWidgetItem(number(value));item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable);self.raw_table.setItem(row,col,item)
        self._draw()

    def _draw(self):
        h=self.plane['history'];self.figure.clear();a=self.figure.add_subplot(211);b=self.figure.add_subplot(212,sharex=a)
        a.plot(h['time_s'],h['strain'],label='원 total 정상변형률')
        if h['stress_mpa'] is not None:b.plot(h['time_s'],h['stress_mpa'],label='원 정상응력')
        if self.cycle:
            for axis,values in ((a,h['strain']),(b,h['stress_mpa'])):
                if values is not None:
                    indices=self.cycle['member_indices'];axis.plot([h['time_s'][i] for i in indices],[values[i] for i in indices],'o',label='선택 사이클 원 표본')
            peaks=self.cycle['sigma_max_indices']
            if peaks:b.plot([h['time_s'][i] for i in peaks],[h['stress_mpa'][i] for i in peaks],'x',markersize=10,label='사이클 최대응력 σmax')
        if self.source_row is not None:
            i=h['source_rows'].index(self.source_row);a.axvline(h['time_s'][i],linestyle='--');b.axvline(h['time_s'][i],linestyle='--')
        a.set_ylabel('total εn [1]');b.set_ylabel('σn [MPa]');b.set_xlabel('물리 시간 [s]');a.legend(fontsize='small')
        if h['stress_mpa'] is not None:b.legend(fontsize='small')
        self.canvas.draw_idle();self.damage_figure.clear();d=self.damage_figure.add_subplot(111)
        d.step([c['cycle'] for c in self.plane['cycles']],[c['admitted_partial_damage'] for c in self.plane['cycles']],where='post')
        d.set_xlabel('rainflow cycle 기록 번호 (물리 시간이 아님)');d.set_ylabel('교정 범위 안의 부분 누적 D [1]')
        d.set_title('미정 cycle은 0으로 완성한 것이 아니며 전체 D와 다릅니다' if self.plane['unknown_cycle_count'] else '선형 Miner 누적')
        self.damage_canvas.draw_idle()


def show_results(parent,result):
    """Apply a checked local selection through the existing host/save contract."""
    def current_key():
        doc=getattr(parent,'document',None)
        return ((doc.get('id'),doc.get('session_id'),doc.get('generation'),getattr(parent,'_selected_job',None),
                 canonical_hash(parent.edited_draft())) if isinstance(doc,dict) and hasattr(parent,'edited_draft') else None)
    key=current_key();draft=deepcopy(parent.edited_draft()) if key else None
    advanced=draft and draft.get('backend')=='damage.rainflow' and 'method' in draft.get('settings',{})
    selection=draft['settings'].get('selection') if advanced else None
    dialog=StrainFatigueResults(result,getattr(parent,'_selected_job',None),selection,parent)
    dialog.remember.setEnabled(bool(advanced and dialog.planes))
    if dialog.exec()!=QDialog.DialogCode.Accepted:return
    if not key or key!=current_key():
        QMessageBox.warning(parent,'선택 반영 중단','현재 문서·조건 또는 선택 job이 바뀌었습니다. 이전 읽기 응답으로 현재 초안을 덮지 않았습니다.');return
    try:selection=dialog.selected()
    except ValueError as error:QMessageBox.warning(parent,'선택 반영 중단',str(error));return
    draft['settings']['selection']=selection
    parent._show_document(parent.document,preserve_draft=draft)
    parent.local_dirty=True;parent._update_actions()
