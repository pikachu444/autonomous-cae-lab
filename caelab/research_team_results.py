"""Exact physical selections over retained owners; no execution or access grants.

The binding owns permission and durable tool reuse. Callbacks here are captured
by the current owner, never accepted from model JSON or portable documents.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
import json
import math
import uuid

from .research_operations import validate_result_reference
from .storage import canonical_hash


def new_id(prefix):
    return prefix + uuid.uuid4().hex


PHYSICAL = ('response', 'association', 'component', 'unit', 'measure', 'frame', 'coordinate_system')
AXES = ('location_ids', 'frame_indices', 'row_intervals')
CHANNEL_KEYS = set(PHYSICAL + AXES)
READ_LIMITS = {'max_rows': 1024, 'max_values': 16384, 'max_bytes': 20000}
ANALYSIS_LIMITS = {'max_calls': 1, 'max_rows': 2048, 'max_columns': 16,
                   'max_input_bytes': 1048576, 'max_output_bytes': 262144}


class UnsupportedSelection(ValueError):
    code = 'UNSUPPORTED_SELECTION'


def _need(value, message):
    if not value:
        raise ValueError(message)


def _bytes(value):
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8'))


def _limits(value, maxima):
    _need(isinstance(value, dict) and set(value) == set(maxima), 'Declare every result/analysis limit')
    _need(all(type(value[k]) is int and 0 < value[k] <= maximum for k, maximum in maxima.items()),
          'Requested limits exceed the supported bounded read/analysis')
    return deepcopy(value)


def probe_retained_result(reference, *, resolve_document, verify_retention):
    """Verify storage identity before a numeric reader is called.

    verify_retention(reference, document) returns authoritative reference,
    descriptor and verified_storage_ref from the owning saved revision. It must
    verify saved bytes, not use a caller hash as its observed result hash.
    """
    reference = validate_result_reference(reference)
    document = resolve_document(reference['document_id'])
    _need(document.get('id') == reference['document_id'], 'Result owner differs')
    run = next((r for r in document.get('runs', []) if r.get('job_id') == reference['job_id']), None)
    _need(run is not None and run.get('retention_complete') and run.get('retained_result') and
          all(run.get(k) == reference[k] for k in ('input_revision', 'input_sha256')),
          'Save the exact submitted result before selecting it')
    verified = verify_retention(deepcopy(reference), document)
    _need(validate_result_reference(verified['reference']) == reference, 'Retained result identity changed')
    descriptor = deepcopy(verified['descriptor'])
    _need(isinstance(descriptor.get('channels'), list), 'Owner has no physical result descriptor')
    return {'reference': reference, 'descriptor': descriptor,
            'descriptor_digest': canonical_hash(descriptor),
            'verified_storage_ref': deepcopy(verified['verified_storage_ref'])}


def _intervals(value):
    _need(isinstance(value, list) and value, 'Select nonempty original row intervals')
    rows = []
    for pair in value:
        _need(isinstance(pair, list) and len(pair) == 2 and all(type(v) is int for v in pair)
              and 0 <= pair[0] < pair[1], 'Rows use nonnegative half-open original intervals')
        rows.append(pair[:])
    rows.sort()
    _need(all(left[1] <= right[0] for left, right in zip(rows, rows[1:])), 'Original row intervals overlap')
    return rows


def _members(value, name):
    if value is None:
        return None
    _need(isinstance(value, list) and value and len(value) <= 16384 and
          len({canonical_hash(v) for v in value}) == len(value), 'Select distinct ' + name)
    if name == 'frame_indices':
        _need(all(type(v) is int and v >= 0 for v in value), 'Choose exact original frame indices')
    else:
        _need(all(isinstance(v, (str, int)) and not isinstance(v, bool) for v in value),
              'Choose actual reader location identities')
    return deepcopy(value)


def _canonical(channel, definition):
    _need(isinstance(channel, dict) and not set(channel) - CHANNEL_KEYS, 'Unsupported physical selection fields')
    result = {}
    for key in PHYSICAL:
        actual = definition.get(key)
        _need(channel.get(key, actual) == actual, 'Physical definition differs: ' + key)
        result[key] = deepcopy(actual)
    for key in AXES:
        value = channel.get(key, definition.get(key))
        result[key] = _intervals(value) if key == 'row_intervals' and value is not None else _members(value, key)
    pairs = definition.get('frame_rows')
    if pairs is not None:
        rows = {row for frame, row in pairs if any(a <= row < b for a, b in result['row_intervals'])}
        frames = result['frame_indices']
        selected = [(f, r) for f, r in pairs if f in frames and r in rows]
        _need(selected, 'No matching original frame/row samples')
        if 'frame_indices' in channel and 'row_intervals' in channel:
            _need({r for f, r in selected} == rows and {f for f, r in selected} == set(frames),
                  'Frame and original row identities disagree')
        result['frame_indices'] = [f for f, r in selected]
        result['row_intervals'] = _row_intervals([r for f, r in selected])
    return result


def _row_intervals(rows):
    intervals = []
    for row in sorted(set(rows)):
        if intervals and row == intervals[-1][1]:
            intervals[-1][1] += 1
        else:
            intervals.append([row, row + 1])
    return intervals


def descriptor_from_metadata(result, *, selector_value=lambda value: value):
    """Catalog stored definitions and identity axes, never field/curve values.

    The owner supplies selector_value only for saved source-row/time arrays.
    Numeric response values remain packed until the exact read is admitted.
    """
    channels = []
    candidates = result.get('candidates')
    if isinstance(candidates, list):
        definitions = {}
        for row in candidates:
            for name, response in row.get('responses', {}).items():
                definition = {key: deepcopy(response.get(key)) for key in PHYSICAL}
                definition.update(response=name, kind=response.get('kind'), location_ids=(
                    [response['location']] if response.get('location') is not None else None),
                    frame_indices=None, row_intervals=[[0, len(candidates)]] if candidates else None,
                    reader_rows=list(range(len(candidates))), candidate_table=True)
                if response.get('label'):
                    definition['label'] = response['label']
                definitions[canonical_hash(definition)] = definition
        channels.extend(definitions.values())
    for name, response in result.get('responses', {}).items():
        kind = response.get('kind')
        if kind not in {'scalar', 'series', 'field'}:
            continue
        definition = {key: deepcopy(response.get(key)) for key in PHYSICAL}
        definition['response'] = name
        if response.get('label'):
            definition['label'] = response['label']
        definition['location_ids'] = [response['location']] if response.get('location') is not None else None
        definition.update(kind=kind, frame_indices=None, row_intervals=None, supported=True)
        if kind in {'series', 'field'}:
            value = response.get('value')
            count = len(value) if isinstance(value, list) else (value or {}).get('data_ref', {}).get('shape', [0])[0]
            if not count:
                continue
            original = response.get('source_rows')
            rows = selector_value(original) if original is not None else list(range(count))
            if not (isinstance(rows, list) and len(rows) == count and
                    all(type(r) is int and r >= 0 for r in rows) and len(set(rows)) == count):
                raise UnsupportedSelection('Original row catalog has no distinct supported identities')
            definition['row_intervals'] = _row_intervals(rows)
            definition['reader_rows'] = rows
            definition['supported'] = kind != 'field' or original is not None
            shape = (value or {}).get('data_ref', {}).get('shape', []) if isinstance(value, dict) else []
            definition['value_width'] = 1
            for size in shape[1:]:
                definition['value_width'] *= size
            time_axis = next((a for a in response.get('axes', []) if a.get('name') == 'time'), None)
            if kind == 'series' and time_axis is not None:
                times = selector_value(time_axis.get('values'))
                if not (isinstance(times, list) and len(times) == count and
                        all(type(t) in (int, float) and math.isfinite(t) for t in times)):
                    raise UnsupportedSelection('Stored time/frame catalog has no supported exact mapping')
                definition.update(frame_indices=list(range(count)), frame_rows=list(map(list, enumerate(rows))),
                                  times=deepcopy(times), time_unit=time_axis.get('unit'))
        channels.append(definition)
    unsupported = [{'label': d.get('label', name),
        'reason': '이 결과 항목은 현재 연구팀에 첨부할 수 없습니다. 기존 결과 화면에서 확인하세요.'}
        for name, d in result.get('native_channels', {}).items() if name not in result.get('responses', {})]
    if unsupported and not channels:
        raise UnsupportedSelection(unsupported[0]['reason'])
    return {'channels': channels, 'execution_status': result.get('execution_status', 'UNKNOWN'),
            **({'unsupported_channels': unsupported} if unsupported else {}),
            'analysis_table': isinstance(result.get('candidates'), list),
            'candidate_count': len(result.get('candidates', [])),
            'candidate_ids': [r.get('candidate_id') for r in result.get('candidates', [])],
            'variables': deepcopy(result.get('variables', []))}


def _owner_snapshot(wb, reference):
    from .evaluation import read_result, file_hash
    from .research_workflows import result_folder
    owner = wb._document_owner(reference['document_id'])
    document = owner.read(reference['document_id'])
    run = next((r for r in document.get('runs', []) if r.get('job_id') == reference['job_id']), None)
    _need(run is not None and run.get('retained_result') and run.get('retention_complete'), 'Result is not retained')
    revision = run['retained_result']['revision']
    owner._verify_revision(reference['document_id'], revision)
    folder, _ = result_folder(wb, reference['document_id'], reference['job_id'])
    manifest_path = owner._folder(reference['document_id']) / 'revisions' / revision / 'revision.json'
    identity = {'document_id': reference['document_id'], 'retained_revision': revision,
                'revision_sha256': file_hash(manifest_path)}
    metadata = read_result(folder, verify='all', selection={'metadata_only': True})
    def selector_value(value):
        if isinstance(value, dict) and set(value) == {'data_ref'}:
            from .workbench import contained
            import numpy as np
            ref = value['data_ref']
            path = contained(folder, ref['path'])
            _need(file_hash(path) == ref['sha256'], 'Selector identity array changed')
            return np.load(path, allow_pickle=False).tolist()
        return deepcopy(value)
    return identity, metadata, descriptor_from_metadata(metadata, selector_value=selector_value)


def capture_result_verification(wb, reference):
    """Explicit attachment only: bind existing canonical reference to saved bytes.

    The Discussion owner must retain this in its existing input snapshot. This
    helper is never exposed as a model tool, nor called to repair a missing grant.
    """
    reference = validate_result_reference(reference)
    before, _, _ = _owner_snapshot(wb, reference)
    actual = wb.document_result_reference(reference['document_id'], reference['job_id'])
    _need(actual == reference, 'The explicitly attached result reference changed')
    after, _, descriptor = _owner_snapshot(wb, reference)
    _need(before == after, 'Result changed while attaching its verification')
    return {'reference': actual, 'verified_storage_ref': after, 'result_files': retained_result_files(wb, actual, after), 'descriptor': descriptor,
            'descriptor_digest': canonical_hash(descriptor)}


def retained_result_files(wb, reference, storage):
    """The existing verified revision's exact result-file inventory, no values.

    Owner/revision names may change in a portable copy; these declared result
    bytes do not. Old receipts are not silently recaptured to create this proof.
    """
    from .storage import load_json
    owner = wb._document_owner(reference['document_id'])
    owner._verify_revision(reference['document_id'], storage['retained_revision'])
    manifest = load_json(owner._folder(reference['document_id']) / 'revisions' /
                         storage['retained_revision'] / 'revision.json')
    prefix = 'results/' + reference['job_id'] + '/'
    files = {r['path'][len(prefix):]: r['sha256'] for r in manifest['files'] if r['path'].startswith(prefix)}
    _need(files and 'result.json' in files, 'The retained result file inventory is unavailable')
    return files


def describe_result_selection(wb, document_id, job_id):
    """Additive metadata for the existing human result picker, without capture."""
    document = wb.document_read(document_id)
    run = next((r for r in document.get('runs', []) if r.get('job_id') == job_id), None)
    if run is None or not run.get('retention_complete') or not run.get('retained_result'):
        return None
    try:
        identity, _, descriptor = _owner_snapshot(wb, {'document_id': document_id, 'job_id': job_id})
    except UnsupportedSelection as error:
        return {'status': error.code, 'reason': str(error)}
    return {'status': 'AVAILABLE', 'descriptor': descriptor, 'descriptor_digest': canonical_hash(descriptor), 'verified_storage_ref': identity}


def prepare_result_update(owner, document, arguments):
    """Called on the command's private copy after CAS, before APPLYING is saved."""
    from types import SimpleNamespace
    from .research_team_contract import enabled, validate_draft
    from .discussion_research_team import retain_result_verification, resolve_asset
    draft = arguments.get('draft')
    if not isinstance(draft, dict) or not enabled(draft):
        return
    # Invalid authored drafts remain editable; they cannot acquire verification
    # evidence or pass the existing Ask validation gate.
    if owner.diagnostics(draft) or validate_draft(draft, owner.list_experts()):
        return
    selections = [r for a in draft['context']['research_team']['assignments'] for r in a['result_refs']]
    existing = document.get('discussion', {}).get('research_team', {}).get('result_verifications', {})
    prior_selections = {canonical_hash(r) for a in document.get('draft', {}).get('context', {}).get(
        'research_team', {}).get('assignments', []) for r in a.get('result_refs', [])}
    captures = {}
    for selected in selections:
        reference = validate_result_reference(selected['reference'])
        key = canonical_hash(reference)
        if key in captures:
            receipt = captures[key]
        elif key in existing:
            receipt = resolve_asset(SimpleNamespace(owner=owner, owner_id=document['id']), existing[key])
        else:
            # Editing/saving existing or relocated selections never manufactures
            # new authority. An explicit picker adoption supplies a new wrapper.
            if canonical_hash(selected) in prior_selections:
                continue
            capture = getattr(owner, 'capture_result_verification', None)
            _need(callable(capture), 'Explicit result attachment is unavailable in this owner')
            receipt = capture(reference)
            captures[key] = receipt
        _need(receipt['reference'] == reference and selected['descriptor_ref'] == receipt['descriptor_digest'],
              'Selected response descriptor no longer matches the exact result')
        verified = {'reference': reference, **{k: receipt[k] for k in
            ('descriptor', 'descriptor_digest', 'verified_storage_ref')}}
        normalized = make_result_selection(verified, source_id=selected['source_id'],
            selection_request=selected['selector'], read_limits=selected['read_limits'])
        _need(normalized == selected, 'Choose a canonical selection from the actual result catalog')
    # Publish no partial registrations when a later selected reference fails.
    for receipt in captures.values():
        retain_result_verification(owner, document, receipt)


