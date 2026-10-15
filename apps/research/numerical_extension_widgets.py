"""Editors and retained views for declared Numerical extensions; no execution."""
from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)


class JointDistributionEditor(QWidget):
    MODES = [('독립 분포', 'independent'), ('상관 정규분포', 'correlated'),
             ('다변량 정규분포 공분산', 'multivariate_normal'), ('Gaussian copula', 'gaussian_copula')]

    def __init__(self, value, variables, parent=None):
        super().__init__(parent)
        self.original = deepcopy(value)
        self.variables = deepcopy(variables)
        self.names = [v['id'] for v in variables]
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel('결합 가정'))
        self.family = QComboBox()
        self.family.setAccessibleName('결합분포 가정')
        for label, key in self.MODES:
            self.family.addItem(label, key)
        joint = value.get('joint', {})
        assumption = value.get('independence')
        mode = (joint.get('family') if assumption == 'JOINT_USER_DECLARED' and isinstance(joint,dict) else
                'independent' if assumption == 'INDEPENDENT_USER_DECLARED' else
                'correlated' if assumption == 'CORRELATED_NORMAL_USER_DECLARED' else '')
        if self.family.findData(mode) < 0:
            self.family.addItem('미지정 가정' if not assumption else str(assumption), mode)
        self.family.setCurrentIndex(self.family.findData(mode))
        self.initial_mode = mode
        row.addWidget(self.family,1)
        clear = QPushButton('결합 선언 제거')
        clear.clicked.connect(self._clear)
        row.addWidget(clear)
        layout.addLayout(row)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.matrix = QTableWidget(len(variables),len(variables)+1)
        self.matrix.setAccessibleName('결합분포 행렬')
        layout.addWidget(self.matrix,1)
        self.declarations = {'correlated':deepcopy(value.get('correlation',{}))}
        if isinstance(joint,dict):
            self.declarations[joint.get('family')] = deepcopy(joint.get('covariance' if joint.get('family')=='multivariate_normal' else 'correlation',{}))
        self.initial_cells = []
        self.edited_modes = set()
        self.cleared = False
        self.active_mode = mode
        self._load(mode)
        self.family.currentIndexChanged.connect(self._switch)

    def _capture(self):
        return [[self.matrix.item(i,j+1).text() for j in range(len(self.names))] for i in range(len(self.names))]

    def _declaration(self):
        from .numerical_methods import number
        from caelab.numerical_extensions import covariance_units
        result = {'variables':self.names,'matrix':[[number(s) for s in row] for row in self._capture()]}
        if self.active_mode == 'multivariate_normal':
            result['units'] = covariance_units(self.variables)
        return result

    def _load(self, mode):
        from .numerical_methods import display_number
        self.matrix.setHorizontalHeaderLabels(['변수 / 행 단위']+[v['id']+' ['+v['unit']+']' for v in self.variables])
        declaration = self.declarations.get(mode,{})
        valid_order = isinstance(declaration,dict) and declaration.get('variables') == self.names
        raw = declaration.get('matrix',[]) if valid_order else []
        self.matrix.setEnabled(mode in {'correlated','multivariate_normal','gaussian_copula'})
        for i,v in enumerate(self.variables):
            label = QTableWidgetItem(v['id']+' ['+v['unit']+']')
            label.setFlags(label.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.matrix.setItem(i,0,label)
            for j in range(len(self.names)):
                value = raw[i][j] if i<len(raw) and isinstance(raw[i],list) and j<len(raw[i]) else ''
                cell = QTableWidgetItem(str(value) if value != '' else '')
                cell.setToolTip(('공분산 단위: '+v['unit']+'*'+self.variables[j]['unit']+'\n' if mode=='multivariate_normal' else '상관 계수 [1]\n')+str(value))
                self.matrix.setItem(i,j+1,cell)
        messages = {'independent':'변수의 독립성을 명시합니다. 결합 행렬을 사용하지 않습니다.',
            'correlated':'물리 정규분포의 상관 계수 [1]. 정규분포 주변분포만 지원합니다.',
            'multivariate_normal':'물리 공분산: 행 단위 × 열 단위. 대각값은 선언한 표준편차의 제곱과 같아야 합니다. 정규분포만 지원합니다.',
            'gaussian_copula':'잠재 정규 상관 [1]을 선언합니다. 변환 뒤 물리 변수의 Pearson 상관과 다릅니다.'}
        text = messages.get(mode,'가정을 선택하고 필요한 행렬을 직접 입력하세요.')
        if declaration and not valid_order:
            text += ' 변수 순서가 달라 기존 선언을 표시하지 않습니다. 그대로 두면 원 선언을 보존하며 실행 검사가 차단합니다.'
        self.note.setText(text)
        self.matrix.resizeColumnsToContents()
        self.initial_cells = self._capture()

    def _switch(self):
        if self._capture() != self.initial_cells:
            self.declarations[self.active_mode] = self._declaration()
            self.edited_modes.add(self.active_mode)
        self.active_mode = self.family.currentData()
        self._load(self.active_mode)

    def _clear(self):
        self.cleared = True
        self.declarations = {}
        self.family.setCurrentIndex(self.family.findData('independent'))
        self.active_mode = 'independent'
        self._load('independent')

    def apply(self, result):
        result = deepcopy(result)
        changed = (self.cleared or self.active_mode != self.initial_mode
                   or self.active_mode in self.edited_modes or self._capture() != self.initial_cells)
        if not changed:
            return result
        mode = self.active_mode
        if mode not in {key for _,key in self.MODES}:
            return result
        result.pop('joint',None)
        result.pop('correlation',None)
        if mode == 'independent':
            result['independence'] = 'INDEPENDENT_USER_DECLARED'
        elif mode == 'correlated':
            result.update(independence='CORRELATED_NORMAL_USER_DECLARED',correlation=self._declaration())
        else:
            result.update(independence='JOINT_USER_DECLARED',joint={'family':mode,
                'covariance' if mode=='multivariate_normal' else 'correlation':self._declaration()})
        return result


class SobolConvergenceWindow(QDialog):
    """Finite N/2N changes in retained indices; no analyzer is called here."""
    def __init__(self, result, parent=None):
        super().__init__(parent,Qt.WindowType.Window)
        from .numerical_methods import display_number
        self.result = deepcopy(result)
        self.setWindowTitle('Sobol 수렴 비교')
        self.resize(1000,650)
        layout = QVBoxLayout(self)
        counts = result.get('base_counts',['?','?'])
        title = QLabel('기본 표본 '+str(counts[0])+' → '+str(counts[1]))
        font=title.font();font.setPointSize(font.pointSize()+2);font.setBold(True);title.setFont(font)
        layout.addWidget(title)
        response=result.get('response',{})
        note=QLabel(str(response.get('response',''))+' ['+str(response.get('unit',''))+']\n저장된 두 설계의 지수와 신뢰구간을 비교합니다. 지수 변화만으로 수렴을 보증하지 않습니다.')
        note.setWordWrap(True);layout.addWidget(note)
        self.table=QTableWidget(0,7)
        self.table.setHorizontalHeaderLabels(['효과','변수','N','2N','차이 (2N−N)','N 신뢰구간 반폭','2N 신뢰구간 반폭'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        labels={'S1':'1차','ST':'총효과','S2':'2차'}
        for i,row in enumerate(result.get('comparison',[])):
            self.table.insertRow(i)
            values=[labels.get(row['index'],row['index']),', '.join(row['variables'])]+[row.get(k) for k in ('N','2N','difference','N_confidence','2N_confidence')]
            for j,value in enumerate(values):
                item=QTableWidgetItem(display_number(value));item.setData(Qt.ItemDataRole.UserRole,deepcopy(value));item.setToolTip(str(value))
                self.table.setItem(i,j,item)
        self.table.resizeColumnsToContents();layout.addWidget(self.table,1)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close);layout.addWidget(buttons)


def joint_summary(sampling):
    family=sampling.get('joint',{}).get('family')
    return ('다변량 정규분포 / 물리 공분산' if family=='multivariate_normal' else
            'Gaussian copula / 잠재 정규 상관' if family=='gaussian_copula' else '')


class SurrogateSearchDialog(QDialog):
    """Edit a prediction recommendation; accepting only changes the Plan draft."""
    def __init__(self, value, parent=None):
        super().__init__(parent)
        from .numerical_methods import display_number
        self.original=deepcopy(value)
        search=value.get('search',{})
        self.setWindowTitle('저장 모델 예측 탐색')
        self.resize(850,700)
        layout=QVBoxLayout(self)
        definition=search.get('objective',{})
        note=QLabel('예측 응답: '+str(definition.get('response','미지정'))+' ['+str(definition.get('unit',''))+']\n저장된 모델을 이용해 추천점을 찾습니다. 실제 해석은 수행하지 않습니다.')
        note.setWordWrap(True);layout.addWidget(note)
        form=QFormLayout()
        self.direction=QComboBox()
        self.direction.addItem('최소화','minimize');self.direction.addItem('최대화','maximize')
        direction=definition.get('direction','minimize')
        if self.direction.findData(direction)<0:self.direction.addItem(str(direction),direction)
        self.direction.setCurrentIndex(self.direction.findData(direction))
        form.addRow('추천 목표',self.direction)
        self.options={}
        for label,key,default,maximum in [('세대 수','max_generations',5,100000),('집단 크기','population_size',8,100000),('난수 시드','seed',0,2147483647)]:
            widget=QSpinBox();widget.setRange(0 if key!='population_size' else 1,maximum)
            raw=search.get('seed',default) if key=='seed' else search.get('options',{}).get(key,default)
            # Keep unsupported raw values in the draft if not explicitly edited.
            widget.setValue(raw if type(raw) is int and widget.minimum()<=raw<=maximum else default)
            widget.setProperty('originalValue',raw);widget.setProperty('shownValue',widget.value())
            form.addRow(label,widget);self.options[key]=widget
        layout.addLayout(form)
        self.table=QTableWidget(0,5)
        self.table.setHorizontalHeaderLabels(['변수','단위','초기값','탐색 하한','탐색 상한'])
        self.table.setAlternatingRowColors(True)
        for i,variable in enumerate(search.get('variables',[])):
            self.table.insertRow(i)
            for j,key in enumerate(('id','unit','value','lower','upper')):
                raw=variable.get(key)
                item=QTableWidgetItem(display_number(raw))
                item.setData(Qt.ItemDataRole.UserRole,{'raw':raw,'shown':item.text()});item.setToolTip(str(raw))
                if j<2:item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i,j,item)
        self.table.resizeColumnsToContents();self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table,1)
        constraint_row=QHBoxLayout()
        constraint_row.addWidget(QLabel('예측 응답 제약'),1)
        self.add_constraint=QPushButton('제약 추가')
        self.remove_constraint=QPushButton('선택 제약 삭제')
        constraint_row.addWidget(self.add_constraint);constraint_row.addWidget(self.remove_constraint)
        layout.addLayout(constraint_row)
        self.constraints=QTableWidget(0,4)
        self.constraints.setHorizontalHeaderLabels(['응답','조건','한계값','단위'])
        self.constraints.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.constraints.setMaximumHeight(170)
        self.constraints.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.constraints,1)
        for declaration in search.get('constraints',[]):self._constraint(declaration)
        self.add_constraint.clicked.connect(lambda:self._constraint({
            **{k:deepcopy(v) for k,v in definition.items() if k!='direction'},'operator':'<=','limit':''}))
        self.remove_constraint.clicked.connect(self._remove_constraint)
        limitation=QLabel('범위는 저장된 정규화 범위 안에 있어야 합니다. 학습점 지원영역 밖 예측은 별도로 표시합니다. 변수·단위·응답이 다른 모델로 재선택하면 실행 검사가 차단합니다.')
        limitation.setWordWrap(True);layout.addWidget(limitation)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def _constraint(self,declaration):
        from .numerical_methods import display_number
        row=self.constraints.rowCount();self.constraints.insertRow(row)
        name=QTableWidgetItem(str(declaration.get('response','미지정')))
        name.setData(Qt.ItemDataRole.UserRole,deepcopy(declaration))
        name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.constraints.setItem(row,0,name)
        operator=QComboBox();operator.addItems(['<=','>='])
        operator.setMinimumWidth(72);operator.setAccessibleName('예측 제약 조건')
        raw=declaration.get('operator','<=')
        if operator.findText(raw)<0:operator.addItem(str(raw))
        operator.setCurrentText(raw);self.constraints.setCellWidget(row,1,operator)
        raw=declaration.get('limit','')
        limit=QTableWidgetItem(display_number(raw))
        limit.setData(Qt.ItemDataRole.UserRole,{'raw':raw,'shown':limit.text()})
        self.constraints.setItem(row,2,limit)
        unit=QTableWidgetItem(str(declaration.get('unit','미지정')))
        unit.setFlags(unit.flags() & ~Qt.ItemFlag.ItemIsEditable);self.constraints.setItem(row,3,unit)
        self.constraints.resizeColumnsToContents()
        self.constraints.setColumnWidth(1,95)
        self.constraints.setColumnWidth(2,110)
        self.constraints.setCurrentCell(row,2)

    def _remove_constraint(self):
        for row in sorted({item.row() for item in self.constraints.selectedIndexes()},reverse=True):
            self.constraints.removeRow(row)

    def value(self):
        from .numerical_methods import number
        result=deepcopy(self.original)
        search=result.setdefault('search',{})
        search.setdefault('objective',{})['direction']=self.direction.currentData()
        for key,widget in self.options.items():
            value=widget.property('originalValue') if widget.value()==widget.property('shownValue') else widget.value()
            if key=='seed':search[key]=value
            else:search.setdefault('options',{})[key]=value
        for i,variable in enumerate(search.get('variables',[])):
            for j,key in enumerate(('value','lower','upper'),2):
                item=self.table.item(i,j);meta=item.data(Qt.ItemDataRole.UserRole)
                variable[key]=meta['raw'] if item.text()==meta['shown'] else number(item.text())
        search['constraints']=[]
        for row in range(self.constraints.rowCount()):
            declaration=deepcopy(self.constraints.item(row,0).data(Qt.ItemDataRole.UserRole))
            declaration['operator']=self.constraints.cellWidget(row,1).currentText()
            item=self.constraints.item(row,2);meta=item.data(Qt.ItemDataRole.UserRole)
            declaration['limit']=meta['raw'] if item.text()==meta['shown'] else number(item.text())
            search['constraints'].append(declaration)
        return result
