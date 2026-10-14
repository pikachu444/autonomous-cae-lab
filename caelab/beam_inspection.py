"""Portable B32R result admission tied to the retained native model and FRD.

This is a companion to the existing native input store, not another result
store or executor. Reopening reparses the original data and regenerates view
bytes in memory. Hash agreement alone never admits field meanings or values.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from .beam_deck import matches_saved_input
from .beam_model import BACKEND, validate_model
from .beam_results import (sha, read_frd, post_metadata, post_files, channels,
                           _read_bytes, _printed_close)
from .storage import save_json

KIND = 'calculix-beam-inspection'
MANIFEST = 'beam_inspection.json'
CONTEXT = 'source/execution.json'
MAX_MEMBERS = 4096


def _normalize(value):
    return json.loads(json.dumps(value, allow_nan=False))


def _json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate beam JSON key: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Non-finite beam JSON value: ' + value)
    return json.loads(_read_bytes(path), object_pairs_hook=unique, parse_constant=invalid)


def _member(root, relative):
    if (not isinstance(relative, str) or not relative or any(c in relative for c in '\\:\x00')
            or Path(relative).is_absolute() or any(p in ('', '.', '..') for p in relative.split('/'))):
        raise ValueError('Beam bundle requires a contained relative file path')
    path = root / relative
    if (any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file()
            or not path.resolve().is_relative_to(root.resolve())):
        raise ValueError('Beam bundle member must be a regular contained file: ' + relative)
    return path


def _row(root, name):
    path = _member(root, name)
    return {'relative':name, 'bytes':path.stat().st_size, 'sha256':sha(path)}


def descriptor(value):
    if (not isinstance(value, dict) or set(value) != {'relative', 'bytes', 'sha256'}
            or value['relative'] != MANIFEST or type(value['bytes']) is not int
            or not 0 < value['bytes'] <= 8*1024**2 or not isinstance(value['sha256'], str)
            or not re.fullmatch('[0-9a-f]{64}', value['sha256'])):
        raise ValueError('Beam declarations require the exact retained bundle reference')
    return deepcopy(value)


def _sources(root, members, context):
    """Revalidate input, execution association, solver version and complete frames."""
    from .adapters.beam_fem import validate_snapshot, log_diagnostics
    required = {CONTEXT, 'source/frozen_input/snapshot.json', 'source/frozen_input/mesh.json',
                'source/frozen_input/beam.inp', 'source/frozen_input/editable.FCStd',
                'source/frozen_input/editable.caepre', 'source/solver/beam.inp', 'source/solver/beam.frd'}
    if not required <= members.keys():
        raise ValueError('Beam bundle is missing native input/model/FRD/execution sources')
    manifest, model, pins = validate_snapshot(members['source/frozen_input/snapshot.json'])
    status = context.get('execution_status')
    if (context.get('kind') != 'beam-execution-context' or context.get('schema_version') != '1'
            or context.get('backend') != BACKEND or status not in {'SUCCEEDED', 'FAILED', 'CANCELLED'}
            or context.get('input_pins') != pins or context.get('snapshot_id') != manifest['id']):
        raise ValueError('Beam execution does not match the preserved native snapshot')
    runtime = context.get('runtime')
    if (not isinstance(runtime, dict) or runtime.get('version') != '2.22'
            or not isinstance(runtime.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', runtime['sha256'])
            or not isinstance(runtime.get('executable'), str) or not runtime['executable']):
        raise ValueError('Beam execution lacks its recorded CalculiX 2.22 executable identity')
    # The executable need not exist on a read-only/Post-only machine. Its digest
    # is retained provenance, not a claim that the historical binary was rerun.
    executed = _read_bytes(members['source/solver/beam.inp'])
    if (hashlib.sha256(executed).hexdigest() != pins['beam.inp']['sha256']
            or not matches_saved_input(executed.decode('ascii'), model)):
        raise ValueError('Executed beam input differs from its frozen model/conditions')
    source = model.get('source')
    if not isinstance(source, dict):
        raise ValueError('Beam bundle lacks its native document/Analysis/mesh source identity')
    draft = model['draft']
    identities = ('document_id', 'native_document', 'analysis_id', 'mesh_id', 'solver_id')
    if (any(not isinstance(source.get(k), str) or not source[k] for k in identities)
            or source['analysis_id'] != draft['analysis_id'] or source['mesh_id'] != draft['mesh_id']
            or source['document_id'] != manifest.get('document_id')
            or source['analysis_id'] != manifest.get('analysis_id')):
        raise ValueError('Beam document/Analysis/mesh source identity differs')
    ends = source.get('end_object_ids')
    if (not isinstance(ends, list) or len(ends) != 2 or
            any(not isinstance(n, str) or not n for n in ends) or len(set(ends)) != 2):
        raise ValueError('Beam source requires two distinct native end conditions')
    binding = source.get('binding')
    if not isinstance(binding, dict) or binding.get('mesh_id') != draft['mesh_id']:
        raise ValueError('Beam source lacks its exact mesh binding')
    from .storage import canonical_hash
    if binding.get('mesh_sha256') != canonical_hash({'nodes':model['nodes'], 'elements':model['elements']}):
        raise ValueError('Beam source binding differs from the retained mesh')
    if not isinstance(binding.get('ends'), list) or len(binding['ends']) != 2:
        raise ValueError('Beam source requires its two original endpoint bindings')
    for reference, saved in [(draft['edge'], binding.get('edge')),
                             *[(r['reference'], pin) for r, pin in zip(
                                 draft['ends'], binding.get('ends', []))]]:
        if not isinstance(saved, dict) or any(saved.get(k) != reference[k] for k in ('object', 'subelement')):
            raise ValueError('Beam native geometry references differ from the frozen conditions')
    observed = read_frd(members['source/solver/beam.frd'], model, allow_partial=status != 'SUCCEEDED')
    logs = []
    for suffix in ('stdout', 'stderr'):
        path = members.get(f'source/solver/ccx_beam.{suffix}.log')
        logs.append(_read_bytes(path).decode('utf-8', errors='replace') if path else '')
    diagnostics = log_diagnostics(*logs)
    for key in ('errors', 'warnings', 'has_unreviewed_native_diagnostic'):
        if key in context.get('diagnostics', {}) and context['diagnostics'][key] != diagnostics[key]:
            raise ValueError('Beam execution diagnostics differ from its retained native logs')
    if status == 'SUCCEEDED':
        if (type(context.get('native_return_code')) is not int or context['native_return_code'] != 0
                or diagnostics['has_unreviewed_native_diagnostic'] or model['draft']['diagnostic_oblique']
                or not observed['complete_file']
                or not _printed_close(observed['frames'][-1]['load_parameter_token'], 1.)):
            raise ValueError('Beam success declaration conflicts with native execution/output')
    return model, observed, status


def retain(run_folder, artifact, execution, *, post_folder=None):
    """Copy stopped, frozen raw sources next to the view; seal before registration.

    Called only by the existing beam adapter after owned process cleanup. Empty
    solver logs are not dependencies; all nonempty solver files are retained.
    """
    run_folder = Path(run_folder).absolute()
    folder = Path(post_folder).absolute() if post_folder is not None else run_folder / 'post'
    if artifact.get('relative') != 'post/beam.pvd':
        raise ValueError('Expected the beam adapter Post artifact')
    view = folder / 'beam.pvd'
    if view.stat().st_size != artifact['bytes'] or sha(view) != artifact['sha256']:
        raise ValueError('Beam view changed before sealing')
    fields = _json(folder / 'beam_fields.json')
    if fields['native_metadata'] != artifact['native_metadata']:
        raise ValueError('Beam declarations changed before sealing')
    source_dir = folder / 'source'
    source_dir.mkdir(exist_ok=False)
    source_names = []
    # Copy the entire fixed input snapshot and nonempty raw solver outputs. Never
    # reference the writable origin or executable path from the portable bundle.
    for group in ('frozen_input', 'solver'):
        original = run_folder / group
        for path in sorted(original.iterdir()):
            if not path.is_file() or path.is_symlink():
                raise ValueError('Unexpected nonregular beam raw source')
            raw = _read_bytes(path)
            if not raw:
                continue
            name = 'source/' + group + '/' + path.name
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            if sha(path) != hashlib.sha256(raw).hexdigest():
                raise ValueError('Beam raw source changed while sealing')
            source_names.append(name)
    keys = ('schema_version', 'backend', 'execution_status', 'snapshot_id', 'data_id',
            'input_pins', 'runtime', 'native_return_code', 'diagnostics', 'diagnostic_only')
    context = {key:deepcopy(execution[key]) for key in keys if key in execution}
    context['kind'] = 'beam-execution-context'
    save_json(folder / CONTEXT, context)
    source_names.append(CONTEXT)
    views = [name for name, _ in post_files(fields['observed'], fields['model'],
                                           source_status=context['execution_status'])]
    names = ['beam_fields.json', *views, *source_names]
    manifest = {'kind':KIND, 'schema_version':'1', 'main_view':'beam.pvd',
                'native_metadata':deepcopy(artifact['native_metadata']),
                'files':[_row(folder, name) for name in names]}
    save_json(folder / MANIFEST, manifest)
    reference = _row(folder, MANIFEST)
    # This is the same mandatory reparse/regeneration path used on registration
    # and reopening, not a hash-only fast path for the producer.
    checked = load(view, reference)
    return {**deepcopy(artifact), 'native_metadata':{
        **checked['manifest']['native_metadata'], 'beam_inspection':reference}}


def load(view, reference=None):
    """Read-only admission. No bypass for rehashed observations or transformed data."""
    view = Path(view).absolute(); root = view.parent
    if view.name != 'beam.pvd':
        raise ValueError('Beam bundle requires its original beam.pvd reader')
    manifest_path = _member(root, MANIFEST)
    if manifest_path.stat().st_size > 8*1024**2:
        raise ValueError('Beam bundle manifest exceeds 8 MiB')
    manifest_pin = _row(root, MANIFEST)
    if reference is not None:
        descriptor(reference)
        if manifest_pin != reference:
            raise ValueError('Retained beam bundle changed')
    manifest = _json(manifest_path)
    if (manifest.get('kind') != KIND or manifest.get('schema_version') != '1'
            or manifest.get('main_view') != view.name):
        raise ValueError('Native view and beam bundle do not match')
    records = manifest.get('files')
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_MEMBERS:
        raise ValueError('Invalid beam bundle dependency set')
    paths = [manifest_path]; members = {}
    for row in records:
        if not isinstance(row, dict) or set(row) != {'relative', 'bytes', 'sha256'}:
            raise ValueError('Invalid beam source descriptor')
        name = row['relative']
        path = _member(root, name)
        if name in members or name == MANIFEST:
            raise ValueError('Duplicate or self-referencing beam source')
        if type(row['bytes']) is not int or row['bytes'] <= 0 or _row(root, name) != row:
            raise ValueError('Retained beam source changed: ' + name)
        members[name] = path; paths.append(path)
    if not {'beam.pvd', 'beam_fields.json', CONTEXT} <= members.keys():
        raise ValueError('Beam bundle is missing view/observations/execution context')
    context = _json(members[CONTEXT])
    model, observed, status = _sources(root, members, context)
    metadata = post_metadata(observed, model, source_status=status)
    fields = _json(members['beam_fields.json'])
    expected = _normalize({'kind':'beam-native-fields', 'schema_version':'1', 'model':model,
        'observed':observed, 'source_execution_status':status, 'native_metadata':metadata})
    if fields != expected:
        raise ValueError('Retained beam observations/model/meaning differ from native FRD and mesh')
    if manifest['native_metadata'] != metadata:
        raise ValueError('Beam declarations differ from native frames, axes, units or execution status')
    expected_names = {'beam_fields.json', CONTEXT}
    expected_names.update(name for name in members if name.startswith(('source/frozen_input/', 'source/solver/')))
    # Do not admit another model file under the frozen input path unnoticed.
    frozen_names = {name for name in members if name.startswith('source/frozen_input/')}
    if frozen_names != {'source/frozen_input/' + name for name in context['input_pins']}:
        raise ValueError('Beam snapshot dependency set differs')
    for name, payload in post_files(observed, model, source_status=status):
        expected_names.add(name)
        if name not in members or _read_bytes(members[name]) != payload:
            raise ValueError('Beam converted view/CSV differs from its native numeric observations: ' + name)
    if expected_names != set(members):
        raise ValueError('Unexpected beam result dependency')
    # Defend source changes during parsing too, before any receipt is published.
    for row in records:
        if _row(root, row['relative']) != row:
            raise ValueError('Beam source changed during admission')
    if _row(root, MANIFEST) != manifest_pin:
        raise ValueError('Beam manifest changed during admission')
    return {'manifest':manifest, 'data':fields, 'execution':context, 'paths':paths}


def validate_metadata(view, metadata):
    if not isinstance(metadata, dict) or 'beam' not in metadata or 'beam_inspection' not in metadata:
        raise ValueError('Beam field declarations require their raw result bundle; do not discard metadata')
    bundle = load(view, descriptor(metadata['beam_inspection']))
    if bundle['manifest']['native_metadata'] != {k:v for k,v in metadata.items() if k != 'beam_inspection'}:
        raise ValueError('Beam field declarations differ from the retained bundle')
    return bundle


def explicit_manifest(path):
    """Register an explicitly selected portable bundle without guessing VTU units."""
    path = Path(path).absolute()
    if path.name != MANIFEST:
        raise ValueError('Select the retained beam_inspection.json bundle')
    reference = _row(path.parent, MANIFEST)
    view = path.parent / 'beam.pvd'
    checked = load(view, reference)
    return view, {**deepcopy(checked['manifest']['native_metadata']), 'beam_inspection':reference}


def inspect(view, *, node_id, component, load_parameter=None, reference=None):
    """Exact original-node component with native step/increment and local basis."""
    checked = load(view, reference)
    frames = checked['data']['observed']['frames']
    selected = frames[-1] if load_parameter is None else next(
        (f for f in frames if f['static']['load_parameter'] == load_parameter), None)
    if selected is None:
        raise ValueError('Select an available static load parameter, not physical seconds')
    data = channels(selected)
    if component not in data or type(node_id) is not int or node_id not in data[component]['values']:
        raise ValueError('Select an available original beam node and component')
    row = data[component]
    return {'node_id':node_id, 'component':component, 'value':row['values'][node_id],
        'unit':row['unit'], 'frame':row['frame'], 'location':'ORIGINAL_BEAM_NODES',
        'source_field':row['source_field'], 'source_component':row['source_component'],
        'static':deepcopy(selected['static']), 'axes':deepcopy(checked['data']['model']['axes']),
        'execution_status':checked['execution']['execution_status'], 'engineering_valid':False,
        'unavailable':deepcopy(checked['data']['observed']['unavailable'])}


def export_saved_run(run_folder, destination):
    """Export a new portable bundle from a sealed old run, without a solver call."""
    from .adapters.beam_fem import read_saved_run
    from .beam_results import write_post
    saved = read_saved_run(run_folder)
    if saved['model'] is None or saved['observed'] is None:
        raise ValueError('The retained run has no complete readable beam frame; keep its original logs')
    destination = Path(destination).absolute()
    if destination.exists() or destination.resolve().is_relative_to(Path(run_folder).resolve()):
        raise ValueError('Choose a new export folder outside the retained run; original results are read-only')
    artifact = write_post(destination, saved['observed'], saved['model'],
                          source_status=saved['execution']['execution_status'])
    retain(run_folder, artifact, saved['execution'], post_folder=destination)
    return destination / MANIFEST


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description='검증된 빔 결과 묶음 열기 또는 이전 계산에서 새 묶음 내보내기')
    parser.add_argument('source', type=Path, help='beam_inspection.json 또는 기존 계산 폴더')
    parser.add_argument('--export', type=Path, help='새 내보내기 폴더; solver 실행 없음')
    args = parser.parse_args(argv)
    if args.export is not None:
        print(export_saved_run(args.source, args.export))
    else:
        view, metadata = explicit_manifest(args.source)
        print(json.dumps({'view':str(view), 'time':metadata['time'], 'beam':metadata['beam']},
                         ensure_ascii=False, allow_nan=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
