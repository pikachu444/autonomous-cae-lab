"""Declared joint UQ and retained Sobol design comparisons.

These operations reuse SciPy sampling and Numerical's actual DOE execution. They
do not identify a physical distribution, optimize candidates or execute on read.
"""
from copy import deepcopy
import math

import numpy as np
from scipy.stats import norm, truncnorm, lognorm, qmc


def covariance_units(variables):
    """Literal product units, with no implicit unit conversion."""
    return [[a['unit'] + '*' + b['unit'] for b in variables] for a in variables]


def _matrix(declaration, variables, *, covariance=False):
    names = [v['id'] for v in variables]
    required = {'variables', 'matrix', 'units'} if covariance else {'variables', 'matrix'}
    if not isinstance(declaration, dict) or set(declaration) != required or declaration['variables'] != names:
        raise ValueError('Joint matrix requires the exact ordered variable names and fields')
    if covariance and declaration['units'] != covariance_units(variables):
        raise ValueError('Covariance units must be the ordered variable-unit products (for example MPa*mm)')
    raw = declaration['matrix']
    if (not isinstance(raw, list) or len(raw) != len(names)
            or any(not isinstance(row, list) or len(row) != len(names) for row in raw)
            or any(type(v) not in (int, float) or not math.isfinite(v) for row in raw for v in row)):
        raise ValueError('Joint matrix must contain finite nonboolean numbers')
    matrix = np.asarray(raw, dtype=float)
    if not np.array_equal(matrix, matrix.T):
        raise ValueError('Joint matrix must be symmetric')
    if covariance:
        if np.any(np.diag(matrix) <= 0):
            raise ValueError('Covariance diagonal must be positive')
        scale = np.sqrt(np.diag(matrix))
        correlation = matrix / np.outer(scale, scale)
    else:
        correlation = matrix
        if not np.all(np.diag(matrix) == 1) or np.any(abs(matrix) > 1):
            raise ValueError('Latent correlation requires unit diagonal and entries within [-1, 1]')
    eigenvalues, axes = np.linalg.eigh(correlation)
    if eigenvalues.min() < -1e-12:
        raise ValueError('Joint matrix is not positive semidefinite')
    return matrix, axes * np.sqrt(np.maximum(eigenvalues, 0))


def joint_points(variables, distributions, *, count, seed, joint):
    """Validate and generate the entire physical design before the first solve."""
    from .numerical import _number, _variables
    from .variable_domains import require_capability
    variables = _variables(variables)
    require_capability('uq', variables)
    if type(count) is not int or count < 2 or type(seed) is not int or not 0 <= seed <= 2**32-1:
        raise ValueError('UQ requires count >=2 and an unsigned seed')
    if not isinstance(distributions, dict) or set(distributions) != {v['id'] for v in variables}:
        raise ValueError('Declare one marginal for every joint variable')
    if not isinstance(joint, dict):
        raise ValueError('Declare an explicit joint family')
    family = joint.get('family')
    covariance = family == 'multivariate_normal'
    key = 'covariance' if covariance else 'correlation'
    if family not in {'multivariate_normal', 'gaussian_copula'} or set(joint) != {'family', key}:
        raise ValueError('Supported joint families: multivariate_normal covariance or explicit gaussian_copula latent correlation')
    matrix, factor = _matrix(joint[key], variables, covariance=covariance)
    uniform = qmc.LatinHypercube(len(variables), rng=np.random.default_rng(seed)).random(count)
    scores = norm.ppf(uniform) @ factor.T
    dependent_uniform = norm.cdf(scores)
    points = np.empty_like(uniform)
    for index, variable in enumerate(variables):
        law = distributions[variable['id']]
        if not isinstance(law, dict) or law.get('unit', variable['unit']) != variable['unit']:
            raise ValueError('Distribution unit differs from variable unit')
        kind = law.get('distribution')
        if covariance and kind != 'normal':
            raise ValueError('Multivariate-normal covariance requires physical normal marginals')
        if kind == 'uniform':
            low = _number(law.get('lower', variable['lower']), 'uniform lower')
            high = _number(law.get('upper', variable['upper']), 'uniform upper')
            if not variable['lower'] <= low < high <= variable['upper']:
                raise ValueError('Uniform support must lie within evaluation bounds')
            column = low + (high-low) * dependent_uniform[:, index]
        elif kind in {'normal', 'truncnorm', 'lognormal'}:
            mean = _number(law.get('mean'), 'distribution mean')
            std = _number(law.get('std'), 'distribution std')
            if std <= 0:
                raise ValueError('Distribution std must be positive')
            if covariance and not math.isclose(matrix[index,index], std*std, rel_tol=1e-12, abs_tol=0):
                raise ValueError('Covariance diagonal must equal each declared normal standard deviation squared')
            if kind == 'normal':
                column = mean + std*scores[:, index]
            elif kind == 'truncnorm':
                column = truncnorm.ppf(dependent_uniform[:,index],
                    (variable['lower']-mean)/std, (variable['upper']-mean)/std, loc=mean, scale=std)
            else:
                if mean <= 0:
                    raise ValueError('Lognormal arithmetic mean must be positive')
                sigma = math.sqrt(math.log1p((std/mean)**2))
                column = lognorm.ppf(dependent_uniform[:,index], sigma, scale=mean/math.exp(sigma*sigma/2))
        else:
            raise ValueError('Supported marginals: uniform, normal, truncnorm, lognormal')
        if not np.all(np.isfinite(column)) or np.any((column < variable['lower']) | (column > variable['upper'])):
            raise ValueError('Joint sample outside evaluation bounds; widen bounds or explicitly select bounded marginals. Tails are never clipped.')
        points[:,index] = column
    return variables, points


