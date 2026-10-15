"""Source-authoritative Impact A editing inside the existing local dialog."""
from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase,QTextCursor
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QPlainTextEdit,QSplitter,QTreeWidget,QTreeWidgetItem,QTableWidget,QTableWidgetItem,
    QAbstractItemView,QHeaderView,QTabWidget,QDialogButtonBox,QComboBox)
from caelab import impact_input_workflow as workflow, impact_reference_bindings as bindings
from caelab.impact_model import model_from_settings
from caelab.storage import canonical_hash


def field_value(value):
    try:return format(float(value),'.12g')
    except (ValueError,TypeError,OverflowError):return str(value)


def identity_label(value,full=False):
    if not isinstance(value,dict):return str(value)
    if 'instance' in value:return str(value['instance'])+' / 원 번호 '+str(value.get('local_id',''))
    if 'native_id' in value:return '원 번호 '+str(value['native_id'])
    if 'members' in value:
        members=value['members']
        names=[identity_label(row.get('element',row))+((' / '+row['side']) if 'side' in row else '') for row in (members if full else members[:5])]
        return str(value.get('label',''))+' / '+', '.join(names)+(' 외 '+str(len(members)-5)+'개' if not full and len(members)>5 else '')
    return str(value.get('label','대상'))


class SourceChangeDialog(QDialog):
    def __init__(self,page,*,field=None,parent=None):
        super().__init__(parent or page);self.page=page;self.field=field;self.applied=None
        self.opened=deepcopy(page.editor.edited());self.token=canonical_hash(self.opened)
        self.setWindowTitle('원 입력 수치 수정' if field else '선택 범위 수정');self.resize(780,600)
        layout=QVBoxLayout(self)
        if field:
            title=field['label']+(' ['+field['unit']+']' if field.get('unit') else '')
            self.original=str(field['value']);self.file=field['file']
        else:
            cursor=page.original.textCursor();self.start=cursor.selectionStart();self.end=cursor.selectionEnd()
            self.file=page.file;self.original=cursor.selectedText().replace('\u2029','\n')
            title=self.file+' / '+str(cursor.document().findBlock(self.start).blockNumber()+1)+'행부터 선택한 범위'
        label=QLabel(title);label.setWordWrap(True);layout.addWidget(label)
        self.replacement=QPlainTextEdit(self.original);self.replacement.setAccessibleName('수정할 원문' if not field else title)
        self.replacement.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont));layout.addWidget(self.replacement,1)
        self.preview=QPlainTextEdit();self.preview.setReadOnly(True);self.preview.setAccessibleName('변경 미리보기');layout.addWidget(self.preview,1)
        self.status=QLabel('미리보기 후 명시적으로 반영하세요. 원파일은 바뀌지 않습니다.');self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout();self.preview_button=QPushButton('미리보기');self.preview_button.clicked.connect(self.show_preview);row.addWidget(self.preview_button)
        self.apply_button=QPushButton('선택 편집 반영');self.apply_button.setEnabled(False);self.apply_button.clicked.connect(self.apply);row.addWidget(self.apply_button)
        cancel=QPushButton('취소');cancel.clicked.connect(self.reject);row.addWidget(cancel);layout.addLayout(row)
        self.replacement.textChanged.connect(lambda:self.apply_button.setEnabled(False))
    def candidate(self):
        settings=self.page.editor.edited()
        if self.field:
            return workflow.apply_native_field(settings,self.field['id'],float(self.replacement.toPlainText().strip()),
                reason='원 입력 수치 명시 편집',expected_definition_sha256=self.token)
        return workflow.apply_display_range(settings,file=self.file,start=self.start,end=self.end,
            replacement=self.replacement.toPlainText(),reason='선택한 원문 범위 명시 편집',expected_definition_sha256=self.token)
    def show_preview(self):
        try:
            reply=self.candidate();report=reply['inspection']
            self.preview.setPlainText('기존 선택\n'+self.original+'\n\n수정할 내용\n'+self.replacement.toPlainText())
            self.status.setText('계산 전 수정이 더 필요합니다. 이 초안을 반영하고 저장할 수 있습니다.' if report['blockers'] else '입력 확인됨. 계산은 실행하지 않았습니다.')
            self.apply_button.setEnabled(True)
        except (ValueError,KeyError,TypeError,OverflowError) as error:self.status.setText(str(error));self.apply_button.setEnabled(False)
    def apply(self):
        try:self.applied=self.candidate()['settings'];self.accept()
        except (ValueError,KeyError,TypeError,OverflowError) as error:self.status.setText(str(error));self.apply_button.setEnabled(False)


