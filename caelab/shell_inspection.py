"""Small, pinned shell result bundle that opens without FreeCAD or a solver.

The companion is relative to the native ParaView input. It contains the raw
input, expansion map and observations, so copying just a VTU is explicitly a
view-only copy, not a lossless engineering result archive.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import math

from .adapters.shell_deck import read_bytes, json_read, sha, build
from .adapters.shell_results import read_expansion, read_frd, read_dat, locations

KIND='calculix-shell-inspection'


def _member(root, relative):
    if (not isinstance(relative,str) or not relative or '\\' in relative or ':' in relative
            or Path(relative).is_absolute() or any(p in ('','.','..') for p in relative.split('/'))):
        raise ValueError('Shell bundle requires a contained relative path')
    path=root/relative
    read_bytes(path)  # Bounded regular-file and symlink guard.
    if not path.resolve().is_relative_to(root.resolve()): raise ValueError('Shell bundle member escapes its root')
    return path


def retain(folder, model, observed, dat, location_rows, view_files, native_metadata, *, execution_status):
    """Seal after the owned solver has stopped; caller retains the raw sources."""
    from .storage import save_json
    folder=Path(folder)
    data={'kind':KIND,'schema_version':'1','model':model,
          'execution_status':execution_status,'engineering_valid':False,
          'surface':{'status':observed.get('status'),'frames':[], 'locations':location_rows,
                     'diagnostic':observed.get('diagnostic'),
                     'recovery':'native_extrapolated_nodal_averaged',
                     'exact_surface_integration_stress':'UNSUPPORTED'},
          'internal':dat,'native_metadata':native_metadata}
    for frame in observed.get('frames',[]):
        # Native IDs become explicit strings in JSON; no source association is inferred on load.
        data['surface']['frames'].append({k:v for k,v in frame.items()})
    save_json(folder/'shell_values.json',data)
    names=['shell_values.json',*view_files]
    names += ['source/'+p.name for p in sorted((folder/'source').iterdir()) if p.is_file() and p.stat().st_size]
    if len(names)!=len(set(names)): raise ValueError('Repeated shell bundle member')
    manifest={'kind':KIND,'schema_version':'1','main_view':view_files[0],
              'native_metadata':native_metadata,'files':[
                  {'relative':name,'bytes':(folder/name).stat().st_size,'sha256':sha(folder/name)} for name in names]}
    save_json(folder/'shell_inspection.json',manifest)
    return {'relative':'shell_inspection.json','sha256':sha(folder/'shell_inspection.json'),
            'bytes':(folder/'shell_inspection.json').stat().st_size}


def load(view, reference=None, *, verify_observations=True):
    """Read-only reopen. No imports of FreeCAD, process execution or JobManager."""
    view=Path(view).absolute(); root=view.parent
    reference=reference or {'relative':'shell_inspection.json'}
    manifest_path=_member(root,reference['relative'])
    payload=read_bytes(manifest_path)
    if ('sha256' in reference and hashlib.sha256(payload).hexdigest()!=reference['sha256'] or
            'bytes' in reference and len(payload)!=reference['bytes']):
        raise ValueError('Shell result bundle changed')
    manifest=json_read(manifest_path)
    if (manifest.get('kind')!=KIND or manifest.get('schema_version')!='1' or manifest.get('main_view')!=view.name):
        raise ValueError('Native view and shell result bundle do not match')
    paths=[manifest_path]; members={}
    for row in manifest['files']:
        name=row['relative']
        if name in members: raise ValueError('Duplicate shell result source')
        path=_member(root,name); raw=read_bytes(path)
        if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:
            raise ValueError('Retained shell source changed: '+name)
        members[name]=path; paths.append(path)
    if not {view.name,'shell_values.json','source/shell.inp','source/shell.12d','source/shell.frd'}<=members.keys():
        raise ValueError('Shell archive is missing native expansion/input/results')
    data=json_read(members['shell_values.json'],256*1024*1024)
    if (data.get('kind')!=KIND or data.get('schema_version')!='1' or
            data.get('native_metadata')!=manifest['native_metadata']):
        raise ValueError('Retained shell result declarations differ')
    deck,mesh=build(data['model'])
    if read_bytes(members['source/shell.inp'])!=deck.encode('ascii'):
        raise ValueError('Retained shell result input differs from its declared model')
    if verify_observations:
        import json
        expansion=read_expansion(members['source/shell.12d'],mesh['elements'])
        observed=read_frd(members['source/shell.frd'],expansion)
        mapped=locations(mesh,expansion,observed)
        # JSON normalizes native integer map keys. Compare complete retained raw channels.
        normalize=lambda value:json.loads(json.dumps(value,allow_nan=False))
        if (normalize(mapped)!=data['surface']['locations'] or
                normalize(observed['frames'])!=data['surface']['frames'] or
                observed['status']!=data['surface']['status']):
            raise ValueError('Retained top/bottom observations differ from native FRD/12d')
        if 'source/shell.dat' in members:
            if normalize(read_dat(members['source/shell.dat'],mesh['elements'],retain_lines='regions' in data['model']['draft']))!=data['internal']:
                raise ValueError('Retained internal observations differ from native DAT')
        elif data['internal'].get('rows'):
            raise ValueError('Internal result rows have no native DAT source')
        # Validate the actual view bytes too, not only a separately stored value table.
        # BytesIO regeneration is read-only: no solver, no disk writes on reopening.
        from io import BytesIO
        from .adapters.shell_post import surface, internal, collection
        complete_frames=[frame for frame in observed['frames'] if frame['fields']]
        entries=[]
        for index,frame in enumerate(complete_frames):
            name=f'surface_{index:04d}.vtu'; buffer=BytesIO()
            declaration=surface(buffer,mesh,mapped,frame)
            if name not in members or read_bytes(members[name])!=buffer.getvalue():
                raise ValueError('Shell surface view differs from its actual native observations')
            entries.append((name,frame['load_parameter']))
        from .adapters.shell_results import REQUIRED
        last=complete_frames[-1]
        complete=(observed['status']=='COMPLETE' and REQUIRED<=last['fields'].keys()
                  and last['load_parameter']==1.0 and data['internal']['status']=='COMPLETE'
                  and any(r['load_parameter']==1.0 for r in data['internal']['rows']))
        declaration.update(execution_status=data['execution_status'],
                           observation_status='COMPLETE' if complete else 'PARTIAL',
                           collection_relative='surfaces.pvd')
        if declaration != manifest['native_metadata']:
            raise ValueError('Shell declarations differ from their native observations and view meaning')
        buffer=BytesIO(); collection(buffer,entries)
        if 'surfaces.pvd' not in members or read_bytes(members['surfaces.pvd'])!=buffer.getvalue():
            raise ValueError('Shell result collection differs from the retained native frames')
        for index,time in enumerate(sorted({r['load_parameter'] for r in data['internal']['rows']})):
            rows=[r for r in data['internal']['rows'] if r['load_parameter']==time]
            name=f'internal_{index:04d}.vtu'; buffer=BytesIO()
            description=internal(buffer,rows,association='CELLS' if 'regions' in data['model']['draft'] else 'POINTS')
            if description is not None and (name not in members or read_bytes(members[name])!=buffer.getvalue()):
                raise ValueError('Internal-point view differs from its native DAT observations')
    return {'manifest':manifest,'data':data,'paths':paths}


def inspect(view, *, side, element_id, shell_node_id, increment=None, reference=None):
    """Return the actual location and available channels; absent fields stay absent."""
    bundle=load(view,reference)
    data=bundle['data']; surface=data['surface']
    if side not in ('top','bottom'): raise ValueError('Select top or bottom, not an unspecified shell node')
    matches=[r for r in surface['locations'] if (r['side'],r['element_id'],r['shell_node_id'])==
             (side,element_id,shell_node_id)]
    if len(matches)!=1: raise ValueError('That shell side/element/node is not in the retained result')
    candidates=[r for r in surface['frames'] if increment is None or r['increment']==increment]
    if not candidates: raise ValueError('The selected native increment is unavailable')
    frame=candidates[-1]; location=matches[0]; node=str(location['expanded_node_id'])
    fields={name:deepcopy(rows[node]) for name,rows in frame['fields'].items() if node in rows}
    return {'location':deepcopy(location),'static':{k:frame[k] for k in ('step','increment','load_parameter')},
            'fields':fields,'available':sorted(fields),'execution_status':data['execution_status'],
            'engineering_valid':False,'exact_surface_integration_stress':'UNSUPPORTED'}


def explicit_manifest(path):
    """Register an explicitly selected portable bundle, never infer units from VTU."""
    path=Path(path).absolute()
    if path.name!='shell_inspection.json':
        raise ValueError('Select the retained shell_inspection.json bundle')
    manifest=json_read(path)
    view=_member(path.parent,manifest['main_view'])
    reference={'relative':path.name,'sha256':sha(path),'bytes':path.stat().st_size}
    checked=load(view,reference)
    return view,{**deepcopy(checked['manifest']['native_metadata']),'shell_inspection':reference}


def inspect_internal(view, *, element_id, integration_point, quantity='S',
                     load_parameter=None, basis='global', reference=None):
    """Exact DAT IP inspection; a center-axis transform is explicitly derived."""
    if quantity not in ('S','E','COORD') or basis not in ('global','element_center_user'):
        raise ValueError('Select native S/E/COORD and an explicitly supported display basis')
    checked=load(view,reference); data=checked['data']; rows=data['internal']['rows']
    times=sorted({r['load_parameter'] for r in rows})
    time=times[-1] if load_parameter is None and times else load_parameter
    matches=[r for r in rows if (r['element_id'],r['integration_point'],r['load_parameter'])==
             (element_id,integration_point,time)]
    if len(matches)!=1 or quantity not in matches[0]:
        raise ValueError('This exact native integration-point quantity is unavailable')
    row=matches[0]; raw=deepcopy(row[quantity]); values=deepcopy(raw['values'])
    transform=None
    if basis!='global':
        if quantity=='COORD': raise ValueError('Native global COORD positions are not a material-axis tensor')
        _,mesh=build(data['model']); axes=mesh['axes'][element_id]
        from .adapters.shell_results import rotate_tensor
        values=rotate_tensor(values,axes)
        transform={'axes':axes,'definition':'constant basis projected at original S8 element center',
                   'native_IP_material_basis':False,'source_values':raw['values']}
    source=next((r for r in checked['manifest']['files'] if r['relative']=='source/shell.dat'),None)
    return {'element_id':element_id,'integration_point':integration_point,'load_parameter':time,
            'quantity':quantity,'values':values,'raw':raw,
            'unit':{'S':'MPa','E':'1','COORD':'mm'}[quantity],
            'position_mm':deepcopy(row.get('COORD',{}).get('values')),
            'position_status':'OBSERVED' if 'COORD' in row else 'UNAVAILABLE',
            'frame':'FREECAD_DOCUMENT_GLOBAL' if basis=='global' else 'SHELL_ELEMENT_CENTER_USER_AXES',
            'location':'internal_integration_point','association':'CELLS','recovery':'none_native_DAT',
            'basis_transform':transform,'shear_convention':'tensor_off_diagonal_not_engineering_gamma',
            'source_pin':source,'source_execution_status':data['execution_status'],
            'point_measurement':'UNSUPPORTED','engineering_valid':False}
