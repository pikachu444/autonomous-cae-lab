"""Exact B-only card additions after the existing A physical postflight.

The admitted original LAW36, property, mesh, units and rate recipe are retained.
No native acceptance is inferred from successful serialization.
"""
from copy import deepcopy
import hashlib
import re
from . import impact_bulk
from .adapters.impact_admission import cards, _int, _real, _same
from .storage import canonical_hash


def real(value):
    result = f'{float(value):20.12e}'
    if len(result) != 20 or not __import__('math').isfinite(float(value)):
        raise ValueError('Native real field exceeds its finite 20-column format')
    return result


def integer(value):
    if type(value) is not int or not 0 <= value <= 999999999:
        raise ValueError('Native integer field exceeds bounds')
    return f'{value:10d}'


def append_before_end(text, addition):
    found = list(re.finditer(r'(?m)^/END[ \t]*\r?$', text))
    if len(found) != 1:
        raise ValueError('Exactly one native /END is required')
    at = found[0].start()
    return text[:at] + addition + text[at:]


def replace_blocks(text, replacements):
    spans = list(re.finditer(r'(?m)^/[^\r\n]+', text)); found = set()
    for i in reversed(range(len(spans))):
        span = spans[i]; key = span.group().strip()
        if key in replacements:
            found.add(key)
            end = spans[i+1].start() if i+1 < len(spans) else len(text)
            text = text[:span.start()] + replacements[key] + text[end:]
    if found != set(replacements):
        raise ValueError('An exact native replacement target is missing')
    return text


def inievo_card(mid, table_id, law):
    """Exact radioss2022 CFG, including the 40-column blank before FAILIP."""
    ini, evo = law['initiation'], law['evolution']
    return '\n'.join([f'/FAIL/INIEVO/{mid}',
        integer(1)+integer(0)+integer(0)+' '*40+integer(evo['failip'])+real(0),
        ''.join(integer(v) for v in (1,2,1,1)),
        integer(table_id)+real(ini['sr_ref_s_inv'])+real(1)+real(0),
        integer(0)+real(1)+real(1),
        real(0)+real(1)+real(evo['gf_n_mm'])])+'\n'


def initiation_cards(table_id, function_ids, law):
    """TABLE/1 eta first, normalized EPSD second; linear native interpolation.

    A function ID and a TABLE ID share a namespace. No invisible extra axes.
    """
    ini = law['initiation']; rates = ini['rates_s_inv']
    text = f'/TABLE/1/{table_id}\nB_INIT_{table_id}\n'+integer(2 if rates else 1)+'\n'
    if not rates:
        return text+''.join(real(x)+real(y)+'\n' for x,y in zip(ini['eta'],ini['plastic_strain'][0]))
    for fid, rate in zip(function_ids,rates):
        text += integer(fid)+' '*10+real(rate/ini['sr_ref_s_inv'])+' '*40+real(1)+'\n'
    for fid, values in zip(function_ids,ini['plastic_strain']):
        text += f'/FUNCT/{fid}\nB_INIT_RATE_{fid}\n'
        text += ''.join(real(x)+real(y)+'\n' for x,y in zip(ini['eta'],values))
    return text


def _allocator(blocks):
    # Conservative common namespace avoids collisions even with unrelated cards.
    used = {int(k.split('/')[-1]) for k in blocks if k.split('/')[-1].isdigit()}
    candidate = max(used | {0})+1
    def allocate():
        nonlocal candidate
        value = candidate; integer(value); candidate += 1
        return value
    return allocate


def _bulk_assignment(blocks, model):
    result = {}
    for key, rows in blocks.items():
        if not key.startswith('/BRICK/'):
            continue
        part = int(key.rsplit('/',1)[1]); part_rows = blocks.get('/PART/'+str(part), [])
        if len(part_rows) != 2:
            raise ValueError('Native bulk part assignment is missing')
        prop, mid = _int(part_rows[1][:10]), _int(part_rows[1][10:20])
        values = [int(line[i:i+10]) for line in rows for i in range(0,len(line),10) if line[i:i+10].strip()]
        if len(values)%9:
            raise ValueError('Truncated native BRICK assignment')
        for at in range(0,len(values),9):
            eid, conn = values[at], values[at+1:at+9]
            if eid in result or eid not in model['elements'] or conn != model['elements'][eid]['nodes']:
                raise ValueError('Native BRICK identity/connectivity differs from the admitted input')
            result[eid] = {'material_id':mid,'part_id':part,'property_id':prop}
    return result


