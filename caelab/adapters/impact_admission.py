"""Independent checks of the bounded INP converter's effective physical model.

Original conversion remains retained. Only global gravity is rewritten: the
upstream section targeting/skew construction does not preserve arbitrary XYZ.
"""
from collections import Counter
import math
import re
from pathlib import Path


def cards(text):
    result={}; key=None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'): continue
        if line.startswith('/'):
            key=line.strip()
            if key in result: raise ValueError('Duplicate native card '+key)
            result[key]=[]
        elif key: result[key].append(line)
    return result


def _int(value):
    return int(value.strip() or '0')


def _real(value):
    number=float(value.strip() or '0')
    if not math.isfinite(number): raise ValueError('Nonfinite effective card')
    return number


def _same(actual, expected):
    # Pinned converter formats material/input numbers with eight decimal digits.
    if not math.isclose(actual,expected,rel_tol=6e-8,abs_tol=1e-15):
        raise ValueError('Converted physical value differs from admitted input')


def global_gravity(text, gravity):
    blocks=cards(text)
    removed=[k for k in blocks if k.startswith('/GRAV/')]
    # Preserve the mandatory #RADIOSS STARTER first line and every untouched
    # card byte. The semantic reader intentionally discards comments; it must
    # never serve as a general native-deck serializer.
    matches=list(re.finditer(r'(?m)^/[^\r\n]+',text))
    spans=[(m.start(),matches[i+1].start() if i+1<len(matches) else len(text))
           for i,m in enumerate(matches) if m.group(0).strip().startswith('/GRAV/')]
    for start,stop in reversed(spans):text=text[:start]+text[stop:]
    function=max((int(k.split('/')[-1]) for k in blocks if k.startswith('/FUNCT/')),default=0)+1
    rows=[]
    def real(x):return f'{x:20.12e}'
    if any(gravity):
        rows += [f'/FUNCT/{function}','CAELab constant global gravity',
                 real(0)+real(1),real(1)+real(1)]
        for i,value in enumerate(gravity,1):
            if value:
                rows += [f'/GRAV/{i}','CAELab global '+ 'XYZ'[i-1],
                         f"{function:10d}{'XYZ'[i-1]:>10}{0:10d}{0:10d}{0:10d}{'':10}"+
                         real(1)+real(value)]
    end=re.search(r'(?m)^/END\s*$',text)
    if end is None:raise ValueError('Native Starter deck has no END card')
    output=text[:end.start()]+'\n'.join(rows)+'\n'+text[end.start():]
    return output,{'removed_gravity_cards':removed,
        'effective_global_mm_s2':list(gravity),'basis':'GLOBAL_XYZ','group':0}


def normalize_contact_friction(text,settings):
    """Repair only the pinned writer's width-10 spill into a width-20 field."""
    lines=text.splitlines(keepends=True);matches={}
    current=None
    for i,line in enumerate(lines):
        if line.startswith('/'):
            current=line.strip() if line.startswith('/INTER/TYPE24/') else None
            if current:matches[current]=[]
        elif current and line.strip() and not line.lstrip().startswith('#'):
            matches[current].append(i)
    for indexes in matches.values():
        if len(indexes)!=7:raise ValueError('Unexpected native contact layout')
        title=lines[indexes[0]].strip()
        known={f'IMPACT{i}':p for i,p in enumerate(settings['contacts'],1)}
        if title not in known:raise ValueError('Unknown effective contact')
        # Retain native pair IDs and every other option. Only field row4 is
        # regenerated because the upstream width error displaces later zeros.
        original=lines[indexes[4]].split()
        if len(original)!=4 or _real(original[0])!=0 or any(_real(v) for v in original[2:]):
            raise ValueError('Unrequested contact options')
        _same(_real(original[1]),known[title]['friction'])
        lines[indexes[4]]=f"{0:20d}{known[title]['friction']:20.12e}{'':20}{0:20d}{0:20d}\n"
    return ''.join(lines)


