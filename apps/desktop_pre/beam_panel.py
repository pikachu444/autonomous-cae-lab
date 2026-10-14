"""Contextual beam editing in the existing FreeCAD document and Qt dock.

Raw draft text and selected native references remain editable. Apply is an
explicit native transaction; a plot preview or selecting a row is not Apply.
"""
from copy import deepcopy
from caelab.storage import canonical_hash
from caelab.beam_model import validate_draft, number, default_draft
from .beam_visuals import section_view, qt_gui


def make_panel(W,C,editor,submit,*,Gui,on_run,on_results,on_runner,on_save):
    G=qt_gui()
    panel=W.QWidget();panel.setObjectName('BeamPanel');layout=W.QVBoxLayout(panel)
    layout.setContentsMargins(12,10,12,10);layout.setSpacing(8)
    available=set(G.QFontDatabase().families())
    for family in ('Malgun Gothic','맑은 고딕','Noto Sans CJK KR','Noto Sans KR'):
        if family in available:
            panel.setFont(G.QFont(family,10));break
    accent=panel.palette().highlight().color().name()
    panel.setStyleSheet(f'''
      #BeamPanel QLineEdit, #BeamPanel QComboBox {{ min-height: 26px; padding: 2px 5px; }}
      #BeamPanel QPushButton {{ min-height: 28px; padding: 2px 9px; }}
      #BeamPanel QLineEdit:focus, #BeamPanel QTableWidget:focus {{ border: 2px solid {accent}; }}
      #BeamPanel QLineEdit[beamError="true"] {{ border: 2px solid #b24537; }}
      #BeamPanel QPushButton[primary="true"] {{ font-weight: 600; border: 2px solid {accent}; }}
    ''')
    state={'analysis':None,'draft':None,'loading':False,'dirty':False,'can_freeze':False,'busy':False}
    fields={};refs={};end_tables=[];systems=[]
    top=W.QGridLayout();top.setColumnStretch(1,1)
    analysis=W.QComboBox();mesh=W.QComboBox()
    analysis.setAccessibleName('대상 해석');mesh.setAccessibleName('선 메시')
    top.addWidget(W.QLabel('해석'),0,0);top.addWidget(analysis,0,1)
    reload_button=W.QPushButton('저장본 읽기');top.addWidget(reload_button,0,2)
    top.addWidget(W.QLabel('선 메시'),1,0);top.addWidget(mesh,1,1)
    create=W.QPushButton('설정 만들기');top.addWidget(create,1,2)
    layout.addLayout(top)
    status=W.QLabel('선 메시와 빔 모서리를 선택하세요.');status.setWordWrap(True);layout.addWidget(status)
    tabs=W.QTabWidget();layout.addWidget(tabs,1)

    def button(text,fn):
        b=W.QPushButton(text);b.clicked.connect(fn);return b
    def safe(fn):
        def wrapped(*unused):
            try:fn()
            except Exception as exc:status.setText(str(exc))
        return wrapped
    def ask_discard():
        return not state['dirty'] or W.QMessageBox.question(panel,'미저장 수정','현재 화면의 수정을 취소하고 저장본을 읽겠습니까?',
            W.QMessageBox.Yes|W.QMessageBox.No,W.QMessageBox.No)==W.QMessageBox.Yes
    def update_buttons():
        ready=state['draft'] is not None and not state['busy']
        for b in (save_draft,apply_button,save_file):b.setEnabled(ready)
        run_button.setEnabled(ready and state['can_freeze'] and not state['dirty'])
        export_button.setEnabled(run_button.isEnabled())
        create.setEnabled(not state['busy'] and analysis.currentData() is not None)
        tabs.setEnabled(not state['busy']);analysis.setEnabled(not state['busy']);mesh.setEnabled(not state['busy'])
        for item in fields.values():item.setEnabled(ready)
        for index in range(1,tabs.count()):tabs.setTabEnabled(index,ready)
    def changed(*unused):
        if state['loading']:return
        if state['draft'] is None:
            status.setText('모서리와 선 메시를 확인한 뒤 설정 만들기를 누르세요.');return
        state['dirty']=True;state['can_freeze']=False
        status.setText('미적용 수정 — 초안 저장 또는 적용을 선택하세요.')
        update_preview();update_buttons()
    def pick(path,kind):
        selection=Gui.Selection.getSelectionEx(editor.owner.doc.Name)
        selected=[(s.Object,n) for s in selection for n in s.SubElementNames if n.startswith(kind)]
        if len(selected)!=1:
            raise ValueError('모델에서 '+('모서리 하나' if kind=='Edge' else '끝 꼭짓점 하나')+'를 선택하세요.')
        obj,name=selected[0]
        if obj.Document is not editor.owner.doc:raise ValueError('같은 문서의 형상을 선택하세요.')
        refs[path][1]={'object':obj.Name,'subelement':name};refs[path][0].setText(obj.Label+' / '+name)
        changed()
    def reference_row(form,label,path,kind):
        display=W.QLineEdit();display.setReadOnly(True);display.setPlaceholderText('모델에서 선택')
        display.setAccessibleName(label+' 대상')
        row=W.QWidget();grid=W.QHBoxLayout(row);grid.setContentsMargins(0,0,0,0)
        grid.addWidget(display,1);grid.addWidget(button('선택 사용',safe(lambda:pick(path,kind))))
        refs[path]=[display,{'object':'','subelement':''}]
        form.addRow(label,row)
    def edit(form,label,path):
        item=W.QLineEdit();item.setAccessibleName(label);item.textEdited.connect(changed)
        fields[path]=item;form.addRow(label,item)
        return item
    section=W.QWidget();section_layout=W.QVBoxLayout(section)
    form=W.QFormLayout();form.setFieldGrowthPolicy(W.QFormLayout.AllNonFixedFieldsGrow)
    reference_row(form,'빔 모서리','edge','Edge')
    element_label=W.QLabel('B32R  ·  직사각 RECT  ·  선형 정적')
    form.addRow('요소',element_label)
    edit(form,'폭 [mm] — 1축','section.width_mm')
    edit(form,'높이 [mm] — 2축','section.height_mm')
    edit(form,'단면 회전 [°]','section.rotation_deg')
    edit(form,'탄성계수 [MPa]','material.young_MPa')
    edit(form,'포아송비','material.poisson')
    section_layout.addLayout(form)
    preview=section_view(W,C);section_layout.addWidget(preview,1)
    axis_label=W.QLabel('단면 방향은 입력 확인 탭에서 전체 좌표계로 확인합니다.');axis_label.setWordWrap(True)
    section_layout.addWidget(axis_label);tabs.addTab(section,'단면')

    end_page=W.QWidget();end_layout=W.QVBoxLayout(end_page)
    end_pick=W.QComboBox();end_pick.addItems(['끝 1','끝 2']);end_layout.addWidget(end_pick)
    end_stack=W.QStackedWidget();end_layout.addWidget(end_stack,1);end_pick.currentIndexChanged.connect(end_stack.setCurrentIndex)
    row_defs=[('force_N','힘 [N]'),('moment_Nmm','모멘트 [Nmm]'),
              ('translation_mm','지정 변위 [mm]'),('rotation_deg','지정 회전 [°]')]
    for ei in range(2):
        page=W.QWidget();vl=W.QVBoxLayout(page);form=W.QFormLayout()
        reference_row(form,'끝점',f'ends.{ei}.reference','Vertex')
        system=W.QComboBox();system.addItem('전체 좌표계','global');system.addItem('단면 좌표계','local')
        systems.append(system);form.addRow('성분 기준',system);vl.addLayout(form)
        table=W.QTableWidget(4,3);table.setVerticalHeaderLabels([r[1] for r in row_defs]);table.setHorizontalHeaderLabels(['X','Y','Z'])
        table.horizontalHeader().setSectionResizeMode(W.QHeaderView.Stretch)
        table.verticalHeader().setDefaultSectionSize(42)
        table.setMinimumHeight(220);table.setAlternatingRowColors(True)
        for r in range(4):
            for c in range(3):
                item=W.QTableWidgetItem('0' if r<2 else '')
                item.setToolTip('자유 구속은 빈칸. 입력 회전은 도(°), CalculiX 경계조건은 rad.')
                table.setItem(r,c,item)
        table.itemChanged.connect(changed);vl.addWidget(table)
        def system_changed(index,ei=ei):
            end_tables[ei].setHorizontalHeaderLabels(['X','Y','Z'] if systems[ei].currentData()=='global' else ['1축','2축','길이축'])
            changed()
        system.currentIndexChanged.connect(system_changed)
        end_tables.append(table)
        def set_constraint(fixed,ei=ei):
            for r in (2,3):
                for c in range(3):end_tables[ei].item(r,c).setText('0' if fixed else '')
            changed()
        controls=W.QHBoxLayout()
        controls.addWidget(button('끝 고정',lambda checked=False,ei=ei:set_constraint(True,ei)))
        controls.addWidget(button('구속 해제',lambda checked=False,ei=ei:set_constraint(False,ei)))
        vl.addLayout(controls);vl.addWidget(W.QLabel('구속의 빈칸은 자유입니다. 힘과 모멘트의 기준점은 선택 끝 절점입니다.'))
        vl.addStretch();end_stack.addWidget(page)
    tabs.addTab(end_page,'끝 조건')

    check_page=W.QWidget();cl=W.QVBoxLayout(check_page)
    axes_table=W.QTableWidget(3,3);axes_table.setVerticalHeaderLabels(['1축 (폭)','2축 (높이)','길이축'])
    axes_table.setHorizontalHeaderLabels(['전체 X','전체 Y','전체 Z'])
    axes_table.setEditTriggers(W.QAbstractItemView.NoEditTriggers);axes_table.horizontalHeader().setSectionResizeMode(W.QHeaderView.Stretch)
    axes_table.setMaximumHeight(165);cl.addWidget(axes_table)
    effective_table=W.QTableWidget(0,4);effective_table.setHorizontalHeaderLabels(['끝점 / 성분','전체 X','전체 Y','전체 Z'])
    effective_table.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
    effective_table.horizontalHeader().setSectionResizeMode(W.QHeaderView.ResizeToContents)
    effective_table.horizontalHeader().setStretchLastSection(True);cl.addWidget(effective_table,1)
    properties=W.QLabel('');properties.setWordWrap(True);cl.addWidget(properties)
    oblique=W.QCheckBox('비축정렬 진단 계산 허용 (검증 완료 아님)');oblique.toggled.connect(changed);cl.addWidget(oblique)
    errors=W.QListWidget();errors.setMaximumHeight(110);errors.setAccessibleName('수정할 설정');cl.addWidget(errors)
    repair=button('참조 다시 지정',safe(lambda:invoke('pre.beam.rebind',with_draft=True)))
    native_import=button('속성 불러오기',safe(lambda:invoke('pre.beam.import_properties')))
    tools=W.QHBoxLayout();tools.addWidget(repair);tools.addWidget(native_import);cl.addLayout(tools)
    tabs.addTab(check_page,'입력 확인')

    history_page=W.QWidget();hl=W.QVBoxLayout(history_page)
    history=W.QListWidget();hl.addWidget(history,1)
    hl.addWidget(button('계산 목록 열기',safe(lambda:on_runner(history.currentItem().data(C.Qt.UserRole) if history.currentItem() else None))))
    hl.addWidget(button('보존 결과 열기…',safe(on_results)))
    hl.addWidget(W.QLabel('결과를 열어도 재계산하지 않습니다. 실패한 계산의 입력과 로그도 남습니다.'))
    tabs.addTab(history_page,'이전 계산')
    footer=W.QGridLayout();footer.setHorizontalSpacing(8);footer.setVerticalSpacing(8)
    save_draft=button('초안 저장',safe(lambda:invoke('pre.beam.draft',with_draft=True)))
    apply_button=button('적용',safe(lambda:invoke('pre.beam.apply',with_draft=True)));apply_button.setProperty('primary',True)
    discard=button('수정 취소',safe(lambda:reload_state() if ask_discard() else None))
    export_button=button('입력 생성…',safe(lambda:on_run(state['analysis'],True)))
    run_button=button('계산 실행',safe(lambda:on_run(state['analysis'],False)));run_button.setProperty('primary',True)
    save_file=button('프로젝트 저장',safe(lambda:invoke('pre.beam.draft',with_draft=True,after=on_save)))
    for n,b in enumerate((save_draft,apply_button,discard,export_button,run_button,save_file)):
        footer.addWidget(b,n//3,n%3)
    layout.addLayout(footer)
    undo_row=W.QHBoxLayout()
    def undo_redo(op):
        if ask_discard():
            submit(op,{},on_done=lambda value:reload_state() if value.get('status')!='FAILED' else status.setText(value['error']['message']))
    undo_row.addWidget(button('되돌리기',safe(lambda:undo_redo('document.undo'))))
    undo_row.addWidget(button('다시 실행',safe(lambda:undo_redo('document.redo'))))
    layout.addLayout(undo_row)

    def read_draft():
        d=deepcopy(state['draft'] or default_draft(analysis.currentData() or '',mesh.currentData() or ''))
        d['mesh_id']=mesh.currentData() or ''
        for path,item in fields.items():
            group,key=path.split('.');d[group][key]=item.text()
        d['edge']=deepcopy(refs['edge'][1]);d['diagnostic_oblique']=oblique.isChecked()
        for i,table in enumerate(end_tables):
            d['ends'][i]['reference']=deepcopy(refs[f'ends.{i}.reference'][1])
            d['ends'][i]['system']=systems[i].currentData()
            for r,(key,_) in enumerate(row_defs):d['ends'][i][key]=[table.item(r,c).text() for c in range(3)]
        return d
    def update_preview():
        preview.set_section(*(fields['section.'+k].text() for k in ('width_mm','height_mm','rotation_deg')))
    def mark_errors(items):
        errors.clear()
        for item in fields.values():
            item.setProperty('beamError',False);item.style().unpolish(item);item.style().polish(item)
        for row in items:
            item=W.QListWidgetItem(row['message']);item.setData(C.Qt.UserRole,row['path']);errors.addItem(item)
            if row['path'] in fields:
                f=fields[row['path']];f.setProperty('beamError',True);f.style().unpolish(f);f.style().polish(f)
    def focus_error(item):
        path=item.data(C.Qt.UserRole)
        if path in fields:tabs.setCurrentIndex(0);fields[path].setFocus();fields[path].selectAll()
        elif path.startswith('ends.'):
            parts=path.split('.');ei=int(parts[1]);tabs.setCurrentIndex(1);end_pick.setCurrentIndex(ei)
            if len(parts)>3:
                row=next((j for j,(k,_) in enumerate(row_defs) if k==parts[2]),None)
                if row is not None:end_tables[ei].setCurrentCell(row,int(parts[3]));end_tables[ei].editItem(end_tables[ei].currentItem())
        elif path=='edge':tabs.setCurrentIndex(0);refs['edge'][0].setFocus()
    errors.itemClicked.connect(focus_error)
    def load_result(value):
        if value.get('status')=='FAILED':
            status.setText(value.get('error',{}).get('message','작업을 완료하지 못했습니다.'));return
        r=value.get('record')
        if r is None:return
        state.update(draft=deepcopy(r['draft']),dirty=False,loading=True,can_freeze=value.get('can_freeze',False))
        d=state['draft']
        for path,item in fields.items():
            group,key=path.split('.');item.setText(str(d[group][key]))
        for path in refs:
            ref=d['edge'] if path=='edge' else d['ends'][int(path.split('.')[1])]['reference']
            refs[path][1]=deepcopy(ref);obj=editor.owner.doc.getObject(ref.get('object',''))
            refs[path][0].setText((obj.Label if obj else ref.get('object',''))+' / '+ref.get('subelement',''))
        mi=mesh.findData(d['mesh_id'])
        if mi<0:
            mesh.addItem('찾을 수 없는 메시: '+d['mesh_id'],d['mesh_id']);mi=mesh.count()-1
        mesh.setCurrentIndex(mi)
        for i,table in enumerate(end_tables):
            systems[i].setCurrentIndex(systems[i].findData(d['ends'][i]['system']))
            for r,(key,_) in enumerate(row_defs):
                for c in range(3):table.item(r,c).setText('' if d['ends'][i][key][c] is None else str(d['ends'][i][key][c]))
        oblique.setChecked(d['diagnostic_oblique']);state['loading']=False
        mark_errors(value.get('errors',[]));preview_data=value.get('preview')
        axes_table.clearContents();effective_table.setRowCount(0)
        if preview_data:
            for row,key in enumerate(('local1','local2','tangent')):
                for col,number_value in enumerate(preview_data['axes'][key]):axes_table.setItem(row,col,W.QTableWidgetItem(f'{number_value:.7g}'))
            for ei,end in enumerate(preview_data['ends']):
                for key,title in [('global_force_N','힘 [N]'),('global_moment_Nmm','모멘트 [Nmm]'),
                                  ('global_translation_mm','변위 [mm]'),('global_rotation_rad','회전 [rad]')]:
                    row=effective_table.rowCount();effective_table.insertRow(row)
                    effective_table.setItem(row,0,W.QTableWidgetItem(f'끝 {ei+1} / {title}'))
                    for col,v in enumerate(end[key],1):effective_table.setItem(row,col,W.QTableWidgetItem('자유' if v is None else f'{v:.7g}'))
            p=preview_data['properties'];properties.setText(f"길이 {preview_data['length_mm']:g} mm   A {p['area_mm2']:g} mm²\nI₁ {p['I1_mm4']:.8g} mm⁴   I₂ {p['I2_mm4']:.8g} mm⁴")
        else:properties.setText('끝점과 단면을 지정하면 실제 입력 방향을 확인할 수 있습니다.')
        status.setText('적용됨 — 새 입력과 계산을 준비할 수 있습니다.' if state['can_freeze'] else '초안 — 수정할 설정을 확인하고 적용하세요.')
        history.clear()
        for row in editor.owner.project.descriptor().get('links',[]):
            jid=row.get('job_id')
            if jid:
                item=W.QListWidgetItem(row.get('label') or ('계산 '+jid));item.setData(C.Qt.UserRole,jid);history.addItem(item)
        update_preview();update_buttons()
    def reload_state():
        key=analysis.currentData()
        state['analysis']=key
        if key in editor._records():load_result(editor.inspect(key))
        else:
            state.update(draft=None,dirty=False,can_freeze=False,loading=True)
            defaults=default_draft(key or '',mesh.currentData() or '')
            for path,item in fields.items():
                group,name=path.split('.');item.setText(str(defaults[group][name]))
            for path in refs:
                refs[path][1]={'object':'','subelement':''};refs[path][0].clear()
            axes_table.clearContents();effective_table.setRowCount(0);errors.clear();history.clear()
            tabs.setCurrentIndex(0);state['loading']=False;update_preview()
            status.setText('모델에서 빔 모서리를 선택한 뒤 설정 만들기를 누르세요.');update_buttons()
    def invoke(op,with_draft=False,after=None):
        if state['draft'] is None:raise ValueError('먼저 빔 설정을 만드세요.')
        args={'analysis_id':state['analysis']}
        if with_draft:args['draft']=read_draft()
        if op in ('pre.beam.apply','pre.beam.rebind'):
            errors_now=validate_draft(args['draft'])
            if errors_now:
                mark_errors(errors_now);focus_error(errors.item(0));status.setText('입력을 수정하세요. 잘못된 초안도 저장할 수 있습니다.');return
        if op=='pre.beam.import_properties' and not ask_discard():return
        state['busy']=True;update_buttons()
        def done(value):
            state['busy']=False
            load_result(value);update_buttons()
            if value.get('status')!='FAILED' and after:after()
        try:submit(op,args,on_done=done)
        except Exception:
            state['busy']=False;update_buttons();raise
    def selection_changed():
        if state['loading']:return
        if not ask_discard():
            state['loading']=True;analysis.setCurrentIndex(analysis.findData(state['analysis']));state['loading']=False;return
        key=analysis.currentData();rows=editor.discover();state['loading']=True;mesh.clear()
        for row in rows:
            if row['id']==key:
                for m in row['meshes']:mesh.addItem(m['label'],m['id'])
        state['loading']=False;reload_state()
    def create_model():
        if not ask_discard():return
        args={'analysis_id':analysis.currentData(),'mesh_id':mesh.currentData(),'edge':deepcopy(refs['edge'][1])}
        state['busy']=True;update_buttons()
        def created(value):
            state['busy']=False;load_result(value);update_buttons()
        try:submit('pre.beam.create',args,on_done=created)
        except Exception:
            state['busy']=False;update_buttons();raise
    analysis.currentIndexChanged.connect(safe(selection_changed));mesh.currentIndexChanged.connect(changed)
    create.clicked.connect(safe(create_model));reload_button.clicked.connect(safe(lambda:reload_state() if ask_discard() else None))
    state['loading']=True
    for row in editor.discover():analysis.addItem(row['label'],row['id'])
    state['loading']=False
    selection_changed()
    def accept_saved_snapshot(snapshot,value):
        if read_draft()==snapshot:
            load_result(value)
        # Newer local edits remain dirty and are not overwritten by a delayed save.
    panel.pending_changes=lambda:state['dirty']
    panel.editor_token=lambda:canonical_hash(read_draft()) if state['dirty'] else None
    panel.pending_snapshot=lambda:deepcopy(read_draft()) if state['dirty'] else None
    panel.accept_saved_snapshot=accept_saved_snapshot
    panel.confirm_close=ask_discard
    panel.reload_beam=reload_state
    return panel