def workbench_readers(wb, *, verification_receipts):
    """Capture this Workbench and the current Discussion's trusted asset lookup."""
    def verify(reference, document):
        receipt = verification_receipts(deepcopy(reference))
        _need(isinstance(receipt, dict) and receipt.get('reference') == reference,
              'Explicit owner-issued result verification is unavailable')
        identity, metadata, descriptor = _owner_snapshot(wb, reference)
        _need(identity == receipt['verified_storage_ref'] and descriptor == receipt['descriptor'] and
              canonical_hash(descriptor) == receipt['descriptor_digest'], 'Retained verification no longer matches source bytes')
        return {'reference': deepcopy(receipt['reference']), 'descriptor': descriptor, 'verified_storage_ref': identity}
    def probe(reference):
        return probe_retained_result(reference, resolve_document=wb.document_read, verify_retention=verify)
    def read(reference, channel):
        descriptor = probe(reference)
        definition = next(d for d in descriptor['descriptor']['channels'] if
                          all(d.get(k) == channel[k] for k in PHYSICAL))
        if definition.get('candidate_table'):
            indices = [i for i in range(descriptor['descriptor']['candidate_count'])
                       if any(a <= i < b for a, b in channel['row_intervals'])]
            selected_ids = [descriptor['descriptor']['candidate_ids'][i] for i in indices]
            result = wb.document_result(reference['document_id'], reference['job_id'],
                selection={'candidate_ids': selected_ids, 'responses': [channel['response']]})
            responses = [r.get('responses', {}).get(channel['response']) for r in result['candidates']]
            # Keep original failed rows and their missing values, never fill zero.
            response = {key: deepcopy(channel[key]) for key in ('unit', 'component', 'measure', 'frame', 'coordinate_system', 'association')}
            response.update(kind='candidate_rows', value=[deepcopy(r.get('value')) if r else None for r in responses],
                candidate_ids=selected_ids, execution_statuses=[r['execution_status'] for r in result['candidates']],
                original_rows=indices)
        elif definition['kind'] == 'scalar':
            result = wb.document_result(reference['document_id'], reference['job_id'],
                                        selection={'responses': [channel['response']]})
            response = result['responses'][channel['response']]
        else:
            rows = definition['reader_rows']
            positions = [i for i, r in enumerate(rows) if any(a <= r < b for a, b in channel['row_intervals'])]
            if definition['kind'] == 'field' and definition.get('association') is None:
                # Row-addressed field reads are supported by the existing reader;
                # vectors/components without an actual declaration are not invented.
                pass
            intervals = _row_intervals(positions)
            pieces = []
            for start, stop in intervals:
                selection = {'responses': [channel['response']], 'rows': [start, stop]}
                if definition['kind'] == 'field':
                    if not channel['row_intervals']:
                        raise UnsupportedSelection('This field has no original-row selector')
                    selection['source_rows'] = rows[start:stop]
                actual = wb.document_result(reference['document_id'], reference['job_id'], selection=selection)
                piece = actual['responses'][channel['response']]
                _need(len(piece['value']) == stop - start, 'Reader did not return the exact original rows')
                pieces.append(piece)
            _need(pieces, 'No exact stored samples selected')
            response = deepcopy(pieces[0])
            if len(pieces) > 1:
                for key in ('value', 'source_rows', 'mask'):
                    if key in response:
                        response[key] = [v for p in pieces for v in p[key]]
                for index, axis in enumerate(response.get('axes', [])):
                    axis['values'] = [v for p in pieces for v in p['axes'][index]['values']]
        return {'response': response, 'returned_selector': deepcopy(channel)}
    return {'probe': probe, 'read': read}


