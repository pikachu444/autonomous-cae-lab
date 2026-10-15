"""Pinned Radioss TFILE/4 readback, with transactional completed-prefix recovery.

HIST1/HIST2 framing is read directly. Converter headers or floating-point output
are not used to guess native variable IDs, member order, clocks, or pair units.
Generic retained-file pin helpers are reused; no CalculiX parser is imported.
"""
from copy import deepcopy
import math
from pathlib import Path
import struct
from .dynamic_result_store import file_pin, verify_pin
from .execution_control import check_cancelled

MAX_FILE = 2*1024**3
MAX_RECORD = 64*1024**2
MAX_ITEMS = 1000000


class InvalidRecord(ValueError):
    pass


class Records:
    def __init__(self, stream):
        self.stream = stream

    def read(self, size, eof=False):
        if not 0 <= size <= MAX_RECORD:
            raise InvalidRecord('Native record width exceeds bounds')
        head = self.stream.read(4)
        if not head and eof:
            return None
        if len(head)!=4:
            raise InvalidRecord('Truncated native record header')
        width=struct.unpack('>I',head)[0]
        if width!=size:
            raise InvalidRecord('Native record width differs')
        data=self.stream.read(width); tail=self.stream.read(4)
        if len(data)!=width or tail!=head:
            raise InvalidRecord('Truncated or mismatched native record trailer')
        return data

    def ints(self,count):
        return list(struct.unpack('>'+str(count)+'i',self.read(count*4)))

    def floats(self,count):
        return list(struct.unpack('>'+str(count)+'f',self.read(count*4)))


def bounded(value):
    if not 0 <= value <= MAX_ITEMS:
        raise ValueError('Native history count exceeds bounds')
    return value


def _text(data):
    try:
        result=data.decode('ascii').rstrip(' \x00')
    except UnicodeDecodeError as error:
        raise ValueError('Native title is not supported ASCII') from error
    if '\x00' in result or '\n' in result or '\r' in result:
        raise ValueError('Malformed native title')
    return result


def _layout(records):
    first=records.read(84); code=struct.unpack_from('>i',first)[0]
    if code not in (3040,3041,4021):
        raise ValueError('Unsupported TFILE/4 format code')
    title_width={3040:40,3041:80,4021:100}[code]
    records.read(80); units=None
    if code==4021:
        if records.ints(1)!=[2] or records.ints(1)!=[title_width]:
            raise ValueError('Native extra-header format differs')
        units=records.floats(3)
        if not all(math.isfinite(v) and v>0 for v in units):
            raise ValueError('Native unit declarations are invalid')
    nparts,nmaterials,nproperties,nsubsets,ngroups,nglobals=records.ints(6)
    for v in (nparts,nmaterials,nproperties,nsubsets,ngroups,nglobals):
        bounded(v)
    if nglobals!=23 or records.ints(nglobals)!=list(range(1,24)):
        raise ValueError('Exact native global membership is required')
    parts=[]
    for _ in range(nparts):
        r=records.read(20+title_width); ident=struct.unpack_from('>i',r)[0]
        title=_text(r[4:4+title_width]); material,prop,subset,width=struct.unpack_from('>4i',r,4+title_width)
        bounded(width)
        parts.append({'id':ident,'title':title,'material_id':material,'property_id':prop,
                      'subset_id':subset,'variables':records.ints(width) if width else []})
    for _ in range(nmaterials+nproperties):
        records.read(4+title_width)
    subsets=[]
    for _ in range(nsubsets):
        r=records.read(20+title_width); ident,parent,children,members,width=struct.unpack_from('>5i',r)
        for v in (children,members,width):
            bounded(v)
        lists=[records.ints(v) if v else [] for v in (children,members,width)]
        subsets.append({'id':ident,'parent_id':parent,'title':_text(r[20:]),
                        'children':lists[0],'members':lists[1],'variables':lists[2]})
    groups=[]
    for _ in range(ngroups):
        r=records.read(20+title_width); ident,kind,subtype,members,width=struct.unpack_from('>5i',r)
        bounded(members); bounded(width); bounded(members*width)
        if not members or not width:
            raise ValueError('Zero-width native groups are not admitted')
        member_rows=[]
        for _ in range(members):
            m=records.read(4+title_width)
            member_rows.append({'id':struct.unpack_from('>i',m)[0],'title':_text(m[4:])})
        if len({m['id'] for m in member_rows})!=members:
            raise ValueError('Duplicate native member identity')
        groups.append({'id':ident,'type':kind,'subtype':subtype,'title':_text(r[20:]),
                       'members':member_rows,'variables':records.ints(width)})
    if len({g['id'] for g in groups})!=len(groups):
        raise ValueError('Duplicate native history group identity')
    return {'format_code':code,'unit_factors':units,'parts':parts,'subsets':subsets,'groups':groups,
            'global_ids':list(range(1,24)),'header_end_byte':records.stream.tell()}


