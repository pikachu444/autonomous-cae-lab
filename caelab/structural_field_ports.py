"""Read pinned existing CCX nodal U on its undeformed C3D10 reference mesh.

No solver, owner, native process or field reconstruction is performed. Static
load parameters remain dimensionless and are never treated as physical time.
"""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
from xml.etree import ElementTree as ET
import numpy as np

from .post_spatial_mapping import tetra10_boundary, selected_boundary

OPERATIONS = tuple('pre.fem.displacement_' + name for name in
                   ('read', 'save', 'preview', 'apply', 'remove'))


def _pinned(path, expected):
    path=Path(path)
    # FreeCAD's embedded Python may lack the executable's longPathAware flag.
    # Read the same exact Windows file with Win32's extended spelling; do not
    # copy, shorten, discover or substitute another source.
    if os.name=='nt':
        absolute=os.path.abspath(path)
        if len(absolute)>=248 and not absolute.startswith('\\\\?\\'):
            path=Path('\\\\?\\UNC\\'+absolute[2:] if absolute.startswith('\\\\') else '\\\\?\\'+absolute)
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


def saved_displacement_sources(workbench):
    """List retained static frames; selection still requires an exact field read.

    No array/native reader, solver or provider is invoked to populate a chooser.
    Current working inputs never replace the saved run's input identity.
    """
    from .storage import load_json, check_id
    rows=[]
    owner=workbench.simulation_documents
    for document in owner.list():
        revision=document.get('saved_revision')
        if not revision:continue
        if not any(run.get('retained_result') and run.get('draft',{}).get('backend') in
                {'structure.calculix.contact','structure.calculix.initial_fields'} for run in document.get('runs',[])):
            continue
        saved=owner._verify_revision(document['id'],revision)
        for index,run in enumerate(saved.get('runs',[])):
            if run.get('draft',{}).get('backend') not in {'structure.calculix.contact','structure.calculix.initial_fields'}:
                continue
            if not run.get('retained_result'):continue
            reference={key:run[key] for key in ('job_id','input_revision','input_sha256')}
            reference.update(document_id=saved['id'],saved_revision=revision)
            retained=run['retained_result']
            if retained.get('job_id')!=run['job_id']:
                raise ValueError('Retained displacement result has a different job identity.')
            retained_revision=check_id(retained['revision'])
            owner._verify_revision(saved['id'],retained_revision)
            root=owner._folder(saved['id'])/'revisions'/retained_revision/'results'/check_id(run['job_id'])
            # Metadata and small frame sidecars only; never hydrate result arrays.
            result=json.loads(_pinned(root/'result.json',load_json(root/'result.sha256.json')['sha256']))
            if result.get('execution_status')!='SUCCEEDED':continue
            artifacts=result.get('artifacts',[])
            for artifact in sorted(artifacts,key=lambda a:a.get('path','')):
                match=re.fullmatch(r'calculation/post/(frame[0-9]{4,8})\.vtu',artifact.get('path',''))
                if match is None or int(match[1][5:])<1:continue
                sidecars=[a for a in artifacts if a.get('path')=='calculation/post/'+match[1]+'.json']
                if len(sidecars)!=1:continue
                frame=json.loads(_pinned(root/sidecars[0]['path'],sidecars[0]['sha256']))
                if frame.get('step_location',{}).get('axis')!={'name':'load_parameter','semantics':'STATIC_LOAD_PARAMETER','unit':'1'}:
                    continue
                rows.append({'reference':{**reference,'frame_id':match[1]},
                    'label':saved['title']+' / 계산 '+str(index+1),'static':_static(frame.get('static')),
                    'units':{'position':'mm','displacement':'mm'},
                    'coordinate_frame':'FREECAD_DOCUMENT_GLOBAL','read_status':'NOT_READ'})
    return rows


