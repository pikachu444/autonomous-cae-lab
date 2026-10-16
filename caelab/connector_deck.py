"""Pinned TYPE13/RBODY card writer. Only validated linear rigid attachments."""
from .connector_model import model,dot,cross

TOKENS=('FX','FY','FZ','MX','MY','MZ','LX','LY','LZ','RX','RY','RZ','IE','LENGTH','OFF')
def ints(*v): return ''.join(f'{x:10d}' for x in v)
def reals(*v): return ''.join(f'{x:20.12g}' for x in v)


def motion_cards(origin,velocity,omega,axes,*,group,ident,frame,version=2022):
    """One supplied rigid initial field, projected to an explicit native frame."""
    if not any(omega):
        return ([f'/INIVEL/TRA/{ident}','EXPLICIT_REFERENCE_TRANSLATION',reals(*velocity)+ints(group,0)]
                if any(velocity) else []),{'origin_mm':origin,'velocity_mm_s':velocity,'omega_rad_s':omega}
    import math
    mag=math.sqrt(dot(omega,omega));z=[v/mag for v in omega]
    seed=min(axes.values(),key=lambda v:abs(dot(v,z)))
    y=[a-dot(seed,z)*b for a,b in zip(seed,z)];norm=math.sqrt(dot(y,y));y=[v/norm for v in y]
    x=cross(y,z);v=[dot(velocity,a) for a in (x,y,z)]
    return [f'/FRAME/FIX/{frame}','INITIAL_OMEGA_FRAME_AT_REFERENCE',reals(*origin),reals(*y),reals(*z),
            f'/INIVEL/AXIS/{ident}','EXPLICIT_RIGID_INITIAL_FIELD',
            f'{"Z":>10}'+ints(frame,group),reals(*v,mag),
            *([reals(0)+ints(0)] if version>=2025 else [])],{
        'origin_mm':origin,'velocity_mm_s':velocity,'omega_rad_s':omega,
        'frame':{'id':frame,'x':x,'y':y,'z':z},'native_translation':v,'native_rotation':mag}


def layout(m):
    """Stable exported labels are recorded, never guessed back from coordinates."""
    rows=[]; mapping=[];next_id=3
    for i,e in enumerate(m['endpoints']):
        ids=[]
        for p in e['points_mm']:
            # The reference is the native RBODY main, not a secondary duplicate.
            if p==e['reference_mm']: continue
            rows.append((next_id,p));ids.append(next_id);next_id+=1
        mapping.append({'main_node':i+1,'secondary_nodes':ids,'rigid_body':i+1,
                        'selection':e['selection']})
    return [(i+1,e['reference_mm']) for i,e in enumerate(m['endpoints'])]+rows,mapping


def starter(m):
    # Revalidate the retained draft even if a caller constructed a model dict.
    if m!=model(m['draft']): raise ValueError('Connector model differs from validated draft')
    nodes,mapping=layout(m)
    lines=['#RADIOSS STARTER','/BEGIN','connector',ints(2022,0),
           '                  Mg                  mm                   s',
           '                  Mg                  mm                   s',
           '/NODE',*[ints(n)+reals(*p) for n,p in nodes],
           '/SKEW/FIX/1','EXPLICIT_CONNECTOR_LOCAL_Y_Z',reals(0,0,0),
           reals(*m['axes']['y']),reals(*m['axes']['z']),
           '/PROP/TYPE13/1','LINEAR_SPR_BEAM_EXPLICIT_MASS_INERTIA',
           reals(m['connector_mass_Mg'],m['connector_inertia_Mg_mm2'])+ints(1,0,0,0,0,0)]
    for k,c in zip(m['k'],m['c']):
        lines.extend([reals(k,c,1,0,1),ints(0,0,0,0,0)+' '*10+reals(0,0),reals(0,0,0,0)])
    lines.extend([reals(0,0,0)+ints(0),*[reals(0,0,0,0)]*6,
                  '/PART/1','CONNECTOR',ints(1,0,0),'/SPRING/1',
                  ints(1,1,2,0,0,0,0)+' '*20+ints(0)])
    for i,(e,link) in enumerate(zip(m['endpoints'],mapping),1):
        # Empty secondary group is not invented. A single real reference is
        # allowed, while a region carries all selected actual point coordinates.
        group=i if link['secondary_nodes'] else 0
        if group:
            lines.extend([f'/GRNOD/NODE/{group}',f'SELECTED_REGION_{i}'])
            for j in range(0,len(link['secondary_nodes']),10): lines.append(ints(*link['secondary_nodes'][j:j+10]))
        lines.extend([f'/RBODY/{i}',f'EXPLICIT_RIGID_ATTACHMENT_{i}',
            ints(i,0,0,3)+reals(e['mass_Mg'])+ints(group,0,4,0),
            reals(*e['inertia_Mg_mm2'][:3]),reals(*e['inertia_Mg_mm2'][3:]),ints(0,0,0),
            f'/GRNOD/NODE/{10+i}',f'REFERENCE_{i}',ints(i)])
        if any(e['fixed']):
            tra=''.join('1' if v else '0' for v in e['fixed'][:3]);rot=''.join('1' if v else '0' for v in e['fixed'][3:])
            lines.extend([f'/BCS/{i}',f'EXPLICIT_FIXED_REFERENCE_{i}',f'{tra:>6}{rot:>4}'+ints(0,10+i)])
        cards,_=motion_cards(e['reference_mm'],e['velocity_mm_s'],e['omega_rad_s'],m['axes'],group=10+i,ident=i,frame=100+i)
        lines.extend(cards)
    lines.extend(['/TH/SPRING/1','NATIVE_LOCAL_GENERALIZED_Q_AND_FORCE'])
    for j in range(0,len(TOKENS),10): lines.append(''.join(f'{s:<10}' for s in TOKENS[j:j+10]))
    lines.append(ints(1)+' '*10+'CONNECTOR_ELEMENT_1')
    lines.extend(['/TH/RBODY/2','ATTACHMENT_REFERENCE_KINEMATICS'])
    lines.append(''.join(f'{s:<10}' for s in ('FX','FY','FZ','MX','MY','MZ','RX','RY','RZ')))
    lines.extend([ints(i)+' '*10+f'ACTUAL_ENDPOINT_{i}' for i in (1,2)])
    lines.extend(['/TH/NODE/3','ACTUAL_REFERENCE_TRANSLATION',
                  ''.join(f'{s:<10}' for s in ('DX','DY','DZ','VX','VY','VZ')),
                  *[ints(i,0)+f'ACTUAL_REFERENCE_{i}' for i in (1,2)],'/END'])
    return '\n'.join(lines)+'\n'


def engine(m):
    if m!=model(m['draft']): raise ValueError('Connector model differs from validated draft')
    return '\n'.join(['/RUN/connector/1',reals(m['time']['end_s']),'/VERS/100','/DT',
        reals(m['time']['scale'],0),'/TFILE/4',reals(m['time']['history_interval_s']),'/TH/TITLE','/PRINT/1'])+'\n'
