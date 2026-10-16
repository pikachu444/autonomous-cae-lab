"""Object-first laminate table in the existing native FreeCAD dock."""
from copy import deepcopy
import uuid

from caelab.composite_shell import (validate,move_ply,reverse_region,ORTHOTROPIC,ISOTROPIC,number)
from caelab.shell_model import digest


def make_panel(W,C,editor,submit,*,on_save,on_freeze,on_run,on_simulation,on_post,on_results):
    panel=W.QWidget();panel.setObjectName('CompositeShellPanel')
    layout=W.QVBoxLayout(panel);layout.setContentsMargins(10,10,10,10);layout.setSpacing(8)
    panel.setStyleSheet('''#CompositeShellPanel QLineEdit, #CompositeShellPanel QComboBox { min-height: 25px; }
      #CompositeShellPanel QPushButton { min-height: 28px; padding: 2px 9px; }
      #CompositeShellPanel QTableWidget { gridline-color: #d9e0e7; }
      #CompositeShellPanel QPushButton[primary="true"] { background: #245f9e; color: white; font-weight: 600; }
      #CompositeShellPanel QPushButton[primary="true"]:disabled { background: #e9eef4; color: #667483; }
      #CompositeShellPanel QLineEdit:focus, #CompositeShellPanel QTableWidget:focus { border: 2px solid #245f9e; }''')
    from .beam_visuals import qt_gui
    G=qt_gui();available=set(G.QFontDatabase().families())
    for name in ('Malgun Gothic','맑은 고딕','Noto Sans KR'):
        if name in available:panel.setFont(G.QFont(name,10));break
    state={'draft':None,'loading':False,'dirty':False,'busy':False,'can_freeze':False,'undo':[],'redo':[],'epoch':0}
    fields={};catalog=[]
    top=W.QGridLayout();analysis=W.QComboBox();mesh=W.QComboBox();solver=W.QComboBox()
    for i,(text,widget) in enumerate((('해석',analysis),('셸 메시',mesh),('솔버',solver))):
        top.addWidget(W.QLabel(text),i,0);top.addWidget(widget,i,1)
    top.setColumnStretch(1,1);layout.addLayout(top)
    start=W.QPushButton('적층 설정 만들기');reload_button=W.QPushButton('저장본 읽기')
    row=W.QHBoxLayout();row.addWidget(start);row.addWidget(reload_button);row.addStretch();layout.addLayout(row)
    splitter=W.QSplitter(C.Qt.Horizontal);regions=W.QListWidget();regions.setMinimumWidth(125)
    left=W.QWidget();ll=W.QVBoxLayout(left);ll.setContentsMargins(0,0,0,0);ll.addWidget(W.QLabel('참여 영역'));ll.addWidget(regions)
    add_region=W.QPushButton('선택한 면 추가');ll.addWidget(add_region);remove_region=W.QPushButton('영역 제외');ll.addWidget(remove_region)
    splitter.addWidget(left);right=W.QWidget();rl=W.QVBoxLayout(right);rl.setContentsMargins(0,0,0,0)
    scope=W.QLabel('native 화면에서 셸 면이나 메시를 선택하세요.');scope.setWordWrap(True);rl.addWidget(scope)
    order=W.QLabel('위쪽 +법선 → 아래쪽 −법선');order.setStyleSheet('font-weight: 600;');rl.addWidget(order)
    table=W.QTableWidget(0,4);table.setHorizontalHeaderLabels(['층','재료','두께 [mm]','각도 [°]'])
    table.setSelectionBehavior(W.QAbstractItemView.SelectRows);table.setSelectionMode(W.QAbstractItemView.SingleSelection)
    table.horizontalHeader().setSectionResizeMode(1,W.QHeaderView.Stretch)
    for column in (0,2,3):table.horizontalHeader().setSectionResizeMode(column,W.QHeaderView.ResizeToContents)
    table.setAccessibleName('위에서 아래로 적층 순서');rl.addWidget(table,1)
    tools=W.QHBoxLayout();buttons={}
    for key,text in (('add','층 추가'),('delete','층 삭제'),('up','위로'),('down','아래로'),('material','재료 편집')):
        buttons[key]=W.QPushButton(text);tools.addWidget(buttons[key])
    rl.addLayout(tools);total=W.QLabel('총두께 —');rl.addWidget(total)
    grid=W.QGridLayout();normal=W.QComboBox()
    normal.addItem('법선 선택',None);normal.addItem('원 요소 법선','native');normal.addItem('반대 법선','reversed')
    grid.addWidget(W.QLabel('층의 위쪽 방향'),0,0);grid.addWidget(normal,0,1,1,3)
    flip=W.QPushButton('법선 반전');grid.addWidget(flip,0,4)
    axisbox=W.QWidget();axisrow=W.QHBoxLayout(axisbox);axisrow.setContentsMargins(0,0,0,0)
    for key in ('x','y','z'):
        field=W.QLineEdit();field.setAccessibleName('국부 기준축 '+key.upper());fields[key]=field
        axisrow.addWidget(W.QLabel(key.upper()));axisrow.addWidget(field)
    grid.addWidget(W.QLabel('국부 1축 기준'),1,0);grid.addWidget(axisbox,1,1,1,4)
    for i,(key,label) in enumerate((('offset','기준면 위치 [두께비]'),('pressure_MPa','압력 [MPa]')),2):
        field=W.QLineEdit();fields[key]=field;grid.addWidget(W.QLabel(label),i,0);grid.addWidget(field,i,1,1,4)
    rl.addLayout(grid);splitter.addWidget(right);splitter.setStretchFactor(1,1);splitter.setSizes([170,540]);layout.addWidget(splitter,1)
    status=W.QLabel('S8R 적층 셸. 기존 S8 해석과 별도로 설정합니다.');status.setWordWrap(True);layout.addWidget(status)
    actions=W.QHBoxLayout();undo=W.QPushButton('되돌리기');redo=W.QPushButton('되살리기')
    save_draft=W.QPushButton('초안 저장');apply_button=W.QPushButton('속성 적용');apply_button.setProperty('primary',True)
    save_file=W.QPushButton('파일 저장')
    for b in (undo,redo,save_draft,apply_button,save_file):actions.addWidget(b)
    layout.addLayout(actions)
    work=W.QHBoxLayout();calculation={}
    for key,text in (('freeze','입력 준비'),('simulation','해석 창에서 열기'),('run','계산'),('post','3D 결과'),('results','층별 응력')):
        calculation[key]=W.QPushButton(text);work.addWidget(calculation[key])
    layout.addLayout(work)

    def safe(fn):
        def call(*unused):
            try:fn()
            except Exception as error:status.setText(str(error));state['busy']=False;enabled()
        return call
    def current():
        i=regions.currentRow()
        return state['draft']['regions'][i] if state['draft'] is not None and 0<=i<len(state['draft']['regions']) else None
    def remember():
        state['undo'].append(deepcopy(state['draft']));state['undo']=state['undo'][-100:];state['redo'].clear()
    def changed(*unused):
        if state['loading'] or current() is None:return
        remember();region=current()
        for i,ply in enumerate(region['plies']):
            ply['material_id']=table.cellWidget(i,1).currentData()
            ply['thickness_mm']=table.item(i,2).text();ply['angle_deg']=table.item(i,3).text()
        region['axis']=[fields[c].text() for c in 'xyz']
        for key in ('offset','pressure_MPa'):region[key]=fields[key].text()
        # An already declared normal changes only through the coupled reversal action.
        if not region['orientation']:
            region['orientation']=normal.currentData() or ''
            normal.setEnabled(not bool(region['orientation']))
        state['dirty']=True;state['can_freeze']=False;check();enabled()
    def check():
        if state['draft'] is None:return
        errors,_=validate(state['draft']);status.setText(errors[0]['message'] if errors else '층 조건을 확인했습니다. 속성 적용 후 입력을 준비하세요.')
        try:total.setText('총두께 '+format(sum(number(p['thickness_mm']) for p in current()['plies']),'.8g')+' mm')
        except (ValueError,TypeError,KeyError):total.setText('총두께 —')
    def enabled():
        ready=state['draft'] is not None and not state['busy']
        for widget in (start,reload_button,analysis,mesh,solver):widget.setEnabled(not state['busy'])
        for b in (add_region,remove_region,save_draft,apply_button,save_file,*buttons.values(),flip):b.setEnabled(ready)
        table.setEnabled(ready);undo.setEnabled(ready and bool(state['undo']));redo.setEnabled(ready and bool(state['redo']))
        calculation['freeze'].setEnabled(ready and state['can_freeze'] and not state['dirty'])
        for key in ('simulation','run'):calculation[key].setEnabled(ready and bool(getattr(panel,'prepared',None)) and not state['dirty'])
        for key in ('post','results'):calculation[key].setEnabled(ready)
    def show_region():
        state['loading']=True;region=current();table.setRowCount(0)
        if region:
            scope.setText(region.get('label','적층 영역')+f' / 면 {sum(len(r["subelements"]) for r in region["face_refs"])}개, 요소 {len(region["elements"])}개')
            table.setRowCount(len(region['plies']))
            for i,ply in enumerate(region['plies']):
                item=W.QTableWidgetItem(str(i+1));item.setFlags(item.flags() & ~C.Qt.ItemIsEditable);table.setItem(i,0,item)
                combo=W.QComboBox();combo.addItem('재료 선택',None)
                for material in catalog:combo.addItem(material['label'],material['id'])
                combo.setCurrentIndex(max(0,combo.findData(ply.get('material_id'))));table.setCellWidget(i,1,combo)
                combo.currentIndexChanged.connect(changed)
                table.setItem(i,2,W.QTableWidgetItem(ply['thickness_mm']));table.setItem(i,3,W.QTableWidgetItem(ply['angle_deg']))
            normal.setCurrentIndex(max(0,normal.findData(region['orientation'])));normal.setEnabled(not bool(region['orientation']))
            for c,v in zip('xyz',region['axis']):fields[c].setText(v)
            for key in ('offset','pressure_MPa'):fields[key].setText(region[key])
        state['loading']=False;check();enabled()
    def draw():
        selected=max(0,regions.currentRow());state['loading']=True;regions.clear()
        if state['draft']:
            for row in state['draft']['regions']:regions.addItem(row.get('label','적층 영역'))
        regions.setCurrentRow(min(selected,regions.count()-1));state['loading']=False;show_region()
    def accept(value,captured=None):
        state['busy']=False
        if value.get('status')=='FAILED':raise ValueError(value.get('error',{}).get('message','작업을 완료하지 못했습니다.'))
        if captured is not None and state['draft'] is not None and digest(state['draft'])!=digest(captured):
            status.setText('응답 뒤의 새 편집을 유지했습니다. 현재 편집을 다시 저장하세요.');enabled();return
        state['draft']=deepcopy(value['draft']);state['dirty']=False;state['can_freeze']=value['can_freeze']
        for widget,key in ((analysis,'analysis_id'),(mesh,'mesh_id'),(solver,'solver_id')):
            widget.blockSignals(True);widget.setCurrentIndex(widget.findData(state['draft'][key]));widget.blockSignals(False)
        draw()
    def send(operation,args,callback):
        state['busy']=True;enabled();epoch=state['epoch']
        def done(value):
            if epoch!=state['epoch']:return
            safe(lambda:callback(value))()
        return submit(operation,args,on_done=done)
    def save_then(callback=None):
        snapshot=deepcopy(state['draft'])
        def done(value):
            accept(value,snapshot)
            if not state['dirty'] and callback:callback()
        send('pre.composite.draft',{'analysis_id':snapshot['analysis_id'],'draft':snapshot},done)
    def create():
        if state['dirty'] and W.QMessageBox.question(panel,'미저장 수정','현재 편집을 취소하고 다른 설정을 여시겠습니까?',W.QMessageBox.Yes|W.QMessageBox.No,W.QMessageBox.No)!=W.QMessageBox.Yes:return
        state['epoch']+=1;state['undo'].clear();state['redo'].clear();panel.prepared=None
        send('pre.composite.begin',{'analysis_id':analysis.currentData(),'mesh_id':mesh.currentData(),'solver_id':solver.currentData()},accept)
    def reload():
        if state['dirty'] and W.QMessageBox.question(panel,'미저장 수정','현재 편집을 버리고 저장본을 읽으시겠습니까?',W.QMessageBox.Yes|W.QMessageBox.No,W.QMessageBox.No)!=W.QMessageBox.Yes:return
        state['epoch']+=1;state['undo'].clear();state['redo'].clear();panel.prepared=None
        accept(editor.inspect(analysis.currentData()))
    def select_analysis(*unused):
        if state['loading'] or state['draft'] is None:return
        if analysis.currentData()==state['draft']['analysis_id']:return
        if state['dirty'] and W.QMessageBox.question(panel,'미저장 수정','현재 편집을 버리고 다른 해석을 선택하시겠습니까?',W.QMessageBox.Yes|W.QMessageBox.No,W.QMessageBox.No)!=W.QMessageBox.Yes:
            analysis.blockSignals(True);analysis.setCurrentIndex(analysis.findData(state['draft']['analysis_id']));analysis.blockSignals(False);return
        state['epoch']+=1;state['draft']=None;state['undo'].clear();state['redo'].clear();state['dirty']=False;state['can_freeze']=False;panel.prepared=None;draw()
    def add():
        save_then(lambda:send('pre.composite.add_region',{'analysis_id':state['draft']['analysis_id'],'label':f'적층 영역 {regions.count()+1}'},accept))
    def mutate(fn):
        if current() is None:return
        remember();fn();state['dirty']=True;state['can_freeze']=False;panel.prepared=None;draw()
    def add_ply():
        mutate(lambda:current()['plies'].append({'id':'P'+uuid.uuid4().hex,'material_id':None,'thickness_mm':'0.5','angle_deg':'0'}))
    def delete_ply():
        i=table.currentRow()
        if i>=0:mutate(lambda:current()['plies'].pop(i))
    def move(delta):
        i=table.currentRow()
        if i<0 or not 0<=i+delta<len(current()['plies']):return
        rid=current()['id'];pid=current()['plies'][i]['id']
        def update():state['draft']=move_ply(state['draft'],rid,pid,delta)
        mutate(update);table.selectRow(i+delta)
    def reverse():
        rid=current()['id']
        def update():state['draft']=reverse_region(state['draft'],rid)
        mutate(update)
    def history(reverse=False):
        source=state['redo'] if reverse else state['undo'];target=state['undo'] if reverse else state['redo']
        if source:target.append(deepcopy(state['draft']));state['draft']=source.pop();state['dirty']=True;state['can_freeze']=False;panel.prepared=None;draw()
    def edit_material():
        i=table.currentRow()
        if i<0:raise ValueError('재료를 편집할 층을 선택하세요.')
        mid=current()['plies'][i].get('material_id')
        if not mid:raise ValueError('FEM의 원 재료를 선택하세요. 재료가 없으면 FEM에서 먼저 추가하세요.')
        original=state['draft']['materials'][mid];dialog=W.QDialog(panel);dialog.setWindowTitle('층 재료');dialog.resize(430,440)
        form=W.QVBoxLayout(dialog);law=W.QComboBox();law.addItem('등방 선형 탄성','isotropic_linear');law.addItem('직교이방성 선형 탄성','orthotropic_linear')
        law.setCurrentIndex(law.findData(original['law']));form.addWidget(law)
        inputs=W.QTableWidget(0,2);inputs.setHorizontalHeaderLabels(['재료 상수','입력값']);inputs.horizontalHeader().setSectionResizeMode(1,W.QHeaderView.Stretch);form.addWidget(inputs)
        raw=deepcopy(original['constants'])
        def rebuild():
            for j in range(inputs.rowCount()):raw[inputs.item(j,0).data(C.Qt.UserRole)]=inputs.item(j,1).text()
            names=ORTHOTROPIC if law.currentData()=='orthotropic_linear' else ISOTROPIC;inputs.setRowCount(len(names))
            for j,name in enumerate(names):
                label=name.replace('_MPa',' [MPa]').replace('nu','ν');item=W.QTableWidgetItem(label);item.setData(C.Qt.UserRole,name);item.setFlags(item.flags() & ~C.Qt.ItemIsEditable)
                inputs.setItem(j,0,item);inputs.setItem(j,1,W.QTableWidgetItem(raw.get(name,'')))
        rebuild();law.currentIndexChanged.connect(rebuild)
        box=W.QDialogButtonBox(W.QDialogButtonBox.Ok|W.QDialogButtonBox.Cancel);box.accepted.connect(dialog.accept);box.rejected.connect(dialog.reject);form.addWidget(box)
        if (dialog.exec() if hasattr(dialog,'exec') else dialog.exec_())!=W.QDialog.Accepted:return
        constants={inputs.item(j,0).data(C.Qt.UserRole):inputs.item(j,1).text() for j in range(inputs.rowCount())}
        remember();state['draft']['materials'][mid]={**original,'law':law.currentData(),'constants':constants};state['dirty']=True;state['can_freeze']=False;panel.prepared=None;check();enabled()
    table.cellChanged.connect(changed)
    for field in fields.values():field.textEdited.connect(changed)
    normal.currentIndexChanged.connect(changed);regions.currentRowChanged.connect(lambda *_:show_region())
    start.clicked.connect(safe(create));reload_button.clicked.connect(safe(reload));analysis.currentIndexChanged.connect(safe(select_analysis))
    add_region.clicked.connect(safe(add));remove_region.clicked.connect(safe(lambda:mutate(lambda:state['draft']['regions'].pop(regions.currentRow()))))
    buttons['add'].clicked.connect(safe(add_ply));buttons['delete'].clicked.connect(safe(delete_ply));buttons['up'].clicked.connect(safe(lambda:move(-1)));buttons['down'].clicked.connect(safe(lambda:move(1)));buttons['material'].clicked.connect(safe(edit_material));flip.clicked.connect(safe(reverse))
    undo.clicked.connect(safe(history));redo.clicked.connect(safe(lambda:history(True)))
    save_draft.clicked.connect(safe(save_then));apply_button.clicked.connect(safe(lambda:save_then(lambda:send('pre.composite.apply',{'analysis_id':state['draft']['analysis_id']},accept))))
    save_file.clicked.connect(safe(lambda:save_then(on_save)))
    for key,fn in (('freeze',on_freeze),('run',on_run),('simulation',on_simulation),('post',on_post),('results',on_results)):
        calculation[key].clicked.connect(safe(fn))
    available=editor.inspect();catalog[:]=available['materials']
    for widget,key in ((analysis,'analyses'),(mesh,'meshes'),(solver,'solvers')):
        for row in available[key]:widget.addItem(row['label'],row['id'])
    panel.prepared=None;panel.composite_state=state;panel.composite_table=table;panel.composite_regions=regions
    panel.pending_changes=lambda:state['dirty'];panel.inspect_result=accept;panel.current_draft=lambda:deepcopy(state['draft']);panel.refresh=draw
    panel.set_status=status.setText;panel.update_enabled=enabled;panel.send=send;panel.save_then=save_then;enabled()
    return panel
