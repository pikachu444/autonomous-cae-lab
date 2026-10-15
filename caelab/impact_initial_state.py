"""Exact homogeneous C3D4 initial integrals, not a rigid-body solver.

Linear tetrahedral shape functions integrate mass, COM, the full inertia tensor
and the INITIAL kinetic energy. A declaration of angular velocity does not turn
a deformable mesh into an /RBODY. Unsupported integration is explicitly UNKNOWN.
"""
from copy import deepcopy
import math
import numpy as np


def rotation_matrix(value):
    """Accept only an explicitly supplied proper orthonormal model-global map."""
    if (not isinstance(value,list) or len(value)!=3 or
            any(not isinstance(row,list) or len(row)!=3 for row in value) or
            any(type(x) not in (int,float) or not math.isfinite(x) for row in value for x in row)):
        raise ValueError('초기 자세에는 유한한 3×3 회전행렬을 지정하세요')
    r=np.asarray(value,dtype=float)
    if not np.allclose(r.T@r,np.eye(3),rtol=0,atol=1e-10) or not math.isclose(float(np.linalg.det(r)),1.,rel_tol=0,abs_tol=1e-10):
        raise ValueError('초기 자세는 반사·늘림·전단이 없는 오른손 회전이어야 합니다')
    return r


def validate_motion(model, motion, gravity):
    pose=motion.get('pose')
    if pose is not None:
        if not isinstance(pose,dict) or set(pose)!={'rotation','frame','vector_frame'}:
            raise ValueError('초기 자세의 회전·기준계·속도 성분 기준계를 명시하세요')
        if pose['frame']!='MODEL_GLOBAL' or pose['vector_frame'] not in ('MODEL_GLOBAL','INITIAL_BODY'):
            raise ValueError('초기 자세/속도의 좌표계를 명시하세요')
        rotation_matrix(pose['rotation'])
    if pose is not None or any(motion['translation_mm']) or motion['mode']=='release_height':
        members=model['nsets'][motion['node_set']]
        for element in model['elements'].values():
            used=set(element['nodes'])
            if used&members and not used<=members:
                raise ValueError('강체 초기 자세변환은 요소의 전체 절점 집합에 적용하세요')
    if motion.get('mode')=='velocity' and motion.get('height_mm') not in (None,0,0.):
        raise ValueError('측정 속도와 같은 비행 구간 높이를 중복 적용하지 마세요')
    ids=model['nsets'][motion['node_set']]
    fixed=set()
    for block in model['blocks']:
        if block['card']!='BOUNDARY':continue
        for _,line in block['rows']:
            row=[p.strip().upper() for p in line.split(',')]
            nodes={int(row[0])} if row[0].isdigit() else model['nsets'][row[0]]
            lo=int(row[1]);hi=int(row[2]) if len(row)>2 and row[2] else lo
            fixed.update((n,a) for n in nodes for a in range(lo,hi+1))
    if fixed:
        nodes,velocities,_=motion_state(model,motion,gravity)
        for n,a in fixed:
            if n in ids and velocities[n][a-1]!=0:
                raise ValueError('초기 속도와 고정 병진 자유도가 충돌합니다')


def motion_state(model, motion, gravity):
    center=np.asarray(motion['center_mm'],float)
    shift=np.asarray(motion['translation_mm'],float)
    velocity=np.asarray(motion['velocity_mm_s'],float)
    omega=np.asarray(motion['omega_rad_s'],float)
    pose=motion.get('pose');rotation=np.eye(3) if pose is None else rotation_matrix(pose['rotation'])
    if pose is not None and pose['vector_frame']=='INITIAL_BODY':
        velocity=rotation@velocity;omega=rotation@omega
    g=math.hypot(*gravity)
    if motion['mode']=='release_height':shift=shift-motion['height_mm']*np.asarray(gravity)/g
    if motion['mode']=='impact_height':velocity=np.asarray(gravity)/g*math.sqrt(2*g*motion['height_mm'])
    nodes={};velocities={}
    for n in model['nsets'][motion['node_set']]:
        radius=rotation@(np.asarray(model['nodes'][n])-center)
        nodes[n]=(center+radius+shift).tolist()
        velocities[n]=(velocity+np.cross(omega,radius)).tolist()
    return nodes,velocities,{'node_set':motion['node_set'],'mode':motion['mode'],
        'rotation':rotation.tolist(),'translation_mm':shift.tolist(),'rotation_center_before_mm':center.tolist(),
        'rotation_center_after_mm':(center+shift).tolist(),'velocity_at_center_mm_s':velocity.tolist(),
        'omega_rad_s':omega.tolist(),'vector_frame':'MODEL_GLOBAL',
        'height_segment':{'release_height':'SIMULATED_FLIGHT_FROM_TRANSLATIONAL_REST','impact_height':'OMITTED_FLIGHT_ENERGY_TO_SPEED',
                          'velocity':'MEASURED_INITIAL_STATE'}[motion['mode']],
        'position_rule':'R*(x-center)+center+translation; velocity=V+omega cross R*(x-center)'}


