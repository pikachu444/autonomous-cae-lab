"""Exact elastic C3D4 post-conversion connector overlay; no second converter.

Existing FE nodes, solid elements, LAW1, density and boundary cards remain byte
identical. A new CoG main collects each selected FE patch's existing mass. The
actual RP remains a secondary and carries native spring rotational DOFs.
"""
from copy import deepcopy
import math
import re
from .connector_model import ConnectorInputError,cross,sub,dot
from .connector_deck import ints,reals,TOKENS
from .storage import canonical_hash


def validate_fe(fe,draft):
    keys={'analysis_id','solver_id','settings','attachments','source_binding'}
    if not isinstance(fe,dict) or set(fe) not in (keys,keys|{'initial_motion_source'}):
        raise ConnectorInputError('fe','현재 해석의 FE 입력과 실제 부착 면을 다시 가져오세요.')
    if fe.get('initial_motion_source','existing_fe') not in ('existing_fe','endpoint_patch'):
        raise ConnectorInputError('fe.initial_motion_source','원 FE 초기운동 유지 또는 선택 영역 초기운동 지정을 명시 선택하세요.')
    from .impact_model import validate_settings,model_from_settings
    s=validate_settings(fe['settings']);m=model_from_settings(s)
    if s['source']['format']!='INP' or s['time']['mass_scaling'] or s.get('cohesive') or any(e['type']!='C3D4' for e in m['elements'].values()) or any(set(v)-{'DENSITY','ELASTIC','_elastic_type'} for v in m['materials'].values()):
        raise ConnectorInputError('fe','첫 FE 연결은 원 밀도·LAW1을 유지하는 전체 탄성 C3D4 메시와 질량 스케일링 없는 입력을 사용합니다.')
    if not isinstance(fe['attachments'],list) or len(fe['attachments'])!=2 or not fe['source_binding']:
        raise ConnectorInputError('fe','두 원 FE 영역의 실제 절점 대응이 필요합니다.')
    fixed=set()
    for b in m['blocks']:
        if b['card']=='BOUNDARY':
            for _,line in b['rows']:
                target=line.split(',')[0].strip().upper();fixed.update([int(target)] if target.isdigit() else m['nsets'][target])
    used=set()
    for i,a in enumerate(fe['attachments']):
        if not isinstance(a,dict) or set(a)!={'native_node_ids','selection_sha256','body_id','mesh_id'}:
            raise ConnectorInputError('fe.attachments','원 CAD 면·메시 대응을 다시 가져오세요.')
        ids=a['native_node_ids']
        if not isinstance(ids,list) or len(ids)<3 or any(type(n) is not int or n not in m['nodes'] for n in ids) or len(ids)!=len(set(ids)) or used.intersection(ids):
            raise ConnectorInputError('fe.attachments','서로 겹치지 않는 실제 FE 절점 세 개 이상의 영역이 필요합니다.')
        if a['selection_sha256']!=canonical_hash(draft['endpoints'][i]['selection']):
            raise ConnectorInputError('fe.attachments','부착 대상을 바꿨습니다. FE 입력과 영역을 다시 가져오세요.')
        if fixed.intersection(ids): raise ConnectorInputError('fe.attachments','선택한 FE 영역이 기존 구속과 겹칩니다. 원 구속을 유지하며 부착 면을 다시 선택하세요.')
        for motion in s['motions']:
            moving=m['nsets'][motion['node_set']]
            if set(ids)&moving and not set(ids)<=moving:
                raise ConnectorInputError('fe.attachments','한 부착 영역의 초기 운동이 일부 절점에만 지정됐습니다. 원 FE에서 일관된 영역 운동을 지정하세요.')
        points=[m['nodes'][n] for n in ids];base=points[0]
        if not any(dot(cross(sub(p,base),sub(q,base)),cross(sub(p,base),sub(q,base)))>0 for p in points[1:] for q in points[1:]):
            raise ConnectorInputError('fe.attachments','회전 전달에는 비공선인 실제 FE 영역이 필요합니다.')
        if any(set(e['nodes'])<=set(ids) for e in m['elements'].values()):
            raise ConnectorInputError('fe.attachments','한 사면체 전체를 강체 영역에 포함할 수 없습니다. 원 변형체 요소를 유지하는 표면 영역을 선택하세요.')
        used.update(ids)
    return m


