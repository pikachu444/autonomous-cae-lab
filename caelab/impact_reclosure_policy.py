"""Pinned LAW117-to-TYPE24 deletion gate; no clock surrogate or solver model."""
from copy import deepcopy
import hashlib
import math
import re
from .storage import canonical_hash
from .impact_bulk_deck import cards,integer,replace_blocks,append_before_end,_allocator
from .impact_damage import geometry

POLICY='DELETION_GATED_TYPE24'
TRACE='caelab_reclosure_trace.jsonl'
PHASE_ENV='CAELAB_RECLOSURE_PHASE'
SEGMENT_ENV='CAELAB_RECLOSURE_ENGINE_SEGMENT'
PIN='cb760c206e346eff12161a2268b134ef9d48a4ef'


def validate(model,settings):
    """One intact-initial cohesive, two adjacent bulk cells, one exact pair."""
    selected=[row for row in settings.get('interface_controls',[]) if row.get('reclosure')==POLICY]
    if not selected:return []
    if len(selected)!=1 or len(settings['interface_controls'])!=1 or len(settings.get('contacts',[]))!=1:
        raise ValueError('삭제 연동은 응집 요소 하나·벌크 이웃 둘·정확한 접촉쌍 하나입니다')
    row=selected[0];index=row['contact_index']
    if row['contact_start_s'] is not None or type(index) is not int or index!=0:
        raise ValueError('삭제 연동은 활성 시각 없이 정확한 접촉쌍을 선택하세요')
    if settings['source'].get('format')!='INP':raise ValueError('생성 삭제 센서는 검증된 INP 변환 경로에만 추가합니다')
    if settings['contacts'][0].get('law')!='TYPE24' or settings['contacts'][0]['friction']!=0:
        raise ValueError('첫 삭제 연동 경로는 원 마찰0 TYPE24를 보존합니다')
    eids=[e for e,name in model['assignment'].items() if name==row['material']]
    if len(eids)!=1 or len(model['elements'])!=3 or model['elements'][eids[0]]['type']!='COH3D8':
        raise ValueError('응집 요소 하나와 별도의 살아 있는 벌크 요소 둘을 선택하세요')
    eid=eids[0];geo=geometry(model,eid);neighbors=[]
    for side in ('lower_nodes','upper_nodes'):
        face=set(geo[side]);found=[e for e,c in model['elements'].items() if c['type']!='COH3D8' and face<=set(c['nodes'])]
        if len(found)!=1:raise ValueError('각 대응면에 정확한 벌크 이웃 하나가 필요합니다')
        neighbors.append(found[0])
    if len(set(neighbors))!=2:raise ValueError('서로 다른 벌크 이웃 둘이 필요합니다')
    return [{'control':deepcopy(row),'cohort':{'cohesive':eid,'lower_bulk':neighbors[0],'upper_bulk':neighbors[1]},'geometry':geo}]


