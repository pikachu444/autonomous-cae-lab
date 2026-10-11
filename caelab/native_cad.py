"""FCStd dependency packaging, not a CAD parser or substitute geometry engine.

Only the native XLink file attribute is relocated. See FreeCAD 1.1.4
src/App/PropertyLinks.cpp PropertyXLink::Save and src/App/Document.cpp saveCopy.
All other ZIP members, native feature data and subelement names are preserved.
"""
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from .storage import canonical_hash, _publish_json

KIND = 'caelab-editable-pre'
MAX_XML = 64 * 1024 * 1024
MAX_FILES = 1024


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _xml(archive):
    entry = archive.getinfo('Document.xml')
    if entry.file_size > MAX_XML:
        raise ValueError('Native document metadata exceeds 64 MiB')
    payload = archive.read(entry)
    if b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():
        raise ValueError('Native document XML entities are not supported')
    return ET.fromstring(payload)


def xlinks(path):
    with zipfile.ZipFile(path) as archive:
        document = _xml(archive)
    result = []
    for obj in document.findall('.//Object'):
        for prop in obj.findall('./Properties/Property'):
            for index, link in enumerate(prop.findall('.//XLink')):
                result.append({'object_id': obj.get('name'), 'property': prop.get('name'), 'index': index,
                    'file': link.get('file', ''), 'target_name': link.get('name', '')})
    return result


def logical_file(parent, value):
    if not isinstance(value, str) or '\x00' in value or '://' in value:
        raise ValueError('Native XLink needs a local file reference')
    # A Windows file is resolved only by Windows, not misread as a relative
    # filename when a archive is inspected on another OS.
    if PureWindowsPath(value).drive and os.name != 'nt':
        raise ValueError('An absolute Windows native dependency must first be packaged on Windows')
    return Path(os.path.abspath(Path(parent) / value)).resolve()


def dependency_files(source, approved_root):
    root, source = Path(approved_root).resolve(), Path(source).resolve(strict=True)
    pending, paths = [source], []
    while pending:
        path = pending.pop(0)
        if path in paths:
            continue
        if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() != '.fcstd':
            raise ValueError('Native Link dependency is missing or outside the approved CAD root')
        paths.append(path)
        if len(paths) > MAX_FILES:
            raise ValueError('Native dependency set exceeds 1024 documents')
        for link in xlinks(path):
            if link['file']:
                pending.append(logical_file(path.parent, link['file']))
    return paths


def relocate(source, destination, resolve):
    """Native saveCopy -> relocated copy; resolver receives exact link context.

    No native geometry/constraint datum or source archive is modified. Failure
    leaves the source and the prepared output available for diagnosis.
    """
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as original:
        document = _xml(original)
        for obj in document.findall('.//Object'):
            for prop in obj.findall('./Properties/Property'):
                for index, link in enumerate(prop.findall('.//XLink')):
                    context = {'object_id': obj.get('name'), 'property': prop.get('name'), 'index': index,
                               'file': link.get('file', ''), 'target_name': link.get('name', '')}
                    new = resolve(context)
                    if new is not None:
                        link.set('file', new)
        payload = ET.tostring(document, encoding='utf-8', xml_declaration=True)
        with zipfile.ZipFile(destination, 'x') as output:
            for info in original.infolist():
                if info.filename == 'Document.xml':
                    output.writestr(info, payload)
                else:
                    with original.open(info) as incoming, output.open(info, 'w') as outgoing:
                        shutil.copyfileobj(incoming, outgoing, 1024 * 1024)


def _safe_member(value):
    if (not isinstance(value, str) or not value or '\\' in value or ':' in value or '\x00' in value
            or PurePosixPath(value).is_absolute() or '..' in PurePosixPath(value).parts):
        raise ValueError('Invalid native project member path')
    return value


