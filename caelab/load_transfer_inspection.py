"""Saved TR-F inspection only: original fields/receipt, no H or solver rerun."""
from copy import deepcopy
from .storage import load_json,canonical_hash
from .evaluation import file_hash


def inspect_mapped(wb,document_id,job_id,result,declaration,record,frozen,progress,*,start,count,folder,read_stage):
    from .workbench import contained
    path=contained(folder,record['receipt_path'])
    if not record.get('receipt_recorded') or file_hash(path)!=record['receipt_sha256']:
        raise ValueError('전달 원기록이 없거나 변경됐습니다. 원 결과는 유지됩니다.')
    receipt=load_json(path)
    if (receipt.get('capture_sha256')!=canonical_hash({k:v for k,v in receipt.items() if k!='capture_sha256'}) or
        receipt.get('mapping')!=declaration['mapping'] or receipt.get('policy')!=declaration['options'] or
        receipt.get('status')!=record['status']):raise ValueError('보존한 전달 정의·상태가 다릅니다.')
    sources=[r for r in progress['stages'] if r['stage_id']==declaration['from_stage'] and r['iteration']==record['source_iteration']]
    targets=[r for r in progress['stages'] if r['stage_id']==declaration['to_stage'] and r['iteration']==record['iteration']]
    if len(sources)!=1 or len(targets)!=1:raise ValueError('원 공급·수신 시도가 모호합니다.')
    source,target=sources[0],targets[0]
    supplied=read_stage(source['attempt_id'],{'responses':[declaration['output']]})['responses'][declaration['output']]
    if record.get('source_response_sha256')!=canonical_hash(supplied):raise ValueError('원 공급 반력이 전달 당시와 다릅니다.')
    expected=next(s['source'] for s in frozen['stages'] if s['id']==declaration['from_stage'])
    for reference in receipt.get('source_refs',[]):
        if (reference['source']!=expected or reference['attempt_id']!=source['attempt_id'] or
            reference['result_sha256']!=source['result_sha256']):raise ValueError('공급 계산 참조가 다릅니다.')
    received=read_stage(target['attempt_id'],{'responses':[]}) if target['state'] in {'SUCCEEDED','FAILED','REJECTED'} else {}
    if target['state']=='SUCCEEDED' and received.get('load_binding',{}).get('receipt_sha256')!=receipt.get('numerical_receipt_sha256'):
        raise ValueError('수신 계산에 적용한 전달 원기록이 다릅니다.')
    rows_source=[{'node_id':n,'coordinates_mm':x,'R_source_N':r,'f_source_N':f}
        for n,x,r,f in zip(supplied['node_ids'],supplied['coordinates'],receipt.get('R_source_N',[]),receipt.get('f_source_N',[]))]
    selected=receipt.get('target',declaration['options']['target'])
    rows_target=[{'node_id':n,'coordinates_mm':x,'f_target_N':f}
        for n,x,f in zip(selected['node_ids'],selected['coordinates'],receipt.get('f_target_N',[]))]
    return {**result,'mapping_kind':'tri6_conservative_load','transfer':deepcopy(record),
        'declaration':deepcopy(declaration),'receipt':receipt,'source_attempt':source,'target_attempt':target,
        'source_rows':deepcopy(rows_source[start:start+count]),'target_rows':deepcopy(rows_target[start:start+count]),
        'source_total':len(rows_source),'target_total':len(rows_target),'start':start,'count':count,
        'total':max(len(rows_source),len(rows_target)),'receiver_equilibrium':deepcopy(received.get('receiver_equilibrium')),
        'source_state':source['state'],'receiver_state':target['state'],'unavailable':receipt.get('error')}
