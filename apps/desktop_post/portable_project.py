"""Native-only adapters around the existing ParaView owner/save/restore path."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import uuid
from dataclasses import dataclass

from caelab.native_post_dependencies import (file_pin, inspect_pvsm, graph_on_source_basis,
    verify_snapshot_members, digest, rewrite_pvsm_paths, history_key, dependency_closure,
    _verified_history_slots, bindings_on_source_basis, build_history_bases)
from caelab.native_project_contract import (OpenBinding, VerifiedNativeInput, _completed_save_witness,
    require_open_binding, require_verified_input)

_open_basis = {}
_HISTORY_SAVE_SEAL = object()


@dataclass(frozen=True)
class HistorySavePlan:
    owner_stamp: dict
    histories: list
    preserve_unavailable: bool
    source_snapshot_sha256: str
    plan_sha256: str
    source_snapshot: dict
    asset_paths: dict
    source_snapshot_file: Path | None
    _seal: object


def _snapshot_file(verified):
    folder = next((path for path in verified.entry_path.parents if path.name == verified.receipt['id'] and path.parent.name == 'inputs'), None)
    if folder is None:
        raise ValueError('HISTORY_BASIS_UNBOUND: registered snapshot proof location is unavailable')
    source = folder / verified.receipt['native_project']['manifest_file']
    if file_pin(source)['sha256'] != verified.receipt['native_project']['manifest_sha256']:
        raise ValueError('SNAPSHOT_CHANGED: registered native snapshot proof differs')
    return source


def prepare_history_save(owner, *, expected_stamp, preserve_unavailable=False):
    """Verify an exact current partial preservation decision; native export0."""
    _expect(owner, expected_stamp)
    if type(preserve_unavailable) is not bool:
        raise ValueError('Choose explicit partial history preservation')
    workspace = owner.workspace
    proof = _open_basis.get(owner.portable_binding.open_id) if owner.portable_binding else None
    unavailable = [row for row in workspace.document.get('native_history_availability', {}).get('histories', [])
                   if row['state'] == 'UNAVAILABLE_DECLARED']
    if unavailable and (not preserve_unavailable or proof is None):
        raise ValueError('MISSING_HISTORY_DEPENDENCY: confirm preservation of the exact unavailable histories')
    from caelab.native_post_dependencies import history_asset_mapping
    assets, original = history_asset_mapping(workspace.document, owner.project_path)
    if proof is not None:
        verify_snapshot_members(proof['snapshot'], proof['member_paths'])
        if original is None:
            original = proof['snapshot']
            assets = {row['original_location']: proof['member_paths'][row['member_id']]
                      for row in original['logical_origins']}
    histories = []
    for ref, obj in workspace.state['objects'].items():
        for record in obj['history']:
            declared = next((row for row in unavailable if row['history'] == history_key(ref, record)), None)
            if declared is not None:
                if declared['record_sha256'] != digest(record) or record['id'] in workspace.bundles:
                    raise ValueError('SNAPSHOT_CHANGED: unavailable history changed or acquired a replacement reader')
                histories.append(deepcopy(declared))
            else:
                bundle = workspace.bundles.get(record['id'])
                if bundle is None:
                    raise ValueError('PIPELINE_CHANGED: undeclared unavailable history cannot be saved')
                workspace._verify_record(obj, record, bundle)
                histories.append({'history': history_key(ref, record), 'state': 'RETAINED_ONLY' if bundle.get('retained_only') else 'AVAILABLE',
                    'record_sha256': digest(record), 'missing': [], 'reason_code': None})
    payload = {'owner_stamp': expected_stamp, 'histories': histories, 'preserve_unavailable': preserve_unavailable,
               'source_snapshot_sha256': original['snapshot_sha256'] if original else '0' * 64}
    return HistorySavePlan(**deepcopy(payload), plan_sha256=digest(payload), source_snapshot=deepcopy(original or {}),
                           asset_paths=assets, source_snapshot_file=(Path(workspace.document['native_history_source_snapshot']['path'])
                               if workspace.document.get('native_history_source_snapshot') else _snapshot_file(owner.portable_binding.verified_input)
                               if owner.portable_binding else None), _seal=_HISTORY_SAVE_SEAL)


def preserve_history_for_save(owner, document, folder, plan):
    if type(plan) is not HistorySavePlan or plan._seal is not _HISTORY_SAVE_SEAL:
        raise ValueError('A current verified history Save plan is required')
    _expect(owner, plan.owner_stamp)
    for row in plan.histories:
        record = next(record for record in owner.workspace.state['objects'][row['history']['object_ref']]['history']
                      if record['id'] == row['history']['revision_id'])
        if digest(record) != row['record_sha256']:
            raise ValueError('SNAPSHOT_CHANGED: history changed after the preservation decision')
    unavailable = [row for row in plan.histories if row['state'] == 'UNAVAILABLE_DECLARED']
    document['native_history_availability'] = {'version': 1, 'histories': deepcopy(plan.histories)}
    if not unavailable:
        return
    if not plan.preserve_unavailable:
        raise ValueError('Partial history preservation was not confirmed')
    wanted = {pin['path'] for row in unavailable
        for record in document['analysis']['objects'][row['history']['object_ref']]['history'] if record['id'] == row['history']['revision_id']
        for pin in [*record.get('result_files', []), *record.get('retained_reader', {}).get('files', [])]}
    origins = {row['original_location']: row['member_id'] for row in plan.source_snapshot['logical_origins']}
    members = {row['id']: row for row in plan.source_snapshot['members']}
    derived = []
    for old in sorted(wanted):
        if old not in plan.asset_paths:
            continue  # The exact missing declaration remains missing.
        identifier = origins[old]; member = members[identifier]; source = Path(plan.asset_paths[old])
        pin = file_pin(source)
        if any(pin[key] != member[key] for key in ('bytes', 'sha256')):
            raise ValueError('CONTENT_CHANGED: retained history asset changed before Save')
        output = Path(folder) / 'history-assets' / member['relative']
        output.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, output)
        if file_pin(output)['sha256'] != member['sha256']:
            raise ValueError('CONTENT_CHANGED: retained history asset copy differs')
        derived.append({'source_member': identifier, 'derived_relative': output.relative_to(folder).as_posix(),
                        **{key: member[key] for key in ('bytes', 'sha256')}, 'edits': []})
    proof = Path(folder) / 'history-source-snapshot.json'
    if plan.source_snapshot_file is None or digest(json.loads(plan.source_snapshot_file.read_text(encoding='utf-8'))) != digest(plan.source_snapshot):
        raise ValueError('SNAPSHOT_CHANGED: retained history source proof differs')
    shutil.copyfile(plan.source_snapshot_file, proof)
    document['native_history_source_snapshot'] = file_pin(proof)
    document['native_relocation_record'] = {'version': 1, 'source_snapshot_sha256': plan.source_snapshot_sha256,
        'open_id': owner.portable_binding.open_id, 'target_id': owner.native_target_id,
        'algorithm_version': 'post-history-raw-v1', 'derived_members': derived,
        'identity_edit': {'source_document_id': plan.source_snapshot['source_document_id'], 'owner_document_id': owner.document_id},
        'original_data_unchanged': True}


@dataclass(frozen=True)
class _HistoryMemberMapping:
    plan: dict


def finalize_history_bases(document, *, saved_readers, member_mapping):
    if type(member_mapping) is not _HistoryMemberMapping:
        raise ValueError('A verified native save member mapping is required')
    plan = member_mapping.plan
    errors = [row for row in plan['issues'] if row['code'] == 'HISTORY_BASIS_UNBOUND']
    if errors:
        raise ValueError(errors[0]['message'])
    return deepcopy(plan['snapshot'].get('relocation_bases', []))


def finalize_saved_history(project, document, *, owner=None):
    """Finish basis before publishing the existing native save completion."""
    if not any(obj.get('history') for obj in document.get('analysis', {}).get('objects', {}).values()):
        return document
    from caelab.native_post_dependencies import post_project_files
    roots = {Path(project).parent.resolve()}
    for record in document.get('sources', {}).values():
        roots.update(Path(pin['path']).resolve().parent for pin in record['source_pins'])
    roots.update(Path(path).resolve().parent for path in document.get('native_reader_files', {}))
    if document.get('native_import'):
        roots.add(Path(document['native_import']['state_pin']['path']).resolve().parent)
    if document.get('native_history_source_snapshot'):
        roots.add(Path(document['native_history_source_snapshot']['path']).resolve().parent)
    for obj in document.get('analysis', {}).get('objects', {}).values():
        for record in obj.get('history', []):
            roots.update(Path(pin['path']).resolve().parent for pin in record.get('result_files', []))
    prior = None
    if owner is not None and getattr(owner, 'portable_binding', None) is not None:
        prior = _open_basis[owner.portable_binding.open_id]['snapshot']
    elif owner is not None and Path(owner.project_path).is_file():
        prior = post_project_files(owner.project_path, approved_roots=sorted(roots | {Path(owner.project_path).parent.resolve()}), limits={})['snapshot']
    plan = post_project_files(project, approved_roots=sorted(roots), limits={}, _basis_source=prior)
    document['native_history_availability'] = {'version': 1, 'histories': deepcopy(plan['snapshot']['history_availability'])}
    document['native_relocation_basis'] = {'version': 1, 'histories': finalize_history_bases(document,
        saved_readers=document.get('native_readers', []), member_mapping=_HistoryMemberMapping(plan))}
    Path(project).write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    # The final manifest itself is now immutable for this completed native Save.
    final = post_project_files(project, approved_roots=sorted(roots), limits={})
    if owner is not None and getattr(owner, 'portable_binding', None) is not None:
        _open_basis[owner.portable_binding.open_id] = {'snapshot': final['snapshot'],
            'member_paths': {row['member_id']: row['source'] for row in final['files']}}
    return document


def validate_binding(binding):
    require_open_binding(binding)
    if not isinstance(binding, OpenBinding) or binding.reference['kind'] != 'native_post':
        raise ValueError('A verified local Post open ticket is required')
    return binding


def _pair(verified_input, binding):
    validate_binding(binding)
    require_verified_input(verified_input)
    if (not isinstance(verified_input, VerifiedNativeInput) or not verified_input.full
            or verified_input.reference != binding.reference
            or verified_input.context_session != binding.context_session):
        raise ValueError('STALE_TARGET: input and current native open ticket differ')
    verify_snapshot_members(verified_input.snapshot, verified_input.member_paths)


def _stamp(owner):
    owner.assert_thread(); owner.refresh()
    return {'document_id': owner.document_id, 'kind': 'post', 'session_id': owner.session_id,
            'generation': owner.generation, 'view_generation': owner.view_generation,
            'saved_revision': owner.saved_revision, 'graph_version': digest([
                {key: row[key] for key in ('label', 'reader', 'properties')} for row in owner.snapshot['sources']])}


def _expect(owner, expected):
    current = _stamp(owner)
    if current != expected:
        raise ValueError('STALE_DOCUMENT: the current native selection or edits changed')
    return current


def saved_offer(owner):
    stamp = _stamp(owner)
    pending = any(row.get('pending_properties') for row in owner.snapshot['sources'] + owner.snapshot['views']
                  + list(owner.snapshot['representations'].values()))
    return {'stamp': stamp, 'saved_file': str(owner.project_path),
            'saved_revision': owner.saved_revision, 'pending': pending,
            'dirty': owner.generation != owner.saved_generation or owner.view_generation != owner.saved_view_generation,
            'selection': {key: deepcopy(owner.snapshot[key]) for key in ('active_source_id', 'active_view_id', 'time')}}


def _record_definite_save_failure(owner, target_save, error, *, stage):
    """Only a matching current reservation may become retryable after no Save."""
    if target_save is None:
        return
    from caelab.native_project_contract import require_target_save
    try:
        require_target_save(target_save)
    except ValueError:
        return
    binding = getattr(owner, 'portable_binding', None)
    context = getattr(owner, 'native_project_context', None)
    if (binding is None or context is None or target_save.open_id != binding.open_id
            or target_save.owner_document_id != owner.document_id or target_save.source_reference != binding.reference
            or target_save.expected_stamp.get('document_id') != owner.document_id
            or target_save.expected_stamp.get('session_id') != owner.session_id):
        return
    identifier = target_save.save_command_id
    if identifier in getattr(owner, 'native_completed_saves', {}):
        return
    attempt = getattr(owner, '_native_save_attempt', {})
    if attempt.get('command_id') == identifier and (stage == 'before_save' or attempt.get('phase') != 'INVOKED'):
        return  # A retry's stale stamp cannot erase an earlier Save or unknown outcome.
    from caelab.native_project_inputs import _record_target_save_failure
    _record_target_save_failure(context, target_save, error, stage=stage)


def _reject_reserved_save_before_effect(owner, request, error):
    """Close only a verified current owner's no-effect private Save rejection."""
    if (request.get('operation') != 'document.save' or request.get('document_id') != owner.document_id
            or request.get('session_id') != owner.session_id):
        return
    binding = getattr(owner, 'portable_binding', None)
    context = getattr(owner, 'native_project_context', None)
    wire = request.get('_target_save')
    if (binding is None or context is None or not isinstance(wire, dict)
            or set(wire) != {'prepare_command_id', 'save_command_id', 'open_id'}
            or wire['save_command_id'] != request.get('command_id') or wire['open_id'] != binding.open_id):
        return
    identifier = wire['save_command_id']
    if identifier in getattr(owner, 'native_completed_saves', {}):
        return
    attempt = getattr(owner, '_native_save_attempt', {})
    if attempt.get('command_id') == identifier:
        return  # A previous native attempt is not a newly proven no-effect refusal.
    from caelab.native_project_inputs import resume_target_save
    try:
        target_save = resume_target_save(context, wire['prepare_command_id'])
    except (ValueError, KeyError, OSError, TypeError):
        return  # Forged/foreign wire cannot release a reservation.
    if target_save.save_command_id != identifier or target_save.open_id != wire['open_id']:
        return
    _record_definite_save_failure(owner, target_save, error, stage='before_save')


