"""LAW117 envelope and opposing-bulk closure controls; no cyclic material solver.

The retained 2025 deck uses the fork's Isym=0/criterion=1/evolution=1 defaults.
It is NOT silently upgraded to the incompatible 2612 additional-card format.
Delayed TYPE24 is a declared clock gate, not automatic deletion-triggered contact.
"""
from copy import deepcopy
import math
from .impact_bulk import number
from .impact_bulk_deck import cards, replace_blocks, real
from .impact_damage import geometry, sub, dot, cross, length


def default_control(material):
    return {'material':material,'compression':'INTACT_COMPRESSION_ISYM0',
            'reclosure':'COHESIVE_ONLY','contact_index':None,'contact_start_s':None}


def _face_nodes(model,name):
    from .adapters.impact_admission import _surface_faces
    return [set(face) for face in _surface_faces(model,name)]


def validate(model,settings):
    rows=settings.get('interface_controls',[])
    if not isinstance(rows,list) or len(rows)>64:
        raise ValueError('계면 압축/재접촉 조건 목록을 확인하세요')
    used=set(); contacts=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'material','compression','reclosure','contact_index','contact_start_s'}:
            raise ValueError('계면 재료·압축 정책·재접촉 정책·접촉쌍·활성 시각을 명시하세요')
        material=row['material']
        eids=[e for e,m in model['assignment'].items() if m==material]
        if material in used or not eids or any(model['elements'][e]['type']!='COH3D8' for e in eids):
            raise ValueError('명시 LAW117 응집 재료 하나당 재접촉 조건 하나를 선택하세요')
        used.add(material)
        if row['compression']!='INTACT_COMPRESSION_ISYM0':
            raise ValueError('현재 2025 deck은 Isym0 압축을 보존합니다. 2612 Isym1 추가 필드를 몰래 적용하지 않습니다')
        matching=set()
        for index,pair in enumerate(settings.get('contacts',[])):
            a,b=_face_nodes(model,pair['a']),_face_nodes(model,pair['b'])
            for eid in eids:
                geo=geometry(model,eid);lower=set(geo['lower_nodes']);upper=set(geo['upper_nodes'])
                if lower in a and upper in b or lower in b and upper in a:
                    matching.add(index)
        if row['reclosure']=='COHESIVE_ONLY':
            if row['contact_index'] is not None or row['contact_start_s'] is not None or matching:
                raise ValueError('응집 압축만 선택한 경우 별도 접촉 조건은 비워 두세요')
            continue
        if row['reclosure']!='DELAYED_TYPE24_REQUIRE_DELETION':
            raise ValueError('재접촉은 응집 압축만 또는 명시 지연 TYPE24입니다')
        index=row['contact_index']; start=number(row['contact_start_s'],'접촉 활성 시각 [s]',positive=True)
        if type(index) is not int or not 0<=index<len(settings['contacts']) or index in contacts:
            raise ValueError('중복 없는 실제 TYPE24 접촉쌍을 선택하세요')
        if matching!={index}:
            raise ValueError('같은 대응면의 중복/별칭 TYPE24 또는 잘못된 접촉쌍을 확인하세요')
        contacts.add(index)
        if start>=settings['time']['end_s']:
            raise ValueError('접촉 활성은 종료 시각보다 앞이어야 합니다')
        pair=settings['contacts'][index]
        faces_a,faces_b=_face_nodes(model,pair['a']),_face_nodes(model,pair['b'])
        for eid in eids:
            geo=geometry(model,eid); lower=set(geo['lower_nodes']);upper=set(geo['upper_nodes'])
            if not ((lower in faces_a and upper in faces_b) or (upper in faces_a and lower in faces_b)):
                raise ValueError('재접촉 면은 원 응집 요소의 아래/위 절점에 정확히 대응해야 합니다')
            for face in (lower,upper):
                neighbors=[e for e,cell in model['elements'].items() if cell['type']!='COH3D8' and face<=set(cell['nodes'])]
                if len(neighbors)!=1:
                    raise ValueError('각 재접촉 면에 정확한 벌크 이웃 하나가 필요합니다')
        # Never allow a second simultaneous pair on the same faces to bypass the clock gate.
        for j,other in enumerate(settings['contacts']):
            if j!=index and {other['a'],other['b']}=={pair['a'],pair['b']}:
                raise ValueError('같은 계면에 중복 penalty 접촉을 적용하지 않습니다')


