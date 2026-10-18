"""Two bonded bulk regions on the existing full-integration Hex8 worker.

Small strain, mm/MPa/s/K. This module supplies material/temperature/BC data;
FELUPE owns quadrature, assembly and Newton. No interface damage is implied.
"""
from copy import deepcopy
import numpy as np
from plugins.material_point import single_branch_native as sls, law_native as law
from plugins.material_point.law_native_tensors import finite, tensor, kelvin, fourth, stiffness
from .adapters.felupe_material import validate_parameters
from .storage import canonical_hash


def layered_mesh(length_mm, width_mm, thicknesses_mm, counts):
    """Explicit rectangular bilayer; cell partitions preserve the shared interface."""
    dims=finite([length_mm,width_mm,*thicknesses_mm],(4,),'bilayer dimensions mm')
    if min(dims)<=0 or len(counts)!=4 or any(type(n) is not int or n<1 for n in counts):
        raise ValueError('Positive length/width/two thicknesses and four positive element counts required')
    nx,ny,n0,n1=counts
    if nx*ny*(n0+n1)>512:raise ValueError('Small FE profile permits at most 512 cells')
    xs=np.linspace(0,dims[0],nx+1);ys=np.linspace(0,dims[1],ny+1)
    zs=np.r_[np.linspace(0,dims[2],n0+1),dims[2]+np.linspace(0,dims[3],n1+1)[1:]]
    points=[[float(x),float(y),float(z)] for z in zs for y in ys for x in xs]
    def ix(i,j,k):return i+(nx+1)*j+(nx+1)*(ny+1)*k
    cells=[];parts=[[],[]]
    for k in range(n0+n1):
        for j in range(ny):
            for i in range(nx):
                parts[int(k>=n0)].append(len(cells))
                cells.append([ix(i,j,k),ix(i+1,j,k),ix(i+1,j+1,k),ix(i,j+1,k),
                              ix(i,j,k+1),ix(i+1,j,k+1),ix(i+1,j+1,k+1),ix(i,j+1,k+1)])
    return {'points':points,'cells':cells,'length_unit':'mm','element':'Hexahedron8',
            'connectivity':'VTK_HEXAHEDRON_0_BASED','quadrature':'Gauss2x2x2'},parts


