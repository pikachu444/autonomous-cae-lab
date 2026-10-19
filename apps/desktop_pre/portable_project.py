"""Saved FreeCAD sets and native adapters; never a geometry/assembly engine.

Inspection imports no FreeCAD or Qt. Original archives are immutable; the only
file relocation allowed below is the existing native_cad XLink-file codec.
"""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import uuid
import zipfile

from caelab import native_cad
from caelab.storage import canonical_hash


def _pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def _issue(code, message, *, member=None, locator=None, recovery=None):
    return {'code': code, 'native_kind': 'pre', 'source_reference': None,
            'member_id': member, 'locator': locator, 'message': message,
            'recovery': recovery or 'FreeCAD에서 참조 부품을 함께 열고 프로젝트를 저장하세요.',
            'severity': 'error'}


def _locator(member, link):
    return {'codec': 'freecad_xlink_v1', 'document_member': member,
            'object_name': link['object_id'], 'property_name': link['property'],
            'xlink_index': link['index'], 'target_name': link['target_name'],
            'original_file': link['file']}


def _links(data):
    # Same codec as native_cad.xlinks, with an in-memory archive member.
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        tree = native_cad._xml(archive)
    links = []
    for obj in tree.findall('.//Object'):
        for prop in obj.findall('./Properties/Property'):
            for index, link in enumerate(prop.findall('.//XLink')):
                links.append({'object_id': obj.get('name'), 'property': prop.get('name'),
                              'index': index, 'file': link.get('file', ''),
                              'target_name': link.get('name', '')})
    return links


def _origin(path):
    return str(Path(path).resolve())


def _declared_file_issues(data, member):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        tree = native_cad._xml(archive)
    issues = []
    for obj in tree.findall('.//Object'):
        for prop in obj.findall('./Properties/Property'):
            if prop.get('type') in {'App::PropertyFile', 'App::PropertyPath'}:
                values = [node.get('value', '') for node in prop]
                if any(values):
                    issues.append(_issue('UNSUPPORTED_FILE_PROPERTY',
                        obj.get('name', '') + '의 ' + prop.get('name', '') + ' 외부 파일을 자동 포함할 수 없습니다.',
                        member=member, recovery='이 기능의 외부 파일을 확인하고 지원되는 프로젝트로 저장하세요. 원문서는 유지됩니다.'))
    return issues


def _embedded_metadata(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        tree = native_cad._xml(archive)
    values = []
    for obj in tree.findall('.//Object'):
        if obj.get('name') == 'CAELabProject':
            for prop in obj.findall('./Properties/Property'):
                if prop.get('name') == 'Definition':
                    node = prop.find('String')
                    if node is not None:
                        values.append(json.loads(node.get('value', '')))
    if not values:
        return None
    if len(values) != 1 or not isinstance(values[0], dict) or values[0].get('schema') != 'caelab-pre-project/1':
        raise ValueError('Unsupported embedded native project metadata; preserve the draft')
    return values[0]


def saved_owner_id_map(verified):
    """Read native saved child identities; missing identities remain unknown."""
    from caelab.native_project_contract import require_verified_input
    from caelab.storage import check_id
    require_verified_input(verified)
    result = []
    for row in verified.snapshot['members']:
        if row['role'] != 'pre_document':
            continue
        if row['storage'] == 'archive_member':
            with zipfile.ZipFile(verified.member_paths[row['archive_member_of']]) as archive:
                data = archive.read(row['archive_member'])
        else:
            data = Path(verified.member_paths[row['id']]).read_bytes()
        if _pin(data) != {key: row[key] for key in ('bytes', 'sha256')}:
            raise ValueError('Saved native document changed while reading its identity')
        stored = _embedded_metadata(data)
        identity = stored.get('document_id') if stored else None
        result.append({'member_id': row['id'], 'owner_document_id': check_id(identity) if identity else None})
    return result


def _non_metadata_fingerprint(doc):
    from .metadata import NAME
    return canonical_hash([{'name': obj.Name, 'type': obj.TypeId,
                            'native_content': _native_dump_payload_sha256(obj)}
                           for obj in doc.Objects if obj.Name != NAME])


def _native_dump_payload_sha256(obj):
    # FreeCAD dumpContent ZIP framing includes wall-clock DOS timestamps.
    # Every member name/order and exact engineering payload remains checked.
    with zipfile.ZipFile(io.BytesIO(bytes(obj.dumpContent()))) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)) or 'Persistence.xml' not in names:
            raise ValueError('Invalid native object content archive')
        return canonical_hash([{'name':info.filename,'sha256':hashlib.sha256(archive.read(info)).hexdigest()}
                               for info in archive.infolist()])


def initialize_import_identity(doc, binding, *, member_id):
    """Fresh import only; metadata initialization is outside user Undo history."""
    from caelab.native_project_contract import require_open_binding
    from . import metadata
    require_open_binding(binding)
    expected = [row['owner_document_id'] for row in binding.owner_id_map if row['member_id'] == member_id]
    if len(expected) != 1 or not expected[0]:
        raise ValueError('Native open has no exact local identity for this document member')
    if Path(doc.FileName).resolve() != Path(binding.member_paths[member_id]).resolve():
        raise ValueError('IDENTITY_INIT_NOT_FRESH: native document is outside its verified import')
    before = metadata.read(doc)
    mode = doc.UndoMode
    geometry = _non_metadata_fingerprint(doc)
    after = deepcopy(before)
    if before.get('document_id') != expected[0]:
        if doc.UndoCount or doc.RedoCount or doc.Transacting or doc.Partial:
            raise ValueError('IDENTITY_INIT_NOT_FRESH: 편집한 문서의 식별 정보를 자동으로 바꾸지 않습니다.')
        after.update(document_id=expected[0], portable_origin={
            'source_reference': deepcopy(binding.reference), 'document_member': member_id, 'authority': 'HISTORY_ONLY'})
        try:
            doc.UndoMode = 0
            metadata.write(doc, after)
        finally:
            doc.UndoMode = mode
    actual = metadata.read(doc)
    changed = sorted(key for key in set(before) | set(actual) if before.get(key) != actual.get(key))
    if actual!=after or set(changed)-{'document_id','portable_origin'}:
        raise ValueError('Native identity initialization changed unapproved metadata')
    if _non_metadata_fingerprint(doc)!=geometry:
        raise ValueError('Native identity initialization changed native engineering payloads')
    if doc.UndoMode!=mode:
        raise ValueError('Native identity initialization did not restore Undo mode')
    return {'open_id': binding.open_id, 'member_id': member_id,
            'source_document_id': before.get('document_id'), 'owner_document_id': expected[0],
            'metadata_before_sha256': canonical_hash(before), 'metadata_after_sha256': canonical_hash(actual),
            'changed_keys': changed, 'undo_mode_before': mode, 'undo_mode_after': doc.UndoMode,
            'adapter_recompute_calls': 0,
            'geometry_check': {'native_non_metadata_content_sha256': geometry, 'unchanged': True}}


