"""Execute the retained separate-body contact capability through existing JobManager."""
from copy import deepcopy
from pathlib import Path
import csv
import hashlib
import json
import re
import shutil
import subprocess

from ..contact import BACKEND
from ..calculix_material import ns1_enabled, has_plasticity, field_specifications
from ..contact_deck import render, validate_model
from ..contact_steps import profile, axis as contact_axis, validate_frames
from ..execution_control import run_owned_command, check_cancelled, ExecutionCancelled, ExecutionCleanupFailed
from ..storage import check_id, save_json
from .frozen_fem import _read, _relative, _sha, _jacobian_gates, read_frd
from .fixture_field import _printed_close
from .contact_results import read_dat, write_post, CHANNELS, BASIS
from ..contact_activation import compile_states, require_contact, output_availability


def validate_snapshot(path):
    path = Path(path)
    if not path.is_absolute() or path.name != 'snapshot.json':
        raise ValueError('Contact snapshot requires an absolute registered manifest path')
    raw = _read(path, 8*1024**2)
    manifest = json.loads(raw)
    if manifest.get('kind') != 'freecad-contact-frozen' or manifest.get('schema_version') != '1':
        raise ValueError('Select the separate-body contact snapshot capability')
    if manifest.get('backend') == 'structure.codeaster.contact':
        from .contact_aster_model import validate_snapshot as validate_aster
        return validate_aster(path)
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
    model = json.loads(_read(path.parent / 'mesh.json'))
    if model.get('restart'):
        from ..dynamic_restart import MEMBERS
        required |= MEMBERS
    if set(pins) != required:
        raise ValueError('Contact snapshot has missing/unadmitted members')
    model = json.loads(_read(path.parent / 'mesh.json'))
    nodes, elements, bodies = validate_model(model)
    if model.get('restart'):
        from ..dynamic_restart import validate_members
        validate_members(path.parent, model, pins)
    rendered = render(model).encode('ascii')
    # Retained inputs written before explicit GLOBAL=YES remain immutable and
    # readable. Only that exact output-card spelling may differ; every original
    # mesh, condition, step and byte pin is still checked above.
    legacy_rendered = rendered.replace(b'*NODE FILE,GLOBAL=YES', b'*NODE FILE')
    if _read(path.parent / entry) not in (rendered, legacy_rendered):
        raise ValueError('Contact deck differs from the admitted body/material/surface/DOF definitions')
    if {row['body_id'] for row in manifest['bodies']} != set(bodies):
        raise ValueError('Snapshot body identities differ from the retained mesh')
    gates = _jacobian_gates(nodes, elements)
    gates.update(interface='independent_body_dofs', mesh_components=len(bodies),
                 stability='contact-dependent; solver convergence required; engineering UNKNOWN')
    return manifest, model, pins, gates


def _check_tie_connections(native):
    """A converged solve with omitted tied nodes is not the requested model."""
    warning = native / 'contact_WarnNodeMissTiedContact.nam'
    if warning.is_file() and any(line.strip() and not line.lstrip().startswith('*')
                                 for line in _read(warning).decode('ascii').splitlines()):
        raise ValueError('묶음으로 연결되지 않은 A면 절점이 있습니다. 원 경고를 확인하고 면 또는 허용거리를 수정하세요.')
    for log in native.glob('ccx_contact.*.log'):
        if b'no tied MPC' in _read(log):
            raise ValueError('묶음 구속 생성이 누락됐습니다. 면 또는 허용거리를 수정하세요. 원 출력은 보존됩니다.')


def _observed_adjustment(observed,receipt,original,elements):
    if receipt is None:
        return None,None
    receipt=deepcopy(receipt)
    adjusted={r['node_id'] for r in receipt['rows']}
    coordinates={n:list(observed['frd_coordinates_mm'][n] if n in adjusted else xyz) for n,xyz in original.items()}
    receipt['observed_quality']=_jacobian_gates(coordinates,elements)
    for row in receipt['rows']:
        row['observed_mm']=coordinates[row['node_id']]
        row['initial_adjustment_mm']=[a-b for a,b in zip(row['observed_mm'],row['original_mm'])]
    return coordinates,receipt