def callback_source(receipt):
    """Only this template plus admitted integer IDs is approved for -python."""
    ids=receipt['cohort'];sid=receipt['sensor_id'];name=receipt['function_name']
    if any(type(v) is not int or v<=0 for v in [sid,*ids.values()]):raise ValueError('유효한 원 센서/요소 번호가 필요합니다')
    if name!='caelab_reclosure_'+str(sid) or receipt['trace_relative']!=TRACE:
        raise ValueError('고정 생성 함수명·상대 trace 경로만 허용합니다')
    # Literal OFF(id) references are discovered by the pinned native producer.
    return f'''def {name}(state):
    import os, json, math, sys
    state = state.setdefault('caelab_reclosure_{sid}', {{}})
    ordinal = state.get('ordinal', 0) + 1
    state['ordinal'] = ordinal
    phase = os.environ.get('{PHASE_ENV}', 'UNKNOWN')
    segment = os.environ.get('{SEGMENT_ENV}', 'UNKNOWN')
    if ordinal == 1:
        runtime = {{'version': sys.version, 'prefix': sys.prefix}}
        runtime['base_prefix'] = sys.base_prefix
        runtime['implementation'] = sys.implementation.name
        runtime['math_file'] = getattr(math, '__file__', None)
        runtime['math_origin'] = getattr(math.__spec__, 'origin', None)
        state['runtime'] = runtime
        state['runtime_ok'] = False
        try:
            import ctypes, hashlib
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            query = kernel.GetModuleFileNameW
            query.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
            query.restype = ctypes.c_uint
            buffer = ctypes.create_unicode_buffer(32768)
            size = query(ctypes.pythonapi._handle, buffer, len(buffer))
            if not 0 < size < len(buffer):
                raise OSError('GetModuleFileNameW:' + str(ctypes.get_last_error()))
            runtime['dll_path'] = os.path.realpath(buffer.value)
            def digest(path):
                with open(path, 'rb') as stream:
                    return hashlib.file_digest(stream, 'sha256').hexdigest()
            runtime['dll_sha256'] = digest(runtime['dll_path'])
            if runtime['math_file'] is not None:
                runtime['math_sha256'] = digest(runtime['math_file'])
            elif runtime['math_origin'] == 'built-in':
                runtime['math_sha256'] = None
            else:
                raise ValueError('math has no verified file or built-in origin')
            runtime['pointer_bits'] = ctypes.sizeof(ctypes.c_void_p) * 8
            state['runtime_ok'] = True
        except (AttributeError, OSError, TypeError, ValueError, ImportError) as error:
            state['runtime_error'] = type(error).__name__ + ':' + str(error)
    reason = 'WAITING_INITIAL_LIVE'
    coh = low = high = previous = clock = step = None
    try:
        coh, low, high = OFF({ids['cohesive']}), OFF({ids['lower_bulk']}), OFF({ids['upper_bulk']})
        previous = sensors[{sid}]['status']
        clock, step = TIME, DT
    except (NameError, KeyError, TypeError) as error:
        reason = 'MISSING_NATIVE_VALUE:' + type(error).__name__
    values = [coh, low, high]
    valid = all(type(v) in (int, float) and math.isfinite(v) for v in values)
    valid = valid and 0 <= coh <= 1 and low in (0, 1) and high in (0, 1)
    gate = 0.0
    if phase == 'ENGINE' and segment == '0001' and valid and state.get('runtime_ok', False):
        warmed = ordinal >= 3
        if not warmed:
            reason = 'WAIT_FOR_PUBLISHED_INITIAL_OFF'
        if warmed and not state.get('armed', False) and values == [1, 1, 1]:
            state['armed'] = True
        if state.get('armed', False):
            if low == 0 or high == 0:
                state['bulk_deleted'] = True
            if state.get('cohesive_zero', False) and coh != 0:
                state['invalid'] = True
                reason = 'COHESIVE_REAPPEARED'
            if coh == 0:
                state['cohesive_zero'] = True
            if state.get('invalid', False):
                reason = 'LATCHED_INVALID'
            elif state.get('bulk_deleted', False):
                reason = 'BULK_DELETED_CONTACT_OFF'
            elif coh == 0:
                gate = 1.0
                reason = 'DELETED_BULK_LIVE'
            elif coh == 1:
                reason = 'LIVE_CONTACT_OFF'
            else:
                reason = 'FADING_CONTACT_OFF'
    elif not valid:
        reason = 'INVALID_NATIVE_VALUE_CONTACT_OFF'
    elif phase != 'ENGINE' or segment != '0001':
        reason = 'NON_INITIAL_ENGINE_CONTACT_OFF'
    if not state.get('runtime_ok', False):
        gate = 0.0
        reason = 'RUNTIME_QUERY_FAILED_CONTACT_OFF'
    def safe(value):
        if type(value) in (int, float) and math.isfinite(value):
            return value
        return None if value is None else repr(value)
    row = {{'phase': phase, 'pid': os.getpid(), 'ordinal': ordinal}}
    row['segment'] = segment
    row['sensor_id'] = {sid}
    row['cohort'] = {ids!r}
    row['time_s'], row['dt_s'] = safe(clock), safe(step)
    row.update(off=[safe(v) for v in values], previous_status=safe(previous))
    row.update(gate=gate, armed=bool(state.get('armed', False)), reason=reason)
    row['runtime_error'] = state.get('runtime_error')
    if ordinal == 1:
        row['python'] = state['runtime']
    with open('{TRACE}', 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, allow_nan=False) + '\\n')
        stream.flush()
    return gate

'''