def pre_snapshot_files(saved_file, *, approved_roots, declared_replacements=(),
                       source_document_id=None, _replacements=None):
    """Read the exact saved closure. No native process, host fallback or save.

    Missing dependencies remain declared partial. Replacement approval belongs
    to N0; callers cannot invent a missing child's expected pin here.
    """
    if declared_replacements:
        raise ValueError('Caller replacement dictionaries are not registered evidence')
    if _replacements is not None:
        from caelab.native_project_contract import require_replacement_map
        require_replacement_map(_replacements)
    source = Path(saved_file).resolve(strict=True)
    roots = [Path(root).resolve(strict=True) for root in approved_roots]
    if not roots or not any(source.is_relative_to(root) for root in roots):
        raise ValueError('The saved project is outside the approved CAD roots')
    if source.suffix.lower() not in ('.caepre', '.fcstd'):
        raise ValueError('Choose a saved .caepre or .FCStd project')
    members, files, edges, origins, unavailable, issues = [], [], [], [], [], []
    payloads, manifest_pin = {}, None
    def add_file(path, member, relative, role):
        data = path.read_bytes()
        row = {'id': member, 'storage': 'file', 'relative': relative, 'role': role, **_pin(data)}
        members.append(row); payloads[member] = data
        files.append({'member_id': member, 'source': path, 'relative': relative,
                      'bytes': row['bytes'], 'sha256': row['sha256']})
        origins.append({'member_id': member, 'original_location': _origin(path)})
    def edge(parent, link, child):
        locator = _locator(parent, link)
        if _replacements is not None and _replacements.has(parent, locator):
            # Current native XLink/missing declarations carry no authoritative
            # expected-child pin. A caller pin must never authorize a repair.
            _replacements.resolve(parent, locator, expected_child=None)
        edges.append({'parent_member': parent, 'locator': locator, 'child_member': child,
                      'required': True, 'original_reference': link['file']})
        if child is None:
            unavailable.append({'parent_member': parent, 'locator': locator,
                                'expected_child': None, 'required': True, 'code': 'MISSING_DEPENDENCY'})
            issues.append(_issue('MISSING_DEPENDENCY', '저장본에 참조 부품이 없습니다.',
                                 member=parent, locator=locator))
    if source.suffix.lower() == '.caepre':
        manifest = native_cad.inspect_project(source)
        identity = manifest['document_id']
        if manifest.get('metadata', {}).get('document_id', identity) != identity:
            raise ValueError('Managed project and embedded document identities differ')
        add_file(source, 'archive', 'project.caepre', 'pre_archive')
        with zipfile.ZipFile(io.BytesIO(payloads['archive'])) as archive:
            data = archive.read('project.json')
            members.append({'id': 'manifest', 'storage': 'archive_member',
                            'archive_member_of': 'archive', 'archive_member': 'project.json',
                            'role': 'declared_metadata', **_pin(data)})
            manifest_pin = {'member_id': 'manifest', **_pin(data)}
            names = {row['file']: 'document' + str(i) for i, row in enumerate(manifest['documents'])}
            for row in manifest['documents']:
                member = names[row['file']]; data = archive.read(row['file'])
                payloads[member] = data
                issues.extend(_declared_file_issues(data, member))
                members.append({'id': member, 'storage': 'archive_member',
                                'archive_member_of': 'archive', 'archive_member': row['file'],
                                'role': 'pre_document', **_pin(data)})
                if row['file'] == manifest['entry']:
                    embedded = _embedded_metadata(data)
                    if embedded is not None and embedded.get('document_id') != identity:
                        raise ValueError('Embedded native document and saved manifest identities differ')
                for link in _links(data):
                    if link['file']:
                        target = str(PurePosixPath(row['file']).parent / link['file'])
                        edge(member, link, names.get(target))
        entry = 'archive'  # Registered native entry; project.json retains the exact internal document.
        saved_revision, native_revision = manifest['revision'], manifest['revision']
        identity_origin, revision_origin = 'native_manifest', 'native_save'
    else:
        paths, active, seen = [], set(), set()
        def visit(path):
            if path in active:
                raise ValueError('Cyclic native documents require a managed FreeCAD project')
            if path in seen:
                return
            if (not any(path.is_relative_to(root) for root in roots)
                    or not path.is_file() or path.suffix.lower() != '.fcstd'):
                raise ValueError('Native Link is missing or outside the approved CAD roots')
            if len(paths) >= native_cad.MAX_FILES:
                raise ValueError('Native dependency set exceeds 1024 documents')
            seen.add(path); active.add(path); paths.append(path)
            for link in native_cad.xlinks(path):
                if link['file']:
                    member = 'document'+str(paths.index(path))
                    if _replacements is not None and _replacements.has(member, _locator(member, link)):
                        _replacements.resolve(member, _locator(member, link), expected_child=None)
                    visit(native_cad.logical_file(path.parent, link['file']))
            active.remove(path)
        visit(source)
        basenames = [path.name.casefold() for path in paths]
        if len(set(basenames)) != len(basenames):
            raise ValueError('참조 부품의 파일 이름이 겹칩니다. FreeCAD에서 함께 열고 .caepre로 저장하세요.')
        names = {path: 'document' + str(i) for i, path in enumerate(paths)}
        for path in paths:
            member = names[path]
            add_file(path, member, 'documents/' + path.name, 'pre_document')
            issues.extend(_declared_file_issues(payloads[member], member))
            for link in _links(payloads[member]):
                if link['file']:
                    edge(member, link, names[native_cad.logical_file(path.parent, link['file'])])
        identity = source_document_id or 'P' + uuid.uuid4().hex
        entry = names[source]
        saved_revision, native_revision = None, None
        identity_origin, revision_origin = 'registration_assigned', 'registered_snapshot'
        embedded = _embedded_metadata(payloads[entry])
        if embedded and embedded.get('document_id'):
            from caelab.storage import check_id
            identity = check_id(embedded['document_id'])
            identity_origin = 'embedded_metadata'
    from caelab.native_project_contract import metadata_declared_links
    source_links = []
    metadata_sites = []
    if source.suffix.lower() == '.caepre':
        metadata_sites.append((manifest.get('metadata', {}), None, {'kind': 'project'}))
        native_entry = names[manifest['entry']]
    else:
        native_entry = entry
    for member in members:
        if member['role'] == 'pre_document':
            stored = _embedded_metadata(payloads[member['id']])
            if stored is not None:
                site = ({'kind': 'project'} if member['id'] == native_entry else
                        {'kind': 'pre_object', 'document_member': member['id'], 'object_name': 'CAELabProject'})
                metadata_sites.append((stored, member['id'], site))
    for stored, member, site in metadata_sites:
        declared = metadata_declared_links(stored, native_kind='pre', source=site)
        for link in declared['links']:
            if link not in source_links:
                source_links.append(link)
        for problem in declared['issues']:
            issue = _issue('LINK_UNSUPPORTED', problem['message'], member=member,
                           recovery='원 계산 연결 기록은 보존됩니다. 필요한 계산 자료를 별도로 확인하세요.')
            issue['severity'] = 'warning'
            issues.append(issue)
    record = {'version': 1, 'native_kind': 'pre', 'input_kind': 'native_design',
              'format': source.suffix.lower()[1:], 'source_document_id': identity,
              'saved_revision': saved_revision, 'native_revision': native_revision,
              'identity_origin': identity_origin, 'revision_origin': revision_origin,
              'entry_member': entry, 'source_manifest_pin': manifest_pin,
              'members': members, 'edges': edges, 'reader_bindings': [],
              'native_metadata_bindings': [], 'logical_origins': origins,
              'unavailable': unavailable, 'source_links': source_links,
              'relocation_bases': [], 'history_availability': [],
              'producer': {'application': 'freecad', 'version': None, 'origin': 'saved_metadata'},
              'required_capabilities': ['freecad_xlink_v1'],
              'validation': {'closure': 'DECLARED_PARTIAL' if any(row['severity'] == 'error' for row in issues) else 'COMPLETE', 'issues': issues}}
    from caelab.native_project_contract import finalize_snapshot
    record = finalize_snapshot(record)
    verify_snapshot_members(record, {row['member_id']: row['source'] for row in files})
    if _replacements is not None:
        _replacements.verify_consumed()
    return {'snapshot': record, 'files': files,
            'bindings': [deepcopy(row) for row in edges if row['child_member'] is not None], 'issues': issues}


def verify_snapshot_members(snapshot, member_paths):
    """Reparse copied bytes using the fixed member table, never old host paths."""
    from caelab.native_project_contract import validate_snapshot
    snapshot = validate_snapshot(snapshot)
    payloads, names = {}, {}
    for row in snapshot['members']:
        if row['storage'] == 'file':
            path = Path(member_paths[row['id']]).resolve(strict=True)
            data = path.read_bytes()
            if row['role'] == 'pre_archive':
                native_cad.inspect_project(path)
        else:
            parent = payloads.get(row['archive_member_of'])
            if parent is None:
                raise ValueError('Archive member precedes its container')
            with zipfile.ZipFile(io.BytesIO(parent)) as archive:
                data = archive.read(row['archive_member'])
        if _pin(data) != {'bytes': row['bytes'], 'sha256': row['sha256']}:
            raise ValueError('Native saved member changed: ' + row['id'])
        payloads[row['id']] = data
        names[row['id']] = row
    expected = {row['parent_member']: [] for row in snapshot['edges']}
    origins = {row['member_id']: row['original_location'] for row in snapshot['logical_origins']}
    archive_names = {(row.get('archive_member_of'), row.get('archive_member')): row['id']
                     for row in snapshot['members'] if row['storage'] == 'archive_member'}
    origin_names = {native_cad.logical_file(Path(value).parent, Path(value).name): member
                    for member, value in origins.items() if names[member]['role'] == 'pre_document'}
    for row in snapshot['edges']:
        expected[row['parent_member']].append(row['locator'])
        child = row['child_member']
        if child is not None and names[child]['role'] != 'pre_document':
            raise ValueError('Native Link must refer to a document member')
        parent = names[row['parent_member']]
        value = row['locator']['original_file']
        if parent['storage'] == 'archive_member':
            relative = str(PurePosixPath(parent['archive_member']).parent / value)
            native_cad._safe_member(relative)
            resolved = archive_names.get((parent['archive_member_of'], relative))
        else:
            resolved = origin_names.get(native_cad.logical_file(Path(origins[parent['id']]).parent, value))
        if child != resolved:
            raise ValueError('Native Link target differs from its exact logical origin')
    for member, row in names.items():
        if row['role'] == 'pre_document':
            actual = [_locator(member, link) for link in _links(payloads[member]) if link['file']]
            if actual != expected.get(member, []):
                raise ValueError('Native Link slots differ from the saved closure')
    # Read again after parse, including all registered files, to detect mutation.
    for row in snapshot['members']:
        if row['storage'] == 'file':
            if native_cad.sha(member_paths[row['id']]) != row['sha256']:
                raise ValueError('Native input changed during verification')
    return {'complete': snapshot['validation']['closure'] == 'COMPLETE',
            'member_count': len(names), 'snapshot_sha256': snapshot['snapshot_sha256']}


