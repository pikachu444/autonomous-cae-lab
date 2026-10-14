"""Calibration and reusable file-acquisition settings for the existing Data draft."""
from copy import deepcopy
import json
from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt, Slot
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from caelab.experiment_calibration import (default_calibration, validate_calibration, calibrate,
    default_acquisition, validate_acquisition, UNITS)
from .data_window import _Read, number_or_raw
from .appearance import configure_plot_fonts
from .report_pages import atomic_export, value_text
from .experiment_labels import sample_reason


class CalibrationDialog(QDialog):
    def __init__(self, client, mapping, preview, parent=None, *, retained_response=None):
        super().__init__(parent)
        self.client=client;self.mapping=deepcopy(mapping);self.preview=deepcopy(preview)
        self.retained_response=deepcopy(retained_response)
        self.recipe=deepcopy(mapping.get('calibration') or default_calibration(mapping.get('unit','N')))
        self._workers=[];self._closed=False;self.fields={}
        self.setWindowTitle('채널 교정');self.resize(1100,780)
        configure_plot_fonts()
        root=QVBoxLayout(self);split=QSplitter();root.addWidget(split,1)
        tabs=QTabWidget();split.addWidget(tabs)
        forms={}
        for label in ('교정식','범위','측정 조건','불확실성'):
            page=QWidget();form=QFormLayout(page);tabs.addTab(page,label);forms[label]=form
        def field(key,label,tab,value):
            edit=QLineEdit('' if value is None else str(value));self.fields[key]=edit
            forms[tab].addRow(label,edit);return edit
        for key,label in [('input_unit','원값 단위'),('coefficient_input_unit','계수의 입력 단위'),
                          ('output_unit','출력 단위'),('a','기울기 a'),('x0','입력 영점 x₀'),
                          ('x0_unit','영점 단위'),('b','출력 오프셋 b')]:
            field(key,label,'교정식',self.recipe[key])
        forms['교정식'].addRow(QLabel('y = a × (x − x₀) + b'))
        self.source=QLabel((self.recipe.get('source') or {}).get('name','교정 원본을 선택하세요.'))
        self.source.setWordWrap(True);forms['교정식'].addRow(self.source)
        self.upload=QPushButton('교정 원본 열기…');self.upload.clicked.connect(self.choose_certificate)
        forms['교정식'].addRow(self.upload)
        for key,label in [('input_range','교정 유효 입력'),('sensor_range','센서 한계')]:
            interval=self.recipe.get(key) or {}
            for sub,sub_label in [('minimum','하한'),('maximum','상한'),('unit','단위')]:
                field(key+'/'+sub,label+' '+sub_label,'범위',interval.get(sub,''))
        for key,label in [('sensor','센서'),('gauge','게이지 위치/방향'),
                          ('observed_at','관측 시각'),('valid_from','유효기간 시작'),('valid_until','유효기간 끝')]:
            field(key,label,'측정 조건',self.recipe[key])
        self.role=QComboBox()
        for label,value in [('미선언','UNDECLARED'),('액추에이터 변위','actuator'),
                            ('시편 표점 변위','specimen_gauge'),('변위가 아님','not_displacement')]:
            self.role.addItem(label,value)
        self.role.setCurrentIndex(max(0,self.role.findData(self.recipe['displacement_role'])))
        forms['측정 조건'].addRow('측정 변위',self.role)
        u=self.recipe.get('uncertainty') or {}
        self.provided=QCheckBox('제공된 불확실성 기록');self.provided.setChecked(bool(u))
        forms['불확실성'].addRow(self.provided)
        self.ukind=QComboBox();self.ukind.addItem('미확인',u.get('kind') if u.get('kind') in (None,'UNKNOWN') else None)
        self.ukind.addItem('표준 불확실성','standard');self.ukind.addItem('확장 불확실성','expanded')
        self.ukind.setCurrentIndex(max(0,self.ukind.findData(u.get('kind'))));forms['불확실성'].addRow('종류',self.ukind)
        for key,label in [('value','값'),('unit','단위'),('k','포함인자 k'),('note','출처 / 상관 설명')]:
            field('uncertainty/'+key,label,'불확실성',u.get(key,''))
        self.correlation=QComboBox()
        for label,value in [('미확인','UNKNOWN'),('독립이라고 제공됨','independent_declared'),('상관이 있다고 제공됨','correlated_declared')]:
            self.correlation.addItem(label,value)
        self.correlation.setCurrentIndex(max(0,self.correlation.findData(u.get('correlation','UNKNOWN'))))
        forms['불확실성'].addRow('상관',self.correlation)
        right=QWidget();view=QVBoxLayout(right);split.addWidget(right)
        self.values=QTableWidget(0,4);self.values.setHorizontalHeaderLabels(['원행','원값','교정값','확인 사항'])
        self.values.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.values.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.values.setMaximumHeight(230);view.addWidget(self.values)
        self.figure=Figure();self.canvas=FigureCanvasQTAgg(self.figure);self.canvas.setMinimumHeight(300)
        view.insertWidget(0,self.canvas,1)
        preview_button=QPushButton('교정 전후 보기');preview_button.clicked.connect(self.refresh_preview);view.addWidget(preview_button)
        split.insertWidget(0,right)
        split.setStretchFactor(0,1);split.setStretchFactor(1,0);split.setSizes([740,325])
        self.message=QLabel('같은 원본 행을 두 단위로 비교합니다.');self.message.setWordWrap(True);root.addWidget(self.message)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('초안에 적용')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
        self.refresh_preview()
        for field in self.fields.values():field.textEdited.connect(self.mark_unapplied)
        for combo in (self.role,self.ukind,self.correlation):combo.currentIndexChanged.connect(self.mark_unapplied)
        self.provided.toggled.connect(self.mark_unapplied)

    def mark_unapplied(self,*_):
        self.message.setText('미적용 입력 — 교정 전후 보기로 확인하세요. 이전 곡선은 유지됩니다.')

    def edited(self):
        recipe=deepcopy(self.recipe)
        for key in ('input_unit','coefficient_input_unit','output_unit','x0_unit','sensor','gauge','observed_at','valid_from','valid_until'):
            recipe[key]=self.fields[key].text()
        for key in ('a','x0','b'):recipe[key]=number_or_raw(self.fields[key].text())
        recipe['displacement_role']=self.role.currentData()
        for key in ('input_range','sensor_range'):
            values={sub:self.fields[key+'/'+sub].text() for sub in ('minimum','maximum','unit')}
            recipe[key]=({**values,'minimum':number_or_raw(values['minimum']),
                          'maximum':number_or_raw(values['maximum'])} if any(values.values()) else None)
        if self.provided.isChecked():
            k=self.fields['uncertainty/k'].text()
            recipe['uncertainty']={'value':number_or_raw(self.fields['uncertainty/value'].text()),
                'unit':self.fields['uncertainty/unit'].text(),'kind':self.ukind.currentData(),
                'k':number_or_raw(k) if k.strip() else None,'correlation':self.correlation.currentData(),
                'note':self.fields['uncertainty/note'].text()}
        else:recipe['uncertainty']=None
        return recipe

    def choose_certificate(self):
        if self._workers:return
        path,_=QFileDialog.getOpenFileName(self,'교정 원본','',
            '교정 자료 (*.pdf *.txt *.md *.csv)')
        if not path:return
        self.upload.setEnabled(False)
        worker=_Read(lambda:self.client.upload(Path(path).name,Path(path).read_bytes()))
        self._workers.append(worker);worker.signals.finished.connect(self._uploaded,Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    @Slot(object,object)
    def _uploaded(self,receipt,error):
        self._workers=[];self.upload.setEnabled(True)
        if self._closed:return
        if error:self.message.setText(str(error));return
        self.recipe['source']={'data_id':receipt['id'],'sha256':receipt['sha256'],'name':receipt['name']}
        self.source.setText(receipt['name']);self.refresh_preview()

    def refresh_preview(self):
        recipe=self.edited()
        axes = None
        try:
            if self.retained_response is not None:
                recipe=self.retained_response['calibration']
                audit=self.retained_response['raw_samples']
                raw=audit['value'];rows=audit['source_rows']
                transformed=audit['transformed_value']
            else:
                validate_calibration(recipe)
                table=(self.preview or {}).get('table_preview',{})
                column=self.mapping['column']
                index=table.get('headers',[]).index(column) if isinstance(column,str) else column
                raw=[float(row[index]) for row in table.get('rows',[])]
                rows=table.get('row_numbers',[])
                if not raw:raise ValueError('현재 원본의 숫자 미리보기가 없습니다. CSV 원본과 열을 확인하세요.')
                transformed,audit=calibrate(raw,recipe)
            self.figure.clear(); axes=self.figure.subplots(2,1,sharex=True)
            self.values.setRowCount(0)
            self.values.setHorizontalHeaderLabels(['원행','원값 ['+recipe['input_unit']+']',
                '교정값 ['+recipe['output_unit']+']','확인 사항'])
            self.values.setRowCount(len(raw))
            for i,(source,x,y,reason) in enumerate(zip(rows,raw,transformed,audit['calibration_reasons'])):
                for j,v in enumerate((source,x,float(y),sample_reason(reason))):
                    self.values.setItem(i,j,QTableWidgetItem(value_text(v)))
            axes[0].plot(rows,[float(v) for v in raw],'o-');axes[0].set_ylabel('원값 ['+recipe['input_unit']+']')
            valid=audit['calibration_valid']
            axes[1].plot(rows,[float(v) if ok else float('nan') for v,ok in zip(transformed,valid)],
                         'o-',label='교정값 (범위 내)')
            for flag,marker,label in [('calibration_out_of_range','o','범위 밖'),('sensor_saturated','x','센서 포화')]:
                chosen=[i for i,marked in enumerate(audit[flag]) if marked]
                if chosen:
                    axes[1].scatter([rows[i] for i in chosen],[transformed[i] for i in chosen],
                        marker=marker,facecolors='none' if marker=='o' else 'red',edgecolors='red',label=label)
            axes[1].legend()
            axes[1].set_ylabel('교정값 ['+recipe['output_unit']+']')
            axes[1].set_xlabel('원본 행')
            self.message.setText('선택한 가져오기에 보존된 원값·교정값입니다. 다시 계산하지 않았습니다.' if self.retained_response is not None else
                '원본 앞부분 '+str(len(raw))+'행 미리보기. 전체 처리는 Data의 가져오기를 누르세요.')
        except (ValueError,KeyError,TypeError,IndexError) as error:
            self.message.setText('미적용 입력: '+str(error)+' 이전 미리보기는 유지됩니다.')
        if axes is not None:
            self.figure.tight_layout();self.canvas.draw_idle()

    def done(self,result):
        if self._workers:
            for worker in self._workers:worker.abandon()
        self._closed=True
        super().done(result)


class AcquisitionDialog(QDialog):
    def __init__(self,setup,channels,parent=None):
        super().__init__(parent);self.setup=deepcopy(setup or default_acquisition());self.channels=deepcopy(channels)
        self.setWindowTitle('파일 수집 설정');self.resize(850,620)
        root=QVBoxLayout(self);form=QFormLayout();root.addLayout(form);self.fields={}
        for key,label in [('name','설정 이름'),('device','장비 기록'),('clock','시각 기준'),
                          ('sample_rate_hz','요청 표본율 [Hz]'),('duration_s','요청 기간 [s]'),('time_offset_s','시간 오프셋 [s]')]:
            edit=QLineEdit(str(self.setup.get(key,'')));self.fields[key]=edit;form.addRow(label,edit)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['채널','역할','단위'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);root.addWidget(self.table,1)
        row=QHBoxLayout()
        for label,fn in [('채널 추가',self.add_channel),('선택 삭제',self.remove),('설정 불러오기…',self.load),('설정 내보내기…',self.export),('입력 확인',self.check)]:
            button=QPushButton(label);button.clicked.connect(fn);row.addWidget(button)
        root.addLayout(row)
        self.message=QLabel('실장비 연결·수집·물리적 중지: 미실행. 파일 자료는 계속 사용할 수 있습니다.')
        self.message.setWordWrap(True);root.addWidget(self.message)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('초안에 적용')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
        self.reuse = QCheckBox('같은 이름의 현재 채널에 이 교정 적용')
        root.insertWidget(root.count()-1,self.reuse)
        self.populate()

    def populate(self):
        self.table.setRowCount(0)
        for channel in self.setup.get('channels',[]):self.add_channel(channel)

    def add_channel(self,channel=None):
        channel=channel if isinstance(channel,dict) else {'name':'','unit':'','role':'measurement','calibration':None}
        i=self.table.rowCount();self.table.insertRow(i)
        item=QTableWidgetItem(channel['name']);item.setData(Qt.ItemDataRole.UserRole,deepcopy(channel.get('calibration')))
        self.table.setItem(i,0,item)
        combo=QComboBox()
        for label,value in [('측정','measurement'),('시간','time'),('액추에이터','actuator'),('시편 표점','specimen_gauge'),('온도','temperature')]:
            combo.addItem(label,value)
        combo.setCurrentIndex(max(0,combo.findData(channel['role'])));self.table.setCellWidget(i,1,combo)
        self.table.setItem(i,2,QTableWidgetItem(channel['unit']))

    def remove(self):
        if self.table.currentRow()>=0:self.table.removeRow(self.table.currentRow())

    def edited(self):
        value={key:field.text() for key,field in self.fields.items()}
        for key in ('sample_rate_hz','duration_s','time_offset_s'):value[key]=number_or_raw(value[key])
        value['channels']=[]
        for i in range(self.table.rowCount()):
            name=self.table.item(i,0).text()
            calibration=deepcopy(self.table.item(i,0).data(Qt.ItemDataRole.UserRole))
            if calibration is None and name in self.channels:calibration=deepcopy(self.channels[name].get('calibration'))
            value['channels'].append({'name':name,'role':self.table.cellWidget(i,1).currentData(),
                'unit':self.table.item(i,2).text(),'calibration':calibration})
        return value

    def accept(self):
        if self.reuse.isChecked():
            try:
                validate_acquisition(self.edited())
            except ValueError as error:
                self.message.setText('현재 채널에 적용하기 전 확인하세요: '+str(error))
                return
        super().accept()

    def check(self):
        try:validate_acquisition(self.edited());self.message.setText('파일 수집 설정이 유효합니다. 실장비 상태는 미확인입니다.')
        except ValueError as error:self.message.setText(str(error))

    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'수집 설정 내보내기','수집설정.json','설정 (*.json)')
        if path:
            try:atomic_export(path,lambda p:p.write_text(json.dumps({'format':'caelab.file_acquisition.v1','setup':self.edited()},
                ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8'))
            except Exception as error:self.message.setText(str(error))

    def load(self):
        path,_=QFileDialog.getOpenFileName(self,'수집 설정 불러오기','','설정 (*.json)')
        if not path:return
        try:
            if Path(path).stat().st_size>96*1024:raise ValueError('설정 파일이 너무 큽니다.')
            value=json.loads(Path(path).read_text(encoding='utf-8-sig'))
            if value.get('format')!='caelab.file_acquisition.v1' or not isinstance(value.get('setup'),dict):
                raise ValueError('지원하는 파일 수집 설정을 선택하세요.')
            setup=value['setup']
            if set(setup)!=set(default_acquisition()) or not isinstance(setup['channels'],list):
                raise ValueError('설정 필드를 확인하세요.')
            # Preserve partial numbers; structural failures leave the current editor untouched.
            if any(not isinstance(c,dict) or set(c)!={'name','role','unit','calibration'} for c in setup['channels']):
                raise ValueError('채널 구조가 잘못되었습니다.')
            self.setup=deepcopy(setup)
            for key,field in self.fields.items():field.setText(str(setup[key]))
            self.populate();self.check()
        except Exception as error:self.message.setText(str(error))
