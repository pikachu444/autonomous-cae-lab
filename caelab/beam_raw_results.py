"""B32R/RECT OUTPUT=3D observations through the existing pinned native readers.

Expanded topology comes only from .12d; coordinates come only from FRD/DAT.
A section-force FRD is never admissible here, even if its STRESS label matches.
Native rotational DOF and complete discrete support reactions remain unavailable.
"""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from .beam_model import validate_model, number
from .beam_output import mode, settings, axes_for, mechanical_identity
from .shell_model import dot, sub, cross, unit
from .adapters.shell_deck import read_bytes
from .adapters import shell_results as native

# Exact topology positions from ccx 2.22 gen3dfrom1d.f, not node-ID arithmetic.
SECTIONS = ((0,'start',(0,3,7,4,11,19,15,16)),
            (1,'middle',(8,10,14,12)),
            (2,'end',(1,2,6,5,9,18,13,17)))
TENSOR_COMPONENTS = ['XX','YY','ZZ','XY','YZ','ZX']
UNAVAILABLE = {
    'native_generalized_rotation_rad': 'No documented exported generalized DOF-to-original-node map is present in this profile. Section fits are separate derived observations.',
    'complete_discrete_support_reaction': 'Native RF and stress-traction integrals are separate observations, not a proof of all MPC/generalized constraint contributions.',
    'section_forces_same_run': 'OUTPUT=3D is mutually exclusive with SECTION FORCES. Select another explicit run for section forces.',
}


def _pin(path):
    from .beam_results import sha
    payload=read_bytes(path)
    digest=hashlib.sha256(payload).hexdigest()
    if sha(path)!=digest:
        raise ValueError('Raw beam source changed while reading')
    return {'bytes':len(payload),'sha256':digest}


def section_locations(model, expansion, observed):
    """Corroborate real expanded RECT dimensions, reference centers and axes."""
    nodes,_,_=validate_model(model)
    xyz=observed['coordinates']; tokens=observed['coordinate_tokens']
    width=float(format(number(model['draft']['section']['width_mm']),'.13G'))
    height=float(format(number(model['draft']['section']['height_mm']),'.13G'))
    source_nodes={n:[float(format(v,'.13G')) for v in p] for n,p in nodes.items()}
    rows=[]
    for element, item in sorted(expansion.items()):
        declared=axes_for(model,element)
        for original_index, station, local in SECTIONS:
            original=item['original'][original_index]
            ids=[item['expanded'][i] for i in local]
            points=[xyz[n] for n in ids]
            errors=[[native._coordinate_error(v) for v in tokens[n]] for n in ids]
            center=[sum(p[k] for p in points[:4])/4 for k in range(3)]
            for k in range(3):
                bound=sum(e[k] for e in errors[:4])/4+64*math.ulp(max(abs(center[k]),abs(source_nodes[original][k])))
                if abs(center[k]-source_nodes[original][k])>bound:
                    raise ValueError(f'Expanded section center differs from retained beam node {original}')
            first=sub(points[2],points[1]); second=sub(points[0],points[1])
            for vector, expected, a,b in ((first,width,2,1),(second,height,0,1)):
                bound=math.hypot(*(errors[a][k]+errors[b][k] for k in range(3)))+64*math.ulp(expected)
                if math.hypot(*vector)<=bound or abs(math.hypot(*vector)-expected)>bound:
                    raise ValueError(f'Expanded RECT dimensions wrong/unresolved at element {element}, node {original}')
            n1,n2=unit(first),unit(second); tangent=unit(cross(n1,n2))
            # Corroborate every corner and actual edge midpoint against the
            # retained native section direction, within printed-coordinate bounds.
            expected_offsets=((-width/2,height/2),(-width/2,-height/2),
                              (width/2,-height/2),(width/2,height/2),
                              (-width/2,0),(0,-height/2),(width/2,0),(0,height/2))
            for j,(u,v) in enumerate(expected_offsets[:len(ids)]):
                expected=[source_nodes[original][k]+u*declared['local1'][k]+v*declared['local2'][k] for k in range(3)]
                for k in range(3):
                    bound=errors[j][k]+64*math.ulp(max(abs(expected[k]),abs(points[j][k])))
                    if abs(points[j][k]-expected[k])>bound:
                        raise ValueError(f'Expanded section axis/shape differs at element {element}, node {ids[j]}; no inferred averaged-axis mapping')
            rows.append({'element_id':element,'beam_node_id':original,'station_kind':station,
                         'expanded_node_ids':ids,'positions_mm':deepcopy(points),
                         'centroid_from_native_corners_mm':center,
                         'axes':{'local1':list(n1),'local2':list(n2),'tangent':list(tangent)},
                         'declared_axes':deepcopy(declared), 'native_12d_line':item['source_line'],
                         'location_kind':'observed_expanded_section',
                         'axis_origin':'actual_expanded_corner_coordinates',
                         'topology_source':'CalculiX_2.22_gen3dfrom1d.f_RECT'})
    return rows


