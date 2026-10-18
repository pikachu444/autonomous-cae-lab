"""Read pinned existing CCX nodal U on its undeformed C3D10 reference mesh.

No solver, owner, native process or field reconstruction is performed. Static
load parameters remain dimensionless and are never treated as physical time.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
from xml.etree import ElementTree as ET
import numpy as np

from .post_spatial_mapping import tetra10_boundary, selected_boundary


def _pinned(path, expected):
    path=Path(path)
    if (not isinstance(expected,str) or re.fullmatch('[0-9a-f]{64}',expected) is None
            or not path.is_file() or any(p.is_symlink() for p in (path,*path.parents))):
        raise ValueError('Select an existing regular retained source and its exact SHA256.')
    content=path.read_bytes()
    if hashlib.sha256(content).hexdigest()!=expected:
        raise ValueError('Retained displacement source differs from its explicit SHA256 pin.')
    return content


def _static(value):
    if (not isinstance(value,dict) or set(value)!={'step','increment','load_parameter'}
            or any(type(value[k]) is not int or value[k]<1 for k in ('step','increment'))
            or type(value['load_parameter']) not in (int,float) or not math.isfinite(value['load_parameter'])):
        raise ValueError('Select one complete native static step/increment/load_parameter.')
    return deepcopy(value)


def _mesh(mesh):
    if (mesh.get('kind') not in ('freecad-fem-mesh','freecad-contact-mesh')
            or mesh.get('units',{}).get('position')!='mm' or mesh.get('units',{}).get('displacement')!='mm'):
        raise ValueError('This CCX producer requires its original reference mesh in mm.')
    from .adapters.frozen_fem import CCX_FROM_NATIVE_TET10
    if mesh.get('native_to_deck_slots')!=list(CCX_FROM_NATIVE_TET10):
        raise ValueError('The source must retain its original native-to-deck ordering identity.')
    nodes=mesh['nodes'];elements=mesh['elements']
    for row in elements:
        if row['node_ids']!=[row['native_node_ids'][slot] for slot in CCX_FROM_NATIVE_TET10]:
            raise ValueError('Reference C3D10 connectivity differs from the producer ordering.')
    ids=[row['node_id'] for row in nodes];coordinates=[row['position_mm'] for row in nodes]
    tetra10_boundary(ids,coordinates,elements)
    return ids,coordinates,deepcopy(elements)


def receiver_from_capture(model, boundary_faces, components, *, coordinate_frame):
    """Extract an explicitly selected native boundary without changing its BCs.

    ``model`` is the original existing native collect/validated snapshot model.
    This only creates the domain mapper's receiver arrays; it neither replaces
    constraints nor writes a deck/snapshot. The shared receiver owns that step.
    """
    if not isinstance(coordinate_frame,str) or not coordinate_frame.strip():
        raise ValueError('An explicit receiver coordinate frame is required.')
    if (not isinstance(components,list) or not components or len(set(components))!=len(components)
            or any(type(v) is not int or v not in (1,2,3) for v in components)):
        raise ValueError('Select distinct receiver translational DOFs1,2,3.')
    ids,coordinates,elements=_mesh(model)
    faces=selected_boundary(ids,coordinates,elements,boundary_faces)
    return {'node_ids':ids,'coordinates':coordinates,'elements':elements,
        'boundary_faces':deepcopy(boundary_faces),
        'boundary_node_ids':sorted({n for face in faces for n in face['node_ids']}),
        'components':deepcopy(components),'units':{'position':'mm','displacement':'mm'},
        'coordinate_frame':coordinate_frame,'geometry':'fixed_reference'}


def bind_transfer_model(captured, receipt):
    """Explicitly replace the selected zero baseline with the READY U trace.

    Bounded first profile: one independently authored linear STATIC solid,
    one zero Fixed ``TransferBoundary`` and no other loads/contact/step edits.
    Original conditions, program and full mapping receipt remain provenance.
    Existing condition/step compilers own every native card and conflict check.
    """
    from .contact_deck import validate_model
    from .contact_steps import default_program, validate_contributions
    from .storage import canonical_hash
    validate_model(captured)
    if (captured.get('analysis_scope')!='single_solid_static' or captured.get('contacts')
            or captured.get('loads') or captured.get('restart')
            or captured.get('step',{}).get('geometry')!='linear'
            or any(m.get('law')!='isotropic_linear_elastic' or m.get('plasticity') for m in captured['materials'])):
        raise ValueError('TR-U first receiver requires an independent linear STATIC solid without other loads/contact/state.')
    if (not isinstance(receipt,dict) or receipt.get('status')!='READY'
            or receipt.get('invalid_required_node_ids')!=[] or receipt.get('units')!={'position':'mm','displacement':'mm'}):
        raise ValueError('Only a complete READY reference-boundary U receipt may bind a receiver.')
    faces=[[row['element_id'],row['face']] for row in receipt['boundaries']]
    receiver=receiver_from_capture(captured,faces,receipt['components'],coordinate_frame=receipt['receiver_frame'])
    ids=receiver['boundary_node_ids'];components=receiver['components'];rows=receipt['rows']
    if (receipt.get('receiver_sha256')!=canonical_hash(receiver) or receipt.get('target_node_ids')!=ids
            or not isinstance(receipt.get('mask'),list) or len(receipt['mask'])!=len(ids)
            or any(type(v) is not bool or not v for v in receipt['mask']) or len(rows)!=len(ids)
            or [row.get('node_id') for row in rows]!=ids
            or any(row.get('valid') is not True or not isinstance(row.get('displacement_mm'),list)
                   or len(row['displacement_mm'])!=3
                   or any(type(v) not in (int,float) or not math.isfinite(v) for v in row['displacement_mm']) for row in rows)):
        raise ValueError('The READY receipt differs from the exact captured receiver or its essential displacement rows.')
    dofs=[{'node_id':row['node_id'],'component':d,'value_mm':row['displacement_mm'][d-1]}
          for row in rows for d in components]
    if receipt.get('boundary_dofs')!=dofs:
        raise ValueError('Prescribed DOFs differ from the original mapped U component rows.')
    conditions=captured.get('conditions',[])
    if (len(conditions)!=1 or conditions[0].get('object_id')!='TransferBoundary'
            or conditions[0].get('type')!='Fem::ConstraintFixed'
            or any(row.get('value_mm')!=0. for row in captured['boundary_dofs'])
            or {(r['node_id'],r['component']) for r in captured['boundary_dofs']}!={(r['node_id'],r['component']) for r in dofs}
            or captured.get('analysis_steps')!=default_program(captured['step'],conditions)):
        raise ValueError('Explicit replacement requires exactly the original zero TransferBoundary and unedited baseline program.')
    model=deepcopy(captured);baseline=conditions[0];model['conditions']=[]
    for row in rows:
        n=row['node_id'];values={d:row['displacement_mm'][d-1] for d in components}
        model['conditions'].append({'object_id':'TransferBoundaryNode'+str(n),'label':'전달 변위 '+str(n),
            'type':'Fem::ConstraintDisplacement','body_id':baseline['body_id'],'targets':[],
            'components_mm':values,'boundary_dofs':[r for r in dofs if r['node_id']==n],
            'source_condition_id':baseline['object_id']})
    model['boundary_dofs']=deepcopy(dofs)
    model['analysis_steps']=default_program(model['step'],model['conditions'])
    model['displacement_transfer']=deepcopy(receipt)
    model['displacement_transfer'].update(captured_model_sha256=canonical_hash(captured),
        original_conditions=deepcopy(conditions),original_boundary_dofs=deepcopy(captured['boundary_dofs']),
        original_analysis_steps=deepcopy(captured['analysis_steps']),
        replacement_policy='explicit_exact_selected_zero_fixed_boundary_dofs')
    validate_contributions(model);validate_model(model)
    return model


def _array(parent, name, components=1, integer=False):
    if parent is None:raise ValueError('Missing retained VTU array container '+str(name))
    rows=[row for row in parent.findall('DataArray') if row.get('Name')==name] if name is not None else parent.findall('DataArray')
    if len(rows)!=1:raise ValueError('The retained VTU requires one exact '+str(name)+' array.')
    row=rows[0]
    if row.get('format')!='ascii' or row.get('NumberOfComponents','1')!=str(components):
        raise ValueError('Only the existing producer ASCII array/component layout is supported.')
    try:values=[int(v) if integer else float(v) for v in (row.text or '').split()]
    except ValueError:raise ValueError('Invalid actual VTU numeric array '+str(name)) from None
    if not integer and not all(math.isfinite(v) for v in values):
        raise ValueError('Nonfinite actual displacement/reference values are not admitted.')
    return values


def read_ccx_vtu(vtu_path, mesh_path, frame_path, *, expected_vtu_sha256,
                 expected_mesh_sha256, expected_frame_sha256, source_reference):
    """Read only the existing single-piece ASCII contact-results VTU producer."""
    content=_pinned(vtu_path,expected_vtu_sha256)
    mesh=json.loads(_pinned(mesh_path,expected_mesh_sha256))
    frame=json.loads(_pinned(frame_path,expected_frame_sha256))
    ids,coordinates,elements=_mesh(mesh);static=_static(frame.get('static'))
    axis=frame.get('step_location',{}).get('axis')
    if axis!={'name':'load_parameter','semantics':'STATIC_LOAD_PARAMETER','unit':'1'}:
        raise ValueError('TR-U currently admits a static load parameter, not a physical-time field.')
    if (frame['step_location'].get('index')!=static['step']
            or frame['step_location'].get('coordinate')!=static['load_parameter']):
        raise ValueError('Native static step location differs from its actual saved frame coordinate.')
    xml=ET.fromstring(content)
    pieces=xml.findall('UnstructuredGrid/Piece')
    if xml.get('type')!='UnstructuredGrid' or len(pieces)!=1 or xml.get('compressor') is not None:
        raise ValueError('Use the pinned existing single-piece ASCII CCX VTU artifact.')
    piece=pieces[0];point_data=piece.find('PointData');cell_data=piece.find('CellData')
    if point_data is None or cell_data is None or int(piece.get('NumberOfPoints','-1'))!=len(ids) or int(piece.get('NumberOfCells','-1'))!=len(elements):
        raise ValueError('VTU and reference mesh have different actual point/cell coverage.')
    actual_ids=_array(point_data,'NativeNodeId',integer=True)
    if len(actual_ids)!=len(ids) or len(set(actual_ids))!=len(ids) or set(actual_ids)!=set(ids):
        raise ValueError('VTU NativeNodeId coverage differs from the reference mesh.')
    raw_xyz=np.asarray(_array(piece.find('Points'),None,3)).reshape((-1,3))
    points={identifier:point for identifier,point in zip(actual_ids,raw_xyz)}
    if raw_xyz.shape!=(len(ids),3) or any(not np.array_equal(points[n],p) for n,p in zip(ids,coordinates)):
        raise ValueError('Use undeformed original reference coordinates, not deformed VTU geometry.')
    connectivity=_array(piece.find('Cells'),'connectivity',integer=True)
    offsets=_array(piece.find('Cells'),'offsets',integer=True)
    types=_array(piece.find('Cells'),'types',integer=True)
    element_ids=_array(cell_data,'NativeElementId',integer=True)
    if (offsets!=list(range(10,10*len(elements)+1,10)) or types!=[24]*len(elements)
            or len(connectivity)!=10*len(elements) or any(i<0 or i>=len(ids) for i in connectivity)
            or len(element_ids)!=len(elements) or len(set(element_ids))!=len(elements)):
        raise ValueError('VTU must retain complete ordered quadratic tetrahedra and element IDs.')
    actual_cells={e:[actual_ids[i] for i in connectivity[10*k:10*k+10]] for k,e in enumerate(element_ids)}
    if actual_cells!={row['element_id']:row['node_ids'] for row in elements}:
        raise ValueError('VTU connectivity differs from the pinned ordered C3D10 reference mesh.')
    values=np.asarray(_array(point_data,'U_mm',3)).reshape((-1,3))
    if values.shape!=(len(ids),3):raise ValueError('Every reference node requires all three actual U components.')
    by_id=dict(zip(actual_ids,values.tolist()))
    return {'node_ids':ids,'coordinates':coordinates,'elements':elements,'values':[by_id[n] for n in ids],
        'valid_mask':[True]*len(ids),'units':{'position':'mm','displacement':'mm'},
        'coordinate_frame':'FREECAD_DOCUMENT_GLOBAL','geometry':'fixed_reference','static':static,'axis':deepcopy(axis),
        'source':{'reference':deepcopy(source_reference),'vtu_sha256':expected_vtu_sha256,
                  'mesh_sha256':expected_mesh_sha256,'frame_sha256':expected_frame_sha256,
                  'producer':'caelab.adapters.contact_results.write_post -> caelab.adapters.vtu.write_vtu'},
        'qualification':'UNKNOWN','engineering_valid':False}


def read_ccx_displacement(displacement_path, mesh_path, *, expected_displacement_sha256, expected_mesh_sha256, source_reference):
    """Read the existing frozen-FEM JSON producer without changing its verdict."""
    raw=json.loads(_pinned(displacement_path,expected_displacement_sha256))
    mesh=json.loads(_pinned(mesh_path,expected_mesh_sha256))
    ids,coordinates,elements=_mesh(mesh)
    if (raw.get('kind')!='frozen_fem_nodal_displacement' or raw.get('position_unit')!='mm'
            or raw.get('displacement_unit')!='mm' or raw.get('coordinate_frame')!='FREECAD_DOCUMENT_GLOBAL'
            or raw.get('coverage')!='ALL_MESH_NODES' or raw.get('elements')!=mesh['elements']
            or raw.get('input_pins',{}).get('mesh.json',{}).get('sha256')!=expected_mesh_sha256):
        raise ValueError('Displacement JSON and its exact original frozen reference mesh disagree.')
    rows=raw['nodes'];by_id={row['node_id']:row for row in rows}
    if len(by_id)!=len(rows) or set(by_id)!=set(ids):raise ValueError('Incomplete or duplicate source displacement nodes.')
    values=[]
    for n,xyz in zip(ids,coordinates):
        row=by_id[n];u=row.get('displacement_mm')
        if row.get('position_mm')!=xyz or not isinstance(u,list) or len(u)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in u):
            raise ValueError('Reference position or actual displacement components are missing.')
        values.append(deepcopy(u))
    return {'node_ids':ids,'coordinates':coordinates,'elements':elements,'values':values,'valid_mask':[True]*len(ids),
        'units':{'position':'mm','displacement':'mm'},'coordinate_frame':raw['coordinate_frame'],
        'geometry':'fixed_reference','static':_static(raw['static']),
        'axis':{'name':'load_parameter','semantics':'STATIC_LOAD_PARAMETER','unit':'1'},
        'source':{'reference':deepcopy(source_reference),'displacement_sha256':expected_displacement_sha256,
                  'mesh_sha256':expected_mesh_sha256,'native_frd':deepcopy(raw['source']),
                  'producer':'caelab.adapters.frozen_fem.FrozenFemCalculixAdapter'},
        'qualification':raw.get('qualification','UNKNOWN'),'engineering_valid':False}
