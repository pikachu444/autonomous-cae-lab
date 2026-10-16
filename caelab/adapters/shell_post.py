"""Lossless ParaView views of observed shell locations; not a second viewer.

Quadratic surface nodes are duplicated per original element and side so local
axis display and shell identity are never merged by this writer. Native FRD
averaging has already occurred in CalculiX; we do not undo or repeat it.
"""
from pathlib import Path
from xml.etree import ElementTree as ET
import math

from .shell_results import rotate_tensor

TENSOR_COMPONENTS = ['XX','YY','ZZ','XY','YZ','ZX']
FRAME = 'FREECAD_DOCUMENT_GLOBAL'


def _write_xml(tree, destination):
    if hasattr(destination, 'write'):
        tree.write(destination, encoding='utf-8', xml_declaration=True)
    else:
        with Path(destination).open('wb') as stream:
            tree.write(stream, encoding='utf-8', xml_declaration=True)


def _document(points, cells, cell_type):
    from .vtu import data_array
    vtk=ET.Element('VTKFile',type='UnstructuredGrid',version='0.1',byte_order='LittleEndian',header_type='UInt32')
    grid=ET.SubElement(vtk,'UnstructuredGrid')
    piece=ET.SubElement(grid,'Piece',NumberOfPoints=str(len(points)),NumberOfCells=str(len(cells)))
    data_array(ET.SubElement(piece,'Points'),'Position_mm',(v for p in points for v in p),3)
    connectivity=ET.SubElement(piece,'Cells')
    data_array(connectivity,'connectivity',(n for c in cells for n in c),integer=True)
    offsets=[]; offset=0
    for c in cells:
        offset+=len(c); offsets.append(offset)
    data_array(connectivity,'offsets',offsets,integer=True)
    data_array(connectivity,'types',[cell_type]*len(cells),integer=True)
    return vtk,ET.SubElement(piece,'PointData'),ET.SubElement(piece,'CellData')


def _array(parent, descriptions, name, values, *, components=1, unit='1', frame='not_applicable',
           measure='identity', names=None, integer=False, location=None, recovery=None):
    from .vtu import data_array
    child=data_array(parent,name,values,components,integer)
    if names:
        for i,label in enumerate(names): child.set('ComponentName'+str(i),label)
    declaration={'name':name,'association':'POINTS' if parent.tag=='PointData' else 'CELLS',
                 'components':components,'units':unit,'frame':frame,'measure':measure}
    if names: declaration['component_names']=names
    if location: declaration['location']=location
    if recovery: declaration['recovery']=recovery
    descriptions.append(declaration)