def analysis_input_factory(wb, *, readers):
    """Resolve an admitted candidate subset through the existing retained reader."""
    def describe(source, definitions, limits):
        descriptor = readers['probe'](source['reference'])
        catalog = descriptor['descriptor']
        _need(catalog['analysis_table'], 'Select a retained Numerical/table result for analyze')
        selector = normalize_selection(descriptor, source['selector'], granted_selector=source['selector'])
        _need(not selector['metadata_only'], 'Metadata is not a numerical analysis input')
        chosen_rows = None
        for definition in definitions:
            matches = [c for c in selector['channels'] if c['response'] == definition['response'] and
                       all(c.get(k) == definition.get(k, c.get(k)) for k in
                           ('unit', 'component', 'measure', 'frame', 'coordinate_system'))]
            _need(len(matches) == 1, 'Analysis response/physical definition is outside the selected source')
            channel = matches[0]
            rows = [i for i in range(catalog['candidate_count']) if any(a <= i < b for a, b in channel['row_intervals'])]
            _need(chosen_rows is None or chosen_rows == rows, 'Analysis columns must use the same exact original rows')
            chosen_rows = rows
        columns = len(catalog['variables']) + len(definitions)
        _need(chosen_rows and len(chosen_rows) <= limits['max_rows'] and columns <= limits['max_columns'],
              'Analysis rows/columns exceed the explicit limit')
        ids = [catalog['candidate_ids'][i] for i in chosen_rows]
        selection = {'candidate_ids': ids, 'responses': [d['response'] for d in definitions]}
        metadata = wb.document_result(source['reference']['document_id'], source['reference']['job_id'],
                                      selection={**selection, 'metadata_only': True})
        def estimate(value):
            if isinstance(value, dict) and set(value) == {'data_ref'}:
                count = 1
                for size in value['data_ref']['shape']:
                    count *= size
                return count * 32  # Conservative numeric JSON bound, not RSS.
            if isinstance(value, dict):
                return sum(estimate(v) for v in value.values())
            if isinstance(value, list):
                return sum(estimate(v) for v in value)
            return 0
        estimate_bytes = _bytes(metadata) + estimate(metadata)
        _need(estimate_bytes <= limits['max_input_bytes'], 'Analysis source bytes exceed the explicit limit')
        table = wb.document_result(source['reference']['document_id'], source['reference']['job_id'], selection=selection)
        _need(readers['probe'](source['reference']) == descriptor, 'Analysis source changed while resolving inputs')
        return {'rows': len(chosen_rows), 'columns': columns, 'input_bytes': estimate_bytes,
                'validated_inputs': {'table': table, 'responses': deepcopy(definitions)},
                'source_receipt_ids': [source.get('receipt_id', 'R' + canonical_hash({'reference': source['reference'], 'selector': selector})[:32])],
                'source_receipts': [{'reference': deepcopy(source['reference']), 'returned_selector': selector,
                    'payload_digest': canonical_hash(table), 'verification': 'VERIFIED'}],
                'input_dependencies': deepcopy(source.get('input_dependencies', []))}
    return describe