def apply(text,model,settings,cohesive):
    entries=validate(model,settings)
    if not entries:return text,[]
    from .impact_b import model_identity
    before=cards(text)
    if any(k.startswith(('/SENSOR/','/FUNCT_PYTHON','/ACTIV')) for k in before):
        raise ValueError('기존 센서·임의 Python·재활성 카드를 덮거나 자동 승인하지 않습니다')
    item=entries[0];control=item['control'];title='IMPACT'+str(control['contact_index']+1)
    matches=[(k,r) for k,r in before.items() if k.startswith('/INTER/TYPE24/') and r[0].strip().upper()==title]
    if len(matches)!=1:raise ValueError('정확한 native TYPE24 하나가 필요합니다')
    key,original=matches[0];rows=deepcopy(original)
    if len(rows)!=7 or len(rows[1])<80 or len(rows[6])<60:
        raise ValueError('고정 TYPE24 카드의 Idel/sens_ID 필드를 확인하세요')
    if int(rows[1][70:80].strip() or '0') or int(rows[6][50:60].strip() or '0'):
        raise ValueError('이미 삭제/센서 제어된 TYPE24를 덮지 않습니다')
    if any(float(rows[4][start:start+20].strip() or '0')!=0 for start in (40,60)):
        raise ValueError('삭제 연동은 원 Tstart/Tstop 기본값을 보존합니다')
    sensor_id=_allocator(before)();name='caelab_reclosure_'+str(sensor_id)
    receipt={'policy':POLICY,'model_identity':model_identity(model),'settings_sha256':canonical_hash(control),
        'cohort':item['cohort'],'geometry':deepcopy(item['geometry']),'native_contact_id':int(key.rsplit('/',1)[1]),
        'sensor_id':sensor_id,'function_name':name,'trace_relative':TRACE,'phase_env':PHASE_ENV,
        'segment_env':SEGMENT_ENV,'allowed_initial_segment':'0001','minimum_arm_ordinal':3,
        'cycle_binding':'PINNED_SENSOR_INIT_THEN_PRINT1',
        'terminal_cycle_relation':'PRINT_LAST_TOTAL_MINUS_ONE',
        'source_pin':PIN,'native_idel':1,'source_ordering':'contact -> solid/fade -> face cleanup -> sensor(previous OFF) -> publish OFF -> next cycle',
        'capability':'RUNTIME_UNVERIFIED','every_increment':'UNKNOWN_UNTIL_COMPLETE_TRACE_AND_PRINT',
        'gap_measure':'derived initial paired bulk-face signed separation, not native PENE'}
    source=callback_source(receipt);receipt['callback_source']=source
    receipt['callback_sha256']=hashlib.sha256(source.encode('ascii')).hexdigest()
    rows[1]=rows[1][:70]+integer(1)+rows[1][80:]
    rows[6]=rows[6][:50]+integer(sensor_id)+rows[6][60:]
    sensor_key='/SENSOR/PYTHON/'+str(sensor_id)
    result=replace_blocks(text,{key:key+'\n'+'\n'.join(rows)+'\n'})
    result=append_before_end(result,sensor_key+'\n'+source)
    receipt['expected_cards']={key:cards(result)[key],sensor_key:cards(result)[sensor_key]}
    verify(result,model,settings,[receipt])
    return result,[receipt]


def verify(text,model,settings,receipts):
    from .impact_b import model_identity
    entries=validate(model,settings)
    if len(entries)!=len(receipts):raise ValueError('삭제 연동의 원 정책 개수가 다릅니다')
    blocks=cards(text)
    expected_sensors={'/SENSOR/PYTHON/'+str(r['sensor_id']) for r in receipts}
    if {key for key in blocks if key.startswith('/SENSOR/')}!=expected_sensors:
        raise ValueError('승인되지 않은 센서가 생성 정책에 추가되었습니다')
    if receipts and any(k.startswith(('/FUNCT_PYTHON','/ACTIV')) for k in blocks):
        raise ValueError('임의 Python 또는 재활성 카드를 자동 실행하지 않습니다')
    for entry,receipt in zip(entries,receipts):
        if (receipt['policy']!=POLICY or receipt['cohort']!=entry['cohort'] or receipt['geometry']!=entry['geometry']
                or receipt['model_identity']!=model_identity(model) or receipt['settings_sha256']!=canonical_hash(entry['control'])):
            raise ValueError('삭제 연동의 원 요소·기하·정책 신원이 바뀌었습니다')
        source=callback_source(receipt)
        if receipt['callback_source']!=source or receipt['callback_sha256']!=hashlib.sha256(source.encode('ascii')).hexdigest():
            raise ValueError('승인된 고정 생성 callback과 다릅니다')
        sensor='/SENSOR/PYTHON/'+str(receipt['sensor_id'])
        normalized=text.replace('\r\n','\n')
        segment=re.search(r'(?ms)^'+re.escape(sensor)+r'\n(.*?)(?=^/|\Z)',normalized)
        if segment is None or segment.group(1)!=source:
            raise ValueError('생성 Python 원문과 필수 끝 빈 줄이 바뀌었습니다')
        if blocks.get(sensor)!=source.splitlines()[:-1]:
            # cards() drops the required final empty Python line.
            if blocks.get(sensor)!=[line for line in source.splitlines() if line.strip()]:
                raise ValueError('생성 센서 callback 카드가 바뀌었습니다')
        for key,expected in receipt['expected_cards'].items():
            if blocks.get(key)!=expected:raise ValueError('삭제 연동 native 카드가 바뀌었습니다: '+key)


