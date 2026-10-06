"""Freeze one verified scalar observation into an explicit numerical target.

Field IDs, history indices and coordinate alignment are not transferable scalar
objectives. The existing immutable model/condition binding owns every candidate.
"""
from copy import deepcopy

from .response_comparison import _path, _sha
from .storage import canonical_hash, load_json


def _numeric_template(settings, descriptors):
    """JSON int/integral-float equivalence only at advertised scalar locations."""
    from .model_parameters import _finite, _leaf, _validated_inputs
    value = deepcopy(settings)
    for descriptor in _validated_inputs(deepcopy(descriptors)):
        parent, key, scalar = _leaf(value, descriptor['settings_path'])
        if not _finite(scalar) or not descriptor['lower'] <= scalar <= descriptor['upper']:
            raise ValueError('Observed model template has an invalid advertised scalar')
        # Converting an integral float to int preserves its exact numeric value.
        # Converting arbitrary ints to float could silently round large values.
        if type(scalar) is float and scalar.is_integer():
            parent[key] = int(scalar)
    return canonical_hash(value)


def freeze(lab, plan, comparison_id):
    record = lab.inspect_response_comparison(comparison_id)
    request, comparison, source = record['request'], record['comparison'], record['source']
    objective = plan['objective']
    if (source['study_id'] != plan['study_id'] or comparison['selection_kind'] != 'SCALAR_METRIC'
            or comparison['status'] != 'NUMERIC_DIFFERENCE_ONLY'
            or set(request['response']) != {'metric'}
            or objective.get('direction') != 'match'
            or objective['metric'] != request['response']['metric']
            or objective['unit'] != request['observation']['unit']
            or objective['target'] != request['observation']['value']):
        raise ValueError('A target requires the same study, compatible scalar, exact unit and observed value')
    origin = {'SPECIFICATION': 'DESIGN_TARGET'}.get(request['observation']['source_kind'], request['observation']['source_kind'])
    if objective['origin'] != origin or objective['reference'] != request['observation']['source']:
        raise ValueError('A saved observation target must retain its origin and reference')
    proposal = load_json(_path(lab, f"experiments/{request['experiment_id']}/proposal.json"))
    template_comparison = {'method': 'EXACT_FROZEN_FIXED_CAD_CONTEXT'}
    if plan.get('route') == 'model_analysis':
        source_template = _numeric_template(proposal['execution'], plan['model_input_descriptors'])
        planned_template = _numeric_template(plan['model_template'], plan['model_input_descriptors'])
        if (objective['source'] != 'model' or proposal['physics']['backend'] != plan['backend']
                or source_template != planned_template):
            raise ValueError('The observed scalar belongs to a different frozen model template')
        template_comparison = {'method': 'ADVERTISED_SCALAR_NUMERIC_VALUE',
            'source_settings_sha256': canonical_hash(proposal['execution']),
            'plan_settings_sha256': canonical_hash(plan['model_template']),
            'numeric_value_sha256': planned_template,
            'scope': 'Finite advertised scalar int/integral-float leaves only; no unit, axis or other setting conversion'}
        selected = {v['native']['path'] for v in plan['variables']}
        varied = [[str(k) for k in d['settings_path']] for d in plan['model_input_descriptors'] if d['id'] in selected]
        for condition in request['observation']['conditions']:
            path = condition['path']
            if (condition['source'] == 'input_parameters' and path[0] in {v['parameter_id'] for v in plan['variables']}
                    or condition['source'] == 'execution' and any(path[:len(p)] == p or p[:len(path)] == path for p in varied)):
                raise ValueError('An observation condition fixes an input selected for numerical variation')
    elif plan.get('route') == 'fixed_cad_analysis':
        # No implicit projection from old execution paths to typed condition leaves.
        if (objective['source'] != 'analysis' or request['observation']['conditions']
                or proposal.get('parent_experiment_id') != plan['fixed_cad']['source']['experiment_id']
                or proposal['physics']['backend'] != plan['fixed_cad']['backend']):
            raise ValueError('Fixed-CAD targets require the same parent/backend and no unqualified condition projection')
        result = load_json(_path(lab, f"experiments/{request['experiment_id']}/result.json"))
        if result['provenance'].get('analysis_conditions', {}).get('id') != plan['fixed_cad']['conditions_id']:
            raise ValueError('Observed response uses a different saved condition template')
    else:
        raise ValueError('Saved observations currently bind declared-model or fixed-CAD scalar searches')
    return {'comparison_id': comparison_id,
            'record_sha256': _sha(_path(lab, f'response_comparisons/{comparison_id}/record.json')),
            'source': deepcopy(source), 'observation': deepcopy(request['observation']),
            'response': deepcopy(request['response']), 'objective': deepcopy(objective),
            'template_comparison': template_comparison,
            'scope': 'VERIFIED_RECORD_USER_DECLARED_SCALAR_TARGET',
            'normalization': 'User scale; not tolerance or measured standard deviation',
            'physical_qualification': 'UNKNOWN', 'causal_verdict': 'NOT_EVALUATED'}


def verify(lab, plan):
    frozen = plan.get('observation_target')
    if frozen is not None and frozen != freeze(lab, plan, frozen['comparison_id']):
        raise ValueError('Frozen observation target differs from its verified original source')