def _covers_intervals(wanted, grants):
    if wanted is None:
        return any(g is None for g in grants)
    if any(g is None for g in grants):
        return False  # null is an irrelevant axis, never an unbounded wildcard.
    merged = []
    for lo, hi in sorted(pair for grant in grants for pair in grant):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return all(any(a <= lo and hi <= b for a, b in merged) for lo, hi in wanted)


def _subset(channel, grants):
    matching = [g for g in grants if all(g.get(k) == channel.get(k) for k in PHYSICAL)]
    # Keep location/frame combinations together; independent field unions would
    # accidentally grant X@B when only X@A and Y@B were selected.
    locations = channel['location_ids'] or [None]
    frames = channel['frame_indices'] or [None]
    _need(len(locations) * len(frames) <= 16384, 'Selection combination limit exceeded')
    for location in locations:
        for frame in frames:
            candidates = [g for g in matching if
                          (location in g['location_ids'] if g['location_ids'] is not None else location is None) and
                          (frame in g['frame_indices'] if g['frame_indices'] is not None else frame is None)]
            if not candidates or not _covers_intervals(channel['row_intervals'], [g['row_intervals'] for g in candidates]):
                return False
    return True


def normalize_selection(descriptor, selection_request, *, granted_selector):
    catalog = descriptor['descriptor']['channels']
    _need(canonical_hash(descriptor['descriptor']) == descriptor['descriptor_digest'], 'Result descriptor changed')
    _need(isinstance(granted_selector, dict) and set(granted_selector) == {'metadata_only', 'channels'},
          'Choose an exact granted selector')
    request = deepcopy(granted_selector if selection_request is None else selection_request)
    _need(isinstance(request, dict) and set(request) == {'metadata_only', 'channels'} and
          type(request['metadata_only']) is bool and isinstance(request['channels'], list) and
          len(request['channels']) <= 512, 'Choose bounded canonical channels')
    _need(request['metadata_only'] or request['channels'], 'A value read needs a physical channel')
    _need(not granted_selector['metadata_only'] or request['metadata_only'], 'Metadata grant cannot read values')
    normalized, grants = [], []
    for group, target in ((granted_selector['channels'], grants), (request['channels'], normalized)):
        for channel in group:
            definitions = [d for d in catalog if all(channel.get(k, d.get(k)) == d.get(k) for k in PHYSICAL)]
            _need(len(definitions) == 1, 'Select one actual, unambiguous physical response definition')
            definition = definitions[0]
            if not request['metadata_only'] and definition.get('supported') is False:
                raise UnsupportedSelection('This field has no supported original-row selection')
            canonical = _canonical(channel, definition)
            full = _canonical({}, definition)
            _need(_subset(canonical, [full]), 'Requested sample is absent from the original descriptor')
            target.append(canonical)
    _need(all(_subset(c, grants) for c in normalized), 'Selection exceeds the granted physical sample combinations')
    return {'metadata_only': request['metadata_only'], 'channels': normalized}


