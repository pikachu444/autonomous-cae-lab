"""Explicit scalar inputs for the existing bounded native domain adapters.

Only coefficients and the final prescribed history endpoint are editable here.
This module neither executes a native program nor edits arbitrary settings paths.
Domain validators retain all coupled admissibility checks and numerical limits.
"""
from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve()
_POSITIVE = math.nextafter(0., math.inf)
_MAX = sys.float_info.max
_POISSON = (math.nextafter(-1., math.inf), math.nextafter(.5, -math.inf))


def _domain(backend):
    if backend == 'material.mfront':
        from plugins.material_point import reference as domain
    elif backend == 'material.mfront.hyperelastic':
        from plugins.hyperelastic import reference as domain
    elif backend == 'material.mfront.viscoelastic':
        from plugins.material_point import viscoelastic_reference as domain
    elif backend == 'structural.code_aster.plasticity':
        from plugins.elasticity import plasticity_reference as domain
    elif backend == 'structural.code_aster.geometric_nonlinearity':
        from plugins.geometric_nonlinearity import reference as domain
    elif backend == 'structural.code_aster.contact_patch':
        from plugins.contact_patch import reference as domain
    elif backend in ('structural.families.code_aster', 'structural.families.calculix'):
        from plugins.structural_families import reference as domain
    else:
        raise ValueError(f'No explicit native input contract for {backend}')
    return domain


def _at(value, path):
    for part in path:
        value = value[part]
    return value


def describe(backend, settings):
    domain = _domain(backend)
    domain.validate_settings(settings)
    items = []

    def add(name, label, unit, bounds, settings_path, *declaration_paths):
        value = _at(settings, settings_path)
        items.append(dict(id=name, label=label, unit=unit, value=value,
                          lower=bounds[0], upper=bounds[1], settings_path=list(settings_path),
                          declaration_paths=[list(path) for path in declaration_paths]))

    if backend.startswith('structural.families.'):
        # Materials and geometry belong to the fixed published family definition.
        add('load_factor', 'Declared load factor', '1',
            (_POSITIVE, domain._definitions()['execution_limits']['max_load_factor']),
            ['load_factor'], ['reference', 'load_factor'])
        return items

    base = ['model', 'materials', 0]
    material_point = backend.startswith('material.mfront')
    if backend == 'material.mfront.viscoelastic':
        for key in domain.MATERIAL_KEYS:
            unit = 's' if key == 'relaxation_time_s' else 'MPa'
            add(key, key.replace('_', ' ').capitalize(), unit,
                (1e-6, 1e6 if unit == 's' else 1e9), ['material', key], base + [key])
    elif backend == 'structural.code_aster.contact_patch':
        add('youngs_modulus_pa', 'Young modulus', 'Pa', (1e4, 1e9),
            ['material', 'youngs_modulus_pa'], base + ['youngs_modulus', 'value'])
        # This contact contract requires nu==0: it is not a free parameter.
        add('top_displacement_m', 'Prescribed top vertical displacement', 'm', (-.2, -1e-4),
            ['top_displacement_m'], ['loads', 0, 'values', 1])
        return items
    else:
        limit = 1e9 if material_point else _MAX
        for key, name, unit, bounds in (
            ('youngs_modulus_mpa', 'Young modulus', 'MPa', (_POSITIVE, limit)),
            ('poisson_ratio', 'Poisson ratio', '1', _POISSON),
        ):
            leaf = [key] if material_point else [key.removesuffix('_mpa'), 'value']
            add(key, name, unit, bounds, ['material', key], base + leaf)
        if backend == 'structural.code_aster.plasticity':
            for key in ('yield_stress_mpa', 'plastic_modulus_mpa'):
                add(key, key.replace('_', ' ').capitalize(), 'MPa', (_POSITIVE, _MAX),
                    ['material', key], base + [key.removesuffix('_mpa'), 'value'])

    if material_point:
        temperature_index = {'material.mfront': 2, 'material.mfront.hyperelastic': 1,
                             'material.mfront.viscoelastic': 5}[backend]
        add('temperature_k', 'Declared constant temperature (no qualified thermal dependence)', 'K',
            (_POSITIVE, 5000.), ['temperature_k'], ['initial_conditions', temperature_index, 'value'])
        end = len(settings['history']) - 1
        tensor = 'deformation_gradient' if backend.endswith('hyperelastic') else 'strain'
        components = domain.F_COMPONENTS if tensor == 'deformation_gradient' else ('xx', 'yy', 'zz', 'xy', 'xz', 'yz')
        bound = 2. if tensor == 'deformation_gradient' else .01
        for axis, component in enumerate(components):
            add(f'final_{tensor}_{component}', f'Final {tensor.replace("_", " ")} {component}', '1',
                (-bound, bound), ['history', end, tensor, axis], ['loads', 0, 'history', end, tensor, axis])
        add('final_time_s', 'Final prescribed material history time', 's',
            (math.nextafter(settings['history'][end - 1]['time_s'], math.inf), 1e6),
            ['history', end, 'time_s'], ['loads', 0, 'history', end, 'time_s'])
    else:
        end = len(settings['history']['times_s']) - 1
        add('final_time_s', 'Final quasi-static load time parameter (not dynamics)', 's',
            (math.nextafter(settings['history']['times_s'][end - 1], math.inf), _MAX),
            ['history', 'times_s', end], ['history', 'times_s', end],
            ['loads', 0, 'times_s', end], ['outputs', 'times_s', end])
        if backend == 'structural.code_aster.plasticity':
            bounds = (-.01, .01) if settings.get('mode') == 'selected_mesh' else (
                0., math.nextafter(settings['history']['axial_strain'][end - 1], -math.inf))
            add('final_axial_strain', 'Final prescribed axial strain', '1', bounds,
                ['history', 'axial_strain', end], ['history', 'axial_strain', end])
        else:
            add('final_moment_n_mm', 'Final prescribed global Z moment', 'N mm',
                (math.nextafter(settings['history']['moments_n_mm'][end - 1], math.inf), _MAX),
                ['history', 'moments_n_mm', end], ['history', 'moments_n_mm', end],
                ['loads', 0, 'values', end])
    return items