def complete_save(owner, *, expected_stamp, _target_save=None, _history_plan=None):
    try:
        _expect(owner, expected_stamp)
        if _target_save is not None:
            from caelab.native_project_contract import require_target_save
            require_target_save(_target_save)
            if _target_save.expected_stamp != expected_stamp:
                raise ValueError('STALE_DOCUMENT: native Save reservation belongs to an earlier owner state')
    except Exception as error:
        _record_definite_save_failure(owner, _target_save, error, stage='before_save')
        raise
    # Owner.save_project owns the native Save boundary. Witness/readback errors
    # after its return leave the reservation unknown for reconciliation.
    saved = owner.save_project(_target_save=_target_save, _history_plan=_history_plan)
    if not Path(saved).is_file():
        raise ValueError('Native Save did not publish a project manifest')
    witness = _completed_save_witness('post', saved, owner_stamp=_stamp(owner),
        command_id=_target_save.save_command_id if _target_save is not None else 'C' + uuid.uuid4().hex, publication_complete=True,
        source={'saved_file': str(saved), 'native_kind': 'post'})
    owner.native_completed_saves[witness.command_id] = witness
    return witness


def record_completed_save(owner, saved, command_id):
    """Called only after this owner completed its actual native Save command."""
    witness = _completed_save_witness('post', saved, owner_stamp=_stamp(owner),
        command_id=command_id, publication_complete=True,
        source={'saved_file': str(saved), 'native_kind': 'post'})
    owner.native_completed_saves[command_id] = witness
    return witness