def make_result_selection(descriptor, *, source_id, selection_request=None, read_limits=None):
    """Build a UI wrapper from owner metadata; this does not issue permission."""
    _need(isinstance(source_id, str) and bool(source_id), 'Choose a result selection identity')
    catalog = descriptor['descriptor']['channels']
    full = {'metadata_only': False, 'channels': [_canonical({}, d) for d in catalog]}
    selected = normalize_selection(descriptor, selection_request, granted_selector=full)
    return {'source_id': source_id, 'reference': deepcopy(descriptor['reference']), 'selector': selected,
            'descriptor_ref': descriptor['descriptor_digest'],
            'read_limits': _limits(read_limits or READ_LIMITS, READ_LIMITS)}


def _sample_count(channel):
    rows = sum(stop - start for start, stop in channel['row_intervals']) if channel['row_intervals'] else 1
    return rows * (len(channel['location_ids']) if channel['location_ids'] else 1)


def read_selected_result(reference, canonical_selector, *, readers, read_limits):
    """Read only compiled original samples, with source checks before and after."""
    limits = _limits(read_limits, READ_LIMITS)
    before = readers['probe'](reference)
    selector = normalize_selection(before, canonical_selector, granted_selector=canonical_selector)
    _need(selector['metadata_only'] or sum(_sample_count(c) for c in selector['channels']) <= limits['max_rows'],
          'Selected rows exceed the read limit')
    expected_values = sum(_sample_count(c) * next(d.get('value_width', 1) for d in before['descriptor']['channels']
        if all(d.get(k) == c[k] for k in PHYSICAL)) for c in selector['channels'])
    _need(selector['metadata_only'] or expected_values <= limits['max_values'], 'Selected values exceed the read limit')
    _need(_bytes(selector) <= limits['max_bytes'], 'Selection metadata exceeds its read limit')
    chunks, returned = [], []
    if not selector['metadata_only']:
        for channel in selector['channels']:
            actual = readers['read'](deepcopy(reference), deepcopy(channel))
            # The adapter reports the exact selection it actually read, not a
            # model request echoed as a success receipt.
            _need(actual['returned_selector'] == channel, 'Reader returned a different physical selection')
            response = actual['response']
            for key in ('unit', 'component', 'measure', 'frame', 'coordinate_system', 'association'):
                _need(response.get(key) == channel[key], 'Reader returned a different ' + key)
            chunks.append({'selection': deepcopy(channel), 'response': deepcopy(response)})
            returned.append(deepcopy(actual['returned_selector']))
    after = readers['probe'](reference)
    _need(before == after, 'Retained result changed during the read')
    payload = {'reference': deepcopy(reference), 'execution_status': before['descriptor'].get('execution_status', 'UNKNOWN'),
               'channels': chunks}
    if selector['metadata_only']:
        shown = []
        for channel in selector['channels']:
            definition = next(d for d in before['descriptor']['channels'] if all(d.get(k) == channel[k] for k in PHYSICAL))
            item = {**deepcopy(channel), 'kind': definition.get('kind')}
            if definition.get('label'):
                item['label'] = definition['label']
            if definition.get('times') is not None and channel['frame_indices'] is not None:
                item['times'] = [definition['times'][i] for i in channel['frame_indices']]
                item['time_unit'] = definition.get('time_unit')
            shown.append(item)
        payload['descriptor'] = {'channels': shown, 'execution_status': payload['execution_status']}
    values = sum(_count_values(c['response'].get('value')) for c in chunks)
    _need(values <= limits['max_values'] and _bytes(payload) <= limits['max_bytes'], 'Read payload exceeds its explicit limit')
    actual_selector = {'metadata_only': selector['metadata_only'], 'channels': returned if chunks else selector['channels']}
    receipt = {'id': new_id('R'), 'reference': deepcopy(reference), 'requested_selector': selector,
               'returned_selector': actual_selector, 'definition_ref': before['descriptor_digest'],
               'verification': 'VERIFIED', 'status': payload['execution_status'], 'payload_ref': None,
               'payload_digest': canonical_hash(payload), 'limitations': []}
    return {'payload': payload, 'receipt': receipt}


