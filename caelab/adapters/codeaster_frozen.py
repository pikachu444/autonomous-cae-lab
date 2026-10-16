"""Run a checked FreeCAD single-solid snapshot with the existing Aster runtime.

The native CalculiX writer remains the source of mesh/Fixed/Force selection.
This adapter translates those admitted values; it does not remesh or select CAD.
"""
from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path
from xml.etree import ElementTree as ET

from . import codeaster_frozen_worker as worker
from . import codeaster_elasticity as native
from .codeaster_execution import process_budgets
from .frozen_fem import validate_snapshot, _read, _sha
from ..execution_control import check_cancelled, ExecutionCancelled, ExecutionCleanupFailed
from ..storage import check_id, save_json
from .vtu import write_vtu, data_array


WORKER = Path(worker.__file__).resolve()
HELPER = WORKER.with_name('codeaster_worker.py')
GEOMETRY = WORKER.with_name('fixture_assembly_field_geometry.py')
LIMITATIONS = ['One connected C3D10 solid; isotropic linear elasticity; full Fixed and resolved nodal Force only',
    'Contact, plasticity, geometric nonlinearity, shell, beam and transient snapshots are not admitted',
    'Static load parameter is not physical time; stresses are native TETRA10 FPG5 integration-point values',
    'No mesh accuracy, material qualification or engineering release is established']


def _source_check(source, retained, pins):
    for relative,pin in pins.items():
        for root in (source.parent,retained):
            data = _read(root/relative)
            if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
                raise ValueError('Frozen source changed: '+relative)


def prepare_input(source, output):
    """Prepare native files before runtime lookup, preserving editable source."""
    manifest,mesh,pins,gates = validate_snapshot(source)
    retained = output/'frozen_input'
    retained.mkdir()
    for relative in pins:
        target = retained/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(_read(source.parent/relative))
    _source_check(source,retained,pins)
    validate_snapshot(retained/'snapshot.json')
    solver = output/'solver'
    solver.mkdir()
    text,labels,elements = worker.mesh_text(mesh)
    (solver/'mesh.mail').write_text(text,encoding='ascii',newline='\n')
    save_json(solver/'mesh.json',mesh)
    for file in (WORKER,HELPER,GEOMETRY):
        (output/file.name).write_bytes(file.read_bytes())
    sources = {file.name:_sha(file) for file in (WORKER,HELPER,GEOMETRY)}
    save_json(solver/'input.json',{'material':manifest['material'],'node_labels':labels,
        'element_labels':elements,'mail_sha256':_sha(solver/'mesh.mail'),
        'mesh_record_sha256':_sha(solver/'mesh.json'),'worker_sources':sources})
    (solver/'model.comm').write_text("import sys\nsys.path.insert(0, '/work')\nfrom codeaster_frozen_worker import solve\nsolve('/work/solver/input.json')\n",encoding='ascii',newline='\n')
    budgets = process_budgets()
    (solver/'model.export').write_text(
        f"P actions make_etude\nP memory_limit {budgets['solver_memory_mb']}\nP time_limit {budgets['solver_time_seconds']}\nP mpi_nbcpu 1\nP ncpus 1\n"
        'F comm /work/solver/model.comm D 1\nF mail /work/solver/mesh.mail D 20\n'
        'F rmed /work/solver/results.med R 80\nF mess /work/solver/aster.mess R 6\nF resu /work/solver/aster.resu R 8\n',encoding='ascii',newline='\n')
    return manifest,mesh,pins,gates,sources,budgets


def execute_native(output,budgets):
    """Reuse the registered Linux/SIF policy and its owned-process cleanup."""
    if any(name.upper().startswith(('SINGULARITY_','SINGULARITYENV_','APPTAINER_','APPTAINERENV_')) for name in os.environ):
        raise RuntimeError('Inherited container option overrides are not admitted')
    image,image_sha,runtime,_gmsh,_prlimit = native._image_identity(output)
    preferences,scratch_root = output/'preferences',output/'scratch'
    preferences.mkdir();scratch_root.mkdir()
    scratch = scratch_root/'level_0';scratch.mkdir()
    command = [runtime,'exec','--cleanenv','--containall','--no-home','--env','OMP_NUM_THREADS=2',
        '--bind',str(output.resolve())+':/work:rw','--bind',str(preferences.resolve())+':'+str(Path.home())+':rw',
        '--bind',str(scratch.resolve())+':/tmp:rw','--pwd','/work',str(image),
        '/bin/bash','--noprofile','--norc','-c',native.CONTAINER_SCRIPT,'caelab-codeaster','/work/solver/model.export']
    native._process(command,output/'solver','solver',timeout=budgets['subprocess_timeout_seconds'])
    if _sha(image) != image_sha:
        raise ValueError('Native Aster image changed during execution')
    return {'image_sha256':image_sha,'runtime':'existing configured Singularity/SIF','solver':'Code_Aster17.4'}


