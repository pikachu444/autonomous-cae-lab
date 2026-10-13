"""Read exact saved producer/bound receiver values; never bind or evaluate on read."""
from copy import deepcopy
import math
from .storage import canonical_hash, revision_read_scope
from .research_workflows import result_folder, evaluation_progress, evaluation_stage_result


def _one(rows,predicate,message):
    matches=[row for row in rows if predicate(row)]
    if len(matches)!=1: raise ValueError(message)
    return matches[0]


@revision_read_scope()
def inspect_transfer(wb,document_id,job_id,transfer_id=None,iteration=None,*,start=0,count=256):
    if wb._document_owner(document_id) is not wb.evaluation_documents:
        raise ValueError('연성 계산을 선택하세요.')
    if type(start) is not int or start<0 or type(count) is not int or not 1<=count<=1024:
        raise ValueError('행 범위는 시작 위치와 1~1024개입니다.')
    _,run=result_folder(wb,document_id,job_id)
    if canonical_hash(run['draft'])!=run['input_sha256']:
        raise ValueError('선택 실행의 보존 정의가 다릅니다.')
    frozen=run['draft'];progress=evaluation_progress(wb,document_id,job_id)
    declarations=frozen.get('transfers',[])
    records=progress.get('transfers',[])
    names={row['id']:row.get('name',row['id']) for row in frozen.get('stages',[])}
    result={'document_id':document_id,'job_id':job_id,
            'transfers':[dict(row,source_name=names.get(row['from_stage'],row['from_stage']),
                              target_name=names.get(row['to_stage'],row['to_stage'])) for row in records],
            'stages':progress.get('stages',[]),'iterations':progress.get('iterations',[]),
            'diagnostics':progress.get('diagnostics',{}),'job_state':progress.get('job_state'),
            'reuse_policy':'성공한 동일 입력의 순서상 앞 단계만 새 실행에서 명시적으로 재사용합니다. 반복 중간 상태 재개는 지원하지 않습니다.'}
    if transfer_id is None:
        return result
    receipt=_one(records,lambda row:row['id']==transfer_id and row['iteration']==iteration,'정확한 전달과 반복을 선택하세요.')
    declaration=_one(declarations,lambda row:row['id']==transfer_id,'보존 정의에 없는 전달입니다.')
    for key in ('from_stage','to_stage','input','mapping'):
        if receipt[key]!=declaration[key]: raise ValueError('전달 기록과 보존 정의가 다릅니다.')
    if declaration['mapping']!='exact_same_mesh':
        raise ValueError('현재 조사 화면은 선언된 동일 메시 전달만 지원합니다.')
    stages=progress.get('stages',[])
    source=_one(stages,lambda row:row['stage_id']==receipt['from_stage'] and row['iteration']==receipt['source_iteration'],'공급 단계가 모호합니다.')
    target=_one(stages,lambda row:row['stage_id']==receipt['to_stage'] and row['iteration']==iteration,'수신 단계가 모호합니다.')
    read=evaluation_stage_result(wb,document_id,job_id,source['attempt_id'],{'responses':[declaration['output']]})
    supplied=read['responses'][declaration['output']]
    if canonical_hash(supplied)!=receipt['source_response_sha256']:
        raise ValueError('공급 장이 보존된 전달 기록과 다릅니다.')
    # Absence is shown only for an actually incomplete receiver attempt. A
    # corrupted completed result must raise, not become "unavailable".
    received=None;settings={};unavailable=None
    try:
        downstream=evaluation_stage_result(wb,document_id,job_id,target['attempt_id'],
                                          {'responses':[],'include_settings':True})
        settings=downstream.get('settings',{})
        received=settings.get(declaration['input'])
    except ValueError as error:
        if str(error)!='This stage has no completed retained result; inspect progress/failure': raise
        unavailable=str(target.get('error') or '수신 입력 저장 없음: 단계 실행 전 실패 또는 취소')
    if received is None and unavailable is None: unavailable='보존 수신 입력에 선택한 port 값이 없습니다.'
    metadata=('unit','quantity','component','association','frame','measure','coordinate_units','coordinate_frame',
              'mesh_sha256','node_ids','cell_node_ids','coordinates','time','time_units','time_origin')
    differences=[] if received is None else [key for key in metadata if supplied.get(key)!=received.get(key)]
    values=supplied.get('value');ids=supplied.get('node_ids');coords=supplied.get('coordinates')
    if (not isinstance(values,list) or not isinstance(ids,list) or not isinstance(coords,list)
            or len(ids)!=len(values) or len(coords)!=len(values) or len(set(ids))!=len(ids)):
        raise ValueError('보존된 절점 장의 행/좌표가 일치하지 않습니다.')
    other=received.get('value') if isinstance(received,dict) else None
    if other is not None and (not isinstance(other,list) or len(other)!=len(values)):
        differences.append('value_shape');other=None
    aligned=not differences
    rows=[]
    for i in range(start,min(start+count,len(values))):
        a=values[i];b=other[i] if other is not None and aligned else None
        valid_a=type(a) in (int,float) and math.isfinite(a)
        valid_b=type(b) in (int,float) and math.isfinite(b)
        rows.append({'row':i,'node':ids[i],'coordinates':deepcopy(coords[i]),'supplied':a,
                     'received':b,'difference':b-a if valid_a and valid_b else None,
                     'required':True,'available':valid_a and valid_b})
    result.update(transfer=deepcopy(receipt),declaration=deepcopy(declaration),source_attempt=source,target_attempt=target,
                  metadata={key:deepcopy(supplied.get(key)) for key in metadata if key not in ('node_ids','coordinates','cell_node_ids')},
                  rows=rows,start=start,count=len(rows),total=len(values),metadata_differences=differences,
                  coverage_policy='ALL_P1_NODES_REQUIRED' if target['backend'] in (
                      'thermal.fenicsx.rectangle','structural.fenicsx.thermoelastic_rectangle') else 'DECLARED_COMPLETE_FIELD',
                  native_mask=supplied.get('valid_mask'),unavailable=unavailable,
                  reference_temperature=deepcopy(settings.get('reference_temperature')),
                  exact_values_match=received is not None and not differences and supplied.get('value')==received.get('value'))
    return result
