"""Read-only native Qt worksheets for sealed S8/B32R observations.

Every table has one location/recovery meaning. IPs are not a point measurement,
section fits are not native DOFs, and stress traction is not discrete reaction.
Opening a worksheet never imports FreeCAD or launches a process.
"""
from copy import deepcopy
from pathlib import Path
import csv
import hashlib
import io

_WINDOWS=[]
_TENSORS=['XX','YY','ZZ','XY','YZ','ZX']
_LOCAL=['11','22','33','12','23','31']


def _get(rows,key):
    return rows[key] if key in rows else rows.get(str(key))


def beam_tables(saved,index=0,*,quantity='S',local=False):
    from caelab.beam_output import axes_for
    from caelab.adapters.shell_results import rotate_tensor
    observed=saved['observed'];model=saved['model']
    if not observed or not observed['frames']:return {}
    if observed.get('output_mode')!='raw_stress':raise ValueError('별도 3D 원응력 실행을 선택하세요.')
    frame=observed['frames'][index];time=frame['static']['load_parameter']
    label={'S':'STRESS','E':'TOSTRAIN','U':'DISP','RF':'FORC'}[quantity]
    units={'S':'MPa','E':'1','U':'mm','RF':'N'}[quantity]
    components=(_LOCAL if local else _TENSORS) if quantity in ('S','E') else ['X','Y','Z']
    def values(v,e):
        return rotate_tensor(v,[axes_for(model,e)[k] for k in ('local1','local2','tangent')]) if local and quantity in ('S','E') else list(v)
    surface=[]
    for elem,entry in sorted(observed['expansion'].items(),key=lambda r:int(r[0])):
        for n in entry['expanded']:
            v=_get(frame['native_fields'].get(label,{}),n)
            if v is None:continue
            surface.append([int(elem),n,*_get(observed['coordinates_mm'],n),*values(v,int(elem))])
    ips=[]
    for row in observed['internal']['rows']:
        if row['load_parameter']!=time or quantity not in row:continue
        ips.append([row['element_id'],row['integration_point'],*row.get('COORD',{}).get('values',[None]*3),
                    *values(row[quantity]['values'],row['element_id']),row[quantity].get('source_line')])
    fits=[[r['element_id'],r['beam_node_id'],{'start':'시작','middle':'중간','end':'끝'}[r['station_kind']],
           *r['centroid_mm'],*r['value_rad'],r['fit_rms_mm'],r['fit_max_mm']] for r in frame['derived_rotations']]
    supports=[]
    for group in frame['supports']:
        for key,name in (('native_RF_sum','원 RF 합 / 원 RF의 모멘트'),('stress_traction','복원 응력 traction 적분')):
            row=group[key]
            supports.append([group['label'],name,*group['reference_mm'],
                *row.get('force_N',[None]*3),*row.get('moment_Nmm',[None]*3),row.get('status','관측/유도값')])
    basis='선언 요소 축 변환 — native IP 재료축 아님' if local and quantity in ('S','E') else '전체 좌표계'
    return {
        '확장 절점':(['원 요소','확장 절점','X [mm]','Y [mm]','Z [mm]',*[quantity+c+' ['+units+']' for c in components]],surface,
                  basis+' / '+('FRD 복원·평균 응력/변형률' if quantity in ('S','E') else '원 확장 절점 관측값')),
        '내부 적분점':(['원 요소','적분점','COORD X [mm]','COORD Y [mm]','COORD Z [mm]',*[quantity+c+' ['+units+']' for c in components],'DAT 원행'],ips,
                    basis+' / 실제 내부 Gauss 관측 / CELLS / 점 보간 측정 미지원'),
        '유도 회전':(['원 요소','원 빔 절점','단면 위치','중심 X [mm]','중심 Y [mm]','중심 Z [mm]',
                    'θX [rad]','θY [rad]','θZ [rad]','fit RMS [mm]','fit 최대 잔차 [mm]'],fits,
                   '원 단면 U의 등가중 최소제곱 강체-fit. 미소 회전 가정. native 회전 DOF가 아닙니다.'),
        '지지 응답':(['지지 집합','물리량 정의','r0 X [mm]','r0 Y [mm]','r0 Z [mm]',
                    'FX [N]','FY [N]','FZ [N]','MX [Nmm]','MY [Nmm]','MZ [Nmm]','관측 상태'],supports,
                  'RF 외력/반력 혼합과 MPC 한계를 보존합니다. 응력 적분은 복원값 추정이며, 전체 이산 구속 반력이 아닙니다.')}


