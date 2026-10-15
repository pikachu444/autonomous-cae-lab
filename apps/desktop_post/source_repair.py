"""Explicit relocation of identical registered native result bytes."""
from copy import deepcopy
import json
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET

from paraview import simple as p
try:
    from . import external
    from .source_change import content_set
except ImportError:
    import external
    from source_change import content_set


def preview_registered(receipt):
    """Read in a separate native process; never modify the existing owner."""
    source, record = external.admit_result(receipt['path'], receipt['id'], receipt['source_pins'],
        receipt.get('native_metadata'), receipt.get('registration_origin'))
    try: return deepcopy(record['metadata'])
    finally: p.Delete(source)


def source_issues(document):
    issues = []
    for ref, record in document.get('sources', {}).items():
        try:
            external.verify_sources(None, {'sources': {ref: record}})
        except (OSError, ValueError, RuntimeError) as error:
            issues.append({'source_ref': ref, 'input_id': record.get('input_id'),
                           'reader_name': record['reader_name'], 'message': str(error),
                           'code': 'MISSING_DEPENDENCY' if any(not Path(pin['path']).is_file()
                               for pin in record.get('source_pins', [])) else 'CONTENT_CHANGED'})
    return issues


def verify_analysis_files(document, *, allow_missing=False, project_path=None):
    issues = []
    from caelab.native_post_dependencies import history_asset_mapping
    assets, proof = history_asset_mapping(document, project_path) if project_path is not None else ({}, None)
    for obj in document.get('analysis', {}).get('objects', {}).values():
        for revision in obj.get('history', []):
            preserved = proof is not None and any(row['history']['object_ref'] == obj['id']
                and row['history']['revision_id'] == revision['id'] and row['state'] == 'UNAVAILABLE_DECLARED'
                for row in document.get('native_history_availability', {}).get('histories', []))
            for record in revision.get('result_files', []):
                mapped = assets.get(record['path']) if preserved else record['path']
                file = Path(mapped) if mapped is not None else None
                if (file is None or not file.is_file()) and allow_missing:
                    issues.append({'code': 'MISSING_HISTORY_DEPENDENCY', 'object_ref': obj['id'],
                        'revision': revision['id'], 'reader_name': revision.get('retained_source_name', revision.get('source_name', '')),
                        'message': '보존한 분석 파일을 찾을 수 없습니다: ' + str(file)})
                    continue
                if file is None or not file.is_file() or file.stat().st_size != record['bytes'] or external.sha(file) != record['sha256']:
                    raise ValueError('Retained analysis values/mask file is missing or changed: ' + str(file))
    return issues