def _count_values(value):
    if isinstance(value, list):
        return sum(_count_values(v) for v in value)
    return 0 if value is None else 1


_SEAL = object()


@dataclass(frozen=True)
class PreparedAnalysis:
    id: str
    scope_revision: str
    source_receipt_ids: tuple
    operation: str
    validated_inputs: dict
    resources: dict
    limits: dict
    input_dependencies: tuple
    request_digest: str
    _revalidate: object = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)
    _state: dict = field(default_factory=lambda: {'status': 'PREPARED'}, repr=False, compare=False)
    _lock: object = field(default_factory=RLock, repr=False, compare=False)


def _analysis_digest(inputs, resources, limits, revision, receipts, dependencies):
    return canonical_hash({'inputs': inputs, 'resources': resources, 'limits': limits,
        'scope_revision': revision, 'source_receipt_ids': list(receipts), 'input_dependencies': list(dependencies)})


def prepare_analysis(request, *, scope, result_access, describe_inputs, describe_resources):
    """Resolve owner data under an explicit grant; preparing never executes math."""
    _need(isinstance(request, dict) and not set(request) - {'source_id', 'selection', 'responses', 'options', 'resources'},
          'Analysis accepts selected sources, never model tables, paths or numbers')
    analysis = scope.get('analysis') if isinstance(scope, dict) else None
    _need(isinstance(scope, dict) and scope.get('allow_execution') is True and isinstance(analysis, dict), 'Explicit analysis permission is required')
    _need(analysis.get('operation') == 'analyze' and analysis.get('request_revision'), 'Select the reviewed analysis revision')
    _need(request.get('source_id') in analysis['source_ids'], 'Analysis source is outside the reviewed scope')
    _need(request.get('options', {}) == analysis.get('options') == {}, 'Only existing empty analysis options are supported')
    definitions = request.get('responses', analysis['response_definitions'])
    _need(definitions == analysis['response_definitions'], 'Analysis response definitions differ from the reviewed scope')
    limits = _limits(analysis['limits'], ANALYSIS_LIMITS)
    resources = request.get('resources', analysis['resources'])
    _need(isinstance(resources, dict) and set(resources) == {'threads', 'memory_mb'} and
          all(type(v) is int and v > 0 and v <= analysis['resources'][k] and
              v <= scope.get('resources', {}).get(k, 0) and v <= {'threads': 1, 'memory_mb': 64}[k]
              for k, v in resources.items()),
          'Analysis requires explicit outer and inner resource permission')
    admitted = describe_resources(deepcopy(resources))
    _need(admitted is not False, 'Existing executor cannot admit these resources')
    _need(not scope.get('hard_memory_limit') and not scope.get('hard_timeout'),
          'Inline analysis cannot promise a hard RSS or preemptive timeout; use an existing Plan')
    # B performs scope checks before this source/metadata callback. C owns the
    # physical input compiler; the callback cannot execute the math engine.
    source = result_access.prepare_analysis_source(request['source_id'], request.get('selection'), limits=limits)
    from .assist.experts import validate_plan_request
    validate_plan_request({'purpose': 'Selected retained numerical analysis', 'operation': 'analyze',
        'inputs': {'result_refs': {'table': source['reference']}, 'responses': definitions}, 'budget': {'evaluations': 1}})
    description = describe_inputs(source, deepcopy(definitions), deepcopy(limits))
    _need(description['rows'] <= limits['max_rows'] and description['columns'] <= limits['max_columns'] and
          description['input_bytes'] <= limits['max_input_bytes'], 'Analysis input metadata exceeds the reviewed limits')
    inputs = deepcopy(description['validated_inputs'])
    _need(set(inputs) == {'table', 'responses'} and inputs['responses'] == definitions, 'Analysis compiler widened the request')
    table = inputs['table']
    _need(isinstance(table.get('candidates'), list) and isinstance(table.get('variables'), list),
          'Only retained candidate/table inputs supported by existing analyze can be used')
    _need(len(table['candidates']) == description['rows'] <= limits['max_rows'] and
          len(table['variables']) + len(definitions) <= limits['max_columns'] and
          _bytes(inputs) <= limits['max_input_bytes'], 'Actual analysis input exceeds the reviewed limits')
    result_access.revalidate_analysis_source(source)
    dependencies = tuple(deepcopy(description['input_dependencies']))
    receipts = tuple(description['source_receipt_ids'])
    prepared = PreparedAnalysis(new_id('A'), analysis['request_revision'], receipts,
        'analyze', inputs, deepcopy(resources), limits, tuple(deepcopy(description['input_dependencies'])),
        _analysis_digest(inputs, resources, limits, analysis['request_revision'], receipts, dependencies),
        lambda: result_access.revalidate_analysis_source(source), _SEAL)
    prepared._state['source_receipts'] = deepcopy(description.get('source_receipts', []))
    return prepared


