"""Retained TYPE13 histories through the existing binary TH reader.

No numerical differentiation substitutes for native generalized deformation,
force or moment. The declared rigid attachment source is retained with every
channel; TH MY/MZ are not labelled nodal reaction moments.
"""
from copy import deepcopy
import json
import math
from pathlib import Path

from .connector_model import BACKEND,model_from_settings
from .connector_deck import TOKENS
from .dynamic_result_store import file_pin,verify_pin
from .impact_bulk_history import read as read_th,series
from .storage import canonical_hash


def units(token):
    if token in ('FX','FY','FZ'): return 'N'
    if token in ('MX','MY','MZ'): return 'N*mm'
    if token in ('LX','LY','LZ','LENGTH'): return 'mm'
    if token in ('RX','RY','RZ'): return 'rad'
    if token=='IE': return 'N*mm'
    if token=='OFF': return '1'
    raise ValueError('지원되지 않는 연결요소 채널입니다.')


def parse(output,settings,*,failed=False):
    root=Path(output);m=model_from_settings(settings)
    mapping=json.loads((root/'connector_mapping.json').read_text(encoding='utf-8'))
    name=mapping['native_run_name']
    if name not in ('connector','impact'):raise ValueError('생성한 연결요소 native 이름이 다릅니다.')
    h=read_th(root/('native/'+name+'T01'),titles=root/('native/'+name+'T01_TITLES'),failed=failed)
    factors=h['layout']['unit_factors']
    if factors is not None and any(not math.isclose(a,b,rel_tol=2**-23,abs_tol=0) for a,b in zip(factors,(1000.,.001,1.))):
        raise ValueError('TH의 실제 단위와 입력의 Mg/mm/s 단위가 다릅니다.')
    group_id=mapping['th_group'];member=mapping['spring_element']
    groups=[g for g in h['layout']['groups'] if g['id']==group_id]
    if len(groups)!=1: raise ValueError('실제 연결요소 TH 그룹이 없거나 중복됐습니다.')
    group=groups[0]
    # TITLES comes from the exact binary group, not a user-provided alias.
    if [r['id'] for r in group['members']]!=[member] or set(group.get('tokens',[]))!=set(TOKENS):
        raise ValueError('TH의 실제 요소·채널이 생성한 연결요소 출력 정의와 다릅니다.')
    bound={**group,'members':[member]}
    times=[s['time_s'] for s in h['samples']]
    data={token:series(h,bound,member,token) for token in TOKENS}
    return {'time_s':times,'values':data,'excluded':h['excluded'],
            'format_code':h['layout']['format_code'],'unit_factors':h['layout']['unit_factors'],
            'native_group':group,'model_sha256':canonical_hash(m),
            'mask':{token:[v is not None and math.isfinite(v) for v in values] for token,values in data.items()},
            'source_rows':[s['source_row'] for s in h['samples']]}


