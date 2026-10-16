from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from connector_correction_fixture import fixture
from test_connector_model import draft
from test_connector_fe import fe_draft
from impact_b_fixtures import history_bytes
from caelab.connector_model import model
from caelab.connector_deck import TOKENS
from caelab.connector_results import read,catalog
from caelab.connector_admission import read_bodies,expected_bodies
from caelab.storage import save_json,load_json
from caelab.dynamic_result_store import file_pin
from caelab.execution_control import CancellationToken,cancellation_scope,ExecutionCancelled


def test_public_path_rejected_before_read(monkeypatch):
    from caelab.adapters.opencourant_connector import ConnectorAdapter
    def forbidden(*a,**kw):raise AssertionError('public validation read a caller path')
    monkeypatch.setattr(Path,'read_text',forbidden)
    a=ConnectorAdapter()
    for method in (a.validate_settings,a.describe_ports,a.describe_model):
        with pytest.raises(ValueError,match='서버 파일 경로'):method({'data_id':'D1','snapshot_path':'C:/private/file'})
        assert method({'data_id':'D1'})


@pytest.mark.parametrize('mode',['nan','failed','cancelled'])
def test_native_mask_and_failed_cancelled_prefix(tmp_path,monkeypatch,mode):
    import caelab.adapters.opencourant_connector as a
    from caelab.adapters.opencourant_runtime import WINDOWS_SOURCE,WINDOWS_FILES
    from caelab.evaluation import normalize_evaluation
    settings={'connector':draft()}
    source=tmp_path/'source';source.mkdir();fixture(source)
    data,titles,_=history_bytes([{'id':1,'type':3,'title':'CONTROLLED_TYPE13','members':[1],'tokens':list(TOKENS)}],nan=mode=='nan')
    token=CancellationToken()
    def command(argv,native,label,**kw):
        if label=='starter':
            (native/'connector_0000.out').write_bytes((source/'native/connector_0000.out').read_bytes())
        else:
            (native/'connectorT01').write_bytes(data if mode=='nan' else data[:-8])
            (native/'connectorT01_TITLES').write_bytes(titles)
            if mode=='cancelled':token.request();token.check()
            if mode=='failed':return SimpleNamespace(returncode=1,stdout='controlled failure')
        return SimpleNamespace(returncode=0,stdout='controlled')
    identity={'platform':'win64','source_tag':WINDOWS_SOURCE,'files':WINDOWS_FILES}
    monkeypatch.setattr(a,'selected_runtime',lambda:({'starter':'NO_EXECUTION','engine':'NO_EXECUTION'},{},identity))
    monkeypatch.setattr(a,'run_owned_command',command)
    monkeypatch.setattr(a,'engine_termination',lambda *args:{'status':'NORMAL'})
    out=tmp_path/'result'
    with cancellation_scope(token):
        result=a.ConnectorAdapter().run(settings,output=out)
        if mode=='cancelled':assert token.requested and token.observed and len(result.get('native_channels',{}))==15
    result=normalize_evaluation(result)
    saved=load_json(out/'connector_execution.json')
    assert result['execution_status']=={'nan':'SUCCEEDED','failed':'FAILED','cancelled':'CANCELLED'}[mode]
    assert len(result['native_channels'])==15 and result['native_result']['backend']==a.domain.BACKEND
    if mode=='nan':
        assert 'connector.IE' not in result['responses'] and 'connector.FX' in result['responses']
        selected=read(saved,out,'connector.IE');assert selected['mask']==[True,False,True] and selected['value'][1] is None
        from caelab.evaluation import _select_native
        _select_native(result,out,['connector.IE'],saved)
        assert result['responses']['connector.IE']['mask']==[True,False,True]
    else:
        selected=read(saved,out,'connector.FX');assert len(selected['value'])==2
        assert saved['execution_status']==mode.upper()
        if mode=='cancelled':assert not (out/'connector_history.json').exists()
    assert len(catalog(saved,out))==15


def test_native_body_mismatch_does_not_admit_positive_wrong_values(tmp_path):
    _,outcome=fixture(tmp_path)
    mapping=load_json(tmp_path/'connector_mapping.json');path=tmp_path/'native/connector_0000.out'
    original=path.read_text(encoding='ascii');assert read_bodies(path,mapping,fe=False)['status']=='PASS'
    for old,new in [('NEW MASS 0.001','NEW MASS 0.002'),('NEW INERTIA xx yy zz 0.0010005','NEW INERTIA xx yy zz 0.0020005'),('NEW X,Y,Z 0 0 0','NEW X,Y,Z 1 0 0'),('SECONDARY NODES\n\n','SECONDARY NODES\n99\n\n')]:
        assert old in original
        path.write_text(original.replace(old,new,1),encoding='ascii')
        with pytest.raises(ValueError):read_bodies(path,mapping,fe=False)
    path.write_text(original,encoding='ascii')


