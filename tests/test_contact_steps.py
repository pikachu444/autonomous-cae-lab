"""Explicit native-byte/process doubles; these checks do not qualify a solver."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace as NS
import pytest

from test_contact_execution import model, native_outputs
from caelab.contact_steps import (default_program, compile_program, validate_contributions,
    profile, validate_frames, axis)
from caelab.contact_deck import render, validate_model
from caelab.adapters.frozen_fem import read_frd
from caelab.adapters.contact_results import read_dat, write_post
from caelab.adapters import contact_fem
from caelab.contact_status import read_status, retained_prefix, require_converged
from caelab.contact_inspection import load, force_history
from caelab.execution_control import ExecutionCancelled


def staged(model, *, dynamic=False):
    result=deepcopy(model)
    force=result['loads'][0]
    result['conditions']=[
        {'object_id':'Support','label':'받침','type':'Fem::ConstraintFixed','body_id':'Base',
         'boundary_dofs':deepcopy(result['boundary_dofs'])},
        {'object_id':'Force','label':'누르는 힘','type':'Fem::ConstraintForce','body_id':'Pad',
         'total_force_N':10.,'force_weights':[{'node_id':force['node_id'],'component':3,'weight':-1.}]}]
    program=default_program(result['step'],result['conditions'])
    first=program['steps'][0]
    first.update(label='가압',duration=.5,initial=.5,maximum=.5)
    first['curves'][0]['points']=[[0,0],[.5,10]]
    second=deepcopy(first); second.update(id='Step2',label='제하')
    second['curves'][0]['points']=[[0,10],[.5,0]]
    program['steps'].append(second)
    program['procedure']='dynamic' if dynamic else 'static'
    result['analysis_steps']=program
    if dynamic:
        for material in result['materials']:
            material['density_tonne_per_mm3']=7.8e-9
    return result


def two_step_outputs(model):
    frd,dat,materials=native_outputs(model)
    lines=[]
    for line in frd.splitlines():
        if line.split()[:1]==['1PSTEP'] and int(line[36:48])==2:
            line=line[:36]+f'{1:12d}{2:12d}'+line[60:]
        if line.startswith('  100CL') and axis(model)['unit']=='s':
            line=line[:36]+' '*21+'1'+line[58:]
        lines.append(line)
    dat=dat.replace(' S T E P 1\n INCREMENT 2',' S T E P 2\n INCREMENT 1')
    return '\n'.join(lines)+'\n',dat,materials


def write_snapshot(model, folder):
    folder.mkdir()
    (folder/'editable.FCStd').write_bytes(b'EXPLICIT_NATIVE_DOCUMENT_DOUBLE')
    (folder/'mesh.json').write_text(json.dumps(model),encoding='utf-8')
    (folder/'contact.inp').write_text(render(model),encoding='ascii',newline='\n')
    data={'kind':'freecad-contact-frozen','schema_version':'1','id':'Fstages','analysis_id':'Analysis',
          'solver_id':'Solver','input_file':'contact.inp','bodies':[{'body_id':b} for b in ('Pad','Base')],
          'files':[{'relative':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                   for p in sorted(folder.iterdir())]}
    path=folder/'snapshot.json'; path.write_text(json.dumps(data),encoding='utf-8')
    return path


def test_overlapping_condition_curves_sum_before_native_dof_and_zero_reference(model):
    m=staged(model)
    force=m['conditions'][1]
    force['total_force_N']=0.
    other=deepcopy(force); other.update(object_id='Second',label='다른 힘')
    m['conditions'].append(other)
    m['loads'][0]['force_N']=0.
    for step in m['analysis_steps']['steps']:
        step['curves']=[
            {'condition_id':'Force','component':0,'unit':'N','points':[[0,0],[.25,10],[.5,0]]},
            {'condition_id':'Second','component':0,'unit':'N','points':[[0,4],[.5,0]]}]
    validate_contributions(m)
    first=compile_program(m['analysis_steps'],m['conditions'])[0]
    assert list(first['loads'].values())==[[[0.,-4.],[.25,-12.],[.5,0.]]]
    deck=render(m)
    assert deck.count('*CONTACT PAIR')==1 and deck.count('*STEP,')==2
    assert deck.count('*CLOAD,OP=NEW')==2 and 'OP=MOD' not in deck
    assert '*AMPLITUDE,NAME=A1_' in deck and '*AMPLITUDE,NAME=A2_' in deck
    assert '*MODEL CHANGE' not in deck and 'ADJUST=' not in deck
    broken=deepcopy(m); broken['conditions'][0]['boundary_dofs'][0]['node_id']=m['loads'][0]['node_id']
    with pytest.raises(ValueError,match='owning body'):
        render(broken)


def test_zero_hold_release_and_blank_are_not_equivalent_and_supports_survive(model):
    m=staged(model)
    node=m['loads'][0]['node_id']
    displacement={'object_id':'Travel','label':'누름 변위','type':'Fem::ConstraintDisplacement',
        'body_id':'Pad','components_mm':{1:.1},
        'boundary_dofs':[{'node_id':node,'component':1,'value_mm':.1}]}
    m['conditions'].append(displacement); m['boundary_dofs']+=deepcopy(displacement['boundary_dofs'])
    first,second=m['analysis_steps']['steps']
    first['curves'].append({'condition_id':'Travel','component':1,'unit':'mm','points':[[0,0],[.5,.1]]})
    second['curves'].append({'condition_id':'Travel','component':1,'unit':'mm','mode':'hold','points':[]})
    rows=compile_program(m['analysis_steps'],m['conditions'])
    assert rows[1]['boundary'][node,1]==[[0.,.1],[.5,.1]]
    second['curves'][-1]['mode']='release'
    second['curves'][0]['mode']='release'
    rows=compile_program(m['analysis_steps'],m['conditions'])
    assert (node,1) not in rows[1]['boundary']
    assert rows[1]['loads'][node,3]==[[0.,0.],[.5,0.]]
    assert len(rows[1]['boundary'])==9  # Fixed supports re-emitted under OP=NEW.
    assert render(m).count('*CLOAD,OP=NEW,AMPLITUDE=')==2
    assert 'OP=MOD' not in render(m)
    second['curves'][-1].update(mode='curve',points=[[0,0],[.5,0]])
    assert compile_program(m['analysis_steps'],m['conditions'])[1]['boundary'][node,1]==[[0.,0.],[.5,0.]]
    second['curves'][-1]['points'][1][1]='1e'
    with pytest.raises(ValueError,match='complete finite'):
        render(m)


def test_dynamic_density_clearance_and_no_implicit_explicit_switch(model):
    m=staged(model,dynamic=True)
    m['contacts'][0]['draft'].update(gap_policy='prescribed',nominal_gap_mm='0.125')
    deck=render(m)
    assert deck.count('*DYNAMIC')==2 and 'EXPLICIT' not in deck
    assert deck.count('*DENSITY\n7.8E-09')==2
    assert '*CLEARANCE,MASTER=INDContact,SLAVE=DEPContact,VALUE=0.125' in deck
    del m['materials'][0]['density_tonne_per_mm3']
    with pytest.raises(ValueError): render(m)
    m=staged(model)
    m['contacts'][0]['draft'].update(gap_policy='prescribed',nominal_gap_mm='1.2357111317')
    with pytest.raises(ValueError): render(m)


@pytest.mark.parametrize('dynamic',[False,True])
def test_step_increment_identity_clock_final_completeness_and_retained_post(model,tmp_path,dynamic):
    m=staged(model,dynamic=dynamic)
    frd,dat,materials=two_step_outputs(m)
    fp,dp=tmp_path/'native.frd',tmp_path/'native.dat'
    fp.write_text(frd,encoding='ascii',newline='\n'); dp.write_text(dat,encoding='ascii',newline='\n')
    nodes,elements,_=validate_model(m)
    with pytest.raises(ValueError):
        read_frd(fp,nodes,elements,contact_materials=materials)  # Legacy remains single static step.
    observed=read_frd(fp,nodes,elements,contact_materials=materials,contact_profile=profile(m))
    validate_frames(m,observed)
    assert [(r['static']['step'],r['static']['increment']) for r in observed['frames']]==[(1,1),(2,1)]
    assert observed['frames'][1]['step_location']['coordinate']==.5
    rows=read_dat(dp,m['contacts'],observed['frames'])
    assert len(rows)==6 and rows[-1]['static']['step']==2
    missing=deepcopy(observed); missing['frames']=missing['frames'][1:]
    with pytest.raises(ValueError,match='endpoint'): validate_frames(m,missing)
    folder=tmp_path/'post'
    metadata=write_post(folder,m,observed['frames'],rows,provenance={
        'snapshot_id':'Fstages','snapshot_sha256':'1'*64,'raw_frd_sha256':'2'*64,'raw_dat_sha256':'3'*64})
    bundle=load(folder/'contact.pvd',metadata['contact_inspection'])
    assert bundle['manifest']['version']==2
    history=force_history(bundle,'Contact','CFN',2)
    assert history['axis']==axis(m)
    assert [r['value'] for r in history['rows']]==[1.,2.]
    assert metadata['time']['values']==[.5,1.] and metadata['time']['unit']==('s' if dynamic else '1')


def test_unconverged_best_solution_is_not_a_committed_partial_frame(model,tmp_path):
    m=staged(model); frd,dat,materials=two_step_outputs(m)
    fp,dp,sp=tmp_path/'native.frd',tmp_path/'native.dat',tmp_path/'native.sta'
    fp.write_text(frd,encoding='ascii',newline='\n'); dp.write_text(dat,encoding='ascii',newline='\n')
    sp.write_text(' 1 1 1 3 5.000000E-1 5.000000E-1 5.000000E-1\n'
                  ' 2 1 1U 8 5.000000E-1 0.000000E+0 5.000000E-1\n',encoding='ascii')
    status=read_status(sp,m)
    assert status['failure_location']['total']==.5
    assert status['failure_location']['attempted_end_derived']==1.
    nodes,elements,_=validate_model(m)
    parsed=read_frd(fp,nodes,elements,contact_materials=materials,contact_profile=profile(m))
    with pytest.raises(ValueError,match='converged'): require_converged(parsed['frames'],status)
    original=fp.read_bytes()
    prefix=retained_prefix(fp,tmp_path/'partial/read.frd',nodes,elements,materials,m,status)
    assert len(prefix['frames'])==1 and fp.read_bytes()==original
    assert len(read_dat(dp,m['contacts'],prefix['frames'],prefix=True))==3
    sp.write_text(sp.read_text(encoding='ascii')+' 2 1 2 3 1.000000E+0 5.000000E-1 5.000000E-1\n',encoding='ascii')
    resumed=read_status(sp,m)
    assert resumed['failure_location'] is None and len(resumed['rows'])==3
    require_converged(parsed['frames'],resumed)


@pytest.mark.parametrize('dynamic',[False,True])
@pytest.mark.parametrize('outcome',['success','failure','cancel'])
def test_owned_adapter_steps_retained_failure_and_no_fake_partial_responses(model,tmp_path,monkeypatch,outcome,dynamic):
    m=staged(model,dynamic=dynamic); snapshot=write_snapshot(m,tmp_path/'input')
    frd,dat,_=two_step_outputs(m)
    exe=tmp_path/'ccx'; exe.write_bytes(b'EXPLICIT_PROCESS_DOUBLE')
    monkeypatch.setattr(contact_fem.shutil,'which',lambda _:str(exe))
    calls=[]
    def command(argv,cwd,label):
        calls.append(argv)
        (cwd/'contact.frd').write_text(frd,encoding='ascii',newline='\n')
        (cwd/'contact.dat').write_text(dat,encoding='ascii',newline='\n')
        sta=' 1 1 1 3 .5 .5 .5\n'+(' 2 1 1 3 1.0 .5 .5\n' if outcome=='success' else ' 2 1 1U 9 .5 0.0 .5\n')
        (cwd/'contact.sta').write_text(sta,encoding='ascii')
        if outcome=='cancel': raise ExecutionCancelled('explicit test cancellation')
        return NS(returncode=0 if outcome=='success' else 1)
    monkeypatch.setattr(contact_fem,'run_owned_command',command)
    result=contact_fem.ContactFemCalculixAdapter().run({'snapshot_path':str(snapshot),'data_id':'Dsteps'},output=tmp_path/'run')
    assert len(calls)==1
    assert result['execution_status']=={'success':'SUCCEEDED','failure':'FAILED','cancel':'CANCELLED'}[outcome],result
    assert result['executed_setup']['program']==m['analysis_steps']
    if outcome=='success':
        assert result['responses']['Contact.CFN.FZ']['value']==[1.,2.]
        assert result['responses']['Contact.CFN.FZ']['axes'][0]['unit']==('s' if dynamic else '1')
        header=(tmp_path/'run/pair_resultants.csv').read_text(encoding='utf-8').splitlines()[0].split(',')
        assert header[4]==('time_s' if dynamic else 'load_parameter')
        for name in ('CPRESS','displacement'):
            metadata=result['responses'][name]['metadata']
            assert metadata['axis']==axis(m)
            assert metadata['coordinate']==1. and metadata['step_location']['index']==2
        receipt=contact_fem.regenerate_post(tmp_path/'run',tmp_path/'rebuilt')
        assert receipt['solver_execution']=='NOT_PERFORMED' and len(calls)==1
    else:
        assert result['responses']=={}
        assert result['partial_result']['status']=='CONVERGED_PREFIX'
        assert result['partial_result']['frame_count']==1 and not result['partial_result']['complete_analysis']
        assert (tmp_path/'run/solver/contact.frd').read_text(encoding='ascii')==frd
        assert result['failure_location']['step_location']['label']=='제하'
        assert result['post_artifact']['relative']=='partial/post/contact.pvd'


def test_serialized_knots_and_dynamic_displacement_continuity(model):
    from caelab.contact_steps import curve
    with pytest.raises(ValueError,match='정밀도'):
        curve([[0,0],[.500000000000001,1],[.500000000000002,2],[1,0]],1.,'하중')
    m=staged(model,dynamic=True)
    n=m['loads'][0]['node_id']
    m['conditions'].append({'object_id':'Travel','label':'변위','type':'Fem::ConstraintDisplacement',
        'body_id':'Pad','components_mm':{1:.2},
        'boundary_dofs':[{'node_id':n,'component':1,'value_mm':.2}]})
    for i,s in enumerate(m['analysis_steps']['steps']):
        s['curves'].append({'condition_id':'Travel','component':1,'unit':'mm',
                           'points':[[0,0 if i==0 else .2],[.5,.2]]})
    assert len(compile_program(m['analysis_steps'],m['conditions']))==2
    m['analysis_steps']['steps'][1]['curves'][-1]['points'][0][1]=0
    with pytest.raises(ValueError,match='연속'):
        compile_program(m['analysis_steps'],m['conditions'])


def test_stage_local_conflicts_release_and_legacy_guard(model):
    m=staged(model)
    n=m['loads'][0]['node_id']
    travel={'object_id':'Travel','label':'누름','type':'Fem::ConstraintDisplacement',
        'body_id':'Pad','components_mm':{3:.1},
        'boundary_dofs':[{'node_id':n,'component':3,'value_mm':.1}]}
    m['conditions'].append(travel)
    m['boundary_dofs']+=deepcopy(travel['boundary_dofs'])
    first,second=m['analysis_steps']['steps']
    first['curves'][0]['mode']='release'
    first['curves'].append({'condition_id':'Travel','component':3,'unit':'mm','points':[[0,0],[.5,.1]]})
    second['curves'][0]['points']=[[0,0],[.5,10]]
    second['curves'].append({'condition_id':'Travel','component':3,'unit':'mm','mode':'release','points':[]})
    assert render(m).count('*STEP,')==2
    legacy=deepcopy(m); legacy.pop('analysis_steps')
    with pytest.raises(ValueError,match='overlaps'):
        render(legacy)
    simultaneous=deepcopy(m)
    simultaneous['analysis_steps']['steps'][0]['curves'][0].pop('mode')
    with pytest.raises(ValueError,match='겹칩니다'):
        render(simultaneous)
    # Different baseline SPC values can own the same DOF if never simultaneous.
    other=deepcopy(travel); other.update(object_id='Other',components_mm={3:.2})
    other['boundary_dofs'][0]['value_mm']=.2
    m['conditions'].append(other)
    first['curves'].append({'condition_id':'Other','component':3,'unit':'mm','mode':'release','points':[]})
    second['curves'][0]['mode']='release'
    second['curves'].append({'condition_id':'Other','component':3,'unit':'mm','points':[[0,.1],[.5,.2]]})
    validate_contributions(m)
    assert render(m).count('*BOUNDARY,OP=NEW')==2
    first['curves'][-1].update(mode='curve',points=[[0,0],[.5,.2]])
    with pytest.raises(ValueError,match='충돌'):
        render(m)


def test_compiled_union_integer_contributions_and_native_clock_admission(model):
    m=staged(model)
    original=deepcopy(m['conditions'][1]); original['object_id']='Other'
    m['conditions'].append(original); m['loads'][0]['force_N']=-20.
    for step in m['analysis_steps']['steps']:
        step['curves'][0]['points']=[[0,0],[.25000000000001,1],[.5,0]]
        step['curves'].append({'condition_id':'Other','component':0,'unit':'N',
            'points':[[0,0],[.25000000000002,1],[.5,0]]})
    with pytest.raises(ValueError,match='정밀도'):
        render(m)
    for kind in ('force_weights','boundary_dofs'):
        bad=staged(model)
        rows=bad['conditions'][1 if kind=='force_weights' else 0][kind]
        rows[0]['node_id']=float(rows[0]['node_id'])
        with pytest.raises(ValueError,match='owning body'):
            render(bad)
    tiny=staged(model)
    first,second=tiny['analysis_steps']['steps']
    first.update(duration=1.,maximum=1.)
    first['curves'][0]['points']=[[0,0],[1.,10]]
    second.update(duration=1e-10,initial=1e-10,minimum=1e-11,maximum=1e-10)
    second['curves'][0]['points']=[[0,10],[1e-10,0]]
    with pytest.raises(ValueError,match='출력 정밀도'):
        render(tiny)


@pytest.mark.parametrize('terminator',['interior','final','missing'])
def test_partial_prefix_never_erases_native_end_markers(model,tmp_path,terminator):
    m=staged(model); frd,_,materials=two_step_outputs(m)
    lines=frd.splitlines()
    if terminator=='interior':
        index=next(i for i,line in enumerate(lines)
            if line.split()[:1]==['1PSTEP'] and int(line[48:60])==2)
        lines.insert(index,' 9999')
    elif terminator=='missing':
        lines=[line for line in lines if line.strip()!='9999']
    fp=tmp_path/'native.frd'; fp.write_text('\n'.join(lines)+'\n',encoding='ascii',newline='\n')
    sp=tmp_path/'native.sta'
    sp.write_text(' 1 1 1 3 .5 .5 .5\n 2 1 1 3 1.0 .5 .5\n',encoding='ascii')
    status=read_status(sp,m); nodes,elements,_=validate_model(m)
    original=fp.read_bytes()
    if terminator=='interior':
        with pytest.raises(ValueError):
            read_frd(fp,nodes,elements,contact_materials=materials,contact_profile=profile(m))
        with pytest.raises(ValueError,match='end marker'):
            retained_prefix(fp,tmp_path/'derived.frd',nodes,elements,materials,m,status)
        assert not (tmp_path/'derived.frd').exists()
    else:
        parsed=retained_prefix(fp,tmp_path/'derived.frd',nodes,elements,materials,m,status)
        assert len(parsed['frames'])==2
    assert fp.read_bytes()==original


def test_explicit_condition_reconcile_keeps_partial_text_and_restores_export(model):
    from caelab.contact_steps import reconcile_program
    m=staged(model)
    m['analysis_steps']['steps'][0]['curves'][0]['points'][1][1]='1e'
    other=deepcopy(m['conditions'][1]); other.update(object_id='Other',label='새 힘')
    m['conditions'].append(other); m['loads'][0]['force_N']=-20.
    before=deepcopy(m['analysis_steps'])
    repaired=reconcile_program(before,m['conditions'])
    assert before==m['analysis_steps'] and len(before['steps'][0]['curves'])==1
    assert repaired['steps'][0]['curves'][0]['points'][1][1]=='1e'
    assert repaired['steps'][0]['curves'][1]['points']==[[0,0],[.5,10.]]
    assert repaired['steps'][1]['curves'][1]['mode']=='hold'
    m['analysis_steps']=repaired
    with pytest.raises(ValueError,match='complete finite'): render(m)
    m['analysis_steps']['steps'][0]['curves'][0]['points'][1][1]='10'
    assert render(m).count('*STEP,')==2
    m['conditions']=m['conditions'][:1]+[other]
    m['loads'][0]['force_N']=-10.
    m['analysis_steps']=reconcile_program(m['analysis_steps'],m['conditions'])
    assert all([c['condition_id'] for c in s['curves']]==['Other'] for s in m['analysis_steps']['steps'])
    assert render(m).count('*STEP,')==2