def read_saved_displacement(workbench,reference,*,with_proof=False):
    """Resolve pinned result/reference mesh from one immutable saved run.

    Retained result artifacts include its frozen input, so no original registered
    input path or another store is needed when reading a portable saved document.
    """
    from .storage import check_id
    from .evaluation import read_result
    keys={'document_id','saved_revision','job_id','input_revision','input_sha256'}
    if (not isinstance(reference,dict) or set(reference) not in (keys,keys|{'frame_id'})
            or not isinstance(reference['input_sha256'],str)
            or re.fullmatch('[0-9a-f]{64}',reference['input_sha256']) is None):
        raise ValueError('Choose the complete saved displacement result reference.')
    frame_id=reference.get('frame_id','frame0001')
    if (not isinstance(frame_id,str) or re.fullmatch(r'frame[0-9]{4,8}',frame_id) is None
            or int(frame_id[5:])<1):
        raise ValueError('Choose one exact retained displacement frame.')
    for key in ('document_id','saved_revision','job_id','input_revision'):check_id(reference[key])
    if not reference['document_id'].startswith('V'):
        raise ValueError('Choose an existing saved Simulation displacement result.')
    owner=workbench.simulation_documents
    saved=owner._verify_revision(reference['document_id'],reference['saved_revision'])
    runs=[run for run in saved.get('runs',[]) if run['job_id']==reference['job_id']]
    if len(runs)!=1:raise ValueError('The selected job is not in this saved Simulation.')
    run=runs[0]
    if any(run.get(key)!=reference[key] for key in ('job_id','input_revision','input_sha256')):
        raise ValueError('The saved displacement run has a different input identity.')
    if run.get('draft',{}).get('backend') not in {'structure.calculix.contact','structure.calculix.initial_fields'}:
        raise ValueError('This displacement authoring profile requires the existing CCX C3D10 producer.')
    retained=run.get('retained_result')
    if not retained or retained.get('job_id')!=reference['job_id']:
        raise ValueError('Save and retain the exact source result before displacement transfer.')
    owner._verify_revision(reference['document_id'],check_id(retained['revision']))
    result_root=owner._folder(reference['document_id'])/'revisions'/retained['revision']/'results'/reference['job_id']
    result=read_result(result_root,verify='all',selection=[])
    if result.get('execution_status')!='SUCCEEDED':
        raise ValueError('The selected retained displacement calculation did not succeed.')
    files={}
    for name in ('calculation/frozen_input/mesh.json','calculation/post/'+frame_id+'.vtu','calculation/post/'+frame_id+'.json'):
        matches=[row for row in result.get('artifacts',[]) if row.get('path')==name]
        if len(matches)!=1:raise ValueError('The retained result lacks one exact reference mesh/static frame artifact.')
        files[name]=(result_root/name,matches[0]['sha256'])
    mesh,mesh_pin=files['calculation/frozen_input/mesh.json']
    vtu,vtu_pin=files['calculation/post/'+frame_id+'.vtu']
    frame,frame_pin=files['calculation/post/'+frame_id+'.json']
    field=read_ccx_vtu(vtu,mesh,frame,expected_vtu_sha256=vtu_pin,expected_mesh_sha256=mesh_pin,
        expected_frame_sha256=frame_pin,source_reference=reference)
    envelope={'reference':deepcopy(reference),'label':saved['title']+' / 정적 단계 '+str(field['static']['step']),'field':field}
    if not with_proof:return envelope
    from .storage import canonical_hash
    proof={'files':{key:{'path':str(path.resolve()),'sha256':pin}
                    for key,(path,pin) in zip(('mesh','vtu','frame'),
                        ((mesh,mesh_pin),(vtu,vtu_pin),(frame,frame_pin)))},
           'field_sha256':canonical_hash(field)}
    return envelope,proof