def shell_tables(checked,index=0,*,quantity='S',local=False):
    from caelab.adapters.shell_deck import build
    from caelab.adapters.shell_results import rotate_tensor
    data=checked['data'];frames=data['surface']['frames']
    if not frames:return {}
    frame=frames[index];time=frame['load_parameter'];_,mesh=build(data['model'])
    label={'S':'STRESS','E':'TOSTRAIN','U':'DISP'}[quantity];units={'S':'MPa','E':'1','U':'mm'}[quantity]
    components=(_LOCAL if local else _TENSORS) if quantity in ('S','E') else ['X','Y','Z']
    def values(v,e):return rotate_tensor(v,mesh['axes'][e]) if local and quantity in ('S','E') else list(v)
    surface=[]
    for loc in data['surface']['locations']:
        v=_get(frame['fields'].get(label,{}),loc['expanded_node_id'])
        if v is None:continue
        surface.append([loc.get('region',{}).get('label','단일 영역'),loc['element_id'],
            '상면' if loc['side']=='top' else '하면',loc['shell_node_id'],loc['expanded_node_id'],
            *loc['position_mm'],*values(v,loc['element_id'])])
    ips=[]
    for row in data['internal']['rows']:
        if row['load_parameter']!=time or quantity not in row:continue
        ips.append([row['element_id'],row['integration_point'],*row.get('COORD',{}).get('values',[None]*3),
                    *values(row[quantity]['values'],row['element_id']),row[quantity].get('source_line')])
    basis='요소 중심의 사용자 기저 변환 — native IP 재료축 아님' if local and quantity in ('S','E') else '전체 좌표계'
    return {
        '상·하면 복원값':(['영역','원 요소','면','원 셸 절점','확장 절점','X [mm]','Y [mm]','Z [mm]',
                         *[quantity+c+' ['+units+']' for c in components]],surface,
                        basis+' / 실제 확장 절점 / 응력·변형률은 native 복원·평균값이며 표면 IP가 아닙니다.'),
        '내부 적분점':(['원 요소','적분점','COORD X [mm]','COORD Y [mm]','COORD Z [mm]',
                     *[quantity+c+' ['+units+']' for c in components],'DAT 원행'],ips,
                    basis+' / DAT 내부 Gauss S/E/COORD / 해당 프레임에 원 관측이 없으면 값 없음')}


def export_table(path, *, headers, rows, provenance):
    """Export one already checked observation table with a hash-bound sidecar.

    This is a table export, not a replacement Post store or a solver result.
    Missing observations remain empty CSV fields, explicitly declared below.
    A sidecar publication error is surfaced; a stale sidecar cannot validate
    different CSV bytes because its digest is checked by the consumer.
    """
    from caelab.storage import save_json
    payload=io.StringIO(newline='');writer=csv.writer(payload)
    writer.writerow(headers)
    writer.writerows([['' if v is None else v for v in row] for row in rows])
    raw=payload.getvalue().encode('utf-8-sig')
    path=Path(path)
    record=deepcopy(provenance)
    record.update(table_csv={'name':path.name,'bytes':len(raw),
                             'sha256':hashlib.sha256(raw).hexdigest()},
                  headers=list(headers),row_count=len(rows),
                  missing_value_encoding='empty field; not zero',
                  artifact_role='exported observation table; not native solver output')
    path.write_bytes(raw)
    save_json(path.with_name(path.name+'.provenance.json'),record)
    return record


