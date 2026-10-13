"""Bounded flattened user FE input for the existing Simulation owner.

Canonical input quantities are Mg, mm, s, N, MPa. Import never guesses units.
Only enumerated INP cards are admitted; converter warnings cannot define physics.
"""
from copy import deepcopy
import math
import re

BACKEND = 'explicit.opencourant.model'
NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
OPTIONS = {
    'HEADING':set(), 'NODE':{'NSET'}, 'ELEMENT':{'TYPE','ELSET'},
    'NSET':{'NSET','GENERATE'}, 'ELSET':{'ELSET','GENERATE'},
    'MATERIAL':{'NAME'}, 'DENSITY':set(), 'ELASTIC':set(), 'PLASTIC':set(),
    'SOLID SECTION':{'ELSET','MATERIAL'}, 'SURFACE':{'NAME','TYPE'},
    'BOUNDARY':set(),
}
WIDTHS = {'C3D4':4, 'C3D8':8, 'C3D8R':8, 'C3D10':10}
# Quadratic contact is the explicit converter's corner-faceted TYPE24, not
# the native static penalty law. No automatic Kn/Kstick transfer.
SURFACE_SIDES = {'C3D4':4,'C3D10':4,'C3D8':6,'C3D8R':6}


def number(value, label, positive=False):
    if type(value) not in (int,float) or not math.isfinite(value) or positive and value <= 0:
        raise ValueError(label + ': 유한한 ' + ('양수' if positive else '수') + '를 입력하세요')
    return float(value)


def vector(value, label):
    if not isinstance(value,list) or len(value)!=3:
        raise ValueError(label + ': X/Y/Z 세 성분을 입력하세요')
    return [number(x,label) for x in value]


def default_settings():
    return {'source':{'title':'', 'format':'INP','units':'Mg/mm/s','text':'','provenance':{}},
        'motions':[], 'contacts':[], 'gravity_mm_s2':[0.,0.,0.],
        'time':{'end_s':.001,'field_interval_s':.0001,'history_interval_s':.00001,
                'scale':.9,'mass_scaling':False,'target_step_s':None},
        'qualification':'UNKNOWN'}


