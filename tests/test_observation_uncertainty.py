from copy import deepcopy
import math
import numpy as np
import pytest
from caelab.storage import canonical_hash
from caelab.experiment_observation_uncertainty import read_problem,template,propagate


class Reader:
    def __init__(self,channels):
        self.channels=channels
        self.ref=dict(document_id='Tsource',job_id='Jsource',input_revision='Rsource',input_sha256='a'*64,result_sha256='b'*64)
    def document_result_reference(self,*args):return deepcopy(self.ref)
    def document_result(self,*args,**kwargs):return {'execution_status':'SUCCEEDED','responses':deepcopy(self.channels)}


def channel(values,unit='mm',axis=None,**extra):
    meta=dict(unit=unit,component='x',location='gauge',reduction='none',measure='force' if unit=='N' else 'displacement',frame='lab')
    if axis is None:return dict(kind='scalar',value=values,**meta,**extra)
    return dict(kind='series',value=values,axes=[dict(name='time',unit='s',values=axis)],**meta,**extra)


def source(reader,name):return {'kind':'result_response','reference':reader.ref,'response':name}


def quantity(value,unit,identity):return dict(value=value,unit=unit,identity=identity,source='공개 합성 입력의 명시 값')


def specimen(q='cauchy_stress',axis=None):
    data={}
    for name in ['u'+p+a for p in 'AB' for a in 'xyz']:
        value=.2 if name=='uBx' else 0.
        data[name]=channel(value if axis is None else [value]*len(axis),axis=axis)
    data['F']=channel(100. if axis is None else [100.]*len(axis),'N',axis)
    r=Reader(data);s=template(r,source(r,'F'));d=s['operands']['A']
    d.update(quantity=q,channels={name:source(r,name) for name in data if name!='F'},
        direction=[1.,0.,0.],basis='lab',reference_points_mm=[[0.,0.,0.],[10.,0.,0.]])
    d['parameters']={}
    if q in ('engineering_strain','stretch','log_strain','cauchy_stress'):d['parameters']['L0']=quantity(10.,'mm','length')
    if q in ('nominal_stress','cauchy_stress'):
        if q=='nominal_stress':d['channels']={}
        d['channels']['force']=source(r,'F');d['parameters']['A0']=quantity(2.,'mm^2','area')
    if q=='cauchy_stress':d['protocol']='uniaxial_coaxial_declared';d['parameters']['J']={**quantity(.99,'1','volume'),'interpretation':'measured'}
    if axis is not None:d['max_gap_s']=2.
    return r,s


def spec(p):return {'uncertainties':{v['id']:{'kind':'standard','value':.01,'unit':v['unit']} for v in p['variables']},
    'dependence':{'kind':'independent_declared','note':'합성 oracle의 명시 가정'},'axis_uncertainty':'fixed_coordinates_declared','output_coverage_factor':2.}


@pytest.mark.parametrize('q,expected',[('projection',.2),('engineering_strain',.02),('stretch',1.02),('log_strain',math.log(1.02)),('nominal_stress',50.),('cauchy_stress',100*1.02/(2*.99))])
def test_selected_physical_transform_analytic_jacobian_h_h2(q,expected):
    r,s=specimen(q);before=canonical_hash(r.channels);p=read_problem(r,s)
    assert p['values']==pytest.approx([expected]);g=p['sensitivities'][0]
    for index,v in enumerate(p['variables']):
        slopes=[]
        for h in (1e-5,5e-6):
            vals=[]
            for sign in (-1,1):
                rr=Reader(deepcopy(r.channels));ss=deepcopy(s)
                if v.get('parameter'):
                    ss['operands']['A']['parameters'][v['parameter']]['value']+=sign*h
                else:rr.channels[v['source']['response']]['value']+=sign*h
                vals.append(read_problem(rr,ss)['values'][0])
            slopes.append((vals[1]-vals[0])/(2*h))
        assert slopes[1]==pytest.approx(g[index],rel=2e-7,abs=2e-8)
        assert slopes[0]==pytest.approx(slopes[1],rel=2e-7,abs=2e-8)
    result=propagate(p,spec(p));a=result['experiment_analysis']
    assert result['execution_status']=='SUCCEEDED' and a['rows'][0]['expanded_uncertainty']==pytest.approx(2*a['rows'][0]['standard_uncertainty'])
    assert canonical_hash(r.channels)==before


def test_noncommuting_time_order_and_offset_slope():
    r,s=specimen('log_strain',axis=[0.,1.]);r.channels['uBx']['value']=[0.,10.]
    # Fixed target from a separate retained scalar history, without changing grid.
    r.channels['target']=channel([0.],'1',[.25]);s['base']=source(r,'target');d=s['operands']['A']
    d['time_offset']=quantity(.1,'s','clock')
    first=read_problem(r,s)
    assert first['values']==pytest.approx([.35*math.log(2)])
    col=next(i for i,v in enumerate(first['variables']) if v['id']=='clock')
    assert first['sensitivities'][0][col]==pytest.approx(math.log(2))
    d['order']='align_then_transform';second=read_problem(r,s)
    assert second['values']==pytest.approx([math.log(1.35)])
    assert second['sensitivities'][0][col]==pytest.approx(1/1.35)
    for order,expected in [('transform_then_align',math.log(2)),('align_then_transform',1/1.35)]:
        d['order']=order
        for h in (1e-5,5e-6):
            vals=[]
            for sign in (-1,1):
                ss=deepcopy(s);ss['operands']['A']['time_offset']['value']+=sign*h
                vals.append(read_problem(r,ss)['values'][0])
            assert (vals[1]-vals[0])/(2*h)==pytest.approx(expected,rel=2e-8)


