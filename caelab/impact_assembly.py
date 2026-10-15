"""Lossless lineage compiler for the first admitted Abaqus assembly subset.

Only meshed PARTs, elastic C3D4, one ASSEMBLY, dependent INSTANCEs,
sets/surfaces and model-level fixed translational BOUNDARY are admitted.
The output is a separate flat input for the existing INP2RAD boundary.
No source IDs, labels, coordinates or connectivity are welded heuristically.
"""
from copy import deepcopy
import math
import re
from .impact_source import SourceError, locate, MAX_BYTES

LABEL = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,79}\Z')
HIERARCHY = {'PART', 'END PART', 'ASSEMBLY', 'END ASSEMBLY', 'INSTANCE', 'END INSTANCE'}
ALLOWED = {
    'PART': {'NAME'}, 'END PART': set(), 'ASSEMBLY': {'NAME'}, 'END ASSEMBLY': set(),
    'INSTANCE': {'NAME', 'PART'}, 'END INSTANCE': set(), 'HEADING': set(),
    'NODE': {'NSET'}, 'ELEMENT': {'TYPE', 'ELSET'}, 'NSET': {'NSET', 'GENERATE', 'INSTANCE'},
    'ELSET': {'ELSET', 'GENERATE', 'INSTANCE'}, 'SURFACE': {'NAME', 'TYPE'},
    'SOLID SECTION': {'ELSET', 'MATERIAL'}, 'MATERIAL': {'NAME'}, 'DENSITY': set(),
    'ELASTIC': set(), 'BOUNDARY': set(),
}


def has_hierarchy(text):
    return bool(re.search(r'(?im)^\s*\*(?:PART|ASSEMBLY|INSTANCE|END PART|END ASSEMBLY|END INSTANCE)(?:\s*,|\s*$)', text or ''))


def origin(spans, line):
    file, physical = locate(spans, line)
    occurrence = next((s['occurrence'] for s in spans
                       if s['flat_line'] <= line < s['flat_line'] + s['count']), 0)
    return {'file': file or 'input.inp', 'line': physical, 'occurrence': occurrence,
            'flat_line': line, 'revision': 'effective_source'}


def tokenize(text, spans=()):
    if not isinstance(text, str) or len(text.encode('ascii')) > MAX_BYTES or '\0' in text:
        raise SourceError('계층 입력은 6 MiB 이하 ASCII 원문이어야 합니다')
    blocks = []
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('**'): continue
        where = origin(spans, line_no)
        if line.startswith('*'):
            fields = [v.strip().upper() for v in line[1:].split(',')]
            if not fields[0]: raise SourceError('빈 카드입니다', where['file'], where['line'])
            options = {}
            for field in fields[1:]:
                if not field: raise SourceError('빈 카드 옵션입니다', where['file'], where['line'])
                key, sep, value = field.partition('=')
                if key in options or sep and not value:
                    raise SourceError('중복되거나 값이 없는 옵션입니다', where['file'], where['line'])
                options[key] = value if sep else True
            blocks.append({'card': fields[0], 'options': options, 'rows': [], 'origin': where})
        elif not blocks:
            raise SourceError('첫 카드를 확인하세요', where['file'], where['line'])
        else:
            blocks[-1]['rows'].append({'text': line, 'origin': where})
    return blocks


def _label(value, b):
    if not isinstance(value, str) or not LABEL.fullmatch(value):
        _fail(b, '첫 지원 이름은 영문자로 시작하는 영숫자·_·- 80자 이하입니다')
    return value


def _fail(b, message, *, instances=()):
    where = b['origin']
    error = SourceError(message, where['file'], where['line'])
    error.occurrence = where['occurrence']
    error.impact = {'instances': list(instances), 'scope': b.get('scope', 'MODEL'),
                    'card': b.get('card'), 'source': deepcopy(where),
                    'references': deepcopy(b.get('options', {})), 'execution': 'BLOCKED'}
    raise error


