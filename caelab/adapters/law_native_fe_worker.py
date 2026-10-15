"""FELUPE spatial assembly/global solve worker, not a material-point stand-in.

Accepted local states are frozen per time increment. Every global Newton trial
uses the same accepted states; only a converged spatial solve may commit them.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import sys
import traceback
import numpy as np
from plugins.material_point import law_native as law
from plugins.material_point.law_native_history import evaluate_history
from .. import law_native_fe as domain
from ..storage import save_json,load_json,canonical_hash
from ..execution_control import check_cancelled
from ..evaluation import save_evaluation
from .law_native_runtime import runtime_identity


class FelupeConstitutive:
    """FELUPE gradient/hessian ABI, with explicit frozen pre-increment state."""
    def __init__(self,settings):
        self.settings=deepcopy(settings)
        self.x=[np.eye(3),np.zeros(0)]
        self.accepted=None;self.time=None;self.initial=False;self.last_failure=None
        self.calls={'gradient':0,'hessian':0}

    def begin(self,accepted,time,*,initial=False):
        self.accepted=deepcopy(accepted);self.time=float(time);self.initial=initial
        self.accepted_hash=canonical_hash(self.accepted);self.last_failure=None

    def batch(self,F):
        F=np.asarray(F,dtype=float)
        if F.ndim!=4 or F.shape[:2]!=(3,3):
            raise ValueError('FELUPE gradient shape must be (3,3,nq,ncell)')
        rows=[]
        for q in range(F.shape[2]):
            for cell in range(F.shape[3]):
                check_cancelled()
                index=q*F.shape[3]+cell
                try:
                    if self.initial:
                        if not np.allclose(F[:,:,q,cell],self.settings['deformation_gradient'][0],rtol=0,atol=2e-14):
                            raise ValueError('Initial FE gradient differs from accepted homogeneous state')
                        r=law.initial_response(self.settings)
                    else:
                        r=law.update(self.settings,deepcopy(self.accepted[index]),F[:,:,q,cell],self.time)
                    rows.append(r)
                except Exception as error:
                    self.last_failure={'quadrature':q,'cell':cell,'time':self.time,'trial_F':F[:,:,q,cell].tolist(),
                        'initial_state':deepcopy(self.accepted[index]),'initial_state_sha256':canonical_hash(self.accepted[index]),
                        'error':str(error),'partial':deepcopy(getattr(error,'evidence',None))}
                    raise
        if canonical_hash(self.accepted)!=self.accepted_hash:
            raise RuntimeError('FE trial mutated accepted constitutive state')
        return rows

    def gradient(self,x):
        self.calls['gradient']+=1
        F=np.asarray(x[0]);rows=self.batch(F)
        stress=np.zeros_like(F)
        for i,r in enumerate(rows):
            q,c=divmod(i,F.shape[3]);stress[:,:,q,c]=law.physical_response(self.settings,r)[0]
        # Local states are retained by this worker, not hidden in FELUPE's scratch.
        return [stress,np.zeros((0,*F.shape[2:]))]

    def hessian(self,x):
        self.calls['hessian']+=1
        F=np.asarray(x[0]);rows=self.batch(F);C=np.zeros((3,3,3,3,*F.shape[2:]))
        for i,r in enumerate(rows):
            q,c=divmod(i,F.shape[3]);tangent=law.physical_response(self.settings,r)[1]
            if tangent is None:
                raise ValueError('NONDIFFERENTIABLE: no discrete tangent for this FE trial')
            C[:,:,:,:,q,c]=tangent
        return [C]


def _boundary(s,points,index):
    F=np.asarray(s['law']['deformation_gradient'][index]);origin=np.asarray(s['boundary']['origin_mm'])
    prescribed={}
    if s['boundary']['mode']=='affine_boundary':
        for node in domain.boundary_nodes(s['mesh']['cells']):
            for c,value in enumerate((F-np.eye(3))@(points[node]-origin)):
                prescribed[3*node+c]=float(value)
    else:
        lo,hi=points.min(axis=0),points.max(axis=0)
        for node,p in enumerate(points):
            if p[0]==lo[0]:prescribed[3*node]=0.
            if p[0]==hi[0]:prescribed[3*node]=float((F[0,0]-1)*(hi[0]-lo[0]))
            if p[1]==lo[1]:prescribed[3*node+1]=0.
            if p[2]==lo[2]:prescribed[3*node+2]=0.
    dof0=np.array(sorted(prescribed),dtype=int)
    dof1=np.setdiff1d(np.arange(points.size),dof0)
    if not len(dof1):raise ValueError('A spatial solve must have actual free DOFs')
    return dof0,dof1,np.array([prescribed[i] for i in dof0])


def _plain(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,dict):return {k:_plain(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [_plain(v) for v in value]
    return value


def solve(settings,output):
    s=domain.validate_settings(settings);folder=Path(output)
    folder.mkdir(parents=True,exist_ok=False)
    save_json(folder/'frozen-input.json',s)
    try:
        runtime=runtime_identity()
    except Exception as error:
        result={'execution_status':'REJECTED','responses':{},'checks':[],
            'diagnostics':{'execution_layer':'FE','FE_execution':'NOT_RUN','point_execution':'NOT_RUN',
                'reason':str(error),'error_type':type(error).__name__,'build_execution':'NOT_REQUIRED',
                'engineering_release':'UNKNOWN'}}
        save_evaluation(result,folder,existing=True);return result
    save_json(folder/'runtime.json',runtime)
    import felupe as fem
    points=np.asarray(s['mesh']['points']);cells=np.asarray(s['mesh']['cells'])
    mesh=fem.Mesh(points=points,cells=cells,cell_type='hexahedron')
    region=fem.RegionHexahedron(mesh)
    if np.any(np.asarray(region.dV)<=0):raise ValueError('Nonpositive native quadrature/Jacobian volume')
    field=fem.FieldContainer([fem.Field(region,dim=3)])
    field[0].values[:]=(points-np.asarray(s['boundary']['origin_mm']))@(np.asarray(s['law']['deformation_gradient'][0])-np.eye(3)).T
    material=FelupeConstitutive(s['law']);solid=fem.SolidBody(umat=material,field=field)
    F=np.asarray(field.extract()[0]);nq,ncells=F.shape[2:]
    accepted=[deepcopy(s['law']['initial_state']) for _ in range(nq*ncells)]
    steps=[];failed=None;last_values=field[0].values.copy();global_calls=0
    def checkpoint():
        save_json(folder/'fe-progress.json',{'steps':steps,'failed_increment':failed,
            'last_accepted_states':accepted,'last_accepted_displacement_mm':last_values.tolist(),
            'source_sha256':canonical_hash(s),'runtime_sha256':canonical_hash(runtime),
            'point_comparison':'NOT_RUN_UNTIL_FE_FINISHES'})
    checkpoint()
    for index,time in enumerate(s['law']['time']):
        material.begin(accepted,time,initial=index==0)
        before=deepcopy(accepted);before_values=last_values.copy();residuals=[];iteration_trace=[]
        trial_displacement=None
        def observe_iteration(dx,x,iteration,xnorm,fnorm,success):
            nonlocal trial_displacement
            # FELUPE's native fnorm is DIMENSIONLESS, not a residual in N.
            residuals.append(float(fnorm))
            iteration_trace.append({'iteration':int(iteration),'relative_force_residual':float(fnorm),
                'displacement_increment_norm_mm':float(xnorm),'native_success':bool(success)})
            trial_displacement=x[0].values.tolist()
            check_cancelled()
        try:
            dof0,dof1,ext0=_boundary(s,points,index)
            if index:
                global_calls+=1
                solution=fem.newtonraphson(x0=field,items=[solid],dof0=dof0,dof1=dof1,ext0=ext0,
                    tol=domain.FE_LIMITS['native_newton_relative_tolerance'],maxiter=s['solver']['max_iterations'],
                    verbose=False,callback=observe_iteration)
                if not solution.success:raise RuntimeError('FELUPE did not converge')
                field=solution.x;solid.field=field
                force=np.asarray(solution.fun.toarray() if hasattr(solution.fun,'toarray') else solution.fun).reshape(-1)
                iterations=int(solution.iterations);residuals=list(map(float,solution.fnorms))
            else:
                force=np.asarray(solid.assemble.vector(field=field).toarray()).reshape(-1)
                iterations=0
            actual_residual=float(np.linalg.norm(force[dof1]))
            if actual_residual>s['solver']['force_tolerance_N']:
                raise RuntimeError('Native free-DOF equilibrium residual exceeds fixed force tolerance')
            F=np.asarray(field.extract()[0]);rows=material.batch(F)
            stress=np.empty((nq,ncells,3,3));local=[]
            for i,r in enumerate(rows):
                q,c=divmod(i,ncells);stress[q,c]=law.physical_response(s['law'],r)[0]
                local.append({'quadrature_index':q,'cell_index':c,'F':F[:,:,q,c].tolist(),
                    'stress':np.asarray(r['stress']).tolist(),'state':deepcopy(r['state']),
                    'initial_state_sha256':canonical_hash(before[i]),'local':deepcopy(r['diagnostics']),
                    'stored_energy':r['stored_energy'],'dissipated_energy':r['dissipated_energy']})
            reaction=force.reshape(len(points),3)
            balance=float(np.linalg.norm(reaction.sum(axis=0)))
            force_scale=max(1.,float(np.linalg.norm(reaction,axis=1).sum()))
            if balance>domain.FE_LIMITS['relative_force_balance']*force_scale:
                raise RuntimeError('Assembled reaction force balance failed')
            steps.append({'increment':index,'time':time,'time_unit':'s','local':local,
                'displacement_mm':field[0].values.tolist(),'reaction_N':reaction.tolist(),
                'force_residual_N':actual_residual,'force_balance_N':balance,
                'iterations':iterations,'relative_residual_history':residuals,'iteration_trace':iteration_trace,
                'native_relative_tolerance':domain.FE_LIMITS['native_newton_relative_tolerance'],
                'absolute_force_tolerance_N':s['solver']['force_tolerance_N'],'actual_free_dofs':len(dof1),
                'quadrature_weights_mm3':np.asarray(region.dV).tolist()})
            accepted=[deepcopy(r['state']) for r in rows];last_values=field[0].values.copy()
            checkpoint()
        except Exception as error:
            # Do not commit failed global or local trials. Retain the last accepted prefix.
            field[0].values[:]=before_values;accepted=before;last_values=before_values
            failed={'increment':index,'time':time,'error_type':type(error).__name__,'reason':str(error),
                'trial':deepcopy(material.last_failure),'relative_residual_history':residuals,
                'iteration_trace':iteration_trace,'trial_displacement_mm':trial_displacement,
                'last_accepted_state_sha256':canonical_hash(before)}
            checkpoint();break
    compare={'status':'NOT_RUN','reason':'Explicit compare_point is false or FE failed'}
    if s['compare_point'] and not failed:
        point=evaluate_history(s['law']);save_evaluation(point,folder/'point-comparison')
        if point['execution_status']!='SUCCEEDED':
            compare={'status':'FAIL','reason':'Independent point history failed; FE evidence is preserved'}
        else:
            model=s['law']['model'];prefix='dp' if model==law.dp.MODEL else 'neo' if model=='neo_hooke' else 'sls'
            checks=[]
            for fe,pt in zip(steps,point['diagnostics']['constitutive_increments']):
                expected=np.asarray(pt['stress_tensor']);scale=max(1.,float(np.max(abs(expected))))
                limit=domain.FE_LIMITS[prefix+'_stress_atol_mpa']+domain.FE_LIMITS[prefix+'_stress_rtol']*scale
                errors=[];gradient_errors=[]
                for local in fe['local']:
                    stress=np.asarray(local['stress']) if model=='neo_hooke' else law.tensor(local['stress'])
                    errors.append(float(np.max(abs(stress-expected))))
                    gradient_errors.append(float(np.max(abs(np.asarray(local['F'])-np.asarray(pt['F'])))))
                checks.append({'increment':fe['increment'],'max_ip_stress_error_MPa':max(errors),
                    'stress_limit_MPa':limit,'max_ip_F_error':max(gradient_errors),
                    'F_limit':domain.FE_LIMITS['F_absolute'],
                    'status':'PASS' if max(errors)<=limit and max(gradient_errors)<=domain.FE_LIMITS['F_absolute'] else 'FAIL'})
            compare={'status':'PASS' if checks and all(c['status']=='PASS' for c in checks) else 'FAIL',
                     'checks':checks,'comparison':'Every integration point; not a nodal extrapolation or mean stress'}
    save_json(folder/'pair-comparison.json',compare)
    responses={};axis=[{'name':'time','unit':'s','values':[row['time'] for row in steps]}]
    if steps:
        responses['ip_stress']={'kind':'field','value':[[row['stress'] for row in step['local']] for step in steps],
            'unit':'MPa','component':'physical9' if s['law']['model']=='neo_hooke' else 'Kelvin6',
            'components':list(law.F9 if s['law']['model']=='neo_hooke' else law.K6),
            'location':'integration_point','reduction':'none','axes':axis,'frame':law.FRAME,
            'measure':law.declaration(s['law'])['stress_measure'],'valid':not bool(failed),'partial':bool(failed)}
        responses['displacement']={'kind':'field','value':[step['displacement_mm'] for step in steps],
            'unit':'mm','component':'xyz','location':'nodes','reduction':'none','axes':deepcopy(axis),
            'frame':'reference_mesh_cartesian','measure':'displacement','valid':not bool(failed)}
        responses['reaction']={'kind':'field','value':[step['reaction_N'] for step in steps],
            'unit':'N','component':'xyz','location':'nodes','reduction':'none','axes':deepcopy(axis),
            'frame':'reference_mesh_cartesian','measure':'assembled_nodal_reaction','valid':not bool(failed)}
    if steps:
        # Exact selected integration-point curves on the existing Simulation reader.
        # These are actual spatial responses at (cell=0,q=0), NEVER nodal/volume means.
        origin={'cell_index':0,'quadrature_index':0,'quadrature':'Gauss2x2x2',
                'reduction':'none','origin':'ACTUAL_SPATIAL_INTEGRATION_POINT'}
        physical=[np.asarray(step['local'][0]['stress']) if s['law']['model']=='neo_hooke'
                  else law.tensor(step['local'][0]['stress']) for step in steps]
        for i,a in enumerate('xyz'):
            for j,b in enumerate('xyz'):
                responses['ip0_stress_'+a+b]={'kind':'series','value':[float(v[i,j]) for v in physical],
                    'unit':'MPa','component':a+b,'location':'integration_point','reduction':'none',
                    'axes':deepcopy(axis),'frame':law.FRAME,'measure':law.declaration(s['law'])['stress_measure'],
                    'selection':deepcopy(origin),'valid':not bool(failed),'partial':bool(failed)}
        for key in ('stored_energy','dissipated_energy'):
            if all(step['local'][0][key] is not None for step in steps):
                responses['ip0_'+key]={'kind':'series','value':[step['local'][0][key] for step in steps],
                    'unit':'MPa','component':key,'location':'integration_point','reduction':'none',
                    'axes':deepcopy(axis),'frame':law.FRAME,'measure':'energy_per_reference_volume',
                    'selection':deepcopy(origin),'source':'constitutive quadrature output, NOT native global energy',
                    'valid':not bool(failed),'partial':bool(failed)}
    success=not failed and compare['status']!='FAIL' and global_calls>0
    result={'execution_status':'SUCCEEDED' if success else 'FAILED','responses':responses,
        'checks':[{'name':'spatial_FE_equilibrium','status':'PASS' if not failed and global_calls else 'FAIL'},
                  {'name':'same_law_point_FE_pair','status':compare['status'] if compare['status'] in ('PASS','FAIL') else 'NOT_ASSESSED'}],
        'diagnostics':{'execution_layer':'FE','FE_execution':'ACTUAL','point_execution':'ACTUAL' if s['compare_point'] and not failed else 'NOT_RUN',
            'build_execution':'NOT_REQUIRED_FIXED_PYTHON_INTERFACE','runtime':runtime,'mesh':s['mesh'],
            'source_receipt':deepcopy(s.get('source_receipt')),'declaration':domain.describe_model(s),
            'steps':steps,'last_accepted_states':accepted,'failed_increment':failed,'pair_comparison':compare,
            'global_newton_calls':global_calls,'constitutive_calls':material.calls,
            'energy_source':'Constitutive quadrature output, not solver-reported global energy',
            'unavailable':['Global native energy output','ParaView spatial exporter for this dedicated Hex8 pair'],
            'physical_calibration':'UNKNOWN','strength':'UNKNOWN','engineering_release':'UNKNOWN'}}
    save_evaluation(result,folder,existing=True)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args(argv)
    try:
        result=solve(load_json(args.input),args.output)
        return 0 if result['execution_status']=='SUCCEEDED' else 2
    except Exception as error:
        folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
        save_json(folder/'worker-failure.json',{'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()})
        traceback.print_exc();return 3


if __name__=='__main__':sys.exit(main())
