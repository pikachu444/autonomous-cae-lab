"""Typed law assignment on the existing FEM editor/FreeCAD transaction owner."""
from copy import deepcopy
import json
import numpy as np
from caelab import material_fe_transfer as transfer
from caelab.storage import canonical_hash
from caelab.law_native_identity import (semantic_target, capture_proxy, stable_native_text,
                                        require_native_version)
from .nonlinear_material import _selection, native_type

OPERATIONS = transfer.OPERATIONS
READ_ONLY = transfer.READ_ONLY
SELECTION = {'analysis_id','material_id','region_id','mesh_id','solver_id'}
# FreeCAD/SMESH local Hex8 ordering -> right-handed VTK/FELUPE Hex8.
# Fixed reference-coordinate reflection, not geometry-based node guessing.
SMESH_TO_VTK = (0,3,2,1,4,7,6,5)


def _semantic(target):
    return semantic_target(target)


def _native_value(value, *, owner=None):
    if value is None or isinstance(value,(str,bool,int,float)):
        return value
    if hasattr(value,'Name') and hasattr(value,'Document'):
        if owner is None or value.Document is not owner.doc:
            raise ValueError('LAW_NATIVE_REFERENCE_UNSUPPORTED: only exact same-document specimen links are admitted')
        return {'object_id':value.Name,'document_id':owner.document_id}
    if isinstance(value,(tuple,list)):
        return [_native_value(v,owner=owner) for v in value]
    if isinstance(value,dict):
        return {str(k):_native_value(v,owner=owner) for k,v in value.items()}
    return stable_native_text(value)


def _physics(obj, *, owner=None):
    # Existing native properties are identity data, not inferred material inputs.
    if owner is not None and obj.Document is not owner.doc:
        raise ValueError('LAW_NATIVE_REFERENCE_UNSUPPORTED: Analysis member belongs to another document')
    ignored={'Shape','FemMesh','Mesh','Label','Label2','ExpressionEngine','Visibility',transfer.PROPERTY}
    props={}
    for name in getattr(obj,'PropertiesList',()):
        if name not in ignored and not name.startswith('CAELab'):
            try:
                value=getattr(obj,name)
                props[name]=(capture_proxy(value,native_type(obj)) if name=='Proxy' else _native_value(value,owner=owner))
            except Exception as error:raise ValueError('Cannot inspect native property '+obj.Name+'.'+name) from error
    return {'object_id':obj.Name,'type':native_type(obj),'properties':props}


