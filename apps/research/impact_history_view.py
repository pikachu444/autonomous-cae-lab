"""Exact retained Impact history selection; no owner commands or execution."""
from copy import deepcopy
import json
import math

from PySide6 import QtCore as C, QtWidgets as W
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from caelab.impact_responses import history_catalog, select_history
from .appearance import configure_plot_fonts


MEANINGS = {
    'NATIVE_CUMULATIVE_SIGNED_PAIR_IMPULSE': '원 접촉쌍 누적 충격량입니다. 표본 적분과 구별하며 원 부호를 유지합니다.',
    'DERIVED_INTERVAL_AVERAGE_PAIR_FORCE': '원 누적 충격량의 구간 기울기인 평균 힘입니다. 시각점의 순간 힘이나 물체 반력이 아닙니다.',
    'DERIVED_SAMPLE_TRAPEZOID_NOT_NATIVE_IMPULSE': '선택한 힘 표본의 사다리꼴 적분입니다. 선택 시작의 적분 기준은 0이며 원 누적 충격량 관측이 아닙니다.',
    'ELEMENT_INTERNAL_ENERGY_DENSITY_NOT_TOTAL_ENERGY': '요소 내부 에너지 밀도입니다. 전체 모델의 총 내부 에너지가 아닙니다.',
    'WHOLE_MODEL_INTERNAL_ENERGY_NOT_ELEMENT_DENSITY': '전체 모델의 내부 에너지입니다. 요소 에너지 밀도와 구별합니다.',
    'NATIVE_CURRENT_TOTAL_MASS_NOT_INPUT_ORIGINAL_MASS': '원 출력의 현재 총질량입니다. 입력 기반 초기 질량과 구별합니다.',
    'NATIVE_ADDED_MASS_NOT_ORIGINAL_MASS': '원 출력의 추가 질량입니다. 초기 질량이 아닙니다.',
    'NATIVE_ADDED_MASS_PERCENTAGE': '원 출력의 추가 질량 비율입니다.',
    'INDIVIDUAL_GLOBAL_ENERGY_OR_WORK_NOT_BALANCE_VERDICT': '개별 전체 에너지 또는 일 이력입니다. 에너지 평형 판정으로 해석하지 않습니다.',
    'DERIVED_PAIRED_SEPARATION_NOT_NATIVE_PENE': '초기 대응 벌크면의 분리 거리입니다. 솔버의 접촉 관입량이 아닙니다.',
}
QUANTITY_NAMES = {'force':'접촉쌍 구간 평균 힘', 'native_impulse':'원 접촉쌍 누적 충격량',
    'sampled_impulse':'접촉력 표본 적분', 'face_separation':'대응면 분리 거리',
    'face_opening_change':'대응면 벌어짐 변화', 'face_slip_change':'대응면 미끄럼 변화',
    'cohesive_active':'응집 요소 활성', 'displacement':'변위', 'velocity':'속도',
    'acceleration':'가속도', 'stress':'응력', 'contact_force':'전체 접촉 절점 힘',
    'contact_impulse':'접촉력 표본 적분', 'cohesive_damage':'응집 손상',
    'internal_energy_density':'요소 내부 에너지 밀도'}
GLOBAL_NAMES = {1:'전체 내부 에너지', 6:'현재 총질량', 17:'추가 질량', 18:'추가 질량 비율'}


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def shown(value):
    return format(value, '.10g') if number(value) else '기록 없음' if value is None else str(value)


class _SamplesTable(W.QTableWidget):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.currentItem() is not None:
            horizontal=self.horizontalScrollBar().value()
            self.scrollToItem(self.currentItem())
            self.horizontalScrollBar().setValue(horizontal)