def verify_relocation(original, derived, edits):
    """Prove that only the declared exact XLink file attributes changed."""
    import xml.etree.ElementTree as ET
    before, after = Path(original).read_bytes(), Path(derived).read_bytes()
    with zipfile.ZipFile(io.BytesIO(before)) as source, zipfile.ZipFile(io.BytesIO(after)) as target:
        if source.namelist() != target.namelist():
            raise ValueError('Native relocation changed archive entries')
        left, right = native_cad._xml(source), native_cad._xml(target)
        def slots(tree):
            result = {}
            for obj in tree.findall('.//Object'):
                for prop in obj.findall('./Properties/Property'):
                    for index, link in enumerate(prop.findall('.//XLink')):
                        result[(obj.get('name'), prop.get('name'), index, link.get('name', ''))] = link
            return result
        old_slots, new_slots = slots(left), slots(right)
        if old_slots.keys() != new_slots.keys():
            raise ValueError('Native relocation changed Link identity')
        seen = set()
        for edit in edits:
            locator = edit['locator']
            key = (locator['object_name'], locator['property_name'], locator['xlink_index'], locator['target_name'])
            if key in seen or key not in old_slots:
                raise ValueError('Duplicate or unknown relocation slot')
            seen.add(key)
            old, new = old_slots[key], new_slots[key]
            if (old.get('file', '') != locator['original_file'] or old.get('file', '') != edit['old_value']
                    or new.get('file', '') != edit['new_value']):
                raise ValueError('Native relocation differs from the approved exact slot')
            old.set('file', '__approved_relocation__'); new.set('file', '__approved_relocation__')
        if ET.tostring(left) != ET.tostring(right):
            raise ValueError('Native relocation changed data outside XLink file slots')
        for name in source.namelist():
            if name != 'Document.xml' and source.read(name) != target.read(name):
                raise ValueError('Native relocation changed an original archive member')
    return {'original_data_unchanged': True, 'bytes': len(after), 'sha256': hashlib.sha256(after).hexdigest()}


def saved_offer(owner):
    owner.assert_thread()
    descriptor = owner.descriptor()
    docs = owner.project._documents()
    pending = [doc.Name for doc in docs if owner.Gui.getDocument(doc.Name).getInEdit()]
    saved = deepcopy(owner.project.last_save)
    if saved is None and hasattr(owner, 'portable_binding'):
        saved = {'revision': owner.portable_binding.reference['saved_revision'], 'portable_source': True}
    return {'title': owner.doc.Label, 'saved': saved,
            'dirty': not owner.project.is_saved(),
            'busy': bool(owner.project.in_save or descriptor['pending_edit'] or pending
                         or owner.pose_candidates.busy or owner.fem._pending),
            'stamp': {'document_id': owner.document_id, 'kind': 'pre', 'session_id': owner.session_id,
                      'generation': owner.generation, 'view_generation': owner.view_generation,
                      'saved_revision': (owner.project.last_save or {}).get('revision'),
                      'graph_version': owner.project.graph_version()},
            'documents': [{'name': doc.Name, 'title': doc.Label,
                           'modified': bool(owner.Gui.getDocument(doc.Name).Modified)} for doc in docs]}


def last_saved_file(owner):
    """Return the exact completed revision, never whichever path is newest."""
    saved = owner.project.last_save or {}
    path = saved.get('retained_project') or saved.get('opened_source')
    expected_identity = owner.document_id
    if path is None and hasattr(owner, 'portable_binding') and hasattr(owner, 'portable_context'):
        from caelab.native_project_inputs import verify_registered
        verified = verify_registered(owner.portable_context, owner.portable_binding.reference, full=True)
        path = verified.entry_path
        saved = {'revision': verified.reference['saved_revision']}
        expected_identity = verified.reference['document_id']
        if verified.snapshot['format'] == 'fcstd':
            return path  # The exact registered raw set has no managed archive revision to infer.
    if not path:
        raise ValueError('먼저 프로젝트를 저장하세요. 현재 편집은 유지됩니다.')
    path = Path(path).resolve(strict=True)
    manifest = native_cad.inspect_project(path)
    if manifest['revision'] != saved.get('revision') or manifest['document_id'] != expected_identity:
        raise ValueError('마지막 저장본의 내용이 바뀌었습니다. 원 저장 파일을 확인하세요.')
    if saved.get('sha256') and native_cad.sha(path) != saved['sha256']:
        raise ValueError('마지막 저장본의 파일이 바뀌었습니다. 다른 파일로 자동 대체하지 않습니다.')
    return path


def capture_native_selection(owner, documents):
    """Optional native UI state, separate from geometry/source input metadata."""
    members = {doc.Name: 'document' + str(index) for index, doc in enumerate(documents)}
    selections = []
    for doc in documents:
        for selected in owner.Gui.Selection.getSelectionEx(doc.Name):
            obj = selected.Object
            if obj.Document is not doc:
                raise ValueError('Native selection document changed during save')
            selections.append({'document_member': members[doc.Name], 'occurrence_chain': [],
                               'object_name': obj.Name, 'subelements': list(selected.SubElementNames)})
    return selections


def save_working(owner, context, *, expected_stamp, path=None, command_id=None):
    """Complete native Save and advance only this target's expected head.

    If publication fails, callers keep this witness and reconcile the pointer;
    the managed archive has already been saved and must not be saved again.
    """
    from caelab.native_project_contract import require_open_binding
    from caelab.native_project_inputs import prepare_target_save, publish_head
    binding = require_open_binding(owner.portable_binding)
    if owner.document_id != binding.owner_document_id:
        raise ValueError('이 저장본의 현지 작업 사본을 먼저 선택하세요.')
    command_id = command_id or 'C' + uuid.uuid4().hex
    if not hasattr(owner, '_portable_head_actions'):
        owner._portable_head_actions = {}
    expected = owner._portable_head_actions.setdefault(command_id, deepcopy(
        getattr(owner, '_portable_head', binding.expected_head)))
    reservation = prepare_target_save(context, binding.open_id, expected_stamp=expected_stamp,
                                      expected_head=expected, command_id=command_id)
    owner._portable_pending_save = {'expected_stamp': deepcopy(expected_stamp), 'path': path, 'command_id': command_id}
    witness = complete_save(owner, expected_stamp=expected_stamp, path=path,
                            command_id=reservation.save_command_id, _target_save=reservation)
    # Persisting/reconciling an interrupted head is the existing N0 action journal.
    result = publish_head(context, reservation.target_id, witness, expected_head=expected,
                          command_id='C'+canonical_hash({'save': command_id, 'target': reservation.target_id})[:40],
                          _target_save=reservation)
    head = result['head']
    current = getattr(owner, '_portable_head', binding.expected_head) or {'generation': -1}
    if head['head_generation'] >= current['generation']:
        owner._portable_head = {'generation': head['head_generation'], 'reference': head['reference']}
    owner.native_target = reservation.target_id
    if getattr(owner, '_portable_pending_save', {}).get('command_id') == command_id:
        del owner._portable_pending_save
    return {'witness': witness, 'publication': result}


def _reject_unstarted_save(owner, request, error):
    """Record only this authenticated owner's proven pre-adapter Save refusal.

    The caller must not invoke this after entering complete_save_command. That
    adapter already distinguishes preflight/native errors from a returned Save.
    """
    if (getattr(owner, 'closed', True) or not isinstance(error, BaseException)
            or request.get('operation') not in {'document.save', 'pre.project.save'}
            or request.get('document_id') != owner.document_id
            or request.get('session_id') != owner.session_id
            or request.get('command_id') in getattr(owner, '_portable_save_outcomes', {})):
        return False
    try:
        from caelab.native_project_contract import require_open_binding, require_target_save
        from caelab.native_project_inputs import resume_target_save, _record_target_save_failure
        binding = require_open_binding(owner.portable_binding)
        wire = request.get('_target_save')
        if not isinstance(wire, dict) or set(wire) != {'prepare_command_id', 'save_command_id', 'open_id'}:
            return False
        reservation = require_target_save(resume_target_save(owner.native_project_context, wire['prepare_command_id']))
        if (binding.owner_document_id != owner.document_id or wire['open_id'] != binding.open_id
                or reservation.open_id != binding.open_id
                or wire['save_command_id'] != request.get('command_id')
                or reservation.save_command_id != request.get('command_id')
                or reservation.owner_document_id != owner.document_id
                or reservation.expected_stamp['document_id'] != owner.document_id
                or reservation.expected_stamp['session_id'] != owner.session_id):
            return False
        # This existing helper also refuses REGISTERED/PUBLISHED or any changed
        # reservation, so lack of an original reply cannot become a failure.
        _record_target_save_failure(owner.native_project_context, reservation, error, stage='before_save')
        return True
    except (AttributeError, KeyError, TypeError, ValueError, OSError):
        # Unverifiable/changed evidence stays unconfirmed. Preserve the native
        # rejection itself rather than replacing it with a recovery error.
        return False

