"""C1: numeric registry coexists with complete typed input/source identity.

The Lab facade in the ordinary example adds metadata/Outcome packaging only;
these ODE tests call the real retained SciPy adapter, not an algebraic double.
Fault injection below targets adapter contracts, never loosens their admission.
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from caelab import dimensioned_models as dm, model_parameters as mp, model_doe
from caelab import variable_binding as vb
from caelab.contracts import CapabilityUnavailable
from caelab.storage import canonical_hash, load_json
from examples.numerical_mixed_legacy_c1 import (
    STUDY, CAMPAIGN, make_lab, model_settings, register_rate, reference_records, run)


@pytest.fixture
def lab_adapter(tmp_path):
    lab, adapter = make_lab(tmp_path / 'lab')
    lab.create_study(STUDY, 'C1 registry', 'Preserve scalar input?', 'Full enum identity', 'Real ODE')
    return lab, adapter


def freeze(lab, settings=None, campaign=CAMPAIGN, count=2):
    return lab.plan_model_doe(study_id=STUDY, campaign_id=campaign, backend=dm.ODE,
        settings=settings or model_settings(), parameter_ids=['cooling_rate'], sample_count=count, seed=13,
        required_validations={'model': ['integration']})


def files(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in Path(folder).rglob('*')
            if p.is_file() and not p.name.endswith('.lock')}


def test_real_public_lab_numeric_describe_register_doe_saved_results(tmp_path):
    receipt = run(tmp_path / 'ordinary')
    assert receipt['discovered_numeric_ids'] == ['rate', 'ambient', 'initial']
    assert [d['id'] for d in receipt['full_descriptors']] == ['rate', 'ambient', 'initial', vb.ODE_METHOD_ID]
    assert receipt['full_descriptors'][-1]['value'] == 'RK45'
    assert receipt['calls_after_describe_register_plan'] == 0
    assert receipt['real_ode_calls'] == 4 and receipt['read_extra_solver_calls'] == 0
    assert receipt['input_effect']['status'] == 'PASS'
    assert len(set(receipt['input_effect']['bound_declaration_sha256'])) == 2
    assert all(r['max_normalized_error'] <= 1 for r in receipt['records'])


@pytest.mark.parametrize('position', [0, 1, 3])
def test_interleaved_enum_candidate_to_descriptor_is_by_id(lab_adapter, monkeypatch, position):
    lab, adapter = lab_adapter
    original = adapter.describe_inputs
    def ordered(s):
        rows = original(s)
        enum = rows.pop()
        rows.insert(position, enum)
        return rows
    monkeypatch.setattr(adapter, 'describe_inputs', ordered)
    settings = model_settings()
    description = mp.describe(lab, dm.ODE, settings)
    assert description['descriptors'] == ordered(settings)
    assert len(description['candidates']) == 3
    by_id = {r['id']: r for r in description['descriptors']}
    for candidate in description['candidates']:
        d = by_id[candidate.native['path']]
        assert all(getattr(candidate, k) == d[k] for k in ('label', 'unit', 'value', 'lower', 'upper'))
        assert vb.legacy_numeric_candidate(description, d['id']) == candidate
    # Select a later numeric input, not the first numeric or enum-list index.
    entry = lab.register_model_parameter(STUDY, dm.ODE, settings,
        'initial', 'start_temperature', '초기 기준 온도', 299., 301.)
    assert entry['native']['path'] == 'initial' and entry['unit'] == 'K'
    assert entry['current_value'] == 300. and entry['input_effect']['status'] == 'PASS'
    assert entry['input_descriptor_sha256'] == canonical_hash(ordered(settings))
    assert adapter.calls == 0


@pytest.mark.parametrize('bounds', [(0., 3.), ('RK45', 'BDF')])
def test_enum_only_legacy_selection_explains_typed_plan_before_probe(lab_adapter, monkeypatch, bounds):
    lab, adapter = lab_adapter
    before = files(lab.store)
    def forbidden(*args, **kwargs):
        raise AssertionError('An enum was passed to numeric probe')
    monkeypatch.setattr(mp, 'probe', forbidden)
    with pytest.raises(CapabilityUnavailable, match='typed Request Plan'):
        lab.register_model_parameter(STUDY, dm.ODE, model_settings(),
            vb.ODE_METHOD_ID, 'method', '적분법', *bounds)
    assert before == files(lab.store) and adapter.calls == 0


@pytest.mark.parametrize('identifier', ['missing', 2, ['rate'], None])
def test_unknown_legacy_selection_stays_rejected(lab_adapter, identifier):
    lab, adapter = lab_adapter
    with pytest.raises(ValueError, match='not advertised'):
        lab.register_model_parameter(STUDY, dm.ODE, model_settings(), identifier, 'Pbad', 'bad', 0., 1.)
    assert lab.registry(STUDY)['revision'] == 0 and adapter.calls == 0


def test_all_enum_description_has_no_numeric_candidate_but_retains_identity(lab_adapter):
    lab, adapter = lab_adapter
    s = model_settings()
    s['states'] = [{'name':'elapsed', 'label':'Elapsed time', 'unit':'s',
                    'initial':0., 'rhs':'1', 'reference':'t', 'atol':1e-9}]
    s['parameters'] = []
    description = mp.describe(lab, dm.ODE, s)
    assert not description['candidates'] and description['descriptors'][0]['id'] == vb.ODE_METHOD_ID
    assert description['declaration']['model']['solver']['method'] == 'RK45'
    with pytest.raises(CapabilityUnavailable, match='typed Request Plan'):
        vb.legacy_numeric_candidate(description, vb.ODE_METHOD_ID)
    assert adapter.calls == 0


@pytest.mark.parametrize('fault', ['value', 'choice_order', 'label', 'descriptor_order'])
def test_enum_changes_numeric_source_identity_without_filtering(lab_adapter, monkeypatch, fault):
    lab, adapter = lab_adapter
    source = model_settings()
    before = mp.describe(lab, dm.ODE, source)
    original = adapter.describe_inputs
    def altered(settings):
        rows = original(settings)
        if fault == 'choice_order': rows[-1]['choices'].reverse()
        if fault == 'label': rows[-1]['choices'][0]['label'] = 'Changed label'
        if fault == 'descriptor_order': rows.insert(0, rows.pop())
        return rows
    if fault == 'value': source['solver']['method'] = 'BDF'
    else: monkeypatch.setattr(adapter, 'describe_inputs', altered)
    after = mp.describe(lab, dm.ODE, source)
    assert [c.value for c in before['candidates']] == [c.value for c in after['candidates']]
    assert before['candidates'][0].source_sha256 != after['candidates'][0].source_sha256
    expected = canonical_hash({'fingerprint': after['fingerprint'], 'inputs': after['descriptors'],
                               'model_revision': after['revision']})
    assert all(c.source_sha256 == expected for c in after['candidates'])
    assert (before['revision'] != after['revision']) == (fault == 'value')


@pytest.mark.parametrize('fault', ['empty_choices', 'duplicate_choice', 'forged_value', 'wrong_location'])
def test_invalid_unselected_enum_is_not_ignored(lab_adapter, monkeypatch, fault):
    lab, adapter = lab_adapter
    original = adapter.describe_inputs
    def altered(settings):
        rows = original(settings); enum = rows[-1]
        if fault == 'empty_choices': enum['choices'] = []
        elif fault == 'duplicate_choice': enum['choices'].append(deepcopy(enum['choices'][0]))
        elif fault == 'forged_value': enum['value'] = 'NOT_A_METHOD'
        else: enum['settings_path'] = ['time', 'end']
        return rows
    monkeypatch.setattr(adapter, 'describe_inputs', altered)
    with pytest.raises(ValueError): lab.discover_model_parameters(dm.ODE, model_settings())
    assert adapter.calls == 0


def test_numeric_setter_cannot_change_unselected_enum_even_reversibly(lab_adapter, monkeypatch):
    lab, adapter = lab_adapter
    original = adapter.bind_inputs
    def altered(settings, values):
        s = original(settings, values)
        s['solver']['method'] = 'RK45' if s['parameters'][0]['value'] == .1 else 'BDF'
        return s
    monkeypatch.setattr(adapter, 'bind_inputs', altered)
    with pytest.raises(ValueError, match='outside its declared locations'): register_rate(lab)
    assert lab.registry(STUDY)['revision'] == 0 and adapter.calls == 0


def test_numeric_declaration_cannot_hide_enum_change(lab_adapter, monkeypatch):
    lab, adapter = lab_adapter
    original = adapter.describe_model
    def altered(settings):
        d = original(settings)
        if settings['parameters'][0]['value'] != .1: d['model']['solver']['method'] = 'BDF'
        return d
    monkeypatch.setattr(adapter, 'describe_model', altered)
    with pytest.raises(ValueError, match='frozen declaration outside selected inputs'): register_rate(lab)
    assert lab.registry(STUDY)['revision'] == 0 and adapter.calls == 0


def test_typed_enum_bind_still_uses_string_and_exact_locations(lab_adapter):
    _, adapter = lab_adapter
    settings = model_settings()
    bound = mp.bind(adapter, settings, {vb.ODE_METHOD_ID: 'DOP853', 'rate': .2})
    assert bound['solver']['method'] == 'DOP853' and settings['solver']['method'] == 'RK45'
    receipt = vb.actual_binding(adapter, settings, bound, {vb.ODE_METHOD_ID: 'DOP853', 'rate': .2})
    assert receipt['assignments'][vb.ODE_METHOD_ID] == receipt['actual_inputs'][vb.ODE_METHOD_ID] == 'DOP853'
    for value in (1, True, 'LSODA', 'rk45'):
        with pytest.raises(ValueError): mp.bind(adapter, settings, {vb.ODE_METHOD_ID: value})
    assert adapter.calls == 0


def test_changed_enum_template_refuses_saved_numeric_binding_before_solver(lab_adapter):
    lab, adapter = lab_adapter
    entry = register_rate(lab)
    before = files(lab.store)
    changed = model_settings(); changed['solver']['method'] = 'BDF'
    after = mp.describe(lab, dm.ODE, changed)
    assert entry['source_sha256'] != after['candidates'][0].source_sha256
    assert entry['model_template_revision'] != after['revision']
    with pytest.raises(ValueError, match='registered model/condition template'): freeze(lab, changed)
    with pytest.raises(ValueError, match='registered model template'):
        lab.plan_model_optimization(study_id=STUDY, campaign_id='Cstale', backend=dm.ODE,
            settings=changed, parameter_ids=['cooling_rate'], constraints=[], seed=1,
            objective={'source':'model','metric':'temperature_final','unit':'K','direction':'minimize'})
    assert before == files(lab.store) and adapter.calls == 0


@pytest.mark.parametrize('fault', ['choice_order', 'enum_actual_value', 'numeric_actual_value'])
def test_saved_plan_source_verification_rejects_later_adapter_changes(lab_adapter, monkeypatch, fault):
    lab, adapter = lab_adapter
    register_rate(lab); freeze(lab)
    before = files(lab.store)
    original = adapter.describe_inputs
    def altered(s):
        rows = original(s)
        if fault == 'choice_order': rows[-1]['choices'].reverse()
        elif fault == 'enum_actual_value': rows[-1]['value'] = 'BDF'
        else: rows[0]['value'] = .11
        return rows
    monkeypatch.setattr(adapter, 'describe_inputs', altered)
    with pytest.raises(ValueError): lab.run_doe(CAMPAIGN)
    assert before == files(lab.store) and adapter.calls == 0


@pytest.mark.parametrize('numeric_count', [32])
def test_frozen_numeric_doe_validates_full_ode_descriptor_limit_without_adapter(lab_adapter, monkeypatch, numeric_count):
    lab, adapter = lab_adapter
    settings = model_settings()
    for i in range(numeric_count - len(settings['parameters'])):
        settings['parameters'].append({'name': 'unused' + str(i), 'unit': '1', 'value': 1.})
    register_rate(lab, settings); freeze(lab, settings)
    before = files(lab.store)
    # Reading a plan must not describe/bind/probe/solve or generate candidates.
    def forbidden(*a, **kw): raise AssertionError('Frozen plan read invoked runtime')
    for name in ('describe_inputs','describe_model','bind_inputs','solve'):
        monkeypatch.setattr(adapter, name, forbidden)
    monkeypatch.setattr(model_doe, '_sample', forbidden)
    result = lab.inspect_doe(CAMPAIGN)
    assert result['status'] == 'PLANNED'
    assert len(result['plan']['model_input_descriptors']) == numeric_count + 1
    assert before == files(lab.store) and adapter.calls == 0
    with pytest.raises(ValueError):
        mp._validated_inputs(result['plan']['model_input_descriptors'])  # other backends keep 32


def test_real_legacy_model_de_with_enum_unselected(lab_adapter):
    lab, adapter = lab_adapter
    register_rate(lab)
    plan = lab.plan_model_optimization(study_id=STUDY, campaign_id='Cde', backend=dm.ODE,
        settings=model_settings(), parameter_ids=['cooling_rate'], constraints=[], seed=3,
        max_generations=1, population_size=5, required_validations={'model':['integration']},
        objective={'source':'model','metric':'temperature_final','unit':'K','direction':'minimize'})
    assert adapter.calls == 0 and plan['model_input_descriptors'][-1]['value'] == 'RK45'
    result = lab.run_optimization('Cde')
    assert result['status'] == 'COMPLETED_REVIEW_REQUIRED'
    assert 1 <= adapter.calls <= 10
    assert all(row['model_settings']['solver']['method'] == 'RK45' for row in result['evaluations'])
    records = reference_records(lab, {**plan, 'samples': result['evaluations']}, result)
    assert len(records) == adapter.calls
    old = adapter.calls
    assert canonical_hash(lab.inspect_optimization('Cde')) == canonical_hash(result)
    assert adapter.calls == old


def test_descriptor_selection_cannot_pair_corrupt_candidate(lab_adapter):
    lab, _ = lab_adapter
    d = mp.describe(lab, dm.ODE, model_settings())
    # Duplicate identities and a mislabeled numeric Candidate are not positional fallback.
    d['candidates'].append(d['candidates'][0])
    with pytest.raises(ValueError): vb.legacy_numeric_candidate(d, 'rate')
    d = mp.describe(lab, dm.ODE, model_settings())
    from dataclasses import replace
    d['candidates'][0] = replace(d['candidates'][0], unit='K')
    with pytest.raises(ValueError): vb.legacy_numeric_candidate(d, 'rate')


@pytest.mark.parametrize('kind', ['doe', 'optimization'])
def test_legacy_schema_reserves_enum_slot_without_raising_numeric_limit(lab_adapter, kind):
    from caelab.schema import validate as validate_schema
    from jsonschema.exceptions import ValidationError
    lab, _ = lab_adapter
    settings = model_settings()
    for i in range(29): settings['parameters'].append({'name':'unused'+str(i), 'unit':'1', 'value':1.})
    register_rate(lab, settings)
    if kind == 'doe':
        plan = freeze(lab, settings)
        schema = 'model-doe-plan'
    else:
        plan = lab.plan_model_optimization(study_id=STUDY, campaign_id='Climit', backend=dm.ODE,
            settings=settings, parameter_ids=['cooling_rate'], constraints=[], seed=1,
            objective={'source':'model','metric':'temperature_final','unit':'K','direction':'minimize'})
        schema = 'optimization-plan'
    assert len(plan['model_input_descriptors']) == 33
    validate_schema(schema, plan)  # 32 numeric descriptors + the real ODE enum.
    for fault in ('other_backend', '33_numeric', 'extra_numeric', 'second_enum'):
        broken = deepcopy(plan)
        descriptors = broken['model_input_descriptors']
        if fault == 'other_backend': broken['backend'] = 'some.other.backend'
        elif fault == '33_numeric': descriptors[-1] = deepcopy(descriptors[0])
        elif fault == 'extra_numeric': descriptors.append(deepcopy(descriptors[0]))
        else: descriptors[-2] = {**deepcopy(descriptors[-1]), 'id':'another-enum'}
        with pytest.raises(ValidationError): validate_schema(schema, broken)
    numeric_only = deepcopy(plan)
    numeric_only['model_input_descriptors'].pop()
    validate_schema(schema, numeric_only)  # Legacy numeric-only frozen documents still read.


def test_64_parameter_ode_still_describes_but_legacy_campaign_count_not_extended(lab_adapter):
    from jsonschema.exceptions import ValidationError
    lab, adapter = lab_adapter
    settings = model_settings()
    for i in range(61): settings['parameters'].append({'name':'unused'+str(i), 'unit':'1', 'value':1.})
    description = mp.describe(lab, dm.ODE, settings)
    assert len(description['candidates']) == 64 and len(description['descriptors']) == 65
    register_rate(lab, settings)
    with pytest.raises(ValidationError): freeze(lab, settings)
    assert not (lab.store / 'campaigns' / CAMPAIGN).exists() and adapter.calls == 0


def test_legacy_saved_numeric_doe_relocated_cold_read_no_bind_or_runtime(tmp_path):
    import shutil
    receipt = run(tmp_path / 'warm')
    moved = tmp_path / 'relocated' / 'lab'
    moved.parent.mkdir()
    shutil.move(tmp_path / 'warm' / 'lab', moved)
    before = files(moved)
    # A new Python process: no installed adapter, no solver, no new sampler or
    # typed dependency evaluation is available to manufacture retained output.
    code = r'''
import json, sys
from unittest.mock import patch
from contextlib import ExitStack
from caelab import Lab, model_parameters as mp, numerical as n, dimensioned_expression as expr
from caelab.variable_domains import VariableDomains
from caelab.adapters.dimensioned_ode import DimensionedODEAdapter
from caelab.optimizers.scipy_lhs import ScipyLatinHypercube
from caelab.storage import canonical_hash
from examples.numerical_mixed_legacy_c1 import CAMPAIGN
calls=[]
def forbidden(*a, **kw):
    calls.append(1)
    raise AssertionError('cold read invoked live binding/numerics')
with ExitStack() as stack:
    for target, attr in [(mp,'describe'),(mp,'bind'),(mp,'probe'),(n,'_candidates'),
                         (expr,'evaluate'),(VariableDomains,'resolve'),
                         (DimensionedODEAdapter,'run'),(ScipyLatinHypercube,'sample')]:
        stack.enter_context(patch.object(target, attr, forbidden))
    lab=Lab(sys.argv[1], adapters={},model_analysis_adapters={},pde_adapters={},
            analysis_adapters={},doe_adapters={},optimization_adapters={})
    result=lab.inspect_doe(CAMPAIGN)
    assert canonical_hash(result)==sys.argv[2]
    print(json.dumps({'status':'PASS','runtime_calls':len(calls), 'result_sha256':canonical_hash(result)}))
'''
    completed = subprocess.run([sys.executable, '-c', code, str(moved), receipt['result_sha256']],
        cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, timeout=45)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)['runtime_calls'] == 0
    assert before == files(moved)