def reference_start_settings(*, length_mm,width_mm,thicknesses_mm,counts,regions,time_s,
                             temperature_K,time_origin,boundary_mode,reference_start_confirmed):
    """Build from user entries, with an explicit zero-state reference-start choice.

    Boundary presets are declarations saved as actual editable nodal constraints.
    They do not infer missing material properties or temperature assumptions.
    """
    try:nt=len(time_s);temperature_count=len(temperature_K)
    except TypeError:
        raise ValueError('온도 이력에 시간(s)과 절대 온도(K)를 2개 이상 같은 행 수로 입력하세요.') from None
    if nt<2 or temperature_count!=nt:
        raise ValueError('온도 이력에 시간(s)과 절대 온도(K)를 2개 이상 같은 행 수로 입력하세요.')
    if reference_start_confirmed is not True:raise ValueError('Confirm reference-temperature, zero displacement and zero viscous-state start explicitly')
    mesh,parts=layered_mesh(length_mm,width_mm,thicknesses_mm,counts);points=np.asarray(mesh['points'])
    if len(regions)!=2:raise ValueError('Provide two region materials')
    rr=[]
    for i,row in enumerate(regions):
        r=deepcopy(row);r['cell_ids']=parts[i];r['thickness_mm']=thicknesses_mm[i]
        if temperature_K[0]!=r['reference_temperature_K']:raise ValueError('Reference start requires initial temperature equal to each region Tref')
        r['initial_state']=sls.state(time=time_s[0]) if r['model']=='single_branch_maxwell' else {'time':time_s[0],'strain_kelvin':[0.]*6}
        rr.append(r)
    constraints=[]
    def pin(ids,c):constraints.append({'node_ids':list(map(int,ids)),'component':c,'values_mm':[0.]*nt})
    if boundary_mode=='free':
        # Six explicit rigid-mode constraints. Curvature is independent of rigid motion.
        for c in 'xyz':pin([0],c)
        for c in 'yz':pin([counts[0]],c)
        pin([(counts[0]+1)*counts[1]],'z')
    elif boundary_mode=='restrained':
        ids=np.flatnonzero((points[:,0]==0)|(points[:,0]==length_mm))
        for c in 'xyz':pin(ids,c)
    else:raise ValueError('Choose free rigid-mode supports or restrained end faces')
    nx,ny=counts[:2];gauge=[0,nx//2,nx]
    if len(set(gauge))!=3:raise ValueError('Curvature gauge requires at least two x elements')
    s={'mesh':mesh,'boundary':{'mode':'prescribed_displacement','constraints':constraints},
       'solver':{'backend':law.FE,'felupe_version':law.FELUPE_VERSION,'step':'quasistatic','max_iterations':40,'force_tolerance_N':1e-8},
       'compare_point':False,'thermal_regions':{'version':1,'regions':rr,'time_s':list(time_s),'time_origin':time_origin,
       'temperature':{'mode':'uniform_history','unit':'K','values':list(temperature_K)},
       'initial_displacement_mm':np.zeros((len(points),3)).tolist(),
       'observations':{'curvature_nodes':gauge,'integration_points':[{'cell':parts[0][-1],'quadrature':4},{'cell':parts[1][0],'quadrature':0}]}}}
    return validate_settings(s)


def bind_temperature_slot(settings, field):
    """Bind one validated root transfer receipt without replacing another slot.

    Root's mapping adapter supplies an absolute-K Hex8-node capture. This final
    admission also checks destination mesh, exact clock and all node coverage.
    """
    s=validate_settings(settings,require_complete=False);tr=s['thermal_regions'];t=tr['temperature']
    if t['mode']!='port_history':raise ValueError('Select temperature port_history before binding a transfer')
    required={'unit':'K','quantity':'absolute_temperature','component':'scalar','association':'POINTS','location':'node','reduction':'none','coordinate_units':'m','coordinate_frame':'global_cartesian','frame':'global_cartesian','time_units':'s','time_origin':tr['time_origin']}
    for key,expected in required.items():
        if field.get(key)!=expected:raise ValueError('Temperature transfer mismatch: '+key)
    nn=len(s['mesh']['points'])
    if field.get('node_ids')!=list(range(nn)) or field.get('valid_mask')!=[True]*nn:raise ValueError('Temperature transfer must cover every exact receiver node with valid values')
    coords=finite(field.get('coordinates'),(nn,3),'temperature receiver coordinates m')
    if not np.array_equal(coords,np.asarray(s['mesh']['points'])/1000):raise ValueError('Temperature transfer receiver coordinates differ from frozen Hex8 mesh')
    # Root explicitly pins the destination mesh and complete capture, separate from source mesh identity.
    if field.get('receiver_mesh_sha256')!=canonical_hash(s['mesh']):raise ValueError('Temperature transfer receiver mesh identity differs')
    if not isinstance(field.get('capture_sha256'),str) or len(field['capture_sha256'])!=64:raise ValueError('Temperature transfer capture receipt is required')
    time=finite([field.get('time')],(1,),'temperature clock')[0]
    if time not in tr['time_s']:raise ValueError('Temperature transfer does not match an exact receiver history time')
    i=tr['time_s'].index(time)
    if t['values'][i] is not None:raise ValueError('Temperature history slot is already bound; no overwrite')
    values=finite(field.get('value'),(nn,),'temperature nodal values K')
    if min(values)<=0:raise ValueError('Temperature transfer needs positive absolute K')
    t['values'][i]=values.tolist();source=t.setdefault('source',[])
    if not isinstance(source,list):raise ValueError('Temperature source receipts must be a list')
    source.append({'time_s':float(time),'capture_sha256':field['capture_sha256'],'receiver_mesh_sha256':field['receiver_mesh_sha256'],'source_refs':deepcopy(field.get('source_refs'))})
    return validate_settings(s,require_complete=False)


def temperature_values(s, *, require_complete=True):
    tr=s['thermal_regions'];t=tr['temperature'];nt=len(tr['time_s']);nn=len(s['mesh']['points'])
    if not isinstance(t,dict) or set(t)-{'mode','unit','values','source','extrusion'} or not {'mode','unit','values'}<=set(t):
        raise ValueError('Temperature requires mode, unit K and explicit history values')
    if t['unit']!='K' or t['mode'] not in ('uniform_history','nodal_history','port_history'):
        raise ValueError('Choose absolute K uniform_history, nodal_history or temperature port_history')
    if t['mode']=='port_history':
        ex=t.get('extrusion')
        if not isinstance(ex,dict) or set(ex)!={'axis','invariant','statement'} or ex['axis']!='z' or ex['invariant'] is not True or not isinstance(ex['statement'],str) or not ex['statement'].strip():
            raise ValueError('P1-to-Hex8 temperature requires an explicit z-invariant extrusion statement')
    elif 'extrusion' in t:raise ValueError('Extrusion declaration belongs only to temperature port_history')
    if t['mode']=='uniform_history':
        a=finite(t['values'],(nt,),'absolute temperature K')[:,None]*np.ones((1,nn))
    else:
        if not isinstance(t['values'],list) or len(t['values'])!=nt:raise ValueError('One temperature slot per retained time is required')
        if any(row is None for row in t['values']):
            if t['mode']!='port_history' or require_complete:raise ValueError('Temperature port history contains unfilled time slots')
            return None
        a=finite(t['values'],(nt,nn),'nodal absolute temperature K')
    if np.any(a<=0):raise ValueError('Absolute temperature must be positive K; no zero-fill')
    return a


def validate_settings(settings, *, require_complete=True):
    from .law_native_fe import validate_mesh, validate_solver
    if not isinstance(settings,dict) or set(settings)!={'mesh','boundary','solver','compare_point','thermal_regions'}:
        raise ValueError('Thermal FE requires exact mesh/boundary/solver/compare_point/thermal_regions')
    s=deepcopy(settings);validate_mesh(s['mesh']);validate_solver(s['solver'])
    if s['compare_point'] is not False:raise ValueError('A heterogeneous thermal specimen has no homogeneous point comparison')
    tr=s['thermal_regions']
    keys={'version','regions','time_s','time_origin','temperature','initial_displacement_mm','observations'}
    if not isinstance(tr,dict) or not keys<=set(tr) or set(tr)-keys-{'initial_ip_states','continuation'} or tr['version']!=1:raise ValueError('Complete two-region thermal history declaration required')
    times=tr['time_s']
    if not isinstance(times,list) or not 2<=len(times)<=128:raise ValueError('Thermal history needs 2..128 explicit times')
    times=finite(times,(len(times),),'time s')
    if times[0]<0 or times[-1]>1e6 or np.any(np.diff(times)<=0):raise ValueError('Times must increase strictly within 0..1e6 s')
    if not isinstance(tr['time_origin'],str) or not tr['time_origin'].strip():raise ValueError('An explicit time origin is required')
    finite(tr['initial_displacement_mm'],(len(s['mesh']['points']),3),'initial displacement mm')
    regions=tr['regions'];nc=len(s['mesh']['cells']);points=np.asarray(s['mesh']['points'])
    if not isinstance(regions,list) or len(regions)!=2:raise ValueError('Exactly two bonded bulk regions are supported')
    assigned=[];ids=[]
    for r in regions:
        if not isinstance(r,dict) or set(r)!={'id','label','cell_ids','thickness_mm','cte_per_K','reference_temperature_K','model','parameters','initial_state'}:
            raise ValueError('Each region needs identity, actual cells/thickness, CTE/Tref, law and initial state')
        if not all(isinstance(r[k],str) and r[k].strip() for k in ('id','label')):raise ValueError('Each region needs a name and stable identity')
        ids.append(r['id']);cs=r['cell_ids']
        if not isinstance(cs,list) or not cs or any(type(c) is not int or not 0<=c<nc for c in cs):raise ValueError('Region cell membership is invalid')
        assigned+=cs
        xyz=points[np.asarray(s['mesh']['cells'])[cs].ravel()]
        h,alpha,ref=finite([r['thickness_mm'],r['cte_per_K'],r['reference_temperature_K']],(3,),'region thermal coefficients')
        if h<=0 or ref<=0 or not np.isclose(xyz[:,2].ptp() if hasattr(xyz[:,2],'ptp') else np.ptp(xyz[:,2]),h,atol=1e-12,rtol=1e-12):
            raise ValueError('Region thickness must equal its actual reference z extent; Tref must be positive K')
        state=r['initial_state']
        if r['model']=='single_branch_maxwell':sls.validate_parameters(r['parameters']);sls.validate_state(state)
        elif r['model']=='linear_elastic':
            validate_parameters('linear_elastic',r['parameters'])
            if not isinstance(state,dict) or set(state)!={'time','strain_kelvin'}:raise ValueError('Elastic initial state needs time and mechanical strain_kelvin')
            finite(state['strain_kelvin'],(6,),'elastic initial strain')
        else:raise ValueError('Only linear_elastic and small-strain single_branch_maxwell bulk regions are supported')
        if finite([state['time']],(1,),'initial time')[0]!=times[0]:raise ValueError('Region state time must equal first history time')
    if len(set(ids))!=2 or len(assigned)!=nc or set(assigned)!=set(range(nc)):raise ValueError('Two region identities must be distinct and their cells must partition the actual mesh exactly')
    _require_bonded_regions(s['mesh']['cells'],regions)
    if 'initial_ip_states' in tr:
        states=tr['initial_ip_states'];bycell={c:r for r in regions for c in r['cell_ids']}
        if not isinstance(states,list) or len(states)!=8*nc:raise ValueError('Continuation requires every actual quadrature state in q-major/cell-major order')
        for i,state in enumerate(states):
            r=bycell[i%nc]
            if r['model']=='single_branch_maxwell':sls.validate_state(state)
            elif not isinstance(state,dict) or set(state)!={'time','strain_kelvin'}:raise ValueError('Invalid elastic quadrature initial state')
            finite(state['strain_kelvin'],(6,),'initial IP mechanical strain')
            if state['time']!=times[0]:raise ValueError('Every continuation state time must equal the first requested time')
    temperature_values(s,require_complete=require_complete)
    boundary(s,np.asarray(s['mesh']['points']),0)
    obs=tr['observations']
    if not isinstance(obs,dict) or set(obs)!={'curvature_nodes','integration_points'}:raise ValueError('Select a three-node x-z curvature gauge and integration points')
    nodes=obs['curvature_nodes']
    if not isinstance(nodes,list) or len(nodes)!=3 or any(type(i) is not int or not 0<=i<len(points) for i in nodes):raise ValueError('Curvature needs three actual node indices')
    p=points[nodes]
    if len(set(p[:,0]))!=3 or np.any(p[:,1:]!=p[0,1:]):raise ValueError('Curvature gauge nodes must have distinct x and equal reference y,z')
    ips=obs['integration_points']
    if not isinstance(ips,list) or not ips or any(not isinstance(v,dict) or set(v)!={'cell','quadrature'} or type(v['cell']) is not int or not 0<=v['cell']<nc or type(v['quadrature']) is not int or not 0<=v['quadrature']<8 for v in ips):raise ValueError('Choose actual Hex8 cell and quadrature indices 0..7')
    return s


def _require_bonded_regions(cells,regions):
    """Bonding uses actual shared Hex8 faces, never coincident coordinates."""
    faces={};neighbors=[set() for _ in cells]
    for ci,cell in enumerate(cells):
        for local in ((0,1,2,3),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)):
            face=tuple(sorted(cell[i] for i in local))
            faces.setdefault(face,[]).append(ci)
    for shared in faces.values():
        if len(shared)==2:
            a,b=shared;neighbors[a].add(b);neighbors[b].add(a)
    partitions=[set(r['cell_ids']) for r in regions]
    for members in partitions:
        visited=set();pending=[next(iter(members))]
        while pending:
            cell=pending.pop()
            if cell in visited:continue
            visited.add(cell);pending.extend((neighbors[cell]&members)-visited)
        if visited!=members:
            raise ValueError('Each bonded bulk region must be connected by shared full Hex8 faces')
    if not any(neighbors[c]&partitions[1] for c in partitions[0]):
        raise ValueError('Two bonded bulk regions require an actual shared full Hex8 face interface')