def validate_physics(text, model, initial, settings):
    b=cards(text)
    def family(prefix):
        return {int(key.rsplit('/',1)[1]):data for key,data in b.items() if key.startswith(prefix)}
    def ids(rows): return [int(row[i:i+10]) for row in rows for i in range(0,len(row),10) if row[i:i+10].strip()]
    parts=family('/PART/')
    element_parts={}
    for key,rows in b.items():
        if key.startswith(('/TETRA4/','/TETRA10/','/BRICK/')):
            width=11 if key.startswith('/TETRA10/') else 5 if key.startswith('/TETRA4/') else 9
            values=ids(rows)
            for offset in range(0,len(values),width):
                element_parts[values[offset]]=int(key.rsplit('/',1)[1])
    if set(element_parts)!=set(model['elements']): raise ValueError('Physical part coverage differs')
    materials={}
    for key,rows in b.items():
        if key.startswith(('/MAT/ELAST/','/MAT/PLAS_TAB/','/MAT/LAW59/')):
            ident=int(key.rsplit('/',1)[1])
            if ident in materials: raise ValueError('Duplicate material identity')
            materials[ident]=(key,rows)
    properties=family('/PROP/SOLID/')
    property_by_element={}
    for eid,part in element_parts.items():
        if part not in parts or len(parts[part])!=2:raise ValueError('Missing native part')
        prop=_int(parts[part][1][:10])
        if model['elements'][eid]['type']=='COH3D8':
            r=b.get('/PROP/TYPE43/'+str(prop),[])[1:]
            if len(r)!=1 or _int(r[0][:10])!=-1 or r[0][10:].strip():raise ValueError('Cohesive formulation changed')
            property_by_element[str(eid)]=prop
            continue
        r=properties.get(prop,[])[1:]
        if len(r)!=4:raise ValueError('Missing effective solid formulation')
        if [_int(r[0][i:i+10]) for i in range(0,80,10)]!=[24,-1,0,-1,2,0,3,-1]:
            raise ValueError('Effective solid formulation changed')
        _same(_real(r[0][80:100]),.1)
        for row,values in zip(r[1:3],[(1.1,.05,0,0,0),(0,.01,100,100,.01)]):
            for index,value in enumerate(values):_same(_real(row[index*20:(index+1)*20]),value)
        if [_int(r[3][i:i+10]) for i in (0,10,20)]!=[0,0,1]:raise ValueError('Distortion control changed')
        property_by_element[str(eid)]=prop
    material_names={}; assignments={}
    for eid,part in element_parts.items():
        if part not in parts or len(parts[part])!=2: raise ValueError('Missing part assignment')
        material=_int(parts[part][1][10:20])
        expected=model['assignment'][eid]
        if material in material_names and material_names[material]!=expected: raise ValueError('Merged different native materials')
        material_names[material]=expected; assignments[eid]=material
    for mid,name in material_names.items():
        if mid not in materials: raise ValueError('Unsupported/missing effective material')
        key,rows=materials[mid]; m=model['materials'][name]
        if rows[0].strip().upper()!=name: raise ValueError('Material title/assignment differs')
        if len(rows)<3: raise ValueError('Incomplete material')
        _same(_real(rows[1][:20]),m['DENSITY'][0][0])
        if m.get('_elastic_type')=='TRACTION':
            if '/LAW59/' not in key or len(rows)!=4:raise ValueError('Original cohesive law changed')
            _same(_real(rows[2][:20]),m['ELASTIC'][0][0])
            _same(_real(rows[2][20:40]),m['ELASTIC'][0][1])
            if rows[2][40:].strip() or any(_real(v) for v in rows[3].split()):raise ValueError('Unexpected cohesive options')
            continue
        _same(_real(rows[1][20:40]),0)
        _same(_real(rows[2][:20]),m['ELASTIC'][0][0])
        _same(_real(rows[2][20:40]),m['ELASTIC'][0][1])
        if 'PLASTIC' in m:
            if '/PLAS_TAB/' not in key or len(rows)!=8 or _int(rows[3][:10])!=1:
                raise ValueError('Plastic law/rate count changed')
            if any(_real(rows[2][i:i+20]) for i in (40,60,80)) or _int(rows[3][10:20]):
                raise ValueError('Unrequested material modifiers')
            if any(_real(rows[3][i:i+20]) for i in (20,40,60,80)):
                raise ValueError('Unrequested plastic options')
            if any(float(v) for v in rows[4].split()) or any(float(v) for v in rows[6].split()):
                raise ValueError('Unrequested material function scaling')
            function=_int(rows[5][:10])
            if rows[5][10:].strip() or float(rows[7].strip())!=1: raise ValueError('Unexpected rate definition')
            table=b.get('/FUNCT/'+str(function),[])[1:]
            if len(table)!=len(m['PLASTIC']): raise ValueError('Plastic table coverage differs')
            for row,(stress,strain) in zip(table,m['PLASTIC']):
                _same(_real(row[:20]),strain); _same(_real(row[20:40]),stress)
        elif '/ELAST/' not in key or len(rows)!=3:
            raise ValueError('Unexpected material law')
    tet={1:(0,2,1),2:(0,1,3),3:(1,2,3),4:(2,0,3)}
    hexa={1:(0,3,2,1),2:(7,4,5,6),3:(0,1,5,4),4:(1,2,6,5),5:(2,3,7,6),6:(3,0,4,7)}
    surfaces=family('/SURF/SEG/'); surface_names={}
    for sid,rows in surfaces.items():
        name=rows[0].strip().upper()
        if name not in model['surfaces'] or name in surface_names: raise ValueError('Unknown/duplicate surface')
        surface_names[name]=sid; expected=[]
        for target,side in model['surfaces'][name]:
            eids=[int(target)] if target.isdigit() else sorted(model['elsets'][target])
            for eid in eids:
                element=model['elements'][eid]
                order=(tet if element['type'].startswith('C3D4') or element['type']=='C3D10' else hexa)[int(side[1:])]
                expected.append(tuple(element['nodes'][n] for n in order))
        actual=[tuple(ids([row[10:]])) for row in rows[1:]]
        if Counter(actual)!=Counter(set(expected)): raise ValueError('Oriented native contact faces differ')
    if set(surface_names)!=set(model['surfaces']): raise ValueError('Missing native surface')
    pairs=family('/INTER/TYPE24/')
    if len(pairs)!=len(settings['contacts']): raise ValueError('Native contact count differs')
    for i,pair in enumerate(settings['contacts'],1):
        matches=[rows for rows in pairs.values() if rows[0].strip().upper()=='IMPACT'+str(i)]
        if len(matches)!=1: raise ValueError('Exact contact pair missing')
        r=matches[0][1:]
        if len(r)!=6 or _int(r[0][:10])!=surface_names[pair['b']] or _int(r[0][10:20])!=surface_names[pair['a']] or _int(r[0][20:30])!=4:
            raise ValueError('Native main/secondary contact sides changed')
        _same(_real(r[3][20:40]),pair['friction'])
        # All other template values are fixed by the admitted TYPE24 recipe.
        template=[
            f"{surface_names[pair['b']]:>10}{surface_names[pair['a']]:>10}         4                             0                   0",
            "         0                             0                   0                   0                   0",
            "                   0                   0         0         0                   0",
            None,
            "       000                             5                   0",
            "         0         0                   0                   0                                       0"]
        for actual,reference in zip(r,template):
            if reference is not None and actual.rstrip()!=reference.rstrip(): raise ValueError('Contact template changed')
        if any(_real(r[3][start:start+20]) for start in (0,40,60,80)):
            raise ValueError('Unrequested contact timing/stiffness')
    groups={}
    for key,rows in b.items():
        if key.startswith('/GRNOD/'):
            ident=int(key.rsplit('/',1)[1])
            if ident in groups: raise ValueError('Duplicate native node group')
            groups[ident]=(key.split('/')[2],ids(rows[1:]))
    brick_groups=family('/GRBRIC/BRIC/')
    def group(ident,trail=()):
        if ident in trail or ident not in groups: raise ValueError('Missing/cyclic node group')
        kind,values=groups[ident]
        if kind=='NODE': result=set(values)
        elif kind=='PART': result={n for e,p in element_parts.items() if p in values for n in model['elements'][e]['nodes']}
        elif kind=='SURF': result={n for sid in values for row in surfaces[sid][1:] for n in ids([row[10:]])}
        elif kind=='GRNOD': result=set().union(*(group(v,(*trail,ident)) for v in values))
        elif kind=='GRBRIC': result={n for v in values for e in ids(brick_groups[v][1:]) for n in model['elements'][e]['nodes']}
        else: raise ValueError('Unsupported native node group '+kind)
        if not result or result-model['nodes'].keys(): raise ValueError('Invalid native node group')
        return result
    expected_fixed=set()
    for block in model['blocks']:
        if block['card']=='BOUNDARY':
            for _,line in block['rows']:
                fields=[v.strip().upper() for v in line.split(',')]
                target={int(fields[0])} if fields[0].isdigit() else model['nsets'][fields[0]]
                lo=int(fields[1]);hi=int(fields[2]) if len(fields)>2 and fields[2] else lo
                expected_fixed.update((n,d) for n in target for d in range(lo,hi+1))
    fixed=set()
    for rows in family('/BCS/').values():
        if len(rows)!=2: raise ValueError('Unexpected native boundary')
        r=rows[1]
        if r[7:10]!='000' or _int(r[10:20]): raise ValueError('Unexpected rotational/local fixed boundary')
        if len(r[3:6])!=3 or set(r[3:6])-{'0','1'}: raise ValueError('Malformed fixed DOFs')
        fixed.update((n,i+1) for n in group(_int(r[20:30])) for i,v in enumerate(r[3:6]) if v=='1')
    if fixed!=expected_fixed: raise ValueError('Native fixed DOFs differ')
    velocities={}
    for rows in family('/INIVEL/TRA/').values():
        if len(rows)!=3: raise ValueError('Unexpected initial velocity card')
        r=rows[1]; v=[_real(r[i:i+20]) for i in (0,20,40)]
        if _int(r[70:80]) or any(float(x) for x in rows[2].split()): raise ValueError('Initial velocity frame/time changed')
        for n in group(_int(r[60:70])):
            if n in velocities: raise ValueError('Duplicate initial velocity assignment')
            velocities[n]=v
    if set(velocities)!=set(initial['velocities_mm_s']): raise ValueError('Initial velocity coverage differs')
    for n,values in velocities.items():
        for a,e in zip(values,initial['velocities_mm_s'][n]): _same(a,e)
    gravity=[0.,0.,0.]; seen=set()
    for rows in family('/GRAV/').values():
        if len(rows)!=2: raise ValueError('Malformed global gravity')
        row=rows[1]; direction=row[10:20].strip()
        if direction not in 'XYZ' or len(direction)!=1 or direction in seen:
            raise ValueError('Duplicate/invalid global gravity component')
        seen.add(direction)
        if any(_int(row[a:a+10]) for a in (20,30,40)) or _real(row[60:80])!=1:
            raise ValueError('Gravity must use global frame, global nodes and unit time scale')
        function=b.get('/FUNCT/'+str(_int(row[:10])),[])[1:]
        if len(function)!=2: raise ValueError('Gravity history changed')
        for actual,expected in zip(function,[(0,1),(1,1)]):
            for a,e in zip((_real(actual[:20]),_real(actual[20:40])),expected):_same(a,e)
        gravity['XYZ'.index(direction)]=_real(row[80:100])
    for actual,expected in zip(gravity,settings['gravity_mm_s2']): _same(actual,expected)
    return {'material_by_element':{str(e):model['assignment'][e] for e in element_parts},
        'part_by_element':{str(e):p for e,p in element_parts.items()},
        'property_by_element':property_by_element,
        'effective_formulation':{'Isolid':24,'Itetra4':3,'Itetra10':2,'Icontrol':1,
            'Abaqus_integration_equivalence':'NOT_CLAIMED'},'global_gravity_mm_s2':gravity,
        'fixed_dof_count':len(fixed),'velocity_node_count':len(velocities),'contact_count':len(pairs)}
