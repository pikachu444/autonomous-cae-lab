"""Read one exact saved research reference without replacing the editable owner."""
import argparse
import json
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QPushButton, QDialog
from copy import deepcopy
from .reference_content import ReferenceContent
from caelab.workbench_client import Client
from .expert_window import _Call
from PySide6.QtCore import QThreadPool, Qt


class ReferenceWindow(QMainWindow):
    def __init__(self, client, reference):
        super().__init__()
        self.client, self.reference = client, deepcopy(reference)
        self._workers, self._busy, self._closed = [], False, False
        self.resize(1050, 750)
        self.setWindowTitle('Research source')
        root=QWidget(); layout=QVBoxLayout(root)
        self.message=QLabel('Reading source…')
        self.message.setWordWrap(True); layout.addWidget(self.message)
        self.tree=QTreeWidget(); self.tree.setHeaderLabels(['Saved item','Exact value']); self.tree.setColumnWidth(0,370)
        self.tree.hide()
        self.content = ReferenceContent()
        self.content.response_requested.connect(self.read_response)
        layout.addWidget(self.content, 1)
        details = QPushButton('Technical details…')
        details.clicked.connect(self.show_details)
        layout.addWidget(details)
        self.open_button=QPushButton('Open original working editor')
        self.open_button.setEnabled(False); self.open_button.clicked.connect(self.open_owner)
        layout.addWidget(self.open_button); self.setCentralWidget(root)
        self._read(reference)

    def _read(self, reference):
        if self._busy or self._closed:
            return False
        self._busy = True
        self.content.read.setEnabled(False)
        self.open_button.setEnabled(False)
        frozen = deepcopy(reference)
        worker = _Call(lambda: self.client.research_reference(frozen))
        self._workers.append(worker)
        def finished(value, error):
            self._workers.remove(worker)
            self._busy = False
            if self._closed:
                return
            self.content.read.setEnabled(True)
            self.received(value, error)
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def closeEvent(self, event):
        self._closed = True
        for worker in self._workers:
            worker.abandon()
        super().closeEvent(event)

    def received(self, value, error):
        if error:
            self.message.setText('Saved source unavailable: '+error)
            self.content.clear('Source unavailable: ' + error)
            return
        self.value=value
        self.tree.clear()
        self.content.set_payload(value, label='Saved source')
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
        self.message.setText('Read only')
        self.open_button.setEnabled(True)

    def read_response(self, name):
        if self._busy or self._closed or self.reference.get('kind') != 'result':
            return
        reference = deepcopy(self.reference)
        reference.pop('response', None)
        reference['selection'] = {'responses': [name], 'rows': [0, 256]}
        self.reference = reference
        self.content.clear('Reading ' + name + '…')
        self._read(reference)

    def show_details(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Source details')
        dialog.resize(850, 600)
        layout = QVBoxLayout(dialog)
        layout.addWidget(self.tree)
        self.tree.show()
        dialog.exec()
        self.tree.setParent(self)
        self.tree.hide()

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