def _titles(path, groups):
    if path.stat().st_size>MAX_RECORD:
        raise ValueError('Native titles exceed bounds')
    lines=path.read_text(encoding='ascii').splitlines(); offset=0
    for group in groups:
        titles=[]
        for _ in group['members']:
            member=[]
            for _ in group['variables']:
                if offset+2>len(lines):
                    raise ValueError('Native _TITLES is truncated')
                try:
                    kind=int(lines[offset])
                except ValueError as error:
                    raise ValueError('Malformed native title type') from error
                token=lines[offset+1].strip(); offset+=2
                if kind!=group['type'] or not token or len(token)>10:
                    raise ValueError('Native title type/token differs')
                member.append(token)
            titles.append(member)
        if any(member!=titles[0] for member in titles[1:]) or len(set(titles[0]))!=len(titles[0]):
            raise ValueError('Native group has ambiguous variable titles')
        group['tokens']=titles[0]
    if offset!=len(lines):
        raise ValueError('Unmatched extra native title records')


def read(path, *, titles=None, failed=False, expected_pin=None):
    """Read whole samples only. A corrupt tail cannot discard a verified prefix.

    Header corruption cannot be recovered by searching for plausible numbers.
    Nonfinite channel values retain masks; malformed clocks terminate the prefix.
    No converter or executable resolution occurs here.
    """
    path=Path(path).absolute(); root=path.parent
    pin=expected_pin or file_pin(root,path)
    if pin['relative']!=path.name or not 0<pin['bytes']<=MAX_FILE:
        raise ValueError('Native history path/size differs')
    verify_pin(root,pin); title_pin=None
    if titles is not None:
        titles=Path(titles).absolute()
        title_pin=file_pin(titles.parent,titles)
    samples=[]; excluded=[]
    with path.open('rb') as stream:
        r=Records(stream); layout=_layout(r)
        if titles is not None:
            _titles(titles,layout['groups'])
        part_width=sum(len(g['variables']) for g in layout['parts'])
        subset_width=sum(len(g['variables']) for g in layout['subsets'])
        for width in (part_width,subset_width):
            bounded(width)
        while True:
            check_cancelled(); begin=stream.tell()
            try:
                clock=r.read(4,eof=True)
                if clock is None:
                    break
                time=struct.unpack('>f',clock)[0]
                if not math.isfinite(time) or time<0 or samples and time<=samples[-1]['time_s']:
                    raise InvalidRecord('Nonfinite, negative, duplicate or reversed native time')
                if len(samples)>=MAX_ITEMS:
                    raise ValueError('Native sample count exceeds bounds')
                globals_=r.floats(23)
                parts=r.floats(part_width) if part_width else []
                subsets=r.floats(subset_width) if subset_width else []
                group_values={}
                for group in layout['groups']:
                    group_values[str(group['id'])]=r.floats(len(group['members'])*len(group['variables']))
                # Commit only after every record in this time step is complete.
                samples.append({'source_row':len(samples),'time_s':time,
                    'byte_range':[begin,stream.tell()],'globals':globals_,'parts':parts,
                    'subsets':subsets,'groups':group_values})
            except InvalidRecord as error:
                if not failed:
                    raise
                excluded.append({'source_row':len(samples),'byte_range':[begin,pin['bytes']],
                    'time_s':None,'reason':str(error),'scope':'uncommitted_tail','reconnected':False})
                break
    verify_pin(root,pin)
    if title_pin:
        verify_pin(titles.parent,title_pin)
    # JSON must not contain NaN/Inf. Original bytes/tokens remain pinned.
    def clean(values):
        return [v if math.isfinite(v) else None for v in values]
    for sample in samples:
        for field in ('globals','parts','subsets'):
            sample[field]=clean(sample[field])
        sample['groups']={k:clean(v) for k,v in sample['groups'].items()}
    return {'layout':layout,'samples':samples,'excluded':excluded,'source_pin':pin,
            'titles_pin':title_pin,'prefix_status':'VERIFIED_COMPLETE_PREFIX' if excluded else 'VERIFIED_RETAINED_RECORDS',
            'failed_source':bool(failed),'full_requested_history':False if failed or excluded else 'UNKNOWN',
            'clock':'NATIVE_BINARY32_ACTUAL_TIME','converter_used':False}


