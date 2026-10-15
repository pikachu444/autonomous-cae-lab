"""Prepare a retained numerical candidate for its original declared PDE owner.

This is a pure input binding. It neither evaluates a candidate nor changes a
document; the owner verifies the retained revision and applies the returned
draft atomically against the original input identity.
"""
from copy import deepcopy
import math

from .backends import get_backend
from .contracts import CapabilityUnavailable
from . import model_parameters, variable_binding, variable_domains
from .numerical import _variables
from .pde_document import BACKENDS
from .storage import canonical_hash, check_id


_KINDS = {'doe': 'doe', 'fit': 'fit', 'optimize': 'optimization',
          'uq': 'uq', 'epsilon': 'epsilon_optimization'}


def _original_reference(source, document):
    if not isinstance(source, dict):
        raise ValueError('The submitted Plan requires an explicitly saved PDE source')
    if 'pde_document_id' in source:
        expected = {'pde_document_id', 'saved_revision', 'input_revision', 'input_sha256'}
        identifier = source['pde_document_id']
    else:
        expected = {'kind', 'document_id', 'saved_revision', 'input_revision', 'input_sha256'}
        if source.get('kind') != 'pde':
            raise ValueError('The submitted Plan source must be a PDE document')
        identifier = source.get('document_id')
    if set(source) != expected:
        raise ValueError('PDE source requires its exact saved revision and input hash')
    check_id(identifier)
    for key in ('saved_revision', 'input_revision'):
        check_id(source[key])
    if not identifier.startswith('Q') or not isinstance(document, dict):
        raise ValueError('Select the original saved PDE document')
    if (document.get('kind') != 'pde' or document.get('id') != identifier
            or document.get('saved_revision') != source['saved_revision']
            or document.get('input_revision') != source['input_revision']
            or canonical_hash(document.get('draft')) != source['input_sha256']):
        raise ValueError('The original saved PDE input differs from the submitted Plan source')
    return {'kind': 'pde', 'document_id': identifier,
            **{key: source[key] for key in ('saved_revision', 'input_revision', 'input_sha256')}}


def _finite(value, label):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(label + ' must be an actual finite scalar number')
    return value


def _normalized_variables(value, label):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(label + ' requires declared numerical variables')
    # The same bounded declarations are used at submission, execution and read.
    # Normalization parses dimensions but never evaluates dependent values.
    return {row['id']: row for row in _variables(value)}


def prepare_candidate(run, result, candidate_id, source_document):
    """Return ``{'draft': PDE draft, 'source': adoption evidence}`` without work.

    The result is supplied by the retained-result owner. Only successful rows
    of the submitted operation are eligible; partial studies may still contain
    eligible completed rows. Fixed settings must match the saved PDE template,
    so an independently edited Plan cannot silently change the physical model
    while presenting an adoption as coefficient selection from that source.
    """
    plan = run.get('draft') if isinstance(run, dict) else None
    if not isinstance(plan, dict) or plan.get('mode') != 'request':
        raise ValueError('PDE candidate adoption requires a submitted Request Plan')
    if 'input_sha256' in run and run['input_sha256'] != canonical_hash(plan):
        raise ValueError('The retained submitted Plan input changed')
    reference = _original_reference(plan.get('model_source') or plan.get('source'), source_document)
    request = plan.get('request')
    if not isinstance(request, dict) or request.get('operation') not in _KINDS:
        raise ValueError('PDE candidates require doe, fit, optimize, uq or epsilon')
    operation = request['operation']
    inputs = request.get('inputs')
    draft = source_document['draft']
    if not isinstance(draft, dict) or set(draft) != {'backend', 'settings'}:
        raise ValueError('Original PDE draft requires its declared backend and settings')
    backend = draft['backend']
    if (backend not in BACKENDS or not isinstance(inputs, dict)
            or inputs.get('backend') != backend):
        raise ValueError('Candidate backend differs from the original supported PDE backend')
    # Fit uses independently declared experiment protocols, not a global
    # settings field. Their hash remains in the request evidence; the adopted
    # coefficients bind onto the original PDE, without adopting those protocols.
    if (operation != 'fit' or 'settings' in inputs) and canonical_hash(inputs.get('settings')) != canonical_hash(draft['settings']):
        raise ValueError('Submitted settings differ from the saved PDE template; fixed inputs cannot be silently adopted')
    if not isinstance(result, dict) or result.get('kind') != _KINDS[operation]:
        raise ValueError('Result kind differs from the submitted numerical operation')
    variables = _normalized_variables(inputs.get('variables'), 'Submitted Plan')
    actual_variables = _normalized_variables(result.get('variables'), 'Retained result')
    if variables != actual_variables:
        raise ValueError('Retained result variables, units or bounds differ from the submitted Plan')
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError('Select an exact retained candidate identity')
    rows = result.get('candidates')
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Retained result requires actual candidate rows')
    matches = [row for row in rows if row.get('candidate_id') == candidate_id]
    if len(matches) != 1:
        raise ValueError('The selected candidate must occur exactly once in the retained result')
    candidate = matches[0]
    diagnostic = candidate.get('diagnostics', {})
    if not isinstance(diagnostic, dict):
        raise ValueError('Candidate diagnostics must describe its actual evaluation')
    if (candidate.get('execution_status') != 'SUCCEEDED' or candidate.get('prediction_status')
            or diagnostic.get('evaluation_mode') == 'PREDICTED'):
        raise ValueError('Only an actually evaluated successful candidate can be adopted')
    if operation in ('fit', 'optimize', 'epsilon'):
        _finite(candidate.get('objective'), 'Search objective')
    values = candidate.get('values')
    if not isinstance(values, dict) or set(values) != set(variables):
        raise ValueError('Candidate assignments differ from the exact submitted free variable IDs')
    adapter = get_backend(backend)
    if not all(callable(getattr(adapter, name, None)) for name in
               ('describe_inputs', 'bind_inputs', 'describe_model')):
        raise CapabilityUnavailable(backend + ': no declared scalar input binding is advertised')
    descriptors = model_parameters._inputs(adapter, draft['settings'])
    by_id = {item['id']: item for item in descriptors}
    variable_binding.admit_domains(variables, descriptors)
    values = variable_binding.verify_candidate(result, variables, candidate,
                                               raw_declarations=inputs['variables'])
    # bind validates the complete declaration, mirrors, simultaneous scientific
    # admission and unchanged fixed settings. Never replace it with a path setter.
    bound = model_parameters.bind(adapter, draft['settings'], values)
    variable_binding.verify_actual_binding(candidate, adapter, draft['settings'], bound,
        required=variable_domains.typed(list(variables.values())))
    adopted = {'backend': backend, 'settings': bound}
    evidence = {'original_pde': reference, 'operation': operation,
                'result_kind': result['kind'], 'candidate_id': candidate_id,
                'parameter_assignments': deepcopy(values),
                'request_sha256': canonical_hash(request), 'result_sha256': canonical_hash(result),
                'settings_template_sha256': canonical_hash(draft['settings']),
                'bound_draft_sha256': canonical_hash(adopted),
                'model_declaration_sha256': canonical_hash(model_parameters.declaration(adapter, bound)),
                'declared_inputs': variable_binding.descriptor_evidence(descriptors, variables),
                'engineering_release': 'NOT_RELEASED'}
    if variable_domains.typed(list(variables.values())):
        evidence['domain_input'] = deepcopy(result['domain_input'])
        evidence['domain_assignment'] = deepcopy(candidate['domain_assignment'])
        evidence['input_binding'] = deepcopy(candidate['input_binding'])
    return {'draft': adopted, 'source': evidence}