def capture(fem, selection):
    if not isinstance(selection,dict) or set(selection)!=SELECTION:
        raise ValueError('Select exact analysis/material/region/mesh/native solver IDs')
    owner=fem.owner
    require_native_version(owner.App.Version())
    base=owner._object(selection['material_id'])
    analysis=_selection(fem,base,selection['analysis_id'])
    mesh=owner._object(selection['mesh_id']);solver=owner._object(selection['solver_id'])
    if mesh not in analysis.Group or solver not in analysis.Group or not hasattr(mesh,'FemMesh'):
        raise ValueError('Mesh and native context solver must belong to this exact Analysis')
    if native_type(solver) != 'Fem::SolverCcxTools':
        raise ValueError('Select the Analysis CalculiX solver as the native context; FELUPE performs this specimen run')
    if getattr(mesh,'Suppressed',False) or getattr(solver,'Suppressed',False):
        raise ValueError('Select active native mesh and solver context')
    region,source,names=fem._region(selection['region_id'])
    if names not in ([],['Solid1']) or len(source.Shape.Solids)!=1:
        raise ValueError('This FE pair requires one exact whole-solid region; no partial/multibody reassignment')
    if getattr(mesh,'Shape',None) is not source:
        raise ValueError('Native mesh source differs from the selected whole-solid region')
    from .fem_edit import _references, _mesh_hash, _target
    refs=_references(base)
    if refs not in ([],[{'object_id':source.Name,'subelements':names}],
                   [{'object_id':source.Name,'subelements':['Solid1']}],
                   [{'object_id':source.Name,'subelements':[]} ]):
        raise ValueError('Existing material references a different region')
    active=[o for o in analysis.Group if not getattr(o,'Suppressed',False)]
    errors=[]
    others=[o.Name for o in active if native_type(o)=='Fem::MaterialCommon' and o is not base]
    if others:errors.append('Only one active whole-solid material is admitted: '+','.join(others))
    excluded=('Contact','Tie','Beam','Shell','MechanicalNonlinear')
    if any(any(word in native_type(o) for word in excluded) for o in active):
        errors.append('Existing contact/J2/shell/beam physics cannot be overridden by this dedicated specimen pair')
    if any(native_type(o).startswith('Fem::Constraint') for o in active):
        errors.append('Native loads/constraints exist. Use a separate specimen Analysis; they cannot be silently replaced')
    data=fem._metadata()
    if (selection['analysis_id'] in data.get('dynamic_programs',{}) or
        any(r.get('analysis_id')==analysis.Name for r in data.get('contact_programs',[]))):
        errors.append('Dynamic/contact steps are outside the quasistatic pair')
    native=mesh.FemMesh
    ids=sorted(native.Nodes);index={key:i for i,key in enumerate(ids)}
    nodes=[[float(native.Nodes[i].x),float(native.Nodes[i].y),float(native.Nodes[i].z)] for i in ids]
    # Placement is deliberately not silently converted into a second frame.
    placement=mesh.getGlobalPlacement() if hasattr(mesh,'getGlobalPlacement') else getattr(mesh,'Placement',None)
    if placement is not None:
        if hasattr(placement,'toMatrix'):
            matrix=np.asarray(placement.toMatrix().A,dtype=float).reshape(4,4)
            identity=np.array_equal(matrix,np.eye(4))
        elif hasattr(placement,'isIdentity'):
            identity=bool(placement.isIdentity())
        else:
            raise ValueError('Native mesh placement cannot be inspected; no assumed identity frame')
        if not identity:
            errors.append('Native mesh global placement is nonidentity; freeze coordinates explicitly in Pre first')
    volumes=sorted(native.Volumes);connectivity=[];raw=[]
    for element in volumes:
        cell=list(native.getElementNodes(element));raw.append([element,cell])
        if len(cell)!=8:raise ValueError('This pair only accepts native linear Hex8 volumes')
        mapped=[index[cell[i]] for i in SMESH_TO_VTK]
        p=np.asarray([nodes[i] for i in mapped])
        if np.linalg.det(np.stack((p[1]-p[0],p[3]-p[0],p[4]-p[0]),axis=1))<=0:
            raise ValueError('Native Hex8 ordering/Jacobian differs from the declared SMESH convention; no guessed repair')
        connectivity.append(mapped)
    frozen={'points':nodes,'cells':connectivity,'length_unit':'mm','element':'Hexahedron8',
            'connectivity':'VTK_HEXAHEDRON_0_BASED','quadrature':'Gauss2x2x2'}
    guarded_metadata={k:v for k,v in data.items() if k not in
                      ('law_native_drafts','law_native_assignments','document_id','session_id')}
    return {'document_id':owner.document_id,'session_id':owner.session_id,'generation':owner.generation,
        'selection':deepcopy(selection),'analysis_id':analysis.Name,'region':deepcopy(region),
        'geometry':_target(source,names),'material':_physics(base,owner=owner),
        'current_assignment_property':str(getattr(base,transfer.PROPERTY,'')),
        'native_analysis_members':[_physics(o,owner=owner) for o in analysis.Group],
        'native_context_solver':_physics(solver,owner=owner),'execution_backend':transfer.law.FE,
        'execution_version':transfer.law.FELUPE_VERSION,'native_solver_is_not_executed':True,
        'mesh':frozen,'mesh_sha256':canonical_hash(frozen),'native_mesh_sha256':_mesh_hash(native),
        'native_node_ids':ids,'native_element_nodes':raw,'native_to_vtk_permutation':list(SMESH_TO_VTK),
        'metadata_sha256':canonical_hash(guarded_metadata),'admission_errors':errors}


def _record(fem,selection):
    rows=[r for r in fem._metadata().get('law_native_assignments',[])
          if (r.get('analysis_id'),r.get('material_id'))==(selection['analysis_id'],selection['material_id'])]
    if len(rows)>1:raise ValueError('Duplicate law assignment records')
    return deepcopy(rows[0]) if rows else None


def read(fem, selection):
    record=_record(fem,selection)
    if record:transfer.cold_assignment(record)
    drafts=[r for r in fem._metadata().get('law_native_drafts',[])
            if r['selection']==selection]
    # Cold read does not inspect shape, require packages or evaluate/update a law.
    base=fem.owner._object(selection['material_id'])
    value=str(getattr(base,transfer.PROPERTY,''))
    if record and value!=record['native_property']:
        raise ValueError('Retained law assignment and native property differ')
    if value and not record:raise ValueError('Native law property has no retained source assignment')
    return {'assignment':record,'drafts':deepcopy(drafts),'executed':False}


