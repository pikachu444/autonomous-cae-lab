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


def test_public_import_freezes_exact_certificate_closure_and_rejects_substitutes(tmp_path):
    wb=Workbench(tmp_path/'store')
    try:
        raw=wb.upload('voltage.csv',RAW)
        cert=wb.upload('calibration.txt',b'public calibration')
        recipe=calibration({'data_id':cert['id'],'sha256':cert['sha256'],'name':cert['name']})
        args={'data_id':raw['id'],'mapping':mapping(recipe)}
        result=completed(wb,wb.submit('import_table',args))
        frozen=result['diagnostics']['calibration_sources']
        assert len(frozen)==1 and frozen[0]['data_id']==cert['id']
        assert frozen[0]['sha256']==cert['sha256']
        wrong=deepcopy(args);wrong['mapping']['columns']['force']['calibration']['source']['sha256']='a'*64
        with pytest.raises(ValueError):wb.submit('import_table',wrong)
        missing=deepcopy(args);missing['mapping']['columns']['force']['calibration']['source']['data_id']='Dabsent'
        with pytest.raises((ValueError,FileNotFoundError)):wb.submit('import_table',missing)
        with pytest.raises(ValueError):wb.submit('import_table',{**args,'calibration_sources':[]})
        other=deepcopy(frozen);other[0]['data_id']=raw['id']
        with pytest.raises(ValueError):wb.submit('import_table',{**args,'calibration_sources':other})
        # Execution cannot bypass admission by omitting the frozen closure.
        with pytest.raises(ValueError):wb._execute('import_table',args,'Jnot_submitted')
    finally:wb.shutdown()


def test_malformed_mapping_and_undo_remain_saveable(tmp_path):
    wb=Workbench(tmp_path/'store')
    try:
        raw=wb.upload('voltage.csv',RAW)
        doc=wb.document_open(kind='data',draft={'data_id':raw['id'],'mapping':'unfinished'})
        doc=command(wb,doc,'document.save')['document']
        assert doc['diagnostics'] and doc['draft']['mapping']=='unfinished'
        with pytest.raises(ValueError):command(wb,doc,'data.import')
        valid=mapping(calibration());valid['columns']['force'].pop('calibration')
        valid['columns']['force'].update(unit='V',measure='voltage')
        doc=command(wb,doc,'data.update',{'draft':{'data_id':raw['id'],'mapping':valid}})['document']
        doc=command(wb,doc,'document.save')['document']
        assert not doc['diagnostics']
        doc=command(wb,doc,'document.undo')['document']
        assert doc['draft']['mapping']=='unfinished'
    finally:wb.shutdown()


def test_acquisition_output_unit_must_match_processed_channel():
    from caelab.experiment_calibration import default_acquisition,validate_acquisition
    setup={**default_acquisition(),'name':'시험','sample_rate_hz':100.,'duration_s':2.,
           'channels':[{'name':'force','unit':'N','role':'measurement','calibration':calibration()}]}
    assert validate_acquisition(setup)==setup
    setup['channels'][0]['unit']='mm'
    with pytest.raises(ValueError):validate_acquisition(setup)


@pytest.mark.parametrize('kind',[None,'UNKNOWN'])
def test_partially_provided_uncertainty_does_not_invent_standard_or_block_calibration(kind):
    recipe=calibration()
    recipe['uncertainty'].update(kind=kind,k=None,correlation='UNKNOWN')
    values,audit=calibrate([.002],recipe)
    assert values.tolist()==[2.5]
    assert audit['uncertainty']==recipe['uncertainty']
    assert audit['calibration_valid']==[True]


@pytest.mark.parametrize('shared_certificate',[True,False])
def test_multichannel_certificate_closure_recovers_lost_admission_reply(tmp_path,monkeypatch,shared_certificate):
    root=tmp_path/'store';wb=Workbench(root)
    try:
        raw=wb.upload('voltage.csv',RAW)
        certificates=[wb.upload('cert-a.txt',b'public A'),wb.upload('cert-b.txt',b'public B')]
        certificates=sorted(certificates,key=lambda r:r['id'],reverse=True)
        if shared_certificate:certificates[1]=certificates[0]
        columns={}
        for i,cert in enumerate(certificates):
            recipe=calibration({'data_id':cert['id'],'sha256':cert['sha256'],'name':cert['name']})
            columns['force'+str(i)]=mapping(recipe)['columns']['force']
        doc=wb.document_open(kind='data',draft={'data_id':raw['id'],
            'mapping':{'delimiter':',','skip_header':1,'columns':columns}})
        owner=wb.data_documents;submit=owner.submit
        def lost(*args,**kwargs):
            submit(*args,**kwargs)
            raise OSError('reply lost after job admission')
        monkeypatch.setattr(owner,'submit',lost)
        with pytest.raises(OSError):
            command(wb,doc,'data.import',command_id='Cimport')
        recovered=wb.document_read(doc['id'])
        assert len(recovered['runs'])==1
        job=wb.manager.status(recovered['runs'][0]['job_id'])
        assert len(job['arguments']['calibration_sources'])==(1 if shared_certificate else 2)
        completed(wb,job)
        receipt=command(wb,doc,'data.import',command_id='Cimport')
        assert receipt['job']['id']==job['id']
        assert len(wb.manager.list())==1
        saved=command(wb,wb.document_read(doc['id']),'document.save')['document']
    finally:wb.shutdown()
    fresh=Workbench(root)
    try:
        restored=fresh.document_open(kind='data',document_id=saved['id'])
        assert len(restored['runs'])==1
        assert fresh.document_result(restored['id'],job['id'])['responses']['force0']['value']==[.5,2.5,6.5]
    finally:fresh.shutdown()