def save_current_project(owner, *, confirm_first_save=None, confirm_partial=None):
    """Existing native Save action, including a standalone imported working copy."""
    binding = getattr(owner, 'portable_binding', None)
    if binding is None:
        saved = owner.save_project()
        return saved if saved is not None else True
    context = getattr(owner, 'native_project_context', None)
    if context is None:
        raise ValueError('Current verified native open context is required for this Save')
    from caelab.native_project_inputs import prepare_target_save, publish_head
    pending = getattr(owner, '_native_pending_save', None)
    if pending is not None:
        # Reconcile the SAME completed Save even when publication succeeded but
        # its reply was lost. New edits remain dirty; no second native Save occurs.
        reservation, witness, publish_command = pending
        result = publish_head(context, reservation.target_id, witness, expected_head=reservation.expected_head,
            command_id=publish_command, _target_save=reservation)
        owner.native_target_id = reservation.target_id
        owner.native_target_head = {'generation': result['head']['head_generation'], 'reference': result['head']['reference']}
        owner._native_pending_save = None
        return Path(witness.saved_file)
    first = owner.native_target_id is None
    if first and (confirm_first_save is None or confirm_first_save() is not True):
        return None
    unavailable = [row for row in owner.workspace.document.get('native_history_availability', {}).get('histories', [])
                   if row['state'] == 'UNAVAILABLE_DECLARED']
    if unavailable and (confirm_partial is None or confirm_partial(deepcopy(unavailable)) is not True):
        return None
    # Save already discards transient previews. Do it before reserving the
    # current stamp and sealed plan so that this owned edit cannot stale them.
    owner.workspace.prepare_for_save()
    owner.refresh()
    stamp = saved_offer(owner)['stamp']
    history_plan = prepare_history_save(owner, expected_stamp=stamp, preserve_unavailable=bool(unavailable))
    expected_head = getattr(owner, 'native_target_head', binding.expected_head)
    reservation = prepare_target_save(context, binding.open_id, expected_stamp=stamp,
        expected_head=expected_head, command_id='C' + uuid.uuid4().hex)
    witness = complete_save(owner, expected_stamp=stamp, _target_save=reservation, _history_plan=history_plan)
    publish_command = 'C' + uuid.uuid4().hex
    owner._native_pending_save = (reservation, witness, publish_command)
    result = publish_head(context, reservation.target_id, witness, expected_head=expected_head,
        command_id=publish_command, _target_save=reservation)
    owner.native_target_id = reservation.target_id
    owner.native_target_head = {'generation': result['head']['head_generation'], 'reference': result['head']['reference']}
    owner._native_pending_save = None
    return Path(witness.saved_file)