def boundary(s,points,index):
    b=s['boundary'];nt=len(s['thermal_regions']['time_s']);nn=len(points)
    if not isinstance(b,dict) or set(b)!={'mode','constraints'} or b['mode']!='prescribed_displacement':raise ValueError('Explicit prescribed_displacement constraints are required')
    prescribed={}
    if not isinstance(b['constraints'],list) or not b['constraints']:raise ValueError('Choose rigid-mode supports or restraints explicitly')
    for row in b['constraints']:
        if not isinstance(row,dict) or set(row)!={'node_ids','component','values_mm'}:raise ValueError('A constraint needs actual nodes, x/y/z component and displacement history mm')
        ids=row['node_ids'];c=row['component']
        if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)) or any(type(n) is not int or not 0<=n<nn for n in ids) or c not in ('x','y','z'):raise ValueError('Invalid constrained node/component selection')
        vals=finite(row['values_mm'],(nt,),'prescribed displacement mm');axis='xyz'.index(c)
        for n in ids:
            dof=3*n+axis
            if dof in prescribed:raise ValueError('Duplicate constrained DOF; select each component once')
            prescribed[dof]=float(vals[index])
    fixed=np.array(sorted(prescribed),int);free=np.setdiff1d(np.arange(points.size),fixed)
    if not len(free):raise ValueError('At least one actual free FE DOF is required')
    # Check the six rigid-body modes only; never invent supports or alter a user's BC.
    centered=points-points.mean(axis=0);scale=max(np.ptp(points,axis=0));modes=np.zeros((points.size,6))
    for i,p in enumerate(centered/scale):
        modes[3*i:3*i+3,:3]=np.eye(3);modes[3*i:3*i+3,3:]=-np.array([[0,-p[2],p[1]],[p[2],0,-p[0]],[-p[1],p[0],0]])
    if np.linalg.matrix_rank(modes[fixed])<6:raise ValueError('Selected supports leave a rigid translation or rotation free')
    return fixed,free,np.array([prescribed[d] for d in fixed])


