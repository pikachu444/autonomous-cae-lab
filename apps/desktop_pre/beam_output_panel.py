"""Explicit beam output and piecewise section-axis controls for the native dock.

There is no execute callback. Values are merged into the host's own pending
snapshot, so a late save receipt cannot erase newer output/reference-point edits.
"""
from copy import deepcopy
from caelab.beam_output import DEFAULT


def make_widget(W,C,editor,draft_provider,on_changed):
    from .b13_selection_dialog import choose_ids
    from .shell_edit import native_type
    widget=W.QWidget();layout=W.QVBoxLayout(widget)
    enabled=W.QCheckBox('출력 설정과 지지 응답 사용');layout.addWidget(enabled)
    body=W.QWidget();form=W.QFormLayout(body);layout.addWidget(body)
    mode=W.QComboBox();mode.addItem('단면력 (기존 2D 출력)','section_forces')
    mode.addItem('별도 실행: 3D 원응력과 내부 적분점','raw_stress');form.addRow('이번 실행의 출력',mode)
    derived=W.QCheckBox('단면 변위의 유도 회전 (솔버 회전 자유도 아님)');form.addRow(derived)
    reference=[];refbox=W.QWidget();refs=W.QHBoxLayout(refbox);refs.setContentsMargins(0,0,0,0)
    for c in 'XYZ':
        field=W.QLineEdit('0');field.setAccessibleName('모멘트 기준점 '+c+' [mm]')
        refs.addWidget(W.QLabel(c));refs.addWidget(field);reference.append(field)
    form.addRow('전역 기준점 [mm]',refbox)
    supports=[]
    for i in range(2):
        row=W.QWidget();bar=W.QHBoxLayout(row);bar.setContentsMargins(0,0,0,0)
        active=W.QCheckBox('사용');name=W.QLineEdit('지지 집합 '+str(i+1));name.setAccessibleName('지지 집합 이름')
        ends=[W.QCheckBox('끝 1'),W.QCheckBox('끝 2')]
        for field in (active,name,*ends):bar.addWidget(field)
        form.addRow('지지 집합 '+str(i+1),row);supports.append((active,name,ends))
    axes_enabled=W.QCheckBox('요소별 단면 방향 사용 (직선 B32R / 전역 끝 조건)');layout.addWidget(axes_enabled)
    axes_box=W.QWidget();axes_layout=W.QVBoxLayout(axes_box);axes_layout.setContentsMargins(0,0,0,0);layout.addWidget(axes_box,1)
    table=W.QTableWidget(0,5);table.setHorizontalHeaderLabels(['영역 이름','회전 [°]','요소 집합','모델 방향 속성','대상 편집'])
    table.setEditTriggers(W.QAbstractItemView.NoEditTriggers);table.setAlternatingRowColors(True)
    table.horizontalHeader().setSectionResizeMode(W.QHeaderView.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True);table.setMinimumHeight(180);axes_layout.addWidget(table,1)
    actions=W.QHBoxLayout();add=W.QPushButton('방향 영역 추가');remove=W.QPushButton('선택 영역 삭제')
    actions.addWidget(add);actions.addWidget(remove);axes_layout.addLayout(actions)
    info=W.QLabel('단면력과 3D 응력은 서로 다른 실행입니다. 두 결과는 원 기계 입력이 같아도 실행 ID를 합치지 않습니다. '
        'RF 합/그 힘의 모멘트, 복원 응력의 traction 적분, native 구속 반력은 서로 다릅니다. '
        '전체 native 회전 DOF·MPC 구속 반력은 이 경로에서 제공하지 않습니다. 곡선 빔으로 일반화하지 않습니다. '
        'B32R/RECT 내부 출력은 50점입니다. ccx 2.22 원 소스의 COORD 경로에는 크기/분기 문제가 있어 '
        '설치 바이너리의 정상 출력은 아직 검증되지 않았습니다. COORD 불일치는 계산한 좌표로 대체하지 않고 거절합니다.')
    info.setWordWrap(True);layout.addWidget(info)
    info.setToolTip(info.text())
    info.setText('단면력과 3D 응력은 별도 실행입니다. 유도 회전, RF 합, 복원 응력 적분은 솔버 회전 자유도나 완전한 구속 반력이 아닙니다.\n'
        'B32R/RECT의 50점 원좌표는 실제 출력 검증 전이며, 불일치는 차단합니다.')
    error=W.QLabel();error.setWordWrap(True);layout.addWidget(error)
    state={'loading':True,'rows':[],'context':{}}
    def changed(*_):
        body.setEnabled(enabled.isChecked());axes_box.setEnabled(axes_enabled.isChecked())
        if not state['loading']:on_changed()
    def safe(fn):
        def call(*_):
            try:fn();error.clear()
            except Exception as exc:error.setText(str(exc))
        return call
    def axis_rows():
        rows=deepcopy(state['rows'])
        for i,row in enumerate(rows):
            row['label']=table.cellWidget(i,0).text()
            row['rotation_deg']=table.cellWidget(i,1).text()
            row['rotation_id']=table.cellWidget(i,3).currentData() or ''
        return rows
    def targets(i):
        d=draft_provider();rows=axis_rows();mesh=editor.owner.doc.getObject(d['mesh_id'])
        if mesh is None or not hasattr(mesh,'FemMesh'):raise ValueError('현재 해석의 native 선 메시가 없습니다.')
        candidates=[]
        for e in sorted(map(int,mesh.FemMesh.Edges)):
            conn=list(mesh.FemMesh.getElementNodes(e))
            if len(conn)!=3:raise ValueError('전체 참여 선 메시가 Seg3/B32R이어야 합니다.')
            points=[mesh.FemMesh.Nodes[n] for n in conn[:2]]
            candidates.append((e,[sum(float(getattr(p,c)) for p in points)/2 for c in 'xyz']))
        from .beam_axis_native import geometry_with_reference
        record=editor._get(d['analysis_id'])
        # Selection arrays belong to the stored reference until explicit Apply.
        # The picker displays current actual IDs and converts only by the exact
        # established bijection; a label collision alone is never a mapping.
        mapped={e:e for e,_ in candidates}
        if 'binding' in record:
            if 'axis_regions' in record['draft']:
                _,_,relation=geometry_with_reference(editor.owner,record)
            else:
                from .beam_native import geometry
                from .beam_mesh_binding import require_same_binding
                model,binding=geometry(editor.owner,record['draft'])
                relation=require_same_binding(record,model,binding)
            mapped=relation['elements']
        inverse={v:k for k,v in mapped.items()}
        chosen=choose_ids(W,C,widget,candidates,[mapped[e] for e in rows[i]['elements'] if e in mapped],'단면 방향 영역: 현재 native 요소 선택')
        if chosen is not None:chosen=[inverse[e] for e in chosen]
        if chosen is not None:
            rows[i]['elements']=chosen;fill_axes(rows);changed()
    def fill_axes(rows):
        prior=state['loading'];state['loading']=True;state['rows']=deepcopy(rows);table.setRowCount(len(rows))
        d=state['context'];analysis=editor.owner.doc.getObject(d.get('analysis_id',''))
        native=[o for o in getattr(analysis,'Group',[]) if native_type(o)=='Fem::ElementRotation1D' and not getattr(o,'Suppressed',False)
                and o.Name!=d.get('section',{}).get('rotation_id')]
        for i,row in enumerate(rows):
            name=W.QLineEdit(row['label']);angle=W.QLineEdit(row['rotation_deg'])
            name.setAccessibleName('단면 방향 영역 이름');angle.setAccessibleName('영역 단면 회전 [°]')
            for j,field in ((0,name),(1,angle)):
                table.setCellWidget(i,j,field);field.textChanged.connect(changed)
            table.setItem(i,2,W.QTableWidgetItem(', '.join(map(str,row['elements'])) or '요소 미선택'))
            choice=W.QComboBox();choice.addItem('적용 때 새 방향 객체 생성','')
            for obj in native:choice.addItem(obj.Label,obj.Name)
            if row['rotation_id'] and choice.findData(row['rotation_id'])<0:choice.addItem('참조 상실된 저장 객체',row['rotation_id'])
            choice.setCurrentIndex(max(0,choice.findData(row['rotation_id'])));table.setCellWidget(i,3,choice)
            choice.currentIndexChanged.connect(changed)
            pick=W.QPushButton('실제 요소 선택…');pick.clicked.connect(safe(lambda i=i:targets(i)));table.setCellWidget(i,4,pick)
        state['loading']=prior
    def add_row():
        rows=axis_rows();used={r['id'] for r in rows};n=1
        while 'R'+str(n) in used:n+=1
        rows.append({'id':'R'+str(n),'label':'방향 영역 '+str(n),'rotation_deg':'0','rotation_id':'','elements':[]})
        fill_axes(rows);table.setCurrentCell(len(rows)-1,0);changed()
    def remove_row():
        rows=axis_rows();i=table.currentRow()
        if i<0:return
        if rows[i]['rotation_id']:
            response=W.QMessageBox.question(widget,'방향 영역 초안 삭제','native 방향 객체는 삭제하지 않습니다. 해석 트리에서 '
                '그 객체를 명시적으로 분리해야 다시 적용할 수 있습니다. 초안 행을 삭제합니까?',W.QMessageBox.Yes|W.QMessageBox.No,W.QMessageBox.No)
            if response!=W.QMessageBox.Yes:return
        del rows[i];fill_axes(rows);changed()
    def set_draft(d):
        state['loading']=True;state['context']=deepcopy(d);out=deepcopy(d.get('output',DEFAULT));enabled.setChecked('output' in d)
        if mode.findData(out['mode'])<0:mode.addItem('지원하지 않는 저장 출력 모드',out['mode'])
        mode.setCurrentIndex(mode.findData(out['mode']));derived.setChecked(out['derived_rotation'])
        for field,value in zip(reference,out['reference_mm']):field.setText(str(value))
        for i,(active,name,ends) in enumerate(supports):
            present=i<len(out['supports']);row=out['supports'][i] if present else {'label':'지지 집합 '+str(i+1),'ends':[]}
            active.setChecked(present);name.setText(row['label'])
            for j,field in enumerate(ends):field.setChecked(j in row['ends'])
        axes_enabled.setChecked('axis_regions' in d);fill_axes(d.get('axis_regions',[]))
        body.setEnabled(enabled.isChecked());axes_box.setEnabled(axes_enabled.isChecked());state['loading']=False
    def merge_draft(d):
        # Every value is read directly from its editor, including focused raw text.
        if enabled.isChecked():
            d['output']={'mode':mode.currentData(),'derived_rotation':derived.isChecked(),
                         'reference_mm':[field.text() for field in reference],
                         'supports':[{'label':name.text(),'ends':[i for i,field in enumerate(ends) if field.isChecked()]}
                                     for active,name,ends in supports if active.isChecked()]}
        else:d.pop('output',None)
        if axes_enabled.isChecked():d['axis_regions']=axis_rows()
        else:d.pop('axis_regions',None)
        return d
    for field in (enabled,derived,axes_enabled,*[v for row in supports for v in (row[0],*row[2])]):field.toggled.connect(changed)
    mode.currentIndexChanged.connect(changed)
    for field in (*reference,*[row[1] for row in supports]):field.textChanged.connect(changed)
    add.clicked.connect(safe(add_row));remove.clicked.connect(safe(remove_row))
    widget.set_draft=set_draft;widget.merge_draft=merge_draft
    # Exposed only for focused Qt regressions and keyboard accessibility tests.
    widget.reference_fields=reference;widget.output_enabled=enabled;widget.mode_choice=mode
    widget.axes_enabled=axes_enabled;widget.axes_table=table
    set_draft({});return widget
