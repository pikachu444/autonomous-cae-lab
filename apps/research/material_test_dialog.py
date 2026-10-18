"""Compact editors for existing Data mappings and Material-bound experiments."""
from copy import deepcopy
import math
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QComboBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QCheckBox, QScrollArea)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from shiboken6 import isValid
from caelab.material_test import column_mapping, measured_protocol


def combo(items):
    widget = QComboBox()
    for label, value in items:
        widget.addItem(label, value)
    return widget


def numeric(text):
    try:
        value = float(text)
        return value if math.isfinite(value) else text
    except ValueError:
        return text


class TestColumnsDialog(QDialog):
    """Only explicit column choices compile existing affine Data mappings."""
    __test__ = False
    def __init__(self, preview, parent=None):
        super().__init__(parent)
        self.setWindowTitle('시험 열 설정')
        self.resize(960, 670)
        self.result_mapping = None
        self.preview = preview
        root = QVBoxLayout(self)
        split = QSplitter()
        root.addWidget(split, 1)
        inputs = QWidget()
        form = QFormLayout(inputs)
        split.addWidget(inputs)
        columns = [('선택…', None)] + [(str(name), index) for index, name in enumerate(preview.get('headers', []))]
        self.time_column, self.response_column, self.drive_column = [combo(columns) for _ in range(3)]
        self.time_unit = combo([(v, v) for v in ('s', 'ms', 'min')])
        self.response_kind = combo([('응력', 'stress'), ('힘 / 초기 단면적', 'force')])
        self.response_unit = combo([(v, v) for v in ('MPa', 'Pa', 'kPa', 'GPa', 'N', 'kN')])
        self.stress_unit = combo([(v, v) for v in ('MPa', 'Pa', 'kPa', 'GPa')])
        self.measure = combo([('선택…', None), ('미소변형 Cauchy', 'infinitesimal_Cauchy'), ('공칭 응력 P', 'first_Piola')])
        self.component = combo([(v, v) for v in ('xx', 'yy', 'zz', 'xy', 'xz', 'yz')])
        self.drive_kind = combo([('공학 변형률', 'engineering_strain'), ('신장비', 'stretch'),
                                 ('변위 / 초기 표점 거리', 'displacement'), ('단순 전단량 γ12', 'simple_shear')])
        self.drive_unit = combo([(v, v) for v in ('1', '%', 'mm', 'm', 'um')])
        self.area, self.gauge = QLineEdit(), QLineEdit()
        self.area_unit, self.gauge_unit = combo([(v+'²', v) for v in ('mm','m','um')]), combo([(v,v) for v in ('mm','m','um')])
        for label, widget in [('시간 열',self.time_column), ('시간 단위',self.time_unit), ('관측 열',self.response_column),
            ('관측 물리량',self.response_kind), ('원본 단위',self.response_unit), ('사용할 응력 단위',self.stress_unit),
            ('응력 정의',self.measure), ('응력 성분',self.component), ('초기 단면적',self.area), ('면적 단위',self.area_unit),
            ('변형 이력 열',self.drive_column), ('변형 물리량',self.drive_kind), ('변형 원본 단위',self.drive_unit),
            ('초기 표점 거리',self.gauge), ('길이 단위',self.gauge_unit)]:
            form.addRow(label,widget)
        table = QTableWidget(len(preview.get('rows', [])), len(preview.get('headers', [])))
        table.setHorizontalHeaderLabels(preview.get('headers', []))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, values in enumerate(preview.get('rows', [])):
            for column, value in enumerate(values):
                table.setItem(row,column,QTableWidgetItem(str(value)))
        split.addWidget(table)
        split.setSizes([350,580])
        self.message = QLabel('열과 물리량을 직접 선택하세요. 원본 열은 그대로 보존됩니다.')
        self.message.setWordWrap(True)
        root.addWidget(self.message)
        self.response_kind.currentIndexChanged.connect(self._visibility)
        self.drive_kind.currentIndexChanged.connect(self._visibility)
        self._visibility()
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept); buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _visibility(self):
        def units(widget,values):
            previous=widget.currentData()
            widget.clear()
            for value in values: widget.addItem(value,value)
            index=widget.findData(previous)
            widget.setCurrentIndex(max(0,index))
        units(self.response_unit,('N','kN') if self.response_kind.currentData()=='force' else ('MPa','Pa','kPa','GPa'))
        units(self.drive_unit,('mm','m','um') if self.drive_kind.currentData()=='displacement' else ('1',) if self.drive_kind.currentData()=='stretch' else ('1','%'))
        self.area.setEnabled(self.response_kind.currentData()=='force')
        self.area_unit.setEnabled(self.area.isEnabled())
        self.gauge.setEnabled(self.drive_kind.currentData()=='displacement')
        self.gauge_unit.setEnabled(self.gauge.isEnabled())

    def _accept(self):
        try:
            if any(widget.currentData() is None for widget in (self.time_column,self.response_column,self.drive_column)):
                raise ValueError('시간·관측·변형 이력 열을 모두 선택하세요.')
            columns=column_mapping(time_column=self.time_column.currentData(),time_unit=self.time_unit.currentData(),
                response_column=self.response_column.currentData(),response_kind=self.response_kind.currentData(),
                response_unit=self.response_unit.currentData(),stress_unit=self.stress_unit.currentData(),
                measure=self.measure.currentData(),component=self.component.currentData(),
                drive_column=self.drive_column.currentData(),drive_kind=self.drive_kind.currentData(),drive_unit=self.drive_unit.currentData(),
                area=numeric(self.area.text()),area_unit=self.area_unit.currentData(),
                gauge=numeric(self.gauge.text()),gauge_unit=self.gauge_unit.currentData())
            self.result_mapping={'delimiter':self.preview.get('delimiter',','),
                'skip_header':self.preview.get('skip_rows',1),'columns':columns}
        except (ValueError,KeyError,TypeError) as error:
            self.message.setText(str(error)); return
        self.accept()