def table_export_metadata(name,quantity,local):
    """Describe the table's actual values; unrelated field controls confer no meaning."""
    if name=='유도 회전':
        return {'quantity':'derived_rotation','units':'rad','coordinate_frame':'global',
            'display_basis':'전체 좌표계','location':'beam_cross_section',
            'recovery':'equal_weight_small_rigid_fit','native_generalized_rotation':False}
    if name=='지지 응답':
        return {'quantity':'support_observations','units':{'force':'N','moment':'Nmm','reference':'mm'},
            'coordinate_frame':'global','display_basis':'전체 좌표계','location':'declared_support_sets',
            'recovery':['native_RF_sum','recovered_stress_traction'],
            'complete_discrete_support_reaction':False}
    transformed=bool(local and quantity in ('S','E'))
    return {'quantity':quantity,'units':{'S':'MPa','E':'1','U':'mm','RF':'N'}[quantity],
        'coordinate_frame':'declared_element_axes' if transformed else 'global',
        'display_basis':'요소별 선언 기저로 변환 (유도값)' if transformed else '전체 좌표계',
        'location':'integration_point' if name=='내부 적분점' else 'expanded_node',
        'recovery':'native_integration_point' if name=='내부 적분점' else
            'extrapolated_averaged' if quantity in ('S','E') else 'native_expanded_node'}


