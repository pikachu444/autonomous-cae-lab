"""Shared physical input editor for the existing Evaluation draft, no execution."""
from copy import deepcopy
import uuid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox,QDialog,QDialogButtonBox,QFormLayout,QHBoxLayout,QLabel,
    QLineEdit,QPushButton,QTreeWidget,QTreeWidgetItem,QVBoxLayout)
from caelab.evaluation_shared_inputs import targets,validate_binding

DATA=Qt.ItemDataRole.UserRole
LABELS={'conductivity':'열전도율','conductivity_temperature_slope':'전도율 온도계수',
        'conductivity_reference_temperature':'전도율 기준온도','heat_source':'체적 열원',
        'boundary_temperature':'경계온도','young_modulus':'탄성계수','poisson_ratio':'포아송비',
        'thermal_expansion':'열팽창계수','reference_temperature':'무응력 기준온도'}


def number_or_draft(text):
    try:return float(text)
    except (TypeError,ValueError):return text


class SharedBindingDialog(QDialog):
    def __init__(self,parent,draft,catalogs,original=None):
        super().__init__(parent)
        self.setWindowTitle('공유 입력');self.resize(850,570)
        self.original=deepcopy(original or {})
        self.stage_ids=[row['id'] for row in draft['stages']]
        self.catalogs=catalogs;self._target_items=[]
        def readable_targets(row):
            if not isinstance(row,dict):return []
            try:items=targets(row)
            except (KeyError,TypeError):return []
            return [t for t in items if isinstance(t,dict) and isinstance(t.get('stage'),str) and isinstance(t.get('input_id'),str)] if isinstance(items,list) else []
        selected=readable_targets(original)
        used={(t['stage'],t['input_id']) for row in draft['bindings'] if isinstance(row,dict) and row.get('id')!=self.original.get('id') for t in readable_targets(row)}
        layout=QVBoxLayout(self);form=QFormLayout()
        self.identifier=self.original.get('id') or ('Shared'+uuid.uuid4().hex[:12])
        self.name=QLineEdit(str(self.original.get('label',self.original.get('id','공유 입력'))));self.name.setObjectName('sharedVariableName')
        self.unit=QComboBox();self.unit.setEditable(True);self.unit.setObjectName('sharedVariableUnit')
        units=sorted({row['unit'] for catalog in catalogs.values() for row in catalog.get('inputs',[])})
        self.unit.addItems(units);self.unit.setCurrentText(str(self.original.get('unit','K')))
        self.value=QLineEdit(str(self.original.get('value','')));self.value.setObjectName('sharedVariableValue')
        bounds=self.original.get('bounds',['',''])
        if not isinstance(bounds,list) or len(bounds)!=2:bounds=[str(bounds),'']
        self.lower=QLineEdit(str(bounds[0]));self.upper=QLineEdit(str(bounds[1]))
        self.lower.setObjectName('sharedVariableLower');self.upper.setObjectName('sharedVariableUpper')
        bound_layout=QHBoxLayout();bound_layout.addWidget(self.lower);bound_layout.addWidget(QLabel('이상'));bound_layout.addWidget(self.upper);bound_layout.addWidget(QLabel('이하'))
        form.addRow('변수 이름',self.name);form.addRow('물리 단위',self.unit);form.addRow('공유 초기값',self.value);form.addRow('선택적 설계 범위',bound_layout)
        layout.addLayout(form)
        note=QLabel('선택한 입력마다 같은 물리값을 적용합니다. 서로 다른 물리적 기준을 묶는 결정은 사용자가 명시해야 하며, 단위 변환은 하지 않습니다.')
        note.setWordWrap(True);layout.addWidget(note)
        self.tree=QTreeWidget();self.tree.setObjectName('sharedInputTargets')
        self.tree.setHeaderLabels(['단계와 입력','단위','원본 값','사용 상태']);self.tree.setAlternatingRowColors(True)
        present=set()
        for stage in draft['stages']:
            group=QTreeWidgetItem(self.tree,[stage['name']])
            for row in catalogs.get(stage['id'],{}).get('inputs',[]):
                target={'stage':stage['id'],'input_id':row['id']};key=(stage['id'],row['id']);present.add(key)
                item=QTreeWidgetItem(group,[LABELS.get(row['id'],row.get('label',row['id'])),row['unit'],str(row.get('value','')),
                    '다른 변수에 연결됨' if key in used else '선택 가능'])
                item.setData(0,DATA,target);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0,Qt.CheckState.Checked if target in selected else Qt.CheckState.Unchecked)
                if key in used and target not in selected:item.setDisabled(True)
                self._target_items.append(item)
        missing=[t for t in selected if (t['stage'],t['input_id']) not in present]
        if missing:
            group=QTreeWidgetItem(self.tree,['복구할 대상'])
            for target in missing:
                item=QTreeWidgetItem(group,[target['input_id'],self.original.get('unit',''),'','현재 원본에서 찾을 수 없음'])
                item.setData(0,DATA,deepcopy(target));item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(0,Qt.CheckState.Checked)
                self._target_items.append(item)
        self.tree.expandAll();self.tree.setColumnWidth(0,350);layout.addWidget(self.tree,1)
        self.message=QLabel('초안 적용은 계산하지 않습니다. 잘못된 입력도 초안으로 보존되며 실행만 차단됩니다.')
        self.message.setWordWrap(True);layout.addWidget(self.message)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel)
        check=QPushButton('입력 점검');buttons.addButton(check,QDialogButtonBox.ButtonRole.ActionRole)
        check.clicked.connect(self.check)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def value_draft(self):
        result={'id':self.identifier,'label':self.name.text(),'unit':self.unit.currentText(),'value':number_or_draft(self.value.text()),
                'targets':[deepcopy(item.data(0,DATA)) for item in self._target_items if item.checkState(0)==Qt.CheckState.Checked]}
        if self.lower.text() or self.upper.text():result['bounds']=[number_or_draft(self.lower.text()),number_or_draft(self.upper.text())]
        return result

    def check(self):
        row=self.value_draft()
        try:
            validate_binding(row,self.stage_ids)
            for target in row['targets']:
                original=next((v for v in self.catalogs.get(target['stage'],{}).get('inputs',[]) if v['id']==target['input_id']),None)
                if not original or original['unit']!=row['unit']:raise ValueError('선택한 대상의 실제 단위와 공유 단위를 일치시키세요.')
        except (ValueError,TypeError,KeyError) as error:
            self.message.setText(str(error));return False
        self.message.setText('입력 구조와 단위가 일치합니다. 적용 후 기존 입력 점검에서 물리 범위까지 확인하세요. 계산 0회.');return True