def save(fem, selection, raw):
    if not isinstance(raw,dict) or len(json.dumps(raw,allow_nan=False).encode('utf-8'))>96*1024:
        raise ValueError('Transfer draft must be a literal JSON object of at most 96 KiB')
    fem._assert_idle()
    def change():
        data=fem._metadata()
        rows=[r for r in data.get('law_native_drafts',[]) if r['selection']!=selection]
        rows.append({'selection':deepcopy(selection),'raw':deepcopy(raw),'applied':False})
        data['law_native_drafts']=rows;fem.owner.write_metadata(data)
    fem._transaction('재료 전달 초안 저장',change)
    return {'saved_draft':deepcopy(raw),'applied':False,'executed':False}


def apply(fem,selection,review):
    fem._assert_idle()
    transfer.verify_review(review,capture(fem,selection))
    base=fem.owner._object(selection['material_id']);result={}
    def change():
        # Recheck while in the existing native transaction, immediately before write.
        transfer.verify_review(review,capture(fem,selection))
        token=json.dumps({'backend':transfer.law.FE,'review_sha256':review['review_sha256'],
                          'source_sha256':review['source']['snapshot_sha256']},sort_keys=True)
        if transfer.PROPERTY not in base.PropertiesList:
            base.addProperty('App::PropertyString',transfer.PROPERTY,'CAE Lab Material Law',
                             'Explicit saved Material interface. Not a CalculiX material card.')
        setattr(base,transfer.PROPERTY,token)
        base.setEditorMode(transfer.PROPERTY,1)
        record={'schema':transfer.SCHEMA,'analysis_id':selection['analysis_id'],
                'material_id':selection['material_id'],'selection':deepcopy(selection),
                'review':deepcopy(review),'native_property':token,
                'applied_target':_semantic(capture(fem,selection)),
                'applied':True,'executed':False,'old_native_material_unchanged':True}
        record['assignment_sha256']=canonical_hash(record)
        data=fem._metadata()
        data['law_native_assignments']=[r for r in data.get('law_native_assignments',[])
            if (r['analysis_id'],r['material_id'])!=(selection['analysis_id'],selection['material_id'])]+[record]
        fem.owner.write_metadata(data)
        # If another source writer races the native transaction, abort rather than
        # guessing success. Original FreeCAD transaction owns rollback.
        transfer.verify_source(review['source'],live=True,current_code=True)
        result.update(assignment=deepcopy(record),applied=True,executed=False)
    fem._transaction('저장 재료 법칙 명시 적용',change)
    return result


def freeze(fem,selection):
    record=read(fem,selection)['assignment']
    if record is None:raise ValueError('Explicitly apply a reviewed saved Material first')
    target=capture(fem,selection)
    if _semantic(target)!=_semantic(record['applied_target']):
        raise ValueError('ASSIGNMENT_STALE: native analysis/region/mesh/material/step changed after Apply')
    # New Material revisions do not retroactively replace an already applied law.
    # Current trusted kernel must still implement the exact retained source.
    transfer.verify_source(record['review']['source'],current_code=True)
    settings=deepcopy(record['review']['interface']['settings'])
    settings['mesh']=target['mesh']
    settings['source_receipt']=record
    transfer.fe.validate_settings(settings)
    return {'simulation_draft':{'backend':transfer.law.FE,'settings':settings},
            'native_target':target,'assignment_sha256':record['assignment_sha256'],
            'executed':False,'notice':'Open existing Simulation owner, then explicitly evaluate; no implicit job'}


def dispatch(fem,operation,arguments,target):
    if target:raise ValueError('Use explicit selection, not a second native target')
    args=deepcopy(arguments)
    args.pop('_public_arguments',None)
    if 'selection' not in args:raise ValueError('Choose exact native FEM selection')
    selection=args.pop('selection')
    if set(selection)!=SELECTION:raise ValueError('Incomplete native FEM selection')
    if operation=='pre.fem.law_read' and not args:return read(fem,selection)
    if operation=='pre.fem.law_save' and set(args)=={'raw'}:return save(fem,selection,args['raw'])
    if operation=='pre.fem.law_preview' and set(args)=={'_source_snapshot','options'}:
        return {'review':transfer.make_review(args['_source_snapshot'],capture(fem,selection),args['options']),
                'executed':False}
    if operation=='pre.fem.law_apply' and set(args)=={'_review'}:return apply(fem,selection,args['_review'])
    if operation=='pre.fem.law_freeze' and not args:return freeze(fem,selection)
    raise ValueError('Unsupported law native command arguments')