def context(outcome,output):
    root=Path(output).resolve(strict=True)
    saved=json.loads((root/'connector_execution.json').read_text(encoding='utf-8'))
    if outcome!=saved or saved.get('backend')!=BACKEND:
        raise ValueError('보존한 연결요소 실행과 선택한 결과가 다릅니다.')
    for pin in saved['artifacts']: verify_pin(root,pin)
    settings=json.loads((root/'input.json').read_text(encoding='utf-8'))
    from .adapters.opencourant_runtime import WINDOWS_SOURCE,WINDOWS_FILES
    identity=saved.get('runtime',{})
    admission=saved.get('starter_admission',{})
    if (identity.get('platform'),identity.get('source_tag'),identity.get('files'))!=('win64',WINDOWS_SOURCE,WINDOWS_FILES) or admission.get('units')!='Mg/mm/s' or admission.get('status')!='PASS':
        raise ValueError('실제 고정 runtime·Starter 단위 근거가 없습니다. 원 응답은 UNKNOWN입니다.')
    mapping=json.loads((root/'connector_mapping.json').read_text(encoding='utf-8'))
    name=mapping['native_run_name']
    if name not in ('connector','impact'):raise ValueError('보존한 native 이름이 생성된 입력과 다릅니다.')
    deferred=(saved.get('prefix_read')=='DEFERRED_CANCELLED_PREFIX' and saved['execution_status']=='CANCELLED')
    required={'input.json','connector_mapping.json',
              *['native/'+name+tail for tail in ('_0000.rad','_0001.rad','_0000.out','T01','T01_TITLES')]}
    if not deferred:required.add('connector_history.json')
    relatives=[p['relative'] for p in saved['artifacts']]
    if len(relatives)!=len(set(relatives)) or not required<=set(relatives):
        raise ValueError('단위·원 입력·native 출력의 정확한 보존 근거가 누락됐습니다.')
    deckpins=saved.get('effective_deck_pins',[])
    if {p.get('relative') for p in deckpins}!={'native/'+name+'_'+tail+'.rad' for tail in ('0000','0001')}:
        raise ValueError('실제 실행한 원 native 입력 pin이 없습니다.')
    for pin in deckpins:
        if pin not in saved['artifacts']:raise ValueError('실제 실행 입력과 보존한 파일의 근거가 다릅니다.')
        verify_pin(root,pin)
    from .adapters.impact import starter_admission
    from .connector_admission import read_bodies,expected_bodies
    m=model_from_settings(settings)
    if saved.get('model_sha256')!=canonical_hash(m):raise ValueError('보존한 실행의 원 모델이 다릅니다.')
    fe_model=None
    if m['fe'] is not None:
        from .impact_model import model_from_settings as fe_from_settings
        fe_model=fe_from_settings(m['fe']['settings'])
    if mapping.get('expected_native_bodies')!=expected_bodies(m,mapping,fe_model):
        raise ValueError('원 입력의 절점 질량·부착 근거와 보존한 계산이 다릅니다.')
    actual=starter_admission(root/('native/'+name+'_0000.out'),{'nodes':dict(mapping['nodes']),'elements':{}})
    if actual!=admission or read_bodies(root/('native/'+name+'_0000.out'),mapping,fe=m['fe'] is not None)!=saved.get('native_attachments'):
        raise ValueError('실제 Starter 단위·기준점·질량관성과 보존한 증명이 다릅니다.')
    parsed=parse(root,settings,failed=saved['execution_status']!='SUCCEEDED')
    if deferred:
        if (root/'connector_history.json').exists():raise ValueError('취소된 원본의 지연 읽기와 저장 이력이 혼합됐습니다.')
    else:
        stored=json.loads((root/'connector_history.json').read_text(encoding='utf-8'))
        if parsed!=stored: raise ValueError('원 TH와 보존한 연결요소 이력이 다릅니다.')
    return saved,settings,parsed


def catalog(outcome,output):
    saved,settings,h=context(outcome,output)
    relative=('native/'+json.loads((Path(output)/'connector_mapping.json').read_text(encoding='utf-8'))['native_run_name']+'T01'
              if saved.get('prefix_read')=='DEFERRED_CANCELLED_PREFIX' else 'connector_history.json')
    artifact=file_pin(Path(output),Path(output)/relative)
    return _descriptors(saved,settings,h,artifact)


def deferred_catalog(saved,output,settings):
    """Inspect only an actually written TH header after cancellation cleanup.

    The active cancellation token is never cleared. No sample loop or process
    starts here; explicit later selection uses the ordinary failed-prefix read.
    """
    if saved.get('execution_status')!='CANCELLED' or saved.get('prefix_read')!='DEFERRED_CANCELLED_PREFIX':
        raise ValueError('원 취소 기록에 연결된 지연 읽기가 아닙니다.')
    from .impact_bulk_history import Records,_layout,_titles
    root=Path(output);mapping=json.loads((root/'connector_mapping.json').read_text(encoding='utf-8'))
    name=mapping['native_run_name']
    if name not in ('connector','impact'):raise ValueError('원 native 이름이 다릅니다.')
    artifact=file_pin(root,root/('native/'+name+'T01'))
    if artifact not in saved['artifacts']:raise ValueError('보존한 취소 기록과 원 TH가 다릅니다.')
    title=file_pin(root,root/('native/'+name+'T01_TITLES'))
    if title not in saved['artifacts']:raise ValueError('보존한 원 TITLES가 다릅니다.')
    with (root/artifact['relative']).open('rb') as stream:layout=_layout(Records(stream))
    factors=layout['unit_factors']
    if factors is not None and any(not math.isclose(a,b,rel_tol=2**-23,abs_tol=0) for a,b in zip(factors,(1000.,.001,1.))):
        raise ValueError('원 TH header의 단위가 다릅니다.')
    _titles(root/title['relative'],layout['groups'])
    groups=[g for g in layout['groups'] if g['id']==mapping['th_group']]
    if len(groups)!=1 or [r['id'] for r in groups[0]['members']]!=[mapping['spring_element']] or set(groups[0].get('tokens',[]))!=set(TOKENS):
        raise ValueError('실제로 쓰인 TH 그룹·요소·채널이 다릅니다.')
    verify_pin(root,artifact);verify_pin(root,title)
    h={'model_sha256':canonical_hash(model_from_settings(settings)),'native_group':groups[0]}
    return _descriptors(saved,settings,h,artifact)


