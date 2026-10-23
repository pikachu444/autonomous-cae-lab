"""Read one exact saved research reference without replacing the editable owner."""
import argparse
import json
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QPushButton
from caelab.workbench_client import Client
from .pde_window import _Read
from PySide6.QtCore import QThreadPool


class ReferenceWindow(QMainWindow):
    def __init__(self, client, reference):
        super().__init__()
        self.client, self.reference = client, reference
        self.resize(1050, 750)
        self.setWindowTitle('Exact saved research source — read only')
        root=QWidget(); layout=QVBoxLayout(root)
        self.message=QLabel('Reading the selected saved revision. The current editor is unchanged.')
        self.message.setWordWrap(True); layout.addWidget(self.message)
        self.tree=QTreeWidget(); self.tree.setHeaderLabels(['Saved item','Exact value']); self.tree.setColumnWidth(0,370)
        layout.addWidget(self.tree)
        self.open_button=QPushButton('Open original working editor')
        self.open_button.setEnabled(False); self.open_button.clicked.connect(self.open_owner)
        layout.addWidget(self.open_button); self.setCentralWidget(root)
        self.worker=_Read(lambda:client.research_reference(reference))
        self.worker.signals.finished.connect(self.received)
        QThreadPool.globalInstance().start(self.worker)

    def received(self, value, error):
        if error:
            self.message.setText('Saved source unavailable: '+error)
            return
        self.value=value
        def append(parent,key,item):
            label=(str(len(item))+' entries') if isinstance(item,(dict,list)) else str(item)
            node=QTreeWidgetItem(parent,[str(key),label])
            rows=item.items() if isinstance(item,dict) else enumerate(item) if isinstance(item,list) else []
            for index,(name,data) in enumerate(rows):
                if index>=2048:
                    QTreeWidgetItem(node,['Additional entries','Read a bounded result selection from the owning editor'])
                    break
                append(node,name,data)
        for key,item in value.items(): append(self.tree,key,item)
        self.tree.expandToDepth(1)
        self.message.setText('Showing the exact saved reference. Editing the original creates a separate current revision.')
        self.open_button.setEnabled(True)

    def open_owner(self):
        from .desktop import launch_tool
        reference=self.reference
        if reference['kind']=='result':
            launch_tool(self.client,'runner',job_id=reference['job_id'])
        else:
            kind='expert' if reference['kind']=='expert_turn' else reference['document_kind']
            identifier=reference.get('discussion_id',reference.get('document_id'))
            launch_tool(self.client,kind,document_id=identifier)


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--service',required=True); parser.add_argument('--reference',required=True)
    args=parser.parse_args(argv)
    app=QApplication.instance() or QApplication(sys.argv[:1])
    window=ReferenceWindow(Client(args.service),json.loads(args.reference)); window.show()
    return app.exec()


if __name__=='__main__':
    raise SystemExit(main())