def describe_model(s):
    s=validate_settings(s,require_complete=False)
    return {'backend':law.FE,'solver':s['solver'],'regions':deepcopy(s['thermal_regions']['regions']),
            'element':'Hexahedron8','quadrature':'Gauss2x2x2','length_unit':'mm','force_unit':'N',
            'strain_measure':'infinitesimal','stress_measure':'infinitesimal_Cauchy',
            'temperature':'absolute K; region Tref subtracted once at constitutive input',
            'interface':'perfectly bonded shared nodes; no damage law',
            'recovery':'finite-time viscoelastic delayed recovery; no permanent plasticity claim',
            'physical_calibration':'UNKNOWN','engineering_release':'UNKNOWN'}


def constitutive(settings,region):
    from .adapters.law_native_fe_worker import FelupeConstitutive
    from .execution_control import check_cancelled
    import felupe as fem
    s=settings;tr=s['thermal_regions'];regions=tr['regions'];temps=temperature_values(s)
    membership={c:r for r in regions for c in r['cell_ids']};nc=len(s['mesh']['cells'])
    h=np.asarray(region.h)[:,:,0]
    class ThermalMaterial(FelupeConstitutive):
        def __init__(self):
            super().__init__({});self.elastic={}
            basis=[tensor(np.eye(6)[j]) for j in range(6)]
            for r in regions:
                if r['model']=='linear_elastic':
                    C=np.asarray(fem.LinearElastic(**r['parameters']).hessian()[0])[:,:,:,:,0,0]
                    CK=np.array([[np.einsum('ij,ijkl,kl',a,C,b) for b in basis] for a in basis])
                    self.elastic[r['id']]=(C,CK)
        def physical(self,r):return tensor(r['stress']),None if r['tangent'] is None else fourth(r['tangent'])
        def batch(self,F):
            F=np.asarray(F);rows=[];ti=tr['time_s'].index(self.time)
            for q in range(F.shape[2]):
                for c in range(nc):
                    check_cancelled();i=q*nc+c;r=membership[c];before=deepcopy(self.accepted[i])
                    try:
                        # The small-strain Field supplies grad(u) directly. Avoid
                        # I+grad(u)-I cancellation in traction-free equilibrium.
                        T=float(h[:,q]@temps[ti,np.asarray(s['mesh']['cells'][c])]);total=(F[:,:,q,c]+F[:,:,q,c].T)/2
                        thermal=np.eye(3)*r['cte_per_K']*(T-r['reference_temperature_K']);mechanical=total-thermal;e=kelvin(mechanical)
                        if np.max(abs(F[:,:,q,c]))>.01+1e-14 or np.max(abs(mechanical))>.01+1e-14:raise ValueError('Thermal profile requires displacement gradient and mechanical strain components <= .01; no large rotation model')
                        if self.initial and not np.allclose(e,before['strain_kelvin'],rtol=0,atol=2e-12):raise ValueError('Initial thermal/mechanical strain differs from explicitly supplied accepted state')
                        if r['model']=='single_branch_maxwell':
                            if self.initial:
                                response=law.initial_response({'model':'single_branch_maxwell','parameters':r['parameters'],'initial_state':before})
                            else:response=sls.integrate(r['parameters'],before,e,self.time)
                        else:
                            C,CK=self.elastic[r['id']]
                            sigma=np.einsum('ijkl,kl->ij',C,mechanical)
                            # Kelvin projection of the existing FELUPE tangent; no new elastic law.
                            response={'stress':kelvin(sigma),'tangent':CK,'state':{'time':self.time,'strain_kelvin':e.tolist()},'stored_energy':float(.5*np.sum(mechanical*sigma)),'dissipated_energy':0.,'diagnostics':{'law':'felupe.LinearElastic','committed':False}}
                        response['thermal']={'region_id':r['id'],'temperature_K':T,'reference_temperature_K':r['reference_temperature_K'],
                            'total_strain_kelvin':kelvin(total).tolist(),'thermal_strain_kelvin':kelvin(thermal).tolist(),
                            'mechanical_strain_kelvin':e.tolist(),'constitutive_input':'mechanical infinitesimal strain, Kelvin6; not physical F'}
                        rows.append(response)
                    except Exception as error:
                        self.last_failure={'quadrature':q,'cell':c,'time':self.time,'initial_state':before,'error':str(error)};raise
            if canonical_hash(self.accepted)!=self.accepted_hash:raise RuntimeError('Thermal trial mutated frozen accepted state')
            return rows
    return ThermalMaterial()


