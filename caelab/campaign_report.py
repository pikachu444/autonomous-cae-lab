"""Verified campaign samples, explicit uncertainty declarations and saved reports."""
from copy import deepcopy
import math
from pathlib import Path

from .response_comparison import _guard_source_paths, _path, _sha
from .storage import canonical_hash, check_id, load_json, save_json, source_identity, utc_now
from .read_paths import guarded_reader


def _campaign(lab, campaign_id):
    check_id(campaign_id)
    matches = [(kind, _path(lab, f'{namespace}/{campaign_id}'))
               for namespace, kind in (('campaigns', 'doe'), ('optimizations', 'optimization'))
               if _path(lab, f'{namespace}/{campaign_id}').is_dir()]
    if len(matches) != 1:
        raise ValueError('A report requires an unambiguous saved campaign')
    kind, folder = matches[0]
    for name in ('plan.json', 'result.json'):
        _path(lab, f'{folder.relative_to(lab.store).as_posix()}/{name}')
    if not (folder/'result.json').is_file():
        raise ValueError('Complete the saved campaign before producing its statistical report')
    raw_result = load_json(folder/'result.json')
    ids = set()
    for row in raw_result.get('evaluations', raw_result.get('samples', [])):
        for key in ('cad_experiment_id', 'analysis_experiment_id', 'model_experiment_id'):
            if row.get(key):
                ids.add(check_id(row[key]))
    for identifier in ids:
        _guard_source_paths(lab, identifier)
    record = lab.inspect_doe(campaign_id) if kind == 'doe' else lab.inspect_optimization(campaign_id)
    if record != load_json(folder/'result.json'):
        raise ValueError('Campaign changed during report verification')
    return kind, folder, load_json(folder/'plan.json'), record


def _declaration(purpose, origin, reference, response_definitions, uncertainty, probability=None):
    if (not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 4096
            or origin not in ('MEASURED_REPORTED', 'PUBLISHED_REFERENCE', 'SYNTHETIC', 'DESIGN_EXPLORATION')
            or not isinstance(reference, str) or not reference.strip() or len(reference) > 2048):
        raise ValueError('Declare report purpose, data origin and reference')
    if (not isinstance(response_definitions, list) or not 1 <= len(response_definitions) <= 16
            or any(not isinstance(d, dict) or set(d) != {'metric', 'unit', 'direction'}
                   or not all(isinstance(d[k], str) and d[k].strip() for k in ('metric', 'unit'))
                   or d['direction'] not in ('minimize', 'maximize') for d in response_definitions)
            or len({d['metric'] for d in response_definitions}) != len(response_definitions)):
        raise ValueError('Select 1–16 distinct scalar responses, exact units and explicit archive directions')
    if (not isinstance(uncertainty, dict) or set(uncertainty) != {'interpretation', 'reference'}
            or uncertainty['interpretation'] not in ('DESIGN_SPACE_ONLY', 'USER_DECLARED_UNIFORM_INPUTS')
            or not isinstance(uncertainty['reference'], str) or not uncertainty['reference'].strip()
            or len(uncertainty['reference']) > 2048):
        raise ValueError('Declare design-space statistics or explicitly assumed uniform inputs')
    value = dict(purpose=purpose, origin=origin, reference=reference,
                 response_definitions=deepcopy(response_definitions), uncertainty=deepcopy(uncertainty))
    if probability is not None:
        if (type(probability) is not dict or
                set(probability) != {'marginals', 'independence', 'source', 'thresholds'}):
            raise ValueError('Probability requires exact marginals, independence, source and thresholds')
        value['probability'] = deepcopy(probability)
    canonical_hash(value)
    return value


def _bound_equal(left, right):
    """JSON integer/integral-float equality without coercion or lost integer bits."""
    if type(left) not in (int, float) or type(right) not in (int, float):
        return False
    try:
        finite = math.isfinite(left) and math.isfinite(right)
    except OverflowError:
        return False
    # Python's mixed int/float comparison is exact; converting the integer to
    # float first would incorrectly accept rounded values above 2**53.
    return finite and left == right


