"""Small native B1.3 models. Creating a model never executes a solver.

The pure mesh/reference functions are testable without FreeCAD. Native create
functions must run in the existing FreeCAD 1.1.4 GUI. They are not claimed to
have run by merely executing the pure tests.
"""
from copy import deepcopy
from pathlib import Path
import math
import uuid
from examples.shell.generate_plate import grid


def curved_mesh(*,radius=400.,length=100.,angle_deg=30.,nx=4,ny=2):
    if not all(math.isfinite(v) for v in (radius,length,angle_deg)) or radius<=0 or length<=0 or not 0<angle_deg<90:
        raise ValueError('Use finite positive radius/length and a 0..90 degree cylindrical patch')
    if type(nx) is not int or nx<2 or nx%2:
        raise ValueError('Use an even positive axial element count to define two exact regions')
    nodes,elements,fixed=grid(length,radius*math.radians(angle_deg),nx,ny)
    original=deepcopy(nodes)
    nodes={n:[radius*math.cos(p[1]/radius),radius*math.sin(p[1]/radius),p[0]] for n,p in nodes.items()}
    first=[e for e,c in elements.items() if sum(original[n][0] for n in c[:4])/4<length/2]
    second=sorted(set(elements)-set(first))
    return nodes,elements,fixed,(first,second)


def beam_reference(angle=0.,case='moment_1'):
    """Analytical Euler-Bernoulli comparison values, NOT computed results."""
    if angle not in (0.,90.) or case not in ('moment_1','moment_2','end_force'):
        raise ValueError('Use the declared independent load/quarter-turn reference cases')
    E=210000.;L=1000.;w,h=(10.,20.) if angle==0 else (20.,10.)
    Iy=w*h**3/12;Iz=h*w**3/12
    if case=='moment_1':u=[0.,0.,-1000*L**2/(2*E*Iy)];F=[0.,0.,0.];M=[0.,-1000.,0.]
    elif case=='moment_2':u=[0.,1000*L**2/(2*E*Iz),0.];F=[0.,0.,0.];M=[0.,0.,-1000.]
    else:u=[0.,0.,-L**3/(3*E*Iy)];F=[0.,0.,1.];M=[0.,-L,0.]
    return {'reference_only':True,'method':'Euler-Bernoulli analytical uniform rectangular cantilever',
        'E_MPa':E,'length_mm':L,'Iy_mm4':Iy,'Iz_mm4':Iz,'tip_U_mm':u,
        'support_F_N':F,'support_M_about_global_origin_Nmm':M,
        'comparison_policy':'U is expanded section centroid translation; do not compare a single corner U with beam-line U',
        'relative_tolerance_nonzero_tip_U':.02,'absolute_tolerance_zero_U_mm':1e-5,
        'relative_tolerance_nonzero_support_traction':.05,
        'absolute_tolerance_zero_support_force_N':1e-4,
        'absolute_tolerance_zero_support_moment_Nmm':.1,
        'native_generalized_rotation_acceptance':'UNAVAILABLE_NOT_CLOSED',
        'complete_discrete_support_reaction_acceptance':'UNAVAILABLE_NOT_CLOSED'}


