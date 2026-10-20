"""Frame-backed NS2 artifacts, using existing attempt files and atomic publication.

The small index is metadata, NOT a second project format. Native arrays live in
individually pinned frame artifacts, just as the existing Post frame artifacts do.
Reading a frame never parses other frames. v1 remains a bounded read-only path.
"""
from collections.abc import Sequence
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import os
import re

from .adapters.frozen_fem import _read, _relative, _sha, MAX_BYTES
from .execution_control import check_cancelled
from .storage import canonical_hash, _publish_json

INDEX_LIMIT = 8 * 1024 * 1024


def _path(root, relative):
    path = Path(root) / _relative(relative)
    if (any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file()
            or not path.resolve().is_relative_to(Path(root).resolve())):
        raise ValueError('Missing, non-regular or escaped retained dynamic artifact: ' + relative)
    return path


def file_pin(root, path):
    root, path = Path(root), Path(path)
    relative = path.relative_to(root).as_posix()
    path = _path(root, relative)
    before = path.stat()
    digest = _sha(path)  # Existing streamed file hashing, never bounded JSON admission.
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino, before.st_dev) != (
            after.st_size, after.st_mtime_ns, after.st_ino, after.st_dev):
        raise ValueError('Dynamic artifact changed while being hashed: ' + relative)
    return {'relative': relative, 'bytes': after.st_size, 'sha256': digest}


def verify_pin(root, pin):
    if (not isinstance(pin, dict) or type(pin.get('bytes')) is not int or pin['bytes'] < 0
            or not isinstance(pin.get('sha256'), str) or re.fullmatch('[a-f0-9]{64}', pin['sha256']) is None):
        raise ValueError('A complete dynamic artifact pin is required')
    path = _path(root, pin['relative'])
    if file_pin(root, path) != {k: pin[k] for k in ('relative', 'bytes', 'sha256')}:
        raise ValueError('Retained dynamic artifact changed (hash/size): ' + pin['relative'])
    return path


def admit_pin(root, pin):
    """Metadata/path/size admission, NOT a content integrity success claim."""
    if (not isinstance(pin, dict) or type(pin.get('bytes')) is not int or pin['bytes'] < 0
            or not isinstance(pin.get('sha256'), str)
            or re.fullmatch('[a-f0-9]{64}', pin['sha256']) is None):
        raise ValueError('A complete dynamic artifact pin is required')
    path = _path(root, pin['relative'])
    if path.stat().st_size != pin['bytes']:
        raise ValueError('Retained dynamic artifact changed (size): ' + pin['relative'])
    return path


def _json(root, pin, limit=MAX_BYTES):
    path = _path(root, pin['relative'])
    payload = _read(path, limit)
    if len(payload) != pin['bytes'] or hashlib.sha256(payload).hexdigest() != pin['sha256']:
        raise ValueError('Retained dynamic artifact changed (hash/size): ' + pin['relative'])
    return json.loads(payload)


def _write(path, value, limit=MAX_BYTES):
    """One bounded frame (not the whole result) and the existing atomic publisher."""
    path = Path(path)
    if path.exists():
        raise ValueError('Retained dynamic artifacts are immutable; choose a new destination')
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False,
                         separators=(',', ':')).encode('utf-8')
    if len(payload) > limit:
        raise ValueError('Single dynamic artifact exceeds its bounded admission limit')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.caelab-', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _publish_json(temporary, path)
    except BaseException:
        # Only a complete published index is readable; raw outputs are not touched.
        raise


def _identity(data):
    return canonical_hash({k: data.get(k) for k in
        ('snapshot_id', 'source_pins', 'job_id', 'job_identity', 'input_origin', 'state_source',
         'execution_status', 'complete_analysis', 'stages', 'derivation')})


def frame_metadata(result):
    """Cheap exact selection: no frame-array read and no solver invocation."""
    if isinstance(result, RetainedResult):
        return deepcopy(result.index['frames'])
    return [{k: deepcopy(f[k]) for k in ('native', 'native_time_token', 'location')}
            | {'field_names': sorted(f.get('fields', {}))} for f in result['frames']]