def parse_inp(text):
    if not isinstance(text,str) or len(text.encode('utf-8'))>6*1024**2 or '\x00' in text:
        raise ValueError('유한요소 입력은 6 MiB 이하의 텍스트여야 합니다')
    text.encode('ascii')
    blocks=[]
    for line_no,line in enumerate(text.splitlines(),1):
        line=line.strip()
        if not line or line.startswith('**'): continue
        if line.startswith('*'):
            parts=[p.strip().upper() for p in line[1:].split(',') if p.strip()]
            card=parts[0]; options={}
            if card not in OPTIONS:
                raise ValueError(f'{line_no}행: {card} 카드는 이 가져오기 경로에서 지원하지 않습니다')
            for option in parts[1:]:
                key,sep,value=option.partition('=')
                if key in options or key not in OPTIONS[card]:
                    raise ValueError(f'{line_no}행: 지원하지 않거나 중복된 옵션 {key}')
                options[key]=value if sep else True
            blocks.append({'card':card,'options':options,'rows':[],'line':line_no})
        elif not blocks: raise ValueError('첫 입력 카드를 확인하세요')
        else: blocks[-1]['rows'].append((line_no,line))
    nodes={}; elements={}; nsets={}; elsets={}; surfaces={}; materials={}; sections=[]
    current=None
    def integer(token):
        if not re.fullmatch(r'[0-9]+',token.strip()) or int(token)<=0: raise ValueError('양의 원본 번호가 필요합니다')
        return int(token)
    def numeric(token):
        x=float(token)
        if not math.isfinite(x): raise ValueError('입력에 비유한 값이 있습니다')
        return x
    def name(value):
        if not isinstance(value,str) or not NAME.fullmatch(value): raise ValueError('입력 집합 이름을 확인하세요')
        return value
    for b in blocks:
        c,o,rows=b['card'],b['options'],b['rows']
        if c=='NODE':
            for _,line in rows:
                values=[p.strip() for p in line.split(',')]
                if len(values)!=4: raise ValueError('절점은 번호와 XYZ 세 좌표가 필요합니다')
                ident=integer(values[0])
                if ident in nodes: raise ValueError('중복 절점 번호')
                nodes[ident]=[numeric(x) for x in values[1:]]
                if 'NSET' in o: nsets.setdefault(name(o['NSET']),set()).add(ident)
        elif c=='ELEMENT':
            kind=o.get('TYPE')
            if kind not in WIDTHS: raise ValueError('지원 솔리드 요소: C3D4, C3D8/R, C3D10')
            for _,line in rows:
                values=[p.strip() for p in line.split(',') if p.strip()]
                if len(values)!=WIDTHS[kind]+1: raise ValueError('요소 연결은 한 행의 정확한 절점 순서가 필요합니다')
                ident=integer(values[0]); conn=[integer(x) for x in values[1:]]
                if ident in elements or len(set(conn))!=len(conn): raise ValueError('중복 요소/절점')
                elements[ident]={'type':kind,'nodes':conn}
                if 'ELSET' in o: elsets.setdefault(name(o['ELSET']),set()).add(ident)
        elif c in ('NSET','ELSET'):
            table=nsets if c=='NSET' else elsets
            target=table.setdefault(name(o.get(c)),set())
            for _,line in rows:
                values=[integer(p) for p in line.split(',') if p.strip()]
                if o.get('GENERATE'):
                    if len(values)!=3 or values[1]<values[0] or (values[1]-values[0])//values[2]>1000000:
                        raise ValueError('유한한 집합 범위를 지정하세요')
                    values=range(values[0],values[1]+1,values[2])
                target.update(values)
        elif c=='MATERIAL':
            current=name(o.get('NAME'))
            if current in materials: raise ValueError('중복 재료')
            materials[current]={}
        elif c in ('DENSITY','ELASTIC','PLASTIC'):
            if current is None or c in materials[current]: raise ValueError('재료 순서/중복 선언 확인')
            data=[[numeric(v) for v in line.split(',') if v.strip()] for _,line in rows]
            if c=='DENSITY' and (len(data)!=1 or len(data[0])!=1 or data[0][0]<=0): raise ValueError('밀도 [Mg/mm³]를 지정하세요')
            if c=='ELASTIC' and (len(data)!=1 or len(data[0])!=2 or data[0][0]<=0 or not -1<data[0][1]<.5): raise ValueError('등방 탄성 E [MPa], ν를 확인하세요')
            if c=='PLASTIC' and (not data or any(len(x)!=2 or x[0]<=0 or x[1]<0 for x in data) or
                data[0][1]!=0 or any(b[1]<=a[1] or b[0]<a[0] for a,b in zip(data,data[1:]))):
                raise ValueError('단조 경화 표: 응력 [MPa], 소성변형률 [1], 첫 소성변형률 0')
            materials[current][c]=data
        elif c=='SOLID SECTION':
            if any(line.strip().strip(',').strip() for _,line in rows): raise ValueError('솔리드 section 추가 입력은 지원하지 않습니다')
            sections.append((name(o.get('ELSET')),name(o.get('MATERIAL'))))
        elif c=='SURFACE':
            if o.get('TYPE')!='ELEMENT': raise ValueError('명시 ELEMENT 면 집합을 사용하세요')
            label=name(o.get('NAME'))
            if label in surfaces: raise ValueError('중복 면 집합')
            surfaces[label]=[tuple(p.strip().upper() for p in line.split(',')) for _,line in rows]
        elif c=='BOUNDARY':
            for _,line in rows:
                values=[v.strip().upper() for v in line.split(',')]
                if not 2<=len(values)<=4: raise ValueError('구속 입력을 확인하세요')
                lo=integer(values[1]); hi=integer(values[2]) if len(values)>2 and values[2] else lo
                if not 1<=lo<=hi<=3 or len(values)>3 and numeric(values[3])!=0:
                    raise ValueError('고정 병진 자유도만 직접 가져옵니다. 변위 이력은 별도 지원이 필요합니다')
    if not nodes or not elements: raise ValueError('자신의 절점·솔리드 메시를 먼저 가져오세요')
    if len(nodes)>1000000 or len(elements)>1000000: raise ValueError('이 문서 경로의 메시 크기를 초과합니다')
    for row in elements.values():
        if set(row['nodes'])-nodes.keys(): raise ValueError('없는 절점을 참조하는 요소')
    for table,known in ((nsets,nodes),(elsets,elements)):
        if any(not ids or ids-known.keys() for ids in table.values()): raise ValueError('집합의 원본 번호를 확인하세요')
    assignment={}
    for eset,mat in sections:
        if eset not in elsets or mat not in materials: raise ValueError('section의 요소/재료 집합이 없습니다')
        for eid in elsets[eset]:
            if eid in assignment: raise ValueError('요소에 재료가 중복 배정되었습니다')
            assignment[eid]=mat
    if set(assignment)!=set(elements) or any(not {'DENSITY','ELASTIC'}<=m.keys() for m in materials.values()):
        raise ValueError('모든 요소에 명시 밀도와 등방 재료가 필요합니다')
    for label,rows in surfaces.items():
        if not rows: raise ValueError('빈 접촉 면 집합')
        for row in rows:
            if len(row)!=2 or not re.fullmatch('S[1-6]',row[1]): raise ValueError('요소 면 번호를 확인하세요')
            ids={int(row[0])} if row[0].isdigit() else elsets.get(row[0],set())
            if not ids or any(e not in elements or int(row[1][1:])>SURFACE_SIDES[elements[e]['type']] for e in ids):
                raise ValueError('없는 요소 면 집합')
    # Validate boundary targets after all sets have been collected.
    for b in blocks:
        if b['card']=='BOUNDARY':
            for _,line in b['rows']:
                target=line.split(',')[0].strip().upper()
                if not (target.isdigit() and int(target) in nodes or target in nsets): raise ValueError('구속 절점 집합을 확인하세요')
    return {'nodes':nodes,'elements':elements,'nsets':nsets,'elsets':elsets,'surfaces':surfaces,
            'materials':materials,'assignment':assignment,'blocks':blocks}


