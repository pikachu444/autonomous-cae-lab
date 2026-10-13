"""Editable declarations for the existing structural/explicit/material adapters.

The catalogue describes the admitted model, not the availability of a solver.
No runtime is imported or started to edit, validate or reopen a document.
"""
from copy import deepcopy
from importlib import import_module

from .material_document import MaterialDocuments


CATALOG = {
    'material.mfront.user': (None, None,
        '운영자가 원문 SHA로 허용한 사용자 법칙. generic 3차원 미소변형, Pa/1/s. FE export는 별도 미지원.'),
    'structure.calculix.design': (None, None,
        'Saved native Analysis candidates: independent editable copy, mapped references, remesh and existing CalculiX execution.'),
    'structural.code_aster': ('plugins.elasticity.reference', 'native_doctor_settings',
        'Existing affine uniaxial 3D elasticity block; exact declared dimensions, mesh and traction, not arbitrary CAD elasticity.'),
    'structural.code_aster.plasticity': ('plugins.elasticity.plasticity_reference', 'selected_settings',
        'Small-strain J2 block; declared axial history and mesh. No DP, damage or contact.'),
    'structural.code_aster.geometric_nonlinearity': ('plugins.geometric_nonlinearity.reference', 'default_settings',
        'Declared geometric-nonlinearity model and original reference limits.'),
    'structural.code_aster.contact_patch': ('plugins.contact_patch.reference', None,
        'Frictionless SSNP121A contact patch; not arbitrary assembly contact or preload.'),
    'structural.families.calculix': ('plugins.structural_families.reference', 'specification',
        'Existing declared cantilever, cylinder and curved-solid families; fixed reference definitions.'),
    'structural.families.code_aster': ('plugins.structural_families.reference', 'specification',
        'The same declared structural families through Code_Aster.'),
    'explicit.openradioss': ('plugins.explicit_dynamics.reference', 'selected_history_settings',
        'Rigid translation or the existing compliant-stop topology; explicit acceleration history. No general crash model.'),
    'material.mfront': ('plugins.material_point.reference', 'canonical_settings',
        'Existing small-strain Elasticity material point, integration and tangent checks.'),
    'material.mfront.inverse': ('plugins.material_point.inverse_reference', 'canonical_settings',
        'Existing bounded MFront inverse input/observation definition.'),
    'material.mfront.hyperelastic': ('plugins.hyperelastic.reference', 'canonical_settings',
        'Existing finite-strain hyperelastic material point and tangent convention.'),
    'material.mfront.viscoelastic': ('plugins.material_point.viscoelastic_reference', 'canonical_settings',
        'Existing single-branch Maxwell material point; delayed recovery is time dependent.'),
    'thermal.fenicsx.rectangle': (None, None,
        'Steady SI conduction on a declared rectangle; actual solved temperature, optional Picard conductivity.'),
    'structural.fenicsx.thermoelastic_rectangle': (None, None,
        'SI plane-stress small-strain thermal expansion; explicit temperature field, CTE and stress-free temperature.'),
}
BACKENDS = tuple(CATALOG)


def _adapter(backend):
    from .backends import get_backend
    return get_backend(backend)


def default_draft(backend='structural.code_aster.plasticity'):
    if backend not in CATALOG:
        raise ValueError('Choose an explicitly supported simulation declaration')
    module, factory, _ = CATALOG[backend]
    if module is None:
        settings = _adapter(backend).default_settings()
    elif factory == 'native_doctor_settings':
        from .adapters.native_doctor import _smoke_settings
        settings = _smoke_settings(backend)
    elif factory == 'specification':
        settings = import_module(module).specification('ansys_vmd1_regular')
    elif factory:
        settings = getattr(import_module(module), factory)()
    else:
        settings = {'case': 'ssnp121a_frictionless_patch',
            'material': {'youngs_modulus_pa': 100000., 'poisson_ratio': 0.},
            'top_displacement_m': -.1,
            'limits': {'reference_relative': .01, 'force_balance_relative': 1e-6}}
    return {'backend': backend, 'settings': deepcopy(settings)}


def validate_draft(draft):
    if not isinstance(draft, dict) or set(draft) != {'backend', 'settings'}:
        raise ValueError('Simulation requires the visible backend and settings only')
    backend = draft['backend']
    if not isinstance(backend, str) or backend not in CATALOG or not isinstance(draft['settings'], dict):
        raise ValueError('Choose a supported simulation backend and an editable settings object')
    module = CATALOG[backend][0]
    return (import_module(module).validate_settings(deepcopy(draft['settings'])) if module else
            _adapter(backend).validate_settings(deepcopy(draft['settings'])))


def diagnostics(draft):
    try:
        validate_draft(draft)
    except (ValueError, TypeError, KeyError, OverflowError, ImportError) as error:
        return [{'path': 'settings', 'severity': 'error', 'message': str(error), 'blocks_evaluation': True}]
    return []


def support_details(draft):
    backend = draft.get('backend') if isinstance(draft, dict) else None
    result = {'limitations': [CATALOG[backend][2]] if isinstance(backend, str) and backend in CATALOG else ['Unsupported declared backend'],
              'readiness': 'NOT_PROBED', 'decision': 'NOT_RELEASED', 'declaration': {}, 'ports': {}}
    if not diagnostics(draft):
        module = CATALOG[backend][0]
        if module:
            result['declaration'] = import_module(module).model_declaration(deepcopy(draft['settings']))
        else:
            result['ports'] = _adapter(backend).describe_ports(deepcopy(draft['settings']))
        result['limitations'].append('Editing and declaration checks do not establish an installed backend or engineering approval.')
    return result


class SimulationDocuments(MaterialDocuments):
    kind, prefix = 'simulation', 'V'
    update_operation, evaluate_operation = 'simulation.update', 'simulation.evaluate'
    evaluation_operation = 'simulation.run'
    default_draft = staticmethod(default_draft)
    diagnostics = staticmethod(diagnostics)

    @staticmethod
    def _draft(value):
        # A captured thermal field is bounded by the existing research document limit.
        from .pde_document import PDEDocuments
        return PDEDocuments._draft(value)

    def _public(self, document):
        result = super()._public(document)
        result['simulation_support'] = support_details(document['draft'])
        return result