def artifact_references(index):
    if isinstance(index, RetainedResult):
        index = index.index
    if index.get('version') == 1:
        return []
    return [index['topology'], *(f['artifact'] for f in index['frames']),
            *index.get('unassociated_artifacts', [])]


class _Frames(Sequence):
    def __init__(self, root, index):
        self.root, self.index = Path(root), index

    def __len__(self):
        return len(self.index['frames'])

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [self[j] for j in range(*i.indices(len(self)))]
        if type(i) is not int:
            raise TypeError('Use an exact integer result frame index')
        if i < 0:
            i += len(self)
        if i < 0 or i >= len(self):
            raise IndexError(i)
        meta = self.index['frames'][i]
        row = _json(self.root, meta['artifact'])
        if (row.get('kind') != 'calculix_dynamic_frame' or row.get('version') != 1
                or row.get('result_identity') != self.index['result_identity']
                or row.get('frame_index') != i):
            raise ValueError('Dynamic frame belongs to a different result/attempt/index')
        data = row['data']
        if (any(data.get(k) != meta[k] for k in ('native', 'native_time_token', 'location'))
                or sorted(data.get('fields', {})) != meta['field_names']):
            raise ValueError('Dynamic frame location or fields differ from its index')
        return data

    def __deepcopy__(self, memo):
        # Explicit copying is an explicit materialisation, not ordinary open/poll.
        return [deepcopy(f, memo) for f in self]


class _Unassociated(Sequence):
    def __init__(self, root, index):
        self.root, self.index = root, index

    def __len__(self):
        return len(self.index.get('unassociated_artifacts', []))

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [self[j] for j in range(*i.indices(len(self)))]
        row = _json(self.root, self.index['unassociated_artifacts'][i])
        if row.get('result_identity') != self.index['result_identity']:
            raise ValueError('Unassociated energy block belongs to a different result')
        return row['data']

    def __deepcopy__(self, memo):
        return [deepcopy(row, memo) for row in self]


class RetainedResult(dict):
    """Public dict-compatible result, with frame arrays fetched only on selection."""
    def __init__(self, root, index, metadata_only=False):
        self.index, self.root = deepcopy(index), Path(root)
        super().__init__(deepcopy(index))
        if not metadata_only:
            topology = _json(root, index['topology'])
            if topology.get('result_identity') != index['result_identity']:
                raise ValueError('Dynamic topology belongs to a different result')
            self.update(nodes=topology['nodes'], elements=topology['elements'])
            self['frames'] = _Frames(root, self.index)
            self['energy_unassociated_blocks'] = _Unassociated(root, self.index)

    def __deepcopy__(self, memo):
        return {key: deepcopy(value, memo) for key, value in self.items()}


def load_result(path, *, metadata_only=False, expected_pin=None):
    path = Path(path)
    # v1 compatibility is intentionally still bounded by MAX_BYTES, never raised.
    payload = _read(path)
    if expected_pin is not None and (len(payload)!=expected_pin.get('bytes') or
            hashlib.sha256(payload).hexdigest()!=expected_pin.get('sha256')):
        raise ValueError('Retained dynamic index changed (hash/size)')
    index = json.loads(payload)
    if index.get('kind') != 'calculix_dynamic_result':
        raise ValueError('Not a retained native dynamic result')
    if index.get('version') == 1:
        return index
    if index.get('version') != 2 or len(payload) > INDEX_LIMIT:
        raise ValueError('Unsupported or oversized dynamic result index')
    if index.get('result_identity') != _identity(index):
        raise ValueError('Dynamic result identity differs from its immutable index')
    frames = index.get('frames')
    if not isinstance(frames, list) or not 1 <= len(frames) <= 1024:
        raise ValueError('Expected 1..1024 retained exact frames')
    names = []
    for ref in artifact_references(index):
        name = _relative(ref['relative'])
        if not name.startswith('dynamic-frames/') or name in names:
            raise ValueError('Duplicate or foreign dynamic frame artifact')
        names.append(name)
        if ref['bytes'] > MAX_BYTES:
            raise ValueError('Dynamic frame exceeds bounded admission size limit')
    return RetainedResult(path.parent, index, metadata_only)