def inspect_project(path, *, limit=2 * 1024 ** 3):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > MAX_FILES + 4:
            raise ValueError('Duplicate or excessive native project entries')
        for name in names:
            _safe_member(name)
        if sum(info.file_size for info in archive.infolist()) > limit:
            raise ValueError('Native project expanded files exceed the configured input limit')
        info = archive.getinfo('project.json')
        if info.file_size > 8 * 1024 * 1024:
            raise ValueError('Native project manifest exceeds 8 MiB')
        manifest = json.loads(archive.read(info).decode('utf-8'))
        if manifest.get('kind') != KIND or manifest.get('schema_version') != 1:
            raise ValueError('Unsupported native Pre project')
        files = manifest.get('documents', [])
        if not files or len(files) > MAX_FILES:
            raise ValueError('The native project must contain editable documents')
        expected = {_safe_member(row['file']) for row in files}
        if set(names) != expected | {'project.json'} or manifest['entry'] not in expected:
            raise ValueError('Native project members differ from its manifest')
        for row in files:
            info = archive.getinfo(row['file'])
            if info.file_size != row['bytes'] or not row['file'].lower().endswith('.fcstd'):
                raise ValueError('Native project file size/type differs from the manifest')
            with archive.open(info) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != row['sha256']:
                    raise ValueError('Native project member hash changed')
        # Validate every stored Link path remains in this bundle. Missing links
        # are explicit draft issues, never automatically resolved on the host.
        missing = {row['replacement'] for row in manifest.get('unavailable_dependencies', [])}
        for row in files:
            with archive.open(row['file']) as stream, zipfile.ZipFile(stream) as native:
                tree = _xml(native)
            for link in tree.findall('.//XLink'):
                value = link.get('file', '')
                if value:
                    ref = str(PurePosixPath(row['file']).parent / value)
                    _safe_member(ref)
                    if ref not in expected and ref not in missing:
                        raise ValueError('Native project contains an unregistered external Link')
    return manifest


def publish_project(path, manifest, files):
    path = Path(path)
    if path.suffix.lower() != '.caepre':
        raise ValueError('Choose a .caepre editable Lab project file')
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.caelab-pre-', suffix='.caepre', dir=path.parent, delete=False) as temp:
        temporary = Path(temp.name)
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('project.json', json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False))
        for row in manifest['documents']:
            archive.write(files[row['file']], row['file'])
    inspect_project(temporary)
    with temporary.open('rb') as stream:
        os.fsync(stream.fileno())
    # Same exact prepared bytes are retried on Windows. Never rerun saveCopy,
    # change geometry or submit a solver after a publication conflict.
    _publish_json(temporary, path)
    return {'path': str(path), 'sha256': sha(path), 'revision': manifest['revision']}


def unpack_project(source, folder):
    source, folder = Path(source), Path(folder)
    before = sha(source)
    manifest = inspect_project(source)
    folder.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(source) as archive:
        for row in manifest['documents']:
            target = folder / row['file']
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(row['file']) as incoming, target.open('xb') as output:
                shutil.copyfileobj(incoming, output, 1024 * 1024)
            if sha(target) != row['sha256']:
                raise ValueError('Native working copy differs from the saved document')
    if sha(source) != before:
        raise ValueError('Project changed while creating its editable working copy')
    return manifest, folder / manifest['entry']


def working_copy(source, folder, *, approved_root=None, registered=None, original_locations=None):
    """Copy an FCStd graph and relocate known Links to the copied files.

    Direct native file-dialog use supplies its explicitly chosen containing
    root; service use supplies already registered and verified dependencies.
    """
    source, folder = Path(source).resolve(), Path(folder)
    if source.suffix.lower() == '.caepre':
        return unpack_project(source, folder)
    root = Path(approved_root or source.parent).resolve()
    paths = dependency_files(source, root) if registered is None else [Path(row['path']).resolve() for row in registered]
    if source not in paths:
        raise ValueError('Registered editable CAD entry is missing')
    # Keep native names where possible (cross-document expressions may refer to
    # them). Link paths are explicit; collisions get a unique copied filename.
    copies, used = {}, set()
    for index, path in enumerate(paths):
        name = path.name
        if name.casefold() in used:
            name = path.stem + '_' + str(index) + '.FCStd'
        used.add(name.casefold())
        copies[path] = folder / name
    original_locations = original_locations or {}
    locations = {path: Path(original_locations.get(str(path), str(path))) for path in paths}
    source_to_copy = {str(location.resolve()): copies[path] for path, location in locations.items()}
    folder.mkdir(parents=True, exist_ok=False)
    hashes = {path: sha(path) for path in paths}
    for path in paths:
        def resolve(link, path=path):
            if not link['file']:
                return None
            referenced = logical_file(locations[path].parent, link['file'])
            if str(referenced) not in source_to_copy:
                raise ValueError('Native source dependency was not registered')
            return source_to_copy[str(referenced)].name
        relocate(path, copies[path], resolve)
    if any(sha(path) != before for path, before in hashes.items()):
        raise ValueError('Native CAD source changed while creating the working copy')
    return {'kind': 'native-import', 'source_files': [{'path': str(path), 'sha256': hashes[path]} for path in paths]}, copies[source]
