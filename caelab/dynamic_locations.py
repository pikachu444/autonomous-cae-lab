"""Exact NS2 locations attached to the existing PVD input/registration contract.

This extends the existing *-locations.json sidecar, not the project format or
scheduler. Its dependencies are copies of the existing result and input files.
A clock value alone is never an identity across sources, steps or restart jobs.
"""
from copy import deepcopy
import json
import math
import hashlib
import os
import tempfile
from pathlib import Path
import shutil
import uuid
from xml.etree import ElementTree as ET

from .adapters.frozen_fem import _read, _relative, _sha
from .storage import save_json
from .dynamic_result_store import (load_result, artifact_references, frame_metadata, RetainedResult,
                                   admit_pin, verify_pin, _json)
from .execution_control import check_cancelled

KEY = 'dynamic_locations'
CLOCKS = {'dynamic': ('s', 'PHYSICAL_TIME'),
          'static-preload': ('1', 'DIMENSIONLESS_MODEL_TIME')}
MAX_SIDECAR = 8 * 1024 * 1024


def _plain(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _path(root, name):
    path = Path(root) / _relative(name)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Dynamic location dependencies must be regular local files')
    if not path.is_file() or not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('Missing or escaped dynamic location dependency: ' + name)
    return path


def pin(root, path):
    path = Path(path)
    return {'relative': path.relative_to(root).as_posix(),
            'bytes': path.stat().st_size, 'sha256': _sha(path)}


def _check(root, reference):
    if (not isinstance(reference, dict) or set(reference) != {'relative', 'bytes', 'sha256'}
            or type(reference['bytes']) is not int or reference['bytes'] < 0
            or not isinstance(reference['sha256'], str) or len(reference['sha256']) != 64
            or any(c not in '0123456789abcdef' for c in reference['sha256'])):
        raise ValueError('An exact dynamic location file reference is required')
    path = _path(root, reference['relative'])
    if path.stat().st_size != reference['bytes'] or _sha(path) != reference['sha256']:
        raise ValueError('Retained dynamic location dependency changed: ' + reference['relative'])
    return path


def required(entry, metadata):
    """Never silently demote a generated NS2 sidecar to anonymous PVD time."""
    path = Path(entry)
    return KEY in (metadata or {}) or (path.stem in CLOCKS and
        (path.parent / (path.stem + '-locations.json')).exists())


def retain_sources(folder, attempt, result):
    """Copy the exact admitted result and its pinned sources once for both clocks."""
    folder, attempt = Path(folder), Path(attempt)
    result_path = _path(attempt, 'dynamic_result.json')
    saved = load_result(result_path, metadata_only=True)
    actual = result.index if isinstance(result, RetainedResult) else _plain(result)
    if dict(saved) != actual:
        raise ValueError('Dynamic Post must project its exact saved result')
    sources = {'dynamic_result.json': pin(attempt, result_path)}
    for name, item in result['source_pins'].items():
        if name in sources:
            raise ValueError('Duplicate dynamic result dependency')
        sources[name] = {'relative': name, **item}
    for reference in artifact_references(saved):
        if reference['relative'] in sources:
            raise ValueError('Duplicate dynamic frame dependency')
        sources[reference['relative']] = reference
    files = []
    for name, reference in sorted(sources.items()):
        check_cancelled()
        source = admit_pin(attempt, reference)
        destination = folder / 'source' / _relative(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ValueError('Refusing to overwrite an existing portable dependency')
        before = source.stat()
        fd, temporary_name = tempfile.mkstemp(prefix='.caelab-', dir=destination.parent)
        temporary = Path(temporary_name)
        digest = hashlib.sha256()
        try:
            with source.open('rb') as stream, os.fdopen(fd, 'wb') as output:
                while True:
                    check_cancelled()
                    block = stream.read(1024*1024)
                    if not block: break
                    digest.update(block); output.write(block)
                output.flush(); os.fsync(output.fileno())
            after = source.stat()
            stamp = lambda st: (st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino, st.st_dev)
            if stamp(before) != stamp(after) or digest.hexdigest() != reference['sha256'] or temporary.stat().st_size != reference['bytes']:
                raise ValueError('Dynamic source changed during portable retention: ' + name)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        files.append({'relative': 'source/' + name, 'bytes': reference['bytes'], 'sha256': reference['sha256']})
    return files


def _origin(data, files):
    refs = {p['relative']: p for p in files}
    return {'snapshot_id': data['snapshot_id'], 'job_id': data.get('job_id'),
            'job_identity': deepcopy(data.get('job_identity')),
            'input_origin': deepcopy(data.get('input_origin')),
            'result': deepcopy(refs['source/dynamic_result.json']),
            'snapshot': deepcopy(refs['source/frozen_input/snapshot.json']),
            'state_source': deepcopy(data['state_source'])}


def write_sidecar(entry, result, metadata, frames, source_files):
    """Return the small reference to be placed in native_metadata."""
    entry = Path(entry)
    category = entry.stem
    if category not in CLOCKS:
        raise ValueError('Separate dynamic and static-preload collections are required')
    files = [pin(entry.parent, entry)]
    files += [pin(entry.parent, entry.parent / r['file']) for r in frames]
    files += deepcopy(source_files)
    companions = []
    declaration_path = entry.parent/'contact-declarations.json'
    if declaration_path.is_file():
        names = ['contact-declarations.json', 'contact.pvd', 'body_map.json']
        names += [p.name for p in entry.parent.glob('frame*.json')]
        names += [p.name for p in entry.parent.glob('frame*.vtu')]
        names += [name for name in ('contact-inspection.json','contact-topology.json',
                                   'contact-surfaces.vtu','tie-adjustment.json') if (entry.parent/name).is_file()]
        companions = sorted(set(names))
        existing = {row['relative'] for row in files}
        files += [pin(entry.parent,entry.parent/name) for name in companions if name not in existing]
    locations = frame_metadata(result)
    sidecar = {'locations': [deepcopy(locations[r['result_frame_index']]['location']) for r in frames],
               'meanings': deepcopy(result['meanings']), 'category': category,
               'native_metadata': deepcopy(metadata), 'frames': deepcopy(frames),
               'files': files, 'origin': _origin(result, files)}
    if companions:
        sidecar['native_coordinate_companions'] = companions
    path = entry.with_name(category + '-locations.json')
    save_json(path, sidecar)
    reference = pin(entry.parent, path)
    # Validate before publication, using the same reader as registration/reopen.
    load(entry, {**metadata, KEY: reference})
    return reference


def load(entry, metadata, *, verification='selected'):
    """Validate exact location/result/model/time membership without solving."""
    if verification not in ('selected', 'full'):
        raise ValueError('Choose selected or explicit full dependency verification')
    entry = Path(entry).absolute()
    if entry.suffix.lower() != '.pvd' or not isinstance(metadata, dict) or KEY not in metadata:
        raise ValueError('Exact dynamic locations require their registered PVD declaration')
    reference = metadata[KEY]
    path = admit_pin(entry.parent,reference)
    sidecar = _json(entry.parent,reference,MAX_SIDECAR)
    category = sidecar.get('category')
    if (category not in CLOCKS or entry.name != category + '.pvd'
            or reference['relative'] != category + '-locations.json'):
        raise ValueError('Dynamic location collection/category differs from its PVD')
    if sidecar.get('native_metadata') != {k: v for k, v in metadata.items() if k != KEY}:
        raise ValueError('Dynamic field/clock declarations differ from the pinned sidecar')
    rows = sidecar.get('files')
    if not isinstance(rows, list) or not rows or len(rows) > 4096:
        raise ValueError('A bounded dynamic location dependency set is required')
    references, paths = {}, [path]
    for item in rows:
        dependency = (_check if verification == 'full' else admit_pin)(entry.parent, item)
        if item['relative'] in references or dependency == path:
            raise ValueError('Duplicate or self-referencing dynamic location dependency')
        references[item['relative']] = item
        paths.append(dependency)
    if entry.name not in references:
        raise ValueError('Dynamic location sidecar does not pin its PVD')
    for name in ('source/dynamic_result.json', 'source/frozen_input/snapshot.json'):
        if name not in references:
            raise ValueError('Dynamic locations lack their exact result/snapshot')
    _check(entry.parent, references[entry.name])
    result = load_result(_path(entry.parent,'source/dynamic_result.json'), metadata_only=True,
                         expected_pin=references['source/dynamic_result.json'])
    if result.get('kind') != 'calculix_dynamic_result' or result.get('version') not in (1, 2):
        raise ValueError('Dynamic locations require the retained NS2 result')
    if sidecar.get('origin') != _origin(result, rows):
        raise ValueError('Dynamic location origin differs from the retained result')
    origin = sidecar['origin']
    if origin['job_id'] is not None and (origin.get('job_identity') or {}).get('id') != origin['job_id']:
        raise ValueError('Dynamic result job identity is missing or inconsistent')
    if sidecar.get('meanings') != result.get('meanings'):
        raise ValueError('Dynamic field meanings differ from the retained result')
    expected_sources = {'source/dynamic_result.json'}
    for name, item in result['source_pins'].items():
        name = 'source/' + _relative(name)
        expected_sources.add(name)
        if references.get(name) != {'relative': name, **item}:
            raise ValueError('Dynamic source lineage differs from the exact result: ' + name)
    for item in artifact_references(result):
        name = 'source/' + item['relative']
        expected_sources.add(name)
        if references.get(name) != {**item, 'relative': name}:
            raise ValueError('Dynamic frame dependency differs from exact result: ' + name)
    # Small pinned snapshot + mesh describe selection. Native deck/CAD/rin
    # byte-level admission remains an explicit full audit, not a hidden seek.
    from .adapters.contact_fem import validate_snapshot
    from .calculix_dynamic import location, stage_contract
    from .contact_deck import validate_model
    snapshot_path = _check(entry.parent, references['source/frozen_input/snapshot.json'])
    if verification == 'full':
        manifest, model, _, _ = validate_snapshot(snapshot_path)
    else:
        manifest = json.loads(_read(snapshot_path, MAX_SIDECAR))
        mesh_name = 'source/frozen_input/mesh.json'
        if mesh_name not in references:
            raise ValueError('Dynamic locations lack their pinned original model')
        model = json.loads(_read(_check(entry.parent,references[mesh_name])))
        if manifest.get('kind') != 'freecad-contact-frozen' or manifest.get('input_file') != 'contact.inp':
            raise ValueError('Dynamic source is not the original frozen input contract')
        for row in manifest['files']:
            name = 'source/frozen_input/' + _relative(row['relative'])
            if references.get(name) != {**row, 'relative': name}:
                raise ValueError('Frozen snapshot members differ from the exact result pins')
        validate_model(model)
    if manifest['id'] != result['snapshot_id'] or stage_contract(model) != result.get('stages'):
        raise ValueError('Dynamic result stages differ from the original frozen snapshot')
    payload = _read(entry, MAX_SIDECAR)
    if b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():
        raise ValueError('PVD declarations/entities are not supported')
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise ValueError('Invalid dynamic PVD collection XML') from error
    if root.tag != 'VTKFile' or root.get('type') != 'Collection':
        raise ValueError('Dynamic locations require a VTK Collection')
    datasets = root.findall('./Collection/DataSet')
    if not 1 <= len(datasets) <= 1024:
        raise ValueError('Dynamic PVD requires 1..1024 exact datasets')
    frames, locations = [], []
    for i, frame in enumerate(result['frames']):
        native = frame['native']
        loc = location(model, native['step'], native['load_parameter'])
        if frame['location'] != loc or type(native.get('increment')) is not int or native['increment'] < 1:
            raise ValueError('Dynamic native step/location differs from the frozen program')
        frame_category = 'dynamic' if loc['physical_time_available'] else 'static-preload'
        if frame_category != category:
            continue
        time = loc['physical_time_s'] if category == 'dynamic' else loc['native_global_coordinate']
        frames.append({'result_frame_index': i, 'file': 'frame' + str(i + 1).zfill(4) + '.vtu',
                       'timestep': time, 'native': deepcopy(native),
                       'native_time_token': frame['native_time_token']})
        locations.append(loc)
    if sidecar.get('frames') != frames or sidecar.get('locations') != locations or len(datasets) != len(frames):
        raise ValueError('Dynamic exact frame membership differs from the retained result')
    values = [row['timestep'] for row in frames]
    unit, semantics = CLOCKS[category]
    if (not values or any(type(t) not in (int, float) or not math.isfinite(t) for t in values)
            or any(b <= a for a, b in zip(values, values[1:]))):
        raise ValueError('Ambiguous dynamic locations; no nearest time or interpolation is permitted')
    if metadata.get('static') is not None or metadata.get('time') != {'unit': unit, 'semantics': semantics, 'values': values}:
        raise ValueError('Dynamic physical seconds and static dimensionless coordinates must remain separate')
    for dataset, row in zip(datasets, frames):
        if (dataset.get('file') != row['file'] or float(dataset.attrib['timestep']) != row['timestep']
                or dataset.get('part', '0') != '0' or dataset.get('group', '') != ''):
            raise ValueError('PVD frame/clock differs from its exact native location')
    expected_files = {entry.name, *(row['file'] for row in frames), *expected_sources}
    companions = sidecar.get('native_coordinate_companions', [])
    if not isinstance(companions, list) or len(companions) != len(set(companions)):
        raise ValueError('Invalid native coordinate companion membership')
    if companions:
        required_companions = {'contact.pvd','contact-declarations.json','body_map.json'}
        if not required_companions <= set(companions):
            raise ValueError('Native contact projection lacks its original declaration')
        for name in companions:
            if (name not in references or '/' in name or
                not (name in required_companions | {'contact-inspection.json','contact-topology.json',
                     'contact-surfaces.vtu','tie-adjustment.json'} or
                     __import__('re').fullmatch(r'frame[0-9]{4}\.(json|vtu)', name))):
                raise ValueError('Foreign native contact companion')
        native_metadata = json.loads(_read(_check(entry.parent, references['contact-declarations.json']),MAX_SIDECAR))
        if native_metadata['arrays'] != metadata['arrays']:
            raise ValueError('Dynamic and native contact field declarations diverge')
        _check(entry.parent,references['contact.pvd'])
        if verification == 'full' and 'contact_inspection' in native_metadata:
            from .contact_inspection import load as load_contact
            contact=load_contact(entry.parent/'contact.pvd', native_metadata['contact_inspection'],lazy=True)
            for _ in contact['frames']:
                check_cancelled()
        expected_files.update(companions)
    if set(references) != expected_files:
        raise ValueError('Dynamic location dependency membership differs from the pinned source set')
    ordered_paths = list(dict.fromkeys([entry, *(entry.parent/r['file'] for r in frames), *paths]))
    return {'paths': ordered_paths, 'references': references, 'sidecar': sidecar,
            'verification': {'scope': 'ALL_REFERENCED_BYTES' if verification == 'full' else 'PINNED_SELECTION_METADATA',
                             'paths_and_sizes': 'CHECKED',
                             'raw_and_unselected_bytes': 'VERIFIED' if verification == 'full' else 'DEFERRED',
                             'engineering_qualification': 'UNKNOWN'},
            'origin': deepcopy(origin), 'frames': frames, 'locations': locations,
            'result_status': {k: deepcopy(result[k]) for k in
                ('execution_status', 'complete_analysis', 'qualification')}}


def select(entry, metadata, *, time, result_frame_index=None, registration_origin=None):
    """Resolve only within this exact registered source; never search other jobs."""
    bundle = verify_registration(entry, metadata, registration_origin)
    if type(time) not in (int, float) or not math.isfinite(time):
        raise ValueError('Choose an exact finite native timestep')
    matches = [(i, r) for i, r in enumerate(bundle['frames']) if r['timestep'] == time]
    if result_frame_index is not None:
        if type(result_frame_index) is not int:
            raise ValueError('Choose an exact result frame index')
        matches = [(i, r) for i, r in matches if r['result_frame_index'] == result_frame_index]
    if len(matches) != 1:
        raise ValueError('No unique exact dynamic location; no nearest time or interpolation')
    index, row = matches[0]
    root = Path(entry).absolute().parent
    _check(root, bundle['references'][row['file']])
    # Selected native arrays must belong to this exact result/index, not merely
    # have a self-consistent file hash. _Frames performs that check on read.
    result = load_result(root/'source/dynamic_result.json',expected_pin=bundle['references']['source/dynamic_result.json'])
    result['frames'][row['result_frame_index']]
    inspection = Path(row['file']).with_suffix('.json').name
    if inspection in bundle['references']:
        _check(root, bundle['references'][inspection])
    return {'category': bundle['sidecar']['category'], 'origin': bundle['origin'],
            **bundle['result_status'],
            'selected_location': deepcopy(bundle['locations'][index]),
            'selected_native': deepcopy(row['native']), 'result_frame_index': row['result_frame_index'],
            'selection_semantics': 'EXACT_NATIVE_LOCATION',
            'verification': {**bundle['verification'], 'scope': 'METADATA_AND_SELECTED_FRAME_BYTES',
                             'selected_result_frame': row['result_frame_index'],
                             'topology_bytes': 'VERIFIED', 'selected_vtu_bytes': 'VERIFIED',
                             'selected_native_array_bytes': 'VERIFIED'}}


def verify_registration(entry, metadata, registration_origin, *, verification='selected'):
    """The saved origin is redundant on purpose: a changed source cannot rebind it."""
    bundle = load(entry, metadata, verification=verification)
    if registration_origin is not None and registration_origin.get(KEY) != bundle['origin']:
        raise ValueError('Registered dynamic origin differs from its pinned source/result')
    return bundle


def verify_saved_source(entry, metadata, registration_origin, source_pins=None, *, full=False):
    """Validate existing saved dependency pins without rereading unselected bytes.

    A save/registration may request full=True. Query/reopen use the exact pins
    already retained by the existing owner; selected arrays get their own check.
    """
    bundle = verify_registration(entry, metadata, registration_origin,
                                 verification='full' if full else 'selected')
    root = Path(entry).absolute().parent
    refs = {**bundle['references'], metadata[KEY]['relative']: metadata[KEY]}
    pinned = [{'path': str(path), 'bytes': refs[path.relative_to(root).as_posix()]['bytes'],
               'sha256': refs[path.relative_to(root).as_posix()]['sha256']}
              for path in bundle['paths']]
    if source_pins is not None:
        expected = {str(Path(row['path']).absolute()): {k: row[k] for k in ('bytes','sha256')}
                    for row in source_pins}
        actual = {row['path']: {k: row[k] for k in ('bytes','sha256')} for row in pinned}
        if len(expected) != len(source_pins) or expected != actual:
            raise ValueError('Registered source pins differ from the exact dynamic dependencies')
    return {'pins': pinned, 'verification': bundle['verification']}


def audit(entry, metadata, registration_origin=None):
    """Explicit complete byte audit; no result or original execution is modified."""
    return verify_saved_source(entry, metadata, registration_origin, full=True)['verification']


def publish_job_inputs(workbench, result, output, job_id, arguments, *, native_job_id=None):
    """Register both existing clock projections through the existing registrar.

    Called once by Workbench's existing run worker. No launch/retry is performed
    here; a publication error remains a failed publication, not another solve.
    """
    from .native_inputs import register_native_input
    output = Path(output)
    artifacts = result['dynamic_post_artifacts']
    if not isinstance(artifacts, dict) or not artifacts or set(artifacts) - set(CLOCKS):
        raise ValueError('Choose the exact dynamic/static-preload output collections')
    primary = 'dynamic' if 'dynamic' in artifacts else 'static-preload'
    if result.get('post_artifact') != artifacts[primary]:
        raise ValueError('Primary dynamic Post artifact differs from this saved result')
    # Validate every category first. Never publish one clock as a substitute for
    # another when the second category is corrupt or from a different run.
    for category, artifact in artifacts.items():
        entry = _check(output, {k: artifact[k] for k in ('relative', 'bytes', 'sha256')})
        bundle = load(entry, artifact.get('native_metadata'))
        origin = bundle['origin']
        if (entry.stem != category or origin['job_id'] != (job_id if native_job_id is None else native_job_id)
                or origin['input_origin'] != arguments.get('origin')
                or result.get('data_id') != arguments['settings']['data_id']
                or origin['snapshot_id'] != result.get('snapshot_id')
                or {k: origin['result'][k] for k in ('bytes', 'sha256')} !=
                   {k: result['dynamic_result'][k] for k in ('bytes', 'sha256')}):
            raise ValueError('Dynamic Post origin does not belong to this exact job/input/result')
    published = {}
    for category, artifact in artifacts.items():
        entry = _check(output, {k: artifact[k] for k in ('relative', 'bytes', 'sha256')})
        receipt = register_native_input(workbench.root, output, entry, 'D' + uuid.uuid4().hex,
            root_id='job:' + job_id, relative=artifact['relative'],
            limit=workbench.config.get('local_input_max_bytes', 2 * 1024 ** 3),
            native_metadata=artifact['native_metadata'])
        published[category] = {'id': receipt['id'], 'format': receipt['format'], 'sha256': receipt['sha256'],
                              'category': category, 'label': '동적 시간 결과' if category == 'dynamic' else '정적 선행하중 결과'}
    result['post_inputs'] = list(published.values())
    result['post_input'] = deepcopy(published[primary])


def contact_bundle(entry, metadata, registration_origin=None):
    """Read existing contact companion metadata; unselected payloads stay deferred.

    The shared contact reader validates its original topology, physical meanings,
    tokens and masks. This only binds that reader to an exact NS2 source/clock.
    """
    saved=verify_registration(entry,metadata,registration_origin)
    root=Path(entry).absolute().parent
    ref=saved['references'].get('contact-declarations.json')
    if ref is None:raise ValueError('No retained native contact companion')
    declarations=json.loads(_read(_check(root,ref),MAX_SIDECAR))
    contact_ref=declarations.get('contact_inspection')
    if not contact_ref:raise ValueError('This structural model has no retained contact inspection')
    if saved['references'].get(contact_ref['relative'])!=contact_ref:
        raise ValueError('Contact inspection is not pinned by the selected dynamic result')
    from .contact_inspection import load as contact_load
    contact=contact_load(root/'contact.pvd',contact_ref,lazy=True)
    source=contact['manifest']['source'];origin=saved['origin']
    index=load_result(root/'source/dynamic_result.json',metadata_only=True,
                      expected_pin=saved['references']['source/dynamic_result.json'])
    if (source['snapshot_id']!=origin['snapshot_id'] or
            source['snapshot_sha256']!=origin['snapshot']['sha256'] or
            source['raw_frd_sha256']!=index['source_pins']['solver/contact.frd']['sha256'] or
            source['raw_dat_sha256']!=index['source_pins']['solver/contact.dat']['sha256'] or
            [r['static'] for r in contact['frames'].metadata] != [r['native'] for r in frame_metadata(index)]):
        raise ValueError('Contact companion and dynamic original source/native frames differ')
    return contact,saved


def inspect_contact(entry, metadata, *, time, pair_id, side='both', field='CPRESS',
                    quantity='CFN', component=2, result_frame_index=None,
                    registration_origin=None, include_history=False):
    """Exact selected contact sample. Full native-coordinate curve is opt-in."""
    selected=select(entry,metadata,time=time,result_frame_index=result_frame_index,
                    registration_origin=registration_origin)
    contact,_=contact_bundle(entry,metadata,registration_origin)
    from .contact_inspection import inspect
    value=inspect(contact,pair_id,side,selected['result_frame_index'],field,quantity,component,
                  include_history=include_history)
    return {**value,'dynamic':selected,'history_requested':include_history,
            'verification':{'scope':'SELECTED_CONTACT_AND_DYNAMIC_FRAME_BYTES',
                            'unselected_payloads':'DEFERRED' if not include_history else 'READ_FOR_EXPLICIT_HISTORY'}}


def contact_history(entry, metadata, *, pair_id, quantity='CFN', component=2,
                    step_id=None, registration_origin=None):
    """Explicit exact native resultant history; metadata filters before byte reads.

    Existing native coordinate axis is preserved, including mixed static/dynamic
    meanings. Selected physical locations are reported separately, never relabelled.
    """
    contact,saved=contact_bundle(entry,metadata,registration_origin)
    index=load_result(Path(entry).parent/'source/dynamic_result.json',metadata_only=True,
                      expected_pin=saved['references']['source/dynamic_result.json'])
    rows=frame_metadata(index)
    chosen=[i for i,r in enumerate(rows) if step_id is None or r['location']['id']==step_id]
    from collections.abc import Sequence
    class Selection(Sequence):
        def __len__(self):return len(chosen)
        def __getitem__(self,i):return contact['frames'][chosen[i]]
    from .contact_inspection import force_history
    result=force_history({**contact,'frames':Selection()},pair_id,quantity,component)
    return {**result,'origin':saved['origin'],'result_frame_indices':chosen,
            'locations':[deepcopy(rows[i]['location']) for i in chosen],
            'selection_semantics':'EXACT_NATIVE_LOCATION','qualification':'UNKNOWN'}
