"""Optional BREP evidence must not block editable saves or relax binding gates.

The retained public FCStd bytes are real; native objects and saveCopy are doubles.
"""
from copy import deepcopy
import zipfile

import pytest

from b13_c1_saved_fixture import saved_editor
from test_b13_c1_cold_binding import configure_project_owner
from apps.desktop_pre import projects
from caelab import native_cad
from caelab.shell_model import ShellError
from caelab.storage import save_json


def test_malformed_old_xml_omits_unavailable_proof_but_saves_live_invalid_binding(tmp_path):
    editor, inputs, _, entry, _ = saved_editor(tmp_path/'replay')
    valid_native = entry.read_bytes()
    original_archive = (inputs/'source/design.caepre').read_bytes()
    shape = editor._object('CurvedPatch').Shape.text
    before = deepcopy(editor.owner.data)
    with zipfile.ZipFile(entry) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    members['Document.xml'] = b'<Document><broken>'
    with zipfile.ZipFile(entry, 'w') as archive:
        for name, data in members.items():
            archive.writestr(name, data)

    # Only historical disk evidence is damaged. The live native save produces
    # its valid document; it must not use the damaged disk archive as its source.
    owner = configure_project_owner(editor, tmp_path, valid_native)
    assert not editor.export_binding_evidence()['breps']
    with pytest.raises(ShellError):
        editor.effective('ShellAnalysis')
    assert not editor.inspect('ShellAnalysis')['records'][0]['ready']
    destination = tmp_path/'editable.caepre'
    owner.project.save(destination)
    saved = native_cad.inspect_project(destination)
    assert saved['metadata'] == before == owner.data
    assert not saved.get('shell_binding_evidence', {}).get('breps')
    assert not owner.project.in_save
    assert not editor.inspect('ShellAnalysis')['records'][0]['ready']
    with pytest.raises(ShellError):
        editor.effective('ShellAnalysis')
    assert editor._object('CurvedPatch').Shape.text == shape
    assert (inputs/'source/design.caepre').read_bytes() == original_archive


def test_near_limit_save_omits_only_optional_proof_and_keeps_manifest_limit(tmp_path, monkeypatch):
    editor, inputs, _, entry, _ = saved_editor(tmp_path/'replay')
    native_bytes = entry.read_bytes()
    archive_bytes = (inputs/'source/design.caepre').read_bytes()
    shape = editor._object('CurvedPatch').Shape.text
    owner = configure_project_owner(editor, tmp_path, native_bytes)
    destination = tmp_path/'editable.caepre'
    owner.project.save(destination)
    baseline = native_cad.inspect_project(destination)
    assert baseline['shell_binding_evidence']['breps']
    base_only = {key: value for key, value in baseline.items() if key != 'shell_binding_evidence'}
    calibration = tmp_path/'base-manifest.json'
    save_json(calibration, base_only)
    limit = 8 * 1024 * 1024
    # Use the existing serializer's actual bytes, including Windows newlines.
    # Leave room for the next parent revision and the added metadata key.
    owner.data['raw_padding'] = 'x' * (limit - calibration.stat().st_size - 1024)
    before = deepcopy(owner.data)
    writes = []

    def observe_save(path, value):
        save_json(path, value)
        if path.name == 'project.json':
            writes.append((path.stat().st_size, 'shell_binding_evidence' in value))

    monkeypatch.setattr(projects, 'save_json', observe_save)
    owner.project.save(destination)
    saved = native_cad.inspect_project(destination)
    assert writes[0][0] > limit and writes[0][1]
    assert writes[1][0] <= limit and not writes[1][1]
    assert limit - 2048 < writes[1][0]
    assert 'shell_binding_evidence' not in saved
    assert saved['metadata'] == before == owner.data
    with zipfile.ZipFile(destination) as archive:
        assert archive.getinfo('project.json').file_size <= limit
        document_bytes = archive.read(saved['entry'])
    restored = tmp_path/'restored.FCStd'
    restored.write_bytes(document_bytes)
    with zipfile.ZipFile(entry) as old, zipfile.ZipFile(restored) as new:
        for name in old.namelist():
            if name.lower().endswith(('.brp', '.unv')):
                assert old.read(name) == new.read(name)

    retained_destination = destination.read_bytes()
    owner.data['raw_padding'] += 'x' * 4096
    oversized = deepcopy(owner.data)
    with pytest.raises(ValueError, match='manifest exceeds 8 MiB'):
        owner.project.save(destination)
    assert destination.read_bytes() == retained_destination
    assert owner.data == oversized and not owner.project.in_save
    assert editor._object('CurvedPatch').Shape.text == shape
    assert entry.read_bytes() == native_bytes
    assert (inputs/'source/design.caepre').read_bytes() == archive_bytes
