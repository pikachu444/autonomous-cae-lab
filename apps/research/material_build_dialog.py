"""Review exact source; grant locally, never through the service API."""
from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPlainTextEdit,
    QPushButton,QDialogButtonBox,QFileDialog)
from caelab import material_build_permission as permission


class MaterialBuildDialog(QDialog):
    def __init__(self,client,context,settings,parent=None):
        super().__init__(parent)
        self.context=deepcopy(context);self.settings=deepcopy(settings);self.approved=False
        self.folder=permission.accessible_directory(context)
        self.setWindowTitle('이 원문 빌드');self.resize(820,650)
        layout=QVBoxLayout(self)
        title=QLabel(settings['behaviour']);title.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(title)
        source=QPlainTextEdit(settings['source']);source.setReadOnly(True);layout.addWidget(source,1)
        self.source=source
        note=QLabel('선택한 원문을 컴파일하고 native 라이브러리를 불러옵니다. 이 버전만 허용하며, 편집·저장만으로는 실행하지 않습니다.')
        note.setWordWrap(True);layout.addWidget(note)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        row=QHBoxLayout()
        self.choose=QPushButton('서비스 권한 폴더 선택…');self.choose.clicked.connect(self.choose_folder);row.addWidget(self.choose)
        details=QPushButton('연결 상세');details.setCheckable(True);row.addWidget(details);row.addStretch();layout.addLayout(row)
        self.details=QPlainTextEdit(client.url+'\n'+context.get('directory',''))
        self.details.setReadOnly(True);self.details.setMaximumHeight(85);self.details.hide();layout.addWidget(self.details)
        details.toggled.connect(self.details.setVisible)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.confirm=self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.confirm.setText('이 버전 빌드' if settings['action']=='build' else '이 버전 빌드하고 평가')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.confirm.clicked.connect(self.approve);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self._show_access()

    def _show_access(self):
        self.confirm.setEnabled(self.folder is not None)
        self.choose.setVisible(self.folder is None)
        self.status.setText('현재 서비스의 로컬 빌드 권한을 확인했습니다.' if self.folder is not None else
            '현재 서비스의 권한 폴더에 접근할 수 없습니다. 같은 사용자 계정의 WSL/로컬 폴더를 선택하거나 서비스 운영자에게 이 원문 버전의 빌드를 요청하세요.')

    def choose_folder(self):
        selected=QFileDialog.getExistingDirectory(self,'현재 서비스의 빌드 권한 폴더')
        if not selected:return
        try:self.folder=permission.verify_local(selected,self.context)
        except (OSError,ValueError) as error:
            self.folder=None;self._show_access();self.status.setText(str(error));return
        self._show_access()

    def approve(self):
        if self.folder is None:return
        try:
            permission.approve_local(self.folder,self.context,self.settings['source'],self.settings['behaviour'])
        except (OSError,ValueError,TimeoutError) as error:
            self.status.setText('빌드를 허용하지 못했습니다. '+str(error));return
        self.approved=True;self.accept()
