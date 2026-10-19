"""Finite geometry/declarations; expected values are independent analytic checks."""
from copy import deepcopy
from apps.desktop_pre.freeze_analysis import CCX_FROM_NATIVE_TET10
from caelab.initial_field_conditions import default_draft,normalize
from caelab.adapters.initial_field_deck import program


def model():
    xyz={1:[0.,0.,0.],2:[10.,0.,0.],3:[0.,1.,0.],4:[0.,0.,1.]};ids=[1,2,3,4]
    for a,b in ((1,2),(2,3),(3,1),(1,4),(2,4),(3,4)):
        n=len(xyz)+1;xyz[n]=[(x+y)/2 for x,y in zip(xyz[a],xyz[b])];ids.append(n)
    native=[None]*10
    for slot,source in enumerate(CCX_FROM_NATIVE_TET10):native[source]=ids[slot]
    boundary=[{'node_id':n,'component':d,'value_mm':0.} for n,ds in ((1,(1,2,3)),(2,(2,3)),(3,(3,))) for d in ds]
    conditions=[{'object_id':'Support'+str(i),'label':'기준 지지 '+str(i),'type':'Fem::ConstraintDisplacement',
        'body_id':'Solid','components_mm':{r['component']:0. for r in boundary if r['node_id']==i},
        'boundary_dofs':[r for r in boundary if r['node_id']==i]} for i in (1,2,3)]
    result={'kind':'freecad-contact-mesh','schema_version':'1','analysis_scope':'single_solid_static',
        'units':{'position':'mm','displacement':'mm','force':'N','stress':'MPa'},'interface_policy':'independent_body_dofs',
        'native_to_deck_slots':list(CCX_FROM_NATIVE_TET10),
        'nodes':[{'node_id':n,'native_node_id':n,'body_id':'Solid','position_mm':v,'native_position_mm':v} for n,v in xyz.items()],
        'elements':[{'element_id':1,'native_element_id':1,'type':'C3D10','body_id':'Solid','node_ids':ids,'native_node_ids':native}],
        'bodies':[{'body_id':'Solid','nodes':list(xyz),'elements':[1]}],'body_maps':{'Solid':{'nodes':{n:n for n in xyz},'elements':{1:1}}},
        'materials':[{'body_id':'Solid','object_id':'Steel','law':'isotropic_linear_elastic','young_modulus_MPa':210000.,'poisson_ratio':.3}],
        'contacts':[],'conditions':conditions,'boundary_dofs':boundary,'loads':[],
        'step':{'period':1.,'initial':1.,'minimum':.001,'maximum':1.,'increments':50,'geometry':'linear','automatic':True,'matrix_solver':'default','controls':None},
        'output':{'frequency':1,'nodal':['U','RF','S','E'],'pair':[]}}
    from caelab.contact_steps import default_program
    result['analysis_steps']=default_program(result['step'],conditions)
    first=result['analysis_steps']['steps'][0]
    first['id']='Equilibrate';first['label']='첫 평형'
    second=deepcopy(first);second['id']='Continue';second['label']='후속 하중'
    result['analysis_steps']['steps'].append(second)
    return result


def draft(kind='temperature'):
    m=model();d=default_draft();d.update(kind=kind,solver='codeaster' if kind=='compatible' else 'calculix',mesh_id='Mesh',
        node_ids=[r['node_id'] for r in m['nodes']],element_ids=[1])
    d['states'][0]['load_factor']=0.;d['states'][1]['load_factor']=1.
    d['temperature'].update(reference_value=293.15,expansion_per_K=1e-5,samples=[[0.,293.15],[1.,343.15],[2.,393.15]])
    d['stress']['values']=[100.,0.,0.,0.,0.,0.]
    d['compatible'].update(origin_mm=[0.,0.,0.],translation_mm=[0.,0.,0.],gradient=[[.001,0,0],[0,-.0003,0],[0,0,-.0003]],
        total_strain=[.001,-.0003,-.0003,0.,0.,0.],stress_values=[210.,0.,0.,0.,0.,0.])
    return d


def applied(kind='temperature'):
    m=model()
    if kind=='compatible':m['step']['automatic']=False
    d=draft(kind);definition=normalize(m,d);m['initial_fields']={'draft':d,'definition':definition};m['analysis_steps']=program(m,definition);return m


def snapshot(folder,kind='temperature'):
    import hashlib,json
    from caelab.contact_deck import render
    folder.mkdir(parents=True,exist_ok=False);m=applied(kind)
    (folder/'mesh.json').write_text(json.dumps(m),encoding='utf-8')
    (folder/'contact.inp').write_text(render(m),encoding='ascii',newline='\n')
    (folder/'editable.FCStd').write_bytes(b'CONTROLLED input fixture; not native CAD')
    files=[{'relative':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in folder.iterdir()]
    manifest={'kind':'freecad-contact-frozen','schema_version':'1','id':'Finitial','input_file':'contact.inp','bodies':[{'body_id':'Solid'}],
        'analysis_id':'Analysis','solver_id':'Solver','files':files}
    path=folder/'snapshot.json';path.write_text(json.dumps(manifest),encoding='utf-8');return path