def write_post(output,manifest,mesh,pins,observed):
    post = output/'post';post.mkdir()
    ordered = sorted(mesh['nodes'],key=lambda row:row['node_id'])
    raw = {'nodes':[{**row,'displacement_mm':observed['displacements'][row['node_id']]} for row in ordered],
        'elements':mesh['elements'],'fixed_node_ids':sorted({r['node_id'] for r in mesh['fixed_dofs']}),'loads':mesh['loads'],
        'snapshot_id':manifest['id'],'coordinate_frame':'FREECAD_DOCUMENT_GLOBAL','static':observed['static'],'input_pins':pins,
        'qualification':'UNKNOWN','engineering_valid':False,'stress_location':'native_integration_points'}
    save_json(post/'native_fields.json',{'mesh':raw,'observed':observed})
    reactions = {name:[observed['reactions'][row['node_id']][axis] for row in ordered]
                 for axis,name in enumerate(('ReactionX_N','ReactionY_N','ReactionZ_N'))}
    write_vtu(post/'displacement.vtu',raw,extra=reactions)
    arrays = [dict(name='U_mm',association='POINTS',components=3,component_names=['UX','UY','UZ'],units='mm',frame=raw['coordinate_frame'],measure='displacement')]
    for name in ('UX_mm','UY_mm','UZ_mm','U_magnitude_mm'):
        arrays.append(dict(name=name,association='POINTS',components=1,units='mm',frame=raw['coordinate_frame'],measure='displacement'))
    for name in reactions:
        arrays.append(dict(name=name,association='POINTS',components=1,units='N',frame=raw['coordinate_frame'],measure='nodal_reaction'))
    for name,association in (('NativeNodeId','POINTS'),('NativeElementId','CELLS'),('FixedXYZ_input','POINTS'),('LoadedNode_input','POINTS')):
        arrays.append(dict(name=name,association=association,components=1,units='1',frame='not_applicable',measure='identity'))
    primary = {'relative':'post/displacement.vtu','bytes':(post/'displacement.vtu').stat().st_size,'sha256':_sha(post/'displacement.vtu'),
        'native_metadata':{'coordinate_units':'mm','coordinate_frame':raw['coordinate_frame'],'static':observed['static'],'arrays':arrays}}
    # Preserve physical Gauss positions as a point cloud, never extrapolate to nodes.
    rows = observed['stress_points']
    vtk = ET.Element('VTKFile',type='UnstructuredGrid',version='0.1',byte_order='LittleEndian')
    piece = ET.SubElement(ET.SubElement(vtk,'UnstructuredGrid'),'Piece',NumberOfPoints=str(len(rows)),NumberOfCells=str(len(rows)))
    data_array(ET.SubElement(piece,'Points'),'Position_mm',(v for row in rows for v in row['position_mm']),3)
    cells = ET.SubElement(piece,'Cells')
    for name,values in (('connectivity',range(len(rows))),('offsets',range(1,len(rows)+1)),('types',[1]*len(rows))):
        data_array(cells,name,values,integer=True)
    points = ET.SubElement(piece,'PointData')
    stress_arrays = []
    for axis,component in enumerate(worker.STRESS_COMPONENTS):
        name = component+'_MPa'
        data_array(points,name,[r['stress_MPa'][axis] for r in rows])
        stress_arrays.append(dict(name=name,association='POINTS',components=1,units='MPa',frame=raw['coordinate_frame'],
            measure='cauchy_stress_at_native_integration_point',quantity='native_integration_point_stress'))
    for name,key in (('NativeElementId','element_id'),('NativeGaussPoint','point'),('NativeSubpoint','subpoint')):
        data_array(points,name,[r[key] for r in rows],integer=True)
        stress_arrays.append(dict(name=name,association='POINTS',components=1,units='1',frame='not_applicable',measure='identity'))
    ET.ElementTree(vtk).write(post/'stress_points.vtu',encoding='utf-8',xml_declaration=True)
    secondary = {'relative':'post/stress_points.vtu','bytes':(post/'stress_points.vtu').stat().st_size,'sha256':_sha(post/'stress_points.vtu'),
        'native_metadata':{'coordinate_units':'mm','coordinate_frame':raw['coordinate_frame'],'static':observed['static'],'arrays':stress_arrays}}
    return primary,secondary