def write_result(output, model, frames, dat_path, *, execution_status, source_pins,
                 snapshot_id, extra_header=None):
    """Publish all frames once; index last. Raw inputs and legacy Post stay intact.

    DAT is scanned once into temporary per-frame blocks. At most one DAT block,
    one retained frame and three velocity samples are transformed at a time.
    The existing strict FRD reader still owns native parsing/admission.
    """
    from .dynamic_results import (result_header, validate_requested, accelerations,
                                  iter_energy_blocks, _empty_energy)
    from .contact_steps import compile_program
    from .dynamic_native_stream import frame_catalog
    from .calculix_dynamic import location
    from .adapters.fixture_field import _printed_close
    output, dat_path = Path(output), Path(dat_path)
    if (output / 'dynamic_result.json').exists() or (output / 'dynamic-frames').exists():
        raise ValueError('Choose a new immutable dynamic result destination')
    if not 1 <= len(frames) <= 1024:
        raise ValueError('Expected 1..1024 retained exact frames')
    validate_requested(model, frames)
    catalog = frame_catalog(frames)
    header = result_header(model, execution_status=execution_status,
                           source_pins=source_pins, snapshot_id=snapshot_id)
    if extra_header:
        allowed = {'job_id', 'job_identity', 'input_origin', 'state_source', 'native_execution', 'derivation'}
        if set(extra_header) - allowed:
            raise ValueError('Unsupported result provenance header')
        header.update(deepcopy(extra_header))
    header['version'] = 2
    header['result_identity'] = _identity(header)
    header['storage'] = 'existing_attempt_pinned_frame_artifacts'
    folder = output / 'dynamic-frames'
    folder.mkdir(parents=True)
    topology = {'result_identity': header['result_identity'],
                'nodes': header.pop('nodes'), 'elements': header.pop('elements')}
    _write(folder / 'topology.json', topology)
    header['topology'] = file_pin(output, folder / 'topology.json')
    header['energy_source'] = ({**file_pin(dat_path.parent, dat_path), 'relative': 'solver/contact.dat'}
                               if dat_path.is_file() else None)
    header['unassociated_artifacts'], header['frames'] = [], []
    stages = compile_program(model['analysis_steps'], model['conditions'])
    with tempfile.TemporaryDirectory(prefix='.dynamic-energy-', dir=output) as temporary:
        spool = Path(temporary)
        seen = set()
        for block in iter_energy_blocks(dat_path, model):
            check_cancelled()
            matches = [i for i, f in enumerate(catalog) if _printed_close(
                block['native_time_token'], f['static']['load_parameter'],
                reference_token=f['load_parameter_token'])]
            if len(matches) > 1:
                raise ValueError('Ambiguous native DAT to FRD energy time association')
            if not matches:
                block['association_reason'] = 'no_retained_converged_output_frame_at_this_time'
                path = folder / ('unassociated%06d.json' % len(header['unassociated_artifacts']))
                _write(path, {'result_identity': header['result_identity'], 'data': block})
                header['unassociated_artifacts'].append(file_pin(output, path))
            else:
                key = matches[0], block['quantity']
                if key in seen:
                    raise ValueError('Duplicate native energy block for one output frame')
                seen.add(key)
                # Temporary derivation only; the final frame atomically retains the block.
                (spool / ('%d-%s.json' % key)).write_text(
                    json.dumps(block, allow_nan=False, separators=(',', ':')), encoding='utf-8')
        for i, frame in enumerate(frames):
            check_cancelled()
            native = frame['static']
            if (i > 0 and i + 1 < len(frames) and
                    catalog[i-1]['static']['step'] == native['step'] == catalog[i+1]['static']['step']):
                acceleration = accelerations(model, frames[i-1:i+2])[1]
                if 'source_frames' in acceleration:
                    acceleration['source_frames'] = [j+i-1 for j in acceleration['source_frames']]
            else:
                acceleration = accelerations(model, [frame])[0]
            energy = _empty_energy()
            for q in energy:
                path = spool / ('%d-%s.json' % (i, q))
                if path.is_file():
                    energy[q] = json.loads(_read(path))
            loc = location(model, native['step'], native['load_parameter'])
            data = {'native': native, 'native_time_token': frame['load_parameter_token'],
                    'location': loc, 'fields': frame['fields'], 'acceleration': acceleration,
                    'energy': energy,
                    'restrained_dofs': [list(k) for k in sorted(stages[native['step']-1]['boundary'])]}
            path = folder / ('frame%04d.json' % (i+1))
            _write(path, {'kind': 'calculix_dynamic_frame', 'version': 1,
                         'result_identity': header['result_identity'], 'frame_index': i, 'data': data})
            header['frames'].append({'native': deepcopy(native), 'location': loc,
                                     'native_time_token': frame['load_parameter_token'],
                                     'field_names': sorted(frame['fields']), 'artifact': file_pin(output, path)})
    for name, pin in source_pins.items():
        verify_pin(output, {'relative': name, **pin})
    check_cancelled()
    _write(output / 'dynamic_result.json', header, INDEX_LIMIT)
    return load_result(output / 'dynamic_result.json')


