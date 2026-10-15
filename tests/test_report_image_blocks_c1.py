"""MOCK native SM API only; no ParaView render/provider/physics is executed."""
from types import SimpleNamespace
import pytest

from apps.desktop_post.report_image_blocks import inspect
from report_image_block_fixture import RawRepresentation, lookup, StringProperty, LookupProperty


def audit(raw=None, lut=None, version=(6, 2, 0)):
    return inspect(SimpleNamespace(SMProxy=raw or RawRepresentation()), lut or lookup(),
        association='POINTS', field_name='stress', version=version,
        representation_properties={'Opacity': 1., 'InterpolateScalarsBeforeMapping': 1, 'MapScalars': 1})


def assigned(raw, *, name='stress', assoc='0', lut=None, selector='/Root/Block1'):
    raw.properties['BlockColorArrayNames'].values = [selector, assoc, name]
    raw.properties['BlockLookupTables'].values = [lut or lookup()]
    return raw


@pytest.mark.parametrize('version', [(5, 13, 2), (6, 2, 0)])
def test_empty_block_settings_use_global_field(version):
    result = audit(version=version)
    assert result['status'] == 'SINGLE_GLOBAL_FIELD'
    assert result['block_lut_ids'] == []


@pytest.mark.parametrize('selector', ['/Root/Block1', '/', '//group', "//*[@cid='2']"])
def test_global_equivalent_assignments_including_parent_selectors_pass(selector):
    raw = assigned(RawRepresentation(), selector=selector)
    raw.properties['BlockMapScalars'].values = [selector, '1']
    raw.properties['BlockInterpolateScalarsBeforeMappings'].values = [selector, '1']
    raw.properties['BlockOpacities'].values = [selector, '1']
    raw.properties['BlockUseSeparateColorMaps'].values = [selector, '0']
    assert audit(raw)['block_lut_ids'] == ['lut']


@pytest.mark.parametrize('problem', ['temperature', 'association', 'solid', 'component', 'lut', 'rgb', 'direct', 'opacity', 'interpolation'])
def test_hidden_legend_or_inspector_selection_cannot_hide_incompatible_override(problem):
    raw = assigned(RawRepresentation())
    if problem == 'temperature': raw.properties['BlockColorArrayNames'].values[2] = 'temperature'
    if problem == 'association': raw.properties['BlockColorArrayNames'].values[1] = '1'
    if problem == 'solid': raw.properties['BlockColorArrayNames'].values[2] = ''
    if problem == 'component': raw.properties['BlockLookupTables'].values = [lookup('componentLut', component=2)]
    if problem == 'lut': raw.properties['BlockLookupTables'].values = [lookup('otherLut', color='hot')]
    if problem == 'rgb': raw.properties['BlockColors'].values = ['/Root/Block2', '1', '0', '0']
    if problem == 'direct': raw.properties['BlockMapScalars'].values = ['/Root/Block2', '0']
    if problem == 'opacity': raw.properties['BlockOpacities'].values = ['/Root/Block2', '0.5']
    if problem == 'interpolation': raw.properties['BlockInterpolateScalarsBeforeMappings'].values = ['/Root/Block2', '0']
    with pytest.raises(ValueError): audit(raw)


def test_same_proxy_not_currently_similar_but_independent_lut():
    with pytest.raises(ValueError): audit(assigned(RawRepresentation(), lut=lookup('independentCopy')))
    shared = lookup('shared', component=2)
    assert audit(assigned(RawRepresentation(), lut=shared), shared)['block_lut_ids'] == ['shared']


def test_reset_colorblocksby_none_removes_array_and_lut_entries():
    raw = assigned(RawRepresentation(), name='temperature')
    with pytest.raises(ValueError): audit(raw)
    # Tagged SetBlocksScalarColoringInternal(None) removes BOTH arrays and LUTs.
    raw.properties['BlockColorArrayNames'].values = []
    raw.properties['BlockLookupTables'].values = []
    assert audit(raw)['block_lut_ids'] == []


def test_dormant_incompatible_selector_is_conservatively_rejected():
    with pytest.raises(ValueError): audit(assigned(RawRepresentation(), name='temperature', selector='/Removed/Block'))


@pytest.mark.parametrize('problem', ['missing', 'wrongtype', 'wrongwidth', 'short', 'duplicates', 'nullLut', 'missingLut', 'orphanLut', 'nan', 'invalidFlag'])
def test_incomplete_or_ambiguous_native_api_is_not_success(problem):
    raw = assigned(RawRepresentation())
    if problem == 'missing': del raw.properties['BlockColors']
    if problem == 'wrongtype': raw.properties['BlockColors'] = LookupProperty()
    if problem == 'wrongwidth': raw.properties['BlockColorArrayNames'].width = 2
    if problem == 'short': raw.properties['BlockColorArrayNames'].values.pop()
    if problem == 'duplicates':
        raw.properties['BlockColorArrayNames'].values *= 2
        raw.properties['BlockLookupTables'].values *= 2
    if problem == 'nullLut': raw.properties['BlockLookupTables'].values = [None]
    if problem == 'missingLut': raw.properties['BlockLookupTables'].values = []
    if problem == 'orphanLut': raw.properties['BlockColorArrayNames'].values = []
    if problem == 'nan': raw.properties['BlockOpacities'].values = ['/', 'nan']
    if problem == 'invalidFlag': raw.properties['BlockUseSeparateColorMaps'].values = ['/', 'UNKNOWN']
    with pytest.raises(ValueError): audit(raw)


@pytest.mark.parametrize('version', [(5, 12, 0), (6, 2, 1), (6, 3, 0), (), ('6', 2, 0)])
def test_unreviewed_version_is_unknown_not_an_empty_override(version):
    with pytest.raises(ValueError): audit(version=version)