def apply(text, model, laws):
    """Return new text and reproducible receipt; never mutates the caller's model."""
    impact_bulk.validate(model,laws); before = cards(text)
    if any(k.startswith('/FAIL/') for k in before):
        raise ValueError('B insertion requires an admitted source without pre-existing failure cards; no double failure')
    alloc = _allocator(before); assignment = _bulk_assignment(before,model)
    additions = ''; elements = {}; materials = {}; protected = {}
    for law in laws:
        name = law['material']; eids = sorted(e for e,m in model['assignment'].items() if m==name)
        mids = {assignment[e]['material_id'] for e in eids}
        for mid in sorted(mids):
            keys = [k for k in before if k in (f'/MAT/LAW36/{mid}',f'/MAT/PLAS_TAB/{mid}')]
            if len(keys) != 1:
                raise ValueError('Exact native LAW36 assignment is missing')
            key = keys[0]; rows = before[key]
            if len(rows) != 8 or rows[0].strip().upper() != name:
                raise ValueError('The preserved single-curve LAW36 format changed')
            if _int(rows[3][:10]) != 1 or _int(rows[3][10:20]) or any(_real(rows[3][i:i+20]) for i in (20,40,60,80)):
                raise ValueError('First LAW36 path preserves NRATE=1, Fsmooth=0, VP=0 and no modifiers')
            if any(_real(rows[2][i:i+20]) for i in (40,60,80)):
                raise ValueError('LAW36 own failure cutoffs must remain disabled; INIEVO is separate')
            _same(_real(rows[7]),1)
            source_function = _int(rows[5][:10]); source_key = '/FUNCT/'+str(source_function)
            if source_key not in before:
                raise ValueError('Original LAW36 hardening function is missing')
            protected[key] = deepcopy(rows); protected[source_key] = deepcopy(before[source_key])
            table = alloc(); functions = [alloc() for _ in law['initiation']['rates_s_inv']]
            additions += initiation_cards(table,functions,law)+inievo_card(mid,table,law)
            materials[str(mid)] = {'material':name,'law':deepcopy(law),'table_id':table,'function_ids':functions,
                'hardening':'preserved original single curve; no hardening-rate interpolation',
                'rate_dispatch':impact_bulk.RATE_KIND,'VP':0,'Fsmooth':0,'NRATE':1,
                'initiation_native_axes':['clipped eta']+(['EPSD/SR_REF; no eta-style clamp in fail_inievo_s'] if functions else []),
                'native_temperature_axis':False,'table_outside_domain':'native TABLE_VINTERP; out-of-grid calibration UNKNOWN; no calibrated extrapolation claim',
                'source_law_sha256':canonical_hash(rows)}
        for eid in eids:
            bound = assignment[eid]; prop_key='/PROP/SOLID/'+str(bound['property_id'])
            rows = before.get(prop_key,[])
            if len(rows)!=5 or [_int(rows[1][i:i+10]) for i in range(0,80,10)] != [24,-1,0,-1,2,0,3,-1]:
                raise ValueError('Actual converted PROP/SOLID is not the preserved Isolid24 HEPH one-IP recipe')
            protected[prop_key]=deepcopy(rows)
            elements[str(eid)] = {**bound,'material':name,'law':'LAW36_INIEVO',
                'source_element_type':model['elements'][eid]['type'],
                'native_formulation':'HEPH_Isolid24','ip_count':1,'failip':1,'ilen':0,
                **impact_bulk.initial_geometry(model,eid)}
    effective = append_before_end(text,additions) if additions else text
    generated = {k:v for k,v in cards(effective).items() if k not in before}
    receipt = {'version':1,'source_commit':impact_bulk.PIN,'materials':materials,'elements':elements,
        'generated_cards':generated,'protected_cards':protected,
        'source_sha256':hashlib.sha256(text.encode('ascii')).hexdigest(),
        'definition_sha256':canonical_hash(laws),'native_acceptance':'NOT_RUN',
        'damage_dissipation':'UNKNOWN; never total internal-energy difference'}
    verify(effective,model,laws,receipt)
    return effective,receipt