def displacement_field(region):
    """Existing FELUPE kinematics, without adding identity for a linear strain law."""
    import felupe as fem
    class GradientFields(fem.FieldContainer):
        def extract(self,grad=True,sym=False,add_identity=True,**kwargs):
            return super().extract(grad=grad,sym=sym,add_identity=False,**kwargs)
    return GradientFields([fem.Field(region,dim=3)])


def convergence_check(s,solid,field,fixed,free,prescribed):
    """Frozen affine-increment backward error; FELUPE still owns Newton.

    These two bulk laws have a constant discrete tangent during one increment.
    rhs is assembled once at fixed accepted state/time/T, never redefined per
    trial. The existing absolute residual remains active. Thermal increments also
    require a displacement correction below 1e-12 mm; native xtol is infinity.
    """
    from felupe.tools._newton import check as native_check
    from scipy.sparse.linalg import norm as sparse_norm
    K=solid.assemble.matrix(field=field).tocsr()
    f=np.asarray(solid.assemble.vector(field=field).toarray()).reshape(-1)
    u=np.asarray(field[0].values).reshape(-1)
    constant=f-K@u;Kff=K[free][:,free];rhs=-constant[free]-K[free][:,fixed]@prescribed
    knorm=float(sparse_norm(Kff,ord=np.inf));rhsnorm=float(np.linalg.norm(rhs,ord=np.inf))
    raw=[]
    def check(dx,x,f,xtol,ftol,dof1=None,dof0=None,items=None,**kwargs):
        xnorm,native,unused=native_check(dx,x,f,xtol,ftol,dof1=dof1,dof0=dof0,items=None)
        residual=np.asarray(f).reshape(-1)[free]
        actual_u=np.asarray(x[0].values).reshape(-1)[free]
        denominator=knorm*float(np.linalg.norm(actual_u,ord=np.inf))+rhsnorm
        numerator=float(np.linalg.norm(residual,ord=np.inf))
        backward=numerator/denominator if denominator else (0. if numerator==0. else float('inf'))
        absolute=float(np.linalg.norm(residual))
        success=bool(backward<ftol and xnorm<1e-12 and absolute<=s['solver']['force_tolerance_N'])
        raw.append({'native_support_normalized_residual':float(native),'backward_error_inf':backward,
                    'denominator_N':denominator,'absolute_free_force_N':absolute,'success':success})
        if success and items is not None:
            for item in items:item.results.update_statevars()
        return xnorm,backward,success
    return check,{'criterion':'reduced_affine_increment_normwise_infinity_backward_error',
                  'K_ff_inf_N_per_mm':knorm,'rhs_free_inf_N':rhsnorm,'relative_limit':1e-12,
                  'absolute_force_limit_N':s['solver']['force_tolerance_N'],'displacement_increment_limit_mm':1e-12,
                  'zero_denominator':'zero only when residual is exactly zero','iterations':raw}