def test_fe_explicit_excitation_and_conflict_are_checked_before_freeze():
    d=fe_draft();d['fe']['initial_motion_source']='endpoint_patch'
    d['endpoints'][1]['velocity_mm_s']=['.3','0','0'];d['endpoints'][1]['omega_rad_s']=['.2','0','0']
    before=deepcopy(d);m=model(d);assert m['endpoints'][1]['velocity_mm_s']==[.3,0,0] and d==before
    d['fe']['settings']['source']['text']+='*NSET,NSET=MOVING\n5,6,7,8\n'
    d['fe']['settings']['motions']=[{'node_set':'MOVING','mode':'velocity','velocity_mm_s':[.4,0.,0.],
        'omega_rad_s':[0.,0.,0.],'center_mm':[10.,0.,0.],'translation_mm':[0.,0.,0.],'height_mm':None}]
    with pytest.raises(ValueError,match='초기운동.*다릅니다'):model(d)


def test_fe_mass_uses_all_incident_tetra_and_spring_once():
    d=fe_draft();s=d['fe']['settings'];s['source']['text']=s['source']['text'].replace('1,1,2,3,4','1,2,1,3,4').replace('2,5,7,6,8','2,5,6,7,8')
    from caelab.connector_fe import append
    from caelab.impact_model import model_from_settings
    m=model(d);base=model_from_settings(s)
    _,mapping=append('/BEGIN\nimpact\n      2025         0\n/NODE\nORIGINAL\n/END\n',m,base)
    mapping['nodes']=[*base['nodes'].items(),*[(r['connector_reference'],m['endpoints'][i]['reference_mm']) for i,r in enumerate(mapping['attachments'])],*[(r['native_cog_main'],m['endpoints'][i]['reference_mm']) for i,r in enumerate(mapping['attachments'])]]
    expected=expected_bodies(m,mapping,base)
    assert expected[0]['mass_Mg']==pytest.approx(7.8e-9/8)
    assert expected[0]['position_mm']==pytest.approx([0,1/3,1/3])
    assert expected[0]['secondary_nodes']==[1,2,3,9]


def test_native_linear_quality_uses_existing_jacobian_floors():
    from apps.desktop_pre.connector_fe_native import validate_native_mesh
    pts={1:(0,0,0),2:(0,1,0),3:(0,0,1),4:(-1,0,0)}
    class Mesh:
        Volumes=[1]
        Nodes={n:SimpleNamespace(x=p[0],y=p[1],z=p[2]) for n,p in pts.items()}
        def getElementNodes(self,n):return [1,2,3,4]
    mesh=SimpleNamespace(FemMesh=Mesh(),Label='actual tetra')
    validate_native_mesh(mesh)
    mesh.FemMesh.Nodes[4]=SimpleNamespace(x=1,y=0,z=0)
    with pytest.raises(ValueError,match='Jacobian'):validate_native_mesh(mesh)


def test_axis_2025_required_start_sensor_does_not_change_2022():
    from caelab.connector_deck import motion_cards
    args=([0,0,0],[.3,0,0],[.2,0,0],{'x':[1,0,0],'y':[0,1,0],'z':[0,0,1]})
    old,_=motion_cards(*args,group=12,ident=10,frame=110)
    new,_=motion_cards(*args,group=12,ident=10,frame=110,version=2025)
    assert new[:-1]==old and float(new[-1][:20])==0 and int(new[-1][20:])==0


def test_reopened_selection_uses_existing_exact_fem_proof_only():
    from apps.desktop_pre.connector_edit import _same_selection
    saved={'label':'실제면','native_refs':[{'object_id':'A','subelements':['Face1']}],
        'reference_mm':[0,0,0],'identity':{'document_id':'P1','native_document':'Source',
        'objects':[{'object_id':'A','brep_sha256':'old','subelements':[{'name':'Face1','brep_sha256':'oldface'}]}]}}
    current=deepcopy(saved);current['identity']['objects'][0]['brep_sha256']='serialized'
    calls=[]
    owner=SimpleNamespace(fem=SimpleNamespace(_same_condition_target=lambda a,b:calls.append((a,b)) or True))
    assert _same_selection(owner,saved,current) and len(calls)==1
    changed=deepcopy(current);changed['reference_mm']=[1,0,0]
    assert not _same_selection(owner,saved,changed) and len(calls)==1
    owner.fem._same_condition_target=lambda a,b:False
    assert not _same_selection(owner,saved,current)


def test_six_modes_k_only_c_only_combined_native_card_projection():
    from caelab.connector_deck import starter
    for axis in range(6):
        for k,c in ((7.,0.),(0.,.25),(7.,.25)):
            d=draft();d['k']=['0']*6;d['c']=['0']*6;d['k'][axis]=str(k);d['c'][axis]=str(c)
            m=model(d);rows=starter(m).split('/PROP/TYPE13/1\n')[1].splitlines()
            for i in range(6):
                line=rows[2+i*3]
                assert float(line[:20])==(k if i==axis else 0.)
                assert float(line[20:40])==(c if i==axis else 0.)