def read_attempt(attempt, *, metadata_only=False, verification='selected',
                 expected_result=None, expected_job_id=None, expected_snapshot_id=None, expected_record=None):
    """Cold open without hashing all raw outputs or frame arrays.

    Index/attempt membership and paths/sizes are checked here; topology is checked
    when loaded, every selected frame is hash checked by _Frames. 'full' is the
    explicit whole-dependency audit. No verification scope is labelled ALL unless
    all bytes were actually checked in this call; no persistent trust cache.
    """
    if verification not in ('selected', 'full'):
        raise ValueError('Choose selected or explicit full integrity verification')
    attempt = Path(attempt).resolve(strict=True)
    record_bytes = _read(attempt / 'contact_execution.json', INDEX_LIMIT)
    if expected_record is not None and (expected_record.get('relative')!='contact_execution.json' or
            expected_record.get('bytes')!=len(record_bytes) or
            expected_record.get('sha256')!=hashlib.sha256(record_bytes).hexdigest()):
        raise ValueError('Original selected attempt record changed')
    record = json.loads(record_bytes)
    reference = record.get('dynamic_result')
    if not reference:
        raise ValueError('This attempt has no retained dynamic result')
    pin = {k: reference[k] for k in ('relative', 'bytes', 'sha256')}
    if expected_result is not None and pin != {k: expected_result[k] for k in pin}:
        raise ValueError('Selected dynamic result differs from the expected exact result')
    if expected_job_id is not None and record.get('job_id') != expected_job_id:
        raise ValueError('Selected dynamic result belongs to a different job')
    if expected_snapshot_id is not None and record.get('snapshot_id') != expected_snapshot_id:
        raise ValueError('Selected dynamic result belongs to a different input')
    path = admit_pin(attempt,pin)
    result = load_result(path, metadata_only=metadata_only, expected_pin=pin)
    artifacts = record.get('artifacts', [])
    entries = {row['relative']: row for row in artifacts}
    if len(entries) != len(artifacts):
        raise ValueError('Duplicate attempt artifact references')
    required = [{'relative': name, **p} for name, p in result['source_pins'].items()]
    required += [pin, *artifact_references(result)]
    for item in required:
        expected = {k: item[k] for k in ('relative', 'bytes', 'sha256')}
        retained = entries.get(item['relative'], {})
        if {key: retained.get(key) for key in expected} != expected:
            raise ValueError('Dynamic result is not pinned by this exact attempt: ' + item['relative'])
        (verify_pin if verification == 'full' else admit_pin)(attempt, expected)
    if (record.get('snapshot_id') != result.get('snapshot_id') or
            record.get('job_id') != result.get('job_id') or
            record.get('job_identity') != result.get('job_identity') or
            record.get('input_origin') != result.get('input_origin') or
            record.get('execution_status') != result.get('execution_status')):
        raise ValueError('Dynamic result belongs to a different job/input/status')
    if _read(attempt / 'contact_execution.json', INDEX_LIMIT) != record_bytes:
        raise ValueError('Attempt changed during retained open')
    # Attributes do not change the immutable result/index or exported field values.
    if isinstance(result, RetainedResult):
        result.verification = {
            'scope': 'ALL_REFERENCED_BYTES' if verification == 'full' else
                     ('INDEX_ONLY' if metadata_only else 'INDEX_AND_TOPOLOGY'),
            'attempt_record_sha256': hashlib.sha256(record_bytes).hexdigest(),
            'result': pin, 'paths_and_sizes': 'CHECKED',
            'raw_source_bytes': 'VERIFIED' if verification == 'full' else 'DEFERRED',
            'unselected_frame_bytes': 'VERIFIED' if verification == 'full' else 'DEFERRED',
            'selected_frame_policy': 'HASH_AND_EXACT_IDENTITY_BEFORE_RETURN',
            'engineering_qualification': 'UNKNOWN'}
    return result


