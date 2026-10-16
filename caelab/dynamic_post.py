"""One native volume projection for contact, dynamic and static clock views.

The existing contact writer owns geometry, contact raw/validity/gap/resultants,
NS1 arrays and its inspection bundle. A per-frame enrichment adds NS2 fields
before that same VTU is pinned. PVD clock views reference the very same files.
"""
from copy import deepcopy
from pathlib import Path
import math
from xml.etree import ElementTree as ET

from .adapters.frozen_fem import _sha
from .storage import save_json
from .dynamic_result_store import frame_metadata
from .execution_control import check_cancelled


class _DynamicFields:
    def __init__(self, model, result):
        self.model, self.result = model, result
        nodes = sorted(model['nodes'], key=lambda r:r['node_id'])
        ids = [r['node_id'] for r in nodes]
        bodies = {b:i+1 for i,b in enumerate(sorted(model['body_maps']))}
        field_names = set().union(*(f['field_names'] for f in frame_metadata(result)))
        declarations = self.declarations = []
        def declare(name,unit,measure,association='POINTS',components=1):
            row={'name':name,'association':association,'components':components,
                 'units':unit,'frame':'FREECAD_DOCUMENT_GLOBAL','measure':measure}
            declarations.append(row)
            return row
        declare('U_mm','mm','native_displacement',components=3)['component_names']=['UX','UY','UZ']
        for name in ('UX_mm','UY_mm','UZ_mm','U_magnitude_mm'):declare(name,'mm','native_displacement')
        for name,association in (('NativeNodeId','POINTS'),('SourceNodeId','POINTS'),('BodyIndex','POINTS'),
            ('NativeElementId','CELLS'),('SourceElementId','CELLS'),('ElementBodyIndex','CELLS')):
            declare(name,'1','retained_native_identity',association)
        for axis in 'XYZ':
            declare('V'+axis+'_mm_per_s','mm/s','native_velocity')
            declare('A'+axis+'_derived_mm_per_s2','mm/s^2',
                    'derived_three_point_nonuniform_dV_dt; step_boundary_missing; NOT_native_A')
            declare('A'+axis+'_valid','1','derived_value_finite_and_three_same_step_samples_present')
            declare('F'+axis+'_N','N','native_RF_nodal_force; reaction_only_at_restrained_DOF')
            declare('Restrained'+axis,'1','exact_boundary_DOF_in_this_native_step')
        declare('ENER_nodal_N_per_mm2','N/mm^2','native_extrapolated_nodal_averaged_internal_energy_density')
        for name,label in (('STRESS','S'),('TOSTRAIN','E')):
            if name in field_names:
                for component in ('XX','YY','ZZ','XY','YZ','ZX'):
                    declare(label+component,'MPa' if name=='STRESS' else '1',
                            'native_cauchy_stress' if name=='STRESS' else ('native_Green_Lagrange_strain_tensor' if model['step']['geometry']=='nonlinear' else 'native_infinitesimal_strain_tensor'))
        if 'PE' in field_names:
            declare('PEEQ','1','native_equivalent_plastic_strain')
        for quantity in ('ELKE','ELSE'):
            declare(quantity+'_Nmm','N*mm','native_whole_element_'+quantity,'CELLS')
            declare(quantity+'_valid','1','native_element_value_recorded_and_finite','CELLS')
        for ip in (1,2,3,4):
            declare('ENER_IP'+str(ip)+'_N_per_mm2','N/mm^2',
                    'native_energy_density_at_element_integration_point_'+str(ip)+'; not_cell_average','CELLS')
        if model['contacts']:
            from .adapters.contact_results import CHANNELS, BASIS
            for j,name in enumerate(CHANNELS):
                declare(name,'mm' if j<3 else 'MPa','native_projected_contact_'+name)['frame']=BASIS
        self.nodes, self.ids, self.bodies, self.field_names = nodes, ids, bodies, field_names

    def enrich(self, tree, index, native_frame):
        from .adapters.vtu import data_array
        frame = self.result['frames'][index]
        if frame['native'] != native_frame['static']:
            raise ValueError('Dynamic and contact projections select different native frames')
        nodes, ids, bodies, field_names = self.nodes, self.ids, self.bodies, self.field_names
        model = self.model
        def vector(mapping,n,count=3):
            return mapping.get(n,mapping.get(str(n),[None]*count))
        def value(v): return math.nan if v is None else v
        fields,loc=frame['fields'],frame['location']
        restraint={tuple(k) for k in frame['restrained_dofs']}
        extra={'SourceNodeId':[n['native_node_id'] for n in nodes],
               'BodyIndex':[bodies[n['body_id']] for n in nodes]}
        for d,axis in enumerate('XYZ'):
            extra['V'+axis+'_mm_per_s']=[value(vector(fields.get('VELO',{}),n)[d]) for n in ids]
            extra['A'+axis+'_derived_mm_per_s2']=[value(vector(frame['acceleration']['values'],n)[d]) for n in ids]
            extra['A'+axis+'_valid']=[int(vector(frame['acceleration']['values'],n)[d] is not None) for n in ids]
            extra['F'+axis+'_N']=[value(vector(fields.get('FORC',{}),n)[d]) for n in ids]
            extra['Restrained'+axis]=[int((n,d+1) in restraint) for n in ids]
        extra['ENER_nodal_N_per_mm2']=[value(vector(fields.get('ENER',{}),n,1)[0]) for n in ids]
        for name,label in (('STRESS','S'),('TOSTRAIN','E')):
            if name in field_names:
                for d,component in enumerate(('XX','YY','ZZ','XY','YZ','ZX')):
                    extra[label+component]=[value(vector(fields.get(name,{}),n,6)[d]) for n in ids]
        if 'PE' in field_names:
            extra['PEEQ']=[value(vector(fields.get('PE',{}),n,1)[0]) for n in ids]
        if model['contacts']:
            from .adapters.contact_results import CHANNELS
            for d,name in enumerate(CHANNELS):
                extra[name]=[value(vector(fields.get('CONTACT',{}),n,6)[d]) for n in ids]
        points = tree.find('./UnstructuredGrid/Piece/PointData')
        present = {array.get('Name') for array in points.findall('DataArray')}
        for name, values in extra.items():
            if name not in present:
                data_array(points, name, values)
        cells = tree.find('./UnstructuredGrid/Piece/CellData')
        for q in ('ELKE','ELSE'):
            by_element={r['element_id']:r['value'] for r in frame['energy'][q]['rows']}
            data_array(cells,q+'_Nmm',[value(by_element.get(r['element_id'])) for r in model['elements']])
            data_array(cells,q+'_valid',[int(by_element.get(r['element_id']) is not None) for r in model['elements']],integer=True)
        density={(r['element_id'],r['integration_point']):r['value'] for r in frame['energy']['ENER']['rows']}
        for ip in (1,2,3,4):
            data_array(cells,'ENER_IP'+str(ip)+'_N_per_mm2',
                       [value(density.get((r['element_id'],ip))) for r in model['elements']])


