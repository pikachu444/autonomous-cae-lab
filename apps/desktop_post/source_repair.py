"""Explicit relocation of identical registered native result bytes."""
from copy import deepcopy
import json
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET

from paraview import simple as p
try:
    from . import external
except ImportError:
    import external


def content_set(record):
    entry = Path(record['entry_path'])
    return {Path(pin['path']).relative_to(entry.parent).as_posix(): (pin['bytes'], pin['sha256'])
            for pin in record['source_pins']}


def source_issues(document):
    issues = []
    for ref, record in document.get('sources', {}).items():
        try:
            external.verify_sources(None, {'sources': {ref: record}})
        except (OSError, ValueError, RuntimeError) as error:
            issues.append({'source_ref': ref, 'input_id': record.get('input_id'),
                           'reader_name': record['reader_name'], 'message': str(error)})
    return issues


def verify_analysis_files(document):
    for obj in document.get('analysis', {}).get('objects', {}).values():
        for revision in obj.get('history', []):
            for record in revision.get('result_files', []):
                file = Path(record['path'])
                if not file.is_file() or file.stat().st_size != record['bytes'] or external.sha(file) != record['sha256']:
                    raise ValueError('Retained analysis values/mask file is missing or changed: ' + str(file))


def partial_state(state, document, issues, output):
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
    if contact and contact.get('source_ref') in {row['source_ref'] for row in issues}:
        bad.update(registrations[name] for name in contact.get('overlay_names', []) if name in registrations)
    proxies = {item.get('id'): item for item in server.findall('Proxy')}
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
            container = group in containers and ('Cue' not in kind and 'Track' not in kind)
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
            'removed_source_names': sorted(name for name, identifier in registrations.items() if identifier in bad),
            'healthy_source_names': sorted(
        name for name, identifier in registrations.items() if identifier not in bad)}


def _rewrite_reader_paths(state, sources, native_readers=()):
    """Change only admitted source reader FileName entries, not arbitrary XML text."""
    tree = ET.parse(state)
    root = tree.getroot()
    server = root.find('ServerManagerState') if root.tag != 'ServerManagerState' else root
    if server is None:
        raise ValueError('Saved ParaView state has no ServerManagerState')
    collection = server.find("ProxyCollection[@name='sources']")
    registrations = {} if collection is None else {item.get('name'): item.get('id') for item in collection.findall('Item')}
    for record in sources.values():
        identifier = registrations.get(record['reader_name'])
        proxy = server.find("Proxy[@id='%s']" % identifier) if identifier else None
        if proxy is None or proxy.get('type') != record['reader_type']:
            raise ValueError('Saved reader name/type does not match the admitted result')
        prop = proxy.find("Property[@name='FileName']")
        if prop is None:
            raise ValueError('Saved native reader has no supported FileName property')
        elements = prop.findall('Element')
        if len(elements) != 1:
            raise ValueError('This relocation supports one VTU or one PVD entry per reader')
        elements[0].set('value', record['entry_path'])
        # Domain/FileList may contain informational old paths. Only actual file
        # properties are modified; the reader rebuilds domains from admitted input.
    source_names = {row['reader_name'] for row in sources.values()}
    for record in native_readers:
        if record['reader_name'] in source_names:
            continue
        identifier = registrations.get(record['reader_name'])
        proxy = server.find("Proxy[@id='%s']" % identifier) if identifier else None
        if proxy is None or proxy.get('type') != record['reader_type']:
            raise ValueError('Saved auxiliary reader identity changed')
        prop = proxy.find("Property[@name='FileName']")
        elements = [] if prop is None else prop.findall('Element')
        if len(elements) != len(record['input_paths']):
            raise ValueError('Saved auxiliary reader file count changed')
        for element, path in zip(elements, record['input_paths']):
            element.set('value', path)
    return tree


def repair_source(owner, source_ref, input_id, receipt):
    document = owner.project_document
    old = document.get('sources', {}).get(source_ref)
    if old is None:
        raise ValueError('Choose the exact missing source in this analysis')
    if receipt.get('id') != input_id or receipt.get('format') not in ('vtu', 'pvd'):
        raise ValueError('Choose a verified registered VTU/PVD result set')
    replacement = dict(old, entry_path=receipt['path'], source_pins=deepcopy(receipt['source_pins']))
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
    proposed = deepcopy(document)
    proposed['sources'][source_ref] = replacement
    proposed['native_reader_files'] = {native_paths.get(path, path): value for path, value in proposed.get('native_reader_files', {}).items()}
    for reader in proposed.get('native_readers', []):
        reader['input_paths'] = [native_paths.get(path, path) for path in reader['input_paths']]
    remaining = source_issues(proposed)
    if previous_source is not None:
        _, pending = owner.native_properties(previous_source)
        if pending:
            raise ValueError('BUSY_EDIT: Apply/Reset this reader\'s native pending properties before location repair')
        original = previous_source.FileName
        statuses = {key: getattr(previous_source, key) for key in ('PointArrayStatus', 'CellArrayStatus', 'PointArrays', 'CellArrays', 'FieldArrays')
                    if key in previous_source.ListProperties()}
        overlay_changes = []
        contact = document.get('analysis', {}).get('contact_selection') or {}
        if contact.get('source_ref') == source_ref:
            for name in contact.get('overlay_names', []):
                proxy = p.FindSource(name)
                if proxy is None or proxy.GetXMLName() != 'XMLUnstructuredGridReader':
                    continue
                _, pending_overlay = owner.native_properties(proxy)
                if pending_overlay:
                    raise ValueError('BUSY_EDIT: Apply/Reset pending contact surface reader properties first')
                original_paths = list(proxy.FileName)
                replacement_files = [native_paths.get(path, path) for path in original_paths]
                if replacement_files != original_paths:
                    overlay_changes.append((proxy, original_paths, replacement_files))
        try:
            for proxy, _, replacement_files in overlay_changes:
                proxy.FileName = replacement_files
                proxy.UpdatePipeline()
            previous_source.FileName = [replacement['entry_path']] if receipt['format'] == 'vtu' else replacement['entry_path']
            previous_source.UpdatePipeline()
            for key, value in statuses.items():
                setattr(previous_source, key, value)
            external.verify_readers({'sources': {source_ref: replacement}})
        except BaseException:
            for proxy, original_paths, _ in overlay_changes:
                proxy.FileName = original_paths
                proxy.UpdatePipeline()
            previous_source.FileName = original
            for key, value in statuses.items():
                setattr(previous_source, key, value)
            raise
        document.clear()
        document.update(proposed)
        document['repair'] = remaining
        return {'source_ref': source_ref, 'input_id': input_id, 'content_changed': False, 'remaining': remaining}
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