def _history_basis(workspace, obj, record):
    key = history_key(obj['id'], record)
    rows = workspace.document.get('native_relocation_basis', {}).get('histories', [])
    found = [row for row in rows if row['history'] == key]
    if len(found) != 1:
        raise ValueError('HISTORY_BASIS_UNBOUND: this exact analysis revision has no path basis')
    return found[0]


def _is_new_history(workspace, obj, record):
    return tuple(history_key(obj['id'], record).values()) in getattr(workspace, '_new_history_keys', set())


def verified_history_slots(workspace, obj, record, *, mode, actual_bindings=None):
    from paraview import simple as p
    try:
        from . import external
    except ImportError:
        import external
    owner = workspace.owner; binding = validate_binding(owner.portable_binding)
    basis = _history_basis(workspace, obj, record)
    proof = _open_basis.get(binding.open_id)
    if proof is None:
        raise ValueError('HISTORY_BASIS_UNBOUND: verified current materialization is unavailable')
    snapshot, paths = proof['snapshot'], proof['member_paths']
    members = {row['id']: row for row in snapshot['members']}
    checked = []
    for slot in basis['slots']:
        if (slot['site'] == 'binding' and mode == 'current' and actual_bindings is not None
                and actual_bindings.get(slot['binding_ref'], {}).get('revision') != slot['upstream']['revision_sha256']):
            continue
        names = [source for (name, _), source in p.GetSources().items() if name == slot['reader_key']['registration_name']]
        if len(names) != 1 or names[0].GetXMLName() != slot['reader_type']:
            raise ValueError('SOURCE_UNAVAILABLE: exact retained native reader is missing or replaced')
        reader = names[0]
        if slot['output_port'] >= reader.SMProxy.GetNumberOfOutputPorts():
            raise ValueError('READER_CHANGED: history output port differs')
        _, pending = owner.native_properties(reader)
        if pending:
            raise ValueError('BUSY_EDIT: history reader has unapplied properties')
        native = reader.GetProperty(slot['file_property']).GetData()
        shape = 'list' if isinstance(native, (list, tuple)) else 'scalar'
        values = list(native) if shape == 'list' else [native]
        # ParaView's owner/analysis encoders use their original shape. File pins
        # are separately read through the actual native FileName property.
        actual_paths = external.reader_input_files(reader)
        if len(actual_paths) != slot['slot_count'] or slot['element_index'] >= len(actual_paths):
            raise ValueError('READER_CHANGED: history reader input count differs')
        current = str(paths[slot['member_id']])
        if actual_paths[slot['element_index']].resolve() != Path(current).resolve():
            raise ValueError('READER_CHANGED: history reader points to a third path')
        closure, hashed = dependency_closure(slot['member_id'], snapshot['members'], snapshot['edges'])
        if closure != slot['closure_member_ids'] or hashed != slot['closure_sha256']:
            raise ValueError('HISTORY_BASIS_UNBOUND: retained dependency closure differs')
        for member_id in closure:
            pin = file_pin(paths[member_id])
            if any(pin[key] != members[member_id][key] for key in ('bytes', 'sha256')):
                raise ValueError('CONTENT_CHANGED: history reader data changed')
        checked.append({**deepcopy(slot), 'current_value': current})
    return _verified_history_slots(basis, checked, (owner.session_id, owner.generation, owner.view_generation))


def compare_history_inputs(workspace, obj, record, *, mode):
    if mode not in {'retained', 'current'}:
        raise ValueError('Choose current or retained input comparison')
    refs = workspace._refs(obj['kind'], record['recipe'])
    revisions = workspace._retained_dependencies(record, refs) if mode == 'retained' else None
    try:
        actual = workspace.source_stamps(refs, revisions)
        if getattr(workspace.owner, 'portable_binding', None) is not None and not _is_new_history(workspace, obj, record):
            basis = _history_basis(workspace, obj, record)
            proof = verified_history_slots(workspace, obj, record, mode=mode, actual_bindings=actual)
            compared = bindings_on_source_basis(actual, expected_bindings=record['bindings'], history_basis=basis, verified_slots=proof)
        else:
            compared = actual
        return {'state': 'SAME' if compared == record['bindings'] else 'DIFFERENT', 'mode': mode,
                'revisions': revisions or {}, 'issues': [], 'comparison_bindings': compared}
    except (ValueError, RuntimeError, OSError) as error:
        return {'state': 'UNAVAILABLE', 'mode': mode, 'revisions': revisions or {},
                'issues': [str(error)], 'comparison_bindings': None}