class ReferenceReviewDialog(QDialog):
    def __init__(self,settings,parent=None):
        super().__init__(parent);self.setWindowTitle('원 대상 대응 확인');self.resize(940,540)
        self.settings=deepcopy(settings);self.applied=None;self.choices=[];self.reviewed=None
        layout=QVBoxLayout(self);note=QLabel('기존 원 대상과 현재 원 대상을 비교하고, 의도한 대상을 고른 뒤 확인하세요. 거절하면 기존 선택과 실행 차단이 유지됩니다.');note.setWordWrap(True);layout.addWidget(note)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['선택 항목','기존 원 대상','현재 선택할 원 대상'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);layout.addWidget(self.table,1)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setMaximumHeight(140);layout.addWidget(self.details)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout();preview=QPushButton('대응 미리보기');preview.clicked.connect(self.show_review);row.addWidget(preview)
        self.confirm=QPushButton('현재 대상 명시 수락');self.confirm.setEnabled(False);self.confirm.clicked.connect(self.apply);row.addWidget(self.confirm)
        reject=QPushButton('거절');reject.clicked.connect(self.reject);row.addWidget(reject);layout.addLayout(row)
        model=model_from_settings(settings)
        for old in settings.get(bindings.KEY,{}).get('rows',[]):
            selection=old['selection'];kind=selection[0];index=selection[1];column=selection[2]
            if index>=len(settings.get(kind,[])):continue
            combo=QComboBox();current=settings[kind][index][column]
            if kind=='responses':
                from caelab.impact_responses import QUANTITIES
                association=QUANTITIES[settings[kind][index]['quantity']][1];table='nodes' if association=='POINTS' else 'elements'
                lineage=model.get('lineage',{}).get(table,{})
                for identifier in sorted(model[table]):
                    origin=lineage.get(str(identifier),{})
                    combo.addItem(identity_label(origin if origin.get('instance') else {'native_id':identifier}),identifier)
            else:
                table='nsets' if kind=='motions' else 'surfaces'
                for key in model[table]:
                    origin=model.get('lineage',{}).get(table,{}).get(key,{})
                    combo.addItem(str(origin.get('qualified_name',origin.get('label',key))),key)
            selected=combo.findData(current)
            try:
                actual=(bindings._entity(model,association,current) if kind=='responses' else bindings._target(model,table,current))
                if canonical_hash(actual)!=canonical_hash(old['source']):selected=-1
            except (ValueError,KeyError,TypeError):selected=-1
            combo.setCurrentIndex(selected)
            row_index=self.table.rowCount();self.table.insertRow(row_index)
            title={'responses':'결과','motions':'운동','contacts':'접촉'}[kind]+' '+str(index+1)+((' / '+column.upper()) if kind=='contacts' else '')
            for col,value in enumerate((title,identity_label(old['source']))):
                item=QTableWidgetItem(value);item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable);self.table.setItem(row_index,col,item)
            self.table.setCellWidget(row_index,2,combo);self.choices.append((selection,combo))
            combo.currentIndexChanged.connect(lambda _:self.confirm.setEnabled(False))
    def current(self):
        result=deepcopy(self.settings)
        for selection,combo in self.choices:
            if combo.currentIndex()<0:raise ValueError('현재 원 대상을 명시적으로 선택하세요.')
            result[selection[0]][selection[1]][selection[2]]=combo.currentData()
        return result
    def show_review(self):
        try:
            current=self.current();self.reviewed=bindings.review(current)
            self.details.setPlainText('\n\n'.join(label+'\n'+'\n'.join(identity_label(row['source'],full=True) for row in self.reviewed[side])
                for side,label in (('before','기존 원 대상 전체 구성원'),('after','현재 원 대상 전체 구성원'))))
            self.confirm.setEnabled(True);self.status.setText('현재 대상의 실제 구성원을 확인한 뒤 명시 수락하세요.')
        except (ValueError,KeyError,TypeError) as error:self.status.setText(str(error));self.confirm.setEnabled(False)
    def apply(self):
        try:
            self.applied=bindings.accept_review(self.current(),expected_definition_sha256=self.reviewed['definition_sha256'],
                expected_review_sha256=self.reviewed['review_sha256'],acknowledged=True);self.accept()
        except (ValueError,KeyError,TypeError) as error:self.status.setText(str(error));self.confirm.setEnabled(False)


