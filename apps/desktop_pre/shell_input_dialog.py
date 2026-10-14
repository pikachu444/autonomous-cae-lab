"""Read-only shell deck preview in the existing native Qt window."""
from pathlib import Path
import shutil

from caelab.adapters.shell_deck import validate_snapshot, read_bytes, sha


def show_input(manifest, W, C, *, parent=None):
    manifest=Path(manifest).absolute()
    record,model,mesh,pins=validate_snapshot(manifest)
    before={name:pin['sha256'] for name,pin in pins.items()}
    dialog=W.QDialog(parent); dialog.setWindowTitle('판재 셸 입력')
    layout=W.QVBoxLayout(dialog)
    summary=W.QLabel(f"S8 {len(mesh['elements'])}개 / 두께 {mesh['section_values']['thickness_mm']:g} mm / "
                     f"Offset {mesh['section_values']['offset']:g}\n계산은 실행하지 않았습니다.")
    summary.setWordWrap(True); layout.addWidget(summary)
    editor=W.QPlainTextEdit(); editor.setReadOnly(True)
    editor.setPlainText(read_bytes(manifest.parent/'shell.inp').decode('ascii')); layout.addWidget(editor,1)
    status=W.QLabel(); status.setWordWrap(True); layout.addWidget(status)
    buttons=W.QDialogButtonBox(W.QDialogButtonBox.Close)
    copy=buttons.addButton('입력 사본 저장…',W.QDialogButtonBox.ActionRole)
    def save_copy():
        try:
            path,_=W.QFileDialog.getSaveFileName(dialog,'셸 입력 사본 저장','shell-copy.inp','CalculiX (*.inp)')
            if not path:return
            destination=Path(path).absolute()
            if destination.resolve().is_relative_to(manifest.parent.resolve()):
                raise ValueError('준비 입력 폴더 밖에 사본을 저장하세요.')
            if destination.exists():raise ValueError('기존 파일을 덮어쓰지 않는 새 이름을 선택하세요.')
            with destination.open('xb') as stream:stream.write(read_bytes(manifest.parent/'shell.inp'))
            status.setText('사본 저장: '+str(destination))
        except Exception as error:status.setText(str(error))
    copy.clicked.connect(save_copy); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
    dialog.resize(840,620); dialog.exec()
    if any(sha(manifest.parent/name)!=pin for name,pin in before.items()):
        raise ValueError('입력 미리보기 도중 준비 파일이 바뀌었습니다.')