def select_bound_target(owner, selector, *, verified_input, binding):
    """Select exact saved locators using native registration, port and domains."""
    _pair(verified_input, binding); owner.assert_thread()
    from caelab.native_project_contract import validate_native_selection
    import xml.etree.ElementTree as ET
    from paraview import simple as p, servermanager
    selector = validate_native_selection(selector, verified_input.snapshot)
    selected = selector['selection']
    state_member = verified_input.snapshot['entry_member'] if verified_input.snapshot['format'] == 'pvsm' else next(
        edge['child_member'] for edge in verified_input.snapshot['edges'] if edge['locator'] == {'codec': 'post_manifest_v1', 'field': 'workspace_file'})
    root = ET.parse(verified_input.member_paths[state_member]).getroot()
    saved = root if root.tag == 'ServerManagerState' else root.find('ServerManagerState')
    def locator(group, name, identifier, kind):
        items = saved.findall("ProxyCollection[@name='%s']/Item" % group)
        matches = [item for item in items if item.get('name') == name]
        proxy = saved.find("Proxy[@id='%s']" % identifier)
        if len(matches) != 1 or matches[0].get('id') != identifier or proxy is None or proxy.get('type') != kind:
            raise ValueError('SELECTION_UNAVAILABLE: saved native proxy locator differs')
    source_spec = selected['source']
    locator('sources', source_spec['registration_name'], source_spec['saved_proxy_id'], source_spec['proxy_type'])
    sources = [source for (name, _), source in p.GetSources().items() if name == source_spec['registration_name']]
    if len(sources) != 1 or sources[0].GetXMLName() != source_spec['proxy_type']:
        raise ValueError('SELECTION_UNAVAILABLE: native source is missing, duplicated or replaced')
    source = sources[0]; port = source_spec['output_port']
    if port >= source.SMProxy.GetNumberOfOutputPorts():
        raise ValueError('SELECTION_UNAVAILABLE: native output port is missing')
    output = p.OutputPort(source, port)
    view = p.GetActiveView()
    if selected['view'] is not None:
        spec = selected['view']; locator('views', spec['registration_name'], spec['saved_proxy_id'], spec['view_type'])
        views = [item for (name, _), item in servermanager.ProxyManager().GetProxiesInGroup('views').items() if name == spec['registration_name']]
        if len(views) != 1 or views[0].GetXMLName() != spec['view_type']:
            raise ValueError('SELECTION_UNAVAILABLE: native view is missing or replaced')
        view = views[0]
    source.UpdatePipelineInformation()
    available = [float(value) for value in getattr(source, 'TimestepValues', [])]
    clock = selected['time']
    if clock is not None:
        data_time = clock['data_time_value']
        if available:
            if clock['value'] not in available or data_time is not None and data_time != clock['value']:
                raise ValueError('SELECTION_UNAVAILABLE: exact native time is absent')
            if clock['frame_index'] is not None and (clock['frame_index'] >= len(available) or available[clock['frame_index']] != clock['value']):
                raise ValueError('SELECTION_UNAVAILABLE: native frame/time mapping differs')
        elif data_time is not None or clock['frame_index'] is not None:
            raise ValueError('SELECTION_UNAVAILABLE: static source has no native data-time frame')
    if selected['analysis'] is not None:
        spec = selected['analysis']; obj = owner.workspace.object(spec['object_ref'])
        record = next((row for row in obj['history'] if row['id'] == spec['revision_id']), None)
        if record is None or source_spec['registration_name'] not in {record.get('source_name'), record.get('retained_source_name')}:
            raise ValueError('SELECTION_UNAVAILABLE: source does not belong to the selected analysis revision')
        owner.workspace._verify_record(obj, record, owner.workspace.bundles[record['id']])
    array = selected['array_name']; association = selected['association']; component = selected['component']
    if array is not None:
        attributes = {'POINTS': output.PointData, 'CELLS': output.CellData, 'FIELD': output.FieldData}
        if association not in attributes or array not in attributes[association].keys():
            raise ValueError('SELECTION_UNAVAILABLE: exact array/association is absent or unsupported by this native view')
        count = attributes[association][array].GetNumberOfComponents()
        if component is not None and (component['mode'] == 'scalar' and count != 1
                or component['mode'] == 'index' and component['index'] >= count):
            raise ValueError('SELECTION_UNAVAILABLE: array component is outside the native domain')
        if view is None or view.GetXMLName() != 'RenderView':
            raise ValueError('SELECTION_UNAVAILABLE: field coloring requires the saved native Render view')
    elif component is not None or association is not None:
        raise ValueError('SELECTION_UNAVAILABLE: array component requires its exact array')
    if selected['block'] is not None:
        # Use the actual native data assembly, never recompute flat block indices.
        info = output.GetDataInformation()
        block = selected['block']
        assembly = info.GetHierarchy() if block['assembly'] == 'Hierarchy' and hasattr(info, 'GetHierarchy') else (
            info.GetDataAssembly() if hasattr(info, 'GetDataAssembly') else None)
        if assembly is None or block['assembly'] != 'Hierarchy' and assembly.GetRootNodeName() != block['assembly']:
            raise ValueError('SELECTION_UNAVAILABLE: exact native data assembly is unavailable')
        if any(not list(assembly.SelectNodes([value])) for value in block['selectors']):
            raise ValueError('SELECTION_UNAVAILABLE: a native block selector has no exact target')
    previous_source, previous_view = p.GetActiveSource(), p.GetActiveView()
    previous_time = float(p.GetAnimationScene().AnimationTime)
    try:
        if view is not None: p.SetActiveView(view)
        if clock is not None:
            p.GetAnimationScene().AnimationTime = clock['value']
            source.UpdatePipeline(time=clock['value']) if available else source.UpdatePipeline()
        p.SetActiveSource(output)
        if array is not None:
            actual_attributes = {'POINTS': output.PointData, 'CELLS': output.CellData, 'FIELD': output.FieldData}
            if array not in actual_attributes[association].keys():
                raise ValueError('SELECTION_UNAVAILABLE: array is absent at the exact selected time')
            display = p.Show(output, view); p.ColorBy(display, (association, array))
            lookup = display.LookupTable
            if component is not None:
                if component['mode'] == 'magnitude': lookup.VectorMode = 'Magnitude'
                else: lookup.VectorMode = 'Component'; lookup.VectorComponent = component['index'] if component['mode'] == 'index' else 0
                if (component['mode'] == 'magnitude' and str(lookup.VectorMode) != 'Magnitude'
                        or component['mode'] != 'magnitude' and int(lookup.VectorComponent) != (component['index'] or 0)):
                    raise ValueError('SELECTION_UNAVAILABLE: native component readback differs')
        if selected['block'] is not None:
            block = selected['block']; display = p.Show(output, view)
            actual_assembly = str(display.Assembly) if 'Assembly' in display.ListProperties() else 'Hierarchy'
            if actual_assembly != block['assembly']:
                raise ValueError('SELECTION_UNAVAILABLE: representation uses another native assembly')
            for index, value in enumerate(block['selectors']):
                p.SelectBlocks(value, Source=output, FieldType='CELL' if association == 'CELLS' else 'POINT',
                    Modifier='ADD' if index else None)
        active = p.GetActiveSource()
        if not external_same_proxy(active, output) or getattr(active, 'Port', 0) != port:
            raise ValueError('SELECTION_UNAVAILABLE: native source/port readback differs')
        if clock is not None and float(p.GetAnimationScene().AnimationTime) != clock['value']:
            raise ValueError('SELECTION_UNAVAILABLE: native scene time readback differs')
        return {'selection': deepcopy(selector), 'selection_status': 'SELECTED'}
    except BaseException:
        p.SetActiveSource(previous_source); p.SetActiveView(previous_view)
        p.GetAnimationScene().AnimationTime = previous_time
        raise


