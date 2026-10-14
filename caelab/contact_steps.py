"""Explicit contact stages. Native condition mapping stays in the existing frozen model."""
from copy import deepcopy
import math
from .contact import number

def axis(model):
    dynamic = model.get('analysis_steps', {}).get('procedure') == 'dynamic'
    return {'name': 'time' if dynamic else 'load_parameter', 'unit': 's' if dynamic else '1',
            'semantics': 'PHYSICAL_TIME' if dynamic else 'STATIC_LOAD_PARAMETER'}

def integer(value, label):
    v = number(value)
    if v != int(v) or not 1 <= v <= 1000000:
        raise ValueError(label + ': 양의 정수를 입력하세요')
    return int(v)

def curve(points, duration, label):
    if not isinstance(points, list) or not 2 <= len(points) <= 10000:
        raise ValueError(label + ': 시작과 끝을 포함한 곡선 점이 필요합니다')
    out = []
    for row in points:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError(label + ': 각 점은 진행값과 조건값입니다')
        out.append([number(row[0]), number(row[1])])
    if out[0][0] != 0 or out[-1][0] != duration:
        raise ValueError(label + ': 곡선은 0에서 단계 길이까지 포함해야 합니다')
    written = [float(format(row[0],'.13G')) for row in out]
    if any(b <= a for a,b in zip(written,written[1:])):
        raise ValueError(label + ': 입력 파일 정밀도에서 곡선 진행값이 겹칩니다')
    if any(b[0] <= a[0] for a, b in zip(out, out[1:])):
        raise ValueError(label + ': 곡선 진행값은 중복 없이 증가해야 합니다')
    return out

def _at(points, t):
    # Interpolation belongs only to the explicitly authored piecewise-linear INPUT.
    for a, b in zip(points, points[1:]):
        if a[0] <= t <= b[0]:
            return a[1] + (b[1]-a[1])*(t-a[0])/(b[0]-a[0])
    raise ValueError('Curve does not cover the step')

def required_curves(conditions):
    out = {}
    for c in conditions:
        if c['type'] == 'Fem::ConstraintForce':
            out[(c['object_id'], 0)] = ('N', c['total_force_N'])
        elif c['type'] == 'Fem::ConstraintDisplacement':
            for d, v in c['components_mm'].items():
                out[(c['object_id'], int(d))] = ('mm', v)
        elif c['type'] != 'Fem::ConstraintFixed':
            raise ValueError('Unsupported step condition')
    return out

def default_program(step, conditions):
    duration = step['period']
    curves = [{'condition_id': c, 'component': d, 'unit': unit,
               'points': [[0, 0], [duration, v]]}
              for (c, d), (unit, v) in required_curves(conditions).items()]
    return {'schema_version': '1', 'procedure': 'static', 'steps': [
        {'id': 'Step1', 'label': '하중 적용', 'duration': duration,
         **{k: deepcopy(step[k]) for k in ('initial','minimum','maximum','increments')},
         'curves': curves, 'output_frequency': 1}]}

def reconcile_program(program, conditions):
    """Explicitly reconcile current native conditions without parsing edited text.

    Matching physical condition/component/unit rows retain every authored value.
    New rows ramp from zero in the first stage and hold their endpoint thereafter.
    Deleted or changed-unit rows are replaced only on this user action.
    """
    result = deepcopy(program)
    required = required_curves(conditions)
    for index, step in enumerate(result['steps']):
        old = {}
        for row in step.get('curves', []):
            key = row.get('condition_id'), row.get('component'), row.get('unit')
            if key in old:
                raise ValueError('중복된 조건 곡선을 먼저 정리하세요')
            old[key] = row
        rows = []
        for (cid, component), (unit, value) in required.items():
            key = cid, component, unit
            rows.append(deepcopy(old[key]) if key in old else {
                'condition_id': cid, 'component': component, 'unit': unit,
                'mode': 'curve' if index == 0 else 'hold',
                'points': [[0, 0], [step.get('duration', ''), value]]})
        step['curves'] = rows
    return result

def _frd_clock(value):
    # Exact 2.22 frdheader.c: ten decimal significant digits in [1,1e10),
    # six exponential significant digits otherwise. This is an admission check,
    # never a replacement for any retained native output coordinate.
    if 1 <= value < 1e10:
        places = 10 - math.floor(math.log10(value) + 1.)
        return float(format(value, '.' + str(places) + 'f'))
    return float(format(value, '.5E'))

