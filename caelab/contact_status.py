"""CalculiX 2.22 STA attempts. A complete FRD can also be a failed best solution."""
from copy import deepcopy
from pathlib import Path
import hashlib
import re

from .contact import number
from .contact_steps import profile, step_location
from .adapters.fixture_field import _printed_close

def read_status(path, model):
    path=Path(path)
    raw=path.read_bytes()
    if len(raw)>32*1024**2:
        raise ValueError('Contact status exceeds the bounded reader size')
    text=raw.decode('ascii')
    rows=[]
    for line_number,line in enumerate(text.splitlines(),1):
        tokens=line.split()
        if not tokens or not tokens[0].isdigit():
            continue
        if (len(tokens)!=7 or not re.fullmatch(r'[1-9][0-9]*U?',tokens[2])
                or any(not t.isdigit() for t in (tokens[0],tokens[1],tokens[3]))):
            raise ValueError('Malformed native contact status row '+str(line_number))
        step,increment,iterations=int(tokens[0]),int(tokens[1]),int(tokens[3])
        total,local,delta=[number(t.replace('D','E')) for t in tokens[4:]]
        if step<1 or increment<1 or delta<=0:
            raise ValueError('Invalid native contact increment')
        location=step_location(model,step,total)
        # Native STA prints only seven significant digits. Compare tokens, not
        # an invented exact arithmetic clock; preserve all original numbers.
        p=profile(model)
        start=p['steps'][step-1]['start'] if p else 0.
        if not _printed_close(tokens[4],start+local,reference_token=tokens[5]):
            raise ValueError('Native total and step coordinates differ from the retained schedule')
        row={'step':step,'increment':increment,'attempt':int(tokens[2].rstrip('U')),
             'iterations':iterations,'converged':not tokens[2].endswith('U'),
             'total':total,'step_coordinate':local,'increment_size':delta,
             'native_tokens':tokens,'line':line_number,'raw':line,
             'step_location':location}
        if not row['converged']:
            row['attempted_end_derived']=total+delta
        rows.append(row)
    if not rows:
        raise ValueError('No native increment status rows')
    terminal=rows[-1]
    cutbacks = []
    for previous, current in zip(rows, rows[1:]):
        if (not previous['converged'] and (previous['step'], previous['increment']) ==
                (current['step'], current['increment']) and current['attempt'] > previous['attempt']
                and current['increment_size'] < previous['increment_size']):
            cutbacks.append({'step': current['step'], 'increment': current['increment'],
                'from_attempt': previous['attempt'], 'to_attempt': current['attempt'],
                'old_increment': previous['increment_size'], 'new_increment': current['increment_size'],
                'source_lines': [previous['line'], current['line']],
                'meaning': 'observed_reduction_between_recorded_attempts'})
    return {'kind':'calculix_increment_attempts','rows':rows,
            'rejected_attempt_count': sum(not row['converged'] for row in rows),
            'observed_cutbacks': cutbacks,
            'residual': {'status': 'unavailable', 'reason': 'not recorded in STA; inspect retained solver stdout'},
            'stabilization_energy': {'status': 'unavailable', 'reason': 'STATIC,STABILIZE is not supported by this 2.22 path'},
            'source':{'relative':'solver/contact.sta','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)},
            'last_converged':next((deepcopy(r) for r in reversed(rows) if r['converged']),None),
            'failure_location':deepcopy(terminal) if not terminal['converged'] else None}

def require_converged(frames, status):
    committed=[r for r in status['rows'] if r['converged']]
    for frame in frames:
        s=frame['static']
        matches=[r for r in committed if (r['step'],r['increment'])==(s['step'],s['increment'])
                 and _printed_close(frame['load_parameter_token'],r['total'],reference_token=r['native_tokens'][4])]
        if len(matches)!=1:
            raise ValueError('Contact field is not a uniquely converged native increment')

def retained_prefix(frd, destination, nodes, elements, materials, model, status):
    """Keep a contiguous committed prefix; never publish a diagnostic best solution.

    The derived reading copy has an explicit terminator. Raw solver bytes and
    truncation remain untouched. Strict geometry/field/component checks still run.
    """
    from .adapters.frozen_fem import read_frd
    from .contact_steps import validate_frames
    raw=Path(frd).read_bytes()
    text=raw.decode('ascii').replace('\r\n','\n')
    lines=text.splitlines()
    endings=[i for i,line in enumerate(lines) if line.strip()=='9999']
    if len(endings)>1 or (endings and any(line.strip() for line in lines[endings[0]+1:])):
        raise ValueError('Native FRD contains content after its end marker')
    starts=[i for i,l in enumerate(lines) if l.split()[:1]==['1PSTEP']]
    committed={(r['step'],r['increment']) for r in status['rows'] if r['converged']}
    if not starts:
        raise ValueError('No native field output')
    stop=len(lines); included=False
    for i in starts:
        line=lines[i].ljust(70)
        key=(int(line[48:60]),int(line[36:48]))
        if key not in committed:
            stop=i
            break
        included=True
    if not included:
        raise ValueError('No converged field prefix')
    # A truncated final committed frame fails strict parsing; it is not filled.
    prefix=lines[:min(stop,endings[0] if endings else len(lines))]
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text('\n'.join(prefix+[' 9999','']),encoding='ascii',newline='\n')
    observed=read_frd(destination,nodes,elements,contact_materials=materials,contact_profile=profile(model),
                      require_contact=any(p['draft']['normal_law'] != 'tie' for p in model['contacts']))
    from .calculix_material import ns1_enabled
    if ns1_enabled(model) and observed['native_version'] != '2.22':
        raise ValueError('NS1 partial readback requires CalculiX 2.22.')
    validate_frames(model,observed,complete=False)
    require_converged(observed['frames'],status)
    return observed