def complete_save_command(owner, request):
    """Consume only the authenticated broker's private reservation on its owner."""
    from caelab.native_project_contract import require_open_binding, require_target_save
    from caelab.native_project_inputs import resume_target_save, _save_witness_receipt
    binding = require_open_binding(owner.portable_binding)
    wire = request.get('_target_save')
    if not isinstance(wire, dict) or set(wire) != {'prepare_command_id', 'save_command_id', 'open_id'}:
        raise ValueError('저장 대상을 먼저 확인한 뒤 같은 저장 요청을 다시 선택하세요.')
    reservation = require_target_save(resume_target_save(owner.native_project_context, wire['prepare_command_id']))
    if (wire['open_id'] != binding.open_id or reservation.open_id != binding.open_id
            or wire['save_command_id'] != request['command_id']
            or reservation.save_command_id != request['command_id']
            or reservation.owner_document_id != owner.document_id
            or reservation.expected_stamp['session_id'] != owner.session_id):
        raise ValueError('Native Save reservation differs from this actual owner command')
    witness = complete_save(owner, expected_stamp=reservation.expected_stamp,
                            command_id=request['command_id'], _target_save=reservation)
    return {**deepcopy(witness.source), 'native_save_receipt':
            _save_witness_receipt(witness, binding, _target_save=reservation)}

def complete_save(owner, *, expected_stamp, path=None, command_id=None, _target_save=None):
    """Exactly one existing managed native save; never infer success from a label."""
    command_id = command_id or 'C' + uuid.uuid4().hex
    from caelab.storage import check_id
    check_id(command_id)
    if hasattr(owner, 'portable_binding'):
        from caelab.native_project_contract import require_target_save
        reservation = require_target_save(_target_save)
        if (reservation.open_id != owner.portable_binding.open_id or reservation.owner_document_id != owner.document_id
                or reservation.expected_stamp != expected_stamp or reservation.save_command_id != command_id):
            raise ValueError('Native Save reservation belongs to another owner or request')
        path = Path(path or (reservation.native_save_root/'design.caepre')).resolve()
        if not path.is_relative_to(reservation.native_save_root.resolve()):
            raise ValueError('기존 원본 또는 다른 사본에 저장할 수 없습니다. 이 작업 사본 안에 저장하세요.')
    elif _target_save is not None:
        raise ValueError('Native target Save reservation requires its actual opened owner')
    request = canonical_hash({'stamp': expected_stamp, 'path': str(Path(path).resolve()) if path else None,
                              'target_save': _target_save.request_sha256 if _target_save is not None else None})
    previous = getattr(owner, '_portable_save_outcomes', {}).get(command_id)
    if previous is not None:
        if previous[0] != request:
            raise ValueError('COMMAND_CONFLICT: 같은 저장 요청의 내용이 달라졌습니다.')
        witness = previous[1]
        if _pin(witness.saved_file.read_bytes()) != witness.pin:
            raise ValueError('INPUT_CHANGED: 보존한 저장 파일이 바뀌었습니다.')
        return witness
    try:
        current = saved_offer(owner)
        if current['stamp'] != expected_stamp:
            raise ValueError('INPUT_CHANGED: 모델이 바뀌었습니다. 저장할 내용을 다시 확인하세요.')
        if _target_save is not None:
            from . import metadata
            actual = {Path(doc.FileName).resolve(): metadata.read(doc).get('document_id')
                      for doc in owner.project._documents()}
            for row in owner.portable_binding.owner_id_map:
                member = row['member_id']
                if actual.get(Path(owner.portable_binding.member_paths[member]).resolve()) != row['owner_document_id']:
                    raise ValueError('OWNER_IDENTITY_CHANGED: 부품 식별 정보가 바뀌었습니다. 원 작업 사본을 유지하세요.')
    except Exception as error:
        if _target_save is not None:
            from caelab.native_project_inputs import _record_target_save_failure
            _record_target_save_failure(owner.native_project_context, _target_save, error, stage='before_save')
            if hasattr(owner, '_portable_pending_save'):
                del owner._portable_pending_save
        raise
    prior = getattr(owner, '_native_target_save', None)
    try:
        if _target_save is not None:
            owner._native_target_save = _target_save
        try:
            result = owner.project.save(path)
        except Exception as error:
            if _target_save is not None:
                from caelab.native_project_inputs import _record_target_save_failure
                _record_target_save_failure(owner.native_project_context, _target_save, error)
                if hasattr(owner, '_portable_pending_save'):
                    del owner._portable_pending_save
            raise
    finally:
        if prior is None:
            if hasattr(owner, '_native_target_save'):
                del owner._native_target_save
        else:
            owner._native_target_save = prior
    from caelab.native_project_contract import _completed_save_witness
    witness = _completed_save_witness('pre', result['retained_project'], owner_stamp=current['stamp'],
                                      command_id=command_id, publication_complete=True, source=result)
    if not hasattr(owner, '_portable_save_outcomes'):
        owner._portable_save_outcomes = {}
    owner._portable_save_outcomes[command_id] = (request, witness)
    return witness


def _trusted(verified, binding):
    from caelab.native_project_contract import require_verified_input, require_open_binding
    require_verified_input(verified)
    require_open_binding(binding)
    if (verified.reference != binding.reference or verified.context_session != binding.context_session
            or verified.snapshot['native_kind'] != 'pre'):
        raise ValueError('Native open binding differs from its verified source')
    verify_snapshot_members(verified.snapshot, verified.member_paths)


def open_bound_project(owner, verified_receipt, binding):
    """Existing Project.open materializes the native graph; no live-owner swap."""
    owner.assert_thread()
    _trusted(verified_receipt, binding)
    receipt = native_open_receipt(verified_receipt)
    source = Path(receipt['path']).resolve(strict=True)
    if source.suffix.lower() == '.caepre':
        manifest = native_cad.inspect_project(source)
        names = {row['native_name'] for row in manifest['documents']}
    else:
        names = {Path(path).stem for path in verified_receipt.member_paths.values()}
    if names & set(owner.App.listDocuments()):
        raise ValueError('OPEN_IN_NEW_PROCESS: 같은 이름의 문서가 열려 있습니다. 사본을 새 FreeCAD 창에서 여세요.')
    return owner.project.open(receipt, _portable_binding=(verified_receipt, binding))


def native_open_receipt(verified):
    """Hydrate only the existing Project.open's file locators from verified pins."""
    from caelab.native_project_contract import require_verified_input
    require_verified_input(verified)
    receipt = deepcopy(verified.receipt)
    receipt['path'] = str(verified.entry_path)
    rows = {row['relative']: row for row in verified.snapshot['members'] if row['storage'] == 'file'}
    for row in receipt['files']:
        row['path'] = str(verified.member_paths[rows[row['relative']]['id']])
    origins = {row['member_id']: row['original_location'] for row in verified.snapshot['logical_origins']}
    receipt.setdefault('native_metadata', {})['original_locations'] = {
        row['relative']: origins[row['id']] for row in rows.values() if row['id'] in origins}
    return receipt


def verify_prepared(verified, binding):
    """Check native_cad's prepared graph before FreeCAD can open any member."""
    _trusted(verified, binding)
    folder = Path(binding.working_root).resolve(strict=True)
    snapshot = verified.snapshot
    proofs = []
    if snapshot['format'] == 'caepre':
        for row in snapshot['members']:
            if row['role'] == 'pre_document':
                path = folder / row['archive_member']
                if path.stat().st_size != row['bytes'] or native_cad.sha(path) != row['sha256']:
                    raise ValueError('Prepared native archive member changed')
    else:
        rows = {row['id']: row for row in snapshot['members']}
        for row in snapshot['members']:
            edits = []
            for edge in snapshot['edges']:
                if edge['parent_member'] == row['id'] and edge['child_member'] is not None:
                    edits.append({'locator': edge['locator'], 'old_value': edge['original_reference'],
                                  'new_value': Path(rows[edge['child_member']]['relative']).name})
            proof = verify_relocation(verified.member_paths[row['id']], folder / Path(row['relative']).name, edits)
            proofs.append({'source_member': row['id'], **proof, 'edits': edits})
    return {'source_snapshot_sha256': snapshot['snapshot_sha256'], 'original_data_unchanged': True,
            'derived_members': proofs}


