"""Native termination, retained record integrity and sampled coverage are distinct.

Pinned HIST1/HIST2 write big-endian TFILE/4 records at actual cycle time.
FINAL TIME is an input declaration, and extra terminal ANIM cycles skip HIST2.
No endpoint interpolation, solver-step reconstruction or physical qualification.
"""
import math
from pathlib import Path
import re
import struct
from ..evaluation import file_hash


def engine_termination(log,stdout,declared_end_s):
    """Read stop evidence, never infer achieved time from the input FINAL TIME."""
    sources=[];texts=[]
    path=Path(log)
    if path.is_file():
        if path.stat().st_size>256*1024**2:raise ValueError('Engine log exceeds reader bound')
        texts.append(path.read_text(encoding='ascii',errors='replace'))
        sources.append({'artifact':path.name,'sha256':file_hash(path)})
    if isinstance(stdout,bytes):stdout=stdout.decode('ascii',errors='replace')
    if stdout:texts.append(str(stdout))
    text='\n'.join(texts)
    normal=bool(re.search(r'\bNORMAL TERMINATION\b',text))
    stopped=bool(re.search(r'\bUSER BREAK\b',text))
    abnormal=bool(re.search(r'\b(?:ABNORMAL TERMINATION|ERROR TERMINATION|FATAL ERROR)\b',text))
    counts=[int(v) for v in re.findall(r'TOTAL NUMBER OF CYCLES\s*:\s*(\d+)',text)]
    count=counts[-1] if counts and len(set(counts))==1 else None
    # Retain literal declared values without assigning them to achieved_end_s.
    declared=re.findall(r'^.*FINAL TIME[^\n]*?([+-]?[0-9.]+(?:[EDed][+-]?\d+)?)\s*$',text,re.MULTILINE)
    status=('STOPPED' if stopped else 'FAILED' if abnormal else
            'NORMAL' if normal and count is not None else 'INCOMPLETE')
    return {'status':status,'normal_termination_recorded':normal,
        'user_break_recorded':stopped,'abnormal_termination_recorded':abnormal,
        'total_cycles':count,'sources':sources,'engine_declared_time_tokens':declared,
        'requested_end_s':declared_end_s,'achieved_end_s':None,'declared_end_reached':'UNKNOWN',
        'reason':('Native USER BREAK includes user/control/stop-limit exits; it is not an application cancel receipt'
                  if stopped else 'Native termination is separate from response sampling and physical validity')}


def sample_coverage(times,requested_end_s,requested_interval_s):
    if (not times or any(type(t) not in (int,float) or not math.isfinite(t) or t<0 for t in times)
            or any(b<=a for a,b in zip(times,times[1:]))):
        raise ValueError('Native coverage needs nonnegative strictly increasing sample times')
    return {'sample_count':len(times),'first_sample_s':times[0],'last_sample_s':times[-1],
        'requested_end_s':requested_end_s,'requested_interval_s':requested_interval_s,
        'tail_before_requested_end_s':max(0.,requested_end_s-times[-1]),
        'samples_after_requested_end':sum(t>requested_end_s for t in times),
        'requested_end_value':'NOT_INFERRED','sampling':'ACTUAL_NATIVE_CYCLE_TIMES',
        'schedule_completeness':'UNKNOWN_VARIABLE_TIMESTEP','interpolation':'NONE',
        'reduction_scope':'final=last retained sample; extrema and quadrature cover retained samples only'}