def compile_program(program, conditions):
    if not isinstance(program, dict) or program.get('schema_version') != '1':
        raise ValueError('지원되는 단계 정의가 아닙니다')
    procedure = program.get('procedure')
    if procedure not in ('static', 'dynamic'):
        raise ValueError('정적 또는 암시적 동적 해석을 선택하세요')
    raw_steps = program.get('steps')
    if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= 100:
        raise ValueError('해석 단계는 1~100개가 필요합니다')
    known = {c['object_id']: c for c in conditions}
    if len(known) != len(conditions):
        raise ValueError('Duplicate native condition')
    required = required_curves(conditions)
    output, names, elapsed, written_elapsed = [], set(), 0., 0.
    preceding = {k:v for k,(unit,v) in required.items()}
    for index, raw in enumerate(raw_steps, 1):
        label, identifier = raw.get('label'), raw.get('id')
        if not isinstance(label, str) or not label.strip() or len(label) > 160:
            raise ValueError('단계 이름을 입력하세요')
        if not isinstance(identifier, str) or not identifier or identifier in names:
            raise ValueError('Duplicate or missing step identity')
        names.add(identifier)
        duration, initial, minimum, maximum = [number(raw.get(k)) for k in ('duration','initial','minimum','maximum')]
        if not 0 < minimum <= initial <= min(duration, maximum):
            raise ValueError(label + ': 최소/초기/최대 증분과 단계 길이를 확인하세요')
        written_duration = float(format(duration,'.13G'))
        written_end = written_elapsed + written_duration
        if (not math.isfinite(written_end) or written_end <= written_elapsed
                or _frd_clock(written_end) <= _frd_clock(written_elapsed)):
            raise ValueError(label + ': 단계 시작과 끝을 CalculiX 출력 정밀도로 구분할 수 없습니다. 단계 길이를 확인하세요')
        written_elapsed = written_end
        parsed = {}
        if not isinstance(raw.get('curves'), list):
            raise ValueError(label + ': 조건 곡선이 필요합니다')
        for row in raw['curves']:
            key = row.get('condition_id'), row.get('component')
            if (type(key[1]) is not int or key not in required or key in parsed
                    or row.get('unit') != required[key][0]):
                raise ValueError(label + ': 조건/성분/단위가 현재 Analysis와 다르거나 중복입니다')
            previous = preceding[key]
            mode = row.get('mode','curve')
            if mode == 'release':
                parsed[key] = None
                preceding[key] = None
            elif mode == 'hold':
                if preceding[key] is None:
                    raise ValueError(label + ': 해제된 변위/하중을 유지할 수 없습니다. 새 곡선을 입력하세요')
                parsed[key] = [[0.,preceding[key]],[duration,preceding[key]]]
            elif mode == 'curve':
                parsed[key] = curve(row.get('points'), duration, known[key[0]].get('label', key[0]))
                preceding[key] = parsed[key][-1][1]
            else:
                raise ValueError(label + ': 곡선 / 이전값 유지 / 해제를 선택하세요')
            if procedure=='dynamic' and key[1]!=0 and parsed[key] is not None:
                start_value=0. if index==1 else previous
                if start_value is None or parsed[key][0][1]!=start_value:
                    raise ValueError(label + ': 동적 지정 변위는 이전 끝값에서 연속이어야 합니다. 초기 변위는 0이며 해제 뒤 재구속은 지원하지 않습니다')
        if set(parsed) != set(required):
            raise ValueError(label + ': 모든 하중 및 지정 변위 성분의 곡선을 작성하세요')
        boundary, forces = {}, {}
        for c in conditions:
            cid, kind = c['object_id'], c['type']
            if kind == 'Fem::ConstraintForce':
                if parsed[(cid,0)] is None:
                    continue
                weights = c.get('force_weights', [])
                if not weights and any(v for t, v in parsed[(cid, 0)]):
                    raise ValueError(c.get('label', cid) + ': native 기준 하중을 0이 아닌 값으로 적용하세요')
                for row in weights:
                    key = row['node_id'], row['component']
                    forces.setdefault(key, []).append([[t, v*number(row['weight'])] for t, v in parsed[(cid, 0)]])
            else:
                for row in c.get('boundary_dofs', []):
                    key = row['node_id'], row['component']
                    points = [[0.,0.],[duration,0.]] if kind == 'Fem::ConstraintFixed' else parsed[(cid,key[1])]
                    if points is None:
                        continue
                    if key in boundary and boundary[key] != points:
                        raise ValueError(label + ': 같은 자유도의 지정 변위 곡선이 충돌합니다')
                    boundary[key] = points
        loads = {}
        for key, curves in forces.items():
            times = sorted({t for points in curves for t, v in points})
            points = [[t, math.fsum(_at(p,t) for p in curves)] for t in times]
            if key in boundary and any(v for t,v in points):
                raise ValueError(label + ': 하중과 지정 변위가 같은 자유도에 겹칩니다')
            loads[key] = points
        # STATIC OP=NEW alone ramps old force to zero through xforcold.
        # Emit explicit zero amplitudes on every known load DOF, including
        # released conditions, so off means zero throughout this step.
        for c in conditions:
            for row in c.get('force_weights',[]):
                loads.setdefault((row['node_id'],row['component']),[[0.,0.],[duration,0.]])
        if not boundary:
            raise ValueError(label + ': 명시적인 구속이 필요합니다')
        # Recheck the compiled union, not only each authored condition: distinct
        # source knots can collapse when two conditions share a native DOF.
        for mapping in (boundary, loads):
            for points in mapping.values():
                curve(points, duration, label)
        output.append(dict(id=identifier, label=label, index=index, procedure=procedure,
            start=elapsed, end=elapsed+duration, duration=duration, initial=initial,
            minimum=minimum, maximum=maximum, increments=integer(raw.get('increments'),label),
            output_frequency=integer(raw.get('output_frequency'),label),
            boundary=boundary, loads=loads, curves=deepcopy(raw['curves'])))
        elapsed += duration
        if not math.isfinite(elapsed):
            raise ValueError(label + ': 누적 단계 길이가 유한해야 합니다')
    return output