def bind(history, output_receipt):
    """Bind generated output group -> raw group -> native member -> title/index."""
    units=history['layout']['unit_factors']
    if units is not None and any(not math.isclose(a,b,rel_tol=2e-7) for a,b in zip(units,(1000.,.001,1.))):
        raise ValueError('B readback requires the retained Mg/mm/s native unit factors')
    found={g['id']:g for g in history['layout']['groups']}; bound=[]
    for expected in output_receipt['groups']:
        group=found.get(expected['id'])
        if (group is None or group['type']!=expected['type'] or group['title']!=expected['title']
                or [m['id'] for m in group['members']]!=expected['members']
                or set(group.get('tokens',[]))!=set(expected['tokens'])
                or len(set(group['variables']))!=len(group['variables'])
                or any(v<1 for v in group['variables'])):
            raise ValueError('Native TH group/type/member/token order differs from the exact B output receipt')
        bound.append({**deepcopy(expected),'requested_tokens':deepcopy(expected['tokens']),
                      'tokens':deepcopy(group['tokens']),'native_variable_ids':deepcopy(group['variables'])})
    return bound


def series(history, group, member, token):
    if member not in group['members'] or token not in group['tokens']:
        raise ValueError('Choose an exact native group member and token')
    index=group['members'].index(member)*len(group['tokens'])+group['tokens'].index(token)
    return [sample['groups'][str(group['id'])][index] for sample in history['samples']]


PAIR_CHANNELS=('FNX','FNY','FNZ','FTX','FTY','FTZ')


_UNIT_SEAL=object()


class _RetainedPairUnits:
    def __init__(self,metadata,*,_seal):
        if _seal is not _UNIT_SEAL:raise ValueError('Use the exact retained attempt unit verification')
        self.metadata=deepcopy(metadata)


def retained_pair_units(root,execution_pin,model,settings,runtime_identity):
    """Verify legacy TH units against this exact, already retained native attempt."""
    import json
    from .impact_native_io import read_bytes
    from .dynamic_result_store import admit_pin
    from .adapters.impact import starter_admission
    from .adapters.opencourant_runtime import WINDOWS_SOURCE,WINDOWS_FILES
    root=Path(root)
    def payload(pin):
        return read_bytes(admit_pin(root,pin),expected=pin,maximum=64*1024**2)
    original=json.loads(payload(execution_pin))
    if (not isinstance(runtime_identity,dict) or
        (runtime_identity.get('platform'),runtime_identity.get('source_tag'))!=('win64',WINDOWS_SOURCE) or
        runtime_identity.get('files')!=WINDOWS_FILES or original['diagnostics'].get('runtime')!=runtime_identity):
        raise ValueError('Legacy pair units require the exact retained fixed runtime')
    retained=original['retained_native'];inp=retained['input_artifacts']['input.json']
    if inp['relative']!='input.json' or json.loads(payload(inp))!=settings or settings['source']['units']!='Mg/mm/s':
        raise ValueError('Legacy pair units differ from the exact retained input')
    pins={name:retained['native_artifacts'][name] for name in ('native/impact_0000.out','native/impactT01','native/impactT01_TITLES')}
    for name,pin in pins.items():
        if pin['relative']!=name:raise ValueError('Legacy pair unit artifact identity differs')
        verify_pin(root,pin)
    checks=[v for v in original['checks'] if v.get('name')=='native_starter']
    actual=starter_admission(admit_pin(root,pins['native/impact_0000.out']),model)
    if len(checks)!=1 or checks[0]!=actual or actual.get('status')!='PASS' or actual.get('units')!='Mg/mm/s':
        raise ValueError('Legacy pair units require the actual matching native Starter unit check')
    # Recheck pins after parsing; caller strings and current locale never supply units.
    for pin in (execution_pin,inp,*pins.values()):verify_pin(root,pin)
    return _RetainedPairUnits({'basis':'EXACT_RETAINED_INPUT_AND_NATIVE_STARTER_UNITS',
        'units':'Mg/mm/s','execution_pin':deepcopy(execution_pin),'input_pin':deepcopy(inp),
        'native_pins':deepcopy(pins),'native_unit_check':deepcopy(actual),
        'producer_source_commit':WINDOWS_SOURCE},_seal=_UNIT_SEAL)


