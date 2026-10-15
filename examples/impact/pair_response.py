"""Public two-elastic-tetra TYPE24 pair, no material/strength qualification.

Use the existing Simulation service to run; this module creates no runtime or job.
The normal components are oriented by the unchanged native surface order.
"""
from caelab.impact_model import default_settings


def settings():
    value=default_settings()
    value['source'].update(title='공개 두 탄성 사면체 접촉쌍',text="""*HEADING
Public synthetic two elastic tetrahedra; Mg mm s
*NODE,NSET=FIXED
1,0,0,0
2,10,0,10
3,0,10,10
4,0,0,10
*NODE,NSET=MOVING
5,0,0,10.1
6,10,0,10.1
7,0,10,10.1
8,0,0,20.1
*ELEMENT,TYPE=C3D4,ELSET=LOWER
1,1,2,3,4
*ELEMENT,TYPE=C3D4,ELSET=UPPER
2,5,6,7,8
*MATERIAL,NAME=PUBLIC_ELASTIC
*DENSITY
7.8e-9
*ELASTIC
210000,0.3
*SOLID SECTION,ELSET=LOWER,MATERIAL=PUBLIC_ELASTIC
*SOLID SECTION,ELSET=UPPER,MATERIAL=PUBLIC_ELASTIC
*BOUNDARY
FIXED,1,3,0
*SURFACE,NAME=LOWER_FACE,TYPE=ELEMENT
LOWER,S3
*SURFACE,NAME=UPPER_FACE,TYPE=ELEMENT
UPPER,S1
""",provenance={'example':'public synthetic contact response; no material identification'})
    value['motions']=[{'node_set':'MOVING','mode':'velocity','height_mm':None,
        'velocity_mm_s':[0.,0.,-100.],'omega_rad_s':[0.,0.,0.],
        'center_mm':[0.,0.,0.],'translation_mm':[0.,0.,0.]}]
    value['contacts']=[{'a':'LOWER_FACE','b':'UPPER_FACE','law':'TYPE24','friction':0.}]
    value['time'].update(end_s=.003,field_interval_s=.0001,history_interval_s=.00002)
    value['b_responses']=[{'name':f'PAIR_{quantity}_{component}','scope':'pair','identity':0,'quantity':quantity,'component':component}
        for quantity in ('native_impulse','force','sampled_impulse') for component in ('FNX','FNY','FNZ','FTX','FTY','FTZ')]
    value['responses']=[{'name':f'MOVING_{quantity}_{node}','quantity':quantity,'identity':node,'component':'Z'}
        for quantity in ('velocity','contact_force') for node in range(5,9)]
    return value
