"""Independent checks of the bounded INP converter's effective physical model.

Original conversion remains retained. Bounded effective-deck corrections preserve
the admitted source physics and are independently checked below.
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
    # Blank physical lines are data in native cards (SURF reads them as zero
    # nodes). No replacement cards means no insertion, not an empty row.
    output=text
    if rows:
        newline='\r\n' if '\r\n' in text else '\n'
        output=text[:end.start()]+newline.join(rows)+newline+text[end.start():]
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



def _surface_faces(model,name):
    """Source-oriented corner union, before native four-node padding."""
    tet={1:(0,2,1),2:(0,1,3),3:(1,2,3),4:(2,0,3)}
    hexa={1:(0,3,2,1),2:(7,4,5,6),3:(0,1,5,4),4:(1,2,6,5),5:(2,3,7,6),6:(3,0,4,7)}
    if name not in model['surfaces']:raise ValueError('Unknown native surface')
    result=set()
    for target,side in model['surfaces'][name]:
        eids=[int(target)] if target.isdigit() else model['elsets'][target]
        for eid in eids:
            element=model['elements'][eid]
            order=(tet if element['type'] in ('C3D4','C3D10') else hexa)[int(side[1:])]
            result.add(tuple(element['nodes'][index] for index in order))
    return result


def _segment_nodes(row):
    """Strict effective native SEGid/N1/N2/N3/N4, five 10-wide integer fields."""
    if len(row)!=50 or any(not re.fullmatch(r' *[0-9]+',row[i:i+10]) for i in range(0,50,10)):
        raise ValueError('Surface segment requires five explicit 10-column integers')
    values=[int(row[i:i+10]) for i in range(0,50,10)]
    if any(v<=0 or v>2147483647 for v in values):raise ValueError('Surface segment identity is outside native integer range')
    nodes=tuple(values[1:])
    if nodes[2]==nodes[3] and len(set(nodes[:3]))==3:return values[0],nodes[:3]
    if len(set(nodes))==4:return values[0],nodes
    raise ValueError('Surface segment has an invalid repeated-node pattern')


def _surface_entries(lines):
    """Read physical surface rows; whitespace is not an ignorable comment."""
    entries={};current=None
    for index,line in enumerate(lines):
        if line.startswith('/'):
            current=line.strip() if line.startswith('/SURF/SEG/') else None
            if current:
                if current in entries:raise ValueError('Duplicate native surface')
                entries[current]=[]
        elif current:
            if not line.strip():
                raise ValueError('Blank physical surface row would define zero nodes')
            if not line.lstrip().startswith('#'):entries[current].append(index)
    return entries


def normalize_surfaces(text,model):
    """Correct only pinned converter SEG rows; original converted deck is retained.

    radioss110/SETS/surf.cfg declares SEGid,N1,N2,N3,N4 at width10.
    hm_read_surf repeats N3 for triangular N4=0. Write that repetition explicitly.
    """
    lines=text.splitlines(keepends=True);entries=_surface_entries(lines)
    seen=set();receipt={}
    for key,indexes in entries.items():
        if len(indexes)<2:raise ValueError('Empty native surface')
        name=lines[indexes[0]].strip().upper()
        if name in seen:raise ValueError('Duplicate native surface title')
        seen.add(name);expected=_surface_faces(model,name);actual=[];replacements=[]
        for ordinal,index in enumerate(indexes[1:],1):
            raw=lines[index].rstrip('\r\n')
            # The pinned writer leaves SEGid blank and emits either three or
            # four corners. Inspect fixed slots, not whitespace-split tokens.
            if len(raw) not in (40,50) or raw[:10].strip() and not raw[:10].strip().isdigit():
                raise ValueError('Unrecognized converter surface layout')
            slots=[raw[i:i+10] for i in range(10,len(raw),10)]
            if any(not re.fullmatch(r' *[0-9]+',v) or int(v)<=0 for v in slots):
                raise ValueError('Converted surface contains an empty/invalid corner')
            nodes=tuple(int(v) for v in slots)
            if len(nodes)==4 and nodes[-1]==nodes[-2]:nodes=nodes[:3]
            if len(set(nodes))!=len(nodes) or len(nodes) not in (3,4):
                raise ValueError('Converted surface corner multiplicity differs')
            actual.append(nodes)
            full=nodes if len(nodes)==4 else (*nodes,nodes[-1])
            formatted=''.join(f'{v:10d}' for v in (ordinal,*full))
            _,checked=_segment_nodes(formatted)
            if checked!=nodes:raise ValueError('Surface serialization changed orientation')
            replacements.append((index,formatted+('\r\n' if lines[index].endswith('\r\n') else '\n')))
        if Counter(actual)!=Counter(expected):raise ValueError('Oriented converter surface differs from input')
        for index,value in replacements:lines[index]=value
        receipt[key]={'name':name,'segment_count':len(actual),'triangle_N4':'repeat_N3','layout':'5I10'}
    if seen!=set(model['surfaces']):raise ValueError('Missing native surface')
    return ''.join(lines),receipt


def normalize_elastic_tetra4(text, model, initial, settings):
    """Use the existing native linear-tetra option only for default INP LAW1.

    Validate the complete original conversion first; never repair an unverified
    mesh/material assignment or override an explicitly selected formulation.
    """
    physics=validate_physics(text,model,initial,settings)
    blocks=cards(text);lines=text.splitlines(keepends=True);indexes={};current=None
    for i,line in enumerate(lines):
        if line.startswith('/'):
            current=line.strip();indexes[current]=[]
        elif current and line.strip() and not line.lstrip().startswith('#'):
            indexes[current].append(i)
    native_types={}
    for key,rows in blocks.items():
        for prefix,width in (('/TETRA4/',5),('/TETRA10/',11),('/BRICK/',9)):
            if key.startswith(prefix):
                values=[_int(row[i:i+10]) for row in rows for i in range(0,len(row),10) if row[i:i+10].strip()]
                for offset in range(0,len(values),width):
                    native_types[values[offset]]=prefix
    users={}
    for eid,prop in physics['property_by_element'].items():
        users.setdefault(prop,[]).append(int(eid))
    receipt={'origin':'INP_EFFECTIVE_DECK','basis':'EXISTING_NATIVE_ELASTIC_TETRA4_1000',
             'Abaqus_integration_equivalence':'NOT_CLAIMED','changed':[],'unchanged':[]}
    for prop,eids in sorted(users.items()):
        eids=sorted(eids);reason=None
        if any(model['elements'][e]['type']!='C3D4' or native_types.get(e)!='/TETRA4/' for e in eids):
            reason='PROPERTY_NOT_EXCLUSIVELY_ORIGINAL_C3D4'
        elif any('PLASTIC' in model['materials'][model['assignment'][e]] or
                 model['materials'][model['assignment'][e]].get('_elastic_type')=='TRACTION' for e in eids):
            reason='NOT_LINEAR_ELASTIC_LAW1'
        parts=sorted({physics['part_by_element'][str(e)] for e in eids})
        materials=sorted({_int(blocks['/PART/'+str(part)][1][10:20]) for part in parts})
        if reason is None and any('/MAT/ELAST/'+str(mid) not in blocks for mid in materials):
            reason='NOT_LINEAR_ELASTIC_LAW1'
        key='/PROP/SOLID/'+str(prop)
        if reason is None:
            row_index=indexes[key][1];row=lines[row_index]
            flags=[_int(row[i:i+10]) for i in range(0,80,10)]
            if flags!=[24,-1,0,-1,2,0,3,-1]:reason='FORMULATION_NOT_CONVERTER_DEFAULT'
        if reason:
            receipt['unchanged'].append({'property_id':prop,'element_ids':eids,'reason':reason})
            continue
        lines[row_index]=row[:60]+f'{1000:10d}'+row[70:]
        receipt['changed'].append({'property_id':prop,'part_ids':parts,'material_ids':materials,
            'element_ids':eids,'before':{'Itetra4':3},'after':{'Itetra4':1000},
            'reason':'Explicit existing native one-point linear tetra; automatic default is incompatible with resolved Ismstr=10/12'})
    return ''.join(lines),receipt


def validate_physics(text, model, initial, settings):
    _surface_entries(text.splitlines())
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
    property_by_element={}; strain_by_element={}; tetra_by_element={}
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
        flags=[_int(r[0][i:i+10]) for i in range(0,80,10)]
        # Keep old immutable attempts readable. New direct C3D4 inputs may
        # explicitly select geometric strain=2 instead of runtime automatic=-1.
        allowed=[[24,-1,0,-1,2,0,3,-1]]
        if model['elements'][eid]['type']=='C3D4':
            allowed.extend(([24,2,0,-1,2,0,3,-1],[24,-1,0,-1,2,0,1000,-1]))
        if flags not in allowed:
            raise ValueError('Effective solid formulation changed')
        strain_by_element[str(eid)]=flags[1]
        tetra_by_element[str(eid)]=flags[6]
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
    surfaces=family('/SURF/SEG/'); surface_names={}
    for sid,rows in surfaces.items():
        name=rows[0].strip().upper()
        if name not in model['surfaces'] or name in surface_names:raise ValueError('Unknown/duplicate surface')
        surface_names[name]=sid;actual=[];segments=set()
        for row in rows[1:]:
            segment,nodes=_segment_nodes(row)
            if segment in segments:raise ValueError('Duplicate native segment identity')
            segments.add(segment);actual.append(nodes)
            if any(n not in model['nodes'] for n in nodes):raise ValueError('Native surface node is absent')
        if Counter(actual)!=Counter(_surface_faces(model,name)):raise ValueError('Oriented native contact faces differ')
    if set(surface_names)!=set(model['surfaces']): raise ValueError('Missing native surface')
    pairs=family('/INTER/TYPE24/')
    if len(pairs)!=len(settings['contacts']): raise ValueError('Native contact count differs')
    for i,pair in enumerate(settings['contacts'],1):
        expected_title=model.get('native_contact_titles',{}).get(str(i),'IMPACT'+str(i))
        matches=[rows for rows in pairs.values() if rows[0].strip().upper()==expected_title]
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
        elif kind=='SURF': result={n for sid in values for row in surfaces[sid][1:] for n in _segment_nodes(row)[1]}
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
        'effective_formulation':{'Isolid':24,'Itetra4':next(iter(set(tetra_by_element.values()))) if len(set(tetra_by_element.values()))==1 else None,'Itetra10':2,'Icontrol':1,
            'Itetra4_by_element':tetra_by_element,
            'Ismstr_by_element':strain_by_element,
            'Abaqus_integration_equivalence':'NOT_CLAIMED'},'global_gravity_mm_s2':gravity,
        'fixed_dof_count':len(fixed),'velocity_node_count':len(velocities),'contact_count':len(pairs)}