def validate_settings(settings):
    if not isinstance(settings,dict) or set(settings)!=set(default_settings()):
        raise ValueError('충격 정의의 필수 항목을 확인하세요')
    source=settings['source']
    if source.get('format')!='INP' or source.get('units')!='Mg/mm/s':
        raise ValueError('이 경로는 명시적으로 Mg/mm/s/N/MPa로 작성한 평탄화 INP를 사용합니다')
    model=parse_inp(source.get('text'))
    t=settings['time']
    for key in ('end_s','field_interval_s','history_interval_s','scale'):
        number(t.get(key),key,True)
    if not 0<t['scale']<=1 or max(t['field_interval_s'],t['history_interval_s'])>t['end_s']:
        raise ValueError('출력 간격은 종료 시간 이하, 시간증분 계수는 0 초과 1 이하여야 합니다')
    if t['end_s']/t['field_interval_s']>1023: raise ValueError('필드 출력은 최대 1024프레임입니다')
    if type(t.get('mass_scaling')) is not bool: raise ValueError('질량 스케일링을 명시적으로 선택하세요')
    if t['mass_scaling']: number(t.get('target_step_s'),'목표 시간증분',True)
    elif t.get('target_step_s') is not None: raise ValueError('질량 스케일링을 사용하지 않으면 목표 증분을 비워 두세요')
    gravity=vector(settings['gravity_mm_s2'],'중력 [mm/s²]')
    touched=set()
    for m in settings['motions']:
        ids=model['nsets'].get(m.get('node_set'))
        if not ids or ids&touched: raise ValueError('초기 운동은 겹치지 않는 절점 집합을 선택하세요')
        touched.update(ids)
        vector(m['velocity_mm_s'],'초기 속도'); vector(m['omega_rad_s'],'초기 각속도')
        vector(m['center_mm'],'회전 중심'); vector(m['translation_mm'],'초기 위치 이동')
        if m['mode'] not in ('velocity','release_height','impact_height'): raise ValueError('초기조건 방식을 선택하세요')
        if m['mode']!='velocity':
            h=number(m['height_mm'],'높이',True)
            if not math.hypot(*gravity): raise ValueError('높이 조건에는 중력 방향과 크기가 필요합니다')
            if m['mode']=='impact_height' and any(m['velocity_mm_s']): raise ValueError('높이 환산 속도와 입력 속도를 중복 적용하지 않습니다')
    pairs=set()
    for pair in settings['contacts']:
        a,b=pair['a'],pair['b']
        if a==b or a not in model['surfaces'] or b not in model['surfaces'] or (a,b) in pairs:
            raise ValueError('서로 다른 정확한 접촉 면 두 집합을 선택하세요')
        pairs.add((a,b))
        if pair.get('law')!='TYPE24': raise ValueError('현재 사용자 메시 경로는 명시 TYPE24 접촉입니다')
        if number(pair.get('friction'),'마찰계수')<0: raise ValueError('음의 마찰계수는 지원하지 않습니다')
    return deepcopy(settings)


