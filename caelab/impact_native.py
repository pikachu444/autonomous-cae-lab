"""Typed admission of a deliberately bounded native RAD solid deck.

This is NOT an INP serializer or a second solver. It projects declared native
cards into the existing impact model ONLY for validation/result identity. Direct
export uses impact_rad_source.export_tree, keeping every untouched byte.
"""
from copy import deepcopy
from pathlib import Path
import math
import re

from .impact_source import SourceError, digest
from .impact_assembly import origin
from .impact_rad_source import inspect_graphs, export_tree

STARTER_FAMILIES = (
    r'/MAT/ELAST/[1-9][0-9]*', r'/PART/[1-9][0-9]*', r'/PROP/SOLID/[1-9][0-9]*',
    r'/TETRA4/[1-9][0-9]*', r'/GRNOD/(?:NODE|PART|SURF|GRBRIC|GRNOD)/[1-9][0-9]*',
    r'/GRBRIC/BRIC/[1-9][0-9]*', r'/SURF/SEG/[1-9][0-9]*', r'/BCS/[1-9][0-9]*',
    r'/INIVEL/TRA/[1-9][0-9]*', r'/INTER/TYPE24/[1-9][0-9]*',
    r'/FUNCT/[1-9][0-9]*', r'/GRAV/[1-9][0-9]*',
)
ENGINE_FIXED = {'/PRINT/-100/50','/PARITH/OFF','/DT','/DT/NODA/CST/0','/DT1/BRICK/STOP','/ANIM/DT',
                '/ANIM/VECT/DISP','/ANIM/VECT/VEL','/ANIM/VECT/ACC','/ANIM/VECT/CONT',
                '/ANIM/BRICK/TENS/STRESS','/ANIM/BRICK/DAMA','/ANIM/ELEM/DAMG',
                '/TH/TITLE','/TFILE/4','/STOP'}
FRAME = 'MODEL_GLOBAL'


def _error(card, message):
    where = card['origin']
    error = SourceError(message, where['file'], where['line'])
    error.occurrence = where['occurrence']
    error.impact = {'source':where, 'card':card.get('key'), 'role':card.get('role'),
                    'affected':'NATIVE_DECK_EXECUTION', 'execution':'BLOCKED'}
    raise error


def cards(graph, role):
    result=[]
    pending_blank=None
    for line_no, raw in enumerate(graph['text'].splitlines(),1):
        if not raw.strip():
            if result:pending_blank=origin(graph['line_map'],line_no)
            continue
        if raw.startswith('#'):continue
        where=origin(graph['line_map'],line_no)
        if raw.startswith('/'):
            pending_blank=None # a blank separator after the last data row is not an option row
            result.append({'key':raw.rstrip(),'origin':where,'rows':[],'role':role})
        elif raw.lstrip().startswith(('/', '#')):
            _error({'origin':where,'role':role},'native 카드/주석은 열 1에서 시작해야 합니다')
        elif not result:
            _error({'origin':where,'role':role},'native data 앞에 카드가 없습니다')
        else:
            if pending_blank is not None:
                _error({'origin':pending_blank,'role':role,'key':result[-1]['key']},
                       '카드 data 중간의 빈 행은 의미가 불명확합니다. 첫 지원은 명시 필드 행을 요구합니다')
            result[-1]['rows'].append({'text':raw,'origin':where})
    return result


def _real(token, card, *, blank=False):
    if not token.strip():
        if blank:return 0.
        _error(card,'명시 수치 필드가 비어 있습니다')
    try:value=float(token)
    except (ValueError,TypeError):_error(card,'유효한 native 실수 필드가 아닙니다')
    if not math.isfinite(value):_error(card,'비유한 native 수치입니다')
    return value


def _integer(token, card, *, zero=False, blank=False):
    if not token.strip() and blank:return 0
    if not re.fullmatch(r'[0-9]+',token.strip()):_error(card,'native 정수 필드를 확인하세요')
    value=int(token)
    if not (0 if zero else 1)<=value<=2147483647:_error(card,'native ID/정수 범위를 벗어났습니다')
    return value