class _NativeResultFrames:
    """Compatibility for explicit write(result) callers; no whole-result copy."""
    def __init__(self, result):
        self.result = result
        self.metadata = [{'static': f['native'], 'load_parameter_token': f['native_time_token'],
                          'fields': {name: {} for name in f['field_names']}}
                         for f in frame_metadata(result)]
    def __len__(self): return len(self.metadata)
    def __getitem__(self, index):
        if isinstance(index, slice): return [self[i] for i in range(*index.indices(len(self)))]
        data = self.result['frames'][index]
        return {'static': data['native'], 'load_parameter_token': data['native_time_token'],
                'step_location': data['location'],
                'fields': {name: {int(n): v for n,v in values.items()} for name,values in data['fields'].items()},
                'contact_tokens': {int(n): v for n,v in data.get('contact_tokens',{}).items()}}


def _write(folder, model, result, *, source_root, native_frames=None, legacy_context=None):
    from .adapters.contact_results import write_post, read_dat
    from .dynamic_locations import retain_sources, write_sidecar, KEY
    folder, source_root = Path(folder), Path(source_root)
    if folder.exists():
        raise ValueError('Choose a new immutable Post projection directory')
    frames = native_frames if native_frames is not None else _NativeResultFrames(result)
    from .dynamic_native_stream import frame_catalog
    if ([f['static'] for f in frame_catalog(frames)] !=
            [f['native'] for f in frame_metadata(result)]):
        raise ValueError('Native contact and retained result frames differ')
    context = dict(legacy_context or {})
    if 'pair_results' not in context:
        context['pair_results'] = read_dat(source_root/'solver/contact.dat',model['contacts'],frames,
                                           prefix=result['execution_status'] != 'SUCCEEDED')
    pairs = context.pop('pair_results')
    context.setdefault('execution', {'status': result['execution_status'],
        'complete_analysis': result['complete_analysis'], 'scope': 'RETAINED_NATIVE_OUTPUT'})
    context.setdefault('provenance', {
        'snapshot_id': result['snapshot_id'],
        'snapshot_sha256': result['source_pins']['frozen_input/snapshot.json']['sha256'],
        'raw_frd_sha256': result['source_pins']['solver/contact.frd']['sha256'],
        'raw_dat_sha256': result['source_pins'].get('solver/contact.dat',{}).get('sha256')})
    enrichment = _DynamicFields(model, result)
    legacy_metadata = write_post(folder, model, frames, pairs, frame_enricher=enrichment, **context)
    save_json(folder/'contact-declarations.json', legacy_metadata)
    # One portable source copy shared by both clock collections, never one per clock.
    source_files = retain_sources(folder, source_root, result)
    collections = {}
    for category in ('dynamic','static-preload'):
        root=ET.Element('VTKFile',type='Collection',version='0.1',byte_order='LittleEndian')
        collections[category]=(root,ET.SubElement(root,'Collection'),[],[])
    for index,frame in enumerate(frame_metadata(result)):
        check_cancelled()
        loc=frame['location']
        category='dynamic' if loc['physical_time_available'] else 'static-preload'
        root,group,times,locations=collections[category]
        coordinate=loc['physical_time_s'] if loc['physical_time_available'] else loc['native_global_coordinate']
        if times and coordinate<=times[-1]:
            raise ValueError('Retained physical/static output times are not uniquely increasing; no resampling')
        times.append(coordinate)
        filename='frame'+str(index+1).zfill(4)+'.vtu'
        locations.append({'result_frame_index':index,'file':filename,'timestep':coordinate,
                          'native':deepcopy(frame['native']),'native_time_token':frame['native_time_token']})
        ET.SubElement(group,'DataSet',timestep=format(coordinate,'.17g'),group='',part='0',file=filename)
    artifacts={}
    for category,(root,group,times,locations) in collections.items():
        if not times:continue
        path=folder/(category+'.pvd')
        ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        metadata={'coordinate_units':'mm','coordinate_frame':'FREECAD_DOCUMENT_GLOBAL','static':None,
                  'time':{'unit':'s' if category=='dynamic' else '1',
                          'semantics':'PHYSICAL_TIME' if category=='dynamic' else 'DIMENSIONLESS_MODEL_TIME',
                          'values':times},'arrays':deepcopy(legacy_metadata['arrays'])}
        metadata[KEY]=write_sidecar(path,result,metadata,locations,source_files)
        artifacts[category]={'relative':path.name,'bytes':path.stat().st_size,'sha256':_sha(path),
                             'native_metadata':metadata}
    save_json(folder/'declarations.json',artifacts)
    return artifacts