def external_same_proxy(a, b):
    return a is not None and b is not None and a.SMProxy == b.SMProxy


def _project_paths(document, relocate, *, preserve_histories=()):
    """Only declared current file locations; recipes/origins/graph stay exact."""
    for source in document.get('sources', {}).values():
        source['entry_path'] = relocate(source['entry_path'])
        if 'input_paths' in source:
            source['input_paths'] = [relocate(path) for path in source['input_paths']]
        for pin in source['source_pins']:
            pin['path'] = relocate(pin['path'])
    document['native_reader_files'] = {relocate(path): hashed for path, hashed in document.get('native_reader_files', {}).items()}
    for reader in document.get('native_readers', []):
        reader['input_paths'] = [relocate(path) for path in reader['input_paths']]
    for obj in document.get('analysis', {}).get('objects', {}).values():
        for record in obj.get('history', []):
            if (obj['id'], record['id']) in preserve_histories:
                continue
            if record.get('result_file'):
                record['result_file'] = relocate(record['result_file'])
            for pin in record.get('result_files', []):
                pin['path'] = relocate(pin['path'])
            retained = record.get('retained_reader')
            if retained:
                retained['input_paths'] = [relocate(path) for path in retained['input_paths']]
                for pin in retained['files']:
                    pin['path'] = relocate(pin['path'])
    if document.get('native_import'):
        document['native_import']['state_pin']['path'] = relocate(document['native_import']['state_pin']['path'])
    if document.get('native_history_source_snapshot'):
        document['native_history_source_snapshot']['path'] = relocate(document['native_history_source_snapshot']['path'])