def verify_displacement_source(envelope,proof):
    """Recheck the queued immutable source locally on the receiving owner.

    The service alone supplies this private proof. No network, source discovery,
    mutable owner lookup or alternative path is used on the native GUI thread.
    """
    from .storage import canonical_hash
    if (not isinstance(envelope,dict) or set(envelope)!={'reference','label','field'}
            or not isinstance(proof,dict) or set(proof)!={'files','field_sha256'}
            or not isinstance(proof['files'],dict) or set(proof['files'])!={'mesh','vtu','frame'}):
        raise ValueError('The verified retained displacement source is missing.')
    files=proof['files']
    for row in files.values():
        if (not isinstance(row,dict) or set(row)!={'path','sha256'}
                or not isinstance(row['path'],str) or not Path(row['path']).is_absolute()):
            raise ValueError('The retained displacement file proof is incomplete.')
    field=read_ccx_vtu(files['vtu']['path'],files['mesh']['path'],files['frame']['path'],
        expected_vtu_sha256=files['vtu']['sha256'],expected_mesh_sha256=files['mesh']['sha256'],
        expected_frame_sha256=files['frame']['sha256'],source_reference=envelope['reference'])
    if (canonical_hash(field)!=proof['field_sha256'] or field!=envelope['field']
            or not isinstance(envelope['label'],str)):
        raise ValueError('The retained displacement source changed after command admission.')
    return deepcopy(envelope)


def enrich_displacement_command(wb,identifier,operation,arguments,session_id,generation,command_id):
    """Resolve source once for a new command; exact retries retain its receipt."""
    if not isinstance(arguments,dict) or any(not isinstance(k,str) or k.startswith('_') for k in arguments):
        raise ValueError('Private displacement source injection is not allowed.')
    if command_id:
        try:previous=wb.native_commands.status(command_id)
        except KeyError:previous=None
        if previous is not None:
            if ((previous['document_id'],previous['operation'],previous['session_id'],previous['expected_generation'])
                    !=(identifier,operation,session_id,generation)
                    or previous['arguments'].get('_public_arguments')!=arguments):
                raise ValueError('command_id conflicts with an earlier displacement request.')
            return previous,None
    args=deepcopy(arguments)
    args['_public_arguments']=deepcopy(arguments)
    if operation in {'pre.fem.displacement_preview','pre.fem.displacement_apply'}:
        reference=args.get('draft',{}).get('source_reference')
    else:
        reference=args.get('source_reference')
    if reference is not None:
        args['_displacement_source'],args['_displacement_proof']=read_saved_displacement(wb,reference,with_proof=True)
    elif operation in {'pre.fem.displacement_preview','pre.fem.displacement_apply'}:
        raise ValueError('Choose the exact retained displacement source before preview or apply.')
    return None,args


def consume_displacement_source(arguments):
    """Strip only service-owned transport keys and return a locally checked source."""
    args=deepcopy(arguments)
    args.pop('_public_arguments',None)
    envelope=args.pop('_displacement_source',None)
    proof=args.pop('_displacement_proof',None)
    if (envelope is None)!=(proof is None):
        raise ValueError('The retained displacement proof is incomplete.')
    if any(key.startswith('_') for key in args):
        raise ValueError('Unknown private displacement argument.')
    return args,verify_displacement_source(envelope,proof) if envelope is not None else None


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


