"""Native NS2 cards and N3 coordinates; reuse contact_steps' actual compiler.

Primary contract: CalculiX cff1bb12 initialconditionss.f, dampings.f,
restartwrite.f/restartread.f, frd.c and CalculiX.tex. No new integration engine.
"""
from copy import deepcopy
from .contact import number
from .dynamic_model import enabled, has_dynamic, validate_effective


def model_cards(model):
    if not enabled(model):
        return []
    from .contact_deck import num
    d = validate_effective(model)
    lines = ['*ELSET,ELSET=CAELAB_DYNAMIC_ALL']
    # Explicit, disjoint original element IDs. Contact-created springs are NOT
    # silently folded into the structural body energy total.
    ids = sorted(r['element_id'] for r in model['elements'])
    lines += [','.join(map(str, ids[i:i+16])) for i in range(0, len(ids), 16)]
    r = d['rayleigh']
    lines += ['*DAMPING,ALPHA=' + num(r['alpha_per_s']) + ',BETA=' + num(r['beta_s'])]
    for kind, native in (('U', 'DISPLACEMENT'), ('V', 'VELOCITY')):
        rows = [r for r in d['initial_conditions'] if r['kind'] == kind]
        if rows:
            lines.append('*INITIAL CONDITIONS,TYPE=' + native)
            lines += [str(r['node_id']) + ',' + str(r['component']) + ',' + num(r['value'])
                      for r in sorted(rows, key=lambda r: (r['node_id'], r['component']))]
    return lines


def procedure_suffix(model, step):
    if not enabled(model) or step['procedure'] != 'dynamic':
        return ''
    from .contact_deck import num
    return ',ALPHA=' + num(model['dynamic']['numerical_alpha'])


def output_cards(model, step, frequency):
    """Request energy in EVERY step, including nonlinear static preload."""
    from .calculix_material import has_plasticity
    if not enabled(model):
        return None
    nodal = 'U,V,RF' if step['procedure'] == 'dynamic' else 'U,RF'
    fields = 'S,E,ENER' + (',PEEQ' if has_plasticity(model) else '')
    return ['*NODE FILE,GLOBAL=YES' + frequency, nodal,
            '*EL FILE,GLOBAL=YES' + frequency, fields,
            '*EL PRINT,ELSET=CAELAB_DYNAMIC_ALL,TOTALS=NO' + frequency, 'ELKE,ELSE,ENER']


def restart_write(model, step, first_executed):
    if enabled(model) and step['index'] == first_executed:
        return ['*RESTART,WRITE,FREQUENCY=' + str(model['dynamic']['restart_frequency'])]
    return []


def stage_contract(model):
    from .contact_steps import compile_program
    rows = compile_program(model['analysis_steps'], model['conditions'])
    physical = 0.0
    result = []
    checkpoint = model.get('restart', {}).get('checkpoint', {})
    for row in rows:
        dynamic = row['procedure'] == 'dynamic'
        result.append({k: deepcopy(row[k]) for k in ('id', 'label', 'index', 'procedure', 'duration')})
        result[-1].update(native_global_start=row['start'], native_global_end=row['end'],
            native_step_start=0., native_step_end=row['duration'],
            physical_time_available=dynamic, physical_start_s=physical if dynamic else None,
            physical_end_s=physical + row['duration'] if dynamic else None,
            state_origin=('RESTART_READ' if row['index'] == checkpoint.get('step', -1) + 1 else
                          'MODEL_INITIAL_CONDITIONS' if row['index'] == 1 else 'PREVIOUS_NATIVE_STEP'),
            time_semantics='PHYSICAL_TIME' if dynamic else 'STATIC_PSEUDO_TIME',
            wall_time_s=None, load_factor_available=False)
        if dynamic:
            physical += row['duration']
    return result


def location(model, step, total):
    rows = stage_contract(model)
    if type(step) is not int or not 1 <= step <= len(rows):
        raise ValueError('Result step is outside the retained dynamic program')
    row = rows[step-1]
    local = number(total) - row['native_global_start']
    # Keep native rounded coordinates: no clamping or invented exact endpoint.
    return dict(row, coordinate=local, native_global_coordinate=number(total),
                native_step_coordinate_derived=local,
                physical_time_s=row['physical_start_s'] + local if row['physical_time_available'] else None,
                axis={'name': 'time' if row['physical_time_available'] else 'static_pseudo_time',
                      'unit': 's' if row['physical_time_available'] else '1',
                      'semantics': row['time_semantics']})


def executed_start(model):
    return model.get('restart', {}).get('checkpoint', {}).get('step', 0) + 1


def render_restart(model):
    """Only step cards follow READ. Mesh/material/IC are restored by native .rin."""
    from .contact_steps import render_steps
    step = model['restart']['checkpoint']['step']
    return '\n'.join(['*RESTART,READ,STEP=' + str(step)] + render_steps(model) + [''])