def _probability_analysis(kind, plan, record, declaration, samples, source):
    """Bind declared laws to every original, completed LHS point; execute nothing.

    Report/holdout seed is deliberately unrelated to the original DOE seed.
    Exact sampler replay is supported only for the installed SciPy/NumPy pair:
    historical native records need no current backend, but an unsupported
    sampler version is refused rather than relabelled as the current version.
    """
    from .optimizers import probabilistic_analysis as uq
    if kind != 'doe' or record.get('status') != 'COMPLETED_REVIEW_REQUIRED':
        raise ValueError('Probability requires a completed DOE, never adaptive optimization evaluations')
    probability = declaration['probability']
    expected_marginals = [{**{k: item[k] for k in ('parameter_id', 'unit', 'lower_bound', 'upper_bound')},
                           'distribution': 'uniform'} for item in plan['variables']]
    marginals = probability['marginals']
    if (type(marginals) is not list or len(marginals) != len(expected_marginals) or any(
            type(actual) is not dict or set(actual) != set(expected) or
            any(actual[key] != expected[key] for key in ('parameter_id', 'unit', 'distribution')) or
            any(not _bound_equal(actual[key], expected[key]) for key in ('lower_bound', 'upper_bound'))
            for actual, expected in zip(marginals, expected_marginals))):
        raise ValueError('Probability marginal order/bounds/unit differs from frozen DOE variables')
    units = uq._thresholds(probability['thresholds'])
    responses = {item['metric']: item['unit'] for item in declaration['response_definitions']}
    if any(responses.get(metric) != unit for metric, unit in units.items()):
        raise ValueError('Probability thresholds must select declared report responses with exact units')
    algorithm = plan.get('algorithm')
    keys = {'engine', 'version', 'numpy_version', 'seed', 'strength', 'optimization'}
    if (type(algorithm) is not dict or set(algorithm) != keys or
            algorithm.get('engine') != 'scipy.latin_hypercube' or
            type(algorithm.get('seed')) is not int or
            type(algorithm.get('strength')) is not int or algorithm['strength'] != 1 or
            algorithm['optimization'] is not None or
            canonical_hash(record.get('algorithm')) != canonical_hash(algorithm)):
        raise ValueError('Probability requires the exact seeded uniform LHS algorithm, not another sampler')
    if record.get('plan_sha256') != source['plan_sha256']:
        raise ValueError('Probability source plan hash differs from the verified campaign')
    seed = algorithm['seed']
    if 'seed' in plan and (type(plan['seed']) is not int or plan['seed'] != seed):
        raise ValueError('DOE seed differs from its frozen algorithm')
    frozen, rows = plan.get('samples'), record.get('samples')
    if (type(frozen) is not list or type(rows) is not list or
            not 2 <= len(frozen) <= 32 or len(frozen) != len(rows) or len(rows) != len(samples) or
            ('sample_count' in plan and
             (type(plan['sample_count']) is not int or plan['sample_count'] != len(frozen)))):
        raise ValueError('Probability requires every frozen DOE sample, including invalid outcomes')
    route = plan.get('route')
    if route not in (None, 'model_analysis', 'fixed_cad_analysis'):
        raise ValueError('Unsupported probability campaign route')
    for index, (point, row, sample) in enumerate(zip(frozen, rows, samples), 1):
        if (type(point.get('index')) is not int or point['index'] != index or
                type(row.get('index')) is not int or row['index'] != index or
                canonical_hash(point.get('values')) != canonical_hash(row.get('values')) or
                canonical_hash(point.get('values')) != canonical_hash(sample['values'])):
            raise ValueError('Probability sample index/point differs from its frozen DOE plan')
        if route == 'model_analysis':
            identifier = point.get('model_experiment_id')
            if identifier != row.get('model_experiment_id'):
                raise ValueError('Probability model sample identity differs from its frozen plan')
        elif route == 'fixed_cad_analysis':
            identifier = point.get('analysis_experiment_id') or f"E-{plan['campaign_id']}-{index:04d}"
            if (row.get('analysis_experiment_id') != point.get('analysis_experiment_id') or
                    row.get('cad_experiment_id') != point.get('cad_experiment_id')):
                raise ValueError('Probability condition sample identity differs from its frozen plan')
        else:
            if row.get('cad_experiment_id') != point.get('cad_experiment_id'):
                raise ValueError('Probability CAD sample identity differs from its frozen plan')
            identifier = row.get('analysis_experiment_id') or row.get('cad_experiment_id')
            if row.get('analysis_experiment_id') not in (None, point.get('analysis_experiment_id')):
                raise ValueError('Probability solver child differs from its frozen plan')
        if sample['id'] != identifier:
            raise ValueError('Probability row is not the original DOE sample or missing-child placeholder')
        original_sha = (row.get('model_result_sha256') if route == 'model_analysis' else
                        row.get('analysis_result_sha256') if row.get('analysis_experiment_id') else
                        row.get('cad_result_sha256') if route is None else None)
        if (original_sha is not None and source['experiment_result_sha256'].get(identifier) != original_sha):
            raise ValueError('Probability native result hash changed after campaign verification')
    design = uq.declare_samples({'marginals': deepcopy(probability['marginals']),
        'independence': probability['independence'], 'source': deepcopy(probability['source']),
        'sample_ids': [item['id'] for item in samples], 'seed': seed})
    expected_algorithm = {k: design['sampling'][k] for k in ('engine', 'version', 'numpy_version',
                                                          'strength', 'optimization')}
    expected_algorithm['seed'] = seed
    if canonical_hash(algorithm) != canonical_hash(expected_algorithm):
        raise ValueError('Frozen DOE sampler version differs from supported exact SciPy/NumPy replay')
    if canonical_hash([item['values'] for item in frozen]) != canonical_hash(
            [item['values'] for item in design['samples']]):
        raise ValueError('Frozen DOE points differ from their exact seeded LHS declaration')
    # Thresholds can select an explicit subset. They use their own complete
    # common cohort; no response is invented for rejected/missing native work.
    probability_rows = [{**deepcopy(item), 'responses': {name: deepcopy(item['responses'][name])
                                                        for name in units}} for item in samples]
    analysis = uq.analyze(design, probability_rows, probability['thresholds'])
    analysis['source_sampling'] = {'algorithm': deepcopy(algorithm),
        'plan_sha256': source['plan_sha256'], 'result_sha256': source['result_sha256'],
        'replay': 'EXACT_CURRENT_SCIPY_NUMPY_VERSION_ONLY'}
    return analysis


