"""Portable declared-input tests; no MFront/Code_Aster/CalculiX execution."""
from copy import deepcopy
import importlib
from pathlib import Path
import subprocess

import pytest

from caelab.model_parameters import _validated_inputs, _locations, bind, ModelInputRejected
from plugins.material_point import reference as elastic, viscoelastic_reference as maxwell
from plugins.hyperelastic import reference as hyper
from plugins.geometric_nonlinearity import reference as geometric
from plugins.structural_families import reference as families
from test_plasticity_response_fields import settings as plastic_settings


def cases():
    family = families.specification(next(iter(families._definitions()['cases'])))
    from test_contact_patch_reference import settings as contact_settings
    contact = contact_settings()
    return [
        ('mfront_material', 'MFrontMaterialAdapter', elastic.canonical_settings()),
        ('mfront_hyperelastic', 'MFrontHyperelasticAdapter', hyper.canonical_settings()),
        ('mfront_viscoelastic', 'MFrontViscoelasticAdapter', maxwell.canonical_settings()),
        ('codeaster_plasticity', 'CodeAsterPlasticityAdapter', plastic_settings()),
        ('codeaster_geometric', 'CodeAsterGeometricAdapter', geometric.default_settings()),
        ('codeaster_contact', 'CodeAsterContactPatchAdapter', contact),
        ('structural_family_codeaster', 'StructuralFamilyCodeAsterAdapter', family),
        ('structural_family_calculix', 'StructuralFamilyCalculiXAdapter', family),
    ]


@pytest.fixture(autouse=True)
def prohibit_native(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Declared scalar editing must not start a native process')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)


@pytest.mark.parametrize('module,klass,settings', cases())
def test_actual_domain_scalar_contract_and_core_binding(module, klass, settings):
    adapter = getattr(importlib.import_module('caelab.adapters.' + module), klass)()
    original = deepcopy(settings)
    descriptors = _validated_inputs(adapter.describe_inputs(settings))
    assert 1 <= len(descriptors) <= 32
    _locations(descriptors, settings, adapter.describe_model(settings))
    assert adapter.input_source_files and all(Path(p).is_file() for p in adapter.input_source_files)
    for descriptor in descriptors:
        value = descriptor['value']
        candidate = float(value) * 1.00001 if value != 0 else 1e-8
        if descriptor['id'] in ('final_axial_strain', 'final_moment_n_mm'):
            candidate = float(value) * .99999
        bound = bind(adapter, settings, {descriptor['id']: candidate})
        assert settings == original
        assert bound != settings
        assert bound.get('limits') == settings.get('limits')
        assert bound.get('mesh_cells') == settings.get('mesh_cells')
        _locations(_validated_inputs(adapter.describe_inputs(bound)), bound, adapter.describe_model(bound))


def test_binding_rejects_unknown_paths_bounds_nonfinite_and_invalid_tensor():
    adapter = importlib.import_module('caelab.adapters.mfront_hyperelastic').MFrontHyperelasticAdapter()
    settings = hyper.canonical_settings()
    for assignment in ({'limits.finite_difference_relative': 1.}, {'temperature_k': float('nan')},
                       {'youngs_modulus_mpa': -1.}, {'final_deformation_gradient_xx': -1.}):
        with pytest.raises(ValueError):
            bind(adapter, settings, assignment)
    assert settings['limits'] == hyper.canonical_settings()['limits']


def test_final_history_only_initial_state_and_other_samples_remain_frozen():
    adapter = importlib.import_module('caelab.adapters.mfront_viscoelastic').MFrontViscoelasticAdapter()
    settings = maxwell.canonical_settings()
    bound = bind(adapter, settings, {'final_strain_xy': .0001, 'relaxation_time_s': .4})
    assert bound['history'][:-1] == settings['history'][:-1]
    assert bound['history'][0] == settings['history'][0]
    assert len(adapter.describe_inputs(settings)) == 13


def test_j2_derived_displacement_uses_domain_not_raw_strain_relabel():
    adapter = importlib.import_module('caelab.adapters.codeaster_plasticity').CodeAsterPlasticityAdapter()
    settings = plastic_settings(selected=True)
    changed = bind(adapter, settings, {'final_axial_strain': -.0002})
    declared = adapter.describe_model(changed)
    assert declared['history']['axial_strain'][-1] == -.0002
    assert declared['loads'][0]['values_mm'][-1] == -.0002 * settings['dimensions_mm'][0]
    assert adapter.expected_input_declaration(changed) == declared


def test_family_derived_loads_keep_original_fixed_material_and_mesh():
    adapter = importlib.import_module('caelab.adapters.structural_family_calculix').StructuralFamilyCalculiXAdapter()
    settings = families.specification(next(iter(families._definitions()['cases'])))
    changed = bind(adapter, settings, {'load_factor': 1.25})
    before, after = adapter.describe_model(settings), adapter.describe_model(changed)
    assert before['model'] == after['model']
    assert before['loads'] != after['loads']
    assert after['reference']['load_factor'] == 1.25
    assert [x['id'] for x in adapter.describe_inputs(settings)] == ['load_factor']
