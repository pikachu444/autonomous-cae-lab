"""Read retained CalculiX 2.22 CVG/stdout, never solve or infer acceptance.

Percentages (CVG) and original N/mm values (stdout) remain distinct. Mechanical
only: the thermal zero columns printed by writecvg.f are not thermal results.
Identity is (step, increment, attempt, iteration); stdout step is resolved by
its printed total-minus-step coordinate, NOT by a row ordinal or iteration reset.
Partial EOF is explicitly different from interior corruption. Parsing stops at
corruption and never resumes a supposedly normal curve on its far side.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import math
import re

from .calculix_controls import resolved

MAX_BYTES = 32 * 1024**2
MAX_ROWS = 20000
FLOAT = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?'
CVG_FLOAT = re.compile(r'[+-]?\d\.\d{4}[eEdD][+-]\d{2,3}\Z')
CVG_NAMES = ('residual_force_pct', 'correction_disp_pct', 'residual_flux_pct', 'correction_temp_pct')
RAW = {
    'average force': ('average_force', 'N'),
    'time avg. forc': ('time_average_force', 'N'),
    'largest residual force': ('residual_force', 'N'),
    'largest increment of disp': ('increment_disp', 'mm'),
    'largest correction to disp': ('correction_disp', 'mm'),
    'line search factor': ('line_search_factor', '1'),
}
CORE = {v[0] for k, v in RAW.items() if k != 'line search factor'}


def _number(token):
    if not re.fullmatch(FLOAT, token):
        raise ValueError('Malformed numeric value')
    result = float(token.replace('D','E').replace('d','e'))
    if not math.isfinite(result):
        raise ValueError('Nonfinite convergence value')
    return result


def _source(path, data=None):
    p = Path(path)
    value = {'name': p.name, 'status': 'missing', 'rows': [], 'diagnostics': []}
    if data is None:
        if not p.exists():
            return value, None
        if any(x.is_symlink() for x in (p, *p.parents)) or not p.is_file():
            raise ValueError('Convergence source must be a regular local file')
        if p.stat().st_size > MAX_BYTES:
            raise ValueError('Convergence log exceeds bounded reader size')
        # A bounded read also protects against growth between stat and read.
        with p.open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Convergence log exceeds bounded reader size')
    value.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), status='empty' if not data else 'records')
    try:
        text = data.decode('ascii').replace('\r\n','\n')
        if '\r' in text or '\x00' in text:
            raise ValueError('Invalid log encoding')
    except (UnicodeError, ValueError) as e:
        value.update(status='corrupt', diagnostics=[{'line': 1, 'message': str(e)}])
        return value, None
    return value, text


def _stop(result, line, message, *, partial=False):
    result['status'] = 'partial_eof' if partial else 'corrupt'
    result['diagnostics'].append({'line': line, 'message': message})


def read_cvg(path, *, data=None):
    result, text = _source(path, data)
    if text is None or not text:
        return result
    lines = text.splitlines()
    last = None
    header = False
    for i, line in enumerate(lines, 1):
        fields = line.split()
        if not fields:
            continue
        if line.strip() in ('SUMMARY OF C0NVERGENCE INFORMATION', 'SUMMARY OF CONVERGENCE INFORMATION'):
            if header or result['rows']:
                _stop(result, i, 'Duplicate CVG header'); break
            header = True
            continue
        if not result['rows'] and header and tuple(fields) in (
                ('STEP','INC','ATT','ITER','CONT.','RESID.','CORR.','RESID.','CORR.'),
                ('EL.','FORCE','DISP','FLUX','TEMP.'), ('(#)','(%)','(%)','(%)','(%)')):
            continue
        if i == len(lines) and not text.endswith('\n') and any(
                title.startswith(line.strip()) for title in ('SUMMARY OF C0NVERGENCE INFORMATION','SUMMARY OF CONVERGENCE INFORMATION')):
            _stop(result,i,'Truncated CVG header',partial=True); break
        try:
            if not header or len(fields) != 9 or not all(re.fullmatch(r'\d+', x) for x in fields[:5]):
                raise ValueError('Malformed CVG identity or column count')
            identity = tuple(int(x) for x in fields[:4])
            if any(x < 1 for x in identity) or last is not None and identity <= last:
                raise ValueError('Duplicate or reversed CVG iteration')
            if identity[3] != (last[3]+1 if last and last[:3] == identity[:3] else 1):
                raise ValueError('Missing CVG iteration in a recorded attempt')
            if not all(CVG_FLOAT.fullmatch(x) for x in fields[5:]):
                raise ValueError('Malformed CVG E11.4 field')
            values = [_number(x) for x in fields[5:]]
            if any(x != 0 for x in values[2:]):
                result['rows']=[]
                _stop(result,i,'Active thermal CVG columns are outside this mechanical contract')
                result['status']='unsupported_scope'; break
            if any(x < 0 for x in values):
                raise ValueError('CVG norms cannot be negative')
            row = dict(zip(('step','increment','attempt','iteration'), identity))
            row.update(contact_elements=int(fields[4]), values=dict(zip(CVG_NAMES,values)),
                native_tokens=fields, raw=line, line=i,
                sentinel_channels=[name for name, x in zip(CVG_NAMES,values) if x in (1e-30,1e30)])
            result['rows'].append(row)
            last = identity
            if len(result['rows']) >= MAX_ROWS:
                _stop(result, i, 'Convergence row limit reached'); break
        except ValueError as e:
            # Accept only an incomplete *last* physical record as a torn EOF.
            # Arbitrary garbage, duplicate IDs and closed invalid rows stay corrupt.
            prefix_ok = (fields and fields[0].isdigit() and
                all(re.fullmatch(r'[0-9+\-.eEdD]*', f) for f in fields) and len(fields) <= 9)
            partial = i == len(lines) and not text.endswith('\n') and prefix_ok and ('Malformed' in str(e))
            _stop(result, i, str(e), partial=partial); break
    if header and not result['rows'] and result['status'] == 'records':
        result['status'] = 'no_iterations'
    result['thermal_channels'] = 'inactive_for_supported_mechanical_analysis'
    return result


def schedule(setup):
    """Coordinate intervals from retained input, not from log ordering."""
    program = setup.get('program', setup.get('analysis_steps'))
    rows = program.get('steps', []) if program else [{'id':'Step1','label':'Step1','duration':setup['step']['period']}]
    total, result = 0., []
    for i, row in enumerate(rows, 1):
        duration = float(row['duration'])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError('Invalid retained step interval')
        result.append({'step': i, 'label': row.get('label', f'Step{i}'), 'start': total, 'end': total+duration})
        total += duration
    return result


def _step(block, intervals):
    clocks = block['coordinates']
    if 'total' not in clocks or 'local' not in clocks:
        return None
    total, local = clocks['total']['value'], clocks['local']['value']
    # stdout prints %e with six decimals. Use both recorded coordinates, not
    # a guessed step based on INC, whose count restarts in every step.
    tol = 1.1e-6 * max(abs(total), abs(local), 1e-12)
    matches = [s for s in intervals if abs((total-local)-s['start']) <= tol and
               s['start']-tol <= total <= s['end']+tol]
    return matches[0]['step'] if len(matches) == 1 else None


def read_stdout(path, setup, *, data=None):
    result, text = _source(path, data)
    result['blocks'] = []
    if text is None or not text:
        return result
    lines = text.splitlines()
    intervals = schedule(setup)
    block, row = None, None
    found_version = False
    last_iteration = 0
    number_line = re.compile(r'^('+'|'.join(re.escape(x) for x in RAW)+r')\s*=\s*('+FLOAT+r')(?:\s+in node ([0-9]+) and dof ([0-9]+))?\s*$')

    def finish_row(eof=False):
        nonlocal row
        if row is None:
            return
        missing = CORE-set(row['values'])
        row['record_status'] = 'complete' if not missing and row['decision'] is not None else ('partial_eof' if eof else 'incomplete')
        row['missing_values'] = sorted(missing)
        row['step'] = _step(block, intervals)
        row['coordinates'] = deepcopy(block['coordinates'])
        if row['step'] is None:
            row['identity_status'] = 'unresolved_step'
        else:
            row['identity_status'] = 'coordinate_matched'
        result['rows'].append(row)
        if missing and not eof and result['status'] != 'corrupt':
            _stop(result,row['line'],'Missing stdout quantities before a later record boundary')
        if eof and row['record_status'] != 'complete' and result['status'] != 'corrupt':
            result['status'] = 'partial_eof'
        row = None

    for i, raw in enumerate(lines, 1):
        line = raw.strip()
        torn = i == len(lines) and not text.endswith('\n')
        if not line:
            continue
        if 'CalculiX Version' in line:
            if found_version or not re.search(r'CalculiX Version 2\.22(?:,|\s|$)', line):
                _stop(result, i, 'Unsupported/duplicate CalculiX version'); break
            found_version = True
            continue
        m = re.fullmatch(r'increment\s+([1-9][0-9]*)\s+attempt\s+([1-9][0-9]*)', line)
        if m:
            finish_row()
            if result['status'] == 'corrupt': break
            if torn:
                _stop(result, i, 'Unterminated stdout attempt header', partial=True); break
            last_iteration = 0
            block = {'increment': int(m[1]), 'attempt': int(m[2]), 'coordinates': {}, 'line': i}
            result['blocks'].append(block)
            continue
        if re.match(r'increment(?:\s|$)', line) and not line.startswith('increment size'):
            _stop(result,i,'Malformed stdout attempt header',partial=torn and bool(re.fullmatch(r'increment(?:\s+\d*(?:\s+attempt(?:\s+\d*)?)?)?',line))); break
        if block is None:
            continue
        clocks = {'increment size': 'delta', 'sum of previous increments': 'previous',
                  'actual step time': 'local', 'actual total time': 'total'}
        clock = next((x for x in clocks if line.startswith(x)), None)
        if clock:
            try:
                value = line[len(clock):].lstrip('= ').strip()
                if not re.fullmatch(re.escape(clock)+r'\s*=\s*'+FLOAT,line):
                    raise ValueError('Malformed stdout coordinate')
                parsed = _number(value)
                if torn:
                    _stop(result,i,'Unterminated stdout coordinate',partial=True); break
                if clocks[clock] in block['coordinates'] or parsed < 0:
                    raise ValueError('Duplicate or negative stdout coordinate')
                block['coordinates'][clocks[clock]] = {'value':parsed, 'token':value, 'line':i}
            except ValueError as e:
                _stop(result,i,str(e),partial=i==len(lines) and not text.endswith('\n') and bool(re.fullmatch(r'[0-9+\-.eEdD]*',value)))
                break
            continue
        m = re.fullmatch(r'iteration\s+([1-9][0-9]*)', line)
        if m:
            finish_row()
            if result['status'] == 'corrupt': break
            if int(m[1]) != last_iteration+1 or torn:
                _stop(result,i,'Missing/reversed or unterminated stdout iteration',partial=torn); break
            last_iteration = int(m[1])
            row = {'increment': block['increment'], 'attempt': block['attempt'], 'iteration': int(m[1]),
                   'values': {}, 'decision': None, 'decision_line': None, 'line': i, 'events': []}
            continue
        if line.startswith('iteration'):
            _stop(result,i,'Malformed stdout iteration',partial=torn and bool(re.fullmatch(r'iteration(?:\s+\d*)?',line))); break
        if row is None:
            continue
        recognized = next((x for x in RAW if line.startswith(x)), None)
        if recognized:
            m = number_line.fullmatch(line)
            try:
                if not m:
                    raise ValueError('Malformed stdout convergence quantity')
                name,unit = RAW[m[1]]
                if name in row['values']:
                    raise ValueError('Duplicate stdout convergence quantity')
                value = _number(m[2])
                if value < 0:
                    raise ValueError('Negative norm or line-search factor')
                if torn:
                    _stop(result,i,'Unterminated stdout quantity',partial=True); break
                if m[3] and (int(m[3]) < 1 or int(m[4]) not in (1,2,3)):
                    raise ValueError('Invalid mechanical node/DOF')
                row['values'][name] = {'value':value,'token':m[2],'unit':unit,'line':i,'raw':raw,
                    'node':int(m[3]) if m[3] else None, 'dof':int(m[4]) if m[4] else None}
            except ValueError as e:
                tail = line[len(recognized):]
                partial = (i==len(lines) and not text.endswith('\n') and
                    not re.search(r'[^\d\s+\-.eEdD=inaof]', tail) and 'Duplicate' not in str(e) and 'Invalid' not in str(e))
                _stop(result,i,str(e),partial=partial); break
            continue
        if line == 'no convergence' or line == 'convergence' or line.startswith('convergence;'):
            if row['decision'] is not None:
                _stop(result,i,'Duplicate convergence decision'); break
            if torn:
                _stop(result,i,'Unterminated stdout decision',partial=True); break
            row['decision'] = 'not_converged' if line == 'no convergence' else 'converged'
            row['decision_line'],row['decision_raw'] = i,raw
        elif torn and any(x.startswith(line) for x in ('no convergence','convergence')):
            _stop(result,i,'Truncated stdout decision',partial=True); break
        elif ('divergence' in line or 'increment size' in line or line.startswith('*ERROR')):
            row['events'].append({'line':i,'raw':raw})
        if len(result['rows']) >= MAX_ROWS:
            _stop(result,i,'Convergence row limit reached'); break
    finish_row(eof=result['status'] != 'corrupt' and not any(x.strip() == 'Job finished' for x in lines))
    result['version_verified'] = found_version
    if not found_version and result['rows']:
        _stop(result,1,'No CalculiX 2.22 banner; raw rows retained but not joined')
    seen = set()
    last = None
    broken = False
    for r in result['rows']:
        if r['step'] is None:
            continue
        key = tuple(r[k] for k in ('step','increment','attempt','iteration'))
        if broken or key in seen or last is not None and key <= last:
            _stop(result,r['line'],'Duplicate/reversed stdout iteration identity')
            r['identity_status'] = 'conflict'
            broken = True
        seen.add(key);last=key
    result['job_finished_recorded'] = any(line.strip() == 'Job finished' for line in lines)
    if not result['rows'] and result['status']=='records':
        result['status'] = 'no_iterations'
    return result


def combine(cvg, stdout, status=None, *, execution_status=None):
    rows = {}
    keys = ('step','increment','attempt','iteration')
    for source,name in ((cvg,'cvg'),(stdout,'stdout')):
        if name == 'stdout' and not source.get('version_verified'):
            continue
        for item in source['rows']:
            if item.get('step') is None or item.get('identity_status') == 'conflict':
                continue
            key = tuple(item[k] for k in keys)
            row = rows.setdefault(key, dict(zip(keys,key)))
            if name in row:
                row['identity_conflict'] = True
            else:
                row[name] = deepcopy(item)
    attempts = {}
    for row in (status or {}).get('rows', []):
        key = row['step'],row['increment'],row['attempt']
        if key in attempts:
            attempts[key] = None  # ambiguous STA is not an acceptance witness
        else:
            attempts[key] = row
    for key,row in rows.items():
        sta = attempts.get(key[:3])
        row['attempt_status'] = ('converged' if sta['converged'] else 'rejected') if sta else 'unconfirmed'
        if key[:3] in attempts and sta is None:
            row['identity_conflict'] = True
            row['attempt_status'] = 'conflict'
        row['job_status'] = execution_status
        row['iteration_status'] = 'unrecorded'
        if 'stdout' in row:
            row['iteration_status'] = row['stdout']['decision'] or 'unrecorded'
        row['sta_line'] = sta['line'] if sta else None
        if sta and 'stdout' in row:
            clock = row['stdout']['coordinates'].get('total', {}).get('value')
            expected = sta['total'] if sta['converged'] else sta['total'] + (sta.get('increment_size') or 0)
            if clock is not None and not math.isclose(clock,expected,rel_tol=2e-6,abs_tol=1e-12):
                row['identity_conflict'] = True
                row['attempt_status'] = 'conflict'
        if sta and (row['iteration'] > sta['iterations'] or
                row['iteration_status']=='converged' and (not sta['converged'] or row['iteration']!=sta['iterations'])):
            row['identity_conflict'] = True
            row['attempt_status'] = 'conflict'
        row['coordinate'] = deepcopy(sta.get('step_location')) if sta else None
    return sorted(rows.values(),key=lambda r:tuple(r[k] for k in keys))


def read_convergence(directory, setup, status=None, *, execution_status=None, flat=False, retained_bytes=None):
    """Read files from one owned attempt, or the explicitly supplied flat fixture."""
    root = Path(directory) if flat else Path(directory)/'solver'
    sources = {}
    for name, fn, filename in (('cvg',read_cvg,'contact.cvg'),('stdout',read_stdout,'ccx_contact.stdout.log')):
        try:
            if retained_bytes is not None and retained_bytes.get(name) is None:
                sources[name] = {'name':filename,'status':'missing','rows':[], 'diagnostics':[]}
                continue
            kwargs = {'data':retained_bytes[name]} if retained_bytes is not None else {}
            sources[name] = fn(root/filename,setup,**kwargs) if name=='stdout' else fn(root/filename,**kwargs)
        except (ValueError,KeyError,TypeError,OSError,UnicodeError) as e:
            sources[name] = {'name':filename,'status':'unreadable','rows':[], 'diagnostics':[{'message':str(e)}]}
    rows = combine(sources['cvg'],sources['stdout'],status,execution_status=execution_status)
    try:
        controls = resolved(setup['step'])
        control_diagnostic = None
    except (ValueError,KeyError,TypeError,IndexError) as e:
        controls, control_diagnostic = {}, str(e)
    counts = {s:sum(r['attempt_status']==s for r in rows) for s in ('converged','rejected','unconfirmed','conflict')}
    for info in sources.values():
        info['record_count'] = len(info['rows'])
        info['rows'] = [r for r in info['rows'] if r.get('identity_status') in ('unresolved_step','conflict')]
        info.pop('blocks',None)
    return {'version':1,'kind':'calculix_2_22_mechanical_convergence','rows':rows,'sources':sources,
        'counts':counts,'axis':deepcopy(setup.get('axis',{'name':'load_parameter','unit':'1','semantics':'STATIC_LOAD_PARAMETER'})),
        'controls':controls,'control_diagnostic':control_diagnostic,
        'line_search_applicable':setup.get('penalty_contact',False) and (setup.get('program') or {}).get('procedure','static') == 'static',
        'stabilization_energy':{'status':'unavailable','reason':'STATIC,STABILIZE is not supported by this 2.22 path'},
        'semantics':{'cvg_residual':'100 * largest residual force / time averaged force',
                    'cvg_correction':'100 * largest displacement correction / largest incremental displacement',
                    'cvg_sentinels':'1e-30/1e30 may encode a tiny denominator, not a measured norm',
                    'stdout_zero':'native stdout norm may be clamped below 1e-6 before printing',
                    'thermal_columns':'native inactive placeholders, not thermal convergence',
                    'acceptance':'native recorded decision only; thresholds are reference criteria, not a new convergence verdict'}}


def reopen_convergence(attempt, *, record_data=None):
    """Strict read-only reopening of an old attempt from its recorded log pins.

    Returns a derived view in memory. Does not change contact_execution.json,
    artifacts, JobManager state, or an earlier convergence parse. A changed raw
    source is not silently attributed to the retained attempt.
    """
    from .adapters.frozen_fem import _read
    attempt=Path(attempt)
    record=json.loads(_read(attempt/'contact_execution.json',MAX_BYTES) if record_data is None else record_data)
    pins={r['relative']:r for r in record.get('artifacts',[])}
    retained_bytes={}
    for name,filename in (('cvg','solver/contact.cvg'),('stdout','solver/ccx_contact.stdout.log')):
        retained_bytes[name]=None
        path=attempt/filename
        if path.exists():
            pin=pins.get(filename)
            data=_read(path,MAX_BYTES)
            if pin is None or hashlib.sha256(data).hexdigest()!=pin['sha256'] or len(data)!=pin['bytes']:
                raise ValueError('보존 로그가 없거나 변경됐습니다: '+filename)
            retained_bytes[name]=data
    return read_convergence(attempt,record['executed_setup'],record.get('increment_history'),
                            execution_status=record['execution_status'],retained_bytes=retained_bytes)