def _rows(card, count=None, minimum=None):
    rows=card['rows']
    if count is not None and len(rows)!=count or minimum is not None and len(rows)<minimum:
        _error(card,'native 카드의 허용 data 행 수와 다릅니다')
    return [r['text'] for r in rows]


def _tail(row, width, card):
    if row[width:].strip():_error(card,'허용 field 뒤에 알 수 없는 값/옵션이 있습니다')


def _ids(rows,card):
    values=[]
    for row in rows:
        if len(row.rstrip())>100:_error(card,'ID 목록은 한 행에 최대 10개 10-column 필드입니다')
        for start in range(0,len(row.rstrip()),10):
            values.append(_integer(row[start:start+10],card))
    if not values or len(values)!=len(set(values)):_error(card,'빈/중복 native ID 목록입니다')
    return values


def _title(card):
    title=card['rows'][0]['text'].strip().upper()
    if not title or len(title)>100:_error(card,'native title은 비어 있지 않은 100자 이하 ASCII여야 합니다')
    return title


def _control_tokens(card,count):
    row=_rows(card,1)[0]
    tokens=row.split()
    if len(tokens)!=count:_error(card,'Engine control 필드 수와 다릅니다')
    return [_real(token,card) for token in tokens]


def parse_source(source):
    from .impact_model import default_settings
    from .adapters.impact_admission import validate_physics, _segment_nodes
    graphs=inspect_graphs(source)
    bundle=source['bundle']
    # Pinning input bytes never implies units. The user must explicitly declare them.
    if source.get('units')!='Mg/mm/s' or source.get('provenance',{}).get('units_declared_by_user') is not True:
        raise SourceError('native 입력 단위를 확인해 Mg/mm/s/N/MPa를 명시하세요. 다른 단위는 자동 재표기하지 않습니다')
    name=re.fullmatch(r'([A-Za-z][A-Za-z0-9_-]{0,63})_0000\.rad',bundle['starter'])
    if not name or bundle['engine']!=name[1]+'_0001.rad':
        raise SourceError('첫 native 직접 실행은 제출 root의 같은이름_0000.rad / 같은이름_0001.rad입니다')
    run_name=name[1]
    starter,engine=cards(graphs['starter'],'starter'),cards(graphs['engine'],'engine')
    table={}
    fields=[]
    from .impact_input_edits import edited_files, original_offset
    effective_files=edited_files(source)
    def field(card,row_index,field_name,start,end,kind='real',unit='1'):
        row=card['rows'][row_index];where=row['origin']
        raw=effective_files[where['file']]
        physical=raw.splitlines(keepends=True)
        line_start=sum(len(line) for line in physical[:where['line']-1])
        offset=line_start+start;stop=line_start+end
        # End of a short field is never extended into the newline/next card.
        content=physical[where['line']-1].rstrip(b'\r\n')
        if end>len(content):return
        fields.append({'id':f"{card['role']}:{card['key']}:{row_index}:{field_name}",
                       'role':card['role'],'card':card['key'],'field':field_name,'row':row_index,
                       'file':where['file'],'line':where['line'],'occurrence':where['occurrence'],
                       'start':original_offset(source,where['file'],offset),
                       'end':original_offset(source,where['file'],stop),
                       'width':end-start,'kind':kind,'unit':unit,'value':row['text'][start:end].strip()})
    def engine_field(card,field_name,index,unit):
        matches=list(re.finditer(r'\S+',card['rows'][0]['text']))
        field(card,0,field_name,matches[index].start(),matches[index].end(),'token',unit)
    for card in starter:
        key=card['key']
        if key not in ('/BEGIN','/NODE','/END') and not any(re.fullmatch(p,key) for p in STARTER_FAMILIES):
            _error(card,'실행 미지원 native 영향 카드: '+key)
        if key in table:_error(card,'native 카드/ID가 중복되었습니다')
        table[key]=card
    if not starter or starter[0]['key']!='/BEGIN' or starter[-1]['key']!='/END' or '/NODE' not in table:
        raise SourceError('native Starter의 BEGIN → 모델 → END 순서를 확인하세요')
    if not graphs['starter']['text'].startswith('#RADIOSS STARTER\n'):
        raise SourceError('native Starter 첫 행은 #RADIOSS STARTER여야 합니다')
    begin=table['/BEGIN'];rows=_rows(begin,4)
    if rows[0].strip()!=run_name:_error(begin,'BEGIN 이름과 원 Starter/Engine 파일명이 다릅니다')
    _tail(rows[1],20,begin)
    if [_integer(rows[1][:10],begin),_integer(rows[1][10:20],begin,zero=True,blank=True)]!=[2025,0]:
        _error(begin,'첫 명시 지원은 native 2025, Irun=0 Starter입니다')
    for row in rows[2:]:
        _tail(row,60,begin)
        if [row[i:i+20].strip() for i in (0,20,40)]!=['Mg','mm','s']:
            _error(begin,'원 INPUT/WORK 단위가 Mg/mm/s가 아닙니다')
    _rows(table['/END'],0)
    model={'nodes':{},'elements':{},'nsets':{},'elsets':{},'surfaces':{},'materials':{},'assignment':{},'blocks':[],
           'native_contact_titles':{},'lineage':{'schema':'impact-native-lineage-v1','nodes':{},'elements':{},
                                               'nsets':{},'elsets':{},'surfaces':{},'materials':{},'instances':{}}}
    material_ids,part_ids,properties,groups,brick_groups,surfaces={}, {}, {}, {}, {}, {}
    native_element_parts={}
    for card in starter:
        key=card['key'];rows=_rows(card)
        ident=int(key.rsplit('/',1)[1]) if key.rsplit('/',1)[-1].isdigit() else None
        if key=='/NODE':
            if not rows:_error(card,'native mesh 절점이 없습니다')
            for i,row in enumerate(rows):
                _tail(row,70,card);n=_integer(row[:10],card)
                if n in model['nodes']:_error(card,'native node ID가 중복됩니다')
                model['nodes'][n]=[_real(row[j:j+20],card) for j in (10,30,50)]
                model['lineage']['nodes'][str(n)]={**card['rows'][i]['origin'],'native_id':n,'local_id':n,'instance':None,'part':None}
                for j,axis in enumerate('XYZ'):field(card,i,axis,10+20*j,30+20*j,unit='mm')
        elif key.startswith('/TETRA4/'):
            if not rows:_error(card,'빈 native TETRA4 카드입니다')
            for i,row in enumerate(rows):
                _tail(row,50,card);eid,*native_conn=[_integer(row[j:j+10],card) for j in range(0,50,10)]
                if eid in model['elements'] or len(set(native_conn))!=4:_error(card,'native element/연결 ID가 중복됩니다')
                # Existing impact model is Abaqus ordered; the inverse is exact,
                # never nearest coordinates or connectivity sorting.
                conn=[native_conn[j] for j in (0,2,1,3)]
                model['elements'][eid]={'type':'C3D4','nodes':conn};native_element_parts[eid]=ident
                model['lineage']['elements'][str(eid)]={**card['rows'][i]['origin'],'native_id':eid,'native_connectivity':native_conn,
                                                      'local_id':eid,'instance':None,'part':ident}
        elif key.startswith('/MAT/ELAST/'):
            rows=_rows(card,3);title=_title(card)
            if title in model['materials']:_error(card,'다른 native material ID에 동일한 title이 있습니다')
            for row in rows[1:]:_tail(row,40,card)
            rho=_real(rows[1][:20],card);e=_real(rows[2][:20],card);nu=_real(rows[2][20:40],card)
            if rho<=0 or e<=0 or not -1<nu<.5 or _real(rows[1][20:40],card,blank=True)!=0:
                _error(card,'elastic 밀도/E/ν 또는 미지원 추가 밀도 옵션입니다')
            model['materials'][title]={'DENSITY':[[rho]],'ELASTIC':[[e,nu]]};material_ids[ident]=title
            model['lineage']['materials'][title]={'native_id':ident,'origin':card['origin']}
            field(card,1,'density',0,20,unit='Mg/mm^3');field(card,2,'E',0,20,unit='MPa');field(card,2,'nu',20,40)
        elif key.startswith('/PART/'):
            rows=_rows(card,2);_tail(rows[1],30,card)
            prop=_integer(rows[1][:10],card);mat=_integer(rows[1][10:20],card)
            if _integer(rows[1][20:30],card,zero=True,blank=True)!=0:_error(card,'native subset 옵션은 첫 지원 밖입니다')
            part_ids[ident]=(prop,mat,_title(card),card)
        elif key.startswith('/PROP/SOLID/'):
            rows=_rows(card,5)
            for row,width in zip(rows[1:],[100,100,100,30]):_tail(row,width,card)
            properties[ident]=card
        elif key.startswith('/GRNOD/'):
            _rows(card,minimum=2)
            if ident in groups:_error(card,'종류가 다른 GRNOD가 같은 native group ID를 사용합니다')
            groups[ident]=(key.split('/')[2],_ids(rows[1:],card),card)
        elif key.startswith('/GRBRIC/BRIC/'):
            _rows(card,minimum=2);brick_groups[ident]=(_ids(rows[1:],card),card)
        elif key.startswith('/SURF/SEG/'):
            rows=_rows(card,minimum=2);title=_title(card)
            if title in model['surfaces']:_error(card,'중복된 native surface title입니다')
            seen=set();faces=[]
            for row in rows[1:]:
                try:seg,nodes=_segment_nodes(row)
                except ValueError as error:_error(card,str(error))
                if seg in seen:_error(card,'native segment ID가 중복됩니다')
                seen.add(seg);faces.append(nodes)
            surfaces[ident]=(title,faces,card);model['surfaces'][title]=[]
        elif key.startswith('/FUNCT/'):
            rows=_rows(card,3)
            for row in rows[1:]:_tail(row,40,card)
            if [[_real(row[:20],card),_real(row[20:40],card)] for row in rows[1:]]!=[[0.,1.],[1.,1.]]:
                _error(card,'첫 native 지원은 명시 constant function (0,1),(1,1)입니다')
        elif key.startswith('/BCS/'):
            rows=_rows(card,2);row=rows[1];_tail(row,30,card)
            if row[:3].strip() or row[6:7].strip() or row[7:10]!='000' or _integer(row[10:20],card,zero=True,blank=True):
                _error(card,'BCS는 global 병진 고정만 지원합니다')
            if len(row[3:6])!=3 or set(row[3:6])-{'0','1'}:_error(card,'BCS 병진 mask가 잘못되었습니다')
        elif key.startswith('/INIVEL/TRA/'):
            rows=_rows(card,3)
            _tail(rows[1],80,card);_tail(rows[2],20,card)
            if (_integer(rows[1][70:80],card,zero=True,blank=True)
                    or _real(rows[2][:10],card,blank=True)!=0
                    or _integer(rows[2][10:20],card,zero=True,blank=True)!=0):
                _error(card,'초기속도는 global/시각0/sensor0만 지원합니다')
            for j,axis in enumerate('XYZ'):field(card,1,'V'+axis,j*20,(j+1)*20,unit='mm/s')
        elif key.startswith('/INTER/TYPE24/'):
            rows=_rows(card,7)
            for row,width in zip(rows[1:],[100,100,80,100,60,100]):_tail(row,width,card)
            field(card,4,'friction',20,40)
        elif key.startswith('/GRAV/'):
            rows=_rows(card,2);_tail(rows[1],100,card);field(card,1,'acceleration',80,100,unit='mm/s^2')
    if not model['nodes'] or not model['elements'] or len(model['nodes'])>1000000 or len(model['elements'])>1000000:
        raise SourceError('첫 native 입력은 1~1000000개의 절점과 C3D4 요소가 필요합니다')
    for eid,element in model['elements'].items():
        if set(element['nodes'])-model['nodes'].keys():raise SourceError('native 요소가 없는 node ID를 참조합니다')
        pid=native_element_parts[eid]
        if pid not in part_ids:raise SourceError('native 요소의 PART가 없습니다')
        prop,mat,title,card=part_ids[pid]
        if prop not in properties or mat not in material_ids:_error(card,'native PART의 property/material이 없습니다')
        model['assignment'][eid]=material_ids[mat]
        model['elsets'].setdefault('P'+str(pid),set()).add(eid)
    # Even unreferenced influence cards must not bypass the effective-property
    # gate. This first subset rejects unused PART/MAT/PROP, rather than pretending
    # their fields were validated by the referenced-element postflight loop.
    used_parts=set(native_element_parts.values())
    used_props={part_ids[pid][0] for pid in used_parts}
    used_mats={part_ids[pid][1] for pid in used_parts}
    for ident,(_,_,_,card) in part_ids.items():
        if ident not in used_parts:_error(card,'참조되지 않은 native PART는 첫 지원에서 실행할 수 없습니다')
    for ident,card in properties.items():
        if ident not in used_props:_error(card,'참조되지 않은 native PROP 필드는 실행 검증 대상이 아닙니다')
    for ident in material_ids:
        if ident not in used_mats:
            _error(table['/MAT/ELAST/'+str(ident)],'참조되지 않은 native material은 실행할 수 없습니다')
    # Expose the exact face-ID mapping; duplicate/ambiguous topology is not matched.
    from .impact_sets import facets
    exact_faces={}
    for face in facets(model):exact_faces.setdefault(tuple(face['corners']),[]).append((face['element'],face['side']))
    for sid,(title,native_faces,card) in surfaces.items():
        faces=[]
        for native_face in native_faces:
            matches=exact_faces.get(tuple(native_face),[])
            if len(matches)!=1:_error(card,'native surface가 정확히 하나의 방향 있는 C3D4 면과 대응하지 않습니다')
            faces.append((str(matches[0][0]),matches[0][1]))
        if len(set(faces))!=len(faces):_error(card,'동일 요소면이 중복되었습니다')
        model['surfaces'][title]=faces
        model['lineage']['surfaces'][title]={'native_id':sid,'qualified':title,'origins':[card['origin']],'faces':faces}
    def group(gid,trail=()):
        if gid in trail or gid not in groups:raise SourceError('native GRNOD 참조가 없거나 순환합니다')
        kind,values,card=groups[gid]
        if kind=='NODE':members=set(values)
        elif kind=='PART':
            if set(values)-part_ids.keys():_error(card,'GRNOD/PART가 없는 PART를 참조합니다')
            members={n for e,p in native_element_parts.items() if p in values for n in model['elements'][e]['nodes']}
        elif kind=='SURF':
            if set(values)-surfaces.keys():_error(card,'GRNOD/SURF가 없는 surface를 참조합니다')
            members={n for sid in values for face in surfaces[sid][1] for n in face}
        elif kind=='GRBRIC':
            if set(values)-brick_groups.keys():_error(card,'GRNOD/GRBRIC가 없는 group을 참조합니다')
            elements={e for bg in values for e in brick_groups[bg][0]}
            if elements-model['elements'].keys():_error(card,'GRBRIC의 element ID가 없습니다')
            members={n for e in elements for n in model['elements'][e]['nodes']}
        else:members=set().union(*(group(v,(*trail,gid)) for v in values))
        if not members or members-model['nodes'].keys():_error(card,'native node group의 대상이 비거나 유실됐습니다')
        return members
    for gid in groups:
        key='G'+str(gid);model['nsets'][key]=group(gid)
        model['lineage']['nsets'][key]={'native_id':gid,'qualified':key,'label':_title(groups[gid][2]),
                                       'origins':[groups[gid][2]['origin']],'effective_ids':sorted(group(gid))}
    for bid,(elements,card) in brick_groups.items():
        if set(elements)-model['elements'].keys():_error(card,'GRBRIC에 없는 element ID가 있습니다')
        model['elsets']['B'+str(bid)]=set(elements)
    controls=default_settings();controls['source']=deepcopy(source)
    initial={'nodes':deepcopy(model['nodes']),'velocities_mm_s':{},'units':'Mg/mm/s/N/MPa',
             'input_route':'NATIVE_DIRECT','active_state':'UNKNOWN'}
    for card in starter:
        key=card['key'];rows=_rows(card)
        if key.startswith('/BCS/'):
            row=rows[1];gid=_integer(row[20:30],card)
            for n in sorted(group(gid)):
                for axis,mask in enumerate(row[3:6],1):
                    if mask=='1':model['blocks'].append({'card':'BOUNDARY','options':{},'rows':[(card['origin']['line'],f'{n},{axis},{axis},0')],'line':card['origin']['line']})
        elif key.startswith('/INIVEL/TRA/'):
            row=rows[1];gid=_integer(row[60:70],card);velocity=[_real(row[j:j+20],card) for j in (0,20,40)]
            for n in group(gid):
                if n in initial['velocities_mm_s']:_error(card,'겹치는 native 초기 운동 집합입니다')
                initial['velocities_mm_s'][n]=velocity[:]
            controls['motions'].append({'node_set':'G'+str(gid),'mode':'velocity','height_mm':None,'velocity_mm_s':velocity,
                                        'omega_rad_s':[0.,0.,0.],'center_mm':[0.,0.,0.],'translation_mm':[0.,0.,0.]})
        elif key.startswith('/INTER/TYPE24/'):
            row=rows[1];main,secondary=_integer(row[:10],card),_integer(row[10:20],card)
            if main not in surfaces or secondary not in surfaces:_error(card,'TYPE24가 없는 surface ID를 참조합니다')
            friction=_real(rows[4][20:40],card)
            if main==secondary or friction<0:_error(card,'TYPE24 대상 또는 마찰계수가 잘못되었습니다')
            controls['contacts'].append({'a':surfaces[secondary][0],'b':surfaces[main][0],'law':'TYPE24','friction':friction})
            model['native_contact_titles'][str(len(controls['contacts']))]=_title(card)
        elif key.startswith('/GRAV/'):
            row=rows[1];direction=row[10:20].strip()
            if direction not in ('X','Y','Z'):_error(card,'global 중력 방향이 아닙니다')
            index='XYZ'.index(direction)
            # Duplicate components, constant function and all auxiliary fields are
            # checked independently by existing validate_physics below.
            controls['gravity_mm_s2'][index]=_real(row[80:100],card)
    engine_table={}
    for card in engine:
        key=card['key']
        if key not in ENGINE_FIXED and key!=f'/RUN/{run_name}/1':_error(card,'실행 미지원 Engine 영향 카드/옵션: '+key)
        if key in engine_table:_error(card,'Engine control이 중복되었습니다')
        engine_table[key]=card
    required={f'/RUN/{run_name}/1','/ANIM/DT','/ANIM/VECT/DISP','/ANIM/VECT/VEL','/TH/TITLE','/TFILE/4','/STOP'}
    if required-engine_table.keys():raise SourceError('필수 native Engine control/output이 없습니다: '+', '.join(sorted(required-engine_table.keys())))
    if not engine or engine[0]['key']!=f'/RUN/{run_name}/1' or engine[-1]['key']!='/STOP':
        raise SourceError('Engine는 원 RUN으로 시작하여 STOP으로 끝나야 합니다')
    if ('/DT' in engine_table)==('/DT/NODA/CST/0' in engine_table):raise SourceError('CFL 또는 mass scaling control을 하나만 지정하세요')
    t={};solid_dt=None
    for key,card in engine_table.items():
        if key.startswith('/RUN/'):
            t['end_s']=_control_tokens(card,1)[0];engine_field(card,'end_s',0,'s')
        elif key in ('/DT','/DT/NODA/CST/0'):
            scale,target=_control_tokens(card,2);t.update(scale=scale,mass_scaling=key!='/DT',target_step_s=target if key!='/DT' else None)
            if key=='/DT' and target!=0:_error(card,'/DT의 미지원 두 번째 field는 0이어야 합니다')
            engine_field(card,'scale',0,'1')
            if key!='/DT':engine_field(card,'target_step_s',1,'s')
        elif key=='/DT1/BRICK/STOP':
            solid_scale,minimum=_control_tokens(card,2)
            if minimum!=0:_error(card,'첫 DT1/BRICK/STOP minimum은 명시 0이어야 합니다')
            solid_dt=solid_scale;engine_field(card,'scale',0,'1')
        elif key=='/ANIM/DT':
            start,interval=_control_tokens(card,2)
            if start!=0:_error(card,'첫 지원 ANIM 시작 시각은 0입니다')
            t['field_interval_s']=interval;engine_field(card,'field_interval_s',1,'s')
        elif key=='/TFILE/4':t['history_interval_s']=_control_tokens(card,1)[0];engine_field(card,'history_interval_s',0,'s')
        elif key=='/STOP':
            if _control_tokens(card,5)!=[0.,0.,0.,1.,1.]:_error(card,'STOP의 제한/출력 옵션이 첫 지원과 다릅니다')
        else:_rows(card,0)
    if (not 0<t['scale']<=1 or any(t[k]<=0 for k in ('end_s','field_interval_s','history_interval_s'))
            or max(t['field_interval_s'],t['history_interval_s'])>t['end_s']
            or t['end_s']/t['field_interval_s']>1023
            or t['mass_scaling'] and t['target_step_s']<=0):
        raise SourceError('종료·출력 간격·CFL·mass scaling을 확인하세요')
    controls['time']=t
    physics=validate_physics(graphs['starter']['text'],model,initial,controls)
    if solid_dt is not None:
        if t['mass_scaling'] or solid_dt!=t['scale']:
            _error(engine_table['/DT1/BRICK/STOP'],'DT1은 mass scaling 없이 /DT와 같은 명시 scale을 사용해야 합니다')
        if (not all(e['type']=='C3D4' for e in model['elements'].values()) or
            physics['effective_formulation']['Itetra4_by_element']!={str(e):1000 for e in model['elements']}):
            _error(engine_table['/DT1/BRICK/STOP'],'DT1 첫 지원은 기존 탄성 C3D4 / Itetra4=1000입니다')
        for item in fields:
            if item['role']=='engine' and item['field']=='scale' and item['card'] in ('/DT','/DT1/BRICK/STOP'):
                item['label']='전체·고체 시간증분 계수 함께 변경'
    # Check nonzero velocity on fixed translational DOFs independently of converter.
    for block in model['blocks']:
        n,axis,*_=map(int,block['rows'][0][1].split(','))
        if initial['velocities_mm_s'].get(n,[0.,0.,0.])[axis-1]!=0:
            raise SourceError('구속 자유도와 native 초기속도가 충돌합니다')
    return {'model':model,'settings':controls,'initial':initial,'physics':physics,'fields':fields,
            'cards':starter+engine,'starter_text':graphs['starter']['text'],'engine_text':graphs['engine']['text'],
            'name':run_name,'starter':bundle['starter'],'engine':bundle['engine'],
            'support':'NATIVE_2025_ELASTIC_C3D4_V1'}


