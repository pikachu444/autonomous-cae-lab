"""Physical-time VTK projections of retained dynamic fields.

Uses the existing native VTK writer and declaration contract. Static preload has
its own dimensionless collection; a static duration is never relabelled seconds.
The original contact Post artifacts remain unmodified for contact inspection.
"""
from copy import deepcopy
from pathlib import Path
import math
from xml.etree import ElementTree as ET

from .adapters.frozen_fem import _sha
from .storage import save_json
from .dynamic_result_store import frame_metadata
from .execution_control import check_cancelled


def write(folder, model, result, *, source_root):
    from apps.desktop_post.prepare import write_vtu, data_array
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    from .dynamic_locations import retain_sources, write_sidecar, KEY
    source_files = retain_sources(folder, source_root, result)
    nodes = sorted(model['nodes'], key=lambda r:r['node_id'])
    ids = [r['node_id'] for r in nodes]
    bodies = {b:i+1 for i,b in enumerate(sorted(model['body_maps']))}
    field_names = set().union(*(f['field_names'] for f in frame_metadata(result)))
    declarations = []
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
    collections = {}
    for category in ('dynamic','static-preload'):
        root=ET.Element('VTKFile',type='Collection',version='0.1',byte_order='LittleEndian')
        collections[category]=(root,ET.SubElement(root,'Collection'),[],[])
    def vector(mapping,n,count=3):
        return mapping.get(n,mapping.get(str(n),[None]*count))
    def value(v):return math.nan if v is None else v
    for index,frame in enumerate(result['frames']):
        check_cancelled()
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
        raw={'nodes':[{**n,'displacement_mm':vector(fields['DISP'],n['node_id'])} for n in nodes],
             'elements':model['elements'],'loads':model['loads'],
             'fixed_node_ids':[n for n in ids if all((n,d) in restraint for d in (1,2,3))]}
        path=folder/('frame'+str(index+1).zfill(4)+'.vtu')
        write_vtu(path,raw,extra=extra)
        tree=ET.parse(path);cells=tree.find('./UnstructuredGrid/Piece/CellData')
        data_array(cells,'SourceElementId',[r['native_element_id'] for r in model['elements']],integer=True)
        data_array(cells,'ElementBodyIndex',[bodies[r['body_id']] for r in model['elements']],integer=True)
        for q in ('ELKE','ELSE'):
            by_element={r['element_id']:r['value'] for r in frame['energy'][q]['rows']}
            data_array(cells,q+'_Nmm',[value(by_element.get(r['element_id'])) for r in model['elements']])
            data_array(cells,q+'_valid',[int(by_element.get(r['element_id']) is not None) for r in model['elements']],integer=True)
        density={(r['element_id'],r['integration_point']):r['value'] for r in frame['energy']['ENER']['rows']}
        for ip in (1,2,3,4):
            data_array(cells,'ENER_IP'+str(ip)+'_N_per_mm2',
                       [value(density.get((r['element_id'],ip))) for r in model['elements']])
        tree.write(path,encoding='utf-8',xml_declaration=True)
        category='dynamic' if loc['physical_time_available'] else 'static-preload'
        root,group,times,locations=collections[category]
        coordinate=loc['physical_time_s'] if loc['physical_time_available'] else loc['native_global_coordinate']
        if times and coordinate<=times[-1]:
            raise ValueError('Retained physical/static output times are not uniquely increasing; no resampling')
        times.append(coordinate)
        locations.append({'result_frame_index':index,'file':path.name,'timestep':coordinate,
                          'native':deepcopy(frame['native']),'native_time_token':frame['native_time_token']})
        ET.SubElement(group,'DataSet',timestep=format(coordinate,'.17g'),group='',part='0',file=path.name)
    artifacts={}
    for category,(root,group,times,locations) in collections.items():
        if not times:continue
        path=folder/(category+'.pvd')
        ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        metadata={'coordinate_units':'mm','coordinate_frame':'FREECAD_DOCUMENT_GLOBAL','static':None,
                  'time':{'unit':'s' if category=='dynamic' else '1',
                          'semantics':'PHYSICAL_TIME' if category=='dynamic' else 'DIMENSIONLESS_MODEL_TIME',
                          'values':times},'arrays':deepcopy(declarations)}
        metadata[KEY]=write_sidecar(path,result,metadata,locations,source_files)
        artifacts[category]={'relative':path.name,'bytes':path.stat().st_size,'sha256':_sha(path),
                             'native_metadata':metadata}
    save_json(folder/'declarations.json',artifacts)
    return artifacts
