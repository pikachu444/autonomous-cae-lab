"""S8 execution slice using existing JobManager-owned cancellation and logs."""
from pathlib import Path
import shutil
import subprocess

from caelab.execution_control import (run_owned_command, check_cancelled,
                                     ExecutionCancelled, ExecutionCleanupFailed)
from caelab.storage import check_id, save_json
from .shell_deck import validate_snapshot, read_bytes, sha
from .shell_results import read_expansion, read_frd, read_dat, locations, REQUIRED
from .shell_post import surface, internal, collection

BACKEND='structure.calculix.shell'


def _same(path, pin):
    raw=read_bytes(path)
    if len(raw)!=pin['bytes'] or sha(path)!=pin['sha256']:
        raise ValueError('Retained shell source changed during execution: '+str(path))


def collect(output, model, mesh, *, execution_status):
    """Read stopped native output, retaining complete fields even after failure.

    A native failure is never promoted to success because a prior increment
    exists. Incomplete fields are absent, not borrowed from another increment.
    """
    from caelab.shell_inspection import retain, load
    output=Path(output); native=output/'solver'; post=output/'post'
    expansion=read_expansion(native/'shell.12d',mesh['elements'])
    observed=read_frd(native/'shell.frd',expansion)
    mapping=locations(mesh,expansion,observed)
    dat=(read_dat(native/'shell.dat',mesh['elements']) if (native/'shell.dat').is_file() and (native/'shell.dat').stat().st_size
         else {'status':'PARTIAL','rows':[],'diagnostic':{'reason':'No nonempty native DAT'}})
    frames=[f for f in observed['frames'] if f['fields']]
    if not frames:
        raise ValueError('No complete native shell field is available; raw output is retained')
    post.mkdir(exist_ok=False); (post/'source').mkdir()
    raw_names=['shell.inp','shell.12d','shell.frd','shell.dat','shell.sta','shell.cvg',
               'ccx_shell.stdout.log','ccx_shell.stderr.log','ccx_shell.execution.json']
    source_pins={}
    for name in raw_names:
        path=native/name
        if path.is_file() and path.stat().st_size:
            raw=read_bytes(path); source_pins[name]={'bytes':len(raw),'sha256':sha(path)}
            (post/'source'/name).write_bytes(raw)
    entries=[]; views=[]; metadata_by_frame=[]
    for index,frame in enumerate(frames):
        name=f'surface_{index:04d}.vtu'
        declarations=surface(post/name,mesh,mapping,frame)
        views.append(name); entries.append((name,frame['load_parameter'])); metadata_by_frame.append(declarations)
    collection(post/'surfaces.pvd',entries)
    # The collection retains per-frame coverage. The default view is the final
    # complete observed frame, including explicit absence of S/E after failure.
    for index,time in enumerate(sorted({r['load_parameter'] for r in dat['rows']})):
        rows=[r for r in dat['rows'] if r['load_parameter']==time]
        name=f'internal_{index:04d}.vtu'
        if internal(post/name,rows) is not None: views.append(name)
    last=frames[-1]
    complete=(observed['status']=='COMPLETE' and REQUIRED<=last['fields'].keys() and
              last['load_parameter']==1.0 and dat['status']=='COMPLETE' and
              any(r['load_parameter']==1.0 for r in dat['rows']))
    final_status=execution_status if execution_status!='SUCCEEDED' or complete else 'FAILED'
    native_metadata=dict(metadata_by_frame[-1])
    native_metadata.update(execution_status=final_status,
                           observation_status='COMPLETE' if complete else 'PARTIAL',
                           collection_relative='surfaces.pvd')
    # Main input is the last observed surface VTU. The bundle also retains every
    # earlier frame and internal DAT cloud; registration copies them together.
    primary=entries[-1][0]
    ordered=[primary,'surfaces.pvd']+[name for name in views if name!=primary]
    reference=retain(post,model,observed,dat,mapping,ordered,native_metadata,execution_status=final_status)
    for name,pin in source_pins.items():
        _same(native/name,pin); _same(post/'source'/name,pin)
    load(post/primary,reference)
    metadata_with_bundle={**native_metadata,'shell_inspection':reference}
    responses={}
    for field,name,unit,components,recovery in (
            ('DISP','shell_surface_displacement','mm',['UX','UY','UZ'],'native_nodal_dof'),
            ('STRESS','shell_surface_stress_recovered','MPa',['XX','YY','ZZ','XY','YZ','ZX'],'native_extrapolated_nodal_averaged'),
            ('TOSTRAIN','shell_surface_strain_recovered','1',['XX','YY','ZZ','XY','YZ','ZX'],'native_extrapolated_nodal_averaged')):
        if field not in last['fields']: continue
        vectors=[last['fields'][field][r['expanded_node_id']] for r in mapping]
        responses[name]={'kind':'field','unit':unit,'value':vectors,'component':'VECTOR' if field=='DISP' else 'TENSOR6',
            'location':'expanded_surface_nodes_top_and_bottom','reduction':'none',
            'metadata':{'association':'POINTS','component_names':components,
                'locations':[{k:r[k] for k in ('element_id','shell_node_id','expanded_node_id','side','zeta')} for r in mapping],
                'coordinates_mm':[r['position_mm'] for r in mapping],
                'coordinate_frame':'FREECAD_DOCUMENT_GLOBAL','position_unit':'mm',
                'static':{k:last[k] for k in ('step','increment','load_parameter')},
                'source':'solver/shell.frd','recovery':recovery,'exact_surface_integration_point':False,
                'interpolated_by_lab':False,'engineering_valid':False}}
    return {'execution_status':final_status,'responses':responses,
            'native_version':observed['native_version'],
            'observation_status':'COMPLETE' if complete else 'PARTIAL',
            'diagnostics':{'frd':observed.get('diagnostic'),'dat':dat.get('diagnostic')},
            'post_artifact':{'relative':'post/'+primary,'bytes':(post/primary).stat().st_size,
                'sha256':sha(post/primary),'native_metadata':metadata_with_bundle}}