def derive_project(verified_input, destination, *, binding):
    _pair(verified_input, binding)
    if verified_input.snapshot['format'] == 'pvsm':
        raise ValueError('MANAGED_SAVE_REQUIRED: explicitly save this native state as an analysis project')
    destination = Path(destination).resolve()
    # The caller supplies a final working directory, never the copy staging root.
    if not destination.is_relative_to(Path(binding.working_root).resolve()):
        raise ValueError('Derived project must stay inside the current working root')
    destination.mkdir(parents=True, exist_ok=True)
    raw_paths = {}
    for member in verified_input.snapshot['members']:
        if member['storage'] != 'file':
            raise ValueError('Post project contains an unsupported archive member')
        output = destination / 'files' / member['relative']
        output.parent.mkdir(parents=True, exist_ok=True)
        source = Path(verified_input.member_paths[member['id']])
        if output.exists():
            if file_pin(output)['sha256'] != member['sha256']:
                raise FileExistsError('Existing derived member differs: ' + str(output))
        else:
            shutil.copyfile(source, output)
        raw_paths[member['id']] = output
    verify_snapshot_members(verified_input.snapshot, raw_paths)
    paths = {row['original_location']: str(raw_paths[row['member_id']]) for row in verified_input.snapshot['logical_origins']}
    for missing in verified_input.snapshot['unavailable']:
        expected = missing.get('expected_child')
        if expected:
            original = next(edge['original_reference'] for edge in verified_input.snapshot['edges']
                if edge['parent_member'] == missing['parent_member'] and edge['locator'] == missing['locator'])
            paths[original] = str(destination / 'files' / expected['relative'])
    document = json.loads(verified_input.entry_path.read_text(encoding='utf-8-sig'))
    def relocate(value):
        if value not in paths:
            raise ValueError('HISTORY_DEPENDENCY_UNBOUND: current file location has no registered member: ' + value)
        return paths[value]
    unavailable_histories = {(row['history']['object_ref'], row['history']['revision_id'])
        for row in verified_input.snapshot.get('history_availability', []) if row['state'] == 'UNAVAILABLE_DECLARED'}
    document['native_history_availability'] = {'version': 1, 'histories': deepcopy(verified_input.snapshot.get('history_availability', []))}
    if document.get('native_relocation_record'):
        original_manifest = next(row['original_location'] for row in verified_input.snapshot['logical_origins']
                                 if row['member_id'] == verified_input.snapshot['entry_member'])
        for row in document['native_relocation_record']['derived_members']:
            old = str(Path(original_manifest).parent / row['derived_relative'])
            row['derived_relative'] = Path(relocate(old)).relative_to(destination).as_posix()
    _project_paths(document, relocate, preserve_histories=unavailable_histories)
    if unavailable_histories and not document.get('native_relocation_record'):
        proof_file = destination / 'history-source-snapshot.json'
        shutil.copyfile(_snapshot_file(verified_input), proof_file)
        document['native_history_source_snapshot'] = file_pin(proof_file)
        wanted = {pin['path'] for ref, obj in document.get('analysis', {}).get('objects', {}).items()
            for record in obj.get('history', []) if (ref, record['id']) in unavailable_histories
            for pin in [*record.get('result_files', []), *record.get('retained_reader', {}).get('files', [])]}
        document['native_relocation_record'] = {'version': 1, 'source_snapshot_sha256': verified_input.snapshot['snapshot_sha256'],
            'open_id': binding.open_id, 'target_id': binding.target_id, 'algorithm_version': 'post-history-raw-v1',
            'derived_members': [{'source_member': origin['member_id'],
                'derived_relative': raw_paths[origin['member_id']].relative_to(destination).as_posix(),
                **{key: file_pin(raw_paths[origin['member_id']])[key] for key in ('bytes', 'sha256')}, 'edits': []}
                for origin in verified_input.snapshot['logical_origins'] if origin['original_location'] in wanted],
            'identity_edit': {'source_document_id': verified_input.snapshot['source_document_id'],
                              'owner_document_id': binding.working_document_id}, 'original_data_unchanged': True}
    for key in ('service_url', 'desktop_python', 'repo_root', 'origin_job_id'):
        document.pop(key, None)
    document['project_root'] = str((binding.native_save_root.parent if binding.native_save_root is not None
                                  else Path(binding.working_root)).resolve())
    document['document_id'] = binding.working_document_id
    state_member = next(edge['child_member'] for edge in verified_input.snapshot['edges']
                        if edge['parent_member'] == verified_input.snapshot['entry_member']
                        and edge['locator'] == {'codec': 'post_manifest_v1', 'field': 'workspace_file'})
    state = destination / 'analysis.pvsm'
    partial = verified_input.snapshot['validation']['closure'] != 'COMPLETE'
    if partial:
        # Original PVSM bytes and old source declarations were inspected before
        # projection. Missing slots deliberately point to absent working files.
        tree = rewrite_pvsm_paths(raw_paths[state_member], document['sources'], document.get('native_readers', []))
    else:
        tree = rewrite_pvsm_paths(raw_paths[state_member], document['sources'], document.get('native_readers', []),
            reader_bindings=verified_input.snapshot['reader_bindings'], member_paths=raw_paths)
    tree.write(state, encoding='utf-8', xml_declaration=True)
    document['workspace_file'] = state.name
    document['workspace_sha256'] = file_pin(state)['sha256']
    document.pop('relocation_basis', None)
    document['native_relocation_basis'] = {'version': 1, 'histories': deepcopy(verified_input.snapshot.get('relocation_bases', []))}
    project = destination / 'project.json'
    project.write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    _open_basis[binding.open_id] = {'snapshot': deepcopy(verified_input.snapshot), 'member_paths': raw_paths}
    return {'project_path': str(project), 'entry_path': str(project), 'member_paths': raw_paths,
        'reader_bindings': deepcopy(verified_input.snapshot['reader_bindings']),
        'relocation': paths, 'status': 'PREPARED'}


def restore_bound_project(verified_input, binding, *, allow_partial=False):
    _pair(verified_input, binding)
    blocking = [row for row in verified_input.snapshot['validation']['issues']
                if row['code'] in {'UNSUPPORTED_EXECUTABLE_PROXY', 'UNSUPPORTED_DEPENDENCY', 'READER_NOT_VERIFIED'}]
    if blocking:
        raise ValueError('UNSUPPORTED_DEPENDENCY: this saved state contains unverified native execution or reader branches; preserve the source and open it explicitly in native ParaView')
    if not allow_partial and verified_input.snapshot['validation']['closure'] != 'COMPLETE':
        raise ValueError('MISSING_DEPENDENCY: choose explicit partial recovery for this saved project')
    from paraview import simple as p
    if p.GetSources():
        raise ValueError('BUSY_DOCUMENT: open this saved project in a new ParaView window')
    derived = derive_project(verified_input, Path(binding.working_root), binding=binding)
    os.environ['CAE_POST_PROJECT'] = derived['project_path']
    try:
        from . import commands, bridge
    except ImportError:
        import commands, bridge
    restored = commands.restore_workspace(allow_repair=allow_partial)
    owner = bridge.Owner(document_id=binding.working_document_id, _portable_binding=binding)
    commands.set_save_owner(owner)
    issues = owner.workspace.restore_issues if owner.workspace else []
    status = 'PARTIAL_OPEN' if issues or restored and restored.get('state') == 'PARTIAL_RESTORE' else 'OPENED'
    from caelab.portable_project_native import _native_open_readback
    readback = _native_open_readback({'open_id': binding.open_id, 'reference': deepcopy(binding.reference),
        'target_id': binding.target_id, 'working_document_id': owner.document_id,
        'context_session': binding.context_session, 'status': status,
        'native_owner_session': owner.session_id, 'native_kind': 'post'})
    return {'status': status,
            'owner': owner, 'project_path': derived['project_path'], 'issues': deepcopy(issues),
            'selection': deepcopy(owner.project_document.get('active_selection')), 'readback': readback}


