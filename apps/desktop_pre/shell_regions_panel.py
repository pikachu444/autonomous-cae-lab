"""S8 region editing in the existing Qt/FreeCAD panel, not a second owner.

The dialog edits a copy. Cancel/close has no native effect. Its explicit accept
returns raw drafts, including invalid numbers; the host's ordinary Save/Apply
and asynchronous-save snapshot rules remain the only commit path.
"""
from copy import deepcopy

from caelab.shell_regions import uniform_region, reverse_region, validate, REGION_FIELDS


def edit_regions(W,C,editor,draft,*,parent=None):
    from .shell_edit import native_type
    from .shell_region_native import selection, check_reversal_edit
    from .b13_selection_dialog import choose_ids
    original=deepcopy(draft)
    working=deepcopy(draft)
    if 'regions' not in working:
        working['regions']=[uniform_region(working)]
    original_rows=deepcopy(working['regions'])
    dialog=W.QDialog(parent); dialog.setWindowTitle('셸 영역 편집'); dialog.resize(1050,710)
    layout=W.QVBoxLayout(dialog)
    message=W.QLabel('각 요소에 영역을 하나 할당합니다. 기하 법선은 계산의 평균 법선과 다를 수 있습니다. '
                    '초안에 반영한 뒤 본 화면에서 속성 적용 → 입력 준비 → 계산을 선택하세요.')
    message.setWordWrap(True);layout.addWidget(message)
    split=W.QSplitter(C.Qt.Horizontal);layout.addWidget(split,1)
    left=W.QWidget();leftbox=W.QVBoxLayout(left);regions=W.QListWidget();regions.setAccessibleName('셸 속성 영역')
    leftbox.addWidget(regions,1);leftbuttons=W.QHBoxLayout();add=W.QPushButton('영역 추가');remove=W.QPushButton('영역 삭제')
    leftbuttons.addWidget(add);leftbuttons.addWidget(remove);leftbox.addLayout(leftbuttons);split.addWidget(left)
    right=W.QWidget();rightbox=W.QVBoxLayout(right);form=W.QFormLayout();rightbox.addLayout(form)
    labels={'label':'영역 이름','thickness_mm':'두께 [mm]','offset':'기준면 오프셋 / 두께',
            'pressure_MPa':'압력 [MPa]','axis_x':'국부 1축 참조 X','axis_y':'국부 1축 참조 Y','axis_z':'국부 1축 참조 Z'}
    fields={}
    for key,label in labels.items():
        field=W.QLineEdit();field.setAccessibleName(label);form.addRow(label,field);fields[key]=field
    normal=W.QLabel();normal.setWordWrap(True);form.addRow('법선',normal)
    reverse=W.QPushButton('선택 영역 법선 반전');keep=W.QCheckBox('물리적 압력 방향 유지');keep.setChecked(True)
    normalbox=W.QHBoxLayout();normalbox.addWidget(reverse);normalbox.addWidget(keep);rightbox.addLayout(normalbox)
    geometry=W.QComboBox();pressure=W.QComboBox();form.addRow('모델 단면 속성',geometry);form.addRow('모델 압력 조건',pressure)
    target=W.QLabel();target.setWordWrap(True);rightbox.addWidget(target)
    target_buttons=W.QHBoxLayout();pickface=W.QPushButton('선택한 면 사용');pickids=W.QPushButton('요소 선택…')
    move=W.QPushButton('다른 영역에서 제외');move.setToolTip('현재 요소를 다른 영역의 대상에서 제외합니다.')
    for b in (pickface,pickids,move):target_buttons.addWidget(b)
    rightbox.addLayout(target_buttons)
    target_table=W.QTableWidget(0,2);target_table.setHorizontalHeaderLabels(['요소 번호','속성 영역'])
    target_table.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
    target_table.horizontalHeader().setSectionResizeMode(W.QHeaderView.Stretch);rightbox.addWidget(target_table,1)
    errors=W.QPlainTextEdit();errors.setReadOnly(True);errors.setMaximumHeight(130);rightbox.addWidget(errors)
    split.addWidget(right);split.setSizes([240,790])
    buttons=W.QDialogButtonBox(W.QDialogButtonBox.Ok|W.QDialogButtonBox.Cancel)
    buttons.button(W.QDialogButtonBox.Ok).setText('초안에 반영')
    buttons.button(W.QDialogButtonBox.Ok).setToolTip('미완성 숫자도 원문 그대로 초안에 보존합니다.')
    buttons.button(W.QDialogButtonBox.Cancel).setText('취소')
    layout.addWidget(buttons)
    state={'row':None,'loading':False}
    def current():
        i=state['row']; return None if i is None or i>=len(working['regions']) else working['regions'][i]
    def safe(fn):
        def call(*_):
            try:fn()
            except Exception as exc:errors.setPlainText(str(exc))
        return call
    def annotate():
        items,_=validate(working)
        messages=[]
        for error in items:
            parts=error['path'].split('/');field=parts[-1]
            label=labels.get(field,{'elements':'요소 집합','regions':'영역 할당',
                'geometry_id':'모델 단면 속성','pressure_id':'모델 압력 조건','orientation':'법선'}.get(field,'속성'))
            prefix=f'영역 {int(parts[1])+1} ' if len(parts)>1 and parts[0]=='regions' and parts[1].isdigit() else ''
            messages.append(prefix+label+': '+error['message'])
        errors.setPlainText('\n'.join(messages))
        errors.setToolTip('\n'.join(e['path']+': '+e['message'] for e in items))
        for i,row in enumerate(working['regions']):
            regions.item(i).setText(f'{row["label"] or "이름 없음"} ({len(row["elements"])}개)')
        row=current()
        if row is None:return
        normal.setText({'native':'참조 메시 순서와 같은 기하 법선', 'reversed':'참조 메시 순서와 반대 기하 법선'}.get(row['orientation'],'법선 미확정'))
        names=[]
        for ref in row['face_refs']:
            obj=editor.owner.doc.getObject(ref['object_id'])
            names.append((obj.Label if obj else '참조 상실')+' / '+', '.join(ref['subelements']))
        target.setText('대상: '+('; '.join(names) if names else '명시 요소 집합')+f' / {len(row["elements"])}개')
        target_table.setRowCount(len(row['elements']))
        for i,e in enumerate(row['elements']):
            target_table.setItem(i,0,W.QTableWidgetItem(str(e)));target_table.setItem(i,1,W.QTableWidgetItem(row['label']))
    def native_choice(combo,kind,value):
        combo.clear();combo.addItem('속성 적용 때 새 객체 생성','')
        analysis=editor.owner.doc.getObject(draft['analysis_id'])
        if analysis:
            for obj in analysis.Group:
                if native_type(obj)==kind and not getattr(obj,'Suppressed',False):combo.addItem(obj.Label,obj.Name)
        if value and combo.findData(value)<0:combo.addItem('참조 상실된 저장 객체',value)
        combo.setCurrentIndex(max(0,combo.findData(value)))
    def load(index):
        state.update(row=index if index>=0 else None,loading=True)
        row=current();right.setEnabled(row is not None)
        if row is not None:
            for key,field in fields.items():field.setText(str(row[key]))
            native_choice(geometry,'Fem::ElementGeometry2D',row['geometry_id'])
            native_choice(pressure,'Fem::ConstraintPressure',row['pressure_id'])
        state['loading']=False;annotate()
    def changed(*_):
        if state['loading'] or current() is None:return
        row=current()
        for key,field in fields.items():row[key]=field.text()
        row['geometry_id']=geometry.currentData() or '';row['pressure_id']=pressure.currentData() or ''
        annotate()
    for field in fields.values():field.textChanged.connect(changed)
    geometry.currentIndexChanged.connect(changed);pressure.currentIndexChanged.connect(changed)
    def refill(index):
        state['loading']=True;regions.blockSignals(True);regions.clear()
        for row in working['regions']:regions.addItem(row['label'])
        regions.blockSignals(False);state['loading']=False
        regions.setCurrentRow(index);load(index)
    def add_row():
        used={r['id'] for r in working['regions']};n=1
        while 'R'+str(n) in used:n+=1
        row=uniform_region(working,region_id='R'+str(n),label='판재 영역 '+str(n))
        row.update(elements=[],face_refs=[],geometry_id='',pressure_id='')
        if row['orientation'] not in ('native','reversed'):row['orientation']='native'
        working['regions'].append(row);refill(len(working['regions'])-1)
    def remove_row():
        row=current()
        if row is None:return
        if row['geometry_id'] or row['pressure_id']:
            answer=W.QMessageBox.question(dialog,'영역 초안 삭제','이 삭제는 native 객체를 삭제하지 않습니다. '
                '기존 객체는 해석 트리에서 명시적으로 분리해야 다시 적용할 수 있습니다. 영역 초안을 삭제합니까?',W.QMessageBox.Yes|W.QMessageBox.No,W.QMessageBox.No)
            if answer!=W.QMessageBox.Yes:return
        del working['regions'][state['row']];refill(0 if working['regions'] else -1)
    def flip():
        row=current()
        if row is None:return
        proposal=reverse_region(working,row['id'],keep_physical_load=keep.isChecked())
        check_reversal_edit(original_rows,proposal['regions'])
        working['regions']=proposal['regions'];load(state['row'])
    def from_faces():
        row=current()
        if row is None:return
        chosen=selection(editor,draft['analysis_id']);row.update(chosen);annotate()
    def from_ids():
        row=current()
        if row is None:return
        _,nodes,elements=editor._mesh(working)
        rows=[(e,[sum(nodes[n][c] for n in elements[e][:4])/4 for c in range(3)]) for e in sorted(working['elements'])]
        chosen=choose_ids(W,C,dialog,rows,row['elements'],'셸 영역의 요소 선택')
        if chosen is not None:row.update(elements=chosen,face_refs=[]);annotate()
    def transfer():
        row=current()
        if row is None:return
        selected=set(row['elements'])
        for other in working['regions']:
            if other is not row and selected & set(other['elements']):
                other['elements']=[e for e in other['elements'] if e not in selected]
                # A CAD face no longer denotes the whole assigned FE subset.
                other['face_refs']=[]
        annotate()
    add.clicked.connect(safe(add_row));remove.clicked.connect(safe(remove_row));reverse.clicked.connect(safe(flip))
    pickface.clicked.connect(safe(from_faces));pickids.clicked.connect(safe(from_ids));move.clicked.connect(safe(transfer))
    regions.currentRowChanged.connect(load);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
    refill(0 if working['regions'] else -1)
    result=dialog.exec() if hasattr(dialog,'exec') else dialog.exec_()
    return deepcopy(working['regions']) if result==W.QDialog.Accepted else None