class ShellFemCalculixAdapter:
    backend=BACKEND
    version='1'

    def run(self, settings, *, output, runtime=None):
        if (not isinstance(settings,dict) or set(settings)-{'snapshot_path','data_id'} or
                not isinstance(settings.get('snapshot_path'),str)):
            raise ValueError('Shell execution requires an exact registered snapshot_path and optional data_id')
        if runtime: raise ValueError('Shell execution uses configured ccx on PATH; no runtime override')
        if 'data_id' in settings: check_id(settings['data_id'])
        output=Path(output).absolute()
        if any(p.is_symlink() for p in (output,*output.parents)):
            raise ValueError('Shell run requires a regular new output directory')
        output.mkdir(parents=True,exist_ok=True)
        if any(output.iterdir()): raise ValueError('A new shell attempt must not overwrite prior input/results')
        result={'backend':BACKEND,'adapter_version':self.version,'execution_status':'FAILED',
                'qualification':'UNKNOWN','engineering_valid':False,'responses':{},
                'limitations':['Homogeneous isotropic linear static S8 only',
                    'Surface S/E are native recovered/averaged estimates, not surface integration-point values',
                    'DAT S/E/COORD are internal 27-point observations',
                    'Program execution success is not engineering validation']}
        model=mesh=None; native=None; pins=None; executable=None; binary_hash=None; source=None
        try:
            check_cancelled()
            source=Path(settings['snapshot_path'])
            manifest,model,mesh,pins=validate_snapshot(source)
            result.update(snapshot_id=manifest['id'],input_pins=pins)
            retained=output/'retained_inputs'; retained.mkdir()
            for name,pin in pins.items():
                _same(source.parent/name,pin)
                (retained/name).write_bytes(read_bytes(source.parent/name))
                _same(retained/name,pin)
            native=output/'solver'; native.mkdir()
            (native/'shell.inp').write_bytes(read_bytes(retained/'shell.inp'))
            command=shutil.which('ccx')
            if not command: raise RuntimeError('CalculiX 2.22 ccx is not on the configured PATH')
            executable=Path(command).resolve(strict=True); binary_hash=sha(executable)
            result['runtime']={'executable':str(executable),'sha256':binary_hash,'configuration':'configured PATH'}
            # Validate the version in actual FRD output, as the contact adapter
            # does: some Windows ccx builds return nonzero for the -v option.
            check_cancelled()
            completed=run_owned_command([str(executable),'-i','shell'],native,'ccx_shell',owned_tree=True)
            result['return_code']=completed.returncode
            result['execution_status']='SUCCEEDED' if completed.returncode==0 else 'FAILED'
            if completed.returncode: result['native_failure']='CalculiX exited nonzero; raw files/logs retained'
            check_cancelled()
        except ExecutionCleanupFailed:
            raise  # Never seal results while an owned process may still be writing.
        except ExecutionCancelled as error:
            result.update(execution_status='CANCELLED',diagnostics={'reason':str(error)})
        except (ValueError,KeyError,TypeError,AttributeError,IndexError,OverflowError,OSError,RuntimeError,subprocess.TimeoutExpired) as error:
            result.update(execution_status='FAILED',diagnostics={'type':type(error).__name__,'reason':str(error)})
        # Collect only after native command ownership has ended, even if cancelled.
        try:
            if pins is not None:
                for name,pin in pins.items():
                    _same(source.parent/name,pin); _same(output/'retained_inputs'/name,pin)
                if native is not None: _same(native/'shell.inp',pins['shell.inp'])
            if executable is not None and sha(executable)!=binary_hash:
                raise ValueError('CalculiX executable changed while running')
            if native is not None and (native/'shell.frd').is_file() and (native/'shell.12d').is_file():
                observed=collect(output,model,mesh,execution_status=result['execution_status'])
                result.update(observed)
            elif result['execution_status']=='SUCCEEDED':
                raise ValueError('CalculiX produced no native expansion/FRD output')
        except (ValueError,KeyError,TypeError,IndexError,OverflowError,OSError) as error:
            if result['execution_status']!='CANCELLED': result['execution_status']='FAILED'
            result['responses']={}; result.pop('post_artifact',None)
            result.setdefault('diagnostics',{})['collection_error']=str(error)
        result['artifacts']=[{'relative':p.relative_to(output).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
                             for p in sorted(output.rglob('*')) if p.is_file() and not p.is_symlink()]
        save_json(output/'shell_execution.json',result)
        return result