def _num(token, b):
    try: value = float(token)
    except (ValueError, TypeError): _fail(b, '유한한 수치가 필요합니다')
    if not math.isfinite(value): _fail(b, '비유한 수치입니다')
    return value


def _id(token, b):
    if not isinstance(token, str) or not re.fullmatch('[0-9]+', token) or not 0 < int(token) <= 2147483647:
        _fail(b, '32-bit 양의 local ID가 필요합니다')
    return int(token)


def rotation(axis_a, axis_b, degrees):
    """Active right-handed rotation of a column vector. Not a frame transform."""
    axis = [b - a for a, b in zip(axis_a, axis_b)]
    length = math.hypot(*axis)
    if not length or not math.isfinite(length): raise ValueError('회전축의 두 점은 달라야 합니다')
    u = [x / length for x in axis]
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    skew = [[0., -u[2], u[1]], [u[2], 0., -u[0]], [-u[1], u[0], 0.]]
    return [[c * (i == j) + (1 - c) * u[i] * u[j] + s * skew[i][j]
             for j in range(3)] for i in range(3)]


def matvec(matrix, vector):
    return [sum(a * b for a, b in zip(row, vector)) for row in matrix]


def transform(b):
    rows = b['rows']
    if len(rows) > 2: _fail(b, 'INSTANCE는 이동 1행과 선택적 회전 1행만 지원합니다')
    translation, a, matrix, angle = [0., 0., 0.], [0., 0., 0.], [[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]], 0.
    axis_b = [0., 0., 1.]
    if rows:
        fields = rows[0]['text'].split(',')
        if len(fields) != 3: _fail(rows[0], '첫 INSTANCE 행은 XYZ 이동입니다. 순수 회전도 0,0,0을 명시하세요')
        translation = [_num(v.strip(), rows[0]) for v in fields]
    if len(rows) == 2:
        fields = rows[1]['text'].split(',')
        if len(fields) != 7: _fail(rows[1], '회전은 축의 두 점과 도(degree) 각도 7개 수치입니다')
        numbers = [_num(v.strip(), rows[1]) for v in fields]
        a, axis_b, angle = numbers[:3], numbers[3:6], numbers[6]
        try: matrix = rotation(a, axis_b, angle)
        except ValueError as error: _fail(rows[1], str(error))
    # Abaqus INSTANCE applies translation BEFORE rotation around the global a-b axis.
    offset = [x + y for x, y in zip(matvec(matrix, [t - q for t, q in zip(translation, a)]), a)]
    return {'rotation': matrix, 'offset_mm': offset, 'translation_mm': translation,
            'axis_a_mm': a, 'axis_b_mm': axis_b, 'angle_degree': angle,
            'order': 'TRANSLATE_THEN_ROTATE', 'frame': 'ASSEMBLY_GLOBAL'}


def _members(b, target, known, sets, resolve_token=None):
    """Sequential sets: only previous labels; exact GENERATE endpoint."""
    if not b['rows']: _fail(b, '빈 집합입니다')
    for row in b['rows']:
        tokens = [t.strip().upper() for t in row['text'].split(',')]
        if tokens[-1:] == ['']: tokens.pop()
        if not tokens or any(not t for t in tokens): _fail(row, '빈 집합 구성원입니다')
        if b['options'].get('GENERATE'):
            if len(tokens) not in (2, 3): _fail(row, 'GENERATE는 시작·끝·선택적 증분입니다')
            lo, hi = [_id(t, row) for t in tokens[:2]]
            step = _id(tokens[2], row) if len(tokens) == 3 else 1
            if hi < lo or (hi - lo) % step or (hi - lo) // step > 1000000:
                _fail(row, 'GENERATE의 끝점이 증분에 정확히 맞아야 합니다')
            tokens = [str(n) for n in range(lo, hi + 1, step)]
        for token in tokens:
            if resolve_token is not None:
                target.update(resolve_token(token, row))
            elif token.isdigit():
                ident = _id(token, row)
                if ident not in known: _fail(row, '집합이 없는 local ID를 참조합니다')
                target.add(ident)
            elif token in sets:
                target.update(sets[token])
            else:
                _fail(row, '집합 label은 앞에서 정의된 같은 scope 집합이어야 합니다')