def render(settings):
    validate_settings(settings)
    model=parse_inp(settings['source']['text'])
    nodes=deepcopy(model['nodes']); velocities={}
    gravity=settings['gravity_mm_s2']; g=math.hypot(*gravity)
    for m in settings['motions']:
        shift=list(m['translation_mm']); velocity=list(m['velocity_mm_s'])
        if m['mode']=='release_height':
            shift=[x-m['height_mm']*a/g for x,a in zip(shift,gravity)]
        elif m['mode']=='impact_height':
            velocity=[math.sqrt(2*g*m['height_mm'])*a/g for a in gravity]
        for n in model['nsets'][m['node_set']]:
            # Rotation centre moves with the prescribed body translation.
            r=[x-c for x,c in zip(nodes[n],m['center_mm'])]; w=m['omega_rad_s']
            spin=[w[1]*r[2]-w[2]*r[1],w[2]*r[0]-w[0]*r[2],w[0]*r[1]-w[1]*r[0]]
            velocities[n]=[v+s for v,s in zip(velocity,spin)]
            nodes[n]=[x+s for x,s in zip(nodes[n],shift)]
    lines=['** CAELab explicit canonical Mg/mm/s input']
    for b in model['blocks']:
        card='*'+b['card']+''.join(','+k+('' if v is True else '='+v) for k,v in b['options'].items())
        lines.append(card)
        for _,line in b['rows']:
            if b['card']=='NODE':
                n=int(line.split(',')[0]); line=str(n)+','+','.join(format(x,'.17g') for x in nodes[n])
            lines.append(line)
    lines.extend(['*INITIAL CONDITIONS,TYPE=VELOCITY'])
    for n,values in sorted(velocities.items()):
        lines.extend(f'{n},{i+1},{v:.17g}' for i,v in enumerate(values))
    for i,p in enumerate(settings['contacts'],1):
        lines.extend([f'*SURFACE INTERACTION,NAME=IMPACT{i}','*FRICTION',str(p['friction']),
                      f'*CONTACT PAIR,INTERACTION=IMPACT{i},TYPE=SURFACE TO SURFACE',p['a']+','+p['b']])
    lines.extend(['*STEP','*DYNAMIC,EXPLICIT',','+format(settings['time']['end_s'],'.17g')])
    if g:
        # DLOAD targets each disjoint section once, never per contact face.
        lines.append('*DLOAD')
        for b in model['blocks']:
            if b['card']=='SOLID SECTION':
                lines.append(b['options']['ELSET']+',GRAV,'+format(g,'.17g')+','+','.join(format(a/g,'.17g') for a in gravity))
    lines.extend(['*END STEP',''])
    return '\n'.join(lines), {'nodes':nodes,'velocities_mm_s':velocities,
        'units':'Mg/mm/s/N/MPa','contact_geometry':'corner_facets','active_state':'UNKNOWN'}


def engine_deck(settings, name='impact'):
    t=settings['time']
    lines=[f'/RUN/{name}/1',format(t['end_s'],'.17g'),'/PRINT/-100/50','/PARITH/OFF',
           '/DT/NODA/CST/0' if t['mass_scaling'] else '/DT/NODA/STOP',
           f"{t['scale']:.17g} {t['target_step_s'] if t['mass_scaling'] else 0}",
           '/ANIM/DT',f"0 {t['field_interval_s']:.17g}",'/ANIM/VECT/DISP','/ANIM/VECT/VEL',
           '/ANIM/VECT/ACC','/ANIM/BRICK/TENS/STRESS','/ANIM/BRICK/DAMA',
           '/ANIM/ELEM/DAMG','/TFILE/4',format(t['history_interval_s'],'.17g'),'/STOP','']
    return '\n'.join(lines)