@guarded_reader
def _calculate(lab, campaign_id, declaration, seed, *, require_advertised=True):
    from .optimizers.campaign_analysis import summarize
    kind, folder, plan, record = _campaign(lab, campaign_id)
    if declaration['uncertainty']['interpretation'] == 'USER_DECLARED_UNIFORM_INPUTS' and kind != 'doe':
        raise ValueError('Adaptive optimization evaluations are not a uniform uncertainty sample')
    probability = 'probability' in declaration
    if probability and kind != 'doe':
        raise ValueError('Probability requires a completed DOE, never adaptive optimization evaluations')
    samples, hashes = [], {}
    backend = (plan['backend'] if plan.get('route') == 'model_analysis' else
               plan.get('analysis', {}).get('backend') if plan.get('analysis') else plan['backend'])
    adapters = {**lab.adapters, **lab.analysis_adapters, **lab.model_analysis_adapters}
    adapter = adapters.get(backend)
    if require_advertised and (adapter is None or any(
            d['metric'] not in adapter.default_metrics for d in declaration['response_definitions'])):
        raise ValueError('Report responses must be advertised by the selected campaign backend')
    for row in record.get('evaluations', record.get('samples', [])):
        # A rejected fixed-CAD condition has no analysis child. Its shared CAD
        # parent is still verified by the frozen campaign, but is not this
        # sample's response or a replacement for the missing solver result.
        identifier = (row.get('analysis_experiment_id') if plan.get('route') == 'fixed_cad_analysis'
                      else row.get('model_experiment_id') or row.get('analysis_experiment_id')
                      or row.get('cad_experiment_id'))
        result = lab.inspect_experiment(identifier) if identifier else None
        if result:
            hashes[identifier] = _sha(_path(lab, f'experiments/{identifier}/result.json'))
        metrics = result['metrics'] if result else {}
        responses = {}
        for definition in declaration['response_definitions']:
            metric = metrics.get(definition['metric'])
            if metric is None:
                responses[definition['metric']] = {'value': None, 'unit': definition['unit'], 'valid': False}
                continue
            if metric.get('unit') != definition['unit']:
                raise ValueError('Report response unit differs from the original native response')
            responses[definition['metric']] = {k: deepcopy(metric.get(k)) for k in ('value', 'unit', 'valid')}
            if probability and metric.get('reason') is not None:
                responses[definition['metric']]['reason'] = deepcopy(metric['reason'])
        from .optimization import _usable
        usable = row.get('usable', _usable(result, [], analysis=bool(row.get('analysis_experiment_id'))))
        sample_id = (row.get('model_experiment_id') or row.get('analysis_experiment_id')
                     or f"E-{campaign_id}-{row['index']:04d}")
        if not plan.get('route'):
            sample_id = identifier
        samples.append({'id': sample_id, 'values': deepcopy(row['values']),
                        'responses': responses, 'usable': usable})
    source = {'type': kind, 'plan_sha256': _sha(folder/'plan.json'), 'result_sha256': _sha(folder/'result.json'),
              'experiment_ids': sorted(hashes), 'experiment_result_sha256': hashes,
              'sample_ids': [s['id'] for s in samples]}
    variables = [{k:v[k] for k in ('parameter_id','lower_bound','upper_bound','unit')} for v in plan['variables']]
    analysis = summarize(samples, variables, declaration['response_definitions'], seed=seed)
    data = {'campaign_id': campaign_id, 'study_id': plan['study_id'], 'source': source,
            'declaration': deepcopy(declaration), 'variables': deepcopy(plan['variables']),
            'samples': samples, 'analysis': analysis}
    if probability:
        data['probability_analysis'] = _probability_analysis(kind, plan, record, declaration, samples, source)
    return data