def verify(text,model,laws,receipt):
    impact_bulk.validate(model,laws); blocks=cards(text)
    if canonical_hash(laws)!=receipt['definition_sha256']:
        raise ValueError('Bulk definition changed after native compilation')
    for key,expected in {**receipt['protected_cards'],**receipt['generated_cards']}.items():
        if blocks.get(key)!=expected:
            raise ValueError('Bulk native card changed: '+key)
    expected_fail = {'/FAIL/INIEVO/'+mid for mid in receipt['materials']}
    if {k for k in blocks if k.startswith('/FAIL/')} != expected_fail:
        raise ValueError('Failure cards must apply exactly to the selected bulk materials, never LAW117')
    assignment=_bulk_assignment(blocks,model)
    for eid,original in receipt['elements'].items():
        if assignment.get(int(eid))!={k:original[k] for k in ('material_id','part_id','property_id')}:
            raise ValueError('Bulk failure material/part/property coverage changed')


BRICK_TOKENS = ('OFF','DAMA','PLAS','IE','VOL','SX','SY','SZ','SXY','SYZ','SXZ','PLSR')
PAIR_TOKENS = ('FNX','FNY','FNZ','FTX','FTY','FTZ')


def add_output_cards(text, bulk, settings, model):
    """Native IDs are obtained from exact admitted cards, not UI list ordinals."""
    blocks=cards(text); allocate=_allocator(blocks); additions=''; groups=[]
    # One source element/member per group avoids unproved multi-IP reductions.
    for eid,element in sorted(bulk.get('elements',{}).items(),key=lambda kv:int(kv[0])):
        gid=allocate(); title=f'B_BULK_{eid}'
        additions+=f'/TH/BRIC/{gid}\n{title}\n'
        for start in range(0,len(BRICK_TOKENS),10):
            additions+=''.join(f'{v:<10}' for v in BRICK_TOKENS[start:start+10])+'\n'
        additions+=integer(int(eid))+' '*10+f'ELEMENT_{eid}'+'\n'
        groups.append({'id':gid,'type':1,'kind':'bulk','title':title,'members':[int(eid)],
                       'tokens':list(BRICK_TOKENS),'ip_scope':'native HEPH single material IP; no generic reduction',
                       'material_id':element['material_id']})
    for index,pair in enumerate(settings.get('contacts',[]),1):
        matched=[(k,r) for k,r in blocks.items() if k.startswith('/INTER/TYPE24/') and r and r[0].strip().upper()=='IMPACT'+str(index)]
        if len(matched)!=1:
            raise ValueError('Exact TYPE24 pair identity is missing')
        key,rows=matched[0]; ident=int(key.rsplit('/',1)[1]); gid=allocate(); title=f'B_PAIR_{ident}'
        additions+=f'/TH/INTER/{gid}\n{title}\n'+''.join(f'{v:<10}' for v in PAIR_TOKENS)+'\n'+integer(ident)+'\n'
        groups.append({'id':gid,'type':101,'kind':'pair','title':title,'members':[ident],
                       'tokens':list(PAIR_TOKENS),'pair':deepcopy(pair),'contact_index':index-1,
                       'normal_tangent':'signed components, global axes, not sum of absolute values',
                       'native_store_semantics':'UNVERIFIED_FSAV_FORCE_OR_IMPULSE',
                       'converter_source_commit':'NOT_PROVEN_BY_RELEASE'})
    effective=append_before_end(text,additions) if additions else text
    generated={k:v for k,v in cards(effective).items() if k not in blocks}
    return effective,{'groups':groups,'generated_cards':generated,'unavailable':['bulk_damage_dissipation','native_temperature_failure_axis','TYPE24_SFW','TYPE24_CE_DAMP']}