def _unavailable_curve_names(document, issues):
    """Materialized curve readers have semantic, not native Input links.

    Follow each saved revision's exact bindings/dependencies. The current editor
    cursor and display name are never substitutes for the frozen input revision.
    """
    import hashlib
    missing = {row.get('source_ref') for row in issues if row.get('source_ref')}
    originals = document.get('sources', {})
    objects = document.get('analysis', {}).get('objects', {})
    memo = {}
    def affected(record, seen):
        identifier = record['id']
        if identifier in memo:
            return memo[identifier]
        if identifier in seen:
            return True  # Invalid lineage may only open as verified retained data.
        for ref, binding in record.get('bindings', {}).items():
            if ref in missing:
                memo[identifier] = True
                return True
            if ref in originals:
                continue
            expected = binding.get('revision')
            candidates = []
            for candidate in objects.get(ref, {}).get('history', []):
                frozen = {k: candidate[k] for k in ('id', 'recipe', 'graph', 'bindings')}
                digest = hashlib.sha256(json.dumps(frozen, sort_keys=True, separators=(',', ':'),
                    ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()
                pinned = record.get('dependencies', {}).get(ref)
                if digest == expected and (pinned is None or candidate['id'] == pinned):
                    candidates.append(candidate)
            if len(candidates) != 1 or affected(candidates[0], seen | {identifier}):
                memo[identifier] = True
                return True
        memo[identifier] = False
        return False
    names = set()
    for obj in objects.values():
        for record in obj.get('history', []):
            if (record.get('summary', {}).get('comparison_version') == 3
                    and affected(record, set())):
                names.update([record['source_name'], *record.get('proxy_names', [])])
    return names


def partial_state(state, document, issues, output, *, retain_applied=False):
    """Remove only unavailable reader branches from a copy of native PVSM.

    Native views/layouts and healthy sources survive. Affected saved analysis
    values are opened separately as retained readers; no filter is reexecuted
    against a guessed replacement input.
    """
    tree = ET.parse(state)
    root = tree.getroot()
    server = root if root.tag == 'ServerManagerState' else root.find('ServerManagerState')
    if server is None:
        raise ValueError('Saved ParaView state has no ServerManagerState')
    collection = server.find("ProxyCollection[@name='sources']")
    registrations = {} if collection is None else {item.get('name'): item.get('id') for item in collection.findall('Item')}
    bad = {registrations[row['reader_name']] for row in issues if row['reader_name'] in registrations}
    contact = document.get('analysis', {}).get('contact_selection') or {}
    if contact and contact.get('source_ref') in {row.get('source_ref') for row in issues}:
        bad.update(registrations[name] for name in contact.get('overlay_names', []) if name in registrations)
    semantic_names = _unavailable_curve_names(document, issues)
    bad.update(registrations[name] for name in semantic_names if name in registrations)
    proxies = {item.get('id'): item for item in server.findall('Proxy')}
    retained = set()
    if retain_applied:
        # A saved field comparison is data on reopen. Keep its XML identity so
        # existing representations, camera/layout and active selection survive.
        for obj in document.get('analysis', {}).get('objects', {}).values():
            for record in obj.get('history', []):
                entry = record.get('result_file')
                kind = {'.vtu': 'XMLUnstructuredGridReader', '.vtp': 'XMLPolyDataReader'}.get(
                    Path(entry).suffix.lower()) if entry else None
                if (record.get('summary', {}).get('comparison_version') != 2 or not kind
                        or record.get('retained_source_name')):
                    continue
                identifier = registrations.get(record['source_name'])
                if identifier not in proxies:
                    continue  # Existing missing-branch fallback opens the pinned result.
                if not any(Path(pin['path']).resolve() == Path(entry).resolve()
                           for pin in record.get('result_files', [])):
                    raise ValueError('Saved comparison entry has no exact retained pin')
                verify_analysis_files({'analysis': {'objects': {'saved': {'history': [record]}}}})
                proxy = proxies[identifier]
                proxy.clear(); proxy.attrib.update(group='sources', type=kind, id=identifier,
                                                   servers='1')
                prop = ET.SubElement(proxy, 'Property', name='FileName', id=identifier + '.FileName',
                                     number_of_elements='1')
                ET.SubElement(prop, 'Element', index='0', value=str(Path(entry).resolve()))
                retained.add(identifier)
                bad.update(registrations[name] for name in record.get('proxy_names', [])
                           if name in registrations and registrations[name] != identifier)
        bad.difference_update(retained)
    containers = {'views', 'layouts', 'timekeeper', 'animation'}
    changed = True
    while changed:
        changed = False
        for identifier, proxy in proxies.items():
            if identifier in bad:
                continue
            references = {item.get('value') for item in proxy.findall('./Property/Proxy')}
            # Views/layout and the animation scene contain healthy siblings.
            # Individual cues/representations depend on their exact input.
            group, kind = proxy.get('group', ''), proxy.get('type', '')
            # TimeKeeper is registered in the timekeeper collection but its
            # proxy XML group is misc. Keep this global container and prune only
            # its missing source entries, just as for views and animation.
            container = (group in containers or kind == 'TimeKeeper') and ('Cue' not in kind and 'Track' not in kind)
            if not container and references & bad:
                bad.add(identifier)
                changed = True
    for proxy in list(server.findall('Proxy')):
        if proxy.get('id') in bad:
            server.remove(proxy)
    for collection in server.findall('ProxyCollection'):
        for item in list(collection):
            if item.get('id') in bad:
                collection.remove(item)
    for prop in server.iter('Property'):
        removed = False
        for item in list(prop):
            if item.tag == 'Proxy' and item.get('value') in bad:
                prop.remove(item)
                removed = True
        if removed:
            values = prop.findall('Proxy')
            prop.set('number_of_elements', str(len(values)))
            for index, item in enumerate(values):
                if 'index' in item.attrib:
                    item.set('index', str(index))
        for domain in prop.findall('Domain'):
            for item in list(domain):
                if item.tag == 'Proxy' and (item.get('value') or item.get('id')) in bad:
                    domain.remove(item)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output, encoding='utf-8', xml_declaration=True)
    return {'removed_proxy_ids': sorted(bad),
            'retained_source_names': sorted(name for name, identifier in registrations.items() if identifier in retained),
            'removed_source_names': sorted(name for name, identifier in registrations.items() if identifier in bad),
            'healthy_source_names': sorted(
        name for name, identifier in registrations.items() if identifier not in bad)}


def _rewrite_reader_paths(state, sources, native_readers=(), *, reader_bindings=None, member_paths=None):
    """Use the same pure exact-slot codec as registration and portable derivation."""
    from caelab.native_post_dependencies import rewrite_pvsm_paths
    return rewrite_pvsm_paths(state, sources, native_readers,
        reader_bindings=reader_bindings, member_paths=member_paths)


def repair_source(owner, source_ref, input_id, receipt):
    document = owner.project_document
    old = document.get('sources', {}).get(source_ref)
    if old is None:
        raise ValueError('Choose the exact missing source in this analysis')
    if receipt.get('id') != input_id or receipt.get('format') not in ('vtu', 'pvd', 'vtt'):
        raise ValueError('Choose a verified registered VTU/PVD result set')
    replacement = dict(old, entry_path=receipt['path'], source_pins=deepcopy(receipt['source_pins']))
    if old.get('native_metadata') != receipt.get('native_metadata'):
        raise ValueError('CONTENT_CHANGED: replacement field declarations differ; add a new result instead')
    if Path(old['entry_path']).suffix.lower() != '.' + receipt['format'] or content_set(old) != content_set(replacement):
        raise ValueError('CONTENT_CHANGED: replacement bytes/dependency names differ; add them as a new result instead')
    external.verify_sources(None, {'sources': {source_ref: replacement}})
    replacement['input_id'] = input_id
    replacement['relocations'] = [*old.get('relocations', []),
                                  {'input_id': old.get('input_id'), 'entry_path': old['entry_path']}]
    previous_source = p.FindSource(old['reader_name'])
    native_paths = {}
    replacement_paths={Path(row['path']).relative_to(Path(replacement['entry_path']).parent).as_posix():row['path']
                       for row in replacement['source_pins']}
    for prior in old['source_pins']:
        relative=Path(prior['path']).relative_to(Path(old['entry_path']).parent).as_posix()
        native_paths[prior['path']]=replacement_paths[relative]
    if 'input_paths' in replacement:
        replacement['input_paths'] = [native_paths.get(path, path) for path in replacement['input_paths']]
    proposed = deepcopy(document)
    proposed['sources'][source_ref] = replacement
    proposed['native_reader_files'] = {native_paths.get(path, path): value for path, value in proposed.get('native_reader_files', {}).items()}
    for reader in proposed.get('native_readers', []):
        reader['input_paths'] = [native_paths.get(path, path) for path in reader['input_paths']]
    remaining = source_issues(proposed)
    if previous_source is not None:
        from caelab.native_post_dependencies import READERS
        workspace = getattr(owner, 'workspace', None)
        old_state = workspace.state if workspace is not None else None
        if workspace is not None:
            proposed['analysis'] = deepcopy(workspace.state)
        unavailable = {(row['history']['object_ref'], row['history']['revision_id'])
            for row in proposed.get('native_history_availability', {}).get('histories', [])
            if row['state'] == 'UNAVAILABLE_DECLARED'}
        for obj in proposed.get('analysis', {}).get('objects', {}).values():
            for record in obj.get('history', []):
                if (obj['id'], record['id']) in unavailable:
                    continue
                if record.get('result_file'):
                    record['result_file'] = native_paths.get(record['result_file'], record['result_file'])
                for pin in record.get('result_files', []):
                    pin['path'] = native_paths.get(pin['path'], pin['path'])
                retained = record.get('retained_reader')
                if retained:
                    retained['input_paths'] = [native_paths.get(path, path) for path in retained['input_paths']]
                    for pin in retained['files']:
                        pin['path'] = native_paths.get(pin['path'], pin['path'])
        # Every exact occurrence that consumes the selected source's pinned files
        # participates in one transaction, including auxiliary/retained readers.
        changes = []
        for (name, _), proxy in p.GetSources().items():
            inputs = list(map(str, external.reader_input_files(proxy)))
            projected = [native_paths.get(path, path) for path in inputs]
            if projected == inputs:
                continue
            if proxy.GetXMLName() not in READERS:
                raise ValueError('READER_NOT_VERIFIED: an affected reader type is unsupported: ' + name)
            declared = [row for row in document.get('native_readers', []) if row['reader_name'] == name]
            if declared and (len(declared) != 1 or declared[0]['reader_type'] != proxy.GetXMLName()
                             or declared[0]['input_paths'] != inputs):
                raise ValueError('READER_CHANGED: affected reader type/ordered slots differ: ' + name)
            if not declared and proxy is not previous_source and any(path not in native_paths for path in inputs):
                raise ValueError('HISTORY_DEPENDENCY_UNBOUND: affected reader has an unpinned additional slot')
            props, pending = owner.native_properties(proxy)
            if pending:
                raise ValueError('BUSY_EDIT: Apply/Reset every affected reader before location repair')
            statuses = {key: deepcopy(props[key]) for key in ('PointArrayStatus', 'CellArrayStatus', 'PointArrays', 'CellArrays', 'FieldArrays') if key in props}
            scalar = not isinstance(props.get('FileName', inputs), list)
            changes.append({'name': name, 'proxy': proxy, 'old': inputs, 'new': projected,
                            'scalar': scalar, 'statuses': statuses})
        if not any(row['proxy'] is previous_source for row in changes):
            raise ValueError('READER_CHANGED: the selected source no longer consumes its saved entry')
        impact_names = {row['name'] for row in changes}
        impacted = set(); refs = {source_ref}
        changed = True
        while changed:
            changed = False
            for ref, obj in proposed.get('analysis', {}).get('objects', {}).items():
                for record in obj.get('history', []):
                    recipe = record['recipe']
                    dependencies = ([recipe['a']['source_ref'], recipe['b']['source_ref']]
                        if obj['kind'] == 'comparison' else [recipe['source_ref']])
                    labels = {node['label'] for site in ('graph', 'retained_graph') for node in (record.get(site) or {}).get('nodes', [])}
                    if set(dependencies) & refs or labels & impact_names:
                        impacted.add((ref, record['id']))
                        if ref not in refs: refs.add(ref); changed = True
        basis_module = None; old_basis = None
        if getattr(owner, 'portable_binding', None) is not None:
            from apps.desktop_post import portable_project as basis_module
            old_basis = basis_module._open_basis[owner.portable_binding.open_id]
            new_paths = {identifier: Path(native_paths.get(str(path), str(path)))
                         for identifier, path in old_basis['member_paths'].items()}
        def assign(row, values):
            row['proxy'].FileName = values[0] if row['scalar'] else list(values)
            for key, value in row['statuses'].items(): setattr(row['proxy'], key, deepcopy(value))
            row['proxy'].UpdatePipeline()
        original_document = deepcopy(document)
        try:
            for row in changes: assign(row, row['new'])
            if basis_module is not None:
                basis_module._open_basis[owner.portable_binding.open_id] = {**old_basis, 'member_paths': new_paths}
            if workspace is not None:
                workspace.document, workspace.state = proposed, proposed['analysis']
            expected_readers = [row for row in proposed.get('native_readers', []) if row['reader_name'] in impact_names]
            external.verify_readers({'sources': {source_ref: replacement}, 'native_readers': expected_readers})
            external._verify_metadata_records({'sources': {source_ref: replacement}}, live=True)
            if workspace is not None:
                for ref, revision_id in impacted:
                    if (ref, revision_id) in unavailable:
                        continue
                    obj = workspace.object(ref)
                    record = next(item for item in obj['history'] if item['id'] == revision_id)
                    bundle = workspace.bundles.get(revision_id)
                    if bundle is None:
                        raise ValueError('SOURCE_UNAVAILABLE: an affected retained history has no verified bundle')
                    workspace._verify_record(obj, record, bundle)
            document.clear(); document.update(proposed); document['repair'] = remaining
            if workspace is not None:
                workspace.document, workspace.state = document, document['analysis']
            return {'source_ref': source_ref, 'input_id': input_id, 'content_changed': False,
                    'remaining': remaining, 'affected_readers': sorted(impact_names),
                    'affected_histories': [list(row) for row in sorted(impacted)], 'retained_branches_recomputed': False}
        except BaseException:
            rollback_errors = []
            for row in reversed(changes):
                try: assign(row, row['old'])
                except BaseException as error: rollback_errors.append(str(error))
            if basis_module is not None:
                basis_module._open_basis[owner.portable_binding.open_id] = old_basis
            document.clear(); document.update(original_document)
            if workspace is not None:
                document['analysis'] = old_state
                workspace.document, workspace.state = document, old_state
            if rollback_errors:
                raise RuntimeError('REPAIR_ROLLBACK_FAILED: current native readers need explicit recovery: ' + '; '.join(rollback_errors))
            raise
    if document.get('partial_workspace'):
        # Restore this admitted reader beside the healthy live graph. Retained
        # dependent results stay read-only until the user explicitly validates
        # and applies their recipe; opening a file does not recompute them.
        source, admitted = external.admit_result(replacement['entry_path'], input_id,
            replacement['source_pins'], replacement.get('native_metadata'))
        try:
            p.RenameSource(old['reader_name'], source)
            replacement['metadata'] = admitted.get('metadata', replacement.get('metadata', {}))
            proposed['sources'][source_ref] = replacement
            external.verify_readers({'sources': {source_ref: replacement}})
        except BaseException:
            p.Delete(source)
            raise
        document.clear()
        document.update(proposed)
        document['repair'] = remaining
        return {'source_ref': source_ref, 'input_id': input_id, 'content_changed': False,
                'remaining': remaining, 'workspace_loaded': True, 'retained_branches_recomputed': False}
    # Legacy repair-only sessions may still be empty. Keep collecting exact
    # locations before loading their preserved original state.
    if remaining:
        document.clear()
        document.update(proposed)
        document['repair'] = remaining
        return {'source_ref': source_ref, 'input_id': input_id, 'content_changed': False, 'remaining': remaining, 'workspace_loaded': False}
    state = owner.project_path.parent / document['workspace_file']
    if external.sha(state) != document['workspace_sha256']:
        raise ValueError('Saved native state changed; source repair cannot replace it')
    verify_analysis_files(proposed)
    tree = _rewrite_reader_paths(state, proposed['sources'], proposed.get('native_readers', []))
    folder = Path(document['project_root']) / 'repairs' / ('R' + uuid.uuid4().hex)
    folder.mkdir(parents=True, exist_ok=False)
    output = folder / 'analysis.pvsm'
    tree.write(output, encoding='utf-8', xml_declaration=True)
    p.LoadState(str(output))
    external.verify_sources(None, proposed)
    external.verify_readers(proposed)
    external.restore_selection(proposed)
    proposed.update(workspace_file=str(output), workspace_sha256=external.sha(output), repair=[])
    document.clear()
    document.update(proposed)
    try:
        from .workspace import Workspace
    except ImportError:
        from workspace import Workspace
    owner.workspace = Workspace(owner, document)
    owner.workspace.restore_selection()
    return {'source_ref': source_ref, 'input_id': input_id, 'content_changed': False, 'remaining': [], 'workspace_loaded': True}


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    receipt = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    result = preview_registered(receipt)
    Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding='utf-8')
