"""A loaded module receipt must match the selected child runtime exactly."""
from copy import deepcopy

import pytest

from caelab.adapters.impact_python_runtime import verify_observed


def observed():
    identity={'implementation':'cpython','version':'test3.12','pointer_bits':64,
        'prefix':'C:/selected','base_prefix':'C:/selected','dll_path':'C:/selected/python312.dll',
        'dll_sha256':'a'*64,'math_file':None,'math_origin':'built-in','math_sha256':None,
        'dependency_sha256':'b'*64}
    return [{'phase':'ENGINE','ordinal':1,'python':deepcopy(identity),'runtime_error':None}],identity


def test_actual_loaded_module_and_builtin_math_receipt():
    rows,identity=observed()
    assert verify_observed(rows,identity)['status']=='PASS'


@pytest.mark.parametrize('key,value',[
    ('dll_path','C:/other/python312.dll'),('dll_sha256','c'*64),('version','other'),
    ('math_origin','unknown'),('math_sha256','d'*64),('pointer_bits',32)])
def test_runtime_substitution_is_rejected(key,value):
    rows,identity=observed();rows[0]['python'][key]=value
    with pytest.raises(ValueError,match='differs'):verify_observed(rows,identity)


def test_query_failure_missing_or_duplicate_observation_is_not_success():
    rows,identity=observed()
    with pytest.raises(ValueError):verify_observed([],identity)
    with pytest.raises(ValueError):verify_observed(rows*2,identity)
    rows[0]['runtime_error']='OSError:lookup failed'
    with pytest.raises(ValueError,match='failed'):verify_observed(rows,identity)


def test_truncated_trace_retains_unknown_and_prior_violation(tmp_path):
    import json
    from caelab.adapters.impact_python_runtime import audit_generated_sensor
    rows,identity=observed()
    cohort={'cohesive':2,'lower_bulk':1,'upper_bulk':3}
    for row in rows:row.update(sensor_id=18,cohort=cohort,segment='0001',off=[1.,1.,1.],gate=0.,armed=False)
    rows.append({'phase':'ENGINE','ordinal':2,'sensor_id':18,'cohort':cohort,'segment':'0001',
                 'off':[.8,1.,1.],'gate':1.,'armed':False})
    trace=tmp_path/'trace.jsonl'
    raw='\n'.join(json.dumps(row) for row in rows)+'\n{"phase":'
    trace.write_text(raw,encoding='utf-8')
    policy={'cohort':cohort,'sensor_id':18}
    audit=audit_generated_sensor(trace,tmp_path/'missing.out',policy,identity)
    assert audit['python_runtime']['status']=='PASS'
    assert audit['unknown_reasons'] and audit['violations']
    assert audit['every_increment']=='VIOLATED'
    assert len(audit['trace_rows'])==2 and trace.read_text(encoding='utf-8')==raw