def create_shell(output_root,*,reverse_second=False):
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part,Fem,ObjectsFem
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre.shell_edit import SETTINGS
    from caelab.shell_regions import uniform_region,reverse_region
    if list(map(str,App.Version()[:3]))!=['1','1','4'] or not App.GuiUp:
        raise RuntimeError('Use installed FreeCAD 1.1.4 GUI')
    root=Path(output_root).absolute();root.mkdir(parents=True,exist_ok=True)
    target=root/'B13-curved-shell.FCStd'
    if target.exists():raise FileExistsError(target)
    nodes,elements,fixed,groups=curved_mesh()
    doc=App.newDocument('B13Shell_'+uuid.uuid4().hex[:8]);doc.Label='곡면 셸 (2/3 mm, 오프셋 0/0.25)';doc.UndoMode=1
    faces=[]
    for z in (0.,50.):
        solid=Part.makeCylinder(400.,50.,App.Vector(0,0,z),App.Vector(0,0,1),30.)
        side=[f for f in solid.Faces if type(f.Surface).__name__=='Cylinder']
        if len(side)!=1:raise ValueError('Expected exactly one native cylindrical face; no guessed topology')
        faces.append(side[0])
    patch=doc.addObject('Part::Feature','CurvedPatch');patch.Label='원통 곡면 (Face1 / Face2)'
    patch.Shape=Part.makeCompound(faces)
    analysis=ObjectsFem.makeAnalysis(doc,'ShellAnalysis')
    solver=ObjectsFem.makeSolverCalculiXCcxTools(doc);analysis.addObject(solver)
    for k,v in SETTINGS.items():setattr(solver,k,v)
    fem=Fem.FemMesh()
    for n,p in nodes.items():fem.addNode(*p,n)
    for e,c in elements.items():fem.addFace(c,e)
    mesh=doc.addObject('Fem::FemMeshObject','ShellMesh');mesh.Label='곡면 S8 영역 메시'
    if 'Shape' not in mesh.PropertiesList:mesh.addProperty('App::PropertyLink','Shape','FEM')
    mesh.Shape=patch;mesh.FemMesh=fem;analysis.addObject(mesh)
    doc.recompute();doc.saveAs(str(target))
    owner=Owner(doc,root/'exports',App=App,Gui=Gui)
    owner.shell.begin({'analysis_id':analysis.Name,'mesh_id':mesh.Name,'solver_id':solver.Name})
    draft=owner.shell._record(analysis.Name)['draft'];draft['elements']=sorted(elements)
    rows=[]
    for i,ids in enumerate(groups):
        row=uniform_region(draft);row.update(id='R'+str(i+1),label=f'곡면 영역 {i+1}',elements=ids,
            geometry_id='',pressure_id='',thickness_mm=str(2+i),offset='0' if i==0 else '0.25',
            axis_x='0',axis_y='0',axis_z='1',orientation='native',
            face_refs=[{'object_id':patch.Name,'subelements':['Face'+str(i+1)]}])
        rows.append(row)
    if reverse_second:
        temporary={**draft,'regions':rows};rows=reverse_region(temporary,'R2')['regions']
    owner.shell.save_draft(analysis.Name,{'regions':rows,'fixed_nodes':fixed})
    selection=owner.shell.preview_rebind(analysis.Name,elements=sorted(elements))
    owner.shell.apply_rebind(selection['token'])
    owner.shell.save_draft(analysis.Name,{'orientation':'native'})
    owner.shell.apply(analysis.Name);owner.project.save()
    mesh.ViewObject.Visibility=False
    Gui.activeDocument().activeView().viewAxonometric();Gui.activeDocument().activeView().fitAll()
    return owner,analysis.Name


def create_beam(output_root,*,case='moment_1',angle=0.,output_mode='raw_stress',regional_axes=False):
    from examples.beam.beam_example import create
    from caelab.beam_output import DEFAULT
    from apps.desktop_pre.beam_mesh_binding import REFERENCE_KEY
    if case not in ('moment_1','moment_2','end_force') or angle not in (0.,90.):
        raise ValueError('Choose the predefined independent force/moment comparison')
    owner,analysis=create(case,output_root=output_root,attach=False)
    record=owner.beam._get(analysis);draft=deepcopy(record['draft'])
    draft['section']['rotation_deg']=str(angle)
    draft['output']=deepcopy(DEFAULT);draft['output']['mode']=output_mode
    if output_mode=='raw_stress':
        draft['output'].update(derived_rotation=True,supports=[{'label':'고정단','ends':[0]}])
    if regional_axes:
        if output_mode!='raw_stress':raise ValueError('Region axes require the explicit 3D output mode')
        ids=[r['id'] for r in record[REFERENCE_KEY]['elements']]
        half=len(ids)//2
        draft['axis_regions']=[{'id':'R'+str(i+1),'label':f'방향 구간 {i+1}',
            'elements':part,'rotation_deg':str(90*i),'rotation_id':''} for i,part in enumerate((ids[:half],ids[half:]))]
    owner.beam.apply(analysis,draft);owner.project.save()
    return owner,analysis
