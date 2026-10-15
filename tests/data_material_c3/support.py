from copy import deepcopy
import json
from pathlib import Path
import uuid
import numpy as np

from caelab.workbench import Workbench
from caelab.storage import canonical_hash
from caelab.related_save_recovery import RawRecoveryDrafts
from caelab.experiment_calibration import default_calibration


def plain(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False,
        default=lambda v: v.tolist() if isinstance(v, np.ndarray) else v.item()))


def command(owner, document, operation, arguments=None):
    return owner.command(document['id'], operation, arguments or {},
        session_id=document['session_id'], expected_generation=document['generation'],
        command_id='C'+uuid.uuid4().hex)


def raw_for(document):
    # The live editor holds text that is deliberately not a Data ID or a float.
    return {'editor_revision': 'C3-editor-1e', 'cells': [{'field_path': ['data_id'],
        'original_value': document['draft']['data_id'], 'raw_text': '1e',
        'position': {'row': 1, 'column': 2, 'table': '시험 원본'}, 'editor_kind': 'text'}],
        'focus': {'field_path': ['data_id'], 'cursor': 2},
        'paste': {'raw_text': '1e\t\nINVALID_ENUM', 'committed': False}}


def mapping(certificate):
    cal = default_calibration('N')
    cal.update(a=2., sensor='Synthetic certificate fixture, not laboratory calibration',
        source={k:certificate[k] for k in ('sha256','name')},
        displacement_role='not_displacement')
    cal['source']['data_id'] = certificate['id']
    axis = {'column': 'time_s', 'name': 'time', 'unit': 's'}
    common = {'component': 'xx', 'frame': 'material_cartesian', 'location': 'material_point',
              'reduction': 'none', 'axis': axis, 'row_selection': {'display_hidden_rows': [2]}}
    return {'delimiter': ',', 'columns': {
        'force': {**deepcopy(common), 'column': 'signal_mV', 'unit': 'N', 'measure': 'force', 'calibration': cal},
        'extension': {**deepcopy(common), 'column': 'extension_mm', 'unit': 'mm', 'measure': 'gauge_extension'},
        'temperature': {**deepcopy(common), 'column': 'temperature_C', 'unit': 'C', 'measure': 'absolute_temperature'}}}


def recipe():
    return {'version': 1, 'operations': [
        {'id':'e','operation':'engineering_strain','input':'extension','output':'e',
         'settings':{'L0':50.,'length_unit':'mm','measurement':'extensometer_gauge_extension'}},
        {'id':'P','operation':'nominal_stress','input':'force','output':'P11',
         'settings':{'A0':20.,'area_unit':'mm2'}},
        {'id':'T','operation':'convert','input':'temperature','output':'T_K',
         'settings':{'quantity':'absolute_temperature','to_unit':'K'}}]}


def fixture_path():
    return Path(__file__).resolve().parents[2] / 'examples' / 'data_material_c3' / 'fixtures'


def basic(w):
    fixtures=fixture_path()
    source=w.upload('시험 A.csv',(fixtures/'A.csv').read_bytes())
    cert=w.upload('교정 계수 A.csv',(fixtures/'calibration_A.csv').read_bytes())
    draft={'data_id':source['id'],'mapping':mapping(cert)}
    d=w.document_open(kind='data',draft=draft)
    return d,source,cert


def import_data(w,d):
    response=command(w.data_documents,d,'data.import')
    job=response['job'];w.manager._futures[job['id']].result(timeout=20)
    assert w.manager.status(job['id'])['state']=='SUCCEEDED'
    return w.document_read(d['id']),job['id']


