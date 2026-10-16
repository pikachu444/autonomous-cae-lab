"""Read original laminate DAT tuples in a native Qt table, without a solver."""
from pathlib import Path
from .beam_visuals import qt_gui

_WINDOWS=[]


def open_result(W,C,folder=None,*,parent=None):
    from caelab.adapters.composite_shell_fem import read_saved_run
    from caelab.composite_shell_results import load,selected_tensor
    if folder is None:
        filename,_=W.QFileDialog.getOpenFileName(parent,'층별 결과 열기','','적층 결과 (composite_execution.json composite_inspection.json)')
        if not filename:return None
        folder=Path(filename).parent
    folder=Path(folder)
    if (folder/'composite_inspection.json').is_file():
        from caelab.adapters.shell_deck import json_read
        manifest=json_read(folder/'composite_inspection.json')
        result=load(folder/manifest['main_view'])
        saved={'execution_status':result['data']['execution_status']}
    else:
        saved=read_saved_run(folder);artifact=saved.get('post_artifact')
        if not artifact:raise ValueError('보존한 원 적층 결과가 없습니다. 계산 목록의 원 로그를 확인하세요.')
        result=load(folder/artifact['relative'],artifact['native_metadata']['composite_inspection'])
    data=result['data'];frames=data['observed']['dat']['frames']
    window=W.QDialog(parent);window.setWindowTitle('층별 응력과 변형률');window.resize(1100,700);window.setAttribute(C.Qt.WA_DeleteOnClose)
    G=qt_gui();font=G.QFont('Malgun Gothic',10);window.setFont(font)
    layout=W.QVBoxLayout(window)
    status={'SUCCEEDED':'계산 완료','FAILED':'실패한 계산의 보존 결과','CANCELLED':'취소한 계산의 보존 결과'}.get(saved['execution_status'],'보존 결과')
    banner=W.QLabel(status+' / 원 적분점 값 · 전체 좌표계 / 공학적 승인 미확인');banner.setWordWrap(True);layout.addWidget(banner)
    row=W.QHBoxLayout();frame=W.QComboBox();ply=W.QComboBox();quantity=W.QComboBox();component=W.QComboBox()
    for name,widget in (('증분',frame),('층',ply),('물리량',quantity),('성분',component)):
        row.addWidget(W.QLabel(name));row.addWidget(widget,1)
    layout.addLayout(row)
    basis=W.QComboBox();basis.addItem('전체 좌표계 · DAT 원값','GLOBAL');basis.addItem('선언 층축 · 원값의 좌표 변환','DECLARED_PLY');layout.addWidget(basis)
    for i,item in enumerate(frames):frame.addItem('하중 계수 '+format(item['load_parameter'],'.8g'),i)
    ply.addItem('모든 층',None)
    seen=set()
    for region in data['model']['draft']['regions']:
        for position,item in enumerate(region['plies'],1):
            if item['id'] not in seen:
                material=data['model']['draft']['materials'][item['material_id']]
                ply.addItem(region.get('label','영역')+f' / 위에서 {position}층 · '+material.get('label','원 재료'),item['id']);seen.add(item['id'])
    quantity.addItem('응력 [MPa]','S');quantity.addItem('변형률 [1]','E')
    for name in ('XX','YY','ZZ','XY','YZ','ZX'):component.addItem(name)
    note=W.QLabel('위치는 보존한 층 형상으로 계산했습니다. 두께 점 1·2는 각 층의 아래쪽부터입니다. 3D 값은 외삽·평균 값입니다.');note.setWordWrap(True);layout.addWidget(note)
    table=W.QTableWidget(0,9);table.setHorizontalHeaderLabels(['원 셸','위에서 층','면내 점','층 두께 점','원 IP','X [mm]','Y [mm]','Z [mm]','값 [MPa]'])
    table.setEditTriggers(W.QAbstractItemView.NoEditTriggers);table.setSelectionBehavior(W.QAbstractItemView.SelectRows);table.setAlternatingRowColors(True)
    table.horizontalHeader().setSectionResizeMode(W.QHeaderView.ResizeToContents);table.horizontalHeader().setStretchLastSection(True);layout.addWidget(table,1)
    def refresh(*unused):
        index=frame.currentIndex();key=quantity.currentData();ci=component.currentIndex();table.setRowCount(0)
        local=basis.currentData()=='DECLARED_PLY'
        for i,name in enumerate(('11','22','33','12','23','31') if local else ('XX','YY','ZZ','XY','YZ','ZX')):component.setItemText(i,name)
        banner.setText(status+' / '+('선언 층축 변환값' if local else '원 적분점 값 · 전체 좌표계')+' / 공학적 승인 미확인')
        table.setHorizontalHeaderItem(8,W.QTableWidgetItem('값 ['+('MPa' if key=='S' else '1')+']'))
        if index<0:return
        rows=[r for r in frames[index]['rows'] if (ply.currentData() is None or r['ply_id']==ply.currentData()) and key in r]
        table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            layer=data['observed']['layer_solids'][str(r['native_solid_id'])]
            tensor=selected_tensor(r,key,basis=basis.currentData(),layer=layer)
            values=[r['element_id'],r['ui_position'],r['inplane_ip'],r['thickness_ip'],r['integration_point'],*r['position_derived_mm'],tensor[ci]]
            for j,value in enumerate(values):table.setItem(i,j,W.QTableWidgetItem(str(value) if j<5 else format(value,'.9g')))
    for widget in (frame,ply,quantity,component,basis):widget.currentIndexChanged.connect(refresh)
    export=W.QPushButton('현재 표 저장…');layout.addWidget(export)
    def save_table():
        import csv
        filename,_=W.QFileDialog.getSaveFileName(window,'현재 층 결과 저장','','CSV (*.csv)')
        if not filename:return
        with Path(filename).open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['물리량',quantity.currentText(),'성분',component.currentText(),'기저',basis.currentText(),'하중 계수',frames[frame.currentIndex()]['load_parameter']])
            writer.writerow(['위치','보존한 FRD 층 형상으로 계산한 적분점 위치','원 수치','DAT S/E','자격','미확인'])
            writer.writerow([table.horizontalHeaderItem(j).text() for j in range(table.columnCount())])
            writer.writerows([[table.item(i,j).text() for j in range(table.columnCount())] for i in range(table.rowCount())])
    export.clicked.connect(save_table)
    close=W.QDialogButtonBox(W.QDialogButtonBox.Close);close.rejected.connect(window.close);layout.addWidget(close)
    window.composite_table=table;window.composite_ply=ply;window.composite_frame=frame;window.composite_quantity=quantity
    frame.setCurrentIndex(len(frames)-1);refresh();_WINDOWS.append(window);window.destroyed.connect(lambda *_:_WINDOWS.remove(window) if window in _WINDOWS else None)
    window.show();return window
