"""One-/two-cell SYNTHETIC native tensile input. Not a calibrated material.

No solver is installed, downloaded or called while making this declaration.
The proposed deletion/energy/mesh checks have NOT been executed natively here.
"""
from caelab.impact_model import default_settings,validate_settings
from caelab.impact_bulk import default_law


def settings(nx=1,output_factor=1.,cfl_scale=.9):
    if nx not in (1,2):raise ValueError('The small comparison has nx=1 or nx=2 only')
    if output_factor not in (1.,.5):raise ValueError('Choose declared output factor 1 or 0.5')
    if cfl_scale not in (.9,.45):raise ValueError('Choose declared native CFL scale 0.9 or 0.45')
    nodes={};node_id={};lines=['*HEADING','SYNTHETIC bulk tensile kinetic-release check: Mg mm s N MPa','*NODE']
    for z in (0,1):
        for y in (0,1):
            for i in range(nx+1):
                n=len(nodes)+1;node_id[i,y,z]=n;nodes[n]=(i/nx,y,z)
                lines.append(f'{n},{i/nx:.17g},{y},{z}')
    lines+=['*ELEMENT,TYPE=C3D8R,ELSET=BULKSET']
    for i in range(nx):
        corners=[(i,0,0),(i+1,0,0),(i+1,1,0),(i,1,0),(i,0,1),(i+1,0,1),(i+1,1,1),(i,1,1)]
        lines.append(str(i+1)+','+','.join(str(node_id[p]) for p in corners))
    for name,z in (('BASE',0),('PULL',1)):
        lines+=['*NSET,NSET='+name,','.join(str(n) for n,p in nodes.items() if p[2]==z)]
    lines+=['*MATERIAL,NAME=SYNTHETIC','*DENSITY','7.8e-9','*ELASTIC','210000,0.3',
            '*PLASTIC','100,0','100,0.01','*SOLID SECTION,ELSET=BULKSET,MATERIAL=SYNTHETIC',
            '*BOUNDARY','BASE,1,3,0']
    value=default_settings();value['source'].update(title='SYNTHETIC bulk tensile check',text='\n'.join(lines)+'\n',
        provenance={'purpose':'synthetic check; no empirical material calibration'})
    value['motions']=[{'node_set':'PULL','mode':'velocity','height_mm':None,'velocity_mm_s':[0.,0.,20000.],
        'omega_rad_s':[0.,0.,0.],'center_mm':[0.,0.,0.],'translation_mm':[0.,0.,0.]}]
    value['time'].update(end_s=1e-5,field_interval_s=2e-7*output_factor,history_interval_s=1e-7*output_factor,scale=cfl_scale)
    law=default_law('SYNTHETIC')
    law['initiation'].update(eta=[-1.,0.,1.],rates_s_inv=[],plastic_strain=[[.001,.001,.001]],sr_ref_s_inv=1.)
    law['evolution']['gf_n_mm']=.02
    law['calibration']['source']='SYNTHETIC plateau/onset/fracture input for prospective native check, NOT material calibration'
    value['bulk_damage']=[law]
    value['b_responses']=[{'name':f'E{e}_{q.upper()}','scope':'bulk','identity':e,'quantity':q,'component':'scalar'}
        for e in range(1,nx+1) for q in ('damage_sum','active','plastic_strain','internal_energy_density','volume')]
    validate_settings(value)
    return value