def build_history(w):
    from caelab.material_document import default_draft
    from caelab.material_test import measured_protocol, deformation_plot_axis
    from caelab.numerical_document import from_material_document
    from caelab.data_material_service import DataMaterialService
    fixtures=fixture_path(); registrations=[]; drafts=[]
    for name in 'ABCD':
        src=w.upload(f'시험 {name}.csv',(fixtures/(name+'.csv')).read_bytes())
        cert=w.upload(f'교정 {name}.csv',(fixtures/('calibration_'+name+'.csv')).read_bytes())
        acq=w.upload(f'수집 교정 {name}.csv',(fixtures/('acquisition_'+name+'.csv')).read_bytes())
        registrations.extend([src,cert,acq])
        draft={'data_id':src['id'],'mapping':mapping(cert),'acquisition':{'channels':[
            {'name':'unrun acquisition','calibration':{'source':{'data_id':acq['id'],
             'sha256':acq['sha256'],'name':acq['name']}}}]}}
        drafts.append(draft)
    d=w.document_open(kind='data',draft=drafts[0]);d,jid=import_data(w,d)
    imported=w.data_documents.result(d['id'],jid)
    run=d['runs'][0]
    origin={'document_id':d['id'],'job_id':jid,'input_revision':run['input_revision'],'input_sha256':run['input_sha256']}
    for draft in drafts[1:]:
        draft['processing']={'source':deepcopy(origin),'recipe':recipe()}
        d=command(w.data_documents,d,'data.update',{'draft':draft})['document']
    d=command(w.data_documents,d,'document.undo')['document']  # current C; Undo A/B; Redo D; run A
    preview=w.data_documents.processing_preview(d['id'])
    applied=command(w.data_documents,d,'data.processing.apply',{'preview_sha256':preview['preview_sha256']})
    d=applied['document'];pid=applied['processing']['id']
    processed=w.data_documents.processing_result(d['id'],pid,selection=['P11','e'])
    kin={'channel':'e','kind':'engineering_strain','lateral_22':1.,'lateral_33':1.}
    md=default_draft();md['settings'].update(model='neo_hooke',parameters={'mu':2.,'lmbda':6.})
    md['settings']=measured_protocol(md['settings'],processed,kin)
    m=w.document_open(kind='material',draft=md)
    nd=from_material_document(m)
    nd['experiments']=[{'id':'Eobserved','role':'fit','source':{**origin,'response':'P11','processing_revision':pid},
        'response':'stress_xx','settings':deepcopy(md['settings']),'weight':1.,'scale':1.,'kinematics':kin}]
    n=w.document_open(kind='numerical',draft=nd)
    service=DataMaterialService(w)
    proposal=service.sample_policy_preview(d['id'],pid,'P11')
    n=service.sample_policy_adopt(n['id'],'Eobserved',proposal,
        session_id=n['session_id'],expected_generation=n['generation'],command_id='C3ExplicitPolicy')['document']
    args=w.numerical_documents.job_arguments(n['draft'])  # compile/read only, NEVER numerical.run
    assert args['experiments']
    unack=w.upload('미적용 GUI 선택.csv',b'x,y\n0,12345\n')
    unrelated=w.upload('관련 없음.csv',b'unrelated\n456\n')
    raw=raw_for(d);raw['local_draft']=deepcopy(d['draft']);raw['local_draft']['data_id']=unack['id']
    return {'data':d,'material':m,'plan':n,'raw':raw,'registrations':registrations,
        'unacknowledged':unack,'unrelated':unrelated,'job_id':jid,'processing_id':pid,
        'imported':imported,'processed':processed,'plan_args':args,'kinematics':kin,
        'plot_axis':deformation_plot_axis(processed['responses']['P11'],processed,kin)}


def keep(w,d,raw=None):
    r=RawRecoveryDrafts(w.root,w._document_owner)
    req={'identity':r.identity(d),'raw':raw or raw_for(d)}
    review=r.prepare([req]);assert not review['targets'][0]['problems'],review
    result=r.execute(review);assert result['close_permitted'],result
    target=result['targets'][0]
    return r,review,target,r._path(w.data_documents,d['id'],target['capsule_id'])
