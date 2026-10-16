"""C1 public saved-member replay: real bytes and production core, native doubles.

No presave runtime BREP was observed. The reconstructed string is accepted as a
historical witness ONLY because its JSON-string SHA equals the old binding.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import difflib
import hashlib
import json
import zipfile
import pytest

from b13_c1_saved_fixture import saved_editor, public_inputs, Shape
from test_b13_native_boundaries import reference_writers
from caelab.shell_model import digest, ShellError
from caelab.adapters.shell_deck import build
from caelab import native_cad
from apps.desktop_pre.shell_edit import (
    ShellEditor, _saved_brep_export_candidate, _brep_zero_identity, _saved_shape_brep)
from apps.desktop_pre.shell_freeze import _native_fragments
from apps.desktop_pre.projects import Project, OPENED


@pytest.fixture
def cold(tmp_path):
    return saved_editor(tmp_path/'replay')


def assert_ready_unchanged(editor):
    before = deepcopy(editor.owner.data)
    transactions = list(editor.owner.transactions)
    result = editor.inspect('ShellAnalysis')['records'][0]
    assert result['applied'] and result['ready'], result
    assert editor.owner.data == before and editor.owner.transactions == transactions
    return editor.effective('ShellAnalysis')


def test_exact_original_digest_recovered_not_inferred_from_digest_difference(cold):
    editor, inputs, manifest, entry, _ = cold
    original = json.loads((inputs/'stamp/saved-binding.json').read_text(encoding='utf-8'))
    current = json.loads((inputs/'stamp/current-stamp.json').read_text(encoding='utf-8'))
    stored = _saved_shape_brep(editor._object('CurvedPatch'))
    assert stored.encode('ascii') == (inputs/'stamp/saved-native-CurvedPatch.Shape.brp').read_bytes()
    candidate = _saved_brep_export_candidate(stored)
    text = editor._object('CurvedPatch').Shape.text
    assert digest(candidate) == original['mesh_source']['brep']
    assert digest(text) == current['mesh_source']['brep']
    assert digest(candidate) != digest(text)  # The recorded failure remains true.
    assert len(candidate) == 2620 and len(text) == 2622
    a, b = candidate.split(), text.split()
    differences = [(x, y) for x, y in zip(a, b) if x != y]
    assert len(a) == len(b) and differences == [('0', '-0'), ('0', '-0')]
    assert _brep_zero_identity(candidate) == _brep_zero_identity(text)
    assert hashlib.sha256(entry.read_bytes()).hexdigest() == '12e0723e2da2c519859b65e5692e8461dfcb0876616490395643a4cb62b9ac5d'


def test_original_saved_member_stamp_effective_inspect_and_native_writer_replay(cold, monkeypatch):
    editor, inputs, manifest, entry, _ = cold
    before = {p: p.read_bytes() for p in inputs.rglob('*') if p.is_file()}
    draft = editor._record('ShellAnalysis')['draft']
    recorded_current = json.loads((inputs/'stamp/current-stamp.json').read_text(encoding='utf-8'))
    assert editor._stamp(draft) == recorded_current
    assert editor._stamp(draft) != draft['binding']
    record, prepared, fixed = assert_ready_unchanged(editor)
    assert len(prepared['nodes']) == 37 and len(prepared['elements']) == 8
    assert fixed == record['draft']['fixed_nodes']
    # The actual saved applied-native binding has the same two old hashes.
    actual = editor._native_state(draft)
    assert actual != record['applied']['native']
    assert {k:v for k,v in actual.items() if k!='binding'} == {
        k:v for k,v in record['applied']['native'].items() if k!='binding'}
    reference_writers(monkeypatch)
    section, pressure, material = _native_fragments(editor, draft, prepared)
    frozen = json.loads((inputs/'source/mesh.json').read_text(encoding='utf-8'))
    assert build(frozen)[0].encode('ascii') == (inputs/'source/shell.inp').read_bytes()
    written = deepcopy(frozen)
    written.update(native_sections=section, native_pressure=pressure, native_material=material)
    assert build(written)[0] == build(frozen)[0]
    assert all(p.read_bytes() == content for p, content in before.items())
    assert editor._record('ShellAnalysis') == manifest['metadata']['shells']['ShellAnalysis']


@pytest.mark.parametrize('fault', ['source_only', 'tiny_nonzero', 'tshape_flags', 'topology_order',
    'mesh_coordinate', 'mesh_connectivity', 'mesh_id', 'source_id', 'source_placement',
    'mesh_placement', 'missing_face', 'target_edit', 'native_pressure', 'native_assignment', 'fixed_reference'])
def test_changed_physical_or_reference_inputs_still_refuse_without_mutation(cold, fault):
    editor, inputs, _, _, connectivity = cold
    doc = editor.owner.doc; draft = editor.owner.data['shells']['ShellAnalysis']['draft']
    source = doc.getObject('CurvedPatch'); mesh = doc.getObject(draft['mesh_id'])
    if fault == 'source_only': source.Shape.text = source.Shape.text.replace('400', '401')
    if fault == 'tiny_nonzero':
        source.Shape.text = source.Shape.text.replace(' 0 -0 0 1 \n', ' 0 -1e-300 0 1 \n', 1)
    if fault == 'tshape_flags': source.Shape.text = source.Shape.text.replace('0101000', '0101100', 1)
    if fault == 'topology_order': source.Shape.text = source.Shape.text.replace('+12 0 +2 0 *', '+2 0 +12 0 *')
    if fault == 'mesh_coordinate': mesh.FemMesh.Nodes[1].x += 1e-12
    if fault == 'mesh_connectivity': connectivity[1][0], connectivity[1][1] = connectivity[1][1], connectivity[1][0]
    if fault == 'mesh_id': mesh.Name = 'DifferentMesh'
    if fault == 'source_id': source.Name = 'DifferentSource'
    if fault == 'source_placement': source.pose.Base.z = 1e-12
    if fault == 'mesh_placement': mesh.pose.Base.x = 1e-12
    if fault == 'missing_face': source.Shape.names.remove('Face2')
    if fault == 'target_edit': draft['regions'][0]['face_refs'][0]['subelements'] = ['Face2']
    if fault == 'native_pressure': doc.getObject(draft['regions'][0]['pressure_id']).Pressure = '0.002'
    if fault == 'native_assignment': doc.getObject(draft['regions'][0]['geometry_id']).CAEElementIds = [1]
    if fault == 'fixed_reference':
        support = doc.new('Fixed', 'Fem::ConstraintFixed'); support.References = [(source, ('Face1',))]
        doc.getObject('ShellAnalysis').Group.append(support)
    before = deepcopy(editor.owner.data); count = len(editor.owner.transactions)
    with pytest.raises((ValueError, ShellError)):
        editor.effective('ShellAnalysis')
    assert not editor.inspect('ShellAnalysis')['records'][0]['ready']
    assert editor.owner.data == before and len(editor.owner.transactions) == count


def test_changed_source_with_unchanged_mesh_still_cannot_preview_rebind(cold):
    editor, _, _, _, _ = cold
    draft = editor._record('ShellAnalysis')['draft']
    editor._object('CurvedPatch').Shape.text = editor._object('CurvedPatch').Shape.text.replace('400', '402')
    before = deepcopy(editor.owner.data)
    with pytest.raises(ShellError, match='메시가 그대로'):
        editor.preview_rebind('ShellAnalysis', elements=draft['elements'])
    assert editor.owner.data == before and not editor._pending


@pytest.mark.parametrize('fault', ['missing_archive', 'wrong_digest', 'altered_saved_brep', 'binary_no_witness'])
def test_missing_or_unauthenticated_evidence_never_admits_the_old_hash(cold, fault):
    editor, _, _, entry, _ = cold
    if fault == 'missing_archive': entry.unlink()
    if fault == 'wrong_digest':
        for binding in (editor.owner.data['shells']['ShellAnalysis']['draft']['binding'],):
            binding['mesh_source']['brep'] = '0'*64
    if fault in ('altered_saved_brep', 'binary_no_witness'):
        with zipfile.ZipFile(entry) as archive: members = {n: archive.read(n) for n in archive.namelist()}
        key = 'CurvedPatch.Shape.brp'
        members[key] = members[key].replace(b'400.', b'401.') if fault == 'altered_saved_brep' else b'EXPLICIT_BINARY_DOUBLE_WITHOUT_ASCII_PREIMAGE'
        with zipfile.ZipFile(entry, 'w') as archive:
            for n, data in members.items(): archive.writestr(n, data)
    before = deepcopy(editor.owner.data)
    with pytest.raises(ShellError): editor.effective('ShellAnalysis')
    assert editor.owner.data == before and editor.owner.transactions == []


def configure_project_owner(editor, tmp_path, native_bytes):
    owner = editor.owner; doc = owner.doc
    owner.document_id = owner.data['document_id']; owner.generation = 0; owner.saved_generation = None
    owner.export_root = tmp_path/'exports'; owner.recovery_error = None; owner.closed = False
    owner.before_design_action = lambda _: None
    owner.find_owner = lambda _: None
    owner.Gui = NS(getDocument=lambda _: NS(getInEdit=lambda: False),
                   Selection=NS(getSelectionEx=lambda _: []))
    owner.App = NS()
    doc.saveCopy = lambda path: Path(path).write_bytes(native_bytes)
    owner.project = Project(owner)
    return owner


def test_existing_project_save_keeps_witness_across_second_cold_member_without_rebinding(cold, tmp_path):
    editor, inputs, manifest, entry, _ = cold
    assert_ready_unchanged(editor)
    original = deepcopy(editor.owner.data)
    # Simulate the next native save storing the already-restored export. That
    # member CANNOT reconstruct the older +0 preimage without retained proof.
    with zipfile.ZipFile(entry) as archive: members = {n: archive.read(n) for n in archive.namelist()}
    members['CurvedPatch.Shape.brp'] = editor._object('CurvedPatch').Shape.text.encode('ascii')
    next_native = tmp_path/'next-native.FCStd'
    with zipfile.ZipFile(next_native, 'w') as archive:
        for n, data in members.items(): archive.writestr(n, data)
    owner = configure_project_owner(editor, tmp_path, next_native.read_bytes())
    destination = tmp_path/'second.caepre'
    owner.project.save(destination)
    saved = native_cad.inspect_project(destination)
    assert saved['metadata'] == original
    proof = saved['shell_binding_evidence']
    old_digest = original['shells']['ShellAnalysis']['draft']['binding']['mesh_source']['brep']
    assert digest(proof['breps'][old_digest]) == old_digest
    fresh, _, second_manifest, second_entry, _ = saved_editor(tmp_path/'second-replay', project=destination)
    # Exercise the actual Project.attach_opened integration, not a mock restore.
    fresh._binding_breps.clear()
    with pytest.raises(ShellError): fresh.effective('ShellAnalysis')
    fresh_owner = configure_project_owner(fresh, tmp_path/'fresh', second_entry.read_bytes())
    OPENED[fresh_owner.doc.Name] = (fresh_owner.doc, deepcopy(second_manifest), str(destination))
    fresh_owner.project.attach_opened()
    assert_ready_unchanged(fresh)
    assert fresh.owner.data == original and fresh.owner.transactions == []
    assert (inputs/'source/design.caepre').read_bytes() != destination.read_bytes()
    assert native_cad.sha(inputs/'source/design.caepre') == 'd61e873dea8109d6bce772ec23fd55f8d19e4b5827f77e53a0557244df44d712'


def test_late_evidence_restore_does_not_replace_new_raw_edit_or_old_applied(cold):
    editor, _, _, _, _ = cold
    evidence = editor.export_binding_evidence()
    editor.save_draft('ShellAnalysis', {'thickness_mm': '1e', 'young_MPa': '1e'})
    before = deepcopy(editor.owner.data)
    editor.restore_binding_evidence(evidence)
    assert editor.owner.data == before
    assert editor._record('ShellAnalysis')['draft']['young_MPa'] == '1e'
    with pytest.raises(ShellError): editor.effective('ShellAnalysis')


def test_evidence_cannot_authenticate_a_changed_source_or_a_different_digest(cold):
    editor, _, _, _, _ = cold
    evidence = editor.export_binding_evidence()
    corrupt = deepcopy(evidence)
    key = next(iter(corrupt['breps'])); corrupt['breps'][key] += ' '
    with pytest.raises(ValueError): editor.restore_binding_evidence(corrupt)
    assert not editor._binding_breps
    editor.restore_binding_evidence(evidence)
    editor._object('CurvedPatch').Shape.text = editor._object('CurvedPatch').Shape.text.replace('400', '403')
    with pytest.raises(ShellError): editor.effective('ShellAnalysis')


@pytest.mark.parametrize('fault', ['shape_orientation', 'location_index', 'plane_origin',
    'cylinder_axis', 'nonzero_plane_axis', 'surface_type', 'surface_count', 'unknown_surface'])
def test_signed_zero_bridge_does_not_normalize_topology_or_unproved_fields(cold, fault):
    editor, _, _, _, _ = cold
    text = editor._object('CurvedPatch').Shape.text
    lines = text.splitlines(keepends=True)
    surface = next(i for i, line in enumerate(lines) if line.startswith('Surfaces '))
    if fault == 'shape_orientation':
        changed = text.replace('+12 0 +2 0 *', '-12 0 +2 0 *')
    elif fault == 'location_index':
        changed = text.replace('+12 0 +2 0 *', '+12 -0 +2 0 *')
    elif fault == 'surface_count':
        changed = text.replace('Surfaces 10\n', 'Surfaces 11\n')
    else:
        index = surface + (1 if fault == 'cylinder_axis' else 3)
        tokens = lines[index].split()
        if fault == 'plane_origin': tokens[1] = '-0'
        if fault == 'cylinder_axis': tokens[4] = '-0'
        if fault == 'nonzero_plane_axis': tokens[4] = '0.50000000000000001'
        if fault == 'surface_type': tokens[0] = '2'
        if fault == 'unknown_surface': tokens[0] = '9'
        lines[index] = ' '.join(tokens) + (' \n' if lines[index].endswith(' \n') else '\n')
        changed = ''.join(lines)
    assert changed != text
    assert _brep_zero_identity(changed) != _brep_zero_identity(text)
    editor._object('CurvedPatch').Shape.text = changed
    with pytest.raises(ShellError): editor.effective('ShellAnalysis')


def test_retained_diagnostic_writes_authenticated_proof_and_does_not_overwrite(tmp_path):
    from examples.b13.c1_binding_probe import retained_proof
    from b13_c1_saved_fixture import ARCHIVE
    original = ARCHIVE.read_bytes()
    report = retained_proof(ARCHIVE, tmp_path/'proof')
    assert report['status'] == 'RETAINED_BYTES_PROOF_PASSED'
    assert report['native_execution'] == 'NOT_RUN' and report['windows_acceptance'] == 'NOT_RUN'
    assert report['old_candidate_bytes'] == 2620 and report['cold_recorded_bytes'] == 2622
    assert report['original_archive_unchanged'] and ARCHIVE.read_bytes() == original
    with pytest.raises(FileExistsError): retained_proof(ARCHIVE, tmp_path/'proof')