def surface(path, mesh, locations, observed_frame):
    """Write only channels complete in this particular retained native frame."""
    lookup={(r['element_id'],r['side'],r['local_node']):r for r in locations}
    ordered=[]; cells=[]; cell_elements=[]; cell_sides=[]
    for e in mesh['elements']:
        for side,sign in (('bottom',-1),('top',1)):
            cell=list(range(len(ordered),len(ordered)+8))
            ordered.extend(lookup[(e,side,j)] for j in range(1,9))
            cells.append(cell); cell_elements.append(e); cell_sides.append(sign)
    vtk,pd,cd=_document([r['position_mm'] for r in ordered],cells,23)  # VTK_QUADRATIC_QUAD
    desc=[]
    for name,key in (('NativeNodeId','expanded_node_id'),('ShellNodeId','shell_node_id'),('NativeElementId','element_id')):
        _array(pd,desc,name,[r[key] for r in ordered],integer=True)
    _array(pd,desc,'ShellSide',[r['zeta'] for r in ordered],integer=True,measure='shell_side')
    _array(cd,desc,'NativeElementId',cell_elements,integer=True)
    _array(cd,desc,'ShellSide',cell_sides,integer=True,measure='shell_side')
    _array(pd,desc,'Normal_native',[v for r in ordered for v in r['normal_from_native_expansion']],components=3,
           frame=FRAME,measure='normal',location='expanded_surface_node')
    fields=observed_frame['fields']
    if 'DISP' in fields:
        vectors=[fields['DISP'][r['expanded_node_id']] for r in ordered]
        _array(pd,desc,'U_mm',[v for row in vectors for v in row],components=3,unit='mm',frame=FRAME,
               measure='displacement',names=['UX','UY','UZ'],location='expanded_surface_node',recovery='native_nodal_dof')
        _array(pd,desc,'U_magnitude_mm',[math.hypot(*v) for v in vectors],unit='mm',frame=FRAME,
               measure='displacement',location='expanded_surface_node',recovery='magnitude_of_native_vector')
    for field,prefix,unit,measure in (('STRESS','S','MPa','stress'),('TOSTRAIN','E','1','strain')):
        if field not in fields: continue
        values=[fields[field][r['expanded_node_id']] for r in ordered]
        _array(pd,desc,prefix+'_surface_recovered', [v for row in values for v in row],components=6,unit=unit,
               frame=FRAME,measure=measure,names=TENSOR_COMPONENTS,location='expanded_surface_node',
               recovery='native_extrapolated_nodal_averaged')
        local=[rotate_tensor(v,mesh['axes'][r['element_id']]) for r,v in zip(ordered,values)]
        _array(pd,desc,prefix+'_surface_local', [v for row in local for v in row],components=6,unit=unit,
               frame='SHELL_ELEMENT_CENTER_USER_AXES',measure=measure,names=['11','22','33','12','23','31'],
               location='expanded_surface_node',recovery='basis_change_of_native_nodal_recovery')
    _write_xml(ET.ElementTree(vtk),path)
    return {'coordinate_units':'mm','coordinate_frame':FRAME,'arrays':desc,
            'static':{k:observed_frame[k] for k in ('step','increment','load_parameter')},
            'time_measure':'static_load_parameter_not_physical_time',
            'location_kind':'expanded_surface_node','side_rule':'ShellSide: -1 bottom, +1 top relative to retained normal',
            'surface_stress_recovery':'native_extrapolated_nodal_averaged',
            'strain_shear_convention':'tensor_off_diagonal_not_engineering_gamma',
            'exact_surface_integration_stress':'UNSUPPORTED',
            'local_axes':'constant user basis projected at each original S8 element center',
            'engineering_valid':False}


def internal(path, rows, *, association='POINTS'):
    """Native COORD points only; never derive coordinates for missing DAT data."""
    if association not in ('POINTS','CELLS'):
        raise ValueError('Explicit native integration-point view association required')
    if not rows or any('COORD' not in r for r in rows):
        return None
    vtk,pd,cd=_document([r['COORD']['values'] for r in rows],[[i] for i in range(len(rows))],1)
    if association=='CELLS': pd=cd
    desc=[]
    _array(pd,desc,'NativeElementId',[r['element_id'] for r in rows],integer=True)
    _array(pd,desc,'IntegrationPoint',[r['integration_point'] for r in rows],integer=True)
    _array(pd,desc,'NaturalCoordinates',[v for r in rows for v in r['natural_coordinates']],components=3,measure='natural_coordinate')
    for field,unit,measure in (('S','MPa','stress'),('E','1','strain')):
        if all(field in r for r in rows):
            _array(pd,desc,field+'_internal',[v for r in rows for v in r[field]['values']],components=6,
                   unit=unit,frame=FRAME,measure=measure,names=TENSOR_COMPONENTS,
                   location='internal_integration_point',recovery='none_native_DAT')
    _write_xml(ET.ElementTree(vtk),path)
    return {'coordinate_units':'mm','coordinate_frame':FRAME,'arrays':desc,
            'location_kind':'internal_integration_point','surface':False,
            'time_measure':'static_load_parameter_not_physical_time','engineering_valid':False}


def collection(path, entries):
    root=ET.Element('VTKFile',type='Collection',version='0.1',byte_order='LittleEndian')
    group=ET.SubElement(root,'Collection')
    for name,time in entries:
        if Path(name).name!=name: raise ValueError('Shell view references must be plain relative filenames')
        ET.SubElement(group,'DataSet',timestep=format(time,'.17g'),group='',part='0',file=name)
    _write_xml(ET.ElementTree(root),path)
