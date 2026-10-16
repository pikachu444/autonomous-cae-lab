"""Public small geometric fixture; not a qualified bolt design."""
from copy import deepcopy
from caelab.pretension import three_step_program
from apps.desktop_pre.freeze_analysis import CCX_FROM_NATIVE_TET10


def model(control='force_N'):
    corners={1:[0.,0.,0.],2:[1.,0.,0.],3:[0.,1.,0.],4:[.25,.25,-1.],5:[.25,.25,1.]}
    nodes=deepcopy(corners);edges={};elements=[]
    for eid,conn in ((1,[1,3,2,4]),(2,[1,2,3,5])):
        ids=list(conn)
        for i,j in ((0,1),(1,2),(2,0),(0,3),(1,3),(2,3)):
            edge=tuple(sorted((conn[i],conn[j])))
            if edge not in edges:
                n=len(nodes)+1;nodes[n]=[(a+b)/2 for a,b in zip(corners[edge[0]],corners[edge[1]])];edges[edge]=n
            ids.append(edges[edge])
        native=[None]*10
        for slot,source in enumerate(CCX_FROM_NATIVE_TET10):native[source]=ids[slot]
        elements.append({'element_id':eid,'type':'C3D10','body_id':'Bolt','node_ids':ids,
                         'native_element_id':eid,'native_node_ids':native})
    boundary=[{'node_id':n,'component':d,'value_mm':0.} for n in (4,5) for d in (1,2,3)]
    boundary += [{'node_id':1,'component':d,'value_mm':0.} for d in (1,2)]
    conditions=[]
    for cid,rows,kind in [('Bottom',[r for r in boundary if r['node_id']==4],'Fem::ConstraintFixed'),
                          ('Top',[r for r in boundary if r['node_id']==5],'Fem::ConstraintDisplacement'),
                          ('Lateral',[r for r in boundary if r['node_id']==1],'Fem::ConstraintDisplacement')]:
        conditions.append({'object_id':cid,'label':cid,'type':kind,'body_id':'Bolt','boundary_dofs':deepcopy(rows),
                           'components_mm':{r['component']:r['value_mm'] for r in rows}})
    step={'period':1.,'initial':1.,'minimum':.001,'maximum':1.,'increments':100,'geometry':'linear',
          'automatic':True,'matrix_solver':'default','controls':None}
    program=three_step_program(step,conditions)
    # External support movement, with the section differential held natively.
    for c in program['steps'][2]['curves']:
        if (c['condition_id'],c['component'])==('Top',3):c['points'][-1][1]=.01
    return {'kind':'freecad-contact-mesh','schema_version':'1',
        'units':{'position':'mm','displacement':'mm','force':'N','stress':'MPa'},
        'nodes':[{'node_id':n,'native_node_id':n,'body_id':'Bolt','position_mm':xyz,'native_position_mm':xyz} for n,xyz in nodes.items()],
        'elements':elements,'bodies':[{'body_id':'Bolt','nodes':sorted(nodes),'elements':[1,2]}],
        'body_maps':{'Bolt':{'nodes':{n:n for n in nodes},'elements':{1:1,2:2}}},
        'native_to_deck_slots':list(CCX_FROM_NATIVE_TET10),'interface_policy':'independent_body_dofs',
        'analysis_scope':'single_solid_static','materials':[{'body_id':'Bolt','object_id':'Steel','law':'isotropic_linear_elastic',
            'young_modulus_MPa':210000.,'poisson_ratio':0.}],
        'contacts':[],'boundary_dofs':boundary,'loads':[],'conditions':conditions,'step':step,'analysis_steps':program,
        'output':{'frequency':1,'nodal':['U','RF','S','E'],'pair':[]},
        'pretension_sections':[{'id':'Pbolt','body_id':'Bolt','mesh_binding':{},'draft':{
            'label':'볼트 조임','mesh_id':'BoltMesh','element_faces':[[1,1]],'axis':[0,0,1],
            'control':{'kind':control,'value':600. if control=='force_N' else .01}}}]}
