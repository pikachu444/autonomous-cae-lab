"""User-law authority, actual owner save, and opt-in native build/integration."""
from copy import deepcopy
import os
import pytest
from caelab import user_material as domain
from caelab.adapters.user_mfront import UserMFrontAdapter
from caelab.material_document import diagnostics
from test_connected_evaluation_study import service,change,wait
from caelab.jobs import TERMINAL


@pytest.fixture(autouse=True)
def private_build_permissions(tmp_path,monkeypatch):
    from caelab import material_build_permission as permission
    monkeypatch.setattr(permission,'directory',lambda:tmp_path/'operator-build')


def test_local_review_permission_exact_source_and_readonly_http(service):
    from caelab import material_build_permission as permission
    wb,client=service;s=domain.default_settings()
    context=client.request('/api/workbench/material-build-context')
    assert context['grant_via_http'] is False
    folder=permission.accessible_directory(context);assert folder is not None
    assert not permission.is_admitted(s['source'],s['behaviour'])
    with pytest.raises(Exception):
        client.request('/api/workbench/material-build-context',{'source':s['source'],'allow':True})
    assert not permission.is_admitted(s['source'],s['behaviour']) and not wb.manager.list()
    permission.approve_local(folder,context,s['source'],s['behaviour'])
    assert domain.require_admission(s)==domain.source_hash(s['source'])
    altered=deepcopy(s);altered['source']+='\n'
    with pytest.raises(PermissionError):domain.require_admission(altered)
    other=deepcopy(s);other['behaviour']='Other'
    with pytest.raises(PermissionError):domain.require_admission(other)
    bad={**context,'authority_id':'0'*32}
    with pytest.raises(ValueError):permission.approve_local(folder,bad,altered['source'],s['behaviour'])
    assert not permission.is_admitted(altered['source'],s['behaviour'])
    assert permission.is_admitted(s['source'],s['behaviour']) and not wb.manager.list()


def test_user_law_edit_save_does_not_build_and_remote_cannot_grant_authority(service,monkeypatch):
    wb,client=service;monkeypatch.delenv('CAELAB_MFRONT_ALLOWED_SOURCE_SHA256',raising=False)
    source=domain.default_settings();draft={'backend':domain.BACKEND,'settings':source}
    assert diagnostics(draft)==[]
    doc=client.document_open(kind='material',title='사용자 법칙',draft=draft)
    doc=change(client,doc,'document.save')['document'];assert not wb.manager.list()
    reopened=client.document_open(kind='material',document_id=doc['id'])
    assert reopened['draft']==draft
    with pytest.raises(PermissionError):domain.require_admission(source)
    unallowed=deepcopy(source);unallowed['allow_build']=True
    assert diagnostics({'backend':domain.BACKEND,'settings':unallowed})
    started=change(client,reopened,'material.evaluate');job=started['job']['id']
    wait(lambda:client.status(job)['state'] in TERMINAL)
    result=client.document_result(doc['id'],job)
    assert result['execution_status']=='FAILED'
    assert '허용' in result['diagnostics']['reason']
    assert not list((wb.root/'results'/job).rglob('libBehaviour.so'))
    assert client.document_read(doc['id'])['draft']==draft


def test_operator_source_hash_is_exact_and_parameter_binding_pure(monkeypatch):
    s=domain.default_settings();digest=domain.source_hash(s['source'])
    monkeypatch.setenv('CAELAB_MFRONT_ALLOWED_SOURCE_SHA256',digest)
    assert domain.require_admission(s)==digest
    altered=deepcopy(s);altered['source']+='\n'
    with pytest.raises(PermissionError):domain.require_admission(altered)
    s['action']='evaluate'
    from caelab.model_parameters import bind
    result=bind(UserMFrontAdapter(),s,{'YoungModulus':2e9})
    assert result['properties'][0]['value']==2e9 and s['properties'][0]['value']==1e9
    assert result['source']==s['source'] and result['history']==s['history']


