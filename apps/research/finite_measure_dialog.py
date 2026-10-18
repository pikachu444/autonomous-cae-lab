"""Finite observation editors. No owner writes or job submission from a modal.

The draft stores original text, including incomplete numbers. A local preview is
explicitly unsealed; retained audit uses the existing immutable processing DAG.
"""
from copy import deepcopy
import math
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QComboBox, QFormLayout, QHeaderView,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QCheckBox, QScrollArea, QTabWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from caelab.finite_measure import F_COMPONENTS
from caelab.finite_measure_input import default_config, local_preview, RESULT_NAMES
from .material_test_dialog import combo, numeric
from .experiment_dialogs import _ExplicitApplyDialog
from .appearance import configure_plot_fonts
from .report_pages import value_text

LABELS = {'first_Piola':'공칭 응력 P', 'finite_Cauchy':'유한변형 진응력 σ',
          'engineering_strain':'공학 변형률 e', 'stretch':'신장비 λ', 'log_strain':'로그 변형률 ln λ'}


def select(widget, value):
    index = widget.findData(value)
    if index < 0:
        widget.addItem(str(value), value); index = widget.count()-1
    widget.setCurrentIndex(index)


def readonly_table(headers):
    table = QTableWidget(0, len(headers)); table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setWordWrap(False)
    table.verticalHeader().hide()
    table.setAlternatingRowColors(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    return table


def fill_table(table, rows):
    table.setRowCount(len(rows))
    for i,row in enumerate(rows):
        for j,value in enumerate(row):
            item=QTableWidgetItem('—' if value is None else value_text(value))
            item.setToolTip('—' if value is None else str(value)); table.setItem(i,j,item)
    table.resizeColumnsToContents()
    for column in range(table.columnCount()):
        table.setColumnWidth(column,min(220,max(70,table.columnWidth(column))))


class FiniteColumnsDialog(_ExplicitApplyDialog):
    """Column declaration + numeric preview; Cancel leaves all owner state intact."""
    def __init__(self, preview, config=None, parent=None):
        super().__init__(parent)
        configure_plot_fonts()
        self.setWindowTitle('유한변형 시험 설정'); self.resize(1160, 760)
        self.setMinimumSize(800,600)
        self.preview=deepcopy(preview); self._original=deepcopy(config or default_config())
        self.result_config=None
        self._preview_records=[];self._preview_config=None
        root=QVBoxLayout(self); split=QSplitter(); root.addWidget(split,1)
        tabs=QTabWidget();split.addWidget(tabs);split.setChildrenCollapsible(False)
        tabs.setMinimumWidth(330)
        def page(title):
            content=QWidget(); form=QFormLayout(content)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(content)
            tabs.addTab(scroll,title); return form
        columns=[('선택하지 않음',None)]+[(str(name),i) for i,name in enumerate(preview.get('headers',[]))]
        main=page('측정값'); self.time_column=combo(columns)
        self.time_unit=combo([('선택…','')]+[(v,v) for v in ('s','ms','min')])
        self.axis=combo([(a+'축',a) for a in 'xyz'])
        self.scope=QCheckBox('회전·전단 없는 단축·동축 시험임을 확인')
        main.addRow('시간 열',self.time_column); main.addRow('시간 단위',self.time_unit)
        main.addRow('축방향',self.axis); main.addRow(self.scope)
        self.entries={}
        def entry(form,role,title,measures,units):
            source=combo(columns); measure=combo(measures)
            unit=combo([('선택…','')]+[(v,v) for v in units]);self.entries[role]=(source,measure,unit)
            form.addRow(title+' 열',source); form.addRow(title+' 물리량',measure);form.addRow(title+' 단위',unit)
        entry(main,'load','하중', [('축방향 힘','axial_force'),('공칭 응력 P','first_Piola'),
              ('유한변형 진응력 σ','finite_Cauchy')], ('N','kN','Pa','kPa','MPa','GPa'))
        entry(main,'deformation','변형', [('표점 변위','gauge_extension'),('크로스헤드 변위','crosshead_extension'),
              ('공학 변형률','engineering_strain'),('신장비','stretch'),('로그 변형률','log_strain')],('mm','m','μm','1','%'))
        self.measurement=combo([('측정 방식 선택…',''),('접촉식 표점 변위','extensometer_gauge_extension'),
            ('광학 표점 변위','optical_gauge_extension'),('크로스헤드 변위를 표점 변위로 가정','crosshead_assumed_gauge'),
            ('축방향 공학 변형률 측정','measured_axial_strain'),('축방향 신장비 측정','measured_axial_stretch'),
            ('축방향 로그 변형률 측정','measured_log_strain')])
        main.addRow('변형 측정 방식',self.measurement)
        geom=page('치수와 가정'); self.geometry={}
        for key,title,units in [('A0','초기 단면적 A0',('mm2','m2','μm²')),('L0','초기 표점 거리 L0',('mm','m','μm'))]:
            val=QLineEdit(); unit=combo([(v,v) for v in units]); evidence=QLineEdit()
            self.geometry[key]=(val,unit,evidence)
            geom.addRow(title,val);geom.addRow(title+' 단위',unit);geom.addRow(title+' 측정 근거',evidence)
        entry(geom,'area','현재 단면적', [('축에 수직인 현재 면적','current_normal_area')],('mm2','m2','μm²'))
        entry(geom,'J','현재 부피비', [('관측 J','volume_ratio')],('1',))
        self.basis=combo([('변환하지 않음','none'),('현재 면적 A(t)','current_area'),('표점 λ와 관측 J','jacobian'),
            ('전체 F의 det(F)','full_F'),('명시한 J=1 가정','isochoric_assumption')]);geom.addRow('응력 변환 근거',self.basis)
        self.assumptions={}
        for key,title in [('isochoric','J=1 등체적 가정'),('crosshead_equals_gauge','크로스헤드 = 표점 변위 가정')]:
            enabled=QCheckBox(title);enabled.setToolTip('이 가정을 명시적으로 사용합니다. 아래에 판단 근거를 입력하세요.');reason=QLineEdit()
            geom.addRow(enabled);geom.addRow('가정 근거',reason);self.assumptions[key]=(enabled,reason)
        full=page('변형구배'); explain=QLabel('전체 변형구배 F를 사용하면 9성분을 모두 지정하세요. 비대각 성분을 0으로 채우지 않습니다.\n다른 측정값과 원행·시간·방향이 같아야 합니다. 비동축 시험의 스칼라 변환은 지원하지 않습니다.')
        explain.setWordWrap(True);full.addRow(explain)
        for comp in F_COMPONENTS:
            entry(full,'F'+comp,'F'+comp,[('변형구배','deformation_gradient')],('1',))
        outputs=page('변환값');self.outputs={}
        for key,label in LABELS.items():
            check=QCheckBox(label);outputs.addRow(check);self.outputs[key]=check
        self.stress_unit=combo([(v,v) for v in ('MPa','Pa','kPa','GPa')]);outputs.addRow('응력 출력 단위',self.stress_unit)
        notice=QLabel('열 단위는 원자료의 단위 선언입니다. 수치는 계산 과정에서 실제로 환산합니다.\n초안 저장은 계산 성공이 아닙니다. 잘못된 선택과 미완성 숫자는 저장되며 실행 관문에서 차단됩니다.')
        notice.setWordWrap(True);outputs.addRow(notice)
        view=QWidget();layout=QVBoxLayout(view);split.addWidget(view)
        self.preview_button=QPushButton('변환 미리보기');self.preview_button.setAutoDefault(False);layout.addWidget(self.preview_button)
        self.table=readonly_table(['미리보기 행','원값','P','σ','e','λ','ln λ','무효 이유'])
        layout.addWidget(self.table,2)
        self.figure=Figure(constrained_layout=True);self.canvas=FigureCanvasQTAgg(self.figure);layout.addWidget(self.canvas,2)
        self.plot_measure=combo([(label,key) for key,label in LABELS.items()]);layout.addWidget(self.plot_measure)
        self.preview_button.clicked.connect(self.calculate);self.plot_measure.currentIndexChanged.connect(self._draw_preview)
        self.message=QLabel('측정값과 치수를 지정한 뒤 변환 미리보기를 누르세요. 여기서는 원자료와 보존 결과를 변경하지 않습니다.')
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True);root.addWidget(self.message)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('초안에 반영')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        for button in buttons.buttons():button.setAutoDefault(False);button.setDefault(False)
        buttons.accepted.connect(self._accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
        split.setSizes([420,720]);self.restore(self._original)
        for field in tabs.findChildren(QComboBox):
            field.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            field.setMinimumContentsLength(8)
            field.setToolTip(field.currentText());field.currentTextChanged.connect(field.setToolTip)
            field.currentIndexChanged.connect(self._invalidate_preview)
        for field in tabs.findChildren(QLineEdit):field.textChanged.connect(self._invalidate_preview)
        for field in tabs.findChildren(QCheckBox):field.toggled.connect(self._invalidate_preview)

    def restore(self, config):
        for name in ('time_column','time_unit','axis','measurement','basis','stress_unit'):
            select(getattr(self,name),config.get(name,''))
        self.scope.setChecked(config.get('scope_confirmed') is True)
        for role,widgets in self.entries.items():
            item=config.get('columns',{}).get(role,{})
            select(widgets[0],item.get('column'))
            if 'measure' in item:select(widgets[1],item['measure'])
            select(widgets[2],item.get('unit',''))
        for key,(val,unit,evidence) in self.geometry.items():
            item=config.get('geometry',{}).get(key,{})
            val.setText(str(item.get('value','')));select(unit,item.get('unit',''));evidence.setText(item.get('evidence',''))
        for key,(check,reason) in self.assumptions.items():
            item=config.get('assumptions',{}).get(key,{})
            check.setChecked(item.get('enabled') is True);reason.setText(item.get('reason',''))
        for key,check in self.outputs.items():check.setChecked(key in config.get('outputs',[]))

    def draft_config(self):
        config=deepcopy(self._original)
        for name in ('time_column','time_unit','axis','measurement','basis','stress_unit'):
            config[name]=getattr(self,name).currentData()
        config['scope_confirmed']=self.scope.isChecked()
        config['columns']={role:dict(column=src.currentData(),measure=measure.currentData(),unit=unit.currentData())
            for role,(src,measure,unit) in self.entries.items() if src.currentData() is not None}
        if not config['columns']:
            src,measure,unit=self.entries['load']
            config['columns']['load']=dict(column=None,measure=measure.currentData(),unit=unit.currentData())
        config['geometry']={key:dict(value=numeric(val.text()),unit=unit.currentData(),evidence=evidence.text())
            for key,(val,unit,evidence) in self.geometry.items()}
        config['assumptions']={key:dict(enabled=check.isChecked(),reason=reason.text())
            for key,(check,reason) in self.assumptions.items()}
        config['outputs']=[key for key,check in self.outputs.items() if check.isChecked()]
        return config

    def calculate(self,*_):
        try:
            config=self.draft_config();records=local_preview(config,self.preview.get('rows',[]))
            self.table.setHorizontalHeaderLabels(['미리보기 행','원값','P ['+config['stress_unit']+']','σ ['+config['stress_unit']+']','e [1]','λ [1]','ln λ [1]','무효 이유'])
            fill_table(self.table,[[r['preview_row'],'; '.join(str(name)+': '+str(value) for name,value in zip(self.preview.get('headers',[]),r['raw']))]+[r['values'].get(k) for k in LABELS]+[
                '; '.join(LABELS.get(k,k)+': '+v for k,v in r['errors'].items())] for r in records])
            self.table.setColumnWidth(1,140)
            self._preview_records=records;self._preview_config=deepcopy(config);self._draw_preview()
            invalid=sum(bool(r['errors']) for r in records)
            self.message.setText(f'미리보기 {len(records)}행 중 무효 {invalid}행입니다. 무효 이유는 표에서 확인하세요. 이 결과는 아직 보존되지 않았습니다.')
        except (ValueError,TypeError,KeyError,OverflowError) as error:
            self._invalidate_preview();self.message.setText('미리보기 입력을 확인하세요. '+str(error))

    def _invalidate_preview(self,*_):
        self._preview_records=[];self._preview_config=None;self.table.setRowCount(0)
        self.figure.clear();self.canvas.draw_idle()
        self.message.setText('입력이 바뀌었습니다. 변환 미리보기를 눌러 현재 입력을 확인하세요. 초안 반영은 별도입니다.')

    def _draw_preview(self,*_):
        if self._preview_config is None:return
        self.figure.clear();ax=self.figure.add_subplot(111);target=self.plot_measure.currentData()
        values=[r['values'].get(target) for r in self._preview_records]
        # Selection changes the plotted cached values, never the input calculation.
        ax.plot(range(1,len(values)+1),[float('nan') if v is None else v for v in values],'o-')
        ax.set_xlabel('취득 순서 (미리보기)');ax.set_ylabel(LABELS[target]+' ['+(
            self._preview_config['stress_unit'] if target in ('first_Piola','finite_Cauchy') else '1')+']')
        self.canvas.draw()

    def _accept(self):
        self.result_config=self.draft_config();self.accept()


class FiniteAuditDialog(QDialog):
    """Read-only full acquisition grid including invalid rows and raw operands."""
    def __init__(self, result, parent=None):
        super().__init__(parent);self.setWindowTitle('응력과 변형률 변환 결과');self.resize(1150,720)
        configure_plot_fonts();self.result=deepcopy(result)
        root=QVBoxLayout(self);self.channels=combo([((LABELS.get(ch.get('metadata',{}).get('measure'),name)+' ['+str(ch.get('metadata',{}).get('unit',''))+']') if name in RESULT_NAMES.values() else name,name) for name,ch in result.get('channels',{}).items()
            if ch.get('metadata',{}).get('extensions',{}).get('finite_measure')])
        root.addWidget(self.channels)
        self.table=readonly_table(['원행','시간','원값과 변환 근거','변환값','계산 포함','화면 표시','변환 유효성','이유'])
        root.addWidget(self.table,3);self.figure=Figure(constrained_layout=True);self.canvas=FigureCanvasQTAgg(self.figure)
        root.addWidget(self.canvas,2);self.detail=QLabel();self.detail.setWordWrap(True);root.addWidget(self.detail)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.button(QDialogButtonBox.StandardButton.Close).setText('닫기');buttons.rejected.connect(self.reject);root.addWidget(buttons)
        self._selected_row=0
        self.table.currentCellChanged.connect(self._selected)
        self.channels.currentIndexChanged.connect(self._show);self._show()

    def _show(self,*_):
        ch=self.result.get('channels',{}).get(self.channels.currentData(),{});rows=[]
        nodes=ch.get('lineage',{}).get('nodes',{})
        for i,(t,v) in enumerate(zip(ch.get('axis',{}).get('values',[]),ch.get('values',[]))):
            sample=ch['samples'][i];node=nodes[sample['sample_id']]
            relation=node.get('nonlinear_relation',{});operands=relation.get('operands',{})
            names={'load':'하중','deformation':'변형','area':'현재 단면적','J':'부피비 J'}
            raw='; '.join(names.get(role,role)+'='+str(nodes[item['sample_id']]['value'])+' '+str(item.get('metadata',{}).get('unit',''))
                for role,item in operands.items())
            reasons='; '.join(ch.get(k,['']*len(ch['values']))[i] for k in ('operation_reasons','quality_reasons','calculation_reasons') if ch.get(k,['']*len(ch['values']))[i])
            rows.append([sample['source_rows'],t,raw,v,'포함' if ch['calculation_valid'][i] else '제외','표시' if ch['display_visible'][i] else '숨김',
                '유효' if ch['operation_valid'][i] else '무효','; '.join(reasons) if isinstance(reasons,list) else str(reasons)])
        self.table.setHorizontalHeaderLabels(['원행','시간 ['+str(ch.get('axis',{}).get('unit','미기록'))+']','원값과 변환 근거','변환값 ['+str(ch.get('metadata',{}).get('unit','미기록'))+']','계산 포함','화면 표시','변환 유효성','이유'])
        self.table.blockSignals(True);fill_table(self.table,rows);self.figure.clear();ax=self.figure.add_subplot(111)
        self.table.setColumnWidth(2,180)
        # Display mask is a display policy, never an execution mask.
        points=[(i+1,v) for i,v in enumerate(ch.get('values',[])) if ch.get('display_visible',[True]*len(ch.get('values',[])))[i]]
        if points:ax.plot([p[0] for p in points],[float('nan') if p[1] is None else p[1] for p in points],'o-')
        measure=ch.get('metadata',{}).get('measure','')
        ax.set_xlabel('취득 순서');ax.set_ylabel(LABELS.get(measure,measure)+' ['+str(ch.get('metadata',{}).get('unit',''))+']')
        self.canvas.draw();self.detail.setText('무효행도 원행과 함께 표시합니다. 계산 포함 여부와 화면 숨김은 서로 다릅니다. 피팅용과 검증용 자료는 수치 연구에서 지정하세요. 표 선택은 결과를 바꾸지 않습니다.')
        self.detail.setTextFormat(Qt.TextFormat.PlainText)
        if rows:self.table.setCurrentCell(min(self._selected_row,len(rows)-1),0)
        self.table.blockSignals(False)
        self._selected(self.table.currentRow())

    def _selected(self,row,*_):
        if row<0:return
        self._selected_row=row
        channel=self.result.get('channels',{}).get(self.channels.currentData(),{})
        if row>=len(channel.get('samples',[])):return
        sample=channel['samples'][row];node=channel['lineage']['nodes'][sample['sample_id']]
        audit=node.get('nonlinear_relation',{}).get('audit',{})
        spec=channel.get('metadata',{}).get('extensions',{}).get('finite_measure',{}).get('payload',{})
        measurement={'extensometer_gauge_extension':'접촉식 표점 변위','optical_gauge_extension':'광학 표점 변위',
            'crosshead_assumed_gauge':'크로스헤드 변위를 표점 변위로 명시 가정'}.get(spec.get('measurement'),spec.get('measurement','미기록'))
        basis={'jacobian':'표점 λ와 관측 J','current_area':'현재 단면적 A(t)','full_F':'전체 F의 det(F)',
            'isochoric_assumption':'명시 J=1 가정','none':'추가 응력 변환 없음'}.get(spec.get('basis'),spec.get('basis','미기록'))
        operands=node.get('nonlinear_relation',{}).get('operands',{})
        if spec.get('basis')=='none' and operands.get('load',{}).get('metadata',{}).get('measure')=='axial_force':
            basis='응력 측도 변환 없음; 축방향 힘/A0로 계산'
        j_label=('명시 가정 J' if audit.get('J_origin')=='EXPLICIT_ASSUMPTION_NOT_MEASURED' or spec.get('basis')=='isochoric_assumption'
            else '입력 J — F의 det와 일치 확인' if spec.get('basis')=='full_F' and 'J' in operands
            else '관측 F에서 계산한 det(F)' if spec.get('basis')=='full_F'
            else '입력 관측 J' if spec.get('basis')=='jacobian' else '변환 J')
        fields=[('A0_mm2','A0','mm²'),('L0_mm','L0','mm'),('current_area_mm2','현재 A','mm²'),
                ('stretch','λ','1'),('J',j_label,'1')]
        operands=' / '.join(f'{label}={value_text(audit[key])} {unit}' for key,label,unit in fields if key in audit)
        value_rows=', '.join(map(str,sample.get('source_rows',[]))) or '없음'
        decision_rows=', '.join(map(str,sample.get('validity_source_rows',sample.get('source_rows',[])))) or '없음'
        lines=[f'값 기여 원행: {value_rows} / 판정 원행: {decision_rows}',measurement+' / 변환 근거: '+str(basis),operands]
        for key,item in spec.get('geometry',{}).items():
            if item.get('evidence'):lines.append(str(key)+' 근거: '+str(item['evidence']))
        for item in spec.get('assumptions',{}).values():
            if item.get('enabled'):lines.append('명시 가정 근거: '+str(item.get('reason','미기록')))
        self.detail.setText('\n'.join(line for line in lines if line))


class FinitePredictionDialog(QDialog):
    """Read-only conversion of retained accepted states, including failed prefix."""
    def __init__(self,evaluation,parent=None):
        super().__init__(parent);self.setWindowTitle('계산 결과의 응력 비교');self.resize(1050,720)
        configure_plot_fonts()
        self.evaluation=deepcopy(evaluation)
        root=QVBoxLayout(self);self.axis=combo([(a+'축',a) for a in 'xyz']);root.addWidget(self.axis)
        self.table=readonly_table(['시간','원 P','실제 축 신장비','실제 J','파생 σ','원 증분'])
        root.addWidget(self.table,2);self.figure=Figure(constrained_layout=True);self.canvas=FigureCanvasQTAgg(self.figure);root.addWidget(self.canvas,2)
        self.message=QLabel();self.message.setWordWrap(True);self.message.setTextFormat(Qt.TextFormat.PlainText);root.addWidget(self.message)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.button(QDialogButtonBox.StandardButton.Close).setText('닫기');buttons.rejected.connect(self.reject);root.addWidget(buttons)
        self.axis.currentIndexChanged.connect(self._show);self._show()

    def _show(self,*_):
        from caelab.finite_measure_prediction import comparison_extension,derive
        failure=self.evaluation.get('diagnostics',{}).get('failed_increment') or {}
        failure_text=('원래 실패: '+str(failure.get('message') or failure.get('error') or '실패 이유 미기록')+' / 증분 '+str(failure.get('increment','미기록'))+'\n') if failure else ''
        try:
            a=self.axis.currentData();name='stress_'+a*2
            derived=derive(self.evaluation,name,comparison_extension(a)['payload'],allow_failed_prefix=True)
            raw=self.evaluation['responses'][name];p=derived['extensions']['finite_measure']['payload'];states=p['actual_accepted_states']
            times=derived['axes'][0]['values'];idx='xyz'.index(a)
            self.table.setHorizontalHeaderLabels(['시간 ['+derived['axes'][0]['unit']+']','공칭 응력 P ['+raw['unit']+']','축 신장비 [1]','부피비 J [1]','진응력 σ ['+derived['unit']+']','원 증분'])
            fill_table(self.table,[[t,P,state['F'][idx][idx],state['J'],s,state['increment']]
                for t,P,s,state in zip(times,raw['value'],derived['value'],states)])
            self.figure.clear();ax=self.figure.add_subplot(111)
            ax.plot(times,raw['value'],'o-',label='공칭 응력');ax.plot(times,derived['value'],'x-',label='진응력')
            ax.set_xlabel('시간 ['+derived['axes'][0]['unit']+']');ax.set_ylabel('응력 ['+derived['unit']+']');ax.legend();self.canvas.draw()
            state=self.evaluation['execution_status']
            self.message.setText(failure_text+{'SUCCEEDED':'계산 완료','FAILED':'계산 실패','PARTIAL_FAILURE':'일부 계산 실패','CANCELLED':'계산 취소','INTERRUPTED':'계산 중단','UNKNOWN':'계산 상태 미확인'}.get(state,state)+'. 원 공칭 응력은 보존됩니다. 실패 전 수락된 결과는 진단용이며 피팅의 성공 점수에 사용하지 않습니다.')
            self.message.setToolTip('원 실행 상태: '+state)
        except (ValueError,TypeError,KeyError) as error:
            self.table.setRowCount(0);self.figure.clear();self.canvas.draw();self.message.setText(failure_text+'응력 비교에 필요한 기록을 확인하세요. '+str(error))