def initial_fields(fe,endpoints,fe_model,*,initial=None):
    """Preserve the original rigid field, or add the user's explicit patch field."""
    if initial is None:
        from .impact_model import render
        _,initial=render(fe['settings'])
    fields=[]
    for i,a in enumerate(fe['attachments']):
        velocity=[0.,0.,0.];omega=[0.,0.,0.]
        for raw,receipt in zip(fe['settings']['motions'],initial['motions']):
            if set(a['native_node_ids'])<=fe_model['nsets'][raw['node_set']]:
                omega=receipt['omega_rad_s'];center=receipt['rotation_center_after_mm']
                rotational=cross(omega,sub(endpoints[i]['reference_mm'],center))
                velocity=[x+y for x,y in zip(receipt['velocity_at_center_mm_s'],rotational)]
        if fe.get('initial_motion_source','existing_fe')=='endpoint_patch':
            requested=endpoints[i];v=requested['velocity_mm_s'];w=requested['omega_rad_s']
            if any(velocity+omega) and (velocity!=v or omega!=w):
                raise ConnectorInputError(f'endpoints.{i}','원 FE의 초기운동과 지정한 영역 초기운동이 다릅니다. 원 설정을 유지하거나 충돌을 원 모델에서 수정하세요.')
            velocity,omega=v,w
        fields.append((velocity,omega))
    return fields


def _blocks(text):
    result=[]
    for line in text.splitlines(keepends=True):
        if line.startswith('/'):
            result.append([line.strip(),line])
        elif result:result[-1][1]+=line
    return result


