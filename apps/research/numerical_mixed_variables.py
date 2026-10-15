"""Local Plan domain editor; actual Pro owns every variable/domain rule.

Root attaches this consumer to the shared windows. All domain rules come from
the actual Pro B5/C1 public API; this dialog never evaluates a dependency.
"""
from copy import deepcopy
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog,
    QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QSplitter, QTableWidgetItem, QVBoxLayout, QWidget)

from .numerical_editing import PlanTable
from .numerical_methods import choice_label, choice_value


KINDS={'continuous':'연속','integer':'정수','discrete':'이산값','categorical':'범주'}
MODES={'free':'탐색','fixed':'고정','dependent':'종속식'}
FIELDS=('id','kind','mode','unit','value','lower','upper','transform')
ERROR_TEXT={
    'VARIABLE_COUNT':'변수는 1개 이상 64개 이하로 선택하세요.',
    'DUPLICATE_ID':'같은 변수 이름이 있습니다. 선택한 변수를 확인하세요.',
    'NONFINITE_NUMBER':'선택한 값에 유한한 숫자를 입력하세요. 원문은 유지됩니다.',
    'FRACTIONAL_INTEGER':'정수 변수에는 소수 부분이 없는 정수를 입력하세요.',
    'ENUM_MEMBERSHIP':'모델이 선언한 선택지에서 실제 값을 선택하세요.',
    'DISCRETE_MEMBERSHIP':'시작값을 허용 이산값 집합에서 선택하세요.',
    'CHOICE_SET':'허용할 선택지를 하나 이상 선택하세요.',
    'DEPENDENT_KIND':'종속식의 결과 종류는 연속 또는 정수로 선택하세요.',
    'INVALID_LOG':'로그 변환은 양의 범위를 가진 탐색용 연속 변수에서 지원합니다.',
    'OUT_OF_BOUNDS':'선택한 값이 허용 범위를 벗어났습니다.',
    'DISCRETE_ORDER':'이산값을 중복 없이 작은 값부터 입력하세요.',
    'UNKNOWN_REFERENCE':'종속식에 정의하지 않은 변수가 있습니다. 표시한 위치를 확인하세요.',
    'SELF_REFERENCE':'종속식에서 자기 변수를 참조할 수 없습니다.',
    'DEPENDENCY_CYCLE':'종속식이 서로 순환 참조합니다. 선택한 식을 확인하세요.',
    'UNIT_MISMATCH':'종속식의 차원과 결과 단위가 다릅니다.',
    'EXPRESSION_DIMENSION_OR_SYNTAX':'종속식의 구문과 단위를 확인하세요.',
    'EXPRESSION_SYNTAX':'종속식의 구문을 확인하세요.',
    'BINDING_UNIT':'단위가 모델의 선언과 다릅니다. 단위 변환은 자동 적용하지 않습니다.',
    'PHYSICAL_ENVELOPE':'탐색 범위가 모델이 허용한 범위를 벗어났습니다.',
    'UNADVERTISED_INPUT':'모델이 선언한 변수를 선택하세요.',
    'FORGED_ENUM':'선택지가 모델의 선언과 다릅니다. 모델에서 선택지를 다시 선택하세요.',
}


def declared_variable(descriptor):
    """Copy one advertised declaration, never its executable binding paths."""
    result={key:deepcopy(descriptor[key]) for key in ('id','unit','value') if key in descriptor}
    if descriptor.get('kind')=='categorical':
        result.update(kind='categorical',choices=deepcopy(descriptor['choices']))
    else:
        for key in ('lower','upper'):
            if key in descriptor:result[key]=deepcopy(descriptor[key])
    return result


def _cell_value(item):
    from .request_plan_window import DATA, CHOICE_DATA, numeric_text
    binding=item.data(DATA); selected=item.data(CHOICE_DATA)
    if isinstance(selected,dict) and selected.get('label')==item.text():
        return deepcopy(selected['value'])
    if item.text()==binding['shown']:return deepcopy(binding['value'])
    value=choice_value(item.text(),binding['choices'])
    return numeric_text(value) if binding['numeric'] and isinstance(value,str) else value