def apply(text,model,settings,cohesive):
    validate(model,settings); blocks=cards(text); replacements={}; controls=[]
    for row in settings.get('interface_controls',[]):
        entry=deepcopy(row);entry['elements']=[int(e) for e,v in cohesive['elements'].items() if v['material']==row['material']]
        entry.update(native_isym=0,native_format='2025 retained fallback',
                     envelope='irreversible maximum history; not cyclic fatigue')
        if row['reclosure']=='DELAYED_TYPE24_REQUIRE_DELETION':
            title='IMPACT'+str(row['contact_index']+1)
            found=[(k,r) for k,r in blocks.items() if k.startswith('/INTER/TYPE24/') and r[0].strip().upper()==title]
            if len(found)!=1:
                raise ValueError('정확한 native TYPE24 재접촉쌍이 없습니다')
            key,rows=found[0]
            if len(rows)!=7 or len(rows[4])<80:
                raise ValueError('TYPE24 원 카드의 시간 필드를 확인할 수 없습니다')
            # Original A postflight requires zero start/stop. Only Tstart is changed.
            if float(rows[4][40:60].strip() or '0')!=0 or float(rows[4][60:80].strip() or '0')!=0:
                raise ValueError('이미 시간 제어된 TYPE24를 덮지 않습니다')
            changed=deepcopy(rows)
            changed[4]=changed[4][:40]+real(row['contact_start_s'])+changed[4][60:]
            replacements[key]=key+'\n'+'\n'.join(changed)+'\n'
            entry.update(native_contact_id=int(key.rsplit('/',1)[1]),
                         required_postflight='cohesive deletion must be observed strictly before activation',
                         gate='explicit native Tstart, not event-driven deletion')
        controls.append(entry)
    effective=replace_blocks(text,replacements) if replacements else text
    after=cards(effective)
    return effective,{'controls':controls,'cards':{k:after[k] for k in replacements},
        'partial_loop':'LAW117 irreversible unloading/reloading with intact compression',
        'post_deletion':'opposing live bulk faces; no resurrection of cohesive traction',
        'native_loop_acceptance':'NOT_RUN','automatic_event_gate':'NOT_IMPLEMENTED'}


def face_sample(raw,model,cohesive,eid,component='normal',change=False):
    """Original paired-face separation in the initial basis, even after deletion.

    The adjacent BULK cells must still be observed active. This is not a native
    contact gap, normal penalty penetration, closest-point distance, or IP state.
    """
    geo=cohesive.get('geometry',{}).get(str(eid))
    if geo is None:
        return None,'원 대응면 기하가 없습니다'
    ids=raw['POINTS']['NODE_ID']['values']; positions={int(n):p for n,p in zip(ids,raw['points'])}
    required=geo['lower_nodes']+geo['upper_nodes']
    if any(n not in positions for n in required):
        return None,'대응 벌크면 절점이 누락됐습니다'
    active={}
    for e,a in zip(raw['CELLS']['ELEMENT_ID']['values'],raw['CELLS']['EROSION_STATUS']['values']):
        active.setdefault(int(e),[]).append(a)
    for face in (set(geo['lower_nodes']),set(geo['upper_nodes'])):
        neighbors=[e for e,c in model['elements'].items() if c['type']!='COH3D8' and face<=set(c['nodes'])]
        if len(neighbors)!=1 or active.get(neighbors[0])!=[1]:
            return None,'정확한 인접 벌크 요소의 활성 상태가 확인되지 않았습니다'
    tangent=sub(model['nodes'][geo['lower_nodes'][1]],model['nodes'][geo['lower_nodes'][0]])
    tangent=[v/length(tangent) for v in tangent]
    direction=geo['normal'] if component=='normal' else tangent if component=='tangent1' else cross(geo['normal'],tangent)
    values=[]
    for a,b in zip(geo['lower_nodes'],geo['upper_nodes']):
        delta=sub(positions[b],positions[a])
        if change:
            delta=sub(delta,sub(model['nodes'][b],model['nodes'][a]))
        values.append(dot(delta,direction))
    if not all(math.isfinite(v) for v in values):
        return None,'대응면 변위가 비유한 값입니다'
    return sum(values)/len(values),''


def audit_controls(frames,controls):
    """A sampled audit is not proof of the unobserved interval before Tstart."""
    findings=[]
    for control in controls.get('controls',[]):
        if control['reclosure']!='DELAYED_TYPE24_REQUIRE_DELETION':
            continue
        start=control['contact_start_s']; results=[]
        for eid in control['elements']:
            samples=[]
            for _,raw in frames:
                match=[v for e,v in zip(raw['CELLS']['ELEMENT_ID']['values'],raw['CELLS']['EROSION_STATUS']['values']) if int(e)==eid]
                samples.append((raw['time'],match[0] if len(match)==1 else None))
            before=[(t,v) for t,v in samples if t<start]
            after=[(t,v) for t,v in samples if t>=start]
            inactive=next((t for t,v in before if v==0),None)
            overlap=[t for t,v in after if v==1]
            status='VIOLATED' if overlap else 'OBSERVED_COMPATIBLE' if inactive is not None else 'UNKNOWN'
            results.append({'element_id':eid,'status':status,'first_observed_deleted_before_gate_s':inactive,
                            'active_at_or_after_gate_samples_s':overlap})
        findings.append({'contact_index':control['contact_index'],'contact_start_s':start,'elements':results,
                         'assessment':'VIOLATED' if any(r['status']=='VIOLATED' for r in results) else 'UNKNOWN',
                         'continuous_no_double_counting':'UNKNOWN_BETWEEN_SAMPLES',
                         'normal_reaction_channel':'NOT_INFERRED_FROM_OPENING'})
    return findings
