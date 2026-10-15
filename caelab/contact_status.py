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
    from .dynamic_native_stream import frame_catalog
    frames = frame_catalog(frames)
    committed=[r for r in status['rows'] if r['converged']]
    for frame in frames:
        s=frame['static']
        matches=[r for r in committed if (r['step'],r['increment'])==(s['step'],s['increment'])
                 and _printed_close(frame['load_parameter_token'],r['total'],reference_token=r['native_tokens'][4])]
        if len(matches)!=1:
            raise ValueError('Contact field is not a uniquely converged native increment')

def retained_prefix(frd, destination, nodes, elements, materials, model, status, *, streaming=False):
    """Derive only completely recorded, uniquely converged output increments.

    Only the strict reader's structural EOF signal permits dropping an incomplete
    final increment or its torn file terminator. Arbitrary parsing errors, interior
    damage and explicit malformed end markers are never repaired by shortening
    the file until it parses.
    """
    from .adapters.frozen_fem import read_frd, FrdTruncatedEOF, _read
    from .contact_steps import validate_frames
    from .calculix_material import ns1_enabled, has_plasticity
    frd, destination = Path(frd), Path(destination)
    if destination.resolve() == frd.resolve():
        raise ValueError('The derived FRD must not replace the raw solver output')
    from .dynamic_native_stream import NativeLines, frame_catalog, read_dynamic_frd, release
    source = None
    if streaming:
        source = NativeLines(frd)
        source.close()  # outline only; every actual parse owns its own stream
        endings = source.endings
        if len(endings) > 1 or source.trailing_after_end:
            raise ValueError('Native FRD contains content after its end marker')
        starts = source.starts
        line_count, ends_with_newline = source.count, source.ends_with_newline
        raw_pin = {'bytes': source.byte_count, 'sha256': source.sha256}
    else:
        raw = _read(frd)
        text = raw.decode('ascii').replace('\r\n', '\n')
        if '\r' in text or '\x00' in text:
            raise ValueError('Malformed ASCII FRD line encoding')
        lines = text.splitlines(keepends=True)
        endings = [i for i, line in enumerate(lines) if line.strip() == '9999']
        if len(endings) > 1 or (endings and any(line.strip() for line in lines[endings[0]+1:])):
            raise ValueError('Native FRD contains content after its end marker')
        starts = [(i, line) for i, line in enumerate(lines) if line.split()[:1] == ['1PSTEP']]
        line_count, ends_with_newline = len(lines), text.endswith('\n')
        raw_pin = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    committed = {(r['step'], r['increment']) for r in status['rows'] if r['converged']}
    if not starts:
        raise ValueError('No native field output')
    stop = endings[0] if endings else line_count
    reason = 'complete_converged_output'
    first_by_key = {}
    for i, original_line in starts:
        line = original_line.rstrip('\n').ljust(70)
        try:
            key = (int(line[48:60]), int(line[36:48]))
        except ValueError:
            if i == line_count-1 and not ends_with_newline and not endings:
                break
            raise ValueError('Malformed native FRD increment identity') from None
        first_by_key.setdefault(key, i)
        if key not in committed:
            stop, reason = i, 'first_nonconverged_increment'
            break
    physical_eof = not endings and stop == line_count

    def parse(cut, *, eof=False):
        if streaming:
            import tempfile
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.dynamic-prefix-', dir=destination.parent) as temporary:
                reading = Path(temporary) / 'reading.frd'
                source.copy_prefix(reading, cut, terminator=not eof)
                return read_dynamic_frd(reading, nodes, elements,
                    allow_missing_end=eof, contact_materials=materials,
                    contact_profile=profile(model),
                    require_contact=any(p['draft']['normal_law'] != 'tie' for p in model['contacts']))
        reading = ''.join(lines[:cut])
        if not eof:
            reading = reading.rstrip('\n') + '\n 9999\n'
        return read_frd(destination, nodes, elements, data=reading.encode('ascii'),
                        allow_missing_end=eof, contact_materials=materials,
                        contact_profile=profile(model),
                        require_contact=any(p['draft']['normal_law'] != 'tie' for p in model['contacts']))

    recovered = False
    try:
        observed = parse(stop, eof=physical_eof)
    except FrdTruncatedEOF as error:
        if not physical_eof or error.prefix_lines is None:
            raise
        stop, reason = error.prefix_lines, error.reason
        recovered = reason != 'partial_end_marker_at_eof'
        # Strictly reparse the reported cutoff, never search backwards for a pass.
        observed = parse(stop)

    try:
        required = {'DISP'}
        if any(p['draft']['normal_law'] != 'tie' for p in model['contacts']):
            required.add('CONTACT')
        if any(p['draft']['normal_law'] == 'tie' for p in model['contacts']):
            required.update(('STRESS', 'FORC'))
        if ns1_enabled(model):
            required.update(('STRESS', 'TOSTRAIN', 'FORC'))
            if has_plasticity(model):
                required.add('PE')
        for index, frame in enumerate(frame_catalog(observed['frames'])):
            from .dynamic_results import required_fields
            missing = (required | required_fields(model, frame)) - set(frame['fields'])
            if not missing:
                continue
            if physical_eof and not recovered and index == len(observed['frames'])-1:
                # EOF can occur exactly BETWEEN output fields, with no short record.
                # Missing requested channels do not make this a complete increment.
                key = (frame['static']['step'], frame['static']['increment'])
                stop, reason, recovered = first_by_key[key], 'incomplete_increment_at_eof', True
                release(observed)
                observed = parse(stop)
                break
            raise ValueError('Incomplete requested FRD fields: ' + ', '.join(sorted(missing)))
        if any((required | required_fields(model, frame)) - set(frame['fields']) for frame in frame_catalog(observed['frames'])):
            raise ValueError('Incomplete requested fields before the EOF increment')
        if ns1_enabled(model) and observed['native_version'] != '2.22':
            raise ValueError('NS1 partial readback requires CalculiX 2.22.')
        validate_frames(model, observed, complete=False)
        require_converged(observed['frames'], status)
        observed['retention'] = {
            'reason': reason, 'raw_sha256': raw_pin['sha256'], 'raw_bytes': raw_pin['bytes'],
            'retained_line_count': stop,
            'discarded_from_line': stop+1 if stop < (endings[0] if endings else line_count) else None,
            'last_retained_increment': deepcopy(observed['frames'][-1]['static']),
            'synthetic_end_marker': not endings or stop != endings[0],
            'scope': 'complete_fields_of_converged_increments_only'}
        # Publish only the validated derived bytes. Raw FRD/STA are never opened for
        # writing, and no failed candidate copy is advertised as a committed prefix.
        if any(path.is_symlink() for path in (destination, *destination.parents)):
            raise ValueError('The derived FRD must be a regular local file')
        destination.parent.mkdir(parents=True, exist_ok=True)
        if streaming:
            import tempfile, os
            from .dynamic_result_store import verify_pin
            fd, name = tempfile.mkstemp(prefix='.dynamic-prefix-', dir=destination.parent)
            os.close(fd)
            temporary = Path(name)
            try:
                source.copy_prefix(temporary, stop, terminator=True)
                verify_pin(frd.parent, {'relative': frd.name, **raw_pin})
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            destination.write_text(''.join(lines[:stop]).rstrip('\n') + '\n 9999\n', encoding='ascii', newline='\n')
        return observed

    except BaseException:
        release(observed)
        raise


def iteration_history(attempt, execution):
    """Separate diagnostic channel, after owned process termination.

    Neither a CVG threshold nor stdout text upgrades the JobManager status.
    FRD prefix admission continues to use the existing strict STA/FRD contract.
    """
    from .calculix_convergence import read_convergence
    return read_convergence(attempt, execution['executed_setup'],
                            execution.get('increment_history'),
                            execution_status=execution.get('execution_status'))