def execute_prepared_analysis(prepared, *, existing_callback, execution_control):
    _need(type(prepared) is PreparedAnalysis and prepared._seal is _SEAL, 'A trusted PreparedAnalysis is required')
    with prepared._lock:
        execution_control.check()
        prepared._revalidate()
        _need(_analysis_digest(prepared.validated_inputs, prepared.resources, prepared.limits, prepared.scope_revision,
              prepared.source_receipt_ids, prepared.input_dependencies) == prepared.request_digest, 'Prepared analysis inputs changed')
        if prepared._state['status'] == 'SUCCEEDED':
            return deepcopy(prepared._state['receipt'])
        _need(prepared._state['status'] == 'PREPARED', 'Analysis outcome is unconfirmed; automatic execution is prohibited')
        prepared._state['status'] = 'OUTCOME_UNCONFIRMED'
        # The captured Workbench callback is the sole mathematical execution.
        output = existing_callback(deepcopy(prepared.validated_inputs))
        prepared._state['full_output'] = deepcopy(output)
        receipt = {'id': new_id('A'), 'prepared_id': prepared.id, 'operation': 'analyze',
                   'source_receipt_ids': list(prepared.source_receipt_ids),
                   'input_dependencies': deepcopy(list(prepared.input_dependencies)),
                   'resources': deepcopy(prepared.resources), 'request_digest': prepared.request_digest,
                   'execution_status': 'SUCCEEDED', 'payload_digest': canonical_hash(output),
                   'source_receipts': deepcopy(prepared._state.get('source_receipts', [])),
                   'payload_bytes': _bytes(output), 'payload': None, 'limitations': []}
        maximum = min(prepared.limits['max_output_bytes'], READ_LIMITS['max_bytes'])
        if receipt['payload_bytes'] <= maximum:
            receipt['payload'] = deepcopy(output)
        else:
            receipt['limitations'].append('Analysis completed; full output exceeds the model payload limit')
        prepared._state.update(status='SUCCEEDED', receipt=deepcopy(receipt))
        execution_control.check()
        prepared._revalidate()
        return receipt


