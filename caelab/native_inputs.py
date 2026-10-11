"""Immutable VTU/PVD snapshots; native readers retain the format's meaning."""
from pathlib import Path, PureWindowsPath
import hashlib
import math
import os
import xml.etree.ElementTree as ET

from .evaluation import file_hash
from .storage import save_json, utc_now


NATIVE_EXTENSIONS = {'.vtu', '.pvd'}


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


def register_native_input(workbench_root, approved_root, source, identifier, *, root_id, relative, limit):
    """Publish a receipt only after the entire referenced file set is copied."""
    root = Path(approved_root).resolve(strict=True)
    source = _within_root(source, root)
    paths, parsed_sha = _files(source, root)
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
        raise ValueError('PVD collection changed while its dependencies were registered')
    # Recheck the set together: an early frame may change while a later one copies.
    for path, entry in zip(paths, files):
        _within_root(path, root)
        if _identity(path.stat()) != before[path] or file_hash(path) != entry['sha256']:
            raise ValueError('Source changed during native registration')
    entry = files[0]
    receipt = {'id': identifier, 'name': source.name, 'file': entry['file'],
               'bytes': entry['bytes'], 'sha256': entry['sha256'], 'created_utc': utc_now(),
               'kind': 'native_result', 'format': source.suffix.lower()[1:],
               'files': files, 'total_bytes': sum(item['bytes'] for item in files),
               'origin': {'mode': 'LOCAL_SNAPSHOT', 'root_id': root_id, 'relative': relative}}
    save_json(folder / 'input.json', receipt)
    return receipt