def step_location(model, step, total):
    if 'analysis_steps' not in model:
        if step != 1:
            raise ValueError('The retained input contains only Step1')
        return {'id':'Step1','label':'Step1','index':1,'coordinate':total,'axis':axis(model)}
    rows = compile_program(model['analysis_steps'], model['conditions'])
    if type(step) is not int or not 1 <= step <= len(rows):
        raise ValueError('Result step is outside the frozen input')
    row = rows[step-1]
    return {'id':row['id'],'label':row['label'],'index':step,'coordinate':total-row['start'],
            'axis':axis(model),'conditions':deepcopy(row['curves'])}

def render_steps(model):
    from .contact_deck import num
    rows, lines = compile_program(model['analysis_steps'], model['conditions']), []
    for step in rows:
        amps = {}
        for mapping in (step['boundary'],step['loads']):
            for points in mapping.values():
                key = tuple(tuple(p) for p in points)
                if key not in amps:
                    amps[key] = 'A'+str(step['index'])+'_'+str(len(amps)+1)
        # Default AMPLITUDE clock is step time, intentionally resets on each step.
        for points, name in amps.items():
            lines += ['*AMPLITUDE,NAME='+name] + [num(t)+','+num(v) for t,v in points]
        lines.append('*STEP,INC='+str(step['increments'])+
                     (',NLGEOM' if model['step']['geometry']=='nonlinear' else ',NLGEOM=NO'))
        solvers = {'default':'','spooles':'SPOOLES','pastix':'PASTIX','pardiso':'PARDISO',
                   'iterativescaling':'ITERATIVE SCALING','iterativecholesky':'ITERATIVE CHOLESKY'}
        solver = solvers[model['step']['matrix_solver']]
        card = '*STATIC' if step['procedure']=='static' else '*DYNAMIC'
        lines.append(card+(',SOLVER='+solver if solver else '')+
                     ('' if model['step']['automatic'] else ',DIRECT'))
        lines.append(','.join(num(step[k]) for k in ('initial','duration','minimum','maximum')))
        if model['step'].get('controls') is not None:
            lines += ['*CONTROLS,PARAMETERS=TIME INCREMENTATION',*model['step']['controls']]
        for mapping, card in ((step['boundary'],'*BOUNDARY'),(step['loads'],'*CLOAD')):
            groups = {}
            for key, points in sorted(mapping.items()):
                groups.setdefault(amps[tuple(tuple(p) for p in points)],[]).append(key)
            if not groups:
                lines.append(card+',OP=NEW')
            for i,(name,keys) in enumerate(groups.items()):
                lines.append(card+(',OP=NEW' if i==0 else '')+',AMPLITUDE='+name)
                lines += [str(n)+','+str(d)+(','+str(d) if card=='*BOUNDARY' else '')+',1' for n,d in keys]
        frequency = ',FREQUENCY='+str(step['output_frequency'])
        has_tie = any(p['draft']['normal_law'] == 'tie' for p in model['contacts'])
        lines += ['*NODE FILE'+frequency, 'U,RF' if has_tie else 'U']
        if has_tie:
            lines += ['*EL FILE'+frequency, 'S']
        contact_pairs = [p for p in model['contacts'] if p['draft']['normal_law'] != 'tie']
        if contact_pairs:
            lines += ['*CONTACT FILE'+frequency, 'CDIS,CSTR']
        for pair in contact_pairs:
            pid = pair['object_id']
            lines += ['*CONTACT PRINT,SLAVE=DEP'+pid+',MASTER=IND'+pid+frequency,'CF,CFN,CFS']
        lines.append('*END STEP')
    return lines