def bind_opened(owner, doc, manifest, source, verified, binding):
    """Private Project.open hook, after native read and before remember_open.

    Identity initialization precedes user transactions. Source bytes,
    source manifest and engineering source bindings remain unchanged.
    """
    _trusted(verified, binding)
    from . import metadata
    from dataclasses import replace
    working = deepcopy(manifest)
    new_branch = binding.intent == 'saved' or verified.snapshot['source_document_id'] != binding.owner_document_id
    working['document_id'] = binding.owner_document_id
    if new_branch:
        working['new_design_branch'] = True
    else:
        working.pop('new_design_branch', None)
    folder = Path(binding.working_root).resolve()
    derived = {}
    for row in verified.snapshot['members']:
        if row['storage'] == 'archive_member' and row['role'] == 'pre_document':
            derived[row['id']] = folder / row['archive_member']
        elif row['storage'] == 'file' and row['role'] == 'pre_document':
            derived[row['id']] = folder / Path(row['relative']).name
    members_by_path = {path.resolve(): member for member, path in derived.items()}
    # XLink may lazily load only a child's referenced features. Writing a new
    # identity in such a document can be ignored by native Save. Use FreeCAD's
    # own full-document reload before ANY working metadata transaction.
    for _ in range(native_cad.MAX_FILES):
        partial = next((item for item in _document_closure(doc) if getattr(item, 'Partial', False)), None)
        if partial is None:
            break
        if partial is doc or Path(partial.FileName).resolve() not in members_by_path:
            raise ValueError('선택한 모델의 전체 편집 문서를 확인하지 못했습니다. 새 FreeCAD 창에서 다시 여세요.')
        loaded = owner.Gui.reload(partial.Name)
        if loaded is None or getattr(loaded, 'Partial', False):
            raise ValueError('외부 부품의 전체 편집 내용을 읽지 못했습니다. 원 저장본은 유지됩니다.')
    else:
        raise ValueError('Native document reload exceeds the saved closure bound')
    initialized_binding = replace(binding, member_paths=derived)
    documents = owner.project._documents() if doc is owner.doc else _document_closure(doc)
    receipts = []
    for current in documents:
        member = members_by_path.get(Path(current.FileName).resolve())
        if member is None:
            raise ValueError('Opened dependency is outside the exact derived native member map')
        expected = next((row['owner_document_id'] for row in binding.owner_id_map if row['member_id'] == member), None)
        if not new_branch and metadata.read(current).get('document_id') != expected:
            raise ValueError('OWNER_IDENTITY_CHANGED: 현지 저장본의 부품 식별 정보가 다릅니다.')
        if not current.UndoCount and not current.RedoCount:
            current.UndoMode = 1  # Same native managed-editable mode as Project.open's entry document.
        receipts.append(initialize_import_identity(current, initialized_binding, member_id=member))
    # Only the private manifest is passed to the existing attach_opened path.
    working['metadata'] = metadata.read(doc)
    working['_portable_identity_initialization'] = receipts  # Runtime OPENED context, not native saved metadata.
    if Path(doc.FileName).resolve() not in {path.resolve() for path in derived.values()}:
        raise ValueError('Opened document is outside the exact derived native member map')
    return working, initialized_binding


def _document_closure(doc):
    from .projects import _linked
    result, pending = [], [doc]
    while pending:
        current = pending.pop(0)
        if any(current is prior for prior in result):
            continue
        result.append(current)
        if len(result) > native_cad.MAX_FILES:
            raise ValueError('Native document graph exceeds 1024 documents')
        for obj in current.Objects:
            for name in obj.PropertiesList:
                if 'PropertyXLink' in obj.getTypeIdOfProperty(name):
                    pending.extend(link.Document for link in _linked(getattr(obj, name)))
    return result


def select_bound_target(owner, selection, binding):
    """Validate all exact native targets before changing native selection."""
    from caelab.native_project_contract import OpenBinding
    owner.assert_thread()
    if not isinstance(binding, OpenBinding) or owner.document_id != binding.working_document_id:
        raise ValueError('Select in the exact opened native working document')
    if (set(selection) != {'version', 'native_kind', 'snapshot_sha256', 'selection'}
            or selection['version'] != 1 or selection['native_kind'] != 'pre'
            or selection['snapshot_sha256'] != binding.reference['snapshot_sha256']):
        raise ValueError('Selection belongs to a different saved native snapshot')
    value = selection['selection']
    if set(value) != {'document_member', 'occurrence_chain', 'object_name', 'subelements'}:
        raise ValueError('Unknown native selection fields')
    paths = {Path(path).resolve(): member for member, path in binding.member_paths.items()}
    docs = {paths.get(Path(doc.FileName).resolve()): doc for doc in _document_closure(owner.doc)}
    doc = docs.get(value['document_member'])
    if doc is None:
        raise ValueError('Selected native document member is not open')
    obj = doc.getObject(value['object_name'])
    if obj is None:
        raise ValueError('Selected native object no longer exists')
    chain = value['occurrence_chain']
    if not isinstance(chain, list) or len(chain) > 64:
        raise ValueError('Invalid native occurrence chain')
    previous = None
    for step in chain:
        if set(step) != {'document_member', 'object_name'}:
            raise ValueError('Invalid native occurrence step')
        current_doc = docs.get(step['document_member'])
        current = current_doc.getObject(step['object_name']) if current_doc else None
        if current is None:
            raise ValueError('Selected occurrence no longer exists')
        if previous is not None:
            children = list(getattr(previous, 'Group', [])) + list(getattr(previous, 'ElementList', []))
            linked = getattr(previous, 'LinkedObject', None)
            if current not in children and linked is not current:
                raise ValueError('Selected occurrence path differs from the saved target')
        previous = current
    if chain and previous is not obj:
        raise ValueError('Occurrence chain does not end at the selected object')
    subs = value['subelements']
    if not isinstance(subs, list) or not all(isinstance(sub, str) and sub for sub in subs):
        raise ValueError('Invalid native subelement selection')
    for sub in subs:
        if obj.getSubObject(sub) is None:
            raise ValueError('Selected native subelement no longer exists')
    gui = owner.Gui
    gui.Selection.clearSelection()
    for sub in subs or ['']:
        gui.Selection.addSelection(doc.Name, obj.Name, sub)
    actual = gui.Selection.getSelectionEx(doc.Name)
    if len(actual) != 1 or actual[0].Object is not obj or list(actual[0].SubElementNames) != subs:
        raise ValueError('Native selection readback differs from the requested target')
    return {'selected': True, 'selection': deepcopy(selection)}


def inspect_repair(snapshot, replacements):
    """Read-only comparison; no missing pin is promoted into identical content."""
    output = []
    for replacement in replacements:
        expected = replacement.get('expected_child')
        path = Path(replacement['path']).resolve(strict=True)
        actual = {'bytes': path.stat().st_size, 'sha256': native_cad.sha(path)}
        status = ('UNKNOWN' if expected is None else
                  'IDENTICAL' if all(actual[key] == expected[key] for key in actual) else 'CONTENT_CHANGED')
        output.append({'status': status, 'expected_child': deepcopy(expected), 'actual': actual})
    return {'snapshot_sha256': snapshot['snapshot_sha256'], 'replacements': output,
            'applicable': bool(output) and all(row['status'] == 'IDENTICAL' for row in output)}


def _file_task(parent, title, work):
    """Use the existing cancellation token on a file-only worker, never App/Gui."""
    from PySide import QtCore, QtGui
    try:
        from PySide import QtWidgets as W
    except ImportError:
        W = QtGui
    import queue
    import threading
    from caelab.execution_control import CancellationToken, cancellation_scope
    token, result = CancellationToken(), queue.Queue()
    class Progress(W.QDialog):
        def closeEvent(self, event):
            token.request(); label.setText('취소를 요청했습니다. 현재 파일 처리가 끝날 때까지 기다리세요.')
            cancel.setEnabled(False); event.ignore()
    dialog = Progress(parent); dialog.setWindowTitle(title); dialog.setMinimumWidth(390)
    layout = W.QVBoxLayout(dialog)
    label = W.QLabel(title); label.setWordWrap(True); layout.addWidget(label)
    bar = W.QProgressBar(); bar.setRange(0, 0); layout.addWidget(bar)
    cancel = W.QPushButton('취소'); layout.addWidget(cancel)
    def request():
        token.request(); cancel.setEnabled(False)
        label.setText('취소를 요청했습니다. 발행이 끝났다면 그 결과를 먼저 확인합니다.')
    cancel.clicked.connect(request)
    def run():
        try:
            with cancellation_scope(token):
                value = work()
            result.put((True, value))
        except Exception as error:
            result.put((False, error))
    thread = threading.Thread(target=run, name='cae-native-file-copy')
    timer = QtCore.QTimer(dialog); timer.setInterval(40)
    settled = []
    def poll():
        try:
            item = result.get_nowait()
        except queue.Empty:
            return
        settled.append(item); timer.stop(); dialog.accept()
    timer.timeout.connect(poll); thread.start(); timer.start()
    try:
        dialog.exec_()
    finally:
        thread.join()
    if not settled:
        raise ValueError('파일 작업의 완료 상태를 확인하지 못했습니다. 원자료와 대상 폴더를 보존하세요.')
    succeeded, value = settled[0]
    if not succeeded:
        raise value
    return value