def initial_states(s,nq):
    if 'initial_ip_states' in s['thermal_regions']:
        if nq!=8:raise ValueError('Continuation quadrature differs from the saved Hex8 eight-point state')
        return deepcopy(s['thermal_regions']['initial_ip_states'])
    bycell={c:r['initial_state'] for r in s['thermal_regions']['regions'] for c in r['cell_ids']}
    return [deepcopy(bycell[c]) for q in range(nq) for c in range(len(s['mesh']['cells']))]


def continue_settings(settings,result,*,time_s,temperature,boundary):
    """A new input from an exact saved accepted prefix, preserving every IP state.

    This is an explicit new run. Reading/reopening a saved result never calls it.
    The caller supplies the future clock, temperatures and prescribed BC history.
    """
    old=validate_settings(settings);diag=result.get('diagnostics',{})
    if diag.get('source_input_sha256')!=canonical_hash(old):raise ValueError('Continuation result does not belong to this exact frozen thermal input')
    steps=diag.get('steps',[])
    if not steps:raise ValueError('No accepted spatial increment is available for continuation')
    last=steps[-1];s=deepcopy(old);tr=s['thermal_regions'];oldtr=old['thermal_regions'];nt=len(time_s)
    if not nt or time_s[0]!=last['time']:raise ValueError('Continuation must start at the exact last accepted time')
    states=[deepcopy(v['state']) for v in last['local']]
    if states!=diag.get('last_accepted_states'):raise ValueError('Accepted IP prefix and last state receipt differ')
    tr['time_s']=list(time_s);tr['temperature']=deepcopy(temperature);s['boundary']=deepcopy(boundary)
    tr['initial_displacement_mm']=deepcopy(last['displacement_mm']);tr['initial_ip_states']=states
    nc=len(s['mesh']['cells'])
    for r in tr['regions']:r['initial_state']=deepcopy(states[r['cell_ids'][0]])
    tr['continuation']={'source_input_sha256':canonical_hash(old),'accepted_increment':last['increment'],
                        'accepted_time_s':last['time'],'accepted_states_sha256':canonical_hash(states),
                        'source_execution_status':result.get('execution_status')}
    previous=temperature_values(old)[oldtr['time_s'].index(last['time'])]
    if not np.array_equal(temperature_values(s)[0],previous):raise ValueError('Continuation initial temperature must equal the accepted previous temperature at every node')
    return validate_settings(s)


