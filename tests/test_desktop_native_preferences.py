"""Remember interactive native app choices without changing explicit/headless runs."""
from pathlib import Path

import pytest

from apps.research import desktop
from caelab import native_tools


@pytest.fixture(autouse=True)
def no_machine_discovery(monkeypatch):
    for key in ('CAELAB_FREECAD_EXE','CAELAB_PARAVIEW_EXE','CAE_POST_EXIT_PLUGIN',
                'CAE_POST_PARAVIEW_ROOT','ProgramFiles','ProgramFiles(x86)','LOCALAPPDATA'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('PATH','')
    monkeypatch.setattr(native_tools,'_windows_app_paths',lambda name:[])
    monkeypatch.setattr(native_tools,'saved_executable',lambda key:None)


@pytest.fixture
def preferences(tmp_path, monkeypatch):
    QSettings = pytest.importorskip('PySide6.QtCore').QSettings
    path = tmp_path / 'launchers.ini'
    def fresh():
        return QSettings(str(path), QSettings.Format.IniFormat)
    monkeypatch.setattr(desktop, '_native_settings', fresh)
    return fresh


def test_native_choices_persist_separately_and_relocate_missing_file(tmp_path, monkeypatch, preferences):
    choices = {}
    for key, name in [('freecad_executable', 'FreeCAD.exe'), ('paraview_executable', 'paraview.exe')]:
        selected = tmp_path / ('설치 폴더 ' + name)
        selected.write_bytes(b'TEST_ONLY')
        monkeypatch.setattr(desktop, '_choose_file', lambda *args: selected)
        assert desktop._executable({}, key) == selected
        choices[key] = selected
    monkeypatch.setattr(desktop, '_choose_file', lambda *args: pytest.fail('Saved app must not prompt again'))
    for key, selected in choices.items():
        assert Path(preferences().value(key)) == selected
        assert desktop._executable({}, key) == selected
    choices['freecad_executable'].unlink()
    moved = tmp_path / '새 FreeCAD.exe'
    moved.write_bytes(b'TEST_ONLY')
    monkeypatch.setattr(desktop, '_choose_file', lambda *args: moved)
    assert desktop._executable({}, 'freecad_executable') == moved
    assert Path(preferences().value('freecad_executable')) == moved
    assert Path(preferences().value('paraview_executable')) == choices['paraview_executable']


def test_explicit_and_headless_launches_never_consult_desktop_preferences(tmp_path, monkeypatch):
    selected = tmp_path / 'selected.exe'
    selected.write_bytes(b'TEST_ONLY')
    monkeypatch.setattr(desktop, '_native_settings', lambda: pytest.fail('Explicit paths stay authoritative'))
    monkeypatch.setattr(desktop, '_choose_file', lambda *args: pytest.fail('No dialog expected'))
    key = 'freecad_executable'
    assert desktop._executable({key: str(selected)}, key) == selected
    assert desktop._executable({}, key, str(selected)) == selected
    assert desktop._executable({key: str(selected)}, key, interactive=False) == selected
    with pytest.raises(ValueError, match='--executable'):
        desktop._executable({key: str(selected)}, key, str(tmp_path / 'missing.exe'))
    with pytest.raises(ValueError, match='실행 파일'):
        desktop._executable({}, key, interactive=False)


def test_cancelled_relocation_preserves_saved_choice(tmp_path, monkeypatch, preferences):
    key = 'freecad_executable'
    original = str(tmp_path / 'missing FreeCAD.exe')
    preferences().setValue(key, original)
    def cancel(*args):
        raise ValueError('No file selected')
    monkeypatch.setattr(desktop, '_choose_file', cancel)
    with pytest.raises(ValueError, match='No file selected'):
        desktop._executable({}, key)
    assert preferences().value(key) == original