def _integral(model, coordinates, velocities, selected=None):
    items=[(eid,e) for eid,e in model['elements'].items() if selected is None or set(e['nodes'])<=selected]
    if not items:return {'status':'UNKNOWN','reason':'No complete volume elements in this selection'}
    if any(e['type']!='C3D4' for _,e in items):
        return {'status':'UNKNOWN','reason':'Exact initial volume integration is declared only for homogeneous C3D4'}
    entries=[];first=np.zeros(3);total=0.;energy=0.;momentum=np.zeros(3)
    for eid,element in items:
        x=np.asarray([coordinates[n] for n in element['nodes']],float)
        determinant=float(np.linalg.det((x[1:]-x[0]).T))
        if not math.isfinite(determinant) or determinant<=0:
            raise ValueError('C3D4 질량 적분에는 양의 유향 체적이 필요합니다: '+str(eid))
        material=model['materials'][model['assignment'][eid]]
        density=material['DENSITY'][0][0]
        mass=determinant/6*density
        if not math.isfinite(mass) or mass<=0:raise ValueError('C3D4 질량이 비물리적입니다')
        center=x.mean(axis=0)
        # Exact central covariance for a uniform tetrahedron: sum(di di^T)/20.
        d=x-center;covariance=d.T@d/20
        inertia=mass*(np.trace(covariance)*np.eye(3)-covariance)
        v=np.asarray([velocities.get(n,[0.,0.,0.]) for n in element['nodes']],float)
        if v.shape!=(4,3) or not np.isfinite(v).all():raise ValueError('초기 속도 적분 성분을 확인하세요')
        # ∫Na Nb dV = V(1+delta_ab)/20, including off-diagonal terms.
        kinetic=mass/40*(float(np.sum(v*v))+float(np.dot(v.sum(axis=0),v.sum(axis=0))))
        energy+=kinetic;momentum+=mass*v.mean(axis=0);total+=mass;first+=mass*center
        entries.append((mass,center,inertia))
    center=first/total;tensor=np.zeros((3,3))
    for mass,c,inertia in entries:
        d=c-center;tensor+=inertia+mass*(float(d@d)*np.eye(3)-np.outer(d,d))
    principal,basis=np.linalg.eigh(tensor)
    if principal[0]<=0 or principal[2]>principal[0]+principal[1]+max(principal[2]*1e-12,1e-25):
        raise ValueError('전체 관성 텐서가 물리 관성의 양의 값/삼각 부등식을 만족하지 않습니다')
    ambiguous=any(abs(principal[i+1]-principal[i])<=max(abs(principal[-1])*1e-10,1e-30) for i in range(2))
    return {'status':'CALCULATED_FROM_INPUT','representation':'HOMOGENEOUS_LINEAR_TETRA_VOLUME_INTEGRAL',
        'rigid_constraint':'NOT_INFERRED','frame':'MODEL_GLOBAL','mass_Mg':total,'com_mm':center.tolist(),
        'inertia_at_com_Mg_mm2':tensor.tolist(),'principal_moments_Mg_mm2':principal.tolist(),
        'principal_axes':None if ambiguous else basis.tolist(),'principal_axes_status':'DEGENERATE_SUBSPACE' if ambiguous else 'EIGENVECTORS_COLUMNS_SIGN_AMBIGUOUS',
        'kinetic_energy_N_mm':energy,'momentum_Mg_mm_s':momentum.tolist(),
        'units':{'mass':'Mg','position':'mm','inertia':'Mg mm^2','energy':'N mm','omega':'rad/s'},
        'element_count':len(items),'native_comparison':'NOT_RUN'}


def describe(model, initial, settings):
    before=_integral(model,model['nodes'],{})
    after=_integral(model,initial['nodes'],initial['velocities_mm_s'])
    bodies=[]
    for motion in settings['motions']:
        selected=model['nsets'][motion['node_set']]
        bodies.append({'node_set':motion['node_set'],
            'before':_integral(model,model['nodes'],{},selected),
            'initial':_integral(model,initial['nodes'],initial['velocities_mm_s'],selected)})
    return {'kind':'INPUT_DERIVED_INITIAL_STATE_NOT_NATIVE_MEASUREMENT','original':before,'initial':after,
            'bodies':bodies,'native_body_mass_inertia':'UNKNOWN','solver_rigidity':'NOT_INFERRED',
            'mass_scaling':deepcopy(settings['time'])}