@pytest.mark.parametrize('target,reason',[(0.,'knot'),(3.,'범위 밖')])
def test_singular_time_derivative_retains_value_mask_and_reason(target,reason):
    r=Reader({'value':channel([1.,2.],'N',[0.,1.]),'target':channel([7.],'N',[target])});s=template(r,source(r,'target'))
    s['operands']['A'].update(channels={'value':source(r,'value')},max_gap_s=2.,time_offset=quantity(0.,'s','clock'))
    p=read_problem(r,s);result=propagate(p,spec(p))
    assert p['included']==[True] and result['experiment_analysis']['rows'][0]['status']=='UNKNOWN'
    assert reason in result['experiment_analysis']['rows'][0]['reason']
    assert p['original']['base_problem']['values']==[7.]
    if target==0:assert p['values']==[1.]


def test_gap_and_invalid_lambda_are_unknown_without_filling():
    r,s=specimen('log_strain');r.channels['uBx']['value']=-20.
    p=read_problem(r,s);a=propagate(p,spec(p))['experiment_analysis']
    assert p['values']==[None] and 'lambda' in a['rows'][0]['reason']
    r=Reader({'v':channel([1.,2.],'N',[0.,2.],segments=[{'rows':[0,1]},{'rows':[1,2]}]),'t':channel([8.],'N',[1.])})
    s=template(r,source(r,'t'));s['operands']['A'].update(channels={'value':source(r,'v')},max_gap_s=3.)
    p=read_problem(r,s);assert 'gap' in p['row_reasons'][0] and p['values']==[None]


def test_same_identity_conflict_and_explicit_J_assumption():
    r,s=specimen();s['operands']['A']['parameters']['A0']['identity']='length'
    with pytest.raises(ValueError,match='충돌'):read_problem(r,s)


def test_processing_source_chain_reuses_existing_value_lineage(tmp_path):
    from tests.experiment_expert.support import ServiceHost
    from tests.experiment_expert.test_file_workflow import import_source
    from tests.experiment_expert.test_processing_source import publish_fixture
    from caelab.data_processing_document import result as read_processing
    with ServiceHost(tmp_path) as h:
        doc,job,_=import_source(h);d=h.data.read(doc);run=d['runs'][-1]
        origin={k:run[k] for k in ('job_id','input_revision','input_sha256')};origin['document_id']=doc
        draft=deepcopy(d['draft']);draft['processing']={'source':origin,'recipe':{'version':1,'operations':[]}}
        h.command(doc,'data.update',{'draft':draft});record=publish_fixture(h.data,doc)
        c=read_processing(h.data,doc,record['id'])['channels']['force']
        base={'kind':'processing_channel','document_id':doc,'revision':record['id'],'channel':'force','channel_sha256':canonical_hash(c)}
        s=template(h.core,base);s['operands']['A']['max_gap_s']=2.
        p=read_problem(h.core,s)
        assert p['values']==c['values'] and p['original']['operand_sources']['A']['value']['source_problem']['trace']
        assert p['calibration_reapplied'] is False
    r,s=specimen();s['operands']['A']['parameters']['J'].pop('interpretation')
    with pytest.raises(ValueError,match='J=1'):read_problem(r,s)


def test_unknown_covariance_stays_unknown_and_area_units_scale():
    r,s=specimen();p=read_problem(r,s);u=spec(p);u['dependence']={'kind':'UNKNOWN'}
    assert propagate(p,u)['execution_status']=='REJECTED'
    from caelab.experiment_uncertainty import unit_factor
    assert unit_factor('m^2','mm^2')==1e6
    s['operands']['A']['parameters']['A0'].update(value=2e-6,unit='m^2')
    assert read_problem(r,s)['values']==pytest.approx(p['values'])


def comparison_reader(channels,a='A',b='B'):
    from caelab.data_comparison import compare_data_curves
    r=Reader(channels)
    saved=compare_data_curves(channels[b],channels[a])
    count=len(channels[a]['value'])
    binding={name:{**r.ref,'response':key,'response_sha256':canonical_hash(channels[key])} for name,key in [('source',a),('prediction_source',b)]}
    r.research_reference=lambda *_:{'status':'AVAILABLE','kind':'comparison','comparison':{'binding':binding,'comparison':saved,'page':{'start':0,'count':count}}}
    return r,{'kind':'retained_comparison','reference':{'kind':'comparison','test':'synthetic'}}