class ImpactHistoryView(W.QDialog):
    study_requested = C.Signal(object)
    plan_requested = C.Signal(object)

    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        self.setWindowTitle('해석 이력 선택'); self.resize(1180, 850); self.setMinimumSize(760, 640)
        configure_plot_fonts()
        self._snapshot = deepcopy(snapshot); self._selected = None; self._row = -1
        self._loading = False; self._catalog_error = ''
        root = W.QVBoxLayout(self)
        self.status = W.QLabel(); self.status.setWordWrap(True); root.addWidget(self.status)
        grid = W.QGridLayout(); root.addLayout(grid)
        self.channel = W.QComboBox(); self.channel.setObjectName('historyChannel')
        self.start = W.QComboBox(); self.start.setObjectName('historyStart')
        self.end = W.QComboBox(); self.end.setObjectName('historyEnd')
        self.transform = W.QComboBox(); self.transform.setObjectName('historyTransform')
        self.transform.addItem('보존된 원 이력', 'identity')
        self.transform.addItem('힘 표본 사다리꼴 적분 (별도 파생량)', 'sample_trapezoid')
        grid.addWidget(W.QLabel('이력 채널'),0,0); grid.addWidget(self.channel,0,1,1,5)
        for col,label,widget in [(0,'시작 [s]',self.start),(2,'끝 [s]',self.end),(4,'표시',self.transform)]:
            grid.addWidget(W.QLabel(label),1,col);grid.addWidget(widget,1,col+1)
        for widget in (self.channel,self.start,self.end,self.transform):
            widget.setSizeAdjustPolicy(W.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            widget.setMinimumContentsLength(10)
        self.context = W.QLabel();self.context.setWordWrap(True);root.addWidget(self.context)
        self.meaning = W.QLabel();self.meaning.setWordWrap(True);root.addWidget(self.meaning)
        self.tabs = W.QTabWidget();root.addWidget(self.tabs,1)
        workspace = W.QWidget();layout = W.QVBoxLayout(workspace);layout.setContentsMargins(0,0,0,0)
        self.splitter = W.QSplitter(C.Qt.Orientation.Vertical);layout.addWidget(self.splitter)
        self.figure=Figure(constrained_layout=True);self.canvas=FigureCanvasQTAgg(self.figure)
        self.splitter.addWidget(self.canvas)
        self.table=_SamplesTable();self.table.setObjectName('historySamples')
        self.table.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(W.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True);self.table.verticalHeader().hide()
        self.splitter.addWidget(self.table);self.splitter.setSizes([340,230])
        self.tabs.addTab(workspace,'곡선과 원행')
        self.details=W.QPlainTextEdit();self.details.setReadOnly(True);self.tabs.addTab(self.details,'원자료 상세')
        self.selection_label=W.QLabel('원행을 선택하면 값과 평균 힘의 원 구간을 확인할 수 있습니다.')
        self.selection_label.setWordWrap(True);root.addWidget(self.selection_label)
        self.message=W.QLabel();self.message.setWordWrap(True);root.addWidget(self.message)
        buttons=W.QHBoxLayout();root.addLayout(buttons)
        self.study_button=W.QPushButton('연구 기록에 추가…');self.plan_button=W.QPushButton('수치 계획으로…')
        buttons.addWidget(self.study_button);buttons.addWidget(self.plan_button);buttons.addStretch()
        close=W.QPushButton('닫기');close.clicked.connect(self.reject);buttons.addWidget(close)
        self.study_button.clicked.connect(lambda: self._emit(self.study_requested))
        self.plan_button.clicked.connect(lambda: self._emit(self.plan_requested))
        self.channel.currentIndexChanged.connect(self._channel_changed)
        for widget in (self.start,self.end,self.transform):widget.currentIndexChanged.connect(self._refresh)
        self.table.currentCellChanged.connect(self._select_row)
        self.canvas.mpl_connect('pick_event',self._pick)
        try:
            self.catalog=history_catalog(self._snapshot)
            self._channels=self.catalog['channels']
        except (ValueError,TypeError,KeyError) as error:
            self.catalog={};self._channels=[];self._catalog_error=str(error);self.message.setText(str(error))
        result=self._snapshot.get('result',{});state=result.get('execution_status')
        states={'SUCCEEDED':'완료','FAILED':'실패','PARTIAL_FAILURE':'일부 실패',
            'CANCELLED':'취소','INTERRUPTED':'중단'}
        if result.get('operation')=='impact.reprocess':
            readback={'SUCCEEDED':'읽기 완료','FAILED':'읽기 실패 또는 일부만 읽음',
                'PARTIAL_FAILURE':'일부만 읽음','CANCELLED':'읽기 취소','INTERRUPTED':'읽기 중단'}
            caption='보존 결과 재읽기: '+readback.get(state,'상태 미확인')
            caption+=' / 원 계산: '+states.get(result.get('source_execution_status'),'미확인')
            caption+=' / 새 솔버 계산: '+('미실행' if result.get('solver_execution')=='NOT_PERFORMED' else '미확인')
        else:
            caption='보존 해석: '+states.get(state,'상태 미확인')
        self.status.setText(caption+' / 공학 적합성: 미확인')
        self.channel.blockSignals(True)
        for item in self._channels:
            response=self._snapshot['result']['responses'][item['response']]
            label=QUANTITY_NAMES.get(item['selection'].get('quantity')) or GLOBAL_NAMES.get(response.get('metadata',{}).get('native_variable')) or item['label']
            location=item.get('location')
            if isinstance(location,dict) and location.get('kind') in ('node','element'):
                label+=' / '+('절점 ' if location['kind']=='node' else '요소 ')+str(location.get('id','미기록'))
            component='값' if item.get('component')=='scalar' else item.get('component') or '성분 미기록'
            self.channel.addItem(str(label)+' / '+str(component)+' ['+item['unit']+']',item['response'])
        self.channel.blockSignals(False);self._channel_changed()

    @property
    def selected(self):
        return deepcopy(self._selected)

    def _emit(self, signal):
        if self._selected is not None:signal.emit(self.selected)

    def _channel_changed(self,*_):
        self._loading=True
        old=(self.start.currentData(),self.end.currentData())
        self.start.clear();self.end.clear()
        response=self._snapshot.get('result',{}).get('responses',{}).get(self.channel.currentData(),{})
        raw=response.get('raw_samples',{});times=raw.get('transformed_axis',[]);rows=raw.get('source_rows',[])
        for i,t in enumerate(times):
            if number(t):
                label=str(t)+' / 원행 '+str(rows[i] if i<len(rows) else '미기록')
                self.start.addItem(label,t);self.end.addItem(label,t)
        if self.start.count():
            self.start.setCurrentIndex(max(0,self.start.findData(old[0])))
            final=self.end.findData(old[1]);self.end.setCurrentIndex(final if final>=0 else self.end.count()-1)
        integral=response.get('measure')=='derived_mean_force_from_native_impulse_secants' and response.get('unit')=='N'
        self.transform.model().item(1).setEnabled(integral)
        if not integral:self.transform.setCurrentIndex(0)
        self._loading=False;self._refresh()

    def _refresh(self,*_):
        if self._loading:return
        previous=self.table.item(self.table.currentRow(),0)
        source_row=previous.data(C.Qt.ItemDataRole.UserRole) if previous else None
        self._selected=None;self.study_button.setEnabled(False);self.plan_button.setEnabled(False)
        request={'response':self.channel.currentData(),'start_s':self.start.currentData(),
            'end_s':self.end.currentData(),'side':'native','transform':self.transform.currentData()}
        try:
            packet=select_history(self._snapshot,request)
        except (ValueError,TypeError,KeyError) as error:
            self.table.setRowCount(0);self.figure.clear();self.canvas.draw_idle()
            self.message.setText(str(error) if self._channels else self._catalog_error or '선택할 수 있는 보존 이력이 없습니다.')
            self.context.clear();self.meaning.clear();self.selection_label.clear();self.details.clear();return
        self._selected=packet;rows=packet['rows'];response=packet['response'];raw=packet['response']['raw_samples']
        item=next(c for c in self._channels if c['response']==request['response'])
        pair=item.get('pair') or {};selection=item.get('selection') or {};location=item.get('location') or {}
        sides=pair.get('pair',pair)
        if isinstance(sides,dict) and 'a' in sides and 'b' in sides:
            target='원 표면 '+str(sides['a'])+' ↔ '+str(sides['b'])
        else:
            target=({'node':'원 절점','element':'원 요소'}.get(location.get('kind'),'원 대상')+' '+str(location.get('id',selection.get('identity','미기록')))) if isinstance(location,dict) else '전체 모델' if location=='whole_model' else '원 대상 '+str(location)
        component='스칼라 값' if item.get('component')=='scalar' else str(item.get('component') or '미기록')
        self.context.setText(target+' / 원 성분 '+component+' / 원 부호 유지 / '+
            str(request['start_s'])+'–'+str(request['end_s'])+' s / '+str(len(rows))+'개 원 표본')
        semantics=packet['selection']['semantics'];meaning=MEANINGS.get(semantics['physical_meaning'],'기록된 물리량·측도와 원 좌표계를 유지합니다. 물체별 반력으로 재해석하지 않습니다.')
        row_kind={'CSV_PHYSICAL_LINE':'CSV 실제 행','RAW_TH_RECORD_INDEX':'원 이력 레코드 순번','ANIMATION_FRAME_INDEX':'원 프레임 순번'}.get(semantics.get('source_row_kind'),'원 표본 식별자')
        self.context.setText(self.context.text()+' / 원행 기준: '+row_kind)
        if request['transform']=='sample_trapezoid':meaning=MEANINGS['DERIVED_SAMPLE_TRAPEZOID_NOT_NATIVE_IMPULSE']
        orientation=semantics.get('normal_orientation') or semantics.get('tangent_orientation')
        if orientation:meaning+=' 원 방향 근거: '+(str(orientation) if isinstance(orientation,str) else '원자료 상세에 보존')
        if semantics.get('conversion_kind')=='DERIVED_SECANT':
            meaning+=' 원 누적 충격량 차이 [N s] / 실제 원 구간 시간 [s] = 구간 평균 힘 [N]입니다. 배율 변환이 아닙니다.'
        elif semantics.get('conversion_kind')=='DISPLAY_UNIT_SCALE' and semantics.get('native_unit')!=semantics.get('display_unit') and number(semantics.get('display_scale_from_native')):
            meaning+=' 원 단위 '+str(semantics['native_unit'])+' → 표시 '+str(semantics['display_unit'])+' (배율 '+shown(semantics['display_scale_from_native'])+').'
        self.meaning.setText(meaning)
        source_unit=self._snapshot['result']['responses'][request['response']]['unit']
        self.table.blockSignals(True);self.table.setRowCount(len(rows));self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(['원행','시간 [s]','선택값 ['+response['unit']+']','원 응답 ['+source_unit+']','원 품질','원 계산 포함','구간 끊김','힘의 원 평균 구간 [s]','사유'])
        for r,row in enumerate(rows):
            support=row.get('force_support') or {};interval=support.get('time_interval_s')
            texts=[str(row['source_row']),str(row['time_s']),shown(row['selected_value']),shown(row['value']),
                '유효' if row['quality_valid'] else '확인 필요','포함' if row['calculation_valid'] else '제외',
                '끊김' if row['gap_before'] else '없음',str(interval) if interval else '해당 없음',str(row.get('reason') or '')]
            for c,text in enumerate(texts):
                cell=W.QTableWidgetItem(text);cell.setToolTip(text)
                if c==0:cell.setData(C.Qt.ItemDataRole.UserRole,row['source_row'])
                self.table.setItem(r,c,cell)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(7,190);self.table.setColumnWidth(8,210)
        row_index=next((i for i,r in enumerate(rows) if r['source_row']==source_row),0)
        if rows:self.table.selectRow(row_index)
        self.table.blockSignals(False)
        self._draw()
        self._select_row(row_index)
        valid=sum(q and c and number(v) for q,c,v in zip(raw['quality_valid'],raw['calculation_valid'],raw['transformed_values']))
        outside=sum(bool(r.get('support_crosses_selection')) for r in rows)
        self.message.setText('유효 계산 표본 '+str(valid)+' / '+str(len(rows))+' · 누락과 제외는 연결하거나 0으로 채우지 않습니다.'+
            (' 선택 밖을 포함한 원 평균 구간 '+str(outside)+'개가 있습니다.' if outside else '')+
            (' 초기 질량 특성은 입력 기반이며 원 질량 이력과 별개입니다.' if self.catalog.get('initial_mass_properties') else ''))
        self.details.setPlainText(json.dumps({'원 출처':self.catalog.get('source'),'원 채널':item,
            '선택':packet,'입력 기반 초기 질량 특성':self.catalog.get('initial_mass_properties')},ensure_ascii=False,indent=2))
        self.study_button.setEnabled(True);self.plan_button.setEnabled(True)

    def _draw(self):
        self.figure.clear();self._point_artist=None
        ax=self.figure.add_subplot(111);packet=self._selected;raw=packet['response']['raw_samples']
        x=[];y=[];indices=[]
        for i,(t,v) in enumerate(zip(raw['transformed_axis'],raw['transformed_values'])):
            if i and raw['gap_before'][i]:x.append(float('nan'));y.append(float('nan'));indices.append(None)
            x.append(t);y.append(v if number(v) and raw['quality_valid'][i] and raw['calculation_valid'][i] else float('nan'));indices.append(i)
        line,=ax.plot(x,y,'o-',markersize=3,picker=5);line._history_rows=indices
        ax.set_xlabel('시간 [s]');ax.set_ylabel(('표본 적분' if self.transform.currentData()=='sample_trapezoid' else '보존 응답')+' ['+packet['response']['unit']+']')
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value,_:format(value,'.6g')));ax.grid(True,alpha=.2)
        self.canvas.draw_idle()

    def _select_row(self,row,*_):
        if self._selected is None or not 0<=row<len(self._selected['rows']):return
        self._row=row;sample=self._selected['rows'][row]
        interval=(sample.get('force_support') or {}).get('time_interval_s')
        self.selection_label.setText('선택 원행 '+str(sample['source_row'])+' / '+str(sample['time_s'])+' s / '+
            shown(sample['selected_value'])+' ['+self._selected['response']['unit']+']'+
            (' / 원 평균 구간 '+str(interval)+' s'+(' (선택 범위 밖 포함)' if sample.get('support_crosses_selection') else '') if interval else '')+
            (' / '+str(sample['reason']) if sample.get('reason') else ''))
        if getattr(self,'_point_artist',None) is not None:
            self._point_artist.remove();self._point_artist=None
        raw=self._selected['response']['raw_samples'];value=sample['selected_value']
        if self.figure.axes and number(value) and raw['quality_valid'][row] and raw['calculation_valid'][row]:
            self._point_artist=self.figure.axes[0].scatter([sample['time_s']],[value],s=65,
                facecolors='none',edgecolors='#a83426',linewidths=1.6,zorder=4)
        self.canvas.draw_idle()

    def _pick(self,event):
        indices=getattr(event.artist,'_history_rows',[])
        for index in event.ind:
            if index<len(indices) and indices[index] is not None:
                self.table.selectRow(indices[index]);self.table.scrollToItem(self.table.item(indices[index],0));break