def add_responses(s,steps,responses,failed):
    if not steps:return
    axis=[{'name':'time','unit':'s','values':[v['time'] for v in steps]}];obs=s['thermal_regions']['observations'];nc=len(s['mesh']['cells'])
    def series(name,values,unit,measure,selection):
        responses[name]={'kind':'series','value':list(map(float,values)),'unit':unit,'component':name,'location':'selected_geometry' if name=='curvature_xz' else 'integration_point','reduction':'none','axes':deepcopy(axis),'frame':'reference_mesh_cartesian','measure':measure,'selection':selection,'valid':not bool(failed),'partial':bool(failed)}
    ns=obs['curvature_nodes'];x=np.asarray(s['mesh']['points'])[ns,0];V=np.vstack([x*x,x,np.ones(3)]).T
    series('curvature_xz',[2*np.linalg.solve(V,np.asarray(v['displacement_mm'])[ns,2])[0] for v in steps],'1/mm','small_slope_three_node_projected_curvature',{'node_ids':ns,'plane':'x-z','assumption':'small slope; three reference nodes with common y,z'})
    for n,sel in enumerate(obs['integration_points']):
        idx=sel['quadrature']*nc+sel['cell'];local=[v['local'][idx] for v in steps]
        series(f'selected{n}_temperature',[v['thermal']['temperature_K'] for v in local],'K','absolute_temperature',sel)
        for j,label in enumerate(('xx','yy','zz','sqrt2xy','sqrt2xz','sqrt2yz')):
            series(f'selected{n}_stress_{label}',[v['stress'][j] for v in local],'MPa','infinitesimal_Cauchy_Kelvin_component',sel)
            for kind in ('total','thermal','mechanical'):
                series(f'selected{n}_{kind}_strain_{label}',[v['thermal'][kind+'_strain_kelvin'][j] for v in local],'1','infinitesimal_'+kind+'_strain_Kelvin_component',sel)
            if all('viscous_strain_kelvin' in v['state'] for v in local):series(f'selected{n}_viscous_strain_{label}',[v['state']['viscous_strain_kelvin'][j] for v in local],'1','mechanical_internal_viscous_strain_Kelvin_component',sel)
