"""Execute the retained separate-body contact capability through existing JobManager."""
from pathlib import Path
import csv
import hashlib
import json
import re
import shutil
import subprocess

from ..contact import BACKEND
from ..contact_deck import render, validate_model
from ..execution_control import run_owned_command, check_cancelled, ExecutionCancelled, ExecutionCleanupFailed
from ..storage import check_id, save_json
from .frozen_fem import _read, _relative, _sha, _jacobian_gates, read_frd
from .fixture_field import _printed_close
from .contact_results import read_dat, write_post, CHANNELS, BASIS


def validate_snapshot(path):
    path = Path(path)
    if not path.is_absolute() or path.name != 'snapshot.json':
        raise ValueError('Contact snapshot requires an absolute registered manifest path')
    raw = _read(path, 8*1024**2)
    manifest = json.loads(raw)
    if manifest.get('kind') != 'freecad-contact-frozen' or manifest.get('schema_version') != '1':
        raise ValueError('Select the separate-body contact snapshot capability')
    check_id(manifest['id'])
    entry = _relative(manifest['input_file'])
    if entry != 'contact.inp':
        raise ValueError('Contact snapshot requires one unsplit contact.inp')
    pins = {'snapshot.json': {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}
    for row in manifest['files']:
        relative = _relative(row['relative'])
        if (relative in pins or type(row['bytes']) is not int or row['bytes'] <= 0 or
                not re.fullmatch('[a-f0-9]{64}', row['sha256'])):
            raise ValueError('Invalid/duplicate contact member pin')
        data = _read(path.parent / relative)
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Contact source changed: ' + relative)
        pins[relative] = {'bytes': row['bytes'], 'sha256': row['sha256']}
    required = {'snapshot.json', 'editable.FCStd', 'mesh.json', entry}
    if manifest.get('editable_project') == 'editable.caepre':
        required.add('editable.caepre')
    elif manifest.get('editable_project') is not None:
        raise ValueError('Unsupported editable contact project member')
    if set(pins) != required:
        raise ValueError('Contact snapshot has missing/unadmitted members')
    model = json.loads(_read(path.parent / 'mesh.json'))
    nodes, elements, bodies = validate_model(model)
    if _read(path.parent / entry) != render(model).encode('ascii'):
        raise ValueError('Contact deck differs from the admitted body/material/surface/DOF definitions')
    if {row['body_id'] for row in manifest['bodies']} != set(bodies):
        raise ValueError('Snapshot body identities differ from the retained mesh')
    gates = _jacobian_gates(nodes, elements)
    gates.update(interface='independent_body_dofs', mesh_components=len(bodies),
                 stability='contact-dependent; solver convergence required; engineering UNKNOWN')
    return manifest, model, pins, gates


class ContactFemCalculixAdapter:
    backend, version = BACKEND, '1'

    def run(self, settings, *, output, runtime=None):
        if (not isinstance(settings, dict) or set(settings)-{'snapshot_path', 'data_id'} or
                not isinstance(settings.get('snapshot_path'), str) or runtime):
            raise ValueError('Contact run requires the registered snapshot and configured CalculiX runtime')
        if 'data_id' in settings:
            check_id(settings['data_id'])
        output = Path(output).absolute()
        if any(p.is_symlink() for p in (output, *output.parents)):
            raise ValueError('Contact output must be a new regular directory')
        output.mkdir(parents=True, exist_ok=True)
        if any(output.iterdir()):
            raise ValueError('Contact run refuses to overwrite an existing attempt')
        result = {'execution_status': 'REJECTED', 'responses': {}, 'checks': [],
            'qualification': 'UNKNOWN', 'decision': 'NOT_RELEASED', 'engineering_valid': False,
            'diagnostics': {}, 'artifacts': []}
        try:
            source = Path(settings['snapshot_path'])
            manifest, model, pins, gates = validate_snapshot(source)
            retained = output / 'frozen_input'
            retained.mkdir()
            for relative, pin in pins.items():
                target = retained / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source.parent / relative, target)
                if target.stat().st_size != pin['bytes'] or _sha(target) != pin['sha256']:
                    raise ValueError('Contact input changed during capture')
            validate_snapshot(retained / 'snapshot.json')
            result.update(snapshot_id=manifest['id'], data_id=settings.get('data_id'), input_pins=pins,
                          checks=[{'name': 'contact_mesh_and_deck', 'status': 'PASS', **gates}])
            result['execution_status'] = 'FAILED'
            check_cancelled()
            command = shutil.which('ccx')
            if not command:
                raise RuntimeError('CalculiX requires ccx on configured PATH')
            executable = Path(command).resolve(strict=True)
            executable_sha = _sha(executable)
            result['runtime'] = {'executable': str(executable), 'sha256': executable_sha,
                                 'configuration': 'configured PATH', 'build_identity': 'UNKNOWN'}
            native = output / 'solver'
            native.mkdir()
            deck = native / 'contact.inp'
            shutil.copyfile(retained / 'contact.inp', deck)
            solved = run_owned_command([str(executable), '-i', deck.stem], native, 'ccx_contact')
            if solved.returncode:
                raise RuntimeError('CalculiX contact failed; solver diagnostics and raw output retained')
            check_cancelled()
            for relative, pin in pins.items():
                if _sha(source.parent / relative) != pin['sha256'] or _sha(retained / relative) != pin['sha256']:
                    raise ValueError('Contact input changed during the attempt')
            if _sha(deck) != pins['contact.inp']['sha256'] or _sha(executable) != executable_sha:
                raise ValueError('Contact executable/deck changed during the attempt')
            nodes, elements, bodies = validate_model(model)
            material_indices = {body: index for index, body in enumerate(sorted(bodies), 1)}
            materials = {'names': ['M'+str(index) for index in material_indices.values()] +
                                   ['INT'+pair['object_id'].upper() for pair in model['contacts']],
                         'elements': {row['element_id']: 'M'+str(material_indices[row['body_id']]) for row in model['elements']}}
            observed = read_frd(deck.with_suffix('.frd'), nodes, elements, contact_materials=materials)
            if not _printed_close(observed['load_parameter_token'], model['step']['period']):
                raise ValueError('Contact result has not reached the retained final load parameter')
            frames = observed['frames']
            pair_results = read_dat(deck.with_suffix('.dat'), model['contacts'], frames)
            save_json(output / 'pair_resultants.json', {'snapshot_id': manifest['id'], 'rows': pair_results,
                'request_order': ['CF', 'CFN', 'CFS'], 'force_units': 'N', 'moment_units': 'N mm',
                'axis': 'static_load_parameter', 'area_units': 'mm^2'})
            with (output / 'pair_resultants.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.writer(stream)
                writer.writerow(['pair', 'quantity', 'step', 'increment', 'load_parameter',
                    'Fx_N','Fy_N','Fz_N','Mx_Nmm','My_Nmm','Mz_Nmm','area_mm2','normal_projection_N','shear_size_N','quality'])
                for row in pair_results:
                    values = [*row['force_N'], *row['moment_origin_Nmm'], row['area_mm2'],
                              row['normal_projection_N'], row['shear_size_N']]
                    writer.writerow([row['pair_id'],row['quantity'],row['static']['step'],row['static']['increment'],
                        row['static']['load_parameter'], *['' if value is None else value for value in values],
                        'native_nonfinite' if any(value is None for value in values) else 'finite_raw'])
            metadata = write_post(output / 'post', model, frames, pair_results)
            final = frames[-1]
            ids = sorted(nodes)
            responses = {}
            for j, key in enumerate(CHANNELS):
                covered = [n for n in ids if n in final['fields']['CONTACT'] and final['fields']['CONTACT'][n][j] is not None]
                responses[key] = {'kind':'field', 'unit':'mm' if j < 3 else 'MPa',
                    'value':[final['fields']['CONTACT'][n][j] for n in covered], 'component':key,
                    'location':'calculix_export_nodes', 'reduction':'none',
                    'metadata': {'node_ids':covered, 'association':'POINTS', 'static':final['static'],
                        'missing_or_invalid_node_ids':[n for n in ids if n not in set(covered)],
                        'raw_frame':'post/frame'+str(len(frames)).zfill(4)+'.json',
                        'basis':BASIS, 'coverage':'actual_finite_native_rows', 'pair_scope':'shared_nodal_projection',
                        'contact_state':'UNKNOWN', 'raw_sign':'unchanged'}}
            responses['displacement'] = {'kind':'field','unit':'mm',
                'value':[final['fields']['DISP'][n] for n in ids], 'component':'VECTOR',
                'location':'calculix_export_nodes','reduction':'none',
                'metadata':{'node_ids':ids,'association':'POINTS','static':final['static'],
                            'frame':'FREECAD_DOCUMENT_GLOBAL'}}
            for pair in model['contacts']:
                for quantity in ('CF','CFN','CFS'):
                    rows = [row for row in pair_results if row['pair_id']==pair['object_id'] and row['quantity']==quantity]
                    for axis, component in enumerate('XYZ'):
                        valid = [row for row in rows if row['force_N'][axis] is not None]
                        # Failed/nonfinite rows remain in raw table with reasons; never filled with zero.
                        responses[pair['object_id']+'.'+quantity+'.F'+component] = {
                            'kind':'series','unit':'N','value':[row['force_N'][axis] for row in valid],
                            'axes':[{'name':'load_parameter','unit':'1','values':[row['static']['load_parameter'] for row in valid]}],
                            'component':'F'+component, 'location':pair['object_id'],'reduction':'none',
                            'metadata':{'axis_semantics':'STATIC_LOAD_PARAMETER','quantity':quantity,
                                'frame':'FREECAD_DOCUMENT_GLOBAL','raw_rows':'pair_resultants.json',
                                'excluded_nonfinite_rows':len(rows)-len(valid)}}
            artifact = output / 'post' / 'contact.pvd'
            result.update(execution_status='SUCCEEDED', responses=responses, native_version=observed['native_version'],
                post_artifact={'relative':'post/contact.pvd','bytes':artifact.stat().st_size,'sha256':_sha(artifact),
                               'native_metadata':metadata},
                contact_outputs={'raw_frd':'solver/contact.frd','raw_dat':'solver/contact.dat',
                    'pair_table':'pair_resultants.csv','pair_detail':'pair_resultants.json',
                    'body_map':'post/body_map.json','frame_count':len(frames),'active_state':'UNKNOWN'})
        except ExecutionCleanupFailed:
            raise
        except ExecutionCancelled as error:
            result.update(execution_status='CANCELLED', responses={}, diagnostics={'reason':str(error)})
        except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            result.update(responses={}, diagnostics={'type':type(error).__name__,'reason':str(error)})
        result['limitations'] = [
            'Static load parameter is not physical seconds; one step, no prescribed activation interval',
            'FRD contact is native projected/averaged nodal output, not pair-specific integration point output',
            'Raw signs unchanged; zero/missing COPEN or pressure does not determine active contact',
            'GeomGap is a labelled linear subdivision of deformed quadratic faces, not solver-effective clearance',
            'Exact tangential basis vectors, active-state classification and engineering release remain UNKNOWN']
        result['artifacts'] = [{'relative':p.relative_to(output).as_posix(),'bytes':p.stat().st_size,'sha256':_sha(p)}
                               for p in sorted(output.rglob('*')) if p.is_file() and not p.is_symlink()]
        save_json(output / 'contact_execution.json', result)
        return result



def regenerate_post(attempt, output):
    """Reparse pinned retained outputs into a new Post directory; never execute ccx."""
    attempt = Path(attempt).resolve(strict=True)
    output = Path(output).resolve()
    if output.exists() or output == attempt or output.is_relative_to(attempt):
        raise ValueError('Choose a new Post directory outside the retained attempt')
    record_path = attempt / 'contact_execution.json'
    record_bytes = _read(record_path)
    record = json.loads(record_bytes)
    if record.get('execution_status') != 'SUCCEEDED':
        raise ValueError('Post regeneration requires an already parsed successful contact attempt')
    manifest, model, input_pins, _ = validate_snapshot(attempt / 'frozen_input' / 'snapshot.json')
    entries = {row['relative']: row for row in record['artifacts']}
    required = ['frozen_input/' + name for name in input_pins] + ['solver/contact.frd', 'solver/contact.dat']
    source_pins = {}
    for relative in required:
        pin = entries.get(relative)
        data = _read(attempt / relative)
        if (pin is None or len(data) != pin['bytes'] or
                hashlib.sha256(data).hexdigest() != pin['sha256']):
            raise ValueError('Retained contact source differs from the attempt: ' + relative)
        source_pins[relative] = {'bytes': pin['bytes'], 'sha256': pin['sha256']}
    nodes, elements, bodies = validate_model(model)
    indices = {body: index for index, body in enumerate(sorted(bodies), 1)}
    materials = {'names': ['M' + str(i) for i in indices.values()] +
                           ['INT' + pair['object_id'].upper() for pair in model['contacts']],
                 'elements': {row['element_id']: 'M' + str(indices[row['body_id']])
                              for row in model['elements']}}
    observed = read_frd(attempt / 'solver/contact.frd', nodes, elements, contact_materials=materials)
    if not _printed_close(observed['load_parameter_token'], model['step']['period']):
        raise ValueError('Retained contact result has not reached its final load parameter')
    frames = observed['frames']
    pairs = read_dat(attempt / 'solver/contact.dat', model['contacts'], frames)
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = write_post(output, model, frames, pairs)
    for relative, pin in source_pins.items():
        if _sha(attempt / relative) != pin['sha256']:
            raise ValueError('Retained source changed during Post regeneration')
    if _read(record_path) != record_bytes:
        raise ValueError('Attempt record changed during Post regeneration')
    artifact = output / 'contact.pvd'
    receipt = {'kind': 'contact_post_regeneration', 'source_attempt': str(attempt),
        'snapshot_id': manifest['id'], 'source_record_sha256': hashlib.sha256(record_bytes).hexdigest(),
        'source_pins': source_pins, 'solver_execution': 'NOT_PERFORMED',
        'frame_count': len(frames), 'native_version': observed['native_version'],
        'post_artifact': {'relative': 'contact.pvd', 'bytes': artifact.stat().st_size,
                          'sha256': _sha(artifact), 'native_metadata': metadata},
        'qualification': 'UNKNOWN', 'decision': 'NOT_RELEASED'}
    save_json(output / 'post_regeneration.json', receipt)
    return receipt


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description='Rebuild contact Post files from an existing retained attempt; no solver execution.',
        allow_abbrev=False)
    parser.add_argument('--rebuild-post-from', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = regenerate_post(args.rebuild_post_from, args.output)
    print(json.dumps({'output': str(args.output.resolve()), 'frame_count': receipt['frame_count'],
                      'solver_execution': receipt['solver_execution']}, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