def adopt_pvsm(verified_input, binding, *, expected_empty_session):
    _pair(verified_input, binding)
    from paraview import simple as p
    if verified_input.snapshot['format'] != 'pvsm' or not expected_empty_session or p.GetSources():
        raise ValueError('Use a new empty ParaView window to adopt the selected native state')
    if verified_input.snapshot['validation']['issues']:
        raise ValueError('UNSUPPORTED_DEPENDENCY: native state has unsupported reader or executable branches')
    try:
        from . import external, source_repair, bridge, commands
    except ImportError:
        import external, source_repair, bridge, commands
    root = Path(binding.working_root).resolve(); root.mkdir(parents=True, exist_ok=True)
    readers = []
    for reader in verified_input.snapshot['reader_bindings']:
        readers.append({'reader_name': reader['reader_key']['registration_name'], 'reader_type': reader['reader_type'],
                        'input_paths': [str(verified_input.member_paths[slot['member_id']]) for slot in reader['input_slots']]})
    state = root / 'admitted.pvsm'
    tree = source_repair._rewrite_reader_paths(verified_input.entry_path, {}, readers,
        reader_bindings=verified_input.snapshot['reader_bindings'], member_paths=verified_input.member_paths)
    tree.write(state, encoding='utf-8', xml_declaration=True)
    p.LoadState(str(state))
    external.verify_readers({'sources': {}, 'native_readers': readers})
    # Existing loaded readers are reused. No admit_result/OpenDataFile duplication.
    sources = {}
    for index, reader in enumerate(readers):
        if len(reader['input_paths']) != 1 or Path(reader['input_paths'][0]).suffix.lower() not in external.READERS:
            continue
        source = p.FindSource(reader['reader_name'])
        entry = Path(reader['input_paths'][0])
        sources['imported%d' % index] = {**reader, 'entry_path': str(entry), 'input_id': None,
            'source_pins': external.pins(external.source_files(entry)), 'metadata': external.inspect_result(source),
            'native_metadata': None, 'registration_origin': None}
    document = {'kind': external.KIND, 'document_id': binding.working_document_id,
        'project_root': str(root), 'sources': sources, 'native_readers': readers,
        'workspace_file': state.name, 'workspace_sha256': file_pin(state)['sha256']}
    imported = root / 'imported' / 'original.pvsm'; imported.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(verified_input.entry_path, imported)
    document['native_import'] = {'kind': 'pvsm', 'state_pin': file_pin(imported),
        'source_reference': deepcopy(verified_input.reference),
        'reader_bindings': deepcopy(verified_input.snapshot['reader_bindings'])}
    initial = root / 'adopted-project.json'
    initial.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.environ['CAE_POST_PROJECT'] = str(initial)
    saved = external.save_project(initial, document)
    owner = bridge.Owner(document_id=binding.working_document_id)
    commands.set_save_owner(owner)
    return _completed_save_witness('post', saved, owner_stamp=_stamp(owner), command_id='C' + uuid.uuid4().hex,
        publication_complete=True, source={'saved_file': str(saved), 'native_kind': 'post'})


def preview_repair(owner, replacements, *, expected_stamp):
    _expect(owner, expected_stamp)
    try:
        from .source_change import content_set
        from . import external
    except ImportError:
        from source_change import content_set
        import external
    proposed = deepcopy(owner.project_document)
    for row in replacements:
        old = proposed.get('sources', {}).get(row['source_ref'])
        receipt = row['receipt']
        if old is None or receipt.get('id') != row['input_id']:
            raise ValueError('Choose an exact registered replacement for this source')
        replacement = dict(old, entry_path=receipt['path'], source_pins=deepcopy(receipt['source_pins']))
        if (content_set(old) != content_set(replacement)
                or Path(old['entry_path']).suffix.lower() != Path(replacement['entry_path']).suffix.lower()
                or old.get('native_metadata') != receipt.get('native_metadata')):
            raise ValueError('CONTENT_CHANGED: add the changed data as a new result')
        external.verify_sources(None, {'sources': {row['source_ref']: replacement}})
        proposed['sources'][row['source_ref']] = replacement
    plan = {'stamp': deepcopy(expected_stamp), 'replacements': deepcopy(replacements), 'content_changed': False}
    plan['sha256'] = digest(plan)
    return plan


def apply_repair(owner, plan, *, expected_stamp, command_id):
    request_sha256 = digest({'plan': plan, 'stamp': expected_stamp})
    completed = getattr(owner, '_portable_completed_repairs', None)
    if completed is None:
        completed = {}; owner._portable_completed_repairs = completed
    prior = completed.get(command_id)
    if prior is not None:
        if prior.get('native_repair_request') != request_sha256:
            raise ValueError('COMMAND_CONFLICT: repair command already belongs to another request')
        return deepcopy(prior['result'])
    _expect(owner, expected_stamp)
    actual = preview_repair(owner, plan['replacements'], expected_stamp=expected_stamp)
    if actual != plan:
        raise ValueError('STALE_REPAIR: replacement or current owner changed')
    # Existing source repair is transactional for one exact reader and its overlays.
    # Do not pretend sequential native edits are an atomic multi-source transaction.
    if len(plan['replacements']) != 1:
        raise ValueError('Repair one selected source at a time')
    row = plan['replacements'][0]
    result = owner.workspace.repair_source(source_ref=row['source_ref'], input_id=row['input_id'], receipt=row['receipt'])
    completed[command_id] = {'native_repair_request': request_sha256, 'result': deepcopy(result)}
    return result


def launch_prepared_project(context, request, *, command_id, executable=None, prepare_only=False, client=None):
    """Native-only Python entry; reuse the existing desktop Post launcher."""
    from types import SimpleNamespace
    import sys
    from caelab.native_project_inputs import _require_context
    from caelab.portable_project_native import prepare_open
    from apps.research.desktop import _post
    context = _require_context(context)
    ticket = prepare_open(context, request, command_id=command_id)
    args = SimpleNamespace(project=None, input_path=None, input_id=None, job_id=None,
        research_source=None, measurement_result=None, curve_origin=None, report_image=None,
        executable=executable, output=None, prepare_only=prepare_only)
    current_installation = {'repo_root': str(Path(__file__).resolve().parents[2]), 'python': sys.executable,
                            'export_root': str(context.workspace / 'exports')}
    return _post(client, args, _native_project_ticket=ticket,
        _local_context=current_installation if client is None else None)