def _open(W,C,*,parent,title,frames,builder,sources,status,source_identity,quantities,observation_pins):
    window=W.QDialog(parent);window.setWindowTitle(title);window.resize(1220,760)
    window.setAttribute(C.Qt.WA_DeleteOnClose)
    status_label={'SUCCEEDED':'계산 완료','FAILED':'계산 실패','CANCELLED':'계산 취소',
        'PARTIAL_FAILURE':'일부 계산 실패','INTERRUPTED':'계산 중단'}.get(status.split(' / ')[0],'계산 상태 미확인')
    box=W.QVBoxLayout(window);banner=W.QLabel(status_label+' / 공학적 적합성 미확인')
    banner.setWordWrap(True);box.addWidget(banner)
    row=W.QHBoxLayout();step=W.QComboBox();quantity=W.QComboBox();basis=W.QComboBox()
    quantity.setObjectName('b13Quantity');basis.setObjectName('b13Basis')
    for f in frames:
        s=f.get('static',f);step.addItem(f'단계 {s["step"]} / 증분 {s["increment"]} / 정적 하중 {s["load_parameter"]:.9g}')
    for q,label in quantities:quantity.addItem(label,q)
    quantity.setToolTip('확장 절점과 내부 적분점 표의 물리량을 선택합니다.')
    basis.addItem('전체 좌표계',False);basis.addItem('요소별 선언 기저로 변환 (유도값)',True)
    for w in (step,quantity,basis):row.addWidget(w)
    box.addLayout(row);scope=W.QLabel();scope.setWordWrap(True);box.addWidget(scope)
    tabs=W.QTabWidget();box.addWidget(tabs,1)
    tables={};models={};descriptions={}
    class TableModel(C.QAbstractTableModel):
        def __init__(self,parent):super().__init__(parent);self.head=[];self.rows=[]
        def rowCount(self,parent=C.QModelIndex()):return 0 if parent.isValid() else len(self.rows)
        def columnCount(self,parent=C.QModelIndex()):return 0 if parent.isValid() else len(self.head)
        def data(self,index,role=C.Qt.DisplayRole):
            if not index.isValid() or role!=C.Qt.DisplayRole:return None
            value=self.rows[index.row()][index.column()]
            if value is None:return '제공 없음'
            return format(value,'.10g') if isinstance(value,float) else str(value)
        def headerData(self,section,orientation,role=C.Qt.DisplayRole):
            if role!=C.Qt.DisplayRole:return None
            return self.head[section] if orientation==C.Qt.Horizontal else str(section+1)
        def replace(self,head,rows):
            self.beginResetModel();self.head=head;self.rows=rows;self.endResetModel()
    initial=builder(0,quantity.currentData(),False) if frames else {}
    for name in initial:
        page=W.QWidget();layout=W.QVBoxLayout(page);description=W.QLabel();description.setWordWrap(True)
        layout.addWidget(description);table=W.QTableView();model=TableModel(table);table.setModel(model)
        table.setAlternatingRowColors(True);table.setSelectionBehavior(W.QAbstractItemView.SelectRows)
        table.setEditTriggers(W.QAbstractItemView.NoEditTriggers);table.setSortingEnabled(False)
        layout.addWidget(table,1);tabs.addTab(page,name.replace('·',''));tables[name]=table;models[name]=model;descriptions[name]=description
    source_page=W.QWidget();sl=W.QVBoxLayout(source_page);choice=W.QComboBox();text=W.QPlainTextEdit();text.setReadOnly(True)
    sl.addWidget(W.QLabel('원 입력·로그는 보존된 파일의 바이트·SHA를 다시 확인한 뒤 표시합니다.'));sl.addWidget(choice);sl.addWidget(text,1)
    tabs.addTab(source_page,'원 입력과 로그')
    table_names=list(initial)
    def selected_table():
        i=tabs.currentIndex();return table_names[i] if 0<=i<len(table_names) else None
    def update_controls(*_):
        name=selected_table();field=name in models and name not in ('유도 회전','지지 응답')
        quantity.setEnabled(field);basis.setEnabled(field and quantity.currentData() in ('S','E'))
        export.setEnabled(name in models)
        if name=='유도 회전':scope.setText('이 표: 전체 좌표계 / 유도 회전 [rad]')
        elif name=='지지 응답':scope.setText('이 표: 전체 좌표계 / 힘 [N], 모멘트 [Nmm], 기준점 [mm]')
        else:scope.clear()
        scope.setVisible(bool(scope.text()))
    source_names=sorted(sources)
    for name in source_names:choice.addItem(name)
    def read_source(i):
        if i<0:return
        try:
            path,pin=sources[source_names[i]]
            from caelab.adapters.shell_deck import read_bytes
            data=read_bytes(path)
            if len(data)!=pin['bytes'] or hashlib.sha256(data).hexdigest()!=pin['sha256']:
                raise ValueError('보존 원자료가 바뀌었습니다. 다른 파일을 같은 결과로 표시하지 않습니다.')
            shown=data[:2*1024**2].decode('utf-8',errors='replace')
            if len(data)>2*1024**2:shown+='\n[앞 2 MiB만 표시함. 원본 전체는 보존됨.]'
            text.setPlainText(shown)
        except Exception as exc:text.setPlainText(str(exc))
    choice.currentIndexChanged.connect(read_source)
    def refresh(*_):
        if step.currentIndex()<0:return
        data=builder(step.currentIndex(),quantity.currentData(),bool(basis.currentData()))
        for name,(header,values,description) in data.items():
            models[name].replace(header,values);tables[name].resizeColumnsToContents()
            descriptions[name].setText(description+f' / {len(values)}행')
        update_controls()
    footer=W.QHBoxLayout();export=W.QPushButton('현재 표 CSV 저장…');details=W.QPushButton('원자료 정보…');close=W.QPushButton('닫기')
    export.setObjectName('exportB13Table')
    footer.addWidget(export);footer.addWidget(details);footer.addStretch();footer.addWidget(close);box.addLayout(footer)
    def save_csv():
        name=selected_table()
        if name not in models:return
        path,_=W.QFileDialog.getSaveFileName(window,'원자료 표 저장','','CSV (*.csv)')
        if not path:return
        try:
            export_table(path,headers=models[name].head,rows=models[name].rows,
                provenance={'worksheet':name,'definition':descriptions[name].text(),
                    'frame':deepcopy(frames[step.currentIndex()].get('static',
                        {k:frames[step.currentIndex()].get(k) for k in ('step','increment','load_parameter')})),
                    **table_export_metadata(name,quantity.currentData(),bool(basis.currentData())),
                    'source_identity':source_identity,
                    'source_pins':deepcopy(observation_pins),'execution_status':status,
                    'native_engineering_acceptance':False})
        except OSError as exc:W.QMessageBox.warning(window,'표 저장 실패',str(exc))
    def show_details():
        dialog=W.QDialog(window);dialog.setWindowTitle('원자료 정보');dialog.resize(760,420)
        layout=W.QVBoxLayout(dialog);text=W.QPlainTextEdit();text.setReadOnly(True)
        text.setPlainText('원 상태: '+status+'\n'+source_identity);layout.addWidget(text)
        dialog.setAttribute(C.Qt.WA_DeleteOnClose);dialog.show()
    details.clicked.connect(show_details);tabs.currentChanged.connect(update_controls)
    export.clicked.connect(save_csv);close.clicked.connect(window.close)
    step.currentIndexChanged.connect(refresh);quantity.currentIndexChanged.connect(refresh);basis.currentIndexChanged.connect(refresh)
    if frames:step.setCurrentIndex(len(frames)-1);refresh()
    else:banner.setText(banner.text()+'\n읽을 수 있는 완전한 관측 프레임이 없습니다. 원 입력과 실패 로그를 유지합니다.');export.setEnabled(False)
    read_source(0 if source_names else -1);_WINDOWS.append(window)
    window.destroyed.connect(lambda *_:_WINDOWS.remove(window) if window in _WINDOWS else None)
    window.show();return window