def test_wrong_native_pair_rejected():
    from types import SimpleNamespace as Obj
    from caelab.adapters.user_mfront_worker import describe
    binding=Obj(Hypothesis=Obj(Tridimensional='3d'),BehaviourType=Obj(StandardStrainBasedBehaviour='small'),
                BehaviourKinematic=Obj(SmallStrainKinematic='strain'))
    wrong=Obj(hypothesis='3d',btype='finite',kinematic='strain')
    with pytest.raises(ValueError,match='small-strain'):describe(binding,wrong)


@pytest.mark.skipif(os.environ.get('CAELAB_RUN_USER_MFRONT_NATIVE')!='1',reason='explicit admitted native source build')
def test_installed_build_only_then_explicit_integration(tmp_path,monkeypatch):
    from caelab.evaluation import run,read_result
    s=domain.default_settings()
    # Opt-in test authorizes ONLY this public source; native UI requires explicit source review.
    monkeypatch.setenv('CAELAB_MFRONT_ALLOWED_SOURCE_SHA256',domain.source_hash(s['source']))
    # Compilation must discover the real input names even with an unfinished
    # numerical mapping. This explicit native check performs no hidden run.
    original=deepcopy(s);s['properties']=[];s['external']=[]
    s['initial_internal']=['1e'];s['history'][1]['time']='1e'
    built=run(domain.BACKEND,s,output=tmp_path/'build')
    assert built['execution_status']=='SUCCEEDED',built
    assert built['responses']=={} and built['diagnostics']['constitutive']['status']=='BUILT_ONLY'
    s=domain.inputs_from_build(original,built['diagnostics']['build'])
    assert s['properties']==original['properties'] and s['external']==original['external']
    result=run(domain.BACKEND,s,output=tmp_path/'evaluation')
    assert result['execution_status']=='SUCCEEDED',result
    row=result['diagnostics']['constitutive']['steps'][0]
    assert row['initial_state']!=row['committed_state']
    for fd in row['finite_differences']:
        import numpy as np
        assert all(p['initial_state']==row['initial_state'] for p in fd['probes'])
        assert np.allclose(fd['column_values'],np.asarray(row['tangent'])[:,0],rtol=1e-7,atol=1e-3)
    assert result['responses']['stress_xx']['value'][0]==pytest.approx(1.2e6)
    assert read_result(tmp_path/'evaluation',verify='all')['diagnostics']['build']['interface']=='generic'



def test_build_discovers_mapping_before_numeric_inputs_and_exact_source_required():
    s=domain.default_settings();s['properties'][0]['value']='1e';s['history'][1]['time']='1e'
    assert domain.validate_settings(s)==s # explicit compilation does not integrate
    build={'source_sha256':domain.source_hash(s['source']),'descriptor':{'behaviour':s['behaviour'],
        'material_properties':[{'name':'YoungModulus','size':1},{'name':'NewCoefficient','size':1}],
        'external_state_variables':[{'name':'Temperature','size':1}],
        'internal_state_variables':[{'name':'memory','size':2}]}}
    mapped=domain.inputs_from_build(s,build)
    assert mapped['properties'][0]==s['properties'][0]
    assert mapped['properties'][1]=={'name':'NewCoefficient','value':'','unit':''}
    assert mapped['initial_internal']==['',''] and mapped['action']=='evaluate'
    assert s['initial_internal']==[] and s['action']=='build'
    with pytest.raises(ValueError):domain.validate_settings(mapped)
    changed=deepcopy(s);changed['source']+='\n'
    with pytest.raises(ValueError,match='현재 법칙 원문'):domain.inputs_from_build(changed,build)



def test_user_unit_error_keeps_exact_field_path():
    from caelab.material_document import diagnostics
    s=domain.default_settings();s['action']='evaluate'
    s['external'][0]['unit']='invalid_unit'
    issue=diagnostics({'backend':domain.BACKEND,'settings':s})[0]
    assert issue['path']=='settings.external.0.unit' and issue['column']==0
