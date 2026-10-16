"""Finite connector gate/unit/deck boundaries, no solver invocation."""
from copy import deepcopy
import json
import math
import pytest
from caelab.connector_model import default_draft,model,validate_settings,ConnectorInputError
from caelab.connector_deck import starter,engine


def draft():
    d=default_draft('실제 대상 연결')
    for i,e in enumerate(d['endpoints']):
        p=[i*10.,0.,0.]
        e.update(selection={'label':'실제점'+str(i),'reference_mm':p,'points_mm':[p],
            'kind':'vertex','native_refs':[{'object_id':'Body'+str(i),'subelements':['Vertex1']}],
            'identity':{'document_id':'P1','object_pin':'a'+str(i)}},
            rigid_attachment=True,reference_is_mass_center=True)
        e['mass']['value']='1';e['inertia']['values']=['1','1','1','0','0','0']
    d.update(k=['100','0','0','10','0','0'],c=['2','0','0','.5','0','0'])
    d['axes']={'x':['1','0','0'],'y':['0','1','0'],'z':['0','0','1']}
    d['time'].update(end_s='.02',history_interval_s='.001')
    d['connector_mass']['value']='0';d['connector_inertia']['value']='.001'
    return d


def test_units_and_exact_card_fields():
    d=draft();m=model(d);a=starter(m)
    assert m['k']==[100,0,0,10,0,0] and m['c']==[2,0,0,.5,0,0]
    assert m['endpoints'][0]['mass_Mg']==.001
    assert m['endpoints'][0]['inertia_Mg_mm2']==[.001,.001,.001,0,0,0]
    common=a.split('/PROP/TYPE13/1\n')[1].splitlines()[1]
    assert len(common)==100 and int(common[40:50])==1
    assert '/TFILE/4\n' in engine(m) and '/SPRING/1\n' in a
    assert '/RBODY/1\n' in a and 'OFF' in a
    assert validate_settings({'connector':d})=={'connector':d}


def test_si_and_angle_coefficients_convert_once():
    d=draft();d['units'].update(translation_k='N/m',translation_c='N*s/m',rotation_k='N*m/rad',rotation_c='N*mm*s/deg')
    d['k'][0]='100000';d['c'][0]='2000';d['k'][3]='.01';d['c'][3]=str(.5*math.pi/180)
    m=model(d);assert m['k'][0]==100 and m['c'][0]==2 and m['k'][3]==10
    assert m['c'][3]==pytest.approx(.5)


@pytest.mark.parametrize('change,path',[
    (lambda d:d['axes']['y'].__setitem__(1,'-1'),'axes'),
    (lambda d:d['endpoints'][1]['selection'].__setitem__('reference_mm',[0,0,0]),'endpoints'),
    (lambda d:d['endpoints'][0].__setitem__('rigid_attachment',False),'endpoints.0'),
    (lambda d:d['endpoints'][0]['mass'].__setitem__('value',''),'endpoints.0.mass.value'),
    (lambda d:d['endpoints'][0]['inertia'].__setitem__('values',['3','1','1','0','0','0']),'endpoints.0.inertia'),
    (lambda d:d['connector_inertia'].__setitem__('value','0'),'connector_inertia'),
    (lambda d:d['k'].__setitem__(0,'-1'),'k'),
    (lambda d:d['time'].__setitem__('scale','NaN'),'time.scale'),
])
def test_invalid_preserved_but_run_blocked(change,path):
    d=draft();change(d);original=deepcopy(d)
    with pytest.raises(ConnectorInputError) as err:model(d)
    assert err.value.path==path and d==original
    assert json.loads(json.dumps(d,ensure_ascii=False))==d


def test_native_mass_floor_not_hidden():
    d=draft();d['connector_inertia']['value']='1e-18'
    with pytest.raises(ConnectorInputError,match='1e-20'):model(d)
    assert d['connector_inertia']['value']=='1e-18'


def test_fixed_velocity_collision():
    d=draft();d['endpoints'][1]['fixed'][3]=True;d['endpoints'][1]['omega_rad_s'][0]='1'
    with pytest.raises(ConnectorInputError,match='초기 속도'):model(d)


def test_angular_velocity_uses_one_axis_field_at_actual_reference():
    d=draft();d['endpoints'][1]['velocity_mm_s']=['1','2','3'];d['endpoints'][1]['omega_rad_s']=['.1','.2','.3']
    text=starter(model(d))
    assert '/FRAME/FIX/102\n' in text and '/INIVEL/AXIS/2\n' in text
    assert '/INIVEL/TRA/2\n' not in text
    axis=text.split('/INIVEL/AXIS/2\n')[1].splitlines()
    assert axis[1][:10].strip()=='Z' and int(axis[1][10:20])==102 and int(axis[1][20:30])==12
    assert len(axis[2])==80
