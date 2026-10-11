"""Independent PDE drafts over the existing declared adapter specifications.

Editing/Undo/save do not import a solver or start a worker. Pure adapter input
checks own the expression language, units, named boundaries and mesh identity.
"""
from copy import deepcopy
from importlib import import_module
from functools import lru_cache
import json

from .material_document import MaterialDocuments


DOMAINS = {
    'pde.fenicsx.rectangle': 'pde_elliptic',
    'pde.fenicsx.nonlinear': 'pde_nonlinear',
    'pde.fenicsx.transient': 'pde_transient',
    'pde.fenicsx.vector': 'pde_vector',
    'pde.fenicsx.coupled': 'pde_coupled',
    'pde.fenicsx.imported': 'pde_imported',
}
BACKENDS = ('pde.fenicsx', *DOMAINS)


def domain_module(backend):
    return import_module('plugins.' + DOMAINS[backend] + '.reference')


def default_draft(backend='pde.fenicsx.rectangle'):
    """Create real adapter settings; selected rectangle needs no reference solve."""
    if backend == 'pde.fenicsx.rectangle':
        settings = domain_module(backend).selected_settings()
    elif backend == 'pde.fenicsx.coupled':
        settings = domain_module(backend).selected_settings()
    elif backend == 'pde.fenicsx.imported':
        # Mesh bytes must be supplied explicitly, never a fabricated CAD link.
        settings = {'problem': domain_module(backend).manufactured_problem(),
                    'mesh': {'degree': 1, 'levels': []},
                    'validation': {'max_l2_error': .02, 'min_l2_rate': 1.8,
                                   'max_h1_seminorm_error': .3, 'min_h1_rate': .9,
                                   'max_residual_relative': 1e-10}}
    elif backend == 'pde.fenicsx':
        settings = domain_module('pde.fenicsx.nonlinear').manufactured_settings(0)
        settings['problem']['weak_form'] = {
            'diffusion': 1., 'reaction': 0., 'rhs': settings['problem']['weak_form']['rhs']}
        settings['validation'] = {key: settings['validation'][key] for key in
                                 ('max_l2_error', 'min_l2_rate', 'max_residual_relative')}
    elif backend in DOMAINS:
        settings = domain_module(backend).manufactured_settings()
    else:
        raise ValueError('Unsupported declared PDE backend')
    return {'backend': backend, 'settings': deepcopy(settings)}


def validate_draft(draft):
    if not isinstance(draft, dict) or set(draft) != {'backend', 'settings'}:
        raise ValueError('PDE draft requires only backend and settings; hidden execution overrides are unsupported')
    backend, settings = draft['backend'], draft['settings']
    if not isinstance(backend, str) or backend not in BACKENDS:
        raise ValueError('Choose a supported declared PDE adapter; arbitrary Python/ODE execution is not registered here')
    if not isinstance(settings, dict):
        raise ValueError('PDE settings must be an object')
    if backend == 'pde.fenicsx':
        from .adapters.fenicsx_worker import validate_settings
        return validate_settings(deepcopy(settings))
    module = domain_module(backend)
    if backend == 'pde.fenicsx.imported':
        from .adapters.fenicsx_gmsh import prepare
        return module.validate_settings(deepcopy(settings), prepare(settings))
    return module.validate_settings(deepcopy(settings))


def diagnostics(draft):
    # Pure input checks can sample many reference coordinates/times. Cache the
    # verdict by exact serialized input so polling/read/save never reruns them.
    return deepcopy(_diagnostics_cached(json.dumps(draft, allow_nan=False, sort_keys=True)))


@lru_cache(maxsize=8)
def _diagnostics_cached(serialized):
    draft = json.loads(serialized)
    try:
        validate_draft(draft)
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, ArithmeticError) as error:
        return [{'severity': 'error', 'path': 'settings', 'message': str(error), 'blocks_evaluation': True}]
    return []


def support_details(draft):
    """Describe declared capability, separately from runtime availability."""
    return deepcopy(_support_cached(json.dumps(draft, allow_nan=False, sort_keys=True)))


@lru_cache(maxsize=8)
def _support_cached(serialized):
    draft = json.loads(serialized)
    backend = draft.get('backend')
    if not isinstance(backend, str) or backend not in BACKENDS:
        return {'limitations': ['No executable adapter is declared for this draft.'], 'declaration': None}
    if backend == 'pde.fenicsx':
        from .adapters.fenicsx_pde import _LIMITATIONS
        limits = _LIMITATIONS
    else:
        module = domain_module(backend)
        selected = isinstance(draft.get('settings'), dict) and draft['settings'].get('mode') == 'selected_mesh'
        limits = getattr(module, 'SELECTED_LIMITATIONS', None) if selected else None
        limits = limits or getattr(module, 'LIMITATIONS', getattr(module, '_LIMITATIONS', []))
    declaration = None
    if not diagnostics(draft) and backend in DOMAINS:
        module = domain_module(backend)
        if backend == 'pde.fenicsx.imported':
            from .adapters.fenicsx_gmsh import prepare
            declaration = module.model_declaration(draft['settings'], prepare(draft['settings']))
        else:
            declaration = module.model_declaration(draft['settings'])
    return {'limitations': list(limits), 'declaration': deepcopy(declaration),
            'runtime': 'Declared support; native runtime availability is checked separately at execution.',
            'expression_language': 'Bounded AST arithmetic, pi, x[0], x[1], sin/cos/exp; transient adds t. No Python eval.',
            'units': 'Declared adapters use dimensionless coordinates/fields (unit 1); labels do not convert values.'}


class PDEDocuments(MaterialDocuments):
    kind = 'pde'
    prefix = 'Q'
    update_operation = 'pde.update'
    evaluate_operation = 'pde.evaluate'
    evaluation_operation = 'pde.evaluate'
    default_draft = staticmethod(default_draft)
    diagnostics = staticmethod(diagnostics)

    def open(self, *, title='PDE research', draft=None, document_id=None, _new_id=None):
        return super().open(title=title, draft=draft, document_id=document_id, _new_id=_new_id)

    @staticmethod
    def _draft(value):
        if not isinstance(value, dict) or len(json.dumps(value, allow_nan=False).encode()) > 8 * 1024 * 1024:
            raise ValueError('A PDE draft must be a JSON object of at most 8 MiB')
        return deepcopy(value)

    @staticmethod
    def job_arguments(draft):
        # Keep exact imported mesh content/source/checksum and all native names.
        return {'backend': draft['backend'], 'settings': deepcopy(draft['settings'])}

    def _public(self, document):
        public = super()._public(document)
        public['pde_support'] = support_details(document['draft'])
        return public