def test_shared_time_offset_cancels_in_physical_difference_not_residual():
    r,base=comparison_reader({'A':channel([1.,2.],'N',[.25,.5]),'B':channel([0.,4.],'N',[0.,1.]),
        'dataA':channel([1.,3.],'N',[0.,1.]),'dataB':channel([2.,4.],'N',[0.,1.])})
    s=template(r,base)
    for side in 'AB':s['operands'][side].update(channels={'value':source(r,'data'+side)},max_gap_s=2.,time_offset=quantity(.1,'s','shared_clock'))
    p=read_problem(r,s);index=next(i for i,v in enumerate(p['variables']) if v['id']=='shared_clock')
    assert p['values']==pytest.approx([1.,1.]) and [row[index] for row in p['sensitivities']]==[0.,0.]
    u=spec(p);u['dependence']={'kind':'UNKNOWN'}
    for key,entry in u['uncertainties'].items():entry['value']=.1 if key=='shared_clock' else 0.
    result=propagate(p,u)
    assert result['execution_status']=='SUCCEEDED'
    assert [row['standard_uncertainty'] for row in result['experiment_analysis']['rows']]==[0.,0.]


def test_affine_x0_raw_units_shared_coefficients_and_original_not_recalibrated(tmp_path,monkeypatch):
    from tests.experiment_expert.test_uncertainty import imported
    response=__import__('caelab.experiment_uncertainty',fromlist=['plain']).plain(imported(tmp_path)['responses']['force'])
    r=Reader({'F':response});s=template(r,source(r,'F'));s['operands']['A']['max_gap_s']=2.
    before=canonical_hash(r.channels)
    monkeypatch.setattr('caelab.experiment_calibration.calibrate',lambda *_:pytest.fail('calibration replay'))
    p=read_problem(r,s);variables=p['variables'];row=p['sensitivities'][0]
    assert p['values']==pytest.approx([.5,2.5,6.5,8.5,10.5])
    x0=next(i for i,v in enumerate(variables) if v.get('coefficient')=='x0')
    a=next(i for i,v in enumerate(variables) if v.get('coefficient')=='a')
    assert row[x0]==-2. and row[a]==0.
    assert variables[x0]['unit']=='mV' and variables[0]['unit']=='V' and row[0]==2000.
    assert canonical_hash(r.channels)==before and not p['calibration_reapplied']


def test_explicit_shared_affine_coefficients_cancel_and_conflicts_block(tmp_path):
    from tests.experiment_expert.test_uncertainty import imported
    from caelab.experiment_uncertainty import plain
    response=plain(imported(tmp_path)['responses']['force'])
    r,base=comparison_reader({'A':response,'B':deepcopy(response)})
    s=template(r,base)
    for side in 'AB':s['operands'][side].update(max_gap_s=2.,shared_identities={'value':{name:'shared_'+name for name in ('a','x0','b')}})
    p=read_problem(r,s)
    for key in ('shared_a','shared_x0','shared_b'):
        index=next(i for i,v in enumerate(p['variables']) if v['id']==key)
        assert all(row[index]==0 for row in p['sensitivities'])
    r.channels['B']['calibration']['b']+=1.
    # Update retained binding too: this is a valid different supplied source,
    # but cannot claim the same coefficient identity as the old A value.
    old=r.research_reference(None)
    old['comparison']['binding']['prediction_source']['response_sha256']=canonical_hash(r.channels['B'])
    r.research_reference=lambda *_:deepcopy(old)
    with pytest.raises(ValueError,match='충돌'):read_problem(r,s)


def test_raw_source_limit_precedes_dense_jacobian_allocation(monkeypatch):
    from caelab.experiment_observation_uncertainty import _source_channel
    from caelab.experiment_uncertainty import MAX_SAMPLES, MAX_VARIABLES
    limit=min(MAX_SAMPLES,MAX_VARIABLES)
    reader=Reader({'long':channel([1.]*(limit+1),'N',list(map(float,range(limit+1)))),
                   'empty':channel([],'N',[])})
    monkeypatch.setattr(np,'eye',lambda *_args,**_kwargs:pytest.fail('dense Jacobian allocated before admission'))
    original=canonical_hash(reader.channels)
    for name in ('long','empty'):
        with pytest.raises(ValueError,match='원 표본 한도'):
            _source_channel(reader,source(reader,name))
    assert canonical_hash(reader.channels)==original


def test_channel_choices_do_not_build_jacobians_for_unselected_curves(monkeypatch):
    pytest.importorskip('PySide6')
    import apps.research.observation_uncertainty_dialog as ui
    from caelab.experiment_uncertainty import MAX_SAMPLES
    reader=Reader({'short':channel([1.,2.],'N',[0.,1.]),
        'long':channel([1.]*(MAX_SAMPLES+1),'N',list(map(float,range(MAX_SAMPLES+1))))})
    monkeypatch.setattr(ui,'_source_channel',lambda *_args:pytest.fail('choice list built a source Jacobian'))
    definition,choices=ui.source_options(reader,source(reader,'short'))
    assert definition['operands']['A']['channels']['value']['response']=='short'
    assert choices['A']['short']['unavailable'] is None and choices['A']['short']['variables'] is None
    assert '원 표본 한도' in choices['A']['long']['unavailable']