def audit_trace(trace_path,engine_print_path,receipt):
    """Audit original callback prefix and PRINT/1 cycles without interpolation.

    PRINT display tokens and callback precision remain separate observations.
    Missing/truncated/ambiguous cycle coverage stays UNKNOWN; violations survive.
    """
    import json
    from pathlib import Path
    from .evaluation import file_hash
    trace_path=Path(trace_path);engine_print_path=Path(engine_print_path)
    rows=[];unknown=[];violations=[];sources={}
    for label,path in (('trace',trace_path),('engine_print',engine_print_path)):
        if not path.is_file() or path.stat().st_size>64*1024*1024:
            unknown.append(label+': missing or exceeds64MiB')
        else:sources[label]={'name':path.name,'sha256':file_hash(path)}
    if 'trace' in sources:
        for line_no,line in enumerate(trace_path.read_text(encoding='utf-8').splitlines(),1):
            try:
                row=json.loads(line)
                if not isinstance(row,dict):raise ValueError('not an object')
                rows.append(row)
            except (ValueError,TypeError) as error:
                unknown.append('trace truncated/invalid at line '+str(line_no)+': '+str(error));break
    engine=[row for row in rows if row.get('phase')=='ENGINE']
    printed=[];total=None;normal=False
    if 'engine_print' in sources:
        text=engine_print_path.read_text(encoding='ascii',errors='replace')
        # ecrit.F FORMAT1000/1100: I8,2(1X,G11.4),1X,A5,... . Positive
        # /PRINT/1 writes this table to .out, not the NC= stdout spelling.
        table=False
        for number,line in enumerate(text.splitlines(),1):
            if line.startswith('   CYCLE    TIME      TIME-STEP  ELEMENT'):
                table=True;continue
            if not table or len(line)<39 or not line[:8].strip().isdigit():continue
            try:
                clock,step=line[9:20].strip(),line[21:32].strip()
                time_s,dt_s=float(clock),float(step)
                if not math.isfinite(time_s) or not math.isfinite(dt_s):raise ValueError('nonfinite')
                printed.append({'cycle':int(line[:8]),'time_token':clock,'dt_token':step,
                    'time_s':time_s,'dt_s':dt_s,'line_number':number,'raw_line':line,
                    'format':'PINNED_ECRIT_1100_TABLE'})
            except ValueError:unknown.append('unreadable PRINT table at line '+str(number))
        pattern=r'NC=\s*(\d+)\s+T=\s*(\S+)\s+DT=\s*(\S+)'
        for cycle,time_token,dt_token in re.findall(pattern,text):
            try:printed.append({'cycle':int(cycle),'time_token':time_token,'dt_token':dt_token,
                                'time_s':float(time_token),'dt_s':float(dt_token),'format':'ECRIT_STDOUT'})
            except ValueError:unknown.append('unreadable PRINT cycle token')
        counts=[int(v) for v in re.findall(r'TOTAL NUMBER OF CYCLES\s*:\s*(\d+)',text)]
        total=counts[-1] if counts and len(set(counts))==1 else None
        normal='NORMAL TERMINATION' in text
    if not engine:unknown.append('no ENGINE callback rows')
    if not printed:unknown.append('no PRINT/1 cycle rows')
    if len({row.get('pid') for row in engine})>1:unknown.append('multiple Engine process traces require explicit restart lineage')
    armed=False;cohesive_zero=False;bulk_deleted=False;invalid_latched=False
    observed_live=None;first_zero=None;gate_on=[];fading=[]
    expected_ids=receipt['cohort']
    for i,row in enumerate(engine):
        ordinal=row.get('ordinal')
        if type(ordinal) is not int or ordinal!=i+1:unknown.append('callback ordinal gap/duplicate at row '+str(i))
        if row.get('sensor_id')!=receipt['sensor_id'] or row.get('cohort')!=expected_ids:
            violations.append({'row':i,'reason':'SENSOR_OR_COHORT_IDENTITY_CHANGED'})
        values=row.get('off');gate=row.get('gate')
        finite=lambda v:type(v) in (int,float) and math.isfinite(v)
        valid=(isinstance(values,list) and len(values)==3 and all(finite(v) for v in values)
               and 0<=values[0]<=1 and values[1] in (0,1) and values[2] in (0,1))
        if not finite(gate) or gate not in (0,1):violations.append({'row':i,'reason':'NON_BINARY_GATE'})
        if row.get('runtime_error'):
            unknown.append('runtime identity query failed at row '+str(i)+': '+str(row['runtime_error']))
            if gate!=0:violations.append({'row':i,'reason':'UNVERIFIED_RUNTIME_ENABLED_CONTACT'})
        if not all(finite(row.get(key)) for key in ('time_s','dt_s','previous_status')):
            unknown.append('missing/nonfinite clock or previous sensor status at row '+str(i))
        if not valid:
            unknown.append('unknown/nonfinite/fractional-bulk OFF at row '+str(i))
            if gate!=0:violations.append({'row':i,'reason':'INVALID_OFF_ENABLED_CONTACT'})
            continue
        coh,lower,upper=values
        # ord1 SENSOR_INIT; ord2 first-loop SENSOR_BASE; regular OFF publish
        # follows ord2. Only ord3+ is an independently published snapshot.
        if i>1 and row.get('segment')=='0001' and not armed and values==[1,1,1]:
            armed=True;observed_live=i
        if armed:
            if lower==0 or upper==0:bulk_deleted=True
            if cohesive_zero and coh!=0:
                invalid_latched=True;violations.append({'row':i,'reason':'COHESIVE_OFF_REAPPEARED'})
            if coh==0:
                cohesive_zero=True
                if first_zero is None:first_zero=i
            if 0<coh<1:fading.append(i)
        allowed=armed and not invalid_latched and not bulk_deleted and coh==0 and lower==upper==1
        if gate==1:
            gate_on.append(i)
            if not allowed:violations.append({'row':i,'reason':'LIVE_FADING_OR_MISSING_BULK_CONTACT_OVERLAP'})
    if observed_live is None:unknown.append('actual published initial all-live OFF not established')
    if not normal or total is None:unknown.append('normal Engine termination/cycle total not established')
    if printed and [r['cycle'] for r in printed]!=list(range(printed[0]['cycle'],printed[-1]['cycle']+1)):
        unknown.append('PRINT is not every-cycle contiguous')
    mapping=[];regular=engine[1:] if engine else []
    if len(regular)!=len(printed):unknown.append('regular callback/PRINT counts differ; preserve initial/tail rows')
    previous_time=None
    for i,row in enumerate(engine):
        clock=row.get('time_s')
        if type(clock) in (int,float) and math.isfinite(clock):
            if previous_time is not None and clock<previous_time:unknown.append('callback clock decreased')
            previous_time=clock
    for call,cycle in zip(regular,printed):
        # Python DT is from the preceding publish. PRINT may show newly computed
        # DT2; neither exact DT equality nor a DT-based row estimate is valid.
        mapping.append({'callback_ordinal':call.get('ordinal'),'print_cycle':cycle['cycle'],
            'actual_callback_time_s':call.get('time_s'),'actual_callback_dt_s':call.get('dt_s'),
            'print_time_token':cycle['time_token'],'print_dt_token':cycle['dt_token'],
            'time_relation':'source-phase/display precision retained; no bit-equality threshold'})
    if receipt.get('cycle_binding')!='PINNED_SENSOR_INIT_THEN_PRINT1':
        unknown.append('pinned initial/final cycle binding not yet established')
    if receipt.get('terminal_cycle_relation')!='PRINT_LAST_TOTAL_MINUS_ONE' or total is None or not printed:
        unknown.append('pinned PRINT terminal cycle relation not established')
    elif printed[0]['cycle']!=0 or printed[-1]['cycle']!=total-1:
        unknown.append('PRINT prefix/tail differs from declared source cycle relation')
    return {'policy':POLICY,'sources':sources,'engine_callback_count':len(engine),'starter_callback_count':sum(r.get('phase')=='STARTER' for r in rows),
        'engine_print_count':len(printed),'engine_total_cycles':total,'cycle_mapping':mapping,
        'initial_callback':engine[0] if engine else None,'unmatched_tail_callbacks':regular[len(printed):],
        'print_rows':printed,
        'print_display':'native source G11.4; tokens retained without new numerical tolerance',
        'actual_initial_live_row':observed_live,'first_exact_cohesive_zero_row':first_zero,
        'gate_on_rows':gate_on,'fading_contact_off_rows':fading,'violations':violations,
        'unknown_reasons':list(dict.fromkeys(unknown)),
        'every_increment':'VIOLATED' if violations else 'EVERY_INCREMENT_UNKNOWN' if unknown else 'COMPLETE_PINNED_TRACE_COVERAGE',
        'trace_rows':rows,'engineering_qualification':'UNKNOWN',
        'force_evidence':'source-phase/logic audit; not directly measured every-increment traction or penalty force',
        'native_PENE':'UNKNOWN_NOT_INFERRED_FROM_PAIRED_SEPARATION'}