def settings_from_source(source):
    """Explicit import of source-authoritative controls; no runtime probing."""
    return deepcopy(parse_source(source)['settings'])


def validate_settings(settings):
    from .impact_model import default_settings
    from .impact_responses import validate as validate_responses
    if not isinstance(settings,dict) or set(settings)-{'generated_sets','cohesive','responses','source_reference_bindings'}!=set(default_settings())-{'generated_sets','cohesive','responses','source_reference_bindings'}:
        raise ValueError('native 충격 정의의 항목을 확인하세요')
    parsed=parse_source(settings['source'])
    for name in ('time','gravity_mm_s2','motions','contacts'):
        if settings.get(name)!=parsed['settings'][name]:
            raise SourceError('native 원문과 '+name+' 표 값이 다릅니다. 원문 field의 명시 편집으로 적용하세요')
    if settings.get('cohesive'):raise SourceError('첫 native 직접 경로는 elastic C3D4입니다. LAW117/B는 별도 지원 범위입니다')
    from .impact_sets import apply
    model=apply(parsed['model'],settings['source'],settings.get('generated_sets',[]))
    from .impact_reference_bindings import validate as validate_bindings
    validate_bindings(settings,model)
    validate_responses(model,settings.get('responses',[]))
    requested={'displacement':'/ANIM/VECT/DISP','velocity':'/ANIM/VECT/VEL','acceleration':'/ANIM/VECT/ACC',
               'contact_force':'/ANIM/VECT/CONT','contact_impulse':'/ANIM/VECT/CONT','stress':'/ANIM/BRICK/TENS/STRESS'}
    declared={c['key'] for c in parsed['cards'] if c['role']=='engine'}
    for row in settings.get('responses',[]):
        if requested.get(row['quantity']) not in declared:raise SourceError('선택 응답의 native 출력 카드가 없습니다')
    return deepcopy(settings)


