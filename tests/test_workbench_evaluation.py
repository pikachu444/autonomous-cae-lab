import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest
from caelab import evaluate, prepare, run, read_result, list_backends
from caelab.evaluation import save_evaluation
from caelab.contracts import CapabilityUnavailable


@pytest.fixture(autouse=True)
def isolate_registered_backends(monkeypatch):
    from caelab import backends
    monkeypatch.setattr(backends,'_registry',dict(backends._registry))


def settings():
    f = np.tile(np.eye(3), (3,1,1))
    f[:,0,0] += [0,.001,.002]
    return {'time':[0,1,2], 'deformation_gradient':f.tolist(), 'stress_unit':'MPa',
            'model':'linear_elastic','parameters':{'E':1000.,'nu':.25}}


def test_default_import_and_discovery_are_lightweight():
    subprocess.run([sys.executable, '-c',
        'import sys; import caelab; caelab.list_backends(); '
        'assert not any(x in sys.modules for x in ("cadquery","mcp","scipy","felupe","caelab.engine"))'], check=True)


def test_library_material_history_and_candidate_state(tmp_path):
    pytest.importorskip('felupe')
    with prepare('material.felupe', settings()) as model:
        a=model.evaluate({'E':1000})
        b=model.evaluate({'E':2000})
        again=model.evaluate({'E':1000})
    np.testing.assert_allclose(a['responses']['stress_xx']['value'], [0,1.2,2.4])
    np.testing.assert_allclose(b['responses']['stress_xx']['value'], [0,2.4,4.8])
    np.testing.assert_array_equal(a['responses']['stress_xx']['value'], again['responses']['stress_xx']['value'])
    with pytest.raises(RuntimeError):
        model.evaluate({})
    result=run('material.felupe', settings(), output=tmp_path/'result')
    read=read_result(tmp_path/'result', selection=['stress_yy'])
    assert list(read['responses'])==['stress_yy']
    np.testing.assert_allclose(read['responses']['stress_yy']['value'], [0,.4,.8])
    with pytest.raises(FileExistsError):
        run('material.felupe', settings(), output=tmp_path/'result')


def test_trusted_callable_no_store_and_explicit_units(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def function(values, settings):
        return {'execution_status':'SUCCEEDED','responses':{'sum':{'kind':'scalar','value':values['a']+settings['b'],'unit':'1'}}}
    assert evaluate(function, {'b':3}, values={'a':2})['responses']['sum']['value']==5
    assert list(tmp_path.iterdir())==[]
    with pytest.raises(ValueError, match='unit'):
        evaluate(lambda v,s: {'execution_status':'SUCCEEDED','responses':{'x':{'kind':'scalar','value':2}}})


def test_missing_capability_and_native_input_rejection(tmp_path):
    with pytest.raises(CapabilityUnavailable, match='prepared'):
        prepare('pde.fenicsx', {})
    result=run('pde.fenicsx', {}, output=tmp_path/'rejected')
    assert result['execution_status']=='REJECTED'
    assert read_result(tmp_path/'rejected')['diagnostics']['native_outcome']['solver_status']=='NOT_RUN'


def test_result_integrity_and_path_containment(tmp_path):
    save_evaluation({'responses':{'x':{'value':np.array([1.,2.])}}},tmp_path/'saved')
    path=tmp_path/'saved/arrays/a000000.npy'
    path.write_bytes(b'broken')
    with pytest.raises(ValueError, match='hash'):
        read_result(tmp_path/'saved')
    assert read_result(tmp_path/'saved', selection=[])['responses']=={}


def test_explicit_table_mapping_and_no_new_candidates(tmp_path):
    path=tmp_path/'forces.csv'; path.write_text('t,f\n0,1\n1,2\n')
    spec={'path':str(path),'columns':{'force':{'column':'f','unit':'N','component':'y','location':'support',
              'axis':{'column':'t','name':'time','unit':'s'}}}}
    result=evaluate('files.table',spec)
    np.testing.assert_array_equal(result['responses']['force']['value'],[1,2])
    assert result['diagnostics']['solver_execution']=='NOT_PERFORMED'
    with pytest.raises(ValueError,match='new candidate'):
        evaluate('files.table',spec,values={'E':2})
    path.write_text('t,f\n0,1\n0,2\n')
    with pytest.raises(ValueError,match='increasing'):
        evaluate('files.table',spec)


def test_registry_does_not_require_core_edit():
    from caelab.backends import register_backend
    class Adapter:
        def prepare(self, settings, runtime=None):
            from caelab.evaluation import PreparedEvaluation
            return PreparedEvaluation(lambda values: {'execution_status':'SUCCEEDED','responses':{
                'x':{'kind':'scalar','unit':'1','value':values['x']}}}, settings)
    register_backend('test.external',Adapter,roles=('prepared',),replace=True)
    assert evaluate('test.external',{},values={'x':7})['responses']['x']['value']==7


def test_npz_and_fortran_mapping_preserves_units_and_axes(tmp_path):
    mapping={'columns':{'force':{'column':'f','unit':'N','component':'y','location':'support',
              'axis':{'column':'t','name':'time','unit':'s'}}}}
    np.savez(tmp_path/'table.npz',t=[0.,1.],f=[1.,2.])
    result=evaluate('files.table',{'path':str(tmp_path/'table.npz'),**mapping})
    np.testing.assert_array_equal(result['responses']['force']['value'],[1,2])
    (tmp_path/'table.txt').write_text('t,f\n0,1.0D+0\n1,2.0D+0\n')
    text=evaluate('files.table',{'path':str(tmp_path/'table.txt'),**mapping})
    np.testing.assert_array_equal(text['responses']['force']['value'],[1,2])


def test_full_verification_includes_unselected_responses_and_slices_axes(tmp_path):
    result={'responses':{'x':{'kind':'series','value':[1.,2.,3.],'unit':'N','component':'x','location':'support',
               'axes':[{'name':'time','unit':'s','values':[0.,1.,2.]}]},'y':{'value':[4.,5.]}}}
    packed=save_evaluation(result,tmp_path/'result')
    selected=read_result(tmp_path/'result',selection={'responses':['x'],'time_range':[.5,2]})
    assert selected['responses']['x']['value']==[2.,3.]
    assert selected['responses']['x']['axes'][0]['values']==[1.,2.]
    (tmp_path/'result'/packed['responses']['y']['value']['data_ref']['path']).write_bytes(b'broken')
    assert list(read_result(tmp_path/'result',selection=['x'])['responses'])==['x']
    with pytest.raises(ValueError,match='hash'):
        read_result(tmp_path/'result',verify='all',selection=['x'])