def open_beam_result(W,C,folder,saved,*,parent=None):
    receipt=saved['execution'];observed=saved['observed'];folder=Path(folder)
    sources={r['relative']:(folder/r['relative'],r) for r in receipt.get('artifacts',[])
             if Path(r['relative']).suffix in ('.inp','.log','.dat','.12d','.sta','.cvg')}
    return _open(W,C,parent=parent,title='빔 원결과',
        frames=observed['frames'] if observed else [],builder=lambda i,q,b:beam_tables(saved,i,quantity=q,local=b),
        sources=sources,status=str(receipt['execution_status'])+' / '+str(receipt.get('saved_reader_error','')),
        source_identity='보존 실행 폴더: '+str(folder)+'\n원 입력: '+str(receipt.get('snapshot_id',''))+' / 출력: 별도 3D 원응력',
        quantities=[('S','응력 [MPa]'),('E','변형률 [1]'),('U','변위 [mm]'),('RF','원 RF [N]')],
        observation_pins=deepcopy(receipt.get('artifacts',[])))


def open_shell_result(W,C,path=None,*,parent=None):
    if path is None:
        filename,_=W.QFileDialog.getOpenFileName(parent,'셸 원결과 묶음 열기','','셸 원결과 (shell_inspection.json)')
        if not filename:return None
        path=filename
    from caelab.shell_inspection import explicit_manifest,load
    try:
        view,metadata=explicit_manifest(path);checked=load(view,metadata['shell_inspection'])
    except Exception as exc:
        W.QMessageBox.warning(parent,'셸 원결과를 열지 못했습니다',str(exc));return None
    data=checked['data'];sources={r['relative']:(view.parent/r['relative'],r) for r in checked['manifest']['files']
                               if r['relative'].startswith('source/')}
    return _open(W,C,parent=parent,title='셸 원결과',frames=data['surface']['frames'],
        builder=lambda i,q,b:shell_tables(checked,i,quantity=q,local=b),sources=sources,
        status=data['execution_status'],source_identity='보존 결과: '+str(view.parent)+' / 현재 편집 모델로 재지정하지 않음',
        quantities=[('S','응력 [MPa]'),('E','변형률 [1]'),('U','변위 [mm]')],
        observation_pins=deepcopy(checked['manifest']['files']))