class ExperimentDialog(QDialog):
    """One retained import, observation, role and measured protocol in one review."""
    def __init__(self, settings, result, parent=None, *, experiment=None, selected=None,
                 selected_result_reader=None):
        super().__init__(parent)
        from .appearance import configure_plot_fonts
        configure_plot_fonts()
        self.setWindowTitle('시험 조건')
        self.resize(1050, 700)
        self.settings, self.imported = deepcopy(settings), deepcopy(result)
        self.recipe = deepcopy((experiment or {}).get('kinematics'))
        self.value = None
        self._selected_result_reader = selected_result_reader
        self._selection_worker = None
        self.explicit = deepcopy(settings)
        root=QVBoxLayout(self)
        split=QSplitter(); root.addWidget(split,1)
        left=QWidget(); self._inputs=left; form=QFormLayout(left)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(left);scroll.setMinimumWidth(290);split.addWidget(scroll)
        self.measure_context=QLabel();self.measure_context.setWordWrap(True)
        self.measure_context.setTextFormat(Qt.TextFormat.PlainText);form.addRow(self.measure_context)
        responses=result.get('responses',{})
        self.observed=combo([(name,name) for name,row in responses.items()
            if row.get('measure') in ('infinitesimal_Cauchy','first_Piola','finite_Cauchy')])
        self.role=combo([('피팅','fit'),('별도 확인 (holdout)','holdout')])
        self.model_response=combo([('응력 '+name.removeprefix('stress_'),name)
            for name in ('stress_xx','stress_yy','stress_zz','stress_xy','stress_xz','stress_yz')])
        self.protocol=combo([('전체 변형구배 편집','explicit'),('측정 변형 이력 사용','measured'),('유한변형 측정 이력 / 횡방향 제어','finite_measured')])
        self.driver=combo([('선택…',None)]+[(name,name) for name,row in responses.items()
            if row.get('measure') in ('engineering_strain','stretch','simple_shear','log_strain')])
        self.lateral_22, self.lateral_33=QLineEdit(),QLineEdit()
        self.weight, self.scale=QLineEdit('1'),QLineEdit('1')
        self.finite_lateral=combo([('명시 선택…',None),('횡응력 0 (자유 횡수축)','free'),('횡변형 고정 F=1','fixed'),('횡변형 지정','prescribed')])
        self.finite_comparison=QCheckBox('후보의 실제 수락 F/J로 P → 진응력 변환')
        self.finite_comparison.setChecked(bool((experiment or {}).get('extensions',{}).get('finite_measure')))
        self.tensor=QPushButton('혼합 제어 조건…' if 'initial_state' in settings else '변형구배 편집…'); self.tensor.clicked.connect(self._tensor)
        for label,widget in [('관측',self.observed),('용도',self.role),('모델 응답',self.model_response),
            ('변형 조건',self.protocol),('변형 채널',self.driver),('지정 F22',self.lateral_22),
            ('지정 F33',self.lateral_33),('시험 가중치',self.weight),('오차 기준값',self.scale)]:
            form.addRow(label,widget)
        form.addRow('유한변형 횡방향 조건',self.finite_lateral)
        form.addRow(self.finite_comparison)
        form.addRow(self.tensor)
        self.condition=QLabel('F22/F33는 지정값입니다. 자유 횡수축을 계산하지 않습니다.')
        self.condition.setWordWrap(True); form.addRow(self.condition)
        self.figure=Figure(constrained_layout=True)
        self.canvas=FigureCanvasQTAgg(self.figure); split.addWidget(self.canvas)
        split.setSizes([310,710])
        self.message=QLabel(); self.message.setWordWrap(True); root.addWidget(self.message)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self._buttons=buttons
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        buttons.accepted.connect(self._accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        if selected_result_reader is not None:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText('선택 채널 확인')
            if result.get('diagnostics',{}).get('processing_status')=='PARTIAL':
                self.message.setText('일부 처리 실패')
        if experiment:
            selected=experiment['source']['response']
            self.role.setCurrentIndex(self.role.findData(experiment['role']))
            self.model_response.setCurrentIndex(self.model_response.findData(experiment['response']))
            self.weight.setText(str(experiment['weight'])); self.scale.setText(str(experiment['scale']))
        if selected and self.observed.findData(selected)>=0:
            self.observed.setCurrentIndex(self.observed.findData(selected))
        if self.recipe:
            self.protocol.setCurrentIndex(2 if self.recipe.get('kind')=='finite_measured' else 1)
            if self.recipe.get('kind')=='finite_measured':
                self.finite_lateral.setCurrentIndex(self.finite_lateral.findData(self.recipe.get('lateral')))
            self.driver.setCurrentIndex(self.driver.findData(self.recipe['channel']))
            self.lateral_22.setText(str(self.recipe.get('lateral_22','')))
            self.lateral_33.setText(str(self.recipe.get('lateral_33','')))
        for widget in (self.observed,self.protocol,self.driver,self.finite_lateral):
            widget.currentIndexChanged.connect(self._preview)
        self.finite_comparison.toggled.connect(self._update_context)
        self.model_response.currentIndexChanged.connect(self._update_context)
        for field in (self.observed,self.protocol,self.driver,self.finite_lateral):
            field.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            field.setMinimumContentsLength(10);field.setToolTip(field.currentText());field.currentTextChanged.connect(field.setToolTip)
        self._preview()

    def _update_context(self,*_):
        from caelab.material_law_validation import measure
        from caelab.data_processing_lineage import aligned_driver_indexes
        from caelab.finite_measure_prediction import comparison_extension,observation_measure
        labels={'first_Piola':'공칭 응력 P','finite_Cauchy':'유한변형 진응력 σ','infinitesimal_Cauchy':'미소변형 Cauchy',
                'stretch':'신장비 λ','engineering_strain':'공학 변형률 e','log_strain':'로그 변형률 ln λ'}
        native=measure(self.settings) if self.settings.get('model') else '미지정'
        model={'neo_hooke':'Neo-Hooke','linear_elastic':'선형 탄성'}.get(self.settings.get('model'),self.settings.get('model','미지정'))
        obs=self.imported.get('responses',{}).get(self.observed.currentData(),{})
        frame={'material_cartesian':'재료 직교좌표'}.get(obs.get('frame'),obs.get('frame','미지정'))
        lines=[f"재료 법칙: {model} / 원 응력: {labels.get(native,native)} [{self.settings.get('stress_unit','미지정')}]",
            f"관측: {labels.get(obs.get('measure'),obs.get('measure','미지정'))} / {obs.get('component','미지정')} [{obs.get('unit','미지정')}] / {frame}"]
        if self.protocol.currentData() == 'explicit':
            targets = self.explicit.get('boundary_control', {}).get('stress_components', {})
            lines.append('응력 목표: ' + ', '.join(targets) + ' / 나머지 F 지정' if targets else '제어: 모든 F 성분 지정')
        experiment={'response':self.model_response.currentData()}
        if self.finite_comparison.isChecked():
            component=obs.get('component','')
            if component in ('xx','yy','zz'):experiment['extensions']={'finite_measure':comparison_extension(component[0])}
            lines.append('비교 변환: 각 후보의 실제 수락 F/J 사용')
        try:
            expected=observation_measure(obs,experiment,native)
            lines.append('비교 예측: '+labels.get(expected,expected)+(' / 관측 정의 일치' if obs.get('measure')==expected else ' / 관측 정의를 확인하세요.'))
        except (ValueError,KeyError,TypeError) as error:lines.append(str(error))
        if self.protocol.currentData() in ('measured','finite_measured'):
            driver=self.imported.get('responses',{}).get(self.driver.currentData(),{})
            lines.append('변형: '+labels.get(driver.get('measure'),driver.get('measure','미지정'))+' ['+str(driver.get('unit','미지정'))+']')
            try:
                indexes=aligned_driver_indexes(obs,driver)
                lines.append(f'원행·시각 대응: {len(indexes)}표본 / 취득 순서 유지')
            except (ValueError,KeyError,TypeError) as error:lines.append('원행·시각 대응 확인: '+str(error))
        self.measure_context.setText('\n'.join(lines))

    def _tensor(self):
        native = 'initial_state' in self.explicit
        if native:
            from .material_control_gui import MixedControlDialog
            dialog=MixedControlDialog(None,self.explicit,self)
        else:
            from .numerical_window import ProtocolDialog
            dialog=ProtocolDialog(self.explicit,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.explicit=dialog.result_settings if native else dialog.draft_settings()
            self.protocol.setCurrentIndex(0)
            self._preview()

    def _preview(self):
        measured=self.protocol.currentData() in ('measured','finite_measured')
        finite=self.protocol.currentData()=='finite_measured'
        self.finite_lateral.setEnabled(finite)
        targets = self.explicit.get('boundary_control', {}).get('stress_components', {})
        self.condition.setText('기존 수락 상태·native tangent·수렴 관문으로 횡방향 조건을 풉니다.' if finite else
                              '응력 목표 성분은 직전 수락 상태에서 풉니다. 나머지 F만 지정합니다.' if not measured and targets else
                              'F22/F33는 지정값입니다. 자유 횡수축을 계산하지 않습니다.')
        for widget in (self.driver,self.lateral_22,self.lateral_33):
            widget.setEnabled(measured)
        for widget in (self.lateral_22,self.lateral_33):
            widget.setEnabled(measured and (not finite or self.finite_lateral.currentData()=='prescribed'))
        self.tensor.setEnabled(not measured)
        self.figure.clear()
        axes=self.figure.subplots(2,1)
        for index,(ax,name) in enumerate(zip(axes,(self.observed.currentData(), self.driver.currentData()))):
            response=self.imported.get('responses',{}).get(name,{})
            if index == 1 and not measured:
                times=self.explicit.get('time',[])
                gradients=self.explicit.get('deformation_gradient',[])
                try:
                    values=[matrix[0][0] for matrix in gradients]
                except (IndexError,TypeError,KeyError):
                    values=[]
                unit='1'; name='지정 F11'
                if 'xx' in targets:
                    values=targets['xx']
                    unit=self.explicit.get('stress_unit','')
                    name={'neo_hooke':'Pxx', 'linear_elastic':'σxx', 'drucker_prager_linear':'σxx',
                          'single_branch_maxwell':'σxx'}.get(self.explicit.get('model'),'xx 응력')+' 목표'
                response={'axes':[{'name':'시간','unit':self.explicit.get('time_unit',''),'values':times}],
                          'value':values,'unit':unit}
            declared_axes=response.get('axes',[])
            axis=declared_axes[0] if isinstance(declared_axes,list) and len(declared_axes)==1 else {}
            x,y=axis.get('values',[]),response.get('value',[])
            if (isinstance(x,list) and isinstance(y,list) and len(x)==len(y) and len(x) and
                    all(type(value) in (int,float) and math.isfinite(value) for value in x+y)):
                ranges = ([segment['rows'] for segment in response['segments']]
                          if 'segments' in response else [[0, len(y)]])
                for first, last in ranges:
                    ax.plot(x[first:last], y[first:last], 'o-', color='C0', markersize=3)
            else:
                ax.text(.5,.5,'변형 이력 확인 필요' if index==1 and not measured else '선택한 채널의 곡선 없음',
                        ha='center',va='center',transform=ax.transAxes)
                ax.set_axis_off()
            ax.set_ylabel(str(name or '변형 채널 선택')+' ['+str(response.get('unit',''))+']')
            ax.set_xlabel(str(axis.get('name',''))+' ['+str(axis.get('unit',''))+']')
        # A cancelled modal preview can be destroyed before an idle Qt draw.
        self.canvas.draw()
        response=self.imported.get('responses',{}).get(self.observed.currentData(),{})
        if response and not self.value:
            index=self.model_response.findData('stress_'+str(response.get('component')))
            if index>=0: self.model_response.setCurrentIndex(index)
        self._update_context()

    def _accept(self):
        if self._selection_worker is not None:
            return
        try:
            name=self.observed.currentData()
            if not name: raise ValueError('응력 관측 채널을 선택하세요.')
            settings=deepcopy(self.explicit); recipe=None
            if self.protocol.currentData()=='measured':
                channel=self.driver.currentData()
                measure=self.imported.get('responses',{}).get(channel,{}).get('measure')
                recipe=dict(channel=channel,kind=measure,
                    lateral_22=numeric(self.lateral_22.text()),lateral_33=numeric(self.lateral_33.text()))
            if self.protocol.currentData()=='finite_measured':
                from caelab.finite_measure_protocol import recipe as finite_recipe
                observed=self.imported.get('responses',{}).get(name,{})
                component=observed.get('component','')
                if component not in ('xx','yy','zz'):raise ValueError('단축·동축 응력 성분을 선택하세요.')
                recipe=finite_recipe(self.driver.currentData(),component[0],lateral=self.finite_lateral.currentData(),
                    lateral_22=numeric(self.lateral_22.text()),lateral_33=numeric(self.lateral_33.text()))
            # Draft protocol/weight may be incomplete; save remains possible.
            pending=dict(name=name,role=self.role.currentData(),response=self.model_response.currentData(),
                settings=settings,weight=numeric(self.weight.text()),scale=numeric(self.scale.text()),kinematics=recipe)
            if self.finite_comparison.isChecked():
                from caelab.finite_measure_prediction import comparison_extension
                observed=self.imported.get('responses',{}).get(name,{})
                component=observed.get('component','')
                if observed.get('measure')!='finite_Cauchy' or component not in ('xx','yy','zz'):
                    raise ValueError('명시 P→Cauchy 비교에는 같은 축의 유한변형 진응력 관측을 선택하세요.')
                pending['extensions']={'finite_measure':comparison_extension(component[0])}
            if self._selected_result_reader is not None:
                names=list(dict.fromkeys([name]+([recipe['channel']] if recipe else [])))
                if any(not isinstance(item,str) or not item for item in names):
                    raise ValueError('변형 이력 채널을 선택하세요.')
                from .data_window import _Read
                reader=self._selected_result_reader
                worker=_Read(lambda: reader(list(names)))
                self._selection_worker=worker
                self._set_reading(True)
                def finished(result,error):
                    if not isValid(self) or self._selection_worker is not worker:
                        return
                    self._selection_worker=None
                    self._set_reading(False)
                    if error:
                        self.message.setText('선택한 범위를 읽지 못했습니다. 응답과 변형 채널을 확인하세요.')
                        self.message.setToolTip(str(error)); return
                    try:
                        if (not isinstance(result,dict) or result.get('execution_status')!='SUCCEEDED'
                                or set(result.get('responses',{}))!=set(names)):
                            raise ValueError('선택한 채널의 사용 가능한 처리 결과를 확인하지 못했습니다.')
                        self._finish_accept(pending,result)
                    except (ValueError,KeyError,TypeError) as error:
                        self.message.setText(str(error))
                worker.signals.finished.connect(finished,Qt.ConnectionType.QueuedConnection)
                QThreadPool.globalInstance().start(worker)
                return
            self._finish_accept(pending,self.imported)
        except (ValueError,KeyError,TypeError) as error:
            self.message.setText(str(error)); return

    def _set_reading(self, reading):
        self._inputs.setEnabled(not reading)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not reading)
        if reading:
            self.message.setText('선택한 관측과 변형 이력을 읽는 중…')

    def _finish_accept(self, pending, result):
        value=deepcopy(pending)
        if value['kinematics'] is not None:
            try:
                value['settings']=measured_protocol(value['settings'],result,value['kinematics'])
            except (ValueError,TypeError,KeyError,OverflowError):
                if value['kinematics'].get('kind')!='finite_measured':raise
                # Keep invalid raw controls for owner diagnostics/save; execution
                # still validates the exact recipe and compiled settings.

        self.value=value
        self.accept()

    def reject(self):
        worker,self._selection_worker=self._selection_worker,None
        if worker is not None:
            worker.abandon()
            self._set_reading(False)
        super().reject()