def append(starter,m,fe_model,*,initial=None):
    """Append only new IDs before /END; return an exact source/ID ledger."""
    from .connector_deck import starter as rigid_starter
    blocks=_blocks(starter)
    if not blocks or blocks[-1][0]!='/END' or sum(k=='/END' for k,_ in blocks)!=1:
        raise ValueError('완료된 기존 native Starter 입력이 필요합니다.')
    if any(k.startswith(('/RBODY/','/SPRING/','/SKEW/')) for k,_ in blocks):
        raise ValueError('기존 rigid/connector membership은 이번 부착 경로에서 중복 해석하지 않습니다.')
    begin=next((text for key,text in blocks if key=='/BEGIN'),None)
    if begin is None or int(begin.splitlines()[2][:10])!=2025:
        raise ValueError('기존 고정 INP 변환기의 2025 입력 형식이 필요합니다.')
    # Validate post-converter mesh by existing native identity checker first.
    from .adapters.impact import converted_mesh
    # Caller invokes converted_mesh on the exact physical file; this function
    # only adds IDs above the actual existing namespaces.
    node_max=max(fe_model['nodes']);elem_max=max(fe_model['elements'])
    ids=[int(k.rsplit('/',1)[1]) for k,_ in blocks if re.fullmatch(r'/[^\s]+/[1-9][0-9]*',k)]
    offset=max(ids+[0])+1;spring=elem_max+1;prop=offset;part=offset;skew=offset
    rp=[node_max+1,node_max+2];main=[node_max+3,node_max+4]
    # Reuse the exact tested TYPE13 template (only property/skew IDs change).
    raw=_blocks(rigid_starter(m));properties=[text for key,text in raw if key.startswith('/PROP/TYPE13/')]
    property_text=properties[0].replace('/PROP/TYPE13/1','/PROP/TYPE13/'+str(prop),1)
    plines=property_text.splitlines();common=plines[2];plines[2]=common[:40]+ints(skew)+common[50:]
    extra=['/NODE',*[ints(rp[i])+reals(*e['reference_mm']) for i,e in enumerate(m['endpoints'])],
           *[ints(main[i])+reals(*e['reference_mm']) for i,e in enumerate(m['endpoints'])],
           f'/SKEW/FIX/{skew}','EXPLICIT_CONNECTOR_LOCAL_Y_Z',reals(0,0,0),reals(*m['axes']['y']),reals(*m['axes']['z']),
           '\n'.join(plines),f'/PART/{part}','TYPE13_FE_CONNECTOR',ints(prop,0,0),f'/SPRING/{part}',
           ints(spring,*rp,0,0,0,0)+' '*20+ints(0)]
    mapping=[]
    for i,a in enumerate(m['fe']['attachments']):
        group=offset+i;body=offset+i
        members=[*a['native_node_ids'],rp[i]]
        extra.extend([f'/GRNOD/NODE/{group}',f'EXPLICIT_SELECTED_FE_PATCH_{i+1}'])
        extra.extend(ints(*members[j:j+10]) for j in range(0,len(members),10))
        extra.extend([f'/RBODY/{body}',f'FE_PATCH_NATIVE_COG_{i+1}',
            ints(main[i],0,0,3)+reals(0)+ints(group,0,2,0),reals(0,0,0),reals(0,0,0),ints(0,0,0)])
        # A new main initialized at zero would overwrite every secondary's
        # existing velocity during native RBODY initialization. Project the
        # already-declared compatible original field onto this new main only.
        velocity,omega=initial_fields(m['fe'],m['endpoints'],fe_model,initial=initial)[i]
        main_group=offset+2+i
        extra.extend([f'/GRNOD/NODE/{main_group}','NEW_COG_MAIN_INITIAL_FIELD',ints(main[i])])
        from .connector_deck import motion_cards
        cards,motion=motion_cards(m['endpoints'][i]['reference_mm'],velocity,omega,m['axes'],
                                  group=main_group,ident=offset+i,frame=offset+100+i,version=2025)
        extra.extend(cards)
        mapping.append({'body':body,'native_cog_main':main[i],'connector_reference':rp[i],
                        'secondary_nodes':members,'additional_mass':0,'additional_inertia':[0]*6,
                        'native_internal_zero_mass_floor_Mg':1e-20,
                        'ICoG':2,'Ispher':3,'source':deepcopy(a)})
        mapping[-1]['initial_field_projection']={**motion,'source':m['fe'].get('initial_motion_source','existing_fe'),
            'target':'new main only; original FE INIVEL rows preserved',
            'native_cog_move_correction':'inirby angular cross deltaX correction'}
    th=max([int(k.rsplit('/',1)[1]) for k,_ in blocks if re.fullmatch(r'/TH/[^/]+/[1-9][0-9]*',k)]+[0])+1
    extra.extend([f'/TH/SPRING/{th}','NATIVE_CONNECTOR_FE_GENERALIZED_RESPONSE'])
    extra.extend(''.join(f'{s:<10}' for s in TOKENS[j:j+10]) for j in range(0,len(TOKENS),10))
    extra.append(ints(spring)+' '*10+'EXACT_FE_CONNECTOR')
    prefix=starter[:starter.rfind('/END')]
    effective=prefix+'\n'.join(extra)+'\n/END\n'
    if not effective.startswith(prefix): raise ValueError('원 FE native 카드가 변경됐습니다.')
    return effective,{'original_starter_sha256':__import__('hashlib').sha256(starter.encode('ascii')).hexdigest(),
        'original_cards_preserved':True,'original_nodes':len(fe_model['nodes']),
        'spring_element':spring,'spring_property':prop,'spring_part':part,'th_group':th,
        'mass_formulation':{'ILENG':0,'IMAS_DS':0},
        'attachments':mapping,'mass_policy':'existing FE nodal mass once; no manual endpoint mass added',
        'scope':'elastic C3D4; selected patches rigid, remaining FE stiffness/mass unchanged'}