class MixedVariablesDialog(QDialog):
    """Edit detached declarations; no owner, Client, evaluator or model setter."""
    def __init__(self, variables, descriptors=None, parent=None, *, operation='doe'):
        super().__init__(parent)
        from caelab.variable_domains import variable_schema
        from .request_plan_window import _WorksheetDelegate
        self.schema=variable_schema()
        self.original=deepcopy(variables);self.rows=deepcopy(variables)
        self.descriptors=deepcopy(descriptors) if descriptors is not None else None
        self.operation=operation;self.value=None;self.normalized=None
        self._showing=False;self._queued=False;self._history=[deepcopy(self.rows)];self._history_index=0
        self.setWindowTitle('변수 범위');self.resize(1120,690)
        layout=QVBoxLayout(self);split=QSplitter();layout.addWidget(split,1)
        self.table=PlanTable(0,len(FIELDS));self.table.setObjectName('mixedPlanVariables')
        self.table.setHorizontalHeaderLabels(['변수','종류','용도','단위','시작값 / 고정값','하한','상한','변환'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setItemDelegate(_WorksheetDelegate(self.table))
        self.table.pasteRejected.connect(lambda message:self.error.setText(message))
        split.addWidget(self.table)
        detail=QWidget();box=QVBoxLayout(detail);box.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.title=QLabel();box.addWidget(self.title)
        self.expression_label=QLabel('종속식');box.addWidget(self.expression_label)
        self.expression=QPlainTextEdit();self.expression.setMaximumHeight(110);box.addWidget(self.expression)
        self.values_label=QLabel('허용 이산값');box.addWidget(self.values_label)
        self.values=PlanTable(0,1);self.values.setHorizontalHeaderLabels(['값'])
        self.values.setItemDelegate(_WorksheetDelegate(self.values));box.addWidget(self.values)
        discrete_actions=QWidget();line=QHBoxLayout(discrete_actions);line.setContentsMargins(0,0,0,0)
        add=QPushButton('값 추가');remove=QPushButton('선택 제거');line.addWidget(add);line.addWidget(remove)
        box.addWidget(discrete_actions);self.discrete_actions=discrete_actions
        self.choices_label=QLabel('허용 선택지');box.addWidget(self.choices_label)
        self.choices=QListWidget();box.addWidget(self.choices)
        enum_actions=QWidget();line=QHBoxLayout(enum_actions);line.setContentsMargins(0,0,0,0)
        up=QPushButton('위로');down=QPushButton('아래로');line.addWidget(up);line.addWidget(down)
        box.addWidget(enum_actions);self.enum_actions=enum_actions
        self.no_detail=QLabel('선택한 변수의 시작값과 범위를 표에서 편집하세요.');self.no_detail.setWordWrap(True)
        box.addWidget(self.no_detail);box.addStretch(1);split.addWidget(detail);split.setSizes([790,290])
        self.error=QLabel();self.error.setWordWrap(True);layout.addWidget(self.error)
        commands=QHBoxLayout();check=QPushButton('입력 확인');commands.addWidget(check);commands.addStretch()
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('초안에 적용')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소');commands.addWidget(buttons);layout.addLayout(commands)
        self.table.itemChanged.connect(self._changed)
        self.table.currentCellChanged.connect(lambda *_:self._show_detail())
        self.expression.textChanged.connect(self._expression_changed)
        self.values.itemChanged.connect(self._values_changed)
        self.choices.itemChanged.connect(self._choices_changed)
        add.clicked.connect(self._add_value);remove.clicked.connect(self._remove_values)
        up.clicked.connect(lambda:self._move_choice(-1));down.clicked.connect(lambda:self._move_choice(1))
        check.clicked.connect(self.validate_inputs);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject)
        for label,key,callback in [('실행 취소',QKeySequence.StandardKey.Undo,self.undo),('다시 실행',QKeySequence.StandardKey.Redo,self.redo)]:
            action=QAction(label,self);action.setShortcut(QKeySequence(key));action.triggered.connect(callback);self.addAction(action)
        self._refresh()

    def _cell(self,table,row,column,value,*,numeric=False,choices=(),editable=True):
        from .request_plan_window import DATA
        shown=choice_label(value,choices)
        item=QTableWidgetItem(shown);item.setData(DATA,dict(path=(row,column) if editable else None,
            value=deepcopy(value),shown=shown,numeric=numeric,choices=list(choices)))
        item.setToolTip(str(value) if value is not None else '')
        if not editable:item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        table.setItem(row,column,item)

    def _refresh(self):
        self._queued=False;selected=max(0,self.table.currentRow());self._showing=True
        from caelab.variable_domains import normalize
        # Static public defaults are display-only; the detached draft keeps omissions.
        try:defaults=normalize(self.rows)
        except (ValueError,TypeError,KeyError):defaults=[]
        try:
            self.table.setRowCount(len(self.rows))
            for index,row in enumerate(self.rows):
                if not isinstance(row,dict):
                    for column in range(len(FIELDS)):self._cell(self.table,index,column,'입력 확인 필요' if column==0 else '',editable=False)
                    self.table.item(index,0).setToolTip(str(row));continue
                kind=row.get('kind','continuous');mode=row.get('mode','free')
                category_choices=row.get('choices',[])
                category_choices=category_choices if isinstance(category_choices,list) else []
                for col,key in enumerate(FIELDS):
                    value=row.get(key,{'kind':'continuous','mode':'free','transform':'linear'}.get(key))
                    choices=([(KINDS[x],x) for x in self.schema['properties']['kind']['enum']] if key=='kind' else
                        [(MODES[x],x) for x in self.schema['properties']['mode']['enum']] if key=='mode' else
                        [('선형','linear'),('로그','log')] if key=='transform' else
                        [(x['label'],x['value']) for x in category_choices if isinstance(x,dict) and {'label','value'}<=set(x)] if key=='value' and kind=='categorical' else ())
                    editable=key!='id' and not (key=='value' and mode=='dependent') and not (key in ('lower','upper') and kind=='categorical')
                    self._cell(self.table,index,col,value,numeric=key in ('lower','upper') or key=='value' and kind!='categorical',choices=choices,editable=editable)
                    if key=='value' and mode!='dependent' and not {'value','initial'} & set(row) and index<len(defaults):
                        item=self.table.item(index,col)
                        shown=choice_label(defaults[index].get('value'),choices)
                        from .request_plan_window import DATA
                        binding=item.data(DATA);binding['shown']=shown;item.setData(DATA,binding)
                        item.setText(shown);item.setToolTip('시작값을 생략하면 사용하는 값: '+shown)
                descriptor=next((d for d in self.descriptors or [] if d.get('id')==row.get('id')),None)
                if descriptor:self.table.item(index,0).setText(descriptor.get('label',row['id']))
            self.table.resizeColumnsToContents()
            if self.rows:self.table.setCurrentCell(min(selected,len(self.rows)-1),0)
        finally:self._showing=False
        self._show_detail()

    def _row(self):
        index=self.table.currentRow()
        return self.rows[index] if 0<=index<len(self.rows) and isinstance(self.rows[index],dict) else None

    def _show_detail(self):
        if self._showing:return
        self._showing=True
        try:
            row=self._row() or {};kind=row.get('kind','continuous');mode=row.get('mode','free')
            descriptor=next((d for d in self.descriptors or [] if d.get('id')==row.get('id')),None)
            self.title.setText(str((descriptor or {}).get('label',row.get('id','변수 선택')))+' ['+str(row.get('unit',''))+']')
            self.title.setToolTip(str(row.get('id','')))
            for widget in (self.expression_label,self.expression):widget.setVisible(mode=='dependent')
            self.expression.setPlainText(str(row.get('expression','')))
            for widget in (self.values_label,self.values,self.discrete_actions):widget.setVisible(kind=='discrete')
            values=row.get('values',[]);self.values.setRowCount(len(values) if isinstance(values,list) else 0)
            for i,value in enumerate(values if isinstance(values,list) else []):self._cell(self.values,i,0,value,numeric=True)
            for widget in (self.choices_label,self.choices,self.enum_actions):widget.setVisible(kind=='categorical')
            self.choices.clear();declared=row.get('choices',[])
            declared=declared if isinstance(declared,list) else []
            all_choices=deepcopy(declared) if isinstance(declared,list) else []
            actual=next((x for x in self.descriptors or [] if x.get('id')==row.get('id')),{}).get('choices',[])
            for choice in actual:
                if choice not in all_choices:all_choices.append(deepcopy(choice))
            for choice in all_choices:
                item=QListWidgetItem(str(choice.get('label','선택지 확인 필요')) if isinstance(choice,dict) else '선택지 확인 필요')
                item.setData(Qt.ItemDataRole.UserRole,choice);item.setToolTip(str(choice.get('value','')) if isinstance(choice,dict) else str(choice))
                item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if choice in declared else Qt.CheckState.Unchecked);self.choices.addItem(item)
            self.no_detail.setVisible(kind not in ('discrete','categorical') and mode!='dependent')
        finally:self._showing=False

    def _remember(self):
        if self.rows!=self._history[self._history_index]:
            self._history=self._history[:self._history_index+1]+[deepcopy(self.rows)];self._history_index+=1

    def _edited(self,refresh=False):
        self.normalized=None;self.error.clear();self.error.setToolTip('');QTimer.singleShot(0,self._remember)
        if refresh and not self._queued:self._queued=True;QTimer.singleShot(0,self._refresh)

    def _changed(self,item):
        if self._showing:return
        row=self.rows[item.row()];key=FIELDS[item.column()];value=_cell_value(item);row[key]=value
        if key=='kind':
            if value!='categorical':row.pop('choices',None)
            if value!='discrete':row.pop('values',None)
            if value=='categorical':
                for field in ('lower','upper','lower_bound','upper_bound'):row.pop(field,None)
                row['unit']='1'
                descriptor=next((d for d in self.descriptors or [] if d.get('id')==row.get('id')),None)
                if descriptor and descriptor.get('kind')=='categorical':
                    row['choices']=deepcopy(descriptor['choices']);row['value']=deepcopy(descriptor['value'])
            elif value=='discrete':row.setdefault('values',[])
        if key=='mode':
            if value=='dependent':
                row.pop('value',None);row.pop('initial',None);row.setdefault('expression','')
            else:row.pop('expression',None)
        self._edited(refresh=key in ('kind','mode'))

    def _expression_changed(self):
        if self._showing or self._row() is None:return
        self._row()['expression']=self.expression.toPlainText();self._edited()

    def _values_changed(self,*_):
        if self._showing or self._row() is None:return
        self._row()['values']=[_cell_value(self.values.item(i,0)) for i in range(self.values.rowCount())];self._edited()

    def _add_value(self):
        if self._row() is not None:
            if not isinstance(self._row().get('values'),list):self._row()['values']=[]
            self._row()['values'].append('');self._edited(refresh=True)

    def _remove_values(self):
        if self._row() is None:return
        selected={x.row() for x in self.values.selectedIndexes()}
        values=self._row().get('values',[])
        self._row()['values']=[x for i,x in enumerate(values if isinstance(values,list) else []) if i not in selected];self._edited(refresh=True)

    def _choices_changed(self,*_):
        if self._showing or self._row() is None:return
        self._row()['choices']=[deepcopy(self.choices.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.choices.count())
            if self.choices.item(i).checkState()==Qt.CheckState.Checked];self._edited(refresh=True)

    def _move_choice(self,offset):
        index=self.choices.currentRow();target=index+offset
        if 0<=index<self.choices.count() and 0<=target<self.choices.count():
            item=self.choices.takeItem(index);self.choices.insertItem(target,item);self.choices.setCurrentRow(target);self._choices_changed()

    def _commit_editor(self):
        focus=QApplication.focusWidget()
        if focus is not None and self.isAncestorOf(focus):focus.clearFocus()
        self._remember()

    def undo(self):
        self._commit_editor()
        if self._history_index:
            self._history_index-=1;self.rows=deepcopy(self._history[self._history_index])
            self.normalized=None;self.error.clear();self.error.setToolTip('');self._refresh()

    def redo(self):
        self._commit_editor()
        if self._history_index+1<len(self._history):
            self._history_index+=1;self.rows=deepcopy(self._history[self._history_index])
            self.normalized=None;self.error.clear();self.error.setToolTip('');self._refresh()

    def validate_inputs(self):
        self._commit_editor()
        from caelab.variable_domains import normalize, capability, DomainError
        from caelab.variable_binding import admit_domains
        try:
            self.normalized=normalize(self.rows)
            if self.descriptors is not None:admit_domains(self.normalized,self.descriptors)
            available=capability(self.operation,self.rows)['available']
            self.error.setText('입력을 확인했습니다.' if available else '이 변수 종류는 선택한 계산 방법에서 지원하지 않습니다. DOE 또는 차분 진화를 선택하세요.')
            return available
        except (ValueError,TypeError,KeyError) as error:
            self.error.setText(ERROR_TEXT.get(getattr(error,'code',None),'변수의 종류, 허용 범위와 종속식을 확인하세요. 입력은 유지됩니다.'));self.error.setToolTip(str(error))
            if isinstance(error,DomainError):self.locate_error(error.diagnostic())
            return False

    def locate_error(self,diagnostic):
        match=re.match(r'^variables\.(\d+)(?:\.(\w+))?',diagnostic.get('path',''))
        if not match:return
        row=int(match[1]);field=match[2]
        if row>=len(self.rows):return
        column=FIELDS.index(field) if field in FIELDS else 0
        self.table.setCurrentCell(row,column);self.table.scrollToItem(self.table.item(row,column))
        if field=='expression':
            self.expression.setFocus();cursor=self.expression.textCursor()
            block=self.expression.document().findBlockByLineNumber(max(0,(diagnostic.get('line') or 1)-1))
            if block.isValid():cursor.setPosition(block.position()+min(diagnostic.get('column') or 0,len(block.text())))
            if diagnostic.get('line') is not None and diagnostic.get('column') is not None:
                cursor.select(type(cursor).SelectionType.WordUnderCursor)
            self.expression.setTextCursor(cursor)

    def accept(self):
        self._commit_editor();self.value=deepcopy(self.rows);super().accept()
