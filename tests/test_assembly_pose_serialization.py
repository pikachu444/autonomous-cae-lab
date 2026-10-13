"""Explicit native serialization doubles; no FreeCAD or FE computation."""
from contextlib import nullcontext
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from apps.desktop_pre import candidate_worker as worker
from apps.desktop_pre import assembly_candidates as pose
from apps.desktop_pre import occurrence_fem as occurrence
from apps.desktop_pre import projects
from apps.desktop_pre.mesh_binding import PROPERTY_NAME


@pytest.mark.parametrize('failure', [None, 'repeat', 'cold', 'stamp', 'foreign'])
def test_candidate_pose_roundtrip_maps_original_once_and_retains_failure(tmp_path, monkeypatch, failure):
    folder = tmp_path / 'candidate'
    working = folder / 'working'
    working.mkdir(parents=True)
    source = working / 'entry.FCStd'
    source.write_bytes(b'original candidate copy')
    external = tmp_path / 'unrelated.FCStd'
    external.write_bytes(b'unrelated open document')
    events, live, current = [], {}, {'owner': None}
    recipe = {'analysis_id': 'Analysis',
              'meshes': [{'object_id': 'Mesh', 'body_id': 'Body'}],
              'assembly': {'connection': {'assembly_id': 'Assembly', 'bodies': [
                  {'body_id': 'Body', 'mesh_id': 'Mesh'}]}, 'variable_id': 'pose', 'unit': 'rad'},
              'correspondence': {'original': 'frozen recipe targets'}}
    original_recipe = deepcopy(recipe)
    unrelated = NS(Name='Unrelated', FileName=str(external))
    live[unrelated.Name] = unrelated

    def document(name, entry, state):
        doc = NS(Name=name, FileName=str(entry), state=deepcopy(state),
                 recompute=lambda: events.append(('recompute', name)))
        body = NS(Name='Body')
        def recompute_body():
            value = 'stable'
            if failure == 'repeat' and name == 'placement':
                value += ':' + str(len(events))
            if failure == 'cold' and name == 'stable':
                value = 'changed after final restore'
            doc.state['brep'] = value
            events.append(('support', name))
            return True
        body.recompute = recompute_body
        mesh = NS(Name='Mesh')
        setattr(mesh, PROPERTY_NAME, state['stamp'])
        if failure == 'stamp' and name == 'placement':
            setattr(mesh, PROPERTY_NAME, 'silently rebound old mesh')
        assembly = NS(Name='Assembly', solve=lambda flag: events.append(('solve', name)) or 0)
        analysis = NS(Name='Analysis')
        doc.objects = {'Body': body, 'Mesh': mesh, 'Assembly': assembly, 'Analysis': analysis}
        body.document = doc
        doc.getObject = doc.objects.get
        live[name] = doc
        return doc

    original = document('original', source, {'brep': 'before-axis-angle-restore',
                        'targets': 'original', 'stamp': 'old-mesh-association'})

    def open_document(entry):
        entry = Path(entry)
        state = json.loads(entry.read_text(encoding='utf-8'))
        return document(entry.parent.name, entry, state)

    def close_document(name):
        # The real owner must have detached before its C++ document disappears.
        assert ('owner-close', name) in events
        events.append(('close-document', name))
        del live[name]
    app = NS(openDocument=open_document, closeDocument=close_document,
             setActiveDocument=lambda name: events.append(('activate', name)),
             listDocuments=lambda: dict(live),
             Units=NS(Quantity=lambda value: NS(Value=float(value.split()[0]),
                                                getValueAs=lambda unit: NS(Value=float(value.split()[0])))))
    gui = NS()

    def owner_factory(doc, export_root, **kwargs):
        assert kwargs.get('App', app) is app
        owner = NS(doc=doc, App=app, Gui=gui, _object=doc.getObject,
                   close=lambda: events.append(('owner-close', doc.Name)))
        def save(path):
            # Unmapped metadata must survive the FIRST save/read.
            assert doc.state['targets'] == ('original' if Path(path).stem == 'placement' else 'stable')
            events.append(('save', Path(path).stem, doc.Name))
            Path(path).write_text(json.dumps(doc.state), encoding='utf-8')
            return {'retained_project': str(path), 'unavailable_dependencies': []}
        owner.project = NS(save=save, _documents=lambda: [doc, unrelated] if failure == 'foreign' else [doc])
        return owner

    original_owner = owner_factory(original, working)
    current['owner'] = original_owner
    def adopt(value):
        current['owner'] = value
        events.append(('adopt', value.doc.Name if value else None))

    def unpack(path, destination):
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=False)
        entry = destination / 'entry.FCStd'
        entry.write_bytes(Path(path).read_bytes())
        return {}, entry

    def apply(owner, correspondence):
        assert correspondence is recipe['correspondence']
        assert owner is current['owner'] and owner.doc.Name == 'placement'
        assert owner.doc.state['targets'] == 'original'
        assert owner.doc.state['brep'] == 'stable'
        events.append(('apply-original', owner.doc.Name))
        owner.doc.state['targets'] = 'stable'
        return [{'method': 'exact occurrence source history'}]

    def contacts(owner):
        assert owner.doc.state['targets'] == owner.doc.state['brep'] == 'stable'
        events.append(('contacts', owner.doc.Name))

    monkeypatch.setattr(worker, 'Owner', owner_factory)
    monkeypatch.setattr(worker, 'unpack_project', unpack)
    monkeypatch.setattr(worker, 'apply_correspondence', apply)
    monkeypatch.setattr(worker, 'validate_original_contacts', contacts)
    monkeypatch.setattr(projects, 'exact_shape_serialization', lambda App: nullcontext())
    monkeypatch.setattr(projects, 'remember_open',
                        lambda doc, manifest, archive: events.append(('remember', doc.Name)))
    monkeypatch.setattr(pose, 'validate_definition',
                        lambda owner, saved: (owner._object('Assembly'), NS()))
    monkeypatch.setattr(pose, 'measure', lambda *a: {'value': .1, 'unit': 'rad'})
    monkeypatch.setattr(occurrence, 'binding', lambda *a: deepcopy(recipe['assembly']['connection']))
    monkeypatch.setattr(occurrence, 'validate_body',
                        lambda owner, asm, row: (NS(), owner._object('Body'), NS()))
    monkeypatch.setattr(occurrence, 'inspect_bindings',
                        lambda *a: deepcopy(recipe['assembly']['connection']))
    monkeypatch.setattr(occurrence, '_target',
                        lambda body, names: {'brep': body.document.state['brep']})

    if failure:
        match = {'repeat': 'differs', 'cold': 'differs', 'stamp': 'mesh association',
                 'foreign': 'candidate-owned'}[failure]
        with pytest.raises(ValueError, match=match):
            worker.prepare_saved_pose(original_owner, recipe, {'pose': .1}, folder, adopt_owner=adopt)
    else:
        owner, result = worker.prepare_saved_pose(
            original_owner, recipe, {'pose': .1}, folder, adopt_owner=adopt)
        assert owner is current['owner'] and owner.doc.Name == 'stable'
        assert result['state'] == 'STABLE' and result['mesh_rebound'] is False
        assert result['updated_bodies'] == ['Body']
        assert getattr(owner._object('Mesh'), PROPERTY_NAME) == 'old-mesh-association'
        assert [event for event in events if event[0] == 'save'] == [
            ('save', 'placement', 'original'), ('save', 'stable', 'placement')]
        assert [event for event in events if event[0] == 'apply-original'] == [('apply-original', 'placement')]
        assert [event[1] for event in events if event[0] == 'close-document'] == ['original', 'placement']
        assert result['verified']['measured'] == {'value': .1, 'unit': 'rad'}

    report = json.loads((folder / 'pose-save' / 'receipt.json').read_text(encoding='utf-8'))
    assert report['state'] == ('FAILED' if failure else 'STABLE')
    assert len(report['archives']) == {'foreign': 0, 'repeat': 1, 'stamp': 1}.get(failure, 2)
    for row in report['archives']:
        assert worker.sha(row['path']) == row['sha256']
    assert recipe == original_recipe
    assert source.read_bytes() == b'original candidate copy'
    assert external.read_bytes() == b'unrelated open document'
    assert live['Unrelated'] is unrelated
    if failure in ('repeat', 'stamp'):
        assert not any(event[0] == 'apply-original' for event in events)
    if failure == 'cold':
        assert current['owner'].doc.Name == 'stable'
        assert len([event for event in events if event[0] == 'apply-original']) == 1
