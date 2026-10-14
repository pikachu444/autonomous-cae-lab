"""Read/export already frozen input. Opening this dialog never submits a job."""
import hashlib
import importlib
import json
from pathlib import Path

def show_input(manifest, W, C, *, parent=None):
    manifest=Path(manifest).resolve(strict=True)
    data=json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('kind')=='freecad-contact-frozen':
        from caelab.adapters.contact_fem import validate_snapshot
        validate_snapshot(manifest)
    entries=[r for r in data.get('files',[]) if str(r.get('relative','')).lower().endswith('.inp')]
    if not entries:
        raise ValueError('보존된 입력 파일을 찾지 못했습니다')
    G=importlib.import_module(W.__package__+'.QtGui')
    dialog=W.QDialog(parent); dialog.setWindowTitle('해석 입력 파일')
    layout=W.QVBoxLayout(dialog)
    layout.addWidget(W.QLabel('입력 생성 완료 / 계산 미실행'))
    selector=W.QComboBox()
    for row in entries: selector.addItem(Path(row['relative']).name,row)
    layout.addWidget(selector)
    text=W.QPlainTextEdit(); text.setReadOnly(True); layout.addWidget(text,1)
    status=W.QLabel(); status.setWordWrap(True); layout.addWidget(status)
    def read():
        row=selector.currentData()
        source=(manifest.parent/row['relative']).resolve(strict=True)
        if not source.is_relative_to(manifest.parent):
            raise ValueError('Input path escapes the retained directory')
        raw=source.read_bytes()
        if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:
            raise ValueError('보존 입력이 변경되었습니다')
        return source,raw
    def show(*_):
        try:
            source,raw=read()
            text.setPlainText(raw.decode('ascii'))
            status.setText(str(source))
        except Exception as error: status.setText(str(error)); text.clear()
    def save():
        source,raw=read()
        selected,_=W.QFileDialog.getSaveFileName(dialog,'입력 파일 저장',source.name,'CalculiX (*.inp)')
        if not selected: return
        target=Path(selected).resolve()
        if target.is_relative_to(manifest.parent):
            raise ValueError('보존 입력 밖의 새 파일을 선택하세요')
        target.write_bytes(raw)
        status.setText('입력 사본 저장: '+str(target))
    buttons=W.QHBoxLayout()
    export=W.QPushButton('입력 사본 저장…')
    def save_safe():
        try: save()
        except Exception as error: status.setText(str(error))
    export.clicked.connect(save_safe); buttons.addWidget(export)
    folder=W.QPushButton('입력 폴더 열기')
    folder.clicked.connect(lambda:G.QDesktopServices.openUrl(C.QUrl.fromLocalFile(str(manifest.parent))))
    buttons.addWidget(folder); buttons.addStretch()
    close=W.QPushButton('닫기'); close.clicked.connect(dialog.accept); buttons.addWidget(close)
    layout.addLayout(buttons)
    selector.currentIndexChanged.connect(show); show()
    dialog.resize(900,680); dialog.exec()
