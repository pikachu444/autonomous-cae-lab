"""Exercise the actual NS1 writer -> Post declaration boundary without a solver."""
from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest

from test_contact_execution import model
from test_desktop_post_external import native, Array, Source
from test_ns1_pipeline import nonlinear_model, outputs
from caelab.contact_deck import validate_model
from caelab.adapters.frozen_fem import read_frd
from caelab.adapters.contact_results import write_post


@pytest.fixture
def produced(model, tmp_path):
    value = nonlinear_model(model, single=True)
    text, _, materials = outputs(value, omit={(1, 'PE')})
    raw = tmp_path / 'result.frd'
    raw.write_text(text)
    nodes, elements, _ = validate_model(value)
    frames = read_frd(raw, nodes, elements, contact_materials=materials, require_contact=False)['frames']
    metadata = write_post(tmp_path / 'post', value, frames, [])
    source = Source('PVDReader', str(tmp_path / 'post/contact.pvd'), temporal=True)
    source.TimestepValues = [.5, 1.]
    tree = ET.parse(tmp_path / 'post/frame0002.vtu')

    class WrittenArray(Array):
        def __init__(self, element):
            super().__init__(int(element.get('NumberOfComponents', '1')))
            self.element = element

        def GetComponentName(self, index):
            return self.element.get('ComponentName' + str(index), '')

    for section in ('PointData', 'CellData', 'FieldData'):
        setattr(source, section, {a.get('Name'): WrittenArray(a) for a in tree.findall('.//' + section + '/DataArray')})
    return source, metadata


def test_ns1_producer_fields_are_admitted_with_meaning_and_missing_frames(native, produced, monkeypatch):
    fake, _, external = native
    source, metadata = produced
    assert external.validate_declared_metadata(source, metadata) == metadata
    result = external._inspect_result(source, 1., metadata)
    pe = next(row for row in result['arrays'] if row['name'] == 'PEEQ_1')
    assert pe['measure'] == 'equivalent_plastic_strain' and pe['units'] == '1'
    assert pe['recovery'] == 'native integration-point extrapolation and nodal averaging'
    strain = next(row for row in result['arrays'] if row['name'] == 'EXY_1')
    assert strain['shear_convention'] == 'tensor_shear_not_engineering_shear'
    assert result['field_availability']['PE']['present_frames'] == 1
    assert result['field_availability']['PE']['total_frames'] == 2
    assert result['time_semantics'] == 'STATIC_LOAD_PARAMETER'
    monkeypatch.setattr(external, '_source_metadata', lambda item: deepcopy(metadata))
    selected = external.select_array(source, 'POINTS', 'PEEQ_1', time=1., view=fake.CreateView('RenderView'))
    assert selected['recovery'] == pe['recovery'] and selected['units'] == '1'


@pytest.mark.parametrize('damage', ['extra', 'meaning', 'count', 'policy', 'recovery', 'recovery_type', 'shear'])
def test_ns1_admission_does_not_accept_unknown_or_inconsistent_declarations(native, produced, damage):
    _, _, external = native
    source, original = produced
    metadata = deepcopy(original)
    if damage == 'extra': metadata['unrecognized'] = True
    elif damage == 'meaning': metadata['field_meanings']['PE']['unit'] = 'MPa'
    elif damage == 'count': metadata['field_availability']['PE']['present_frames'] = 3
    elif damage == 'policy': metadata['field_availability']['PE']['missing_policy'] = 'zero fill'
    elif damage == 'recovery': next(a for a in metadata['arrays'] if a['name'] == 'PEEQ_1')['recovery'] = 'integration point value'
    elif damage == 'recovery_type': next(a for a in metadata['arrays'] if a['name'] == 'PEEQ_1')['recovery'] = {}
    else: next(a for a in metadata['arrays'] if a['name'] == 'EXY_1')['shear_convention'] = 'engineering_shear'
    with pytest.raises(ValueError):
        external.validate_declared_metadata(source, metadata)