class ContactFemCalculixAdapter:
    backend, version = BACKEND, '1'

    def run(self, settings, *, output, runtime=None):
        if (not isinstance(settings, dict) or set(settings)-{'snapshot_path', 'data_id'} or
                not isinstance(settings.get('snapshot_path'), str)):
            raise ValueError('Contact run requires the registered snapshot and configured CalculiX runtime')
        if runtime and (not isinstance(runtime, dict) or set(runtime) != {'freecad_executable'}
                        or not isinstance(runtime['freecad_executable'], str)):
            raise ValueError('Native CalculiX accepts only the configured FreeCAD installation')
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
        model = manifest = pins = None
        read_nodes = adjustment = None
        observed = observed_pin = None
        dynamic_legacy = None
        tie_connected = True
        try:
            source = Path(settings['snapshot_path'])
            manifest, model, pins, gates = validate_snapshot(source)
            if manifest.get('backend') == 'structure.codeaster.contact':
                raise ValueError('비관통 입력은 Code_Aster 접촉 해석에서 실행하세요.')
            tie_connected = not any(p['draft']['normal_law'] == 'tie' for p in model['contacts'])
            retained = output / 'frozen_input'
            retained.mkdir()
            for relative, pin in pins.items():
                target = retained / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source.parent / relative, target)
                if target.stat().st_size != pin['bytes'] or _sha(target) != pin['sha256']:
                    raise ValueError('Contact input changed during capture')
            validate_snapshot(retained / 'snapshot.json')
            nodes,elements,_=validate_model(model)
            from .tie_adjustment import expected_coordinates
            read_nodes,adjustment=expected_coordinates(model,nodes,elements,output/'tie_projection')
            result.update(snapshot_id=manifest['id'], data_id=settings.get('data_id'), input_pins=pins,
                          checks=[{'name': 'contact_mesh_and_deck', 'status': 'PASS', **gates}])
            result['execution_status'] = 'FAILED'
            check_cancelled()
            from ..native_tools import calculix_executable
            executable, configuration = calculix_executable(runtime)
            executable_sha = _sha(executable)
            result['runtime'] = {'executable': str(executable), 'sha256': executable_sha,
                                 'configuration': configuration, 'build_identity': 'UNKNOWN'}
            native = output / 'solver'
            native.mkdir()
            from ..contact_execution_extensions import require_runtime
            result['runtime'].update(require_runtime(executable, native, model, run_owned_command))
            if _sha(executable) != executable_sha:
                raise ValueError('Contact executable changed during native version admission')
            deck = native / 'contact.inp'
            shutil.copyfile(retained / 'contact.inp', deck)
            from .dynamic_fem import before_run
            before_run(retained, native, model, result['runtime'], result, settings)
            solved = None
            try:
                solved = run_owned_command([str(executable), '-i', deck.stem], native, 'ccx_contact')
            finally:
                from ..dynamic_execution import capture_terminal
                capture_terminal(output, model, manifest, pins, result, completed=solved)
            if any(p['draft']['normal_law'] == 'tie' for p in model['contacts']):
                _check_tie_connections(native)
                tie_connected = True
            if solved.returncode:
                raise RuntimeError('CalculiX contact failed; solver diagnostics and raw output retained')
            check_cancelled()
            for relative, pin in pins.items():
                if _sha(source.parent / relative) != pin['sha256'] or _sha(retained / relative) != pin['sha256']:
                    raise ValueError('Contact input changed during the attempt')
            if _sha(deck) != pins['contact.inp']['sha256'] or _sha(executable) != executable_sha:
                raise ValueError('Contact executable/deck changed during the attempt')
            nodes, elements, bodies = validate_model(model)
            contact_pairs = [p for p in model['contacts'] if p['draft']['normal_law'] != 'tie']
            has_tie = len(contact_pairs) != len(model['contacts'])
            material_indices = {body: index for index, body in enumerate(sorted(bodies), 1)}
            materials = {'names': ['M'+str(index) for index in material_indices.values()] +
                                   ['INT'+pair['object_id'].upper() for pair in contact_pairs],
                         'elements': {row['element_id']: 'M'+str(material_indices[row['body_id']]) for row in model['elements']}}
            from ..dynamic_model import enabled as dynamic_enabled
            from ..dynamic_native_stream import read_dynamic_frd, frame_catalog, release
            dynamic = dynamic_enabled(model)
            from .pretension_results import solver_mesh as pretension_solver_mesh
            post_model, read_nodes, elements, pretension_copies = pretension_solver_mesh(model, read_nodes, elements)
            native_reader = read_dynamic_frd if dynamic else read_frd
            observed = native_reader(deck.with_suffix('.frd'), read_nodes, elements, contact_materials=materials,
                                contact_profile=profile(model), require_contact=require_contact(model))
            from ..dynamic_result_store import file_pin
            observed_pin = file_pin(output, deck.with_suffix('.frd'))
            validate_frames(model, observed)
            frames = observed['frames']
            from ..dynamic_results import validate_requested
            validate_requested(model, frames)
            if ns1_enabled(model) or model.get('pretension_sections'):
                if observed['native_version'] != '2.22':
                    raise ValueError('NS1 requires CalculiX 2.22 result output.')
                required = {'STRESS', 'TOSTRAIN', 'FORC'} | ({'PE'} if has_plasticity(model) else set())
                missing = sorted({name for frame in frame_catalog(frames) for name in required - set(frame['fields'])})
                if missing:
                    raise ValueError('Requested NS1 fields were not output: ' + ', '.join(missing))
            coordinates,adjustment=_observed_adjustment(observed,adjustment,nodes,elements)
            if has_tie and any(not {'DISP', 'STRESS', 'FORC'} <= set(frame['fields']) for frame in frame_catalog(frames)):
                raise ValueError('묶음 접촉의 변위·응력·절점 힘 출력이 누락됐습니다. 원 출력은 보존됩니다.')
            if profile(model) or ns1_enabled(model):
                from ..contact_status import read_status, require_converged
                progress=result.get('increment_history') or read_status(deck.with_suffix('.sta'),model)
                require_converged(frames,progress)
                result['increment_history']=progress
            pair_results = read_dat(deck.with_suffix('.dat'), model['contacts'], frames, activation=compile_states(model))
            from .pretension_results import read as read_pretension, responses as pretension_responses
            pretension_rows = read_pretension(deck.with_suffix('.dat'), model, frames)
            if model.get('pretension_sections'):
                from .pretension_results import attach_nodal_resultants
                attach_nodal_resultants(model, pretension_rows, frames)
            if model.get('pretension_sections'):
                save_json(output/'pretension_resultants.json', {'rows':pretension_rows, 'node_copies':pretension_copies,
                    'method':'native SOF stress-extrapolation section integral; raw RP U/RF separate',
                    'reference_U1':'generalized section differential, not bolt total elastic extension',
                    'source_model':'frozen_input/mesh.json', 'engineering_release':'UNKNOWN'})
            save_json(output / 'pair_resultants.json', {'snapshot_id': manifest['id'], 'rows': pair_results,
                'request_order': ['CF', 'CFN', 'CFS'], 'force_units': 'N', 'moment_units': 'N mm',
                'axis': contact_axis(model), 'area_units': 'mm^2',
                'contact_state_profile': compile_states(model),
                'missing_policy': 'Inactive pair outputs are not requested; absence is not a measured zero.'})
            with (output / 'pair_resultants.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.writer(stream)
                writer.writerow(['pair', 'quantity', 'step', 'increment',
                    'time_s' if contact_axis(model)['unit']=='s' else 'load_parameter',
                    'Fx_N','Fy_N','Fz_N','Mx_Nmm','My_Nmm','Mz_Nmm','area_mm2','normal_projection_N','shear_size_N','quality'])
                for row in pair_results:
                    values = [*row['force_N'], *row['moment_origin_Nmm'], row['area_mm2'],
                              row['normal_projection_N'], row['shear_size_N']]
                    writer.writerow([row['pair_id'],row['quantity'],row['static']['step'],row['static']['increment'],
                        row['static']['load_parameter'], *['' if value is None else value for value in values],
                        'native_nonfinite' if any(value is None for value in values) else 'finite_raw'])
            legacy = dict(solver_coordinates=coordinates, adjustment=adjustment, provenance={
                'snapshot_id': manifest['id'], 'snapshot_sha256': pins['snapshot.json']['sha256'],
                'raw_frd_sha256': _sha(deck.with_suffix('.frd')), 'raw_dat_sha256': _sha(deck.with_suffix('.dat')) if deck.with_suffix('.dat').is_file() else None})
            if dynamic:
                dynamic_legacy = {'pair_results': pair_results, **legacy}
                metadata = None
            else:
                metadata = write_post(output / 'post', post_model, frames, pair_results, **legacy)
                if pretension_copies:
                    metadata['pretension_geometry']={'basis':'CalculiX 2.22 explicit native partner-node map',
                        'node_copies':pretension_copies,'original_mesh_unchanged':True}
            final = frames[-1]
            if model.get('pretension_sections'):
                nodes = read_nodes
            ids = sorted(nodes)
            field_clock = ({'axis':contact_axis(model), 'coordinate':final['static']['load_parameter'],
                            'step_location':deepcopy(final.get('step_location'))} if profile(model) or ns1_enabled(model) else {})
            responses = {}
            final_contact = final['fields'].get('CONTACT', {})
            final_availability = output_availability(model, final['static']['step'])
            for j, key in enumerate(CHANNELS if contact_pairs else ()):
                covered = [n for n in ids if n in final_contact and final_contact[n][j] is not None]
                responses[key] = {'kind':'field', 'unit':'mm' if j < 3 else 'MPa',
                    'value':[final_contact[n][j] for n in covered], 'component':key,
                    'location':'calculix_export_nodes', 'reduction':'none',
                    'metadata': {'node_ids':covered, 'association':'POINTS', 'static':final['static'], **field_clock,
                        'missing_or_invalid_node_ids':[n for n in ids if n not in set(covered)],
                        'raw_frame':('dynamic-post' if dynamic else 'post')+'/frame'+str(len(frames)).zfill(4)+'.json',
                        'basis':BASIS, 'coverage':'actual_finite_native_rows', 'pair_scope':'shared_nodal_projection',
                        'pair_output_availability': final_availability,
                        'contact_state':'UNKNOWN', 'raw_sign':'unchanged'}}
            responses['displacement'] = {'kind':'field','unit':'mm',
                'value':[final['fields']['DISP'][n] for n in ids], 'component':'VECTOR',
                'location':'calculix_export_nodes','reduction':'none',
                'metadata':{'node_ids':ids,'association':'POINTS','static':final['static'], **field_clock,
                            'frame':'FREECAD_DOCUMENT_GLOBAL'}}
            if has_tie or ns1_enabled(model) or model.get('pretension_sections'):
                for native, prefix, unit, measure, components in field_specifications(model):
                    if native not in final['fields']:
                        continue
                    key = {'FORC': 'nodal_force', 'STRESS': 'stress', 'TOSTRAIN': 'total_strain', 'PE': 'PEEQ'}[native]
                    responses[key] = {'kind':'field', 'unit':unit,
                        'value':[final['fields'][native][n][0] if native == 'PE' else final['fields'][native][n] for n in ids],
                        'component': 'SCALAR' if native == 'PE' else ('VECTOR' if native == 'FORC' else 'TENSOR'),
                        'location':'calculix_export_nodes', 'reduction':'none',
                        'metadata':{'node_ids':ids, 'association':'POINTS', 'static':final['static'], **field_clock,
                            'frame':'FREECAD_DOCUMENT_GLOBAL', 'component_names':list(components),
                            'measure': measure, 'native_field': native,
                            'meaning':'native_RF_nodal_force_including_applied_loads' if native == 'FORC' else measure,
                            'shear_convention': 'tensor_shear_not_engineering_shear' if native == 'TOSTRAIN' else None}}
            for pair in contact_pairs:
                for quantity in ('CF','CFN','CFS'):
                    rows = [row for row in pair_results if row['pair_id']==pair['object_id'] and row['quantity']==quantity]
                    for axis, component in enumerate('XYZ'):
                        valid = [row for row in rows if row['force_N'][axis] is not None]
                        # Failed/nonfinite rows remain in raw table with reasons; never filled with zero.
                        responses[pair['object_id']+'.'+quantity+'.F'+component] = {
                            'kind':'series','unit':'N','value':[row['force_N'][axis] for row in valid],
                            'axes':[{'name':contact_axis(model)['name'],'unit':contact_axis(model)['unit'],'values':[row['static']['load_parameter'] for row in valid]}],
                            'component':'F'+component, 'location':pair['object_id'],'reduction':'none',
                            'metadata':{'axis_semantics':contact_axis(model)['semantics'],'quantity':quantity,
                                'frame':'FREECAD_DOCUMENT_GLOBAL','raw_rows':'pair_resultants.json',
                                'frame_availability':[{'static': f['static'], 'output': output_availability(model, f['static']['step'])[pair['object_id']]}
                                                      for f in frame_catalog(frames)],
                                'excluded_nonfinite_rows':len(rows)-len(valid)}}
            responses.update(pretension_responses(model, pretension_rows, frames))
            artifact = output / 'post' / 'contact.pvd'
            result.update(execution_status='SUCCEEDED', responses=responses, native_version=observed['native_version'],
                **({'post_artifact': {'relative':'post/contact.pvd','bytes':artifact.stat().st_size,'sha256':_sha(artifact),
                               'native_metadata':metadata}} if not dynamic else {}),
                contact_outputs={'raw_frd':'solver/contact.frd','raw_dat':'solver/contact.dat',
                    'pair_table':'pair_resultants.csv','pair_detail':'pair_resultants.json',
                    'body_map':('dynamic-post' if dynamic else 'post')+'/body_map.json','frame_count':len(frames),'active_state':'UNKNOWN'})
            from .initial_field_results import augment
            augment(result, output, model, frames)
        except ExecutionCleanupFailed:
            raise
        except ExecutionCancelled as error:
            result.update(execution_status='CANCELLED', responses={}, diagnostics={'reason':str(error)})
        except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            result.update(responses={}, diagnostics={'type':type(error).__name__,'reason':str(error)})
        if model is not None and manifest is not None:
            result['executed_setup']={'analysis_id':manifest.get('analysis_id'), 'solver_id':manifest.get('solver_id'),
                'snapshot_id':manifest['id'],'axis':contact_axis(model),
                'program':model.get('analysis_steps'), 'step':deepcopy(model['step']),
                'materials':deepcopy(model['materials']),
                'penalty_contact':any(p['draft']['normal_law']=='linear' for p in model['contacts']),
                'unavailable_controls': ['STATIC,STABILIZE (CalculiX 2.22)', 'generic Newton line search'],
                'conditions':[{'object_id':r['object_id'],'label':r.get('label',r['object_id']),
                               'type':r['type'],'body_id':r['body_id']} for r in model.get('conditions',[])]}
            status_path=output/'solver/contact.sta'
            if status_path.is_file():
                try:
                    from ..contact_status import read_status
                    progress=result.get('increment_history') or read_status(status_path,model)
                    result['increment_history']=progress
                    result['failure_location']=progress['failure_location']
                except (ValueError,OSError,KeyError,UnicodeError) as error:
                    result.setdefault('diagnostics',{})['increment_readback']=str(error)
            if not tie_connected and result.get('increment_history'):
                try:
                    _check_tie_connections(output/'solver')
                    tie_connected = True
                except (ValueError,OSError,UnicodeError) as error:
                    result.setdefault('diagnostics',{})['tie_readback']=str(error)
            if tie_connected and result['execution_status'] in ('FAILED','CANCELLED') and result.get('increment_history'):
                try:
                    # Owned process is terminal before this point. Read retained
                    # committed increments only; no solver/retry/resume is invoked.
                    from ..contact_status import retained_prefix
                    if pins is None:
                        raise ValueError('No admitted retained input')
                    validate_snapshot(output/'frozen_input/snapshot.json')
                    if any(_sha(output/'frozen_input'/name)!=pin['sha256'] for name,pin in pins.items()):
                        raise ValueError('Frozen input changed before partial readback')
                    if _sha(output/'solver/contact.inp')!=pins['contact.inp']['sha256']:
                        raise ValueError('Executed deck changed before partial readback')
                    if 'runtime' not in result or _sha(Path(result['runtime']['executable']))!=result['runtime']['sha256']:
                        raise ValueError('Executed runtime changed before partial readback')
                    nodes,elements,bodies=validate_model(model)
                    from .pretension_results import solver_mesh as pretension_solver_mesh
                    partial_model, partial_nodes, elements, pretension_copies = pretension_solver_mesh(model, nodes, elements)
                    if model.get('pretension_sections'):
                        nodes = read_nodes = partial_nodes
                    indices={body:i for i,body in enumerate(sorted(bodies),1)}
                    materials={'names':['M'+str(i) for i in indices.values()]+
                        ['INT'+p['object_id'].upper() for p in model['contacts'] if p['draft']['normal_law'] != 'tie'],
                        'elements':{r['element_id']:'M'+str(indices[r['body_id']]) for r in model['elements']}}
                    from ..dynamic_model import enabled as dynamic_enabled
                    from ..dynamic_native_stream import release
                    release(observed)
                    dynamic = dynamic_enabled(model)
                    observed=retained_prefix(output/'solver/contact.frd',output/'partial/committed.frd',
                        read_nodes if read_nodes is not None else nodes,elements,materials,model,result['increment_history'],
                        streaming=dynamic)
                    from ..dynamic_result_store import file_pin
                    observed_pin = file_pin(output, output/'partial/committed.frd')
                    coordinates,partial_adjustment=_observed_adjustment(observed,adjustment,nodes,elements)
                    frames=observed['frames']
                    pairs=read_dat(output/'solver/contact.dat',model['contacts'],frames,prefix=True,activation=compile_states(model))
                    legacy=dict(solver_coordinates=coordinates,adjustment=partial_adjustment,
                        execution={'status':result['execution_status'],'complete_analysis':False,'scope':'CONVERGED_PREFIX',
                                   'frd_retention':observed['retention']},provenance={
                        'snapshot_id':manifest['id'],'snapshot_sha256':pins['snapshot.json']['sha256'],
                        'raw_frd_sha256':_sha(output/'solver/contact.frd'),'raw_dat_sha256':_sha(output/'solver/contact.dat') if (output/'solver/contact.dat').is_file() else None})
                    if dynamic:
                        dynamic_legacy = {'pair_results': pairs, **legacy}
                    else:
                        metadata=write_post(output/'partial/post',partial_model,frames,pairs,**legacy)
                        if model.get('pretension_sections'):
                            metadata['pretension_geometry']={'basis':'CalculiX 2.22 explicit native partner-node map',
                                'node_copies':pretension_copies,'original_mesh_unchanged':True}
                            try:
                                from .pretension_results import read as read_pretension, attach_nodal_resultants, responses as pretension_responses
                                rows=read_pretension(output/'solver/contact.dat',model,frames,prefix=True)
                                attach_nodal_resultants(model,rows,frames)
                                save_json(output/'partial/pretension_resultants.json',{'rows':rows,'node_copies':pretension_copies,
                                    'source_execution_status':result['execution_status'],'complete_analysis':False})
                                result['responses'].update(pretension_responses(model,rows,frames,raw_rows='partial/pretension_resultants.json'))
                            except (ValueError,OSError,KeyError,TypeError,IndexError,UnicodeError) as error:
                                result.setdefault('diagnostics',{})['pretension_partial_readback']=str(error)

                    artifact=output/'partial/post/contact.pvd'
                    result['partial_result']={'status':'CONVERGED_PREFIX','frame_count':len(frames),
                        'complete_analysis':False,'status_source':result['increment_history']['source'],
                        'frd_retention':observed['retention']}
                    if not dynamic:
                        result['post_artifact']={'relative':'partial/post/contact.pvd','bytes':artifact.stat().st_size,
                            'sha256':_sha(artifact),'native_metadata':metadata}
                except (ExecutionCancelled,ValueError,OSError,KeyError,TypeError,IndexError,UnicodeError) as error:
                    if isinstance(error, ExecutionCancelled):
                        result['execution_status']='CANCELLED'
                        result['responses']={}
                    result.setdefault('diagnostics',{})['partial_readback']=str(error)
        if result.get('executed_setup'):
            from ..contact_status import iteration_history
            result['convergence_history'] = iteration_history(output, result)
            save_json(output / 'convergence_history.json', result['convergence_history'])
        result['limitations'] = [
            'Static steps use cumulative dimensionless load parameter; dynamic-only steps use seconds. Mixed procedures and within-step contact activation are not supported',
            'FRD contact is native projected/averaged nodal output, not pair-specific integration point output',
            'Raw signs unchanged; zero/missing COPEN or pressure does not determine active contact',
            'GeomGap is a labelled linear subdivision of deformed quadratic faces, not solver-effective clearance',
            'Exact tangential basis vectors, active-state classification and engineering release remain UNKNOWN']
        if model is not None and manifest is not None and pins is not None:
            from .dynamic_fem import finish
            from ..dynamic_native_stream import release
            try:
                finish(output, model, manifest, pins, result, parsed=observed, parsed_pin=observed_pin,
                       legacy_context=dynamic_legacy)
            finally:
                release(observed)
        result['artifacts'] = [{'relative':p.relative_to(output).as_posix(), 'path':p.relative_to(output).as_posix(),
                               'bytes':p.stat().st_size,'sha256':_sha(p)}
                               for p in sorted(output.rglob('*')) if p.is_file() and not p.is_symlink()
                               and p.name != 'contact_execution.json'
                               and not any(part.startswith(('.caelab-', '.dynamic-energy-')) for part in p.relative_to(output).parts)]
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
    from ..dynamic_model import enabled as dynamic_enabled
    _, source_model, _, _ = validate_snapshot(attempt / 'frozen_input/snapshot.json')
    if dynamic_enabled(source_model):
        from ..dynamic_recovery import reprocess
        return reprocess(attempt, output)
    if record.get('execution_status') != 'SUCCEEDED':
        raise ValueError('Post regeneration requires an already parsed successful contact attempt')
    manifest, model, input_pins, _ = validate_snapshot(attempt / 'frozen_input' / 'snapshot.json')
    entries = {row['relative']: row for row in record['artifacts']}
    required = ['frozen_input/' + name for name in input_pins] + ['solver/contact.frd']
    has_adjustment=any(p['draft']['normal_law']=='tie' and p['draft'].get('tie_adjust',False) for p in model['contacts'])
    if has_adjustment:
        required += ['tie_projection/expected.json','tie_projection/points.json','tie_projection/projected.json']
    stages = profile(model)
    needs_dat = any(require_contact(model, row['index']) for row in stages['steps']) if stages else require_contact(model)
    if needs_dat or 'solver/contact.dat' in entries:
        required.append('solver/contact.dat')
    if profile(model) or ns1_enabled(model):
        required.append('solver/contact.sta')
    source_pins = {}
    for relative in required:
        pin = entries.get(relative)
        data = _read(attempt / relative)
        if (pin is None or len(data) != pin['bytes'] or
                hashlib.sha256(data).hexdigest() != pin['sha256']):
            raise ValueError('Retained contact source differs from the attempt: ' + relative)
        source_pins[relative] = {'bytes': pin['bytes'], 'sha256': pin['sha256']}
    nodes, elements, bodies = validate_model(model)
    from .tie_adjustment import retained_coordinates
    read_nodes,adjustment=retained_coordinates(model,nodes,elements,attempt/'tie_projection') if has_adjustment else (nodes,None)
    indices = {body: index for index, body in enumerate(sorted(bodies), 1)}
    materials = {'names': ['M' + str(i) for i in indices.values()] +
                           ['INT' + pair['object_id'].upper() for pair in model['contacts'] if pair['draft']['normal_law'] != 'tie'],
                 'elements': {row['element_id']: 'M' + str(indices[row['body_id']])
                              for row in model['elements']}}
    observed = read_frd(attempt / 'solver/contact.frd', read_nodes, elements, contact_materials=materials,
                        contact_profile=profile(model), require_contact=require_contact(model))
    validate_frames(model, observed)
    frames = observed['frames']
    coordinates,adjustment=_observed_adjustment(observed,adjustment,nodes,elements)
    if profile(model) or ns1_enabled(model):
        from ..contact_status import read_status, require_converged
        require_converged(frames, read_status(attempt / 'solver/contact.sta', model))
    pairs = read_dat(attempt / 'solver/contact.dat', model['contacts'], frames, activation=compile_states(model))
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = write_post(output, model, frames, pairs, solver_coordinates=coordinates,adjustment=adjustment,provenance={
        'snapshot_id': manifest['id'], 'snapshot_sha256': input_pins['snapshot.json']['sha256'],
        'raw_frd_sha256': source_pins['solver/contact.frd']['sha256'],
        'raw_dat_sha256': source_pins.get('solver/contact.dat', {}).get('sha256'),
        'source_record_sha256': hashlib.sha256(record_bytes).hexdigest()})
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
