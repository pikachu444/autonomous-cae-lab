"""Review actual compiled input names without guessing physical units or running code."""
from copy import deepcopy
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QTabWidget,QTableWidget,
    QTableWidgetItem,QHeaderView,QDialogButtonBox)
from PySide6.QtCore import Qt
from caelab.user_material import inputs_from_build
from .pde_window import typed_value,display


class MaterialLawInputsDialog(QDialog):
    def __init__(self,settings,build,parent=None):
        super().__init__(parent)
        self.settings=inputs_from_build(settings,build)
        self.setWindowTitle('빌드된 법칙의 입력');self.resize(780,600)
        layout=QVBoxLayout(self)
        note=QLabel('같은 이름의 기존 값은 유지했습니다. 새 물성의 값과 단위는 원문 선언에 맞게 입력하세요.')
        note.setWordWrap(True);layout.addWidget(note)
        tabs=QTabWidget();layout.addWidget(tabs,1);self.tables={}
        for key,title in (('properties','물성'),('external','외부 상태')):
            rows=self.settings[key];table=QTableWidget(len(rows),3)
            table.setHorizontalHeaderLabels(['법칙의 입력','값','단위'])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            for i,row in enumerate(rows):
                for j,name in enumerate(('name','value','unit')):
                    item=QTableWidgetItem(display(row[name]))
                    if j==0:item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    table.setItem(i,j,item)
            self.tables[key]=table;tabs.addTab(table,title)
        values=self.settings['initial_internal'];table=QTableWidget(len(values),2)
        table.setHorizontalHeaderLabels(['초기 내부 상태 (원문 단위)','값'])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        names=[]
        for row in build['descriptor']['internal_state_variables']:
            names.extend(row['name'] if row['size']==1 else row['name']+' ['+str(i+1)+']'
                         for i in range(row['size']))
        for i,value in enumerate(values):
            item=QTableWidgetItem(names[i]);item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(i,0,item);table.setItem(i,1,QTableWidgetItem(display(value)))
        self.tables['initial_internal']=table;tabs.addTab(table,'초기 내부 상태')
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('입력 초안에 반영')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def edited_settings(self):
        result=deepcopy(self.settings)
        for key in ('properties','external'):
            table=self.tables[key]
            for i,row in enumerate(result[key]):
                row['value']=typed_value(table.item(i,1).text(),row['value'],('settings',key,i,'value'),'material.mfront.user')
                row['unit']=table.item(i,2).text()
        table=self.tables['initial_internal']
        for i,value in enumerate(result['initial_internal']):
            result['initial_internal'][i]=typed_value(table.item(i,1).text(),value,
                ('settings','initial_internal',i),'material.mfront.user')
        return result