def edit_field(settings, field_id, value, *, reason, expected_source_sha256):
    from .impact_input_edits import replace_range
    from .storage import canonical_hash
    parsed=parse_source(settings['source'])
    matches=[f for f in parsed['fields'] if f['id']==field_id]
    if len(matches)!=1:raise SourceError('정확한 native 원문 field를 선택하세요')
    f=matches[0]
    if type(value) not in (int,float) or not math.isfinite(value):raise SourceError('유한한 수치를 입력하세요')
    token=format(value,'.17g') if f['kind']=='token' else f'{value:{f["width"]}.12e}'
    if f['kind']!='token' and len(token)!=f['width']:raise SourceError('수치가 native field 폭을 벗어납니다')
    source=replace_range(settings['source'],f['file'],f['start'],f['end'],token,reason=reason,
                         expected_source_sha256=expected_source_sha256)
    # DT1 projects one common scale: an explicit scale edit updates both exact fields atomically.
    linked=[v for v in parsed['fields'] if v['field']=='scale' and v['card'] in ('/DT','/DT1/BRICK/STOP')]
    if f['field']=='scale' and len(linked)==2:
        for other in linked:
            if other['id']!=f['id']:
                source=replace_range(source,other['file'],other['start'],other['end'],format(value,'.17g'),
                    reason=reason,expected_source_sha256=canonical_hash(source))
    # Source is authoritative. Refresh only its exactly projected physical controls.
    result=settings_from_source(source)
    result['responses']=deepcopy(settings.get('responses',[]))
    # Generated target receipts bind the source bytes; retain as stale instead of silently re-anchoring.
    result['generated_sets']=deepcopy(settings.get('generated_sets',[]))
    result['qualification']=settings['qualification']
    from .impact_reference_bindings import KEY,preserve_before_edit
    result[KEY]=preserve_before_edit(settings)
    return result


def export_direct(settings, output):
    validate_settings(settings)
    before=parse_source(settings['source'])
    receipt=export_tree(settings['source'],output)
    # Readback the exported bytes, not a regenerated INP or a normalized card set.
    from .impact_input_edits import edited_files
    for name,raw in edited_files(settings['source']).items():
        if (Path(output)/name).read_bytes()!=raw:raise SourceError('내보낸 native bytes가 명시 수정본과 다릅니다',name)
    return {'route':'NATIVE_DIRECT','starter':before['starter'],'engine':before['engine'],'files':receipt,
            'physics':before['physics'],'converter_execution':'NOT_PERFORMED'}