def validate_contributions(model):
    """Do not admit forged/stale condition weights behind a valid aggregate deck."""
    nodes = {r['node_id']: r['body_id'] for r in model['nodes']}
    boundaries, forces = {}, {}
    for c in model['conditions']:
        if c['type'] == 'Fem::ConstraintForce':
            for row in c.get('force_weights', []):
                n, d = row['node_id'], row['component']
                if type(n) is not int or n<1 or nodes.get(n) != c['body_id'] or type(d) is not int or d not in (1,2,3):
                    raise ValueError('Condition force contribution lies outside its owning body')
                key = n,d
                forces[key] = forces.get(key,0.) + number(row['weight'])*number(c['total_force_N'])
        else:
            for row in c.get('boundary_dofs', []):
                n,d,v = row['node_id'],row['component'],number(row['value_mm'])
                if type(n) is not int or n<1 or nodes.get(n) != c['body_id'] or type(d) is not int or d not in (1,2,3):
                    raise ValueError('Condition boundary contribution lies outside its owning body')
                if c['type']=='Fem::ConstraintFixed' and v != 0:
                    raise ValueError('Fixed support is not a prescribed displacement')
                if c['type']=='Fem::ConstraintDisplacement' and v != number(c['components_mm'].get(d,c['components_mm'].get(str(d)))):
                    raise ValueError('Boundary contribution differs from the native component')
                if (n,d) in boundaries and boundaries[n,d] != v and 'analysis_steps' not in model:
                    raise ValueError('Conflicting native boundary contributions')
                # Match the collector's first-declared baseline without imposing
                # that inactive native value on an explicit staged condition.
                boundaries.setdefault((n,d), v)
    expected = {(r['node_id'],r['component']):number(r['value_mm']) for r in model['boundary_dofs']}
    loads = {(r['node_id'],r['component']):number(r['force_N']) for r in model['loads']}
    if boundaries != expected or set(forces) != set(loads):
        raise ValueError('Condition contributions do not cover the retained native loads/boundaries')
    if any(not math.isclose(forces[k],loads[k],rel_tol=1e-12,abs_tol=1e-12) for k in forces):
        raise ValueError('Condition weights differ from the retained native force total')

def profile(model):
    if 'analysis_steps' not in model:
        return None
    rows = compile_program(model['analysis_steps'],model['conditions'])
    return {'version':1,'axis':axis(model),'steps':[
        {k:deepcopy(row[k]) for k in ('id','label','index','procedure','start','end','duration')} for row in rows]}

def validate_frames(model, observed, *, complete=True):
    from .adapters.fixture_field import _printed_close
    p = profile(model)
    expected = p['steps'] if p else [{'index':1,'start':0.,'end':number(model['step']['period'])}]
    for frame in observed['frames']:
        s = frame['static']; index=s['step']
        if not 1 <= index <= len(expected):
            raise ValueError('FRD step is outside the frozen schedule')
        row=expected[index-1]; value=s['load_parameter']; token=frame['load_parameter_token']
        if (value < row['start'] and not _printed_close(token,row['start']) or
                value > row['end'] and not _printed_close(token,row['end'])):
            raise ValueError('FRD coordinate is outside its frozen step')
        if p:
            frame['step_location']=step_location(model,index,value)
    if complete:
        for row in expected:
            if not any(f['static']['step']==row['index'] and
                       _printed_close(f['load_parameter_token'],row['end']) for f in observed['frames']):
                raise ValueError('Contact result is missing a completed step endpoint')
    if complete and (observed['static']['step'] != len(expected) or
                     not _printed_close(observed['load_parameter_token'],expected[-1]['end'])):
        raise ValueError('Contact result has not completed every retained step and its final coordinate')
    return observed
