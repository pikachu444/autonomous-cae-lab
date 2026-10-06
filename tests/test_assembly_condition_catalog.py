"""Catalog and shared-family source controls; no native solver acceptance."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from caelab.adapters.fixture_assembly_conditions_catalog import AssemblyConditionsCADAdapter
from caelab.adapters import fixture_assembly_conditions_catalog as module
from caelab.storage import artifact_manifest
from plugins.elasticity.conditions import validate_declaration
from plugins.elasticity.native_conditions import support as native_support


def minimal_files(tmp_path):
    # Mocked original CAD validator: these controls exercise manifest/frame/ID
    # joins. The existing original validator has its own full15-body controls.
    catalog = {'units': {'length':'mm','area':'mm^2','volume':'mm^3'}, 'frame': 'global_assembly_cartesian_mm', 'source_sha256': 'a'*64,
        'input_sha256': 'b'*64, 'interfaces': [], 'components': [{'id': 'printed_base',
        'volume_mm3': 8.0, 'bounds': {'min_mm': [0,0,0], 'max_mm': [2,2,2], 'size_mm': [2,2,2]},
        'center_of_mass_mm': [1,1,1], 'native_geometry_sha256': 'c'*64, 'faces': [{
        'id': 'printed_base:face:1:'+'d'*64, 'local_ordinal': 1, 'native_geometry_sha256': 'd'*64,
        'area_mm2': 4.0, 'center_of_mass_mm': [1,1,0], 'bounds': {'min_mm': [0,0,0],
        'max_mm': [2,2,0], 'size_mm': [2,2,0]}, 'geom_type': 'PLANE', 'orientation': 'FORWARD'}]}]}
    folder = tmp_path / 'cad'
    folder.mkdir()
    (folder/'assembly_catalog.json').write_text(json.dumps(catalog))
    (folder/'surface.json').write_text(json.dumps({'display_only': True}))
    from hashlib import sha256
    result = {'source_sha256': 'a'*64, 'input_sha256': 'b'*64, 'cad_generated': True, 'native_revision': 'e'*64,
              'catalog_sha256': sha256((folder/'assembly_catalog.json').read_bytes()).hexdigest(),
              'surface_sha256': sha256((folder/'surface.json').read_bytes()).hexdigest()}
    (folder/'result.json').write_text(json.dumps(result))
    parent = {'cad_revision': 'f'*64, 'artifacts': artifact_manifest(tmp_path, revision='f'*64)}
    return catalog, parent


def test_catalog_keeps_exact_face_native_identity_and_optional_operator_revision(tmp_path, monkeypatch):
    original, parent = minimal_files(tmp_path)
    monkeypatch.setattr(module, 'validate_catalog', lambda c,s: None)
    retained = {'cad_revision': 'f'*64, 'mesh_revision': '1'*64, 'active_components': ['printed_base'], 'profile': 'coarse3'}
    adapter = AssemblyConditionsCADAdapter(retained)
    catalog = adapter.conditions_catalog(tmp_path, parent, {})
    assert catalog['selections'][1]['catalog_face_id'] == original['components'][0]['faces'][0]['id']
    assert catalog['selections'][1]['id'] == 'S-printed_base-1'
    assert catalog['selections'][1]['native_ordinal'] == 1
    assert catalog['retained_mesh'] == retained
    assert catalog['native_frame_mapping']['sensor_world_alignment'] == 'UNKNOWN'
    retained['mesh_revision'] = '2'*64
    assert adapter.conditions_catalog(tmp_path, parent, {})['retained_mesh']['mesh_revision'] == '1'*64
    assert 'retained_mesh' not in AssemblyConditionsCADAdapter().conditions_catalog(tmp_path, parent, {})
    assert 'retained_mesh' not in AssemblyConditionsCADAdapter({'cad_revision': '0'*64}).conditions_catalog(tmp_path, parent, {})


def test_catalog_rejects_changed_manifest_before_native_body_validation(tmp_path, monkeypatch):
    _, parent = minimal_files(tmp_path)
    monkeypatch.setattr(module, 'validate_catalog', lambda c,s: pytest.fail('Manifest must be checked first'))
    with (tmp_path/'cad/assembly_catalog.json').open('a') as stream:
        stream.write(' ')
    with pytest.raises(ValueError, match='manifest'):
        AssemblyConditionsCADAdapter().conditions_catalog(tmp_path, parent, {})


def test_mixed_metadata_not_mistaken_for_selection_ids_and_retained_mesh_exact():
    catalog = {'selections': [{'id': 'A', 'roles': ['contact']}, {'id': 'B', 'roles': ['contact']}],
               'coordinate_systems': [{'id': 'global'}], 'retained_mesh': {'mesh_revision': 'a'*64}}
    declaration = {'coordinate_system': 'global', 'materials': [], 'loads': [], 'boundary_conditions': [],
                   'contact': {'mode': 'mixed', 'source': 'ASSUMED law', 'pairs': [{'selection_a': 'A',
                       'selection_b': 'B', 'law': 'bonded', 'master': 'a', 'source': 'explicit tie', 'distance_max_mm': .001}]},
                   'mesh': {'mode': 'retained', 'mesh_revision': 'a'*64}}
    validate_declaration(catalog, declaration)
    broken = deepcopy(declaration)
    broken['mesh']['mesh_revision'] = 'b'*64
    with pytest.raises(ValueError, match='Retained'):
        validate_declaration(catalog, broken)
    broken = deepcopy(declaration)
    broken['contact']['pairs'][0]['master'] = 'unknown'
    with pytest.raises(ValueError, match='master'):
        validate_declaration(catalog, broken)


def test_existing_native_solver_refuses_new_nonlinear_or_retained_modes():
    # This control tests only the additional guard, not the native-face parser.
    catalog = {'cad_backend': 'fixture.freecad', 'selections': [{'id': 'B-final', 'roles': ['material']},
        {'id': 'F1', 'roles': ['boundary','load'], 'kind': 'native_face'}],
        'coordinate_systems': [{'id': 'global'}]}
    declaration = {'analysis_type': 'nonlinear_static', 'coordinate_system': 'global',
        'materials': [{'id': 'M1', 'selection_id': 'B-final', 'young_modulus_MPa': 1000.,
                     'poisson_ratio': .25, 'source': {'description':'ASSUMED'}}],
        'loads': [{'id': 'L1','selection_id':'F1','coordinate_system':'global','components':{'FX':1.,'FY':0.,'FZ':0.},'source':'ASSUMED'}],
        'boundary_conditions': [{'id': 'BC1','selection_id':'F1','coordinate_system':'global','components':{'UX':0.},'source':'ASSUMED'}],
        'contact': {'mode':'none','source':'none'}, 'mesh':{'mode':'selected','max_size_mm':3.}}
    assert native_support(catalog, declaration)['status'] == 'UNSUPPORTED_FOR_CONDITIONS'
