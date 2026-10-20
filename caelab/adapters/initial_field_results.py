"""Exact C3D10 IP stress tables at actual accepted FRD states; no recovery."""
from copy import deepcopy
import re,math
from pathlib import Path
from .shell_results import DAT_HEADER,DAT_NAMES
from .fixture_field import _number,_identifier,_printed_close
from ..dynamic_native_stream import frame_catalog
from ..storage import save_json
from ..initial_field_conditions import effective


def read(path,model,frames,*,require_definition=True):
    if require_definition and effective(model) is None:return []
    catalog=list(frame_catalog(frames));expected={(r['element_id'],p) for r in model['elements'] for p in range(1,5)}
    lines=Path(path).read_text(encoding='ascii').splitlines();tables={};i=0
    while i<len(lines):
        header=DAT_HEADER.fullmatch(lines[i]);i+=1
        if header is None or header[3].upper()!='INITIAL_BODY':continue
        name,labels=DAT_NAMES[header[1].lower()]
        if name not in ('S','COORD') or tuple(t.strip().lower() for t in header[2].split(','))!=labels:
            raise ValueError('초기장 적분점 출력의 물리량·성분 순서가 다릅니다.')
        matching=[f for f in catalog if _printed_close(header[4],f['static']['load_parameter'])]
        if len(matching)!=1:raise ValueError('초기장 DAT 시각을 실제 수렴 단계에 유일하게 대응할 수 없습니다.')
        frame=matching[0];key=(frame['static']['step'],frame['static']['increment'],name)
        if key in tables:raise ValueError('같은 초기장 단계·적분점 출력이 중복됐습니다.')
        while i<len(lines) and not lines[i].strip():i+=1
        values={}
        while i<len(lines) and lines[i].strip():
            tokens=lines[i].split();i+=1
            if len(tokens)!=(8 if name=='S' else 5):raise ValueError('초기장 native 적분점 행이 손상됐습니다.')
            point=(_identifier(tokens[0]),_identifier(tokens[1]))
            if point not in expected or point in values:raise ValueError('원 요소·적분점이 다르거나 중복됐습니다.')
            values[point]={'values':[_number(v) for v in tokens[2:]],'tokens':tokens[2:],'source_line':i}
        if set(values)!=expected:raise ValueError('원 C3D10 네 적분점의 출력이 빠졌습니다. 누락값을 0으로 채우지 않습니다.')
        tables[key]=(frame,values,header[4])
    rows=[]
    for f in catalog:
        state=f['static'];key=(state['step'],state['increment'])
        if (*key,'S') not in tables or (*key,'COORD') not in tables:raise ValueError('수렴 상태의 초기장 응력·적분점 좌표가 빠졌습니다.')
        _,stress,token=tables[(*key,'S')];_,coords,_=tables[(*key,'COORD')]
        # Same four barycentric samples/order as frozen_fem._jacobian_gates;
        # retain the native per-IP identity, never match an Aster FPG5 point.
        xyz={n['node_id']:n['position_mm'] for n in model['nodes']}
        for element,point in sorted(expected):
            import numpy as np
            cell=next(r for r in model['elements'] if r['element_id']==element)
            L=np.full(4,.1381966011250105);L[point-1]=.5854101966249685
            shape=[v*(2*v-1) for v in L]+[4*L[a]*L[b] for a,b in ((0,1),(1,2),(2,0),(0,3),(1,3),(2,3))]
            wanted=np.array(shape)@np.array([xyz[n] for n in cell['node_ids']])
            if any(not _printed_close(token,float(v)) for token,v in zip(coords[(element,point)]['tokens'],wanted)):
                raise ValueError('원 C3D10 적분점 좌표·순서가 native 출력과 다릅니다.')
            rows.append({'static':deepcopy(state),'element_id':element,'point':point,
                'stress_MPa':stress[(element,point)]['values'],'position_mm':coords[(element,point)]['values'],
                'time_token':token,'raw_stress_tokens':stress[(element,point)]['tokens'],
                'source_line':stress[(element,point)]['source_line'],'frame':'FREECAD_DOCUMENT_GLOBAL',
                'component_names':['XX','YY','ZZ','XY','XZ','YZ'],'basis':'native_CCX_2.22_C3D10_IP4'})
    return rows


def augment(result,output,model,frames):
    if effective(model) is None:return
    rows=read(Path(output)/'solver/contact.dat',model,frames)
    save_json(Path(output)/'initial_fields.json',{'definition':model['initial_fields'],'rows':rows,
        'raw_source':'solver/contact.dat','first_equilibrium':'actual native accepted state; no assumed preservation'})
    result['initial_field_outputs']={'raw_ip':'initial_fields.json','source_model':'frozen_input/mesh.json',
        'initial_state_kind':model['initial_fields']['definition']['kind'],'first_equilibrium_verified':'READ_ONLY_NOT_ENGINEERING_RELEASE'}
    requested=[state['parameter'] for state in model['initial_fields']['definition']['states']]
    times=[]
    for value in requested:
        matches={r['static']['load_parameter'] for r in rows if _printed_close(r['time_token'],value)}
        if len(matches)!=1:raise ValueError('요청한 초기장 상태 시각을 native 출력에 유일하게 대응할 수 없습니다.')
        times.append(next(iter(matches)))
    for prefix,time in (('first_equilibrium',times[0]),('subsequent',times[-1])):
        selected=[r for r in rows if r['static']['load_parameter']==time]
        for axis,name in enumerate(('XX','YY','ZZ','XY','XZ','YZ')):
            result.setdefault('responses',{})[prefix+'_IP_stress_'+name]={'kind':'field','unit':'MPa','value':[r['stress_MPa'][axis] for r in selected],
                'component':name,'location':'native_C3D10_IP4','reduction':'none','metadata':{'element_ids':[r['element_id'] for r in selected],
                    'point_ids':[r['point'] for r in selected],'static':deepcopy(selected[0]['static']),'raw_rows':'initial_fields.json',
                    'frame':'FREECAD_DOCUMENT_GLOBAL','measure':'small_strain_Cauchy_stress_at_native_integration_point'}}
        frame=next(f for f in frame_catalog(frames) if f['static']['load_parameter']==time)
        ids=sorted(r['node_id'] for r in model['nodes'])
        for field,key,unit,measure in (('DISP','displacement','mm','native_displacement'),('FORC','nodal_force','N','native_nodal_force_RF_semantics')):
            if field not in frame['fields']:raise ValueError('첫 평형·후속 상태의 원 절점 응답이 빠졌습니다.')
            result['responses'][prefix+'_'+key]={'kind':'field','unit':unit,'value':[frame['fields'][field][n] for n in ids],
                'component':'VECTOR','location':'native_C3D10_nodes','reduction':'none','metadata':{'node_ids':ids,
                    'static':deepcopy(frame['static']),'measure':measure,'frame':'FREECAD_DOCUMENT_GLOBAL'}}