def bind_transfer_model(captured, receipt, *, replace_condition_ids=()):
    """Add mapped U, replacing only explicitly selected overlapping DOFs.

    Preserve unrelated supports, forces and the user's single STATIC program.
    The native condition/step compilers still own conflicts and every card.
    """
    from .contact_deck import validate_model, name
    from .contact_steps import required_curves, validate_contributions
    from .storage import canonical_hash
    validate_model(captured,allow_unrestrained_capture=True)
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
    conditions=captured['conditions']
    if (not isinstance(replace_condition_ids,(list,tuple))
            or any(not isinstance(cid,str) for cid in replace_condition_ids)
            or len(set(replace_condition_ids))!=len(replace_condition_ids)):
        raise ValueError('교체할 기존 조건을 중복 없이 선택하세요.')
    selected=set(replace_condition_ids)
    target={(r['node_id'],r['component']) for r in dofs}
    eligible={c['object_id'] for c in conditions if c['type'] in
              ('Fem::ConstraintFixed','Fem::ConstraintDisplacement') and
              any((r['node_id'],r['component']) in target for r in c['boundary_dofs'])}
    if not selected<=eligible:
        raise ValueError('교체할 조건이 없거나 선택한 면과 성분에 겹치지 않습니다. 조건을 다시 선택하세요.')
    if eligible-selected:
        labels=[c.get('label',c['object_id']) for c in conditions if c['object_id'] in eligible-selected]
        raise ValueError('기존 조건과 겹칩니다. 교체할 조건을 명시적으로 선택하세요: '+', '.join(labels))
    model=deepcopy(captured);model['conditions']=[]
    for original in conditions:
        condition=deepcopy(original)
        if condition['object_id'] in selected:
            condition['boundary_dofs']=[r for r in condition['boundary_dofs']
                                       if (r['node_id'],r['component']) not in target]
            if not condition['boundary_dofs']:continue
            if condition['type']=='Fem::ConstraintDisplacement':
                remaining={r['component'] for r in condition['boundary_dofs']}
                condition['components_mm']={d:v for d,v in condition['components_mm'].items() if int(d) in remaining}
        model['conditions'].append(condition)
    node_bodies={r['node_id']:r['body_id'] for r in captured['nodes']}
    names={c['object_id'].upper() for c in conditions}
    mapped=[]
    for row in rows:
        n=row['node_id'];values={d:row['displacement_mm'][d-1] for d in components}
        identifier='ImportedDisplacementNode'+str(n)
        suffix=1
        while identifier.upper() in names:
            identifier='ImportedDisplacementNode'+str(n)+'_'+str(suffix);suffix+=1
        names.add(name(identifier).upper())
        mapped.append({'object_id':identifier,'label':'가져온 변위 '+str(n),
            'type':'Fem::ConstraintDisplacement','body_id':node_bodies[n],'targets':[],
            'components_mm':values,'boundary_dofs':[r for r in dofs if r['node_id']==n],
            'source_condition_ids':list(replace_condition_ids)})
    model['conditions'].extend(mapped)
    union={}
    for condition in model['conditions']:
        for row in condition.get('boundary_dofs',[]):
            union.setdefault((row['node_id'],row['component']),deepcopy(row))
    model['boundary_dofs']=list(union.values())
    stage=model['analysis_steps']['steps'][0]
    required=required_curves(model['conditions'])
    stage['curves']=[r for r in stage['curves'] if (r['condition_id'],r['component']) in required]
    for condition in mapped:
        for d,value in condition['components_mm'].items():
            stage['curves'].append({'condition_id':condition['object_id'],'component':d,'unit':'mm',
                                    'points':[[0,0],[stage['duration'],value]]})
    model['displacement_transfer']=deepcopy(receipt)
    model['displacement_transfer'].update(captured_model_sha256=canonical_hash(captured),
        original_conditions=deepcopy(conditions),original_boundary_dofs=deepcopy(captured['boundary_dofs']),
        original_analysis_steps=deepcopy(captured['analysis_steps']),
        replacement_condition_ids=list(replace_condition_ids),
        replacement_mask=deepcopy(dofs),
        replacement_policy='explicit_selected_condition_dof_intersection')
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
    location=frame['step_location']
    if 'analysis_steps' in mesh:
        from .contact_steps import step_location, compile_program
        expected=step_location(mesh,static['step'],static['load_parameter'])
        stages=compile_program(mesh['analysis_steps'],mesh['conditions'])
        coordinate=expected['coordinate']
        if not 0<=coordinate<=stages[static['step']-1]['duration']:
            raise ValueError('Static frame is outside its retained input step.')
    else:
        expected={'index':1,'coordinate':static['load_parameter'],'axis':axis}
    if any(location.get(key)!=expected[key] for key in ('index','coordinate','axis')):
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
