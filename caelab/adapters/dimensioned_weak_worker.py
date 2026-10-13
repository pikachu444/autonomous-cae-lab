"""Captured FEniCSx worker for the explicitly dimensioned linear scalar form."""
from pathlib import Path
import hashlib
import json
import math
import os
import sys


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value): Path(path).write_text(json.dumps(value,allow_nan=False,sort_keys=True),encoding='utf-8')


def main(input_path):
    output=Path(input_path).resolve().parent
    manifest=json.loads((output/'sources.json').read_text(encoding='utf-8'))
    for name,digest in manifest.items():
        if Path(name).name!=name or sha(output/name)!=digest: raise ValueError('Captured weak-form source changed')
    sys.path.insert(0,str(output));sys.dont_write_bytecode=True
    from dimensioned_expression import parse,evaluate,Meaning,UNITS,unit_dimension
    from dimensioned_models import validate_settings,parameters,WEAK
    settings=validate_settings(WEAK,json.loads(Path(input_path).read_text(encoding='utf-8')))
    for name in ('PETSC_OPTIONS','PETSC_OPTIONS_YAML'): os.environ.pop(name,None)
    import petsc4py
    petsc4py.init(['caelab_dimensioned_weak','-skip_petscrc'])
    from petsc4py import PETSc
    if PETSc.Options().getAll()!={'skip_petscrc':None}: raise RuntimeError('Ambient PETSc options are not allowed')
    from mpi4py import MPI
    import numpy as np
    import dolfinx,ufl
    from dolfinx import fem,mesh,io
    from dolfinx.fem.petsc import LinearProblem
    if MPI.COMM_WORLD.size!=1 or np.dtype(PETSc.ScalarType)!=np.dtype('float64'):
        raise RuntimeError('Dimensioned weak form requires serial real64 FEniCSx')
    symbols,coefficients=parameters(settings)
    symbols.update(pi=Meaning(),x=Meaning(UNITS['m']),y=Meaning(UNITS['m']))
    basic=dict(symbols);dim=unit_dimension(settings['field']['unit'])
    symbols.update(u=Meaning(dim,0,(1,0)),v=Meaning(dim,0,(0,1)))
    a_tree=parse(settings['forms']['bilinear'],symbols,weak=True)[0]
    l_tree=parse(settings['forms']['linear'],symbols,weak=True)[0]
    functions={name:getattr(ufl,name) for name in ('sin','cos','exp','sqrt','grad','inner')}
    functions['log']=ufl.ln
    numeric={name:getattr(np,name) for name in ('sin','cos','exp','sqrt','log')}
    studies=[];fields=[];responses={}
    lx,ly=settings['domain']['width'],settings['domain']['height']
    def finite(value):
        result=float(value)
        if not math.isfinite(result): raise RuntimeError('Nonfinite native weak-form output')
        return result
    for n in settings['mesh']['levels']:
        level=output/('level_'+str(n));level.mkdir()
        rectangle=mesh.create_rectangle(MPI.COMM_WORLD,[np.array([0.,0.]),np.array([lx,ly])],
                                        [n,n],cell_type=mesh.CellType.triangle)
        V=fem.functionspace(rectangle,('Lagrange',1))
        x=ufl.SpatialCoordinate(rectangle)
        # Keep zero dimensional coefficients as UFL constants: zero source must
        # retain the form's test argument instead of collapsing to Python zero.
        env={k:fem.Constant(rectangle,PETSc.ScalarType(v)) for k,v in coefficients.items()}
        env.update(pi=math.pi,x=x[0],y=x[1],u=ufl.TrialFunction(V),v=ufl.TestFunction(V))
        dx=ufl.Measure('dx',domain=rectangle,metadata={'quadrature_degree':8})
        a=evaluate(a_tree,env,functions)*dx;L=evaluate(l_tree,env,functions)*dx
        positions={'left':(0,0.),'right':(0,lx),'bottom':(1,0.),'top':(1,ly)}
        boundary=fem.Function(V);assigned={}
        for bc in settings['boundaries']:
            axis,position=positions[bc['side']]
            facets=mesh.locate_entities_boundary(rectangle,1,lambda x,axis=axis,position=position: np.isclose(x[axis],position,rtol=1e-12,atol=1e-12))
            nodes=fem.locate_dofs_topological(V,1,facets)
            tree=parse(bc['expression'],basic)[0]
            probe=fem.Function(V)
            def boundary_values(x,tree=tree):
                values=evaluate(tree,{**coefficients,'pi':math.pi,'x':x[0],'y':x[1]},numeric)
                return np.broadcast_to(np.asarray(values,dtype=float),x.shape[1]).copy()
            probe.interpolate(boundary_values)
            for node in nodes:
                value=finite(probe.x.array[node])
                if int(node) in assigned and not math.isclose(assigned[int(node)],value,rel_tol=1e-12,abs_tol=1e-12):
                    raise ValueError('Conflicting Dirichlet values at a shared corner')
                assigned[int(node)]=value;boundary.x.array[node]=value
        boundary.x.scatter_forward()
        bc=fem.dirichletbc(boundary,np.asarray(sorted(assigned),dtype=np.int32))
        problem=LinearProblem(a,L,bcs=[bc],petsc_options_prefix=f'cae_dimensioned_{n}_',
                              petsc_options={'ksp_type':'preonly','pc_type':'lu'})
        solution=problem.solve();solution.x.scatter_forward();solution.name=settings['field']['name']
        residual=problem.b.duplicate();problem.A.mult(problem.x,residual);residual.axpy(-1.,problem.b)
        absolute=finite(residual.norm());denominator=finite(problem.b.norm());residual.destroy()
        relative=absolute/denominator if denominator>0 else absolute
        reason=problem.solver.getConvergedReason()
        nodes=V.dofmap.index_map.size_local
        ids=V.dofmap.index_map.local_to_global(np.arange(nodes,dtype=np.int32)).astype(int).tolist()
        coordinates=V.tabulate_dof_coordinates()[:nodes].tolist()
        values=[finite(v) for v in solution.x.array[:nodes]]
        cells=[list(map(int,V.dofmap.cell_dofs(i))) for i in range(rectangle.topology.index_map(2).size_local)]
        field={'node_ids':ids,'coordinates':coordinates,'values':values,'components':[solution.name],
               'association':'POINTS','cell_node_ids':[[ids[j] for j in cell] for cell in cells],
               'coordinates_unit':'m','field_unit':settings['field']['unit']}
        entry={'name':settings['field']['label']+' n='+str(n),'study_index':len(studies),'field':field,
               'time':None,'time_unit':None,'step_index':None,
               'source':{'artifact':'pde/level_'+str(n)+'/field.json'}}
        fields.append(entry)
        save(level/'field.json',field)
        entry['source']['sha256']=sha(level/'field.json')
        with io.XDMFFile(MPI.COMM_WORLD,str(level/'field.xdmf'),'w') as out:
            out.write_mesh(rectangle);out.write_function(solution)
        (level/'forms.ufl.txt').write_text(str(a)+'\n'+str(L),encoding='utf-8')
        row={'cells_per_axis':n,'global_dofs':nodes,'relative_residual':relative,'ksp_convergence_reason':reason,
             'reference':settings['reference'],'l2_error':None,'h1_seminorm_error':None,
             'l2_unit':'('+settings['field']['unit']+')*m','h1_unit':settings['field']['unit'],
             'norm_definition':'sqrt(integral(error^2) dx), sqrt(integral(grad(error)^2) dx); 2D SI measure'}
        row['reference_status']='NOT_REQUESTED'
        studies.append(row)
        save(output/'progress.json',{'completed_levels':studies,'fields':fields})
        if settings['reference']:
            try:
                ref=evaluate(parse(settings['reference'],basic)[0],{k:v for k,v in env.items() if k not in ('u','v')},functions)
                error=solution-ref
                l2=math.sqrt(max(0.,finite(fem.assemble_scalar(fem.form(error*error*dx)))))
                h1=math.sqrt(max(0.,finite(fem.assemble_scalar(fem.form(ufl.inner(ufl.grad(error),ufl.grad(error))*dx)))))
                row.update(l2_error=l2,h1_seminorm_error=h1,reference_status='AVAILABLE')
            except (ValueError,TypeError,RuntimeError,ArithmeticError) as error:
                row.update(reference_status='FAILED',reference_error=str(error))
        save(output/'progress.json',{'completed_levels':studies,'fields':fields})
    ok=all(row['ksp_convergence_reason']>0 and row['relative_residual']<=settings['solver']['residual_relative'] for row in studies)
    finest=studies[-1]
    for name,unit in [('l2_error',finest['l2_unit']),('h1_seminorm_error',finest['h1_unit']),('relative_residual','1')]:
        if finest[name] is not None:
            responses[name]={'kind':'scalar','value':finest[name],'unit':unit,'component':name,
                             'location':'domain','reduction':'native_integral' if name!='relative_residual' else 'algebraic_norm'}
    save(output/'worker_result.json',{'input_sha256':sha(input_path),'sources_sha256':sha(output/'sources.json'),
         'execution_status':'SUCCEEDED' if ok else 'REJECTED','responses':responses,
         'checks':[{'name':'relative_algebraic_residual','status':'PASS' if ok else 'FAIL',
                    'observed':[r['relative_residual'] for r in studies],'limit':settings['solver']['residual_relative']}],
         'diagnostics':{'native_fields':fields,'mesh_studies':studies,'versions':{'dolfinx':dolfinx.__version__,'ufl':ufl.__version__},
                        'reference_errors':[{'cells_per_axis':r['cells_per_axis'],'reason':r['reference_error']} for r in studies if r.get('reference_error')],
                        'decision':'NOT_RELEASED','reference_kind':'USER_DECLARED_NOT_QUALIFICATION'}})


if __name__=='__main__':
    main(sys.argv[1])