def probability_statistics(table, definitions, total):
    """Same full/valid/failed denominators as the existing Numerical UQ path."""
    from .numerical import _scalar, _number, EvaluationFailed
    output = []
    if definitions is None:
        inferred = {}
        for row in table['candidates']:
            for name, response in row.get('responses', {}).items():
                if response.get('kind') == 'scalar':
                    inferred[name] = {'response': name, 'unit': response['unit']}
        definitions = list(inferred.values())
    for definition in definitions:
        operator = definition.get('operator', '>')
        if operator not in {'>', '>=', '<', '<='}:
            raise ValueError('Unknown threshold operator')
        limit = _number(definition['limit'], 'threshold limit') if 'limit' in definition else None
        values = []
        for row in table['candidates']:
            try:
                values.append(_scalar(row, definition))
            except EvaluationFailed:
                pass
        value = np.asarray(values)
        missing = total-len(values)
        operation = {'>':np.greater, '>=':np.greater_equal, '<':np.less, '<=':np.less_equal}[operator]
        exceeded = int(operation(value, limit).sum()) if limit is not None else None
        output.append({'response':definition.get('response',definition.get('metric')), 'unit':definition['unit'],
            'total_count':total, 'valid_count':len(values), 'failed_count':missing,
            'failure_fraction':missing/total, 'mean':float(value.mean()) if len(value) else None,
            'std':float(value.std(ddof=1)) if len(value)>1 else None,
            'min':float(value.min()) if len(value) else None, 'max':float(value.max()) if len(value) else None,
            'quantiles':dict(zip(['q05','q50','q95'],np.quantile(value,[.05,.5,.95]).tolist())) if len(value) else {},
            'threshold':deepcopy(definition),
            'exceedance_count':exceeded,
            'exceedance_fraction_total_bounds':([exceeded/total,(exceeded+missing)/total]
                if exceeded is not None else None),
            'exceedance_fraction_valid':float(operation(value,limit).mean()) if len(value) and limit is not None else None,
            'limitations':['Statistics condition on successful evaluations; failures may bias the estimated distribution.']})
    return output