class SourceEditor(QWidget):
    def __init__(self,editor):
        super().__init__(editor);self.editor=editor;self.file=None;self.buffer=None
        layout=QVBoxLayout(self);split=QSplitter();layout.addWidget(split,1)
        self.files=QTreeWidget();self.files.setHeaderLabels(['원 입력 파일','상태']);self.files.setMinimumWidth(210)
        self.files.setColumnWidth(0,160);self.files.header().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents);split.addWidget(self.files)
        right=QWidget();rl=QVBoxLayout(right);rl.setContentsMargins(0,0,0,0)
        self.content_tabs=QTabWidget();rl.addWidget(self.content_tabs,1)
        self.original=QPlainTextEdit();self.original.setReadOnly(True);self.original.setAccessibleName('선택한 파일의 현재 원문')
        self.original.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.fields=QTableWidget(0,4);self.fields.setHorizontalHeaderLabels(['수치 항목','값','단위','원 위치'])
        self.fields.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.fields.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.fields.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents);self.fields.horizontalHeader().setStretchLastSection(True)
        self.content_tabs.addTab(self.fields,'입력 조건');self.content_tabs.addTab(self.original,'고급 원문 편집')
        split.addWidget(right);split.setSizes([240,720]);split.setStretchFactor(1,1)
        row=QHBoxLayout()
        for name,label,call in [('range_button','선택 범위 수정…',self.edit_range),('field_button','선택 수치 수정…',self.edit_field),('reference_button','원 대상 대응 확인…',self.review_references)]:
            button=QPushButton(label);button.clicked.connect(call);row.addWidget(button);setattr(self,name,button)
        row.addStretch();layout.addLayout(row)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.diagnostics=QTreeWidget();self.diagnostics.setHeaderLabels(['수정이 필요한 원 위치','진단']);self.diagnostics.setMaximumHeight(110);layout.addWidget(self.diagnostics)
        self.diagnostics.itemActivated.connect(self.locate_diagnostic);self.files.currentItemChanged.connect(self.load_file)
        self.fields.itemSelectionChanged.connect(self.locate_field);self.original.selectionChanged.connect(self.update_actions)
        self.refresh()
    def refresh(self):
        current=self.file;settings=self.editor.edited();self.report=workflow.inspect(settings)
        self.files.blockSignals(True);self.files.clear()
        for row in self.report['files']:
            item=QTreeWidgetItem(self.files,[row['file'],'수정됨' if row['edited'] else '원본'])
            item.setToolTip(0,row['file'])
            if row['file']==current:self.files.setCurrentItem(item)
        self.files.blockSignals(False)
        if self.files.currentItem() is None and self.files.topLevelItemCount():self.files.setCurrentItem(self.files.topLevelItem(0))
        else:self.load_file()
        self.diagnostics.clear()
        for blocker in self.report['blockers']:
            location=(blocker.get('file') or '입력')+(' / '+str(blocker['line'])+'행' if blocker.get('line') else '')
            if type(blocker.get('occurrence')) is int:location+=' / 포함 순서 '+str(blocker['occurrence'])
            item=QTreeWidgetItem(self.diagnostics,[location,blocker['message']]);item.setData(0,Qt.ItemDataRole.UserRole,blocker)
        self.diagnostics.setColumnWidth(0,230);self.diagnostics.setVisible(bool(self.report['blockers']))
        self.status.setText('계산 전 수정 필요. 초안은 반영하고 저장할 수 있습니다. 진단을 두 번 눌러 원 위치를 여세요.' if self.report['blockers'] else '입력 확인됨. 선택 범위와 수치를 편집할 수 있습니다. 계산은 실행하지 않았습니다.')
        self.update_actions()
    def load_file(self,*_):
        item=self.files.currentItem();self.file=item.text(0) if item else None;self.buffer=None
        self.fields.setRowCount(0);self.original.clear()
        if self.file:
            self.buffer=workflow.editor_buffer(self.editor.edited(),self.file);self.original.setPlainText(self.buffer['effective_text'])
            for field in self.report['fields']:
                if field['file']!=self.file:continue
                row=self.fields.rowCount();self.fields.insertRow(row)
                for col,value in enumerate((field['label'],field_value(field['value']),field.get('unit',''),str(field['line'])+'행')):
                    self.fields.setItem(row,col,QTableWidgetItem(str(value)))
                self.fields.item(row,1).setToolTip('원 입력: '+str(field['value']))
                self.fields.item(row,0).setData(Qt.ItemDataRole.UserRole,field)
        self.update_actions()
    def update_actions(self):
        self.range_button.setEnabled(self.buffer is not None and self.original.textCursor().hasSelection())
        self.field_button.setEnabled(self.fields.currentRow()>=0)
        self.reference_button.setEnabled(bindings.KEY in self.editor.value)
    def select_line(self,line):
        block=self.original.document().findBlockByNumber(line-1)
        if block.isValid():
            cursor=QTextCursor(block);cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            self.original.setTextCursor(cursor);self.original.ensureCursorVisible();self.original.setFocus()
    def locate_field(self):
        row=self.fields.currentRow()
        if row>=0:self.select_line(self.fields.item(row,0).data(Qt.ItemDataRole.UserRole)['line'])
        self.update_actions()
    def locate_diagnostic(self,item,*_):
        blocker=item.data(0,Qt.ItemDataRole.UserRole)
        for i in range(self.files.topLevelItemCount()):
            target=self.files.topLevelItem(i)
            if target.text(0)==blocker.get('file'):
                self.files.setCurrentItem(target)
                self.content_tabs.setCurrentWidget(self.original)
                if blocker.get('line'):self.select_line(blocker['line'])
                break
    def change(self,dialog):
        if dialog.exec()==QDialog.DialogCode.Accepted and dialog.applied is not None:
            self.editor.replace_settings(dialog.applied)
    def edit_range(self):
        if self.original.textCursor().hasSelection():self.change(SourceChangeDialog(self))
    def edit_field(self):
        row=self.fields.currentRow()
        if row>=0:self.change(SourceChangeDialog(self,field=self.fields.item(row,0).data(Qt.ItemDataRole.UserRole)))
    def review_references(self):
        try:self.change(ReferenceReviewDialog(self.editor.edited(),self))
        except (ValueError,KeyError,TypeError) as error:self.status.setText(str(error))
