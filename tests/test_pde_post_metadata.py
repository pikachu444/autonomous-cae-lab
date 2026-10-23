"""Actual PDE export declarations against labelled native-reader doubles.

VTU/PVD files and registered snapshots use production exporters/registration.
ParaView's reader/state boundaries reuse the existing fixture; no native process
or physics solver is started.
"""
from copy import deepcopy
import xml.etree.ElementTree as ET

import pytest

from caelab.native_inputs import register_native_input
from caelab.pde_results import write_post_sets
from caelab.storage import load_json
from caelab.workbench_client import Client
from test_desktop_post_external import native, Array
from test_pde_workbench_results import field_fixture


@pytest.fixture
def pde_reader(native, monkeypatch):
    fake, commands, external = native
    original = fake.reader

    def reader(kind, registrationName, FileName):
        source = original(kind, registrationName, FileName)
        path = source.FileName[0]
        document = ET.parse(path)
        if kind == 'PVDReader':
            frames = document.findall('.//DataSet')
            source.TimestepValues = [float(entry.attrib['timestep']) for entry in frames]
            from pathlib import Path
            document = ET.parse(Path(path).parent / frames[0].attrib['file'])
        else:
            source.TimestepValues = []
        for label, attribute in (('PointData', 'PointData'), ('CellData', 'CellData'), ('FieldData', 'FieldData')):
            arrays = {element.attrib['Name']: Array(int(element.attrib.get('NumberOfComponents', 1)))
                      for element in document.findall('.//' + label + '/DataArray')}
            setattr(source, attribute, arrays)
        return source

    monkeypatch.setattr(fake, 'reader', reader)
    return native


def registered_set(tmp_path, external, *, temporal):
    values = []
    for step, time in enumerate([0., .25] if temporal else [None]):
        values.append({'study_index': 4, 'step_index': step if temporal else None,
                       'time': time, 'time_unit': '1' if temporal else None,
                       'field': field_fixture(1, shift=step, vector=True)})
    exported = write_post_sets(values, tmp_path / 'post')[0]
    root = tmp_path / 'workbench'
    receipt = register_native_input(root, tmp_path / 'post', exported['path'], 'Dexactpde',
                                    root_id='TEST_ONLY_EXPORT', relative=exported['path'].name,
                                    limit=1024*1024, native_metadata=exported['native_metadata'])
    # This is the existing native_input receipt shape delivered to the real reader.
    entry = root / receipt['file']
    return {'id': receipt['id'], 'path': str(entry), 'format': receipt['format'],
            'source_pins': external.pins([root / item['file'] for item in receipt['files']]),
            'native_metadata': deepcopy(receipt['native_metadata'])}


@pytest.mark.parametrize('temporal', [False, True])
def test_generated_pde_metadata_opens_saves_and_restores_exact_clock(pde_reader, tmp_path, monkeypatch, temporal):
    fake, commands, external = pde_reader
    receipt = registered_set(tmp_path, external, temporal=temporal)
    monkeypatch.setattr(Client, 'native_input', lambda client, identifier: deepcopy(receipt))
    project = external.open_registered(receipt['id'], tmp_path / 'project', 'http://127.0.0.1:9914')
    inspected = external.inspect_result(fake.active)
    assert inspected['coordinate_units'] == '1'
    assert inspected['coordinate_frame'] == 'PDE_MODEL_CARTESIAN'
    assert inspected['static'] is None  # Stationary PDE is not a fabricated mechanical load step.
    fields = {row['name']: row for row in inspected['arrays']}
    for name in ('u0', 'u1'):
        assert fields[name]['units'] == '1'
        assert fields[name]['frame'] == 'PDE_MODEL_CARTESIAN'
        assert fields[name]['measure'] == 'declared_PDE_field'
        assert fields[name]['metadata_status'] == 'DECLARED'
    if temporal:
        assert inspected['timesteps'] == [0., .25]
        assert inspected['time_units'] == '1'
        assert inspected['time'] == 0.
        assert inspected['time_semantics'] == 'DIMENSIONLESS_MODEL_TIME'
        selected = external.select_array(fake.active, 'POINTS', 'u1', time=.25)
        assert selected['time_units'] == '1' and selected['time'] == .25
        assert selected['time_semantics'] == 'DIMENSIONLESS_MODEL_TIME'
    else:
        assert inspected['timesteps'] == [] and inspected['time'] is None and inspected['time_units'] is None
        selected = external.select_array(fake.active, 'POINTS', 'u1')
        assert selected['time'] is None and selected['static'] is None
    saved = commands.save_project()
    fake.sources.clear()
    commands.restore_workspace()
    restored = external.inspect_result(fake.active)
    assert restored['time'] == selected['time'] and restored['timesteps'] == inspected['timesteps']
    assert restored['coordinate_units'] == '1'
    assert load_json(saved)['sources']['result']['native_metadata'] == receipt['native_metadata']
    assert project.is_file()


def test_dimensionless_pvd_clock_mismatch_cannot_be_relabelled(pde_reader, tmp_path, monkeypatch):
    fake, _, external = pde_reader
    receipt = registered_set(tmp_path, external, temporal=True)
    receipt['native_metadata']['time']['values'] = [0., 1.]  # Not the actual PVD clock.
    monkeypatch.setattr(Client, 'native_input', lambda client, identifier: deepcopy(receipt))
    with pytest.raises(ValueError, match='exact native PVD timesteps'):
        external.open_registered(receipt['id'], tmp_path / 'bad_project', 'http://127.0.0.1:9914')