def run_joint_uq(evaluator_or_factory, variables, distributions, *, joint, independence,
                 source, settings=None, count=128, seed=0, thresholds=None,
                 correlation=None, execution=None, record=None):
    from .numerical import run_doe, _record, _number, _nullable
    if (independence != 'JOINT_USER_DECLARED' or correlation is not None
            or not isinstance(source, dict) or source.get('origin') not in
            {'ASSUMED','MEASURED_REPORTED','PUBLISHED_REFERENCE','SYNTHETIC'}
            or not isinstance(source.get('reference'), str) or not source['reference'].strip()):
        raise ValueError('Declare the joint assumption and source; legacy correlation cannot be mixed with an explicit joint')
    # Invalid threshold declarations must not spend any evaluator calls.
    if thresholds is not None:
        for definition in thresholds:
            if (not isinstance(definition, dict) or not isinstance(definition.get('response', definition.get('metric')), str)
                    or not isinstance(definition.get('unit'), str) or not definition['unit'].strip()):
                raise ValueError('Thresholds require an explicit response and physical unit')
            if definition.get('operator','>') not in {'>','>=','<','<='}:
                raise ValueError('Unknown threshold operator')
            if 'limit' in definition:
                _number(definition['limit'], 'threshold limit')
    variables, points = joint_points(variables, distributions, count=count, seed=seed, joint=joint)
    names = [v['id'] for v in variables]
    table = run_doe(evaluator_or_factory, variables, settings=settings,
                   candidates=[dict(zip(names,row)) for row in points], execution=execution)
    table.update(kind='uq', sampling={'method':'declared_joint_lhs_normal_scores', 'seed':seed,
        'count':count, 'independence':independence, 'source':deepcopy(source),
        'distributions':deepcopy(distributions), 'joint':deepcopy(joint),
        'variable_order':names, 'coordinates':'physical',
        'matrix_semantics':'physical_covariance' if joint['family']=='multivariate_normal' else 'latent_normal_correlation',
        'sample_covariance':_nullable(np.atleast_2d(np.cov(points,rowvar=False,ddof=1)).tolist()),
        'covariance_units':covariance_units(variables),
        'sample_correlation':_nullable(np.atleast_2d(np.corrcoef(points,rowvar=False)).tolist()),
        'limitations':['Gaussian copula correlation is latent normal correlation, not physical Pearson correlation of transformed marginals.',
                       'The transformed design is not a stratified LHS in physical marginals. No iid confidence interval or distribution identification is claimed.']})
    table['probability_statistics'] = probability_statistics(table, thresholds, count)
    return _record(table, record)


def sensitivity_evaluation_context(reference, resolve_document):
    """Identity of the actual submitted DOE, excluding its N-dependent points."""
    from .storage import canonical_hash
    from .numerical import _variables
    from .research_operations import validate_result_reference
    validate_result_reference(reference)
    document=resolve_document(reference['document_id'])
    run=next((r for r in document.get('runs',[]) if r.get('job_id')==reference['job_id']),None)
    draft=run.get('draft',{}) if run else {}
    if (document.get('id')!=reference['document_id'] or not run or not run.get('retention_complete')
            or any(run.get(key)!=reference[key] for key in ('input_revision','input_sha256'))
            or canonical_hash(draft)!=reference['input_sha256']):
        raise ValueError('Sobol actual evaluator requires its exact saved submitted DOE input')
    request=draft.get('request',{});inputs=request.get('inputs',{})
    if (draft.get('mode')!='request' or request.get('operation')!='doe'
            or not isinstance(inputs.get('backend'),str) or not inputs['backend']
            or not isinstance(inputs.get('settings',{}),dict)):
        # Existing single-analysis APIs still work. Such a result cannot claim
        # same-evaluator convergence until an explicit DOE context is retained.
        return None
    # Retained-point DOE can inherit variables from its sampling result. The
    # paired analyses separately verify their complete actual variable meanings.
    variables=_variables(inputs['variables']) if 'variables' in inputs else None
    return {'backend':inputs['backend'],'settings':deepcopy(inputs.get('settings',{})),
        'variables':variables,'model_source':deepcopy(draft.get('model_source',draft.get('source')))}