def history_inventory(path,table):
    """Verify complete TFILE/4 record framing and one-to-one converted time rows.

    This checks retained bytes, not whether an unrecorded native cycle should
    have emitted another sample. The official converter can stop quietly at EOF;
    a partial record or conversion row loss must not be mistaken for coverage.
    """
    path=Path(path)
    if not path.is_file() or not 0<path.stat().st_size<=2*1024**3:
        raise ValueError('Native history is missing or exceeds 2 GiB')
    digest=file_hash(path);rows=table['rows']
    def bounded(value):
        if not 0<=value<=1000000:raise ValueError('Native history inventory exceeds bounds')
        return value
    with path.open('rb') as stream:
        def record(size,eof=False):
            header=stream.read(4)
            if not header and eof:return None
            if len(header)!=4:raise ValueError('Truncated native history record header')
            length=struct.unpack('>I',header)[0]
            if length!=size or length>64*1024**2:raise ValueError('Native history record width differs')
            payload=stream.read(length);tail=stream.read(4)
            if len(payload)!=length or tail!=header:raise ValueError('Truncated/mismatched native history record')
            return payload
        def integer(payload,offset=0):return struct.unpack_from('>i',payload,offset)[0]
        def integers(count):return struct.unpack('>'+str(count)+'i',record(count*4))
        first=record(84);code=integer(first)
        # Supported pinned layouts. 3050 is intentionally not admitted: the
        # pinned CSV converter does not consume its additional metadata records.
        if code not in (3040,3041,4021):raise ValueError('Unsupported native history format code')
        title=100 if code==4021 else 80 if code==3041 else 40
        record(80)
        if code==4021:
            if integers(1)!=(2,) or integers(1)!=(title,):raise ValueError('Native history extra layout differs')
            record(12)  # Native mass/length/time declarations, retained unchanged.
        parts,materials,properties,subsets,groups,globals_=integers(6)
        for count in (parts,materials,properties,subsets,groups,globals_):bounded(count)
        if globals_!=23 or integers(globals_)!=tuple(range(1,24)):
            raise ValueError('Native global history membership differs')
        part_width=0
        for _ in range(parts):
            descriptor=record(20+title);width=bounded(integer(descriptor,16+title))
            part_width+=width
            if width:record(4*width)
        for _ in range(materials+properties):record(4+title)
        subset_width=0
        for _ in range(subsets):
            descriptor=record(20+title)
            children,members,width=(bounded(integer(descriptor,i)) for i in (8,12,16))
            for count in (children,members,width):
                if count:record(4*count)
            subset_width+=width
        group_widths=[]
        for _ in range(groups):
            descriptor=record(20+title)
            members=bounded(integer(descriptor,12));width=bounded(integer(descriptor,16))
            for _ in range(members):record(4+title)
            if width:record(4*width)
            total=bounded(members*width)
            if not total:raise ValueError('Zero-width history groups are unsupported by the pinned CSV converter')
            group_widths.append(total)
        expected_columns=1+globals_+part_width+subset_width+sum(group_widths)
        if len(table['header'])!=expected_columns:raise ValueError('Converted history column count differs from native records')
        count=0;previous=None;first_time=last_time=None
        while True:
            clock=record(4,eof=True)
            if clock is None:break
            t=struct.unpack('>f',clock)[0]
            if 0<abs(t)<2.**-126:
                raise ValueError('Subnormal native timestamps are unsupported by the pinned CSV converter')
            if not math.isfinite(t) or t<0 or previous is not None and t<=previous:
                raise ValueError('Native binary time is not finite and strictly increasing')
            # th_to_csv stores binary32 and writes C %e: six fractional digits.
            # Compare that exact representation, not a widened time tolerance.
            if count>=len(rows) or rows[count]['values'][0]!=float(format(t,'.6e')):
                raise ValueError('Converted history time/row coverage differs from retained native records')
            record(4*globals_)
            if part_width:record(4*part_width)
            if subset_width:record(4*subset_width)
            for width in group_widths:record(4*width)
            count+=1
            if count>1000000:raise ValueError('Native history sample count exceeds bound')
            if first_time is None:first_time=t
            last_time=t;previous=t
        if not count or count!=len(rows):raise ValueError('Converted history has missing or additional rows')
    if file_hash(path)!=digest:raise ValueError('Native history changed during inspection')
    return {'status':'MATCHED_RETAINED_LAYOUT_AND_TIMES','format_code':code,'record_count':count,
        'source_artifact':path.name,'source_sha256':digest,
        'first_native_binary32_time_s':first_time,'last_native_binary32_time_s':last_time,
        'csv_time_encoding':'binary32 formatted with %e (six fractional digits)',
        'value_validation':'Existing history parser; inventory verifies record layout and timestamps',
        'schedule_completeness':'UNKNOWN_VARIABLE_TIMESTEP'}


def energy_observations(table,path):
    """Direct signed observations; no engineering threshold or inferred balance."""
    channels=[]
    for column in (1,2):
        channels.append({'native_name':table['header'][column],
            'negative_source_rows':[r['source_row'] for r in table['rows']
                                    if r['values'][column] is not None and r['values'][column]<0],
            'invalid_source_rows':[r['source_row'] for r in table['rows'] if r['values'][column] is None]})
    return {'assessment':'UNKNOWN','decision':'NOT_RELEASED','channels':channels,
        'source_artifact':Path(path).name,'source_sha256':file_hash(path),
        'reason':'Signed native values retained; no energy-balance or physical-acceptance assessment'}
