"""Immutable VTU/PVD snapshots; native readers retain the format's meaning."""
from pathlib import Path, PureWindowsPath
import hashlib
import json
import math
import os
import xml.etree.ElementTree as ET

from .evaluation import file_hash
from .storage import save_json, utc_now, canonical_hash


NATIVE_EXTENSIONS = {'.vtu', '.pvd', '.fcstd', '.caepre'}


def _identity(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _within_root(path, root):
    logical = Path(os.path.abspath(path))
    if not logical.is_relative_to(root):
        raise ValueError('Native dependency escapes the approved input root')
    resolved = logical.resolve(strict=True)
    if not logical.is_relative_to(root) or not resolved.is_relative_to(root):
        raise ValueError('Native dependency escapes the approved input root')
    if not resolved.is_file():
        raise ValueError('Native dependency must be a regular file')
    return logical


def _files(source, root):
    paths = [source]
    parsed_sha = None
    if source.suffix.lower() == '.pvd':
        if source.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('PVD collection metadata exceeds 8 MiB')
        with source.open('rb') as stream:
            payload = stream.read(8 * 1024 * 1024 + 1)
        if len(payload) > 8 * 1024 * 1024:
            raise ValueError('PVD collection metadata exceeds 8 MiB')
        text = payload.decode('utf-8-sig')
        if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
            raise ValueError('PVD declarations and entities are not supported')
        try:
            document = ET.fromstring(text)
        except ET.ParseError as exc:
            raise ValueError(f'Invalid PVD collection XML: {exc}') from exc
        if document.tag != 'VTKFile' or document.get('type') != 'Collection':
            raise ValueError('A VTK Collection PVD file is required')
        collection = document.find('Collection')
        datasets = [] if collection is None else collection.findall('DataSet')
        if not datasets:
            raise ValueError('PVD collection has no datasets')
        if len(datasets) > 1024:
            raise ValueError('PVD registration supports at most 1024 datasets')
        references = []
        for dataset in datasets:
            relative = dataset.get('file', '')
            if (not relative or '\\' in relative or ':' in relative or '\x00' in relative
                    or Path(relative).anchor or PureWindowsPath(relative).anchor):
                raise ValueError('PVD dependencies require relative file paths')
            if '..' in Path(relative).parts:
                raise ValueError('PVD datasets must be inside the collection folder')
            if Path(relative).suffix.lower() != '.vtu':
                raise ValueError('PVD registration currently supports VTU datasets only')
            try:
                time = float(dataset.attrib['timestep'])
            except (KeyError, ValueError) as exc:
                raise ValueError('Each PVD frame needs a finite numeric timestep') from exc
            if not math.isfinite(time):
                raise ValueError('Each PVD frame needs a finite numeric timestep')
            references.append(relative)
        for relative in references:
            dependency = _within_root(source.parent / relative, root)
            if dependency not in paths:
                paths.append(dependency)
        parsed_sha = hashlib.sha256(payload).hexdigest()
    return paths, parsed_sha


def _frozen_files(source, root, *, kind='freecad-fem-frozen'):
    if kind == 'freecad-shell-frozen':
        from .adapters.shell_deck import validate_snapshot
        manifest, _, _, _ = validate_snapshot(source)
        paths = [source] + [_within_root(source.parent / entry['relative'], root) for entry in manifest['files']]
        return paths, file_hash(source)
    if source.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('FEM snapshot manifest exceeds 8 MiB')
    with source.open('rb') as stream:
        payload = stream.read(8 * 1024 * 1024 + 1)
    if len(payload) > 8 * 1024 * 1024:
        raise ValueError('FEM snapshot manifest exceeds 8 MiB')
    manifest = json.loads(payload)
    if manifest.get('kind') != kind or manifest.get('schema_version') != '1':
        raise ValueError('A completed FreeCAD FEM snapshot is required')
    entries = manifest.get('files', [])
    names = [entry.get('relative') for entry in entries]
    inp = manifest.get('input_file', '')
    expected = {'editable.FCStd', 'mesh.json', inp}
    if manifest.get('editable_project') == 'editable.caepre':
        expected.add('editable.caepre')
    elif manifest.get('editable_project') is not None:
        raise ValueError('Unsupported editable native project member')
    if kind == 'freecad-contact-frozen':
        from .dynamic_restart import MEMBERS
        if set(names) & MEMBERS:
            # Only the existing admitted READ snapshot may carry restart files.
            # Validate both the source and the copied set via this same function.
            from .adapters.contact_fem import validate_snapshot
            _, model, _, _ = validate_snapshot(source)
            if not model.get('restart'):
                raise ValueError('Restart members require an admitted native READ snapshot')
            expected |= MEMBERS
    if (len(entries) != len(expected) or not isinstance(inp, str) or Path(inp).suffix.lower() != '.inp'
            or set(names) != expected):
        raise ValueError('FEM snapshot must retain its native CAD, mesh and unsplit input')
    paths = [source]
    for entry in entries:
        name = entry['relative']
        if not isinstance(name, str) or Path(name).name != name or any(char in name for char in '/\\:\x00'):
            raise ValueError('FEM snapshot dependencies require plain filenames')
        path = _within_root(source.parent / name, root)
        if path.stat().st_size != entry.get('bytes') or file_hash(path) != entry.get('sha256'):
            raise ValueError('FEM snapshot file changed or is incomplete')
        paths.append(path)
    return paths, hashlib.sha256(payload).hexdigest()


def _register_set(workbench_root, root, source, paths, parsed_sha, identifier, *, root_id, relative, limit, kind, format, native_metadata=None):
    if native_metadata is not None:
        if not isinstance(native_metadata, dict) or len(json.dumps(native_metadata, allow_nan=False).encode('utf-8')) > 64 * 1024:
            raise ValueError('Native metadata must be a bounded explicit object')
    before = {path: _identity(path.stat()) for path in paths}
    if any(identity[2] < 1 for identity in before.values()):
        raise ValueError('Native inputs and dependencies must not be empty')
    if sum(identity[2] for identity in before.values()) > limit:
        raise ValueError(f'Native input set exceeds {limit} bytes')
    folder = Path(workbench_root) / 'inputs' / identifier
    folder.mkdir(parents=True)
    files = []
    for path in paths:
        destination = folder / 'files' / path.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        total = 0
        with path.open('rb') as stream, destination.open('xb') as output:
            if _identity(os.fstat(stream.fileno())) != before[path]:
                raise ValueError('Source changed during native registration')
            while chunk := stream.read(min(1024 * 1024, before[path][2] - total + 1)):
                total += len(chunk)
                if total > before[path][2]:
                    raise ValueError('Source changed during native registration')
                digest.update(chunk)
                output.write(chunk)
            if total != before[path][2] or _identity(os.fstat(stream.fileno())) != before[path]:
                raise ValueError('Source changed during native registration')
        files.append({'relative': path.relative_to(root).as_posix(),
                      'file': destination.relative_to(workbench_root).as_posix(),
                      'bytes': total, 'sha256': digest.hexdigest()})
    if parsed_sha is not None and files[0]['sha256'] != parsed_sha:
        raise ValueError('Native manifest changed while its dependencies were registered')
    # Recheck the set together: an early frame may change while a later one copies.
    for path, entry in zip(paths, files):
        _within_root(path, root)
        if _identity(path.stat()) != before[path] or file_hash(path) != entry['sha256']:
            raise ValueError('Source changed during native registration')
    entry = files[0]
    if kind in {'frozen_fem', 'frozen_contact', 'frozen_shell', 'frozen_beam'}:
        # The copied bytes must match the manifest too, including a change before copying.
        _frozen_files(Path(workbench_root) / entry['file'], folder.resolve(),
                      kind={'frozen_beam':'freecad-beam-frozen', 'frozen_contact':'freecad-contact-frozen', 'frozen_shell':'freecad-shell-frozen',
                            'frozen_fem':'freecad-fem-frozen'}[kind])
    dynamic_origin = None
    if kind == 'native_result' and (native_metadata or {}).get('dynamic_locations') is not None:
        from .dynamic_locations import load
        dynamic_bundle = load(Path(workbench_root) / entry['file'], native_metadata)
        dynamic_origin = dynamic_bundle['origin']
        if str(root_id).startswith('job:') and dynamic_origin['job_id'] != root_id[4:]:
            from .dynamic_recovery_job import verify_registration_job
            verify_registration_job(workbench_root, root_id[4:], dynamic_bundle)
    if kind == 'native_result' and (native_metadata or {}).get('contact_inspection') is not None:
        from .contact_inspection import load
        load(Path(workbench_root) / entry['file'], native_metadata['contact_inspection'])
    if kind == 'native_result' and (native_metadata or {}).get('shell_inspection') is not None:
        from .shell_inspection import load
        load(Path(workbench_root) / entry['file'], native_metadata['shell_inspection'])
    if kind == 'native_result' and any(key in (native_metadata or {}) for key in ('beam', 'beam_inspection')):
        from .beam_inspection import validate_metadata
        validate_metadata(Path(workbench_root) / entry['file'], native_metadata)
    receipt = {'id': identifier, 'name': source.name, 'file': entry['file'],
               'bytes': entry['bytes'], 'sha256': entry['sha256'], 'created_utc': utc_now(),
               'kind': kind, 'format': format,
               'files': files, 'total_bytes': sum(item['bytes'] for item in files),
               'origin': {'mode': 'LOCAL_SNAPSHOT', 'root_id': root_id, 'relative': relative}}
    if dynamic_origin is not None:
        receipt['origin']['dynamic_locations'] = dynamic_origin
    if native_metadata is not None:
        receipt.update(native_metadata=native_metadata, native_metadata_sha256=canonical_hash(native_metadata))
    save_json(folder / 'input.json', receipt)
    return receipt


def register_native_input(workbench_root, approved_root, source, identifier, *, root_id, relative, limit, native_metadata=None):
    """Publish a receipt only after the entire referenced file set is copied."""
    root = Path(approved_root).resolve(strict=True)
    source = _within_root(source, root)
    if source.suffix.lower() in {'.fcstd', '.caepre'}:
        from .native_cad import dependency_files, inspect_project
        if native_metadata is not None:
            raise ValueError('Native design metadata is extracted from its registered file set')
        if source.suffix.lower() == '.caepre':
            inspect_project(source, limit=limit)
            paths = [source]
        else:
            paths = dependency_files(source, root)
        return _register_set(workbench_root, root, source, paths, None, identifier,
            root_id=root_id, relative=relative, limit=limit, kind='native_design', format=source.suffix.lower()[1:],
            native_metadata={'kind': 'native_design_dependencies',
                'original_locations': {path.relative_to(root).as_posix(): str(path) for path in paths}})
    paths, parsed_sha = _files(source, root)
    from .dynamic_locations import required, load
    if required(source, native_metadata):
        bundle = load(source, native_metadata)
        paths = list(dict.fromkeys([*paths, *[_within_root(path, root) for path in bundle['paths']]]))
    if (any(key in (native_metadata or {}) for key in ('beam', 'beam_inspection')) or
            source.name == 'beam.pvd' and (source.parent/'beam_inspection.json').exists()):
        from .beam_inspection import validate_metadata
        bundle = validate_metadata(source, native_metadata)
        paths = list(dict.fromkeys([*paths, *[_within_root(path, root) for path in bundle['paths']]]))
    if (native_metadata or {}).get('shell_inspection') is not None:
        from .shell_inspection import load
        bundle = load(source, native_metadata['shell_inspection'])
        if bundle['manifest']['native_metadata'] != {k:v for k,v in native_metadata.items() if k != 'shell_inspection'}:
            raise ValueError('Shell field declarations differ from their native pinned bundle')
        paths = list(dict.fromkeys([*paths, *[_within_root(path, root) for path in bundle['paths']]]))
    if (native_metadata or {}).get('contact_inspection') is not None:
        from .contact_inspection import load
        bundle = load(source, native_metadata['contact_inspection'])
        if bundle['manifest']['native_metadata'] != {k: v for k, v in native_metadata.items() if k != 'contact_inspection'}:
            raise ValueError('Contact field declarations differ from the pinned bundle')
        paths = list(dict.fromkeys([*paths, *[_within_root(path, root) for path in bundle['paths']]]))
    return _register_set(workbench_root, root, source, paths, parsed_sha, identifier,
                         root_id=root_id, relative=relative, limit=limit,
                         kind='native_result', format=source.suffix.lower()[1:], native_metadata=native_metadata)


def register_frozen_input(workbench_root, approved_root, source, identifier, *, root_id, relative, limit):
    root = Path(approved_root).resolve(strict=True)
    source = _within_root(source, root)
    if source.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('FEM snapshot manifest exceeds 8 MiB')
    with source.open('rb') as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('FEM snapshot manifest exceeds 8 MiB')
    kind = json.loads(raw).get('kind')
    if kind not in {'freecad-fem-frozen', 'freecad-contact-frozen', 'freecad-shell-frozen', 'freecad-beam-frozen'}:
        raise ValueError('Select an admitted native frozen snapshot kind')
    paths, parsed_sha = _frozen_files(source, root, kind=kind)
    receipt_kind, format_name = {'freecad-fem-frozen':('frozen_fem','freecad-fem'),
        'freecad-contact-frozen':('frozen_contact','freecad-contact'),
        'freecad-shell-frozen':('frozen_shell','freecad-shell'),
        'freecad-beam-frozen':('frozen_beam','freecad-beam')}[kind]
    return _register_set(workbench_root, root, source, paths, parsed_sha, identifier,
                         root_id=root_id, relative=relative, limit=limit,
                         kind=receipt_kind, format=format_name)
