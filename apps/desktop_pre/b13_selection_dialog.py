"""Small native Qt chooser of actual mesh identities, with no execution side effects."""


def choose_ids(W, C, parent, rows, selected, title):
    if len(rows) > 20000:
        raise ValueError('표 선택은 20,000행까지입니다. native 면 선택으로 범위를 줄이세요.')
    dialog = W.QDialog(parent); dialog.setWindowTitle(title); dialog.resize(660,480)
    layout = W.QVBoxLayout(dialog)
    hint = W.QLabel('실제 요소 번호와 참조 메시의 기하 중심 [mm]입니다. 적분점/결과 좌표가 아닙니다.')
    hint.setWordWrap(True); layout.addWidget(hint)
    table = W.QTableWidget(len(rows),4); table.setHorizontalHeaderLabels(['요소','X [mm]','Y [mm]','Z [mm]'])
    table.setSelectionBehavior(W.QAbstractItemView.SelectRows)
    table.setSelectionMode(W.QAbstractItemView.ExtendedSelection)
    table.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
    table.horizontalHeader().setSectionResizeMode(W.QHeaderView.Stretch)
    table.setAlternatingRowColors(True)
    selected = set(selected)
    for i,(number,xyz) in enumerate(rows):
        for j,value in enumerate([str(number),*(format(v,'.9g') for v in xyz)]):
            table.setItem(i,j,W.QTableWidgetItem(value))
        if number in selected:
            table.selectionModel().select(table.model().index(i,0),C.QItemSelectionModel.Select|C.QItemSelectionModel.Rows)
    layout.addWidget(table,1)
    buttons=W.QDialogButtonBox(W.QDialogButtonBox.Ok|W.QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
    result=dialog.exec() if hasattr(dialog,'exec') else dialog.exec_()
    return [rows[index.row()][0] for index in table.selectionModel().selectedRows()] if result==W.QDialog.Accepted else None