def write(folder, model, result, *, source_root, native_frames=None, legacy_context=None):
    """Explicit projection; native contact tokens are never fabricated from floats."""
    own=None
    try:
        if native_frames is None and model['contacts']:
            from .dynamic_native_stream import read_dynamic_frd
            from .dynamic_result_store import verify_pin
            from .contact_deck import validate_model
            from .contact_steps import profile,validate_frames
            root=Path(source_root)
            name='partial/committed.frd' if 'partial/committed.frd' in result['source_pins'] else 'solver/contact.frd'
            path=verify_pin(root,{'relative':name,**result['source_pins'][name]})
            nodes,elements,bodies=validate_model(model)
            indices={b:i+1 for i,b in enumerate(sorted(bodies))}
            materials={'names':['M'+str(i) for i in indices.values()]+[
                'INT'+p['object_id'].upper() for p in model['contacts'] if p['draft']['normal_law']!='tie'],
                'elements':{e['element_id']:'M'+str(indices[e['body_id']]) for e in model['elements']}}
            own=read_dynamic_frd(path,nodes,elements,contact_materials=materials,
                contact_profile=profile(model),require_contact=any(p['draft']['normal_law']!='tie' for p in model['contacts']))
            validate_frames(model,own,complete=result['complete_analysis'])
            native_frames=own['frames']
        return _write(folder,model,result,source_root=source_root,native_frames=native_frames,legacy_context=legacy_context)
    finally:
        if own is not None:
            from .dynamic_native_stream import release
            release(own)