def _descriptors(saved,settings,h,artifact):
    result={}
    for token in TOKENS:
        key='connector.'+token
        result[key]={'kind':'series','unit':units(token),'component':token,
            'location':settings['connector']['label']+' / 실제 대상 A–B','reduction':'none',
            'quantity':('native generalized internal work (includes viscous work)' if token=='IE' else
                        'native total connector length' if token=='LENGTH' else
                        'native local generalized force '+token if token in ('FX','FY','FZ') else
                        'native local generalized moment '+token if token in ('MX','MY','MZ') else
                        'native beam deformation '+token if token in ('LX','LY','LZ') else
                        'native relative rotation '+token if token in ('RX','RY','RZ') else 'native OFF flag (uninterpreted)'),
            'axes':[{'name':'time','unit':'s','semantics':'ACTUAL_NATIVE_TIME'}],
            'coordinate_frame':'NATIVE_CURRENT_CONNECTOR_LOCAL','source':{
                'backend':BACKEND,'artifact':artifact['relative'],'sha256':artifact['sha256'],
                'model_revision':h['model_sha256'],'native_origin':'TYPE13_TH_SPRING',
                'value_origin':'NATIVE','manifest_sha256':canonical_hash(saved['artifacts']),
                'sha256_kind':'ARTIFACT_SHA256'},
            'model_conditions':deepcopy(settings),'qualification':'UNKNOWN',
            'original_execution_status':saved['execution_status'],
            'read_status':'EXPLICIT_READ_REQUIRED' if saved.get('prefix_read')=='DEFERRED_CANCELLED_PREFIX' else 'RETAINED_PREFIX',
            'native_element_id':h['native_group']['members'][0]['id'],
            'semantics':{'LX':'L-L0','LY':'native accumulated beam shear; not raw global delta Uy',
                         'LZ':'native accumulated beam shear; not raw global delta Uz',
                         'RX':'integrated relative angular velocity in native midpoint basis',
                         'MY':'generalized moment; excludes end shear lever-arm reaction',
                         'MZ':'generalized moment; excludes end shear lever-arm reaction'}.get(token,'pinned native TYPE13 channel')}
    return result


def read(outcome,output,selector,*,start=None,stop=None):
    saved,settings,h=context(outcome,output)
    if selector not in catalog(outcome,output): raise ValueError('실제 연결요소 응답을 선택하세요.')
    token=selector.split('.',1)[1]
    start=0 if start is None else start;stop=len(h['time_s']) if stop is None else stop
    if type(start) is not int or type(stop) is not int or not 0<=start<=stop<=len(h['time_s']):
        raise ValueError('실제 이력의 유효한 반열린 표본 구간을 선택하세요.')
    indices=list(range(start,stop))
    if not indices: raise ValueError('선택한 실제 시간 구간에 출력 표본이 없습니다.')
    meta=catalog(outcome,output)[selector]
    return {**meta,'source':{**meta['source'],'selector':selector,'sample_slice':[start,stop]},
            'value':[h['values'][token][i] for i in indices],
            'axes':[{'name':'time','unit':'s','values':[h['time_s'][i] for i in indices]}],
            'valid_mask':[h['mask'][token][i] for i in indices],
            'mask':[h['mask'][token][i] for i in indices],
            'source_rows':[h['source_rows'][i] for i in indices],
            'source_excluded':deepcopy(h['excluded']),'status':'UNKNOWN' if not all(h['mask'][token][i] for i in indices) else 'AVAILABLE'}
