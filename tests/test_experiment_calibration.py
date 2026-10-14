"""Changed calibration/Data contracts; no solver or device campaign."""
from copy import deepcopy
import time
import pytest

from caelab.experiment_calibration import default_calibration, calibrate, validate_calibration
from caelab.adapters.file_table import read_table
from caelab.workbench import Workbench


RAW=b't,voltage\n0,0.001\n1,0.002\n2,0.004\n3,0.005\n4,0.006\n'


def calibration(source=None):
    return {**default_calibration('N'), 'input_unit':'V','coefficient_input_unit':'mV',
        'a':2.,'x0':1.,'x0_unit':'mV','b':.5,
        'source':source or {'data_id':'Dcertificate','sha256':'a'*64,'name':'교정서.txt'},
        'input_range':{'minimum':1.,'maximum':4.,'unit':'mV'},
        'sensor_range':{'minimum':0.,'maximum':5.,'unit':'mV'},
        'uncertainty':{'value':.1,'unit':'N','kind':'expanded','k':None,'correlation':'UNKNOWN','note':'제공된 값'}}


def mapping(recipe):
    return {'delimiter':',','skip_header':1,'columns':{'force':{
        'column':1,'unit':'N','component':'z','location':'gauge_A','measure':'force','frame':'lab',
        'axis':{'column':0,'name':'time','unit':'s'},'calibration':recipe,
        'row_selection':{'display_hidden_rows':[3]}}}}


def command(wb,doc,op,args=None,**kwargs):
    return wb.document_command(doc['id'],op,args or {},session_id=doc['session_id'],
        expected_generation=doc['generation'],**kwargs)


def completed(wb,job):
    limit=time.monotonic()+15
    while time.monotonic()<limit:
        status=wb.manager.status(job['id'])
        if status['state'] in {'SUCCEEDED','FAILED','CANCELLED'}:
            assert status['state']=='SUCCEEDED',status
            return wb.result(job['id'])
        time.sleep(.01)
    raise AssertionError(wb.manager.status(job['id']))


def imported(wb):
    raw=wb.upload('전압.csv',RAW);cert=wb.upload('교정서.txt',b'Public synthetic calibration. Not a real instrument certificate.')
    recipe=calibration({'data_id':cert['id'],'sha256':cert['sha256'],'name':cert['name']})
    doc=wb.document_open(kind='data',title='힘 시험',draft={'data_id':raw['id'],'mapping':mapping(recipe)})
    receipt=command(wb,doc,'data.import');result=completed(wb,receipt['job'])
    doc=command(wb,wb.document_read(doc['id']),'document.save')['document']
    return doc,receipt['job']['id'],result,cert


def test_affine_voltage_scale_zero_range_saturation_and_unknown_uncertainty(tmp_path):
    a=calibration()
    millivolt={**deepcopy(a),'input_unit':'mV'}
    volts,audit=calibrate([.001,.002,.004,.005,.006],a)
    mv,_=calibrate([1,2,4,5,6],millivolt)
    assert volts.tolist()==pytest.approx([.5,2.5,6.5,8.5,10.5])
    assert volts.tolist()==mv.tolist()
    assert audit['calibration_out_of_range']==[False,False,False,True,True]
    assert audit['sensor_saturated']==[False,False,False,True,True]
    assert audit['uncertainty']['k'] is None and audit['uncertainty']['correlation']=='UNKNOWN'
    with pytest.raises(ValueError):validate_calibration({**a,'input_unit':'count'})
    source=tmp_path/'source.csv';source.write_bytes(RAW)
    result=read_table(source,mapping(a));response=result['responses']['force']
    assert response['value'].tolist()==pytest.approx([.5,2.5,6.5])
    raw=response['raw_samples']
    assert raw['value']==[.001,.002,.004,.005,.006]
    assert raw['transformed_value']==pytest.approx([.5,2.5,6.5,8.5,10.5])
    assert raw['calculation_requested']==[True]*5
    assert raw['calculation_valid']==[True,True,True,False,False]
    assert raw['display_visible']==[True,True,False,True,True]
    assert raw['quality_valid']==[True,True,True,False,False]


def test_owner_retains_certificate_invalid_draft_original_rows_and_cold_open(tmp_path):
    root=tmp_path/'store';wb=Workbench(root)
    try:
        data,job,result,cert=imported(wb)
        reference=wb.document_result_reference(data['id'],job)
        selected=wb.document_result(data['id'],job,selection={'responses':['force'],'source_rows':[2,4]})
        force=selected['responses']['force']
        assert force['source_rows']==[2] and force['value']==[2.5]
        assert force['raw_samples']['source_rows']==[2,4]
        assert force['raw_samples']['transformed_value']==[2.5,8.5]
        draft=deepcopy(data['draft']);draft['mapping']['columns']['force']['calibration']['a']='1e'
        data=command(wb,data,'data.update',{'draft':draft})['document']
        data=command(wb,data,'document.save')['document']
        assert data['diagnostics'] and cert['id'] in data['retained_inputs']
        with pytest.raises(ValueError):command(wb,data,'data.import')
    finally:wb.shutdown()
    fresh=Workbench(root)
    try:
        data=fresh.document_open(kind='data',document_id=data['id'])
        assert data['draft']['mapping']['columns']['force']['calibration']['a']=='1e'
        assert fresh.document_result_reference(data['id'],job)==reference
        assert fresh.document_result(data['id'],job)['responses']['force']['value']==[.5,2.5,6.5]
        data=command(fresh,data,'document.undo')['document']
        assert data['draft']['mapping']['columns']['force']['calibration']['a']==2.
    finally:fresh.shutdown()