class FrozenFemCodeAsterAdapter:
    backend,version = 'structure.codeaster.frozen','1'

    def run(self,settings,*,output,runtime=None):
        if (not isinstance(settings,dict) or set(settings)-{'snapshot_path','data_id'} or not isinstance(settings.get('snapshot_path'),str)):
            raise ValueError('Frozen Aster requires snapshot_path and optional registered data_id')
        if runtime:
            raise ValueError('Use the existing operator-configured Aster runtime')
        if 'data_id' in settings:check_id(settings['data_id'])
        output = Path(output).absolute()
        if any(p.is_symlink() for p in (output,*output.parents)):
            raise ValueError('Frozen Aster output must be a regular new directory')
        output.mkdir(parents=True,exist_ok=True)
        if any(output.iterdir()):raise ValueError('Frozen Aster preserves existing output; choose a new run')
        result = dict(execution_status='REJECTED',solver_status='NOT_RUN',responses={},checks=[],diagnostics={},
            qualification='UNKNOWN',decision='NOT_RELEASED',engineering_valid=False,limitations=LIMITATIONS)
        try:
            source = Path(settings['snapshot_path'])
            manifest,mesh,pins,gates,sources,budgets = prepare_input(source,output)
            result.update(snapshot_id=manifest['id'],data_id=settings.get('data_id'),input_pins=pins,
                checks=[{'name':'frozen_mesh_admission','status':'PASS',**gates}])
            save_json(output/'process_budgets.json',budgets)
            prepared = {p.relative_to(output).as_posix():_sha(p) for p in (output/'solver').iterdir() if p.is_file()}
            check_cancelled()
            result['execution_status'] = 'FAILED'
            result['runtime'] = execute_native(output,budgets)
            check_cancelled()
            _source_check(source,output/'frozen_input',pins)
            for name,digest in prepared.items():
                if _sha(output/name) != digest:
                    raise ValueError('Prepared native Aster input changed: '+name)
            for name,digest in sources.items():
                if _sha(output/name) != digest or _sha(WORKER.parent/name) != digest:
                    raise ValueError('Frozen Aster worker source changed')
            config = json.loads(_read(output/'solver/input.json'))
            if _sha(output/'solver/mesh.mail') != config['mail_sha256'] or _sha(output/'solver/mesh.json') != config['mesh_record_sha256']:
                raise ValueError('Native Aster input changed')
            raw = json.loads(_read(output/'solver/worker_result.json'))
            if raw.get('input_sha256') != _sha(output/'solver/input.json') or raw.get('mail_sha256') != config['mail_sha256']:
                raise ValueError('Native Aster input/result association differs')
            if json.loads(_read(output/'solver/native_mesh_checks.json')) != raw.get('native_mesh_checks'):
                raise ValueError('Native Aster admission receipt differs from raw output')
            med = output/'solver/results.med'
            if med.is_symlink() or not med.is_file() or med.stat().st_size == 0:
                raise ValueError('Native Aster MED output is missing')
            observed = worker.parse_result(raw,mesh)
            primary,secondary = write_post(output,manifest,mesh,pins,observed)
            scratch = output/'scratch/level_0'
            if scratch.is_dir():native._cleanup_scratch(output,scratch)
            result.update(execution_status='SUCCEEDED',solver_status='COMPLETED',native_version=raw['versions'],
                static=observed['static'],post_artifact=primary,additional_post_artifacts=[secondary],
                support_reaction_N=observed['support_reaction_N'])
        except ExecutionCleanupFailed:
            raise
        except ExecutionCancelled as error:
            result.update(execution_status='CANCELLED',diagnostics={'reason':str(error)})
        except (ValueError,TypeError,KeyError,IndexError,AttributeError,OSError,RuntimeError,OverflowError) as error:
            result['diagnostics'] = {'reason':str(error),'type':type(error).__name__}
        execution = output/'solver/solver.execution.json'
        if execution.is_file():
            state = json.loads(_read(execution))
            result['native_execution'] = state
            result['solver_status'] = ('COMPLETED' if state['status'] == 'COMPLETED' else
                'CANCELLED' if state['status'] == 'CANCELLED' else 'FAILED' if state.get('pid') else 'NOT_RUN')
        result['artifacts'] = [{'relative':p.relative_to(output).as_posix(),'bytes':p.stat().st_size,'sha256':_sha(p)}
            for p in sorted(output.rglob('*')) if p.is_file() and not p.is_symlink()]
        save_json(output/'frozen_execution.json',result)
        return result
