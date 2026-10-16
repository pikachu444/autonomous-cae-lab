from copy import deepcopy
import pytest
from test_connector_model import draft
from caelab.connector_model import model,ConnectorInputError
from caelab.connector_fe import validate_fe,append
from caelab.impact_model import default_settings,model_from_settings
from caelab.storage import canonical_hash


def fe_draft():
    d=draft();s=default_settings()
    s['source']['text']='''*NODE
1,0,0,0
2,0,1,0
3,0,0,1
4,-1,0,0
5,10,0,0
6,10,1,0
7,10,0,1
8,11,0,0
*ELEMENT,TYPE=C3D4,ELSET=ALL
1,1,2,3,4
2,5,7,6,8
*MATERIAL,NAME=ELASTIC
*DENSITY
7.8e-9
*ELASTIC
210000,.3
*SOLID SECTION,ELSET=ALL,MATERIAL=ELASTIC
'''
    s['source']['provenance']={'kind':'native_FE_capture','document_id':'P1'}
    attachments=[]
    for i,ids in enumerate(([1,2,3],[5,6,7])):
        attachments.append({'native_node_ids':ids,'selection_sha256':canonical_hash(d['endpoints'][i]['selection']),
                            'body_id':'Body'+str(i),'mesh_id':'Mesh'+str(i)})
    d['fe']={'analysis_id':'Analysis','solver_id':'Solver','settings':s,
             'attachments':attachments,'source_binding':[{'exact':'native binding'}]}
    return d


def test_fe_single_mass_source_and_original_cards_unchanged():
    d=fe_draft()
    for end in d['endpoints']:
        end['mass']['value']='';end['inertia']['values']=['']*6;end['reference_is_mass_center']=False
    m=model(d);assert [e['mass_Mg'] for e in m['endpoints']]==[0,0]
    base=model_from_settings(d['fe']['settings'])
    original='/BEGIN\nimpact\n      2025         0\n/NODE\nEXACT_ORIGINAL_NODE_ROWS\n/PROP/SOLID/1\nORIGINAL_LAW1_PROPERTY\n/PART/1\nORIGINAL_PART\n/END\n'
    effective,receipt=append(original,m,base)
    assert effective.startswith(original[:original.rfind('/END')])
    assert receipt['spring_element']==3 and receipt['original_cards_preserved'] is True
    for a in receipt['attachments']:
        assert a['ICoG']==2 and a['additional_mass']==0 and a['additional_inertia']==[0]*6
        assert a['native_cog_main'] not in a['secondary_nodes']
        assert a['connector_reference'] in a['secondary_nodes']


@pytest.mark.parametrize('change,message',[
    (lambda d:d['fe']['attachments'][0]['native_node_ids'].append(4),'사면체 전체'),
    (lambda d:d['fe']['attachments'][1].__setitem__('native_node_ids',[1,5,6]),'겹치지'),
    (lambda d:d['fe']['settings']['time'].__setitem__('mass_scaling',True),'목표'),
    (lambda d:d['endpoints'][0]['selection'].__setitem__('label','changed'),'다시 가져'),
    (lambda d:d['endpoints'][0]['fixed'].__setitem__(0,True),'원 구속'),
])
def test_fe_boundaries_preserve_draft(change,message):
    d=fe_draft();change(d);before=deepcopy(d)
    with pytest.raises(ValueError,match=message):model(d)
    assert d==before


def test_existing_bc_not_deleted_to_attach():
    d=fe_draft();d['fe']['settings']['source']['text']+='*BOUNDARY\n1,1,3,0\n'
    with pytest.raises(ConnectorInputError,match='기존 구속'):model(d)


def test_source_assembly_preserves_body_ids_and_native_tet_order():
    from apps.desktop_pre.connector_fe_native import assemble
    rows=[{'body_id':'A','nodes':[{'node_id':n,'position_mm':[n,0,0]} for n in range(1,5)],
           'elements':[{'element_id':99,'native_node_ids':[1,2,3,4]}]}]
    result=assemble(rows)
    assert result['elements'][0]['node_ids']==[2,1,3,4]
    assert result['body_maps']['A']['elements']=={99:1}


def test_fe_original_initial_velocity_is_projected_to_new_main_only():
    d=fe_draft();s=d['fe']['settings'];s['source']['text']+='*NSET,NSET=MOVING\n5,6,7,8\n'
    s['motions']=[{'node_set':'MOVING','mode':'velocity','velocity_mm_s':[.3,0.,0.],
                   'omega_rad_s':[0.,0.,0.],'center_mm':[10.,0.,0.],'translation_mm':[0.,0.,0.],'height_mm':None}]
    m=model(d);base=model_from_settings(s)
    original='/BEGIN\nimpact\n      2025         0\n/NODE\nORIGINAL\n/INIVEL/TRA/1\nORIGINAL_FE_VELOCITY_ROWS\n/END\n'
    effective,receipt=append(original,m,base)
    assert effective.startswith(original[:original.rfind('/END')])
    assert receipt['attachments'][1]['initial_field_projection']['velocity_mm_s']==[.3,0.,0.]
    assert receipt['attachments'][0]['initial_field_projection']['velocity_mm_s']==[0.,0.,0.]
    assert effective.count('/INIVEL/TRA/')==2