class AnalysisAccess:
    """Per-action callback capture with the existing owner checkpoint journal."""
    def __init__(self, *, describe_inputs, describe_resources, existing_callback, execution_control):
        self.describe_inputs, self.describe_resources = describe_inputs, describe_resources
        self.existing_callback, self.execution_control = existing_callback, execution_control
        self._prepared = {}
        self._lock = RLock()

    def tool_parameters(self, binding):
        from .assist.experts import _OBJECTIVE
        current = binding.current_scope_probe()
        scope = current['context'].get('calculation_scope', {})
        if scope.get('allow_execution') is not True or not scope.get('analysis'):
            return None
        sources = sorted(set(scope['analysis']['source_ids']) & {r['source_id'] for r in binding.result_selections})
        if not sources:
            return None
        return {'type': 'object', 'additionalProperties': False, 'required': ['source_id'], 'properties': {
            'source_id': {'type': 'string', 'enum': sources}, 'selection': {'type': 'object'},
            'responses': {'type': 'array', 'items': deepcopy(_OBJECTIVE), 'minItems': 1, 'maxItems': 16},
            'options': {'type': 'object', 'additionalProperties': False},
            'resources': {'type': 'object', 'additionalProperties': False, 'required': ['threads', 'memory_mb'],
                'properties': {'threads': {'const': 1}, 'memory_mb': {'type': 'integer', 'minimum': 1, 'maximum': 64}}}}}

    def prepare(self, request, *, scope, result_access, binding):
        prepared = prepare_analysis(request, scope=scope, result_access=result_access,
            describe_inputs=self.describe_inputs, describe_resources=self.describe_resources)
        key = 'analysis-' + canonical_hash({'owner': binding.owner_id, 'phase': binding.phase_id,
            'action': binding.action_id, 'revision': prepared.scope_revision})
        self._prepared[prepared.id] = (prepared, binding, deepcopy(scope), key)
        return prepared

    def execute(self, prepared):
        _need(type(prepared) is PreparedAnalysis and prepared.id in self._prepared and
              self._prepared[prepared.id][0] is prepared, 'Prepared analysis belongs to another callback factory')
        _, binding, approved_scope, key = self._prepared[prepared.id]
        with self._lock, prepared._lock:
            current = binding.current_scope_probe()
            _need(current['context'].get('calculation_scope') == approved_scope, 'Analysis permission changed')
            ledger = binding.generation_ledger
            prior = ledger.lookup_operation('analysis', key)
            if prior:
                _need(prior['metadata']['request_digest'] == prepared.request_digest, 'The reviewed analysis call limit was consumed by another request')
                _need(prior['status'] == 'SUCCEEDED', 'Analysis outcome is unconfirmed; no automatic recalculation')
                prepared._revalidate()
                self.execution_control.check()
                return deepcopy(prior['payload'])
            ledger.record_operation('analysis', key, {'status': 'OUTCOME_UNCONFIRMED'},
                {'status': 'STARTED', 'request_digest': prepared.request_digest})
            receipt = execute_prepared_analysis(prepared, existing_callback=self.existing_callback,
                                                execution_control=self.execution_control)
            output = prepared._state['full_output']
            retained = binding.checkpoint(key + '-output', {'asset': {'id': 'A' + prepared.request_digest[:40], 'payload': output}})
            receipt['payload_ref'] = retained['asset_ref']
            ledger.record_operation('analysis', key, receipt,
                {'status': 'SUCCEEDED', 'request_digest': prepared.request_digest})
            return receipt