def bind(backend, settings, values):
    from ..model_parameters import expected_settings
    bound = expected_settings(settings, describe(backend, settings), values)
    _domain(backend).validate_settings(bound)
    # Validation must not normalize unrelated editable input types or thresholds.
    return bound


def expected_declaration(backend, settings):
    """Independent pure builder for declarations with physically derived fields."""
    declaration = _domain(backend).model_declaration(settings)
    if backend == 'structural.code_aster.plasticity':
        model = {name: declaration.pop(name) for name in ('geometry', 'materials', 'mesh')}
        return {'model': model, **declaration}
    if backend.startswith('structural.families.'):
        return declaration
    if backend == 'structural.code_aster.contact_patch':
        # Native mesh overlay is read-only declared asset metadata, no solver.
        from . import codeaster_contact_worker as worker
        selected = worker.mesh_contracts.variant(settings)
        if selected is not None:
            profile = worker.selected_mesh_contract(selected)
            declaration['mesh'].update(asset_sha256=profile['mesh_sha256'], catalog_sha256=profile['catalog_sha256'],
                parent_asset_sha256=profile['parent']['mesh_sha256'], generation_recipe_sha256=profile['recipe_sha256'],
                generation_source_sha256=profile['generator_sha256'], mesh_profile_sha256=worker.REFINED_PROFILE_SHA256)
        fields = ('geometry', 'materials', 'mesh', 'sections', 'interfaces', 'contact', 'coordinate_systems')
        return {'model': {name: declaration.pop(name) for name in fields if name in declaration}, **declaration}
    raise ValueError(f'{backend} has no derived-declaration input hook')


def material_runtime_identity():
    """Read configured original MFront transport identity without launching it."""
    from . import mfront_material as transport
    image, digest, executable = transport._runtime_identity()
    binary = Path(executable).resolve(strict=True)
    return {'image_path': str(image), 'image_sha256': digest,
            'singularity': {'path': str(binary), 'sha256': transport.sha256(binary)},
            'compiler_policy': transport.COMPILER_POLICY,
            'oci_manifest_sha256': transport.OCI_MANIFEST_SHA256}


def aster_runtime_identity():
    from .codeaster_elasticity import CodeAsterElasticityAdapter
    return deepcopy(CodeAsterElasticityAdapter().input_runtime_identity())