def verify_attempt(attempt, **expected):
    """Explicit audit; byte reads are deliberate and never launch a solver."""
    result = read_attempt(attempt, verification='full', metadata_only=True, **expected)
    return deepcopy(getattr(result, 'verification', {'scope': 'ALL_REFERENCED_BYTES',
                    'legacy_v1': True, 'engineering_qualification': 'UNKNOWN'}))


def select_frame(attempt, frame_index, *, expected_native=None, **expected):
    """Select verified payload + topology, never metadata labelled as evidence.

    metadata_only=False remains accepted for callers sharing read_attempt options.
    For metadata-only navigation use describe_attempt/read_attempt instead.
    """
    if expected.pop('metadata_only', False) is not False:
        raise ValueError('select_frame requires payload verification; '
                         'use describe_attempt for metadata-only navigation')
    result = read_attempt(attempt, metadata_only=False, **expected)
    catalog = frame_metadata(result)
    if type(frame_index) is not int or not 0 <= frame_index < len(catalog):
        raise ValueError('Choose an exact result frame index')
    if expected_native is not None and catalog[frame_index]['native'] != expected_native:
        raise ValueError('Selected native step/increment/coordinate differs')
    frame = result['frames'][frame_index]
    verification = deepcopy(getattr(result, 'verification', {'legacy_v1': True}))
    verification.update(selected_frame_index=frame_index, selected_frame_bytes='VERIFIED')
    return {'frame': frame, 'verification': verification,
            'execution_status': result['execution_status'], 'qualification': result['qualification']}


def describe_attempt(attempt, **expected):
    """Serializable catalogue and truthful integrity scope; no native array read."""
    data=read_attempt(attempt,metadata_only=True,**expected)
    return {'kind':'retained_dynamic_catalog','snapshot_id':data['snapshot_id'],
            'job_id':data.get('job_id'),'job_identity':deepcopy(data.get('job_identity')),
            'execution_status':data['execution_status'],'complete_analysis':data['complete_analysis'],
            'qualification':'UNKNOWN','frames':frame_metadata(data),
            'verification':deepcopy(getattr(data,'verification',{
                'scope':'BOUNDED_LEGACY_V1_MATERIALIZED','raw_source_bytes':'DEFERRED',
                'engineering_qualification':'UNKNOWN'})),
            'solver_execution':'NOT_PERFORMED'}