def pair_provenance(history,group,runtime_identity,unit_evidence=None):
    """Admit this raw interface buffer only for the traced, fixed producer."""
    from .adapters.opencourant_runtime import WINDOWS_SOURCE,WINDOWS_FILES
    if not isinstance(runtime_identity,dict) or (runtime_identity.get('platform'),runtime_identity.get('source_tag'))!=('win64',WINDOWS_SOURCE) or runtime_identity.get('files')!=WINDOWS_FILES:
        return None
    if group.get('type')!=101 or len(group.get('members',[]))!=1:
        return None
    if dict(zip(group.get('tokens',[]),group.get('native_variable_ids',[])))!={token:i+1 for i,token in enumerate(PAIR_CHANNELS)}:
        return None
    legacy_units=None
    if history['layout']['format_code']!=4021 or history['layout']['unit_factors'] is None:
        if history['layout']['format_code'] not in (3040,3041) or not isinstance(unit_evidence,_RetainedPairUnits):return None
        legacy_units=unit_evidence.metadata
        for key,pin in (('native/impactT01',history['source_pin']),('native/impactT01_TITLES',history.get('titles_pin'))):
            expected=legacy_units['native_pins'][key]
            if pin is None or expected['relative']!='native/'+pin['relative'] or any(pin[k]!=expected[k] for k in ('bytes','sha256')):return None
    return {'producer_source_commit':WINDOWS_SOURCE,'engine_sha256':WINDOWS_FILES['exec/engine_win64.exe'],
        **({'legacy_unit_evidence':deepcopy(legacy_units)} if legacy_units else {}),
        'native_store_semantics':'CUMULATIVE_SIGNED_CONTACT_IMPULSE','native_unit':'N s',
        'native_channel_ids':{token:i+1 for i,token in enumerate(PAIR_CHANNELS)},
        'pair_member_id':group['members'][0],'basis':'MODEL_GLOBAL',
        'sign':'native signed global components, no absolute value or user-side sign reversal',
        'normal_orientation':'surface-to-surface TYPE24: +FNI*N for surface1 main segments, -FNI*N for surface2 main segments',
        'tangent_orientation':'native sum of FXT/FYT/FZT main-contact contributions; not reoriented to a selected body',
        'aggregation':'one exact interface member; sum of its contact contributions, not all contacts',
        'accumulation':'FSAV += force * DT12; DT12=(DT1+DT2)/2; not cleared at TH output on writing rank',
        'clock':'TH records actual TT; requested output interval is not substituted',
        'force_transform':'DERIVED_SECANT_OF_NATIVE_IMPULSE; forward/backward endpoints and centered interior',
        'converter':'raw TFILE/4 reader bypasses converter; native impulse is never taken from converted FN/FT CSV',
        'converter_sha256':WINDOWS_FILES['exec/th_to_csv_win64.exe']}


def impulse_secants(times,values,*,source_rows=None,gap_before=None):
    """Output-supported signed mean force, never an instantaneous solver force."""
    if len(times)!=len(values) or any(not math.isfinite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('Actual impulse sample clocks must be finite and increasing')
    n=len(times);rows=list(range(n)) if source_rows is None else list(source_rows)
    gaps=[False]*n if gap_before is None else list(gap_before)
    if len(rows)!=n or len(gaps)!=n:raise ValueError('Impulse sample mask/row lengths differ')
    result=[];support=[]
    for i in range(n):
        a,b=(0,1) if i==0 else (n-2,n-1) if i==n-1 else (i-1,i+1)
        valid=n>=2 and all(type(value) in (int,float) and math.isfinite(value) for value in values[a:b+1])
        valid=valid and not any(gaps[a+1:b+1]) and all(y==x+1 for x,y in zip(rows[a:b],rows[a+1:b+1]))
        result.append((values[b]-values[a])/(times[b]-times[a]) if valid else None)
        support.append({'source_rows':rows[a:b+1],'time_interval_s':[times[a],times[b]]} if n>=2 else None)
    return result,support
