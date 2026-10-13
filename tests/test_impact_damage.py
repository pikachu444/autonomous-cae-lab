"""Real pinned converter/cards and explicit synthetic readback doubles; no solver by default."""
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import pytest
from examples.impact.cohesive_model import settings
from caelab.impact_model import render,parse_inp,validate_settings
from caelab.impact_damage import apply_laws,verify_laws
from caelab.adapters.impact_admission import global_gravity,normalize_surfaces,validate_physics,cards
from caelab.adapters.impact import converted_mesh


def converted(tmp_path,s):
    import caelab.adapters.inp2rad_worker as worker
    text,initial=render(s);path=tmp_path/'impact.inp';path.write_text(text,encoding='ascii',newline='\n')
    result=subprocess.run([sys.executable,worker.__file__,str(path)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    native=(tmp_path/'impact_0000.rad').read_text(encoding='ascii')
    return native,initial


def test_pinned_cohesive_conversion_exact_law_and_model_binding(tmp_path):
    from caelab.model_parameters import bind
    from caelab.adapters.impact import ImpactAdapter
    s=settings();original=deepcopy(s);model=parse_inp(s['source']['text'])
    raw,initial=converted(tmp_path,s)
    assert raw.startswith('#RADIOSS STARTER')
    converted_mesh(tmp_path/'impact_0000.rad',model,initial['nodes'])
    adjusted,_=global_gravity(raw,s['gravity_mm_s2'])
    adjusted,surfaces=normalize_surfaces(adjusted,model)
    physical=validate_physics(adjusted,model,initial,s)
    assert len(surfaces)==2
    for key,rows in cards(adjusted).items():
        if key.startswith('/SURF/SEG/'):
            assert len(rows[1])==50
            fields=[int(rows[1][i:i+10]) for i in range(0,50,10)]
            assert fields[0]>0 and len(set(fields[1:]))==4
    effective,receipt=apply_laws(adjusted,{**model,'nodes':initial['nodes']},s['cohesive'])
    verify_laws(effective,model,s['cohesive'],receipt)
    assert set(receipt['elements'])=={'2'} and receipt['geometry']['2']['thickness_mm']==pytest.approx(.02)
    assert effective.startswith('#RADIOSS STARTER') and '/MAT/LAW59/' in raw and '/MAT/LAW59/' not in effective
    assert len(physical['material_by_element'])==3
    law=next(v for k,v in cards(effective).items() if k.startswith('/MAT/LAW117/'))
    assert [int(law[2][i:i+10]) for i in (40,50,60)]==[2,1,1]
    changed=bind(ImpactAdapter(),s,{'cohesive_0_normal_strength_mpa':2.5})
    assert changed['cohesive'][0]['normal_strength_mpa']==2.5
    assert changed['source']==s['source'] and s==original


def test_invalid_energy_orientation_and_missing_law_are_not_silently_repaired():
    s=settings();s['cohesive'][0]['mode_I_n_mm']=.001
    with pytest.raises(ValueError,match='탄성 에너지'):validate_settings(s)
    s=settings();s['cohesive']=[]
    with pytest.raises(ValueError,match='LAW117'):validate_settings(s)
    s=settings();s['source']['text']=s['source']['text'].replace('9,0,0,1.02','9,0,0,.99')
    with pytest.raises(ValueError):validate_settings(s)


def frames(tmp_path):
    """Explicit double of already converted native arrays, not native execution."""
    model=parse_inp(settings()['source']['text']);base=model['nodes'];output=[]
    for i,t in enumerate((0.,.1,.3)):
        positions=deepcopy(base)
        for n in range(9,17):positions[n][2]+=i*.01
        native=tmp_path/f'frame{i}.vtk';native.write_text('synthetic array contract '+str(i),encoding='ascii')
        raw={'time':t,'points':list(positions.values()),
             'cells':[[n-1 for n in model['elements'][e]['nodes']] for e in (1,2,3)],'types':[12,12,12],
             'POINTS':{'NODE_ID':{'components':1,'values':list(base)},
                       'Contact_Forces':{'components':3,'values':[v for n in base for v in (0.,0.,float(i*10))]},
                       'Acceleration':{'components':3,'values':[0.]*48}},
             'CELLS':{'ELEMENT_ID':{'components':1,'values':[1,2,3]},
                      'EROSION_STATUS':{'components':1,'values':[1,1,1]},
                      '3DELEM_Damage':{'components':1,'values':[0.,i*.2,0.]},
                      '3DELEM_Stress':{'components':9,'values':[0.]*27}}}
        output.append((native,raw))
    from caelab.impact_damage import validate
    receipt={'elements':{'2':{'law':'LAW117'}},'geometry':validate(model,settings()['cohesive'])}
    return model,output,receipt


def test_exact_selected_force_derived_impulse_damage_opening_and_missing_rows(tmp_path):
    from caelab.impact_responses import read_selected
    from caelab.adapters.impact_results import write_post
    model,raw,receipt=frames(tmp_path)
    selections=settings()['responses']+[
        {'name':'force','quantity':'contact_force','identity':13,'component':'Z'},
        {'name':'impulse','quantity':'contact_impulse','identity':13,'component':'Z'}]
    result,record=read_selected(raw,model,selections,receipt)
    assert result['force']['value']==[0.,10.,20.] and result['force']['unit']=='N'
    assert result['impulse']['value']==pytest.approx([0.,.5,3.5])
    assert result['impulse']['metadata']['origin']=='DERIVED'
    assert result['opening']['value']==pytest.approx([0.,.01,.02])
    assert result['damage']['value']==[0.,.2,.4]
    metadata=write_post(tmp_path/'post',raw,damage=receipt)
    assert next(v for v in metadata['arrays'] if v['name']=='3DELEM_Damage')['measure']=='LAW117_mean_damage'
    # A missing middle contact array never becomes a zero or a bridged integral.
    del raw[1][1]['POINTS']['Contact_Forces']
    result,record=read_selected(raw,model,selections,receipt)
    assert result['force']['value']==[0.,20.] and result['force']['has_calculation_gaps']
    assert result['impulse']['value']==[0.] and record['impulse']['values']==[0.,None,None]
    assert record['impulse']['reasons'][2]
    raw[2][1]['CELLS']['EROSION_STATUS']['values'][1]=0
    result,_=read_selected(raw,model,selections,receipt)
    assert result['damage']['raw_samples']['quality_valid']==[True,True,False]
    assert result['opening']['raw_samples']['quality_valid']==[True,True,False]


@pytest.mark.skipif(os.environ.get('CAELAB_RUN_COHESIVE_IMPACT')!='1',reason='explicit installed LAW117 workflow check')
def test_installed_cohesive_law_and_retained_selected_fields(tmp_path):
    from caelab.evaluation import run,read_result
    from caelab.impact_model import BACKEND
    result=run(BACKEND,settings(),output=tmp_path/'actual'/'calculation')
    assert result['execution_status']=='SUCCEEDED',result
    assert result['responses']['damage']['value']
    assert result['responses']['opening']['metadata']['origin']=='DERIVED'
    saved=read_result(tmp_path/'actual'/'calculation',verify='all')
    assert saved['responses']['damage']==result['responses']['damage']