def compare_sobol(baseline, refined, *, source_refs=None):
    """Compare two already computed exact designs; never sample/analyze/solve."""
    from .storage import canonical_hash
    from .numerical import _variables
    for result in (baseline, refined):
        sampling = result.get('sampling', {})
        variables = _variables(result.get('variables', []))
        count = sampling.get('base_count')
        digest = result.get('matched_design_sha256', '')
        context=result.get('evaluation_context')
        if (result.get('method') != 'SALib.sobol' or type(count) is not int or count < 2
                or count & (count-1) or sampling.get('problem',{}).get('names') != [v['id'] for v in variables]
                or type(sampling.get('second_order')) is not bool
                or not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)):
            raise ValueError('Select retained matched Sobol analyses with preserved variable meanings and exact design identity')
        if (not isinstance(context,dict) or not isinstance(context.get('backend'),str)
                or not isinstance(context.get('settings'),dict)
                or result.get('evaluation_context_sha256')!=canonical_hash(context)):
            raise ValueError('Select Sobol analyses preserving the exact actual evaluator, fixed settings and model source')
        identifiers = result.get('candidate_ids', [])
        expected = count*(2*len(variables)+2 if sampling['second_order'] else len(variables)+2)
        if len(identifiers) != expected or len(set(identifiers)) != expected:
            raise ValueError('Sobol analysis has incomplete or duplicate original sample identities')
    def meanings(result):
        return [(v['id'],v['unit'],v['lower'],v['upper'],v['transform']) for v in _variables(result['variables'])]
    a,b = baseline['sampling'],refined['sampling']
    if (b['base_count'] != 2*a['base_count'] or meanings(baseline) != meanings(refined)
            or baseline['response'] != refined['response'] or a['problem'] != b['problem']
            or a['seed'] != b['seed'] or a['second_order'] != b['second_order']
            or baseline['evaluation_context']!=refined['evaluation_context']):
        raise ValueError('N/2N comparison requires the same actual evaluator/fixed settings/model, variable units/bounds/order, response, seed and second-order setting')
    rows = []
    for key in ('S1','ST','S2'):
        if key not in baseline.get('indices', {}) and key not in refined.get('indices', {}):
            continue
        aa,bb = baseline['indices'].get(key),refined['indices'].get(key)
        shape = (len(baseline['variables']),)* (2 if key == 'S2' else 1)
        if np.shape(aa) != shape or np.shape(bb) != shape:
            raise ValueError('Retained Sobol index dimensions differ')
        for index in np.ndindex(shape):
            if key=='S2' and index[0]>=index[1]:
                continue
            def at(value):
                for i in index:value=value[i]
                if value is not None and (type(value) not in (int,float) or not math.isfinite(value)):
                    raise ValueError('Retained Sobol index must be finite or explicitly undefined')
                return value
            x,y = at(aa),at(bb)
            ac = baseline['indices'].get(key+'_conf')
            bc = refined['indices'].get(key+'_conf')
            rows.append({'index':key, 'variables':[a['problem']['names'][i] for i in index],
                'N':x, '2N':y, 'difference':y-x if x is not None and y is not None else None,
                'N_confidence':at(ac) if np.shape(ac)==shape else None,
                '2N_confidence':at(bc) if np.shape(bc)==shape else None})
    return {'kind':'sensitivity_convergence', 'execution_status':'SUCCEEDED',
        'variables':deepcopy(baseline['variables']), 'response':deepcopy(baseline['response']),
        'base_counts':[a['base_count'],b['base_count']], 'comparison':rows,
        'analyses':deepcopy([baseline,refined]), 'source_refs':deepcopy(source_refs),
        'analysis_sha256':[canonical_hash(baseline),canonical_hash(refined)],
        'solver_execution':'NOT_PERFORMED', 'sampling_performed':False, 'analysis_performed':False,
        'limitations':['Finite N/2N estimate changes are a convergence comparison, not a convergence guarantee or engineering qualification. Undefined estimates remain null.']}