def show_copy_dialog(owner, context, *, on_open=None):
    """Native file action using the same registration/portable transaction.

    The caller supplies its current file context and native opener; no service,
    Client, owner or execution engine is manufactured by this dialog.
    """
    from PySide import QtCore, QtGui
    try:
        from PySide import QtWidgets as W
    except ImportError:
        W = QtGui
    from caelab.native_project_inputs import register_saved
    from caelab.portable_project import inspect_copy, create_copy
    offer = saved_offer(owner)
    parent = owner.Gui.getMainWindow()
    source, known_reference = None, None
    if offer['dirty'] or offer['saved'] is None:
        question = W.QMessageBox(parent)
        question.setWindowTitle('작업 사본에 포함할 모델')
        question.setText(offer['title'])
        question.setInformativeText('현재 변경을 저장해 포함하거나 마지막 저장본만 선택하세요.')
        current = question.addButton('현재 내용 저장 후 포함', W.QMessageBox.AcceptRole)
        last = question.addButton('마지막 저장본만', W.QMessageBox.ActionRole)
        question.addButton('취소', W.QMessageBox.RejectRole)
        current.setEnabled(not offer['busy'])
        last.setEnabled(offer['saved'] is not None)
        if offer['busy']:
            question.setInformativeText('편집 중인 작업을 완료하거나 취소한 뒤 현재 내용을 저장할 수 있습니다.')
        question.exec_()
        chosen = question.clickedButton()
        if chosen is current:
            save_path = None
            if owner.project.path is None and not hasattr(owner, 'portable_binding'):
                save_path = W.QFileDialog.getSaveFileName(parent, '프로젝트 저장', owner.doc.Name+'.caepre',
                                                         'CAE 프로젝트 (*.caepre)')[0]
                if not save_path:
                    return None
                if not save_path.lower().endswith('.caepre'):
                    save_path += '.caepre'
            if hasattr(owner, 'portable_binding'):
                completed = save_working(owner, context, expected_stamp=offer['stamp'], path=save_path)
                source = completed['witness']
                known_reference = completed['publication']['reference']
            else:
                source = complete_save(owner, expected_stamp=offer['stamp'], path=save_path)
        elif chosen is not last:
            return None
    if source is None:
        path = last_saved_file(owner)
        if hasattr(owner, 'portable_binding'):
            from caelab.native_project_inputs import verify_registered
            head = getattr(owner, '_portable_head', None)
            candidate = head['reference'] if head else owner.portable_binding.reference
            current = _file_task(parent, '마지막 저장본을 확인하는 중…',
                                  lambda: verify_registered(context, candidate, full=True))
            if native_cad.sha(current.entry_path) != native_cad.sha(path):
                raise ValueError('마지막 저장본과 현재 작업 사본의 저장 기록이 다릅니다. 목록을 다시 확인하세요.')
            known_reference = candidate
        approved = [(key, root) for key, root in context.approved_roots.paths.items() if path.is_relative_to(root)]
        if not approved:
            raise ValueError('저장 폴더를 승인된 모델 위치로 선택한 뒤 다시 시도하세요.')
        root_id, root = approved[0]
        source = {'mode': 'selected_file', 'native_kind': 'pre', 'root_id': root_id,
                  'relative': path.relative_to(root).as_posix()}
    registered = ({'reference': known_reference} if known_reference is not None else
                  _file_task(parent, '저장한 모델의 필수 부품을 확인하는 중…',
                             lambda: register_saved(context, source, command_id='C'+uuid.uuid4().hex)))
    selection = {'native': registered['reference'], 'copy_intent': 'complete', 'working_target': True}
    inspection = _file_task(parent, '작업 사본에 포함할 파일을 확인하는 중…', lambda: inspect_copy(context, [selection]))
    # The include list comes from the registered saved bytes, not current dirty objects.
    from caelab.native_project_inputs import verify_registered
    verified = _file_task(parent, '저장본을 확인하는 중…', lambda: verify_registered(context, registered['reference'], full=True))
    dialog = W.QDialog(parent); dialog.setWindowTitle('작업 사본 만들기')
    dialog.setMinimumSize(560, 340); dialog.resize(720, 430)
    layout = W.QVBoxLayout(dialog)
    title = W.QLabel(offer['title']); title.setTextFormat(QtCore.Qt.PlainText)
    font = title.font(); font.setPointSize(font.pointSize()+2); font.setBold(True); title.setFont(font)
    layout.addWidget(title)
    table = W.QTableWidget(0, 3); table.setHorizontalHeaderLabels(['포함할 문서', '종류', '크기'])
    table.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(W.QAbstractItemView.SelectRows)
    table.horizontalHeader().setStretchLastSection(True)
    rows = []
    if verified.snapshot['format'] == 'caepre':
        manifest = native_cad.inspect_project(verified.entry_path)
        rows = [(row.get('label') or row['native_name'], '편집 가능한 부품', row['bytes'])
                for row in manifest['documents']]
    else:
        rows = [(Path(row['relative']).stem, '외부 Link 문서' if row['id'] != verified.snapshot['entry_member'] else '모델', row['bytes'])
                for row in verified.snapshot['members'] if row['storage'] == 'file']
    table.setRowCount(len(rows))
    for index, row in enumerate(rows):
        for column, value in enumerate((row[0], row[1], format(row[2]/1024, '.1f')+' KB')):
            table.setItem(index, column, W.QTableWidgetItem(value))
    table.setColumnWidth(0, 300); table.setColumnWidth(1, 150)
    layout.addWidget(table, 1)
    note = W.QLabel('필수 외부 부품을 함께 포함합니다. 메시 생성과 계산은 실행하지 않습니다.')
    note.setWordWrap(True); layout.addWidget(note)
    buttons = W.QDialogButtonBox(W.QDialogButtonBox.Cancel)
    buttons.button(W.QDialogButtonBox.Cancel).setText('취소')
    copy_button = buttons.addButton('폴더 선택 후 복사…', W.QDialogButtonBox.AcceptRole)
    layout.addWidget(buttons)
    result = {}
    def publish():
        destination = W.QFileDialog.getExistingDirectory(dialog, '새 폴더 또는 빈 폴더 선택')
        if not destination:
            return
        copy_button.setEnabled(False)
        try:
            value = _file_task(dialog, '작업 사본을 만드는 중…', lambda: create_copy(
                context, inspection, destination, approved=True, command_id='C'+uuid.uuid4().hex,
                session_id=context.session_id))
            result.update(value=value, destination=destination)
            dialog.accept()
        except Exception as error:
            copy_button.setEnabled(True)
            note.setText('사본을 만들지 못했습니다. 모델과 필수 부품, 비어 있는 대상 폴더를 확인하세요. 원 저장본은 유지됩니다.')
            detail = W.QMessageBox(dialog); detail.setIcon(W.QMessageBox.Warning)
            detail.setWindowTitle('작업 사본을 만들지 못했습니다')
            detail.setTextFormat(QtCore.Qt.PlainText)
            detail.setText(note.text()); detail.setDetailedText(str(error)); detail.exec_()
    copy_button.clicked.connect(publish); buttons.rejected.connect(dialog.reject)
    if dialog.exec_() != W.QDialog.Accepted:
        return None
    done = W.QMessageBox(parent); done.setWindowTitle('작업 사본을 만들었습니다')
    done.setText('새 폴더에서 모델을 열어 작업을 이어갈 수 있습니다.')
    done.setInformativeText(result['destination'])
    folder_button = done.addButton('폴더 열기', W.QMessageBox.ActionRole)
    open_button = done.addButton('사본에서 모델 열기', W.QMessageBox.AcceptRole)
    open_button.setEnabled(on_open is not None)
    done.addButton('닫기', W.QMessageBox.RejectRole); done.exec_()
    if done.clickedButton() is folder_button:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(result['destination']))
    elif done.clickedButton() is open_button:
        on_open(Path(result['destination']))
    return result


_LOCAL_HOSTS = []  # Native UI lifetimes only, never portable authority or a document store.