def check_native_ip_coordinates(dat, expansion, expanded):
    """Corroborate DAT COORD against the actual expanded RECT element.

    The trilinear check is valid here only after section_locations has proved
    a straight affine RECT prism, including all midside nodes. Calculated
    coordinates are used for rejection, NEVER published as native COORD.
    In particular guard the 2.22 printoutint.f coordinate branch/buffer hazard
    for 50-point beams. The installed binary is not assumed to fix that source.
    """
    signs=((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
           (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))
    for row in dat['rows']:
        if 'COORD' not in row:
            continue
        ids=expansion[row['element_id']]['expanded'][:8]
        r,s,t=row['natural_coordinates']
        weights=[(1+a*r)*(1+b*s)*(1+c*t)/8 for a,b,c in signs]
        for k in range(3):
            expected=sum(w*expanded['coordinates'][n][k] for w,n in zip(weights,ids))
            reported=row['COORD']['values'][k]
            bound=sum(abs(w)*native._coordinate_error(expanded['coordinate_tokens'][n][k])
                      for w,n in zip(weights,ids))
            bound+=native._coordinate_error(row['COORD']['tokens'][k])
            bound+=64*math.ulp(max(abs(expected),abs(reported)))
            if abs(reported-expected)>bound:
                raise ValueError('Native beam DAT COORD does not match its 50-point expanded topology '
                                 f"at element {row['element_id']}, IP {row['integration_point']}; "
                                 'do not substitute calculated coordinates (ccx 2.22 COORD needs native verification)')


def read(path, model, *, allow_partial=False):
    if mode(model)!='raw_stress':
        raise ValueError('Select an explicit 3D raw-stress snapshot, not a section-force run')
    _,elements,_=validate_model(model)
    path=Path(path)
    sources={suffix:path.with_suffix(suffix) for suffix in ('.12d','.frd')}
    if path.with_suffix('.dat').is_file() and path.with_suffix('.dat').stat().st_size:
        sources['.dat']=path.with_suffix('.dat')
    pins={p.name:_pin(p) for p in sources.values()}
    expansion=native.read_expansion(sources['.12d'],elements,family='B32R_RECT')
    expanded=native.read_frd(sources['.frd'],expansion,profile='B32R_RECT')
    locations=section_locations(model,expansion,expanded)
    dat=(native.read_dat(sources['.dat'],elements,profile='B32R_RECT') if '.dat' in sources
         else {'status':'PARTIAL','rows':[],'diagnostic':{'reason':'No nonempty native DAT'}})
    check_native_ip_coordinates(dat,expansion,expanded)
    frames=[]
    from .beam_support_response import derived_rotation, support_responses
    for frame in expanded['frames']:
        fields=frame['fields']
        row={'output_mode':'raw_stress','static':{k:frame[k] for k in ('step','increment','load_parameter')},
             'load_parameter_token':frame['load_parameter_token'], 'native_fields':deepcopy(fields),
             'source_lines':deepcopy(frame['source_lines']),'complete':frame['complete']}
        row['supports']=support_responses(model,locations,fields,pins)
        row['derived_rotations']=([derived_rotation(s,fields['DISP'],pins) for s in locations]
                                  if settings(model['draft'])['derived_rotation'] and 'DISP' in fields else [])
        frames.append(row)
    times={f['static']['load_parameter'] for f in frames}
    dat_times={r['load_parameter'] for r in dat['rows']}
    complete=expanded['status']=='COMPLETE' and dat['status']=='COMPLETE' and times==dat_times
    if not complete and not allow_partial:
        raise ValueError('Incomplete/mismatched 3D beam FRD and DAT observations; retained raw sources remain available')
    for name,p in sources.items():
        if _pin(p)!=pins[p.name]:
            raise ValueError('Raw beam source changed during observation assembly')
    return {'native_version':'2.22','output_mode':'raw_stress','frames':frames,
            'coordinates_mm':expanded['coordinates'],'coordinate_tokens':expanded['coordinate_tokens'],
            'frd_elements':expanded['topology'],'expansion':expansion,'sections':locations,
            'internal':dat,'source_pins':pins,'mechanical_sha256':mechanical_identity(model),
            'complete_file':complete,'truncation':None if complete else
                {'frd':expanded['diagnostic'],'dat':dat['diagnostic'],'frame_times_match':times==dat_times},
            'unavailable':deepcopy(UNAVAILABLE)}


def _normalize_maps(observed):
    value=deepcopy(observed)
    for key in ('coordinates_mm','coordinate_tokens','expansion','frd_elements'):
        value[key]={int(k):v for k,v in value[key].items()}
    for f in value['frames']:
        f['native_fields']={name:{int(n):v for n,v in rows.items()} for name,rows in f['native_fields'].items()}
    return value


def _expanded_view(destination, observed, model, frame):
    from .adapters.shell_post import _document, _array, _write_xml
    order=[]; cells=[]; element_ids=[]
    for e,row in sorted(observed['expansion'].items()):
        cells.append(list(range(len(order),len(order)+20)))
        order.extend((e,n) for n in row['expanded']); element_ids.append(e)
    vtk,pd,cd=_document([observed['coordinates_mm'][n] for _,n in order],cells,25)
    desc=[]
    _array(pd,desc,'NativeExpandedNodeId',[n for _,n in order],integer=True,location='expanded_3D_node')
    _array(pd,desc,'NativeElementId',[e for e,_ in order],integer=True,location='expanded_3D_node_element_incidence')
    _array(cd,desc,'NativeElementId',element_ids,integer=True,location='expanded_B32R_C3D20R')
    for field,name,width,units,measure,components,recovery in (
            ('DISP','U_mm',3,'mm','displacement',['UX','UY','UZ'],'native_expanded_nodal_dof'),
            ('FORC','RF_expanded_raw_N',3,'N','native_external_nodal_force',['X','Y','Z'],'native_expanded_RF'),
            ('STRESS','S_expanded_recovered_MPa',6,'MPa','stress',TENSOR_COMPONENTS,'native_extrapolated_nodal_averaged'),
            ('TOSTRAIN','E_expanded_recovered',6,'1','strain',TENSOR_COMPONENTS,'native_extrapolated_nodal_averaged')):
        if field not in frame['native_fields']: continue
        _array(pd,desc,name,[v for _,n in order for v in frame['native_fields'][field][n]],
               components=width,unit=units,frame='FREECAD_DOCUMENT_GLOBAL',measure=measure,
               names=components,location='expanded_3D_node',recovery=recovery)
        desc[-1].update(source_field=field,interpolated_by_lab=False)
        if field in ('STRESS','TOSTRAIN'):
            desc[-1]['shear_convention']='tensor_off_diagonal_not_engineering_gamma'
            transformed=[native.rotate_tensor(frame['native_fields'][field][n],
                           [axes_for(model,e)[key] for key in ('local1','local2','tangent')]) for e,n in order]
            _array(pd,desc,name+'_declared_local',[v for t in transformed for v in t],components=6,unit=units,
                   frame='DECLARED_BEAM_ELEMENT_AXES',measure=measure,names=['11','22','33','12','23','31'],
                   location='expanded_3D_node',recovery='basis_change_of_native_nodal_recovery')
            desc[-1].update(source_array=name,shear_convention='tensor_off_diagonal_not_engineering_gamma',
                            basis_is_native_IP_material_basis=False)
    _write_xml(ET.ElementTree(vtk),destination)
    return desc


def post_metadata(observed, model, *, source_status):
    from io import BytesIO
    if source_status not in {'SUCCEEDED','FAILED','CANCELLED','PARTIAL_FAILURE'}:
        raise ValueError('Preserve the actual beam execution status')
    observed=_normalize_maps(observed)
    if mode(model)!='raw_stress' or observed['mechanical_sha256']!=mechanical_identity(model):
        raise ValueError('Raw beam observations and mechanical input differ')
    arrays={}
    from .adapters.shell_post import internal
    for f in observed['frames']:
        for d in _expanded_view(BytesIO(),observed,model,f):
            d['source_blocks']=[{'group':'expanded_recovered','part':0}]
            arrays[d['association'],d['name']]=d
        rows=[r for r in observed['internal']['rows'] if r['load_parameter']==f['static']['load_parameter']]
        declaration=internal(BytesIO(),rows,association='CELLS')
        if declaration:
            for d in declaration['arrays']:
                d['source_blocks']=[{'group':'internal_native_DAT','part':1}]
                key=d['association'],d['name']
                if key in arrays:
                    # Identity arrays shared by the two native blocks have the
                    # same quantity, but retain both incidence locations.
                    d['source_blocks']=arrays[key]['source_blocks']+d['source_blocks']
                arrays[key]=d
    times=[f['static']['load_parameter'] for f in observed['frames']]
    if not times or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('Native beam frame times must increase')
    return {'coordinate_units':'mm','coordinate_frame':'FREECAD_DOCUMENT_GLOBAL','static':None,
        'time':{'unit':'1','semantics':'STATIC_LOAD_PARAMETER','values':times},'arrays':list(arrays.values()),
        'beam':{'element':'B32R','output':'3D_RAW_STRESS','location':'NATIVE_EXPANDED_3D_AND_INTERNAL_IP',
                'axes':deepcopy(model['axes']),'element_axes':deepcopy(model.get('element_axes',{})),
                'units':deepcopy(model['units']),'mechanical_sha256':observed['mechanical_sha256'],
                'source_execution_status':source_status,'complete_file':observed['complete_file'],
                'truncation':observed['truncation'],
                'observation_status':'COMPLETE' if observed['complete_file'] and source_status=='SUCCEEDED' else 'PARTIAL',
                'frames':[deepcopy(f['static']) for f in observed['frames']],
                'unavailable':deepcopy(UNAVAILABLE),'source_pins':deepcopy(observed['source_pins']),
                'strain_shear_convention':'tensor_off_diagonal_not_engineering_gamma',
                'blocks':[{'group':'expanded_recovered','part':0,'element_type':'C3D20RBR_NATIVE_EXPANSION',
                           'location':'native_expanded_3D_nodes'},
                          {'group':'internal_native_DAT','part':1,'element_type':'VTK_VERTEX',
                           'location':'internal_integration_point','association':'CELLS'}],
                'integration_rule':'CalculiX_2.22_gauss3d13_50_points',
                'internal_point_association':'CELLS','point_measurement_of_IP':'UNSUPPORTED',
                'native_generalized_rotation':'UNAVAILABLE','engineering_valid':False}}


def post_files(observed, model, *, source_status):
    from io import BytesIO
    from .adapters.shell_post import internal
    observed=_normalize_maps(observed)
    root=ET.Element('VTKFile',type='Collection',version='0.1',byte_order='LittleEndian')
    datasets=ET.SubElement(root,'Collection')
    for index,frame in enumerate(observed['frames']):
        name=f'beam_raw_{index:04d}.vtu'; stream=BytesIO()
        _expanded_view(stream,observed,model,frame)
        yield name,stream.getvalue()
        time=frame['static']['load_parameter']
        ET.SubElement(datasets,'DataSet',timestep=format(time,'.17g'),group='expanded_recovered',part='0',file=name)
        rows=[r for r in observed['internal']['rows'] if r['load_parameter']==time]
        stream=BytesIO(); declaration=internal(stream,rows,association='CELLS')
        if declaration:
            name=f'beam_ip_{index:04d}.vtu';yield name,stream.getvalue()
            ET.SubElement(datasets,'DataSet',timestep=format(time,'.17g'),group='internal_native_DAT',part='1',file=name)
    yield 'beam.pvd',ET.tostring(root,encoding='utf-8',xml_declaration=True)


def final_responses(observed, model):
    observed=_normalize_maps(observed); frame=observed['frames'][-1]; result={}
    nodes=sorted(observed['coordinates_mm'])
    for field,name,unit,width,components in (
            ('DISP','beam_expanded_displacement','mm',3,['UX','UY','UZ']),
            ('STRESS','beam_expanded_stress_recovered','MPa',6,TENSOR_COMPONENTS),
            ('TOSTRAIN','beam_expanded_strain_recovered','1',6,TENSOR_COMPONENTS)):
        if field not in frame['native_fields']: continue
        result[name]={'kind':'field','unit':unit,'value':[frame['native_fields'][field][n] for n in nodes],
                      'component':'VECTOR' if width==3 else 'TENSOR6','location':'native_expanded_3D_nodes',
                      'reduction':'none','metadata':{'association':'POINTS','expanded_node_ids':nodes,
                      'coordinates_mm':[observed['coordinates_mm'][n] for n in nodes],
                      'coordinate_frame':'FREECAD_DOCUMENT_GLOBAL','position_unit':'mm',
                      'component_names':components,'static':deepcopy(frame['static']),
                      'source_field':field,'source_pins':deepcopy(observed['source_pins']),
                      'recovery':'native_nodal_dof' if field=='DISP' else 'native_extrapolated_nodal_averaged',
                      'shear_convention':'tensor_off_diagonal_not_engineering_gamma' if width==6 else 'not_applicable',
                      'engineering_valid':False,'interpolated':False}}
    rows=[r for r in observed['internal']['rows'] if r['load_parameter']==frame['static']['load_parameter']]
    for field,unit in (('S','MPa'),('E','1')):
        if rows and all(field in r and 'COORD' in r for r in rows):
            result['beam_internal_'+field]={'kind':'field','unit':unit,'value':[r[field]['values'] for r in rows],
                'component':'TENSOR6','location':'native_internal_integration_points','reduction':'none',
                'metadata':{'association':'CELLS','component_names':TENSOR_COMPONENTS,
                    'locations':[{'element_id':r['element_id'],'integration_point':r['integration_point']} for r in rows],
                    'coordinates_mm':[r['COORD']['values'] for r in rows],'position_unit':'mm',
                    'coordinate_frame':'FREECAD_DOCUMENT_GLOBAL','static':deepcopy(frame['static']),
                    'source_pins':deepcopy(observed['source_pins']),'recovery':'none_native_DAT',
                    'shear_convention':'tensor_off_diagonal_not_engineering_gamma',
                    'point_measurement':'UNSUPPORTED','engineering_valid':False,'interpolated':False}}
    return result