def compile_source(text, spans=()):
    """Return the existing flat model plus a reversible source/instance receipt."""
    from .impact_model import parse_inp
    blocks = tokenize(text, spans)
    parts, instances, global_blocks, assembly_blocks = {}, [], [], []
    state, part, instance, assembly, assembly_closed = 'MODEL', None, None, None, False
    part_users = {}
    for b in blocks:
        if b['card'] == 'INSTANCE':
            part_users.setdefault(b['options'].get('PART'), []).append(b['options'].get('NAME'))
    for b in blocks:
        c, o = b['card'], b['options']
        b['scope'] = part or (instance['name'] if instance else assembly if state == 'ASSEMBLY' else state)
        if c not in ALLOWED or set(o) - ALLOWED.get(c, set()):
            _fail(b, '미지원 카드/옵션: ' + c + ' ' + ', '.join(sorted(set(o) - ALLOWED.get(c, set()))),
                  instances=part_users.get(part, [i['name'] for i in instances]))
        for key in ('GENERATE',):
            if key in o and o[key] is not True: _fail(b, key + '은 값 없는 flag입니다')
        if c in HIERARCHY - {'INSTANCE'} and b['rows']: _fail(b, c + '에는 data 행이 없어야 합니다')
        if c == 'PART':
            if state != 'MODEL' or assembly is not None: _fail(b, 'PART는 ASSEMBLY 앞 model level에서 정의하세요')
            part = _label(o.get('NAME'), b)
            if part in parts: _fail(b, '같은 이름의 PART가 반복 정의되었습니다', instances=part_users.get(part, []))
            parts[part] = {'blocks': [], 'origin': b['origin']}; state = 'PART'
        elif c == 'END PART':
            if state != 'PART': _fail(b, 'END PART의 scope가 다릅니다')
            part, state = None, 'MODEL'
        elif c == 'ASSEMBLY':
            if state != 'MODEL' or assembly is not None: _fail(b, '하나의 ASSEMBLY만 지원합니다')
            assembly = _label(o.get('NAME'), b); state = 'ASSEMBLY'
        elif c == 'END ASSEMBLY':
            if state != 'ASSEMBLY': _fail(b, 'END ASSEMBLY 전에 INSTANCE를 닫으세요')
            state, assembly_closed = 'MODEL', True
        elif c == 'INSTANCE':
            if state != 'ASSEMBLY': _fail(b, 'INSTANCE는 ASSEMBLY 안에서만 지원합니다')
            name, pname = _label(o.get('NAME'), b), _label(o.get('PART'), b)
            if name == 'ASSEMBLY' or any(i['name'] == name for i in instances): _fail(b, '중복되거나 예약된 INSTANCE 이름입니다')
            if pname not in parts: _fail(b, 'INSTANCE가 없는 PART를 참조합니다')
            instance = {'name': name, 'part': pname, 'origin': b['origin'], 'transform': transform(b), 'blocks': []}
            instances.append(instance); state = 'INSTANCE'
        elif c == 'END INSTANCE':
            if state != 'INSTANCE': _fail(b, 'END INSTANCE의 scope가 다릅니다')
            instance, state = None, 'ASSEMBLY'
        elif state == 'PART':
            if c not in ('NODE','ELEMENT','NSET','ELSET','SURFACE','SOLID SECTION'): _fail(b, 'PART level에서 지원하지 않는 카드입니다')
            if 'INSTANCE' in o: _fail(b, 'INSTANCE 집합 옵션은 assembly level 전용입니다')
            parts[part]['blocks'].append(b)
        elif state == 'INSTANCE':
            if c not in ('NSET','ELSET','SURFACE') or 'INSTANCE' in o: _fail(b, 'INSTANCE에는 새로운 집합/면만 추가할 수 있습니다')
            instance['blocks'].append(b)
        elif state == 'ASSEMBLY':
            if c not in ('NSET','ELSET','SURFACE'): _fail(b, '첫 assembly 지원은 집합·요소면입니다. connector/추가 mesh는 미지원입니다')
            assembly_blocks.append(b)
        else:
            if c not in ('HEADING','MATERIAL','DENSITY','ELASTIC','BOUNDARY'): _fail(b, '계층 모델의 model level 카드가 아닙니다')
            if c == 'BOUNDARY' and not assembly_closed: _fail(b, 'model BOUNDARY는 닫힌 ASSEMBLY 뒤에 지정하세요')
            global_blocks.append(b)
    if state != 'MODEL' or not assembly_closed or not instances:
        raise SourceError('PART/INSTANCE/ASSEMBLY scope가 완전히 닫히지 않았습니다')
    if set(parts) != set(part_users):
        # Do not silently ignore unsupported/uninstanced input definitions.
        unused = sorted(set(parts) - set(part_users))
        if unused: raise SourceError('사용되지 않은 PART가 있습니다: ' + ', '.join(unused))

    # Prepare each original part once, without global ID/label collisions.
    local = {}
    for pname, p in parts.items():
        nodes, elements, nsets, elsets, locations = {}, {}, {}, {}, {'nodes':{}, 'elements':{}, 'nsets':{}, 'elsets':{}}
        for b in p['blocks']:
            c, o = b['card'], b['options']
            if c == 'NODE':
                automatic = _label(o['NSET'], b) if 'NSET' in o else None
                for row in b['rows']:
                    tokens = [t.strip() for t in row['text'].split(',')]
                    if len(tokens) != 4: _fail(row, '절점은 local ID,X,Y,Z 네 값입니다')
                    ident = _id(tokens[0], row)
                    if ident in nodes: _fail(row, '같은 PART의 local node ID가 중복됩니다', instances=part_users[pname])
                    nodes[ident] = [_num(t, row) for t in tokens[1:]]; locations['nodes'][ident] = row['origin']
                    if automatic:
                        nsets.setdefault(automatic, set()).add(ident); locations['nsets'].setdefault(automatic, []).append(b['origin'])
            elif c == 'ELEMENT':
                if o.get('TYPE') != 'C3D4': _fail(b, '첫 계층 지원 요소/법칙은 elastic C3D4입니다', instances=part_users[pname])
                automatic = _label(o['ELSET'], b) if 'ELSET' in o else None
                for row in b['rows']:
                    tokens = [t.strip() for t in row['text'].split(',')]
                    if len(tokens) != 5: _fail(row, 'C3D4는 local element ID와 순서 있는 4절점입니다')
                    ident, *conn = [_id(t, row) for t in tokens]
                    if ident in elements or len(set(conn)) != 4: _fail(row, '중복 요소/연결 절점입니다', instances=part_users[pname])
                    elements[ident] = conn; locations['elements'][ident] = row['origin']
                    if automatic:
                        elsets.setdefault(automatic, set()).add(ident); locations['elsets'].setdefault(automatic, []).append(b['origin'])
            elif c in ('NSET','ELSET'):
                table, known, kind = (nsets,nodes,'nsets') if c == 'NSET' else (elsets,elements,'elsets')
                name = _label(o.get(c), b)
                added = set(); _members(b, added, known, table)
                table.setdefault(name, set()).update(added); locations[kind].setdefault(name, []).append(b['origin'])
        if not nodes or not elements: raise SourceError('각 PART에는 C3D4 mesh가 있어야 합니다', p['origin']['file'],p['origin']['line'])
        for eid, conn in elements.items():
            if set(conn) - nodes.keys(): _fail({'origin':locations['elements'][eid]}, '없는 local node를 참조합니다')
        local[pname] = {'nodes':nodes,'elements':elements,'nsets':nsets,'elsets':elsets,'locations':locations}

    output, compile_map = [], []
    lineage = {'schema':'impact-assembly-lineage-v1', 'assembly':assembly,
               'nodes':{}, 'elements':{}, 'nsets':{}, 'elsets':{}, 'surfaces':{}, 'materials':{}, 'conditions':[], 'instances':{}}
    def emit(line, where, count=1):
        output.append(line)
        compile_map.append({'flat_line':len(output),'count':1,'file':where['file'],
                            'source_line':where['line'],'occurrence':where['occurrence']})
    def setname(kind, scope, label):
        # An explicit namespace table, not lossy punctuation replacement.
        table = lineage[kind]
        qualified = scope + '.' + label
        for key, row in table.items():
            if row['qualified'] == qualified: return key
        key = {'nsets':'N','elsets':'E','surfaces':'S'}[kind] + f'{len(table)+1:06d}'
        table[key] = {'qualified':qualified,'scope':scope,'label':label,'origins':[]}
        return key
    catalogs, next_n, next_e = {}, 1, 1
    for inst in instances:
        name, pname = inst['name'], inst['part']; p = local[pname]
        scope = assembly + '.' + name
        nm = {n:next_n+j for j,n in enumerate(sorted(p['nodes']))}; next_n += len(nm)
        em = {e:next_e+j for j,e in enumerate(sorted(p['elements']))}; next_e += len(em)
        if max(next_n,next_e) > 1000001: _fail({'origin':inst['origin']}, '계층 compile 메시 크기 한도를 초과했습니다')
        ns, es = deepcopy(p['nsets']), deepcopy(p['elsets'])
        inherited = {'NSET':set(ns),'ELSET':set(es)}
        # Additional instance sets cannot override any inherited part name.
        for b in inst['blocks']:
            if b['card'] in ('NSET','ELSET'):
                c=b['card']; target=ns if c=='NSET' else es; known=p['nodes'] if c=='NSET' else p['elements']
                label=_label(b['options'].get(c),b)
                if label in inherited[c]: _fail(b,'INSTANCE는 상속된 집합을 재정의할 수 없습니다')
                added=set(); _members(b,added,known,target); target.setdefault(label,set()).update(added)
        nkeys={label:setname('nsets',scope,label) for label in ns}
        ekeys={label:setname('elsets',scope,label) for label in es}
        catalogs[name]={'nm':nm,'em':em,'ns':ns,'es':es,'nkeys':nkeys,'ekeys':ekeys,'scope':scope,'inst':inst}
        lineage['instances'][name] = {k:deepcopy(v) for k,v in inst.items() if k!='blocks'}
        emit('*NODE',inst['origin'])
        for n, effective in nm.items():
            xyz = [a+b for a,b in zip(matvec(inst['transform']['rotation'],p['nodes'][n]),inst['transform']['offset_mm'])]
            emit(str(effective)+','+','.join(format(v,'.17g') for v in xyz),p['locations']['nodes'][n])
            lineage['nodes'][str(effective)] = {**p['locations']['nodes'][n], 'part':pname,'instance':name,
                                                'local_id':n,'instance_origin':inst['origin'],'part_coordinates_mm':p['nodes'][n]}
        emit('*ELEMENT,TYPE=C3D4',inst['origin'])
        for eid, effective in em.items():
            emit(str(effective)+','+','.join(str(nm[n]) for n in p['elements'][eid]),p['locations']['elements'][eid])
            lineage['elements'][str(effective)] = {**p['locations']['elements'][eid],'part':pname,'instance':name,'local_id':eid,
                                                   'local_connectivity':p['elements'][eid], 'instance_origin':inst['origin']}
        for card,table,keys,mapping,kind in [('NSET',ns,nkeys,nm,'nsets'),('ELSET',es,ekeys,em,'elsets')]:
            for label, members in table.items():
                if not members: _fail({'origin':inst['origin']},'빈 상속 집합입니다')
                key=keys[label]; origins=p['locations'][kind].get(label,[inst['origin']])
                lineage[kind][key].update(origins=origins,instance=name,part=pname,local_ids=sorted(members),
                                          effective_ids=sorted(mapping[n] for n in members))
                emit('*'+card+','+card+'='+key,origins[0])
                values=sorted(mapping[n] for n in members)
                for i in range(0,len(values),16): emit(','.join(map(str,values[i:i+16])),origins[0])
        # Local section and surface targets stay in their own instance.
        inherited_surfaces={b['options'].get('NAME') for b in parts[pname]['blocks'] if b['card']=='SURFACE'}
        surface_seen=set()
        for b in parts[pname]['blocks']+inst['blocks']:
            c,o=b['card'],b['options']
            if c=='SOLID SECTION':
                label=_label(o.get('ELSET'),b); material=_label(o.get('MATERIAL'),b)
                if label not in ekeys: _fail(b,'section의 local ELSET이 없습니다')
                if any(row['text'].strip(',').strip() for row in b['rows']): _fail(b,'추가 section data는 미지원입니다')
                emit('*SOLID SECTION,ELSET='+ekeys[label]+',MATERIAL='+material,b['origin'])
            elif c=='SURFACE':
                label=_label(o.get('NAME'),b)
                if label in surface_seen: _fail(b,'같은 scope의 면을 중복 정의할 수 없습니다')
                surface_seen.add(label)
                if o.get('TYPE')!='ELEMENT': _fail(b,'ELEMENT 요소면만 지원합니다')
                key=setname('surfaces',scope,label); faces=[]
                emit('*SURFACE,NAME='+key+',TYPE=ELEMENT',b['origin'])
                for row in b['rows']:
                    fields=[t.strip().upper() for t in row['text'].split(',')]
                    if len(fields)!=2 or not re.fullmatch('S[1-4]',fields[1]): _fail(row,'C3D4 S1~S4의 정확한 요소면을 지정하세요')
                    target,side=fields
                    members={_id(target,row)} if target.isdigit() else es.get(target,set())
                    if not members or set(members)-em.keys(): _fail(row,'없는 local element/ELSET 면입니다')
                    for eid in sorted(members): emit(f'{em[eid]},{side}',row['origin']); faces.append([em[eid],side])
                if not faces: _fail(b,'빈 면입니다')
                lineage['surfaces'][key].update(origins=[b['origin']],instance=name,part=pname,faces=faces)

    assembly_sets={'NSET':{},'ELSET':{}}
    assembly_keys={'NSET':{},'ELSET':{}}
    def resolve_target(token,kind,b,instance_name=None):
        if instance_name:
            if instance_name not in catalogs: _fail(b,'없는 INSTANCE 집합입니다')
            names=[instance_name,token]
        else:
            names=token.split('.')
            if names and names[0]==assembly: names=names[1:]
        if len(names)==1:
            if names[0] in assembly_sets[kind]: return set(assembly_sets[kind][names[0]])
            _fail(b,'assembly 대상은 이전 집합 또는 instance.localID/집합의 완전한 이름이어야 합니다')
        if len(names)!=2 or names[0] not in catalogs: _fail(b,'정확한 instance 대상이 없습니다')
        cat=catalogs[names[0]]; mapping=cat['nm' if kind=='NSET' else 'em']; table=cat['ns' if kind=='NSET' else 'es']
        if names[1].isdigit(): values={_id(names[1],b)}
        else: values=table.get(names[1],set())
        if not values or set(values)-mapping.keys(): _fail(b,'없는 instance localID/집합 참조입니다')
        return {mapping[n] for n in values}
    for b in assembly_blocks:
        c,o=b['card'],b['options']
        if c in ('NSET','ELSET'):
            label=_label(o.get(c),b); name=o.get('INSTANCE')
            if name is not None: _label(name,b)
            members=set(); _members(b,members,{}, {}, lambda token,row:resolve_target(token,c,row,name))
            assembly_sets[c].setdefault(label,set()).update(members)
            key=setname('nsets' if c=='NSET' else 'elsets',assembly,label)
            assembly_keys[c][label]=key
            entry=lineage['nsets' if c=='NSET' else 'elsets'][key]
            entry['origins'].append(b['origin']);entry['effective_ids']=sorted(assembly_sets[c][label])
            emit('*'+c+','+c+'='+key,b['origin'])
            values=sorted(members)
            for i in range(0,len(values),16):emit(','.join(map(str,values[i:i+16])),b['origin'])
        else:
            label=_label(o.get('NAME'),b)
            if o.get('TYPE')!='ELEMENT':_fail(b,'assembly 면은 TYPE=ELEMENT만 지원합니다')
            qualified=assembly+'.'+label
            if any(v['qualified']==qualified for v in lineage['surfaces'].values()):_fail(b,'중복 assembly 면입니다')
            key=setname('surfaces',assembly,label);faces=[]
            emit('*SURFACE,NAME='+key+',TYPE=ELEMENT',b['origin'])
            for row in b['rows']:
                fields=[t.strip().upper() for t in row['text'].split(',')]
                if len(fields)!=2 or not re.fullmatch('S[1-4]',fields[1]):_fail(row,'정확한 C3D4 요소면이 필요합니다')
                for eid in sorted(resolve_target(fields[0],'ELSET',row)):
                    emit(f'{eid},{fields[1]}',row['origin']);faces.append([eid,fields[1]])
            if not faces:_fail(b,'빈 assembly 면입니다')
            lineage['surfaces'][key].update(origins=[b['origin']],faces=faces)
    for b in global_blocks:
        c,o=b['card'],b['options']
        if c=='BOUNDARY':
            emit('*BOUNDARY',b['origin'])
            for row in b['rows']:
                fields=[t.strip().upper() for t in row['text'].split(',')]
                if not 2<=len(fields)<=4:_fail(row,'고정 병진 BOUNDARY data를 확인하세요')
                ids=resolve_target(fields[0],'NSET',row)
                for n in sorted(ids):emit(str(n)+','+','.join(fields[1:]),row['origin'])
                lineage['conditions'].append({'kind':'BOUNDARY','target':fields[0],'effective_node_ids':sorted(ids),'origin':row['origin']})
        else:
            if c=='MATERIAL':lineage['materials'][_label(o.get('NAME'),b)]={'origin':b['origin']}
            emit('*'+c+''.join(','+k+'='+str(v) for k,v in o.items()),b['origin'])
            for row in b['rows']:emit(row['text'],row['origin'])
    compiled='\n'.join(output)+'\n'
    if len(compiled.encode('ascii'))>MAX_BYTES:raise SourceError('계층 compile 산출물이 6 MiB를 초과합니다')
    model=parse_inp(compiled,compile_map)
    # Existing parser validates physical assignments and fixed DOFs. Preserve its result.
    model.update(lineage=lineage,compiled_text=compiled,compile_map=compile_map)
    return model


def target_key(model, kind, qualified):
    """Map a visible original qualified label to exactly one compiled key."""
    if kind not in ('nsets','elsets','surfaces'):raise ValueError('집합 종류를 확인하세요')
    matches=[key for key,row in model.get('lineage',{}).get(kind,{}).items() if row['qualified']==qualified.upper()]
    if len(matches)!=1:raise ValueError('정확히 하나의 원 instance 집합을 선택하세요')
    return matches[0]


def exact_entity(model, association, instance, local_id):
    if association not in ('POINTS','CELLS') or type(local_id) is not int:
        raise ValueError('원 절점/요소와 정수 local ID를 지정하세요')
    table=model.get('lineage',{}).get('nodes' if association=='POINTS' else 'elements',{})
    matches=[int(key) for key,row in table.items() if row['instance']==instance.upper() and row['local_id']==local_id]
    if len(matches)!=1:raise ValueError('instance/local ID 대응이 없거나 모호합니다')
    return matches[0]