def install_file_actions(config, *, connection=None, owner=None):
    """Attach native file commands. Existing service owners take precedence."""
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui
    try:
        from PySide import QtWidgets as W
    except ImportError:
        W = QtGui
    from .bridge import Owner
    from caelab.native_project_inputs import NativeOnlyContext
    main = Gui.getMainWindow()
    QAction = getattr(W, 'QAction', None) or QtGui.QAction
    existing = getattr(main, '_caelab_native_file_actions', None)
    if existing is not None:
        existing['config'].update(config)
        if connection is not None:
            existing['connection'] = connection
        if owner is not None and all(item is not owner for item in existing['owners']):
            existing['owners'].append(owner)
        existing['reconcile']()
        return existing
    file_menu = next((menu for menu in main.findChildren(W.QMenu)
                      if any(action.objectName() == 'Std_Open' for action in menu.actions())), None)
    if file_menu is None:
        raise ValueError('FreeCAD 파일 메뉴를 찾지 못했습니다. 작업대를 확인하세요.')
    # UI lifetime cache uses the existing Owner class. No second owner is made
    # for a document already attached to the normal Connection.
    local_owners = [owner] if owner is not None else []
    state = {'config': dict(config), 'connection': connection, 'owners': local_owners, 'disposed': set()}
    def dispose(item):
        if id(item) not in state['disposed']:
            state['disposed'].add(id(item))
            item.close()  # slotDeletedDocument only marks closed; resources still require cleanup.
            if hasattr(item, 'portable_context'):
                del item.portable_context
    def reconcile():
        docs = list(App.listDocuments().values())
        current_connection = state['connection']
        if 'refresh_save_action' in state:
            state['refresh_save_action']()
        for item in list(local_owners):
            connected = None
            if current_connection is not None:
                connected = current_connection.owners.get(item.doc.Name)
            if connected is not None and connected[0] is item:
                local_owners.remove(item)  # Its existing Connection owns cleanup from now on.
                continue
            if (item.closed or not any(item.doc is doc for doc in docs)
                    or (connected is not None and connected[0] is not item)):
                dispose(item); local_owners.remove(item)
    state['reconcile'] = reconcile
    def current():
        reconcile()
        if state['connection'] is not None:
            return state['connection'].active_owner()
        doc = App.ActiveDocument
        if doc is None:
            raise ValueError('먼저 모델을 여세요.')
        found = next((item for item in local_owners if item.doc is doc and not item.closed), None)
        if found is None:
            found = Owner(doc, Path(state['config']['output'])/'native-saves', App=App, Gui=Gui)
            local_owners.append(found)
        return found
    state['current_owner'] = current
    def context_for(active):
        if hasattr(active, 'portable_context'):
            return active.portable_context
        roots = {'Managed': active.export_root}
        active.export_root.mkdir(parents=True, exist_ok=True)
        if active.project.path:
            roots['Saved'] = active.project.path.parent
        saved = active.project.last_save or {}
        if saved.get('opened_source'):
            roots['Opened'] = Path(saved['opened_source']).resolve().parent
        active.portable_context = NativeOnlyContext(Path(state['config']['output'])/'native-file-actions', approved_roots=roots)
        return active.portable_context
    def report(error):
        box = W.QMessageBox(main); box.setIcon(W.QMessageBox.Warning)
        box.setWindowTitle('모델 작업을 완료하지 못했습니다')
        box.setTextFormat(QtCore.Qt.PlainText)
        box.setText('현재 모델과 저장본은 유지됩니다. 편집 중인 작업을 마치고 모델과 참조 부품을 다시 확인하세요.')
        box.setDetailedText(str(error)); box.exec_()
    def save():
        active = None
        try:
            active = current()
            if getattr(active, '_portable_pending_save', None) is None:
                from .connector_menu import store_native_pending
                store_native_pending(Gui, active)
            if getattr(active, '_portable_pending_save', None) is None:
                from .pretension_controls import store_native_pending
                store_native_pending(active, connection=state['connection'])
                from .initial_field_controls import store_native_pending as store_initial
                store_initial(active, connection=state['connection'])
            ctx = context_for(active)
            pending = getattr(active, '_portable_pending_save', None)
            if pending is not None:
                value = save_working(active, ctx, **pending)
            elif hasattr(active, 'portable_binding'):
                answer = W.QMessageBox.question(main, '프로젝트 저장',
                    '현재 모델과 참조 부품을 이 작업 사본에 저장하시겠습니까? 원 저장본은 유지됩니다.',
                    W.QMessageBox.Save | W.QMessageBox.Cancel, W.QMessageBox.Cancel)
                if answer != W.QMessageBox.Save:
                    return None
                value = save_working(active, ctx, expected_stamp=saved_offer(active)['stamp'])
            else:
                path = active.project.path
                if path is None:
                    path, _ = W.QFileDialog.getSaveFileName(main, '프로젝트 저장',
                        str(active.export_root/(active.doc.Name+'.caepre')), 'CAE 프로젝트 (*.caepre)')
                    if not path:
                        return None
                    if not str(path).lower().endswith('.caepre'):
                        path = str(path)+'.caepre'
                value = complete_save(active, expected_stamp=saved_offer(active)['stamp'], path=path)
            main.statusBar().showMessage('프로젝트와 참조 부품을 저장했습니다.')
            return value
        except Exception as error:
            if getattr(active, '_portable_pending_save', None) is not None:
                error = ValueError('저장 연결을 확인하지 못했습니다. 현재 편집과 원 저장본을 유지합니다. '
                                   '파일 메뉴의 저장 연결 다시 확인을 선택하세요.\n'+str(error))
            report(error)
            return None
    def reconfirm():
        try:
            active = current()
            pending = getattr(active, '_portable_pending_save', None)
            if pending is None:
                main.statusBar().showMessage('다시 확인할 저장 요청이 없습니다. 현재 모델을 저장하려면 프로젝트 저장을 선택하세요.')
                return None
            return save()
        except Exception as error:
            report(error)
            return None
    def copy():
        try:
            active = current()
            return show_copy_dialog(active, context_for(active), on_open=launch_copy)
        except Exception as error:
            report(error)
    def open_copy():
        path = W.QFileDialog.getExistingDirectory(main, '작업 사본 폴더 열기')
        if path:
            try: launch_copy(path)
            except Exception as error: report(error)
    file_menu.addSeparator()
    for name, title, callback in [('CAELabPortablePreSave', '프로젝트 저장', save),
                                  ('CAELabPortablePreReconfirm', '저장 연결 다시 확인', reconfirm),
                                  ('CAELabPortablePreCopy', '작업 사본 만들기…', copy),
                                  ('CAELabPortablePreOpen', '작업 사본 열기…', open_copy)]:
        action = QAction(title, main); action.setObjectName(name)
        action.triggered.connect(lambda unused=False, callback=callback: callback())
        file_menu.addAction(action)
    replacements = {}
    def refresh_save_action():
        active = next((item for item in local_owners if item.doc is App.ActiveDocument and not item.closed), None)
        enabled = state['connection'] is None and active is not None and hasattr(active, 'portable_binding')
        for action in main.findChildren(QAction):
            if action.objectName() == 'CAELabPortablePreSave':
                action.setVisible(not enabled)  # Native Save occupies its familiar place for a portable owner.
            elif action.objectName() == 'CAELabPortablePreReconfirm':
                action.setEnabled(active is not None and getattr(active, '_portable_pending_save', None) is not None)
        if enabled:
            for original in main.findChildren(QAction):
                if original.objectName() != 'Std_Save':
                    continue
                if original not in replacements:
                    proxy = QAction(original.icon(), '프로젝트 저장', main)
                    proxy.setObjectName('CAELabPortableNativeSave')
                    proxy.triggered.connect(lambda unused=False: save())
                    replacements[original] = (proxy, original.shortcuts())
                proxy, keys = replacements[original]
                if original.shortcuts():
                    keys = original.shortcuts(); replacements[original] = (proxy, keys)
                proxy.setShortcuts(keys); original.setShortcuts([])
                widgets = original.associatedObjects() if hasattr(original, 'associatedObjects') else original.associatedWidgets()
                for widget in list(widgets):
                    if hasattr(widget, 'actions') and original in widget.actions():
                        widget.insertAction(original, proxy); widget.removeAction(original)
        else:
            for original, (proxy, keys) in list(replacements.items()):
                widgets = proxy.associatedObjects() if hasattr(proxy, 'associatedObjects') else proxy.associatedWidgets()
                for widget in list(widgets):
                    if hasattr(widget, 'actions') and proxy in widget.actions():
                        widget.insertAction(proxy, original); widget.removeAction(proxy)
                proxy.setShortcuts([]); original.setShortcuts(keys)
                proxy.deleteLater()
            replacements.clear()
    state['refresh_save_action'] = refresh_save_action
    refresh_save_action()
    def close():
        timer.stop()
        state['connection'] = object()  # Restore native actions before releasing our UI.
        refresh_save_action()
        for item in list(local_owners):
            dispose(item)
        local_owners.clear()
    timer = QtCore.QTimer(main); timer.setInterval(500); timer.timeout.connect(reconcile); timer.start()
    state.update(timer=timer, current=current, context_for=context_for, close=close, save=save, reconfirm=reconfirm)
    main._caelab_native_file_actions = state
    W.QApplication.instance().aboutToQuit.connect(close)
    _LOCAL_HOSTS.append(state)
    return state