def create(lab, *, campaign_id, report_id, purpose, origin, reference, response_definitions,
           uncertainty, seed=13, probability=None):
    check_id(report_id)
    declaration = _declaration(purpose, origin, reference, response_definitions, uncertainty, probability)
    data = _calculate(lab, campaign_id, declaration, seed)
    record = {'schema_version': '1.0', 'report_id': report_id, **data, 'seed': seed,
              'decision': 'NOT_RELEASED', 'engineering_qualification': 'UNKNOWN', 'created_utc': utc_now(),
              'provenance': source_identity(Path(__file__).resolve().parents[1])}
    canonical_hash(record)
    folder = _path(lab, f'campaign_reports/{report_id}')
    folder.mkdir(parents=True, exist_ok=False)
    save_json(folder/'record.json', record)
    save_json(folder/'receipt.json', {'report_id': report_id, 'record_sha256': _sha(folder/'record.json')})
    return _envelope(record, _sha(folder/'record.json'))


def _envelope(record, sha):
    return {**deepcopy(record), 'integrity': 'VERIFIED', 'report_sha256': sha}


@guarded_reader
def inspect(lab, report_id):
    folder = _path(lab, f'campaign_reports/{check_id(report_id)}')
    record_path = _path(lab, f'campaign_reports/{report_id}/record.json')
    receipt_path = _path(lab, f'campaign_reports/{report_id}/receipt.json')
    record, receipt = load_json(record_path), load_json(receipt_path)
    sha = _sha(record_path)
    if (receipt != {'report_id': report_id, 'record_sha256': sha} or record.get('schema_version') != '1.0'
            or record.get('report_id') != report_id or record.get('decision') != 'NOT_RELEASED'
            or record.get('engineering_qualification') != 'UNKNOWN'):
        raise ValueError('Saved research report identity/hash/verdict mismatch')
    if ('probability_analysis' in record) != ('probability' in record.get('declaration', {})):
        raise ValueError('Saved report probability declaration/analysis presence differs')
    declaration = _declaration(**record['declaration'])
    # A sealed historical report is verified against its retained native records,
    # not today's installed adapters or metric catalogue. New reports still need
    # the current advertised-response admission above.
    calculated = _calculate(lab, record['campaign_id'], declaration, record['seed'],
                            require_advertised=False)
    if any(record.get(k) != value for k, value in calculated.items()):
        raise ValueError('Saved report differs from verified native samples/plan/analysis')
    return _envelope(record, sha)


def list_reports(lab, campaign_id):
    check_id(campaign_id)
    namespace = _path(lab, 'campaign_reports')
    rows = []
    if namespace.is_dir():
        for folder in sorted(namespace.iterdir()):
            path = _path(lab, f'campaign_reports/{check_id(folder.name)}/record.json')
            record = load_json(path)
            if record.get('campaign_id') == campaign_id:
                # Detailed reading performs the complete source/analysis verification.
                rows.append({'report_id': folder.name, 'campaign_id': campaign_id,
                             'study_id': record.get('study_id'), 'integrity': 'NOT_CHECKED'})
    return rows
