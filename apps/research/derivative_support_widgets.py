"""Read-only presentation of the existing descriptor's derivative contracts."""
import json
from copy import deepcopy
from PySide6.QtCore import Qt,QTimer,QRect
from PySide6.QtWidgets import QDialog,QDialogButtonBox,QLabel,QVBoxLayout,QWidget,QTableWidgetItem,QHeaderView
from .runner_window import readonly_table
from .numerical_methods import display_number


class DerivativeSupport(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);layout=QVBoxLayout(self)
        self.summary=QLabel('미분법 지원 정보가 미제공 상태입니다.');self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.table=readonly_table(['방법','용도','지원 범위','모델 범위','한계'])
        self.table.setObjectName('derivativeMethodSupport');layout.addWidget(self.table,1)
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.setColumnWidth(0,190);self.table.setColumnWidth(1,125);self.table.setColumnWidth(3,100)
        for column in (2,4):self.table.horizontalHeader().setSectionResizeMode(column,QHeaderView.ResizeMode.Stretch)

    def set_descriptor(self,payload,*,message=''):
        profiles=payload.get('derivative_methods',[])
        self.profiles=deepcopy(profiles) if isinstance(profiles,list) else []
        rows=[]
        if isinstance(profiles,list):
            for row in profiles:
                if isinstance(row,dict):
                    limitations=row.get('limitations',[]);reasons=row.get('reasons',[])
                    if isinstance(limitations,list) and isinstance(reasons,list):limitations=limitations+reasons
                    role={'optimizer_gradient':'최적화 미분','final_candidate_diagnostic':'최종점 진단','search':'탐색'}.get(row.get('role'),row.get('role'))
                    rows.append((row.get('label',row.get('method')),role,row.get('scope'),
                        {'SUPPORTED':'지원 범위 내','UNSUPPORTED':'지원 안 됨','UNASSESSED':'미확인'}.get(row.get('problem_support'),'미제공'),limitations))
        self.table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate(row):
                shown='\n'.join(str(v) for v in value) if isinstance(value,list) else display_number(value)
                item=QTableWidgetItem(shown);item.setToolTip(str(value));self.table.setItem(i,j,item)
        self._resize_rows()
        summary=message or ('지원 범위는 원 descriptor의 선언입니다. 저장된 결과를 읽거나 이 표를 여는 동작은 계산하지 않습니다.'
            if rows else '미분법 지원 정보가 미제공 상태입니다.')
        unprobed=payload.get('runtime')=='NOT_PROBED' or any(
            isinstance(row,dict) and (row.get('runtime')=='NOT_PROBED' or
                'runtime_available' in row and row['runtime_available'] is None) for row in self.profiles)
        self.summary.setText(summary+('\n현재 실행 환경은 확인하지 않았습니다.' if unprobed else ''))
        self.summary.setToolTip(json.dumps(payload.get('derivative_capability',{}),ensure_ascii=False,indent=2))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        QTimer.singleShot(0,self._resize_rows)

    def _resize_rows(self):
        metrics=self.table.fontMetrics()
        for row in range(self.table.rowCount()):
            height=metrics.height()+16
            for column in range(self.table.columnCount()):
                item=self.table.item(row,column)
                if item is not None:
                    rect=QRect(0,0,max(20,self.table.columnWidth(column)-20),10000)
                    height=max(height,metrics.boundingRect(rect,Qt.TextFlag.TextWordWrap,item.text()).height()+16)
            self.table.setRowHeight(row,height)


def support_dialog(parent,payload,*,message=''):
    dialog=QDialog(parent);dialog.setWindowTitle('미분법 지원');dialog.resize(1000,520)
    layout=QVBoxLayout(dialog);content=DerivativeSupport(dialog);content.set_descriptor(payload,message=message);layout.addWidget(content,1)
    dialog.content=content
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.button(QDialogButtonBox.StandardButton.Close).setText('계획으로 돌아가기')
    buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
    return dialog