def launch_copy(folder, *, target_id=None, command_id=None):
    """Launch a new native process; successful production windows belong to users.

    Tests wrap their parent invocation in native_check. The current installation
    and source location are used, never an executable remembered by the copy.
    """
    import FreeCAD as App
    import subprocess
    import os
    from caelab.portable_project import verify_project
    from caelab.storage import save_json, load_json, check_id
    folder = Path(folder).resolve(strict=True)
    if verify_project(folder)['status'] != 'READY':
        raise ValueError('작업 사본의 누락 또는 변경된 파일을 먼저 복구하세요.')
    if target_id is None:
        manifest = load_json(folder/'portable-project.json')
        targets = [row for row in manifest.get('native_projects', []) if row['native_kind'] == 'pre']
        if not targets:
            raise ValueError('이 사본에 편집할 FreeCAD 모델이 없습니다.')
        if len(targets) == 1:
            target_id = targets[0]['target_id']
        else:
            import FreeCADGui as Gui
            from PySide import QtGui
            try:
                from PySide import QtWidgets as W
            except ImportError:
                W = QtGui
            labels = [str(index+1)+'. '+row['title'] for index, row in enumerate(targets)]
            chosen, accepted = W.QInputDialog.getItem(Gui.getMainWindow(), '작업 사본 모델 열기',
                                                       '모델', labels, 0, False)
            if not accepted:
                return None
            target_id = targets[labels.index(chosen)]['target_id']
    command_id = check_id(command_id or 'C'+uuid.uuid4().hex)
    launch = folder/'workbench'/'native_project'/'launches'/command_id
    record = launch/'launch.json'
    arguments = {'folder': str(folder), 'target_id': target_id}
    if record.exists():
        previous = load_json(record)
        if previous['arguments'] != arguments:
            raise ValueError('COMMAND_CONFLICT: 같은 열기 요청의 모델이 달라졌습니다.')
        return previous
    launch.mkdir(parents=True, exist_ok=False)
    executable = Path(App.getHomePath())/'bin'/('FreeCAD.exe' if os.name == 'nt' else 'FreeCAD')
    executable = executable.resolve(strict=True)
    repo = Path(__file__).resolve().parents[2]
    macro = launch/'open.FCMacro'
    macro.write_text('import sys\nsys.path.insert(0, '+repr(str(repo))+')\n'
        'from PySide import QtCore\nfrom apps.desktop_pre.portable_project import _open_from_launch\n'
        'QtCore.QTimer.singleShot(300, lambda: _open_from_launch('+repr(str(folder))+', '+repr(target_id)+
        ', '+repr(command_id)+', '+repr(str(launch))+'))\n', encoding='utf8')
    environment = os.environ.copy()
    for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH',
                'CAELAB_ORIGIN_JOB_ID', 'CAE_POST_MEASUREMENT', 'CAE_POST_REPORT_ORIGIN'):
        environment.pop(key, None)
    # Journal intent before launch. An uncertain outcome is reconciled rather
    # than launching a second process for the same command.
    result = {'status': 'OPEN_UNCONFIRMED', 'command_id': command_id, 'arguments': arguments}
    save_json(record, result)
    with (launch/'stdout.log').open('wb') as stdout, (launch/'stderr.log').open('wb') as stderr:
        process = subprocess.Popen([str(executable), '--user-cfg', str(launch/'user.cfg'),
                                    '--system-cfg', str(launch/'system.cfg'), str(macro)], cwd=repo, env=environment,
                                   stdout=stdout, stderr=stderr)
    result.update(status='LAUNCH_REQUESTED', pid=process.pid)
    save_json(record, result)
    return result


def _open_from_launch(folder, target_id, command_id, launch):
    from caelab.storage import save_json
    try:
        owner, actual = open_local_copy(folder, target_id=target_id, command_id=command_id)
        save_json(Path(launch)/'opened.json', actual)
        return owner
    except Exception as error:
        save_json(Path(launch)/'opened.json', {'status': 'FAILED', 'error': str(error)})
        import FreeCADGui as Gui
        from PySide import QtGui
        try:
            from PySide import QtWidgets as W
        except ImportError:
            W = QtGui
        box = W.QMessageBox(Gui.getMainWindow()); box.setIcon(W.QMessageBox.Warning)
        box.setWindowTitle('작업 사본을 열지 못했습니다')
        box.setText('원 저장본은 유지됩니다. 사본 폴더의 필수 부품과 저장 상태를 확인한 뒤 다시 여세요.')
        box.setDetailedText(str(error)); box.exec_()
        return None


def open_local_copy(folder, *, target_id=None, command_id=None, selection=None, intent='working', reference=None):
    """Fresh native process entry; its verified folder supplies no old runtime."""
    import FreeCAD as App
    import FreeCADGui as Gui
    from .bridge import Owner
    from .assembly_pose_candidate import _hold
    from caelab.native_project_inputs import NativeOnlyContext
    from caelab.portable_project import verify_project
    from caelab.portable_project_native import prepare_open, verify_opened, _native_open_readback
    from caelab.storage import load_json
    folder = Path(folder).resolve(strict=True)
    checked = verify_project(folder)
    if checked['status'] != 'READY':
        raise ValueError('작업 사본의 파일을 확인하지 못했습니다. 원 파일을 보존하고 누락된 부품을 복구하세요.')
    if App.listDocuments():
        raise ValueError('사본을 새 FreeCAD 창에서 여세요. 열려 있는 문서는 유지됩니다.')
    manifest = load_json(folder/'portable-project.json')
    targets = [row for row in manifest['native_projects'] if row['native_kind'] == 'pre']
    if target_id is None and len(targets) != 1:
        raise ValueError('열 모델을 명시적으로 선택하세요.')
    target = next((row for row in targets if target_id is None or row['target_id'] == target_id), None)
    if target is None:
        raise ValueError('선택한 모델이 이 사본에 없습니다.')
    head = load_json(folder/target['head_file'])
    context = NativeOnlyContext(folder, approved_roots={'Project': folder})
    if intent not in {'working', 'saved'}:
        raise ValueError('Choose saved or working native open explicitly')
    if reference is not None and intent != 'saved':
        raise ValueError('Working open must use the current exact target head')
    request = {'reference': reference or head['reference'], 'intent': intent,
               'target_id': target['target_id'] if intent == 'working' else None,
               'expected_head': {'generation': head['head_generation'], 'reference': head['reference']} if intent == 'working' else None,
               'selection': deepcopy(selection), 'allow_partial': False}
    ticket = prepare_open(context, request, command_id=command_id or 'C'+uuid.uuid4().hex)
    return _open_ticket(context, ticket, selection=selection)


def open_launch_config(config_path):
    """Private startup path supplied by the existing authenticated launcher."""
    from caelab.portable_project_native import resume_open_ticket
    from caelab.storage import load_json
    context, ticket = resume_open_ticket(config_path)
    record = load_json(context.open_actions[ticket.binding.open_id])
    return _open_ticket(context, ticket, selection=record['request']['selection'])


def _open_ticket(context, ticket, *, selection=None):
    import FreeCAD as App
    import FreeCADGui as Gui
    from .bridge import Owner
    from .assembly_pose_candidate import _hold
    from caelab.portable_project_native import verify_opened, _native_open_readback
    if App.listDocuments():
        raise ValueError('사본을 새 FreeCAD 창에서 여세요. 열려 있는 문서는 유지됩니다.')
    bootstrap = App.newDocument('CopyOpening'); _hold(bootstrap)
    launcher = Owner(bootstrap, ticket.binding.target_root/'local', App=App, Gui=Gui)
    owner = None
    try:
        result = open_bound_project(launcher, ticket.verified_input, ticket.binding)
        doc = App.getDocument(result['native_document']); _hold(doc)
        owner = Owner(doc, ticket.binding.target_root/'local', App=App, Gui=Gui)
        owner.portable_context = context
        owner.native_project_context = context
        readback = {'status': 'OPENED', 'open_id': ticket.binding.open_id,
                    'reference': ticket.binding.reference, 'target_id': ticket.binding.target_id,
                    'working_document_id': owner.document_id, 'context_session': context.session_id,
                    'native_owner_session': owner.session_id, 'native_kind': 'pre'}
        if selection is not None:
            selected = select_bound_target(owner, selection, owner.portable_binding)
            readback.update(selection_status='SELECTED', selection=selected['selection'])
        readback['identity_initialization'] = deepcopy(getattr(owner, 'native_identity_initialization', []))
        verified = verify_opened(context, ticket.binding.open_id, _native_open_readback(readback))
        _LOCAL_HOSTS.append(owner)
        App.setActiveDocument(doc.Name)
        Gui.activeDocument().activeView().viewAxonometric(); Gui.activeDocument().activeView().fitAll()
        install_file_actions({'output': str(ticket.binding.target_root/'local')}, owner=owner)
        return owner, verified
    except Exception:
        from .assembly_pose_candidate import _release
        if owner is not None:
            owner.close()
        # The fresh-process entry refused existing user documents above. Only
        # documents created by this failed native open are cleaned up here.
        for name in list(App.listDocuments()):
            current_doc = App.getDocument(name)
            if current_doc is bootstrap:
                continue
            _release(current_doc)
            Gui.getDocument(name).Modified = False
            App.closeDocument(name)
        raise
    finally:
        from .assembly_pose_candidate import _release
        launcher.close(); _release(bootstrap)
        Gui.getDocument(bootstrap.Name).Modified = False
        App.closeDocument(bootstrap.Name)
