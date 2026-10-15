"""Synthetic serialization fixtures, NOT a native execution or physical result.

Uses the existing FRD record encoder. Topology positions follow the cited 2.22
Fortran source; sparse shuffled IDs deliberately defeat node-number guesses.
"""
from copy import deepcopy
import random
from pathlib import Path
from test_beam_support import model as beam_model
from test_shell_support import record
from caelab.beam_output import DEFAULT, element_axes, axes_for
from caelab.shell_model import cross
from caelab.adapters.shell_results import LABELS, FRD_FROM_C3D20


def raw_model(angle='0', regional=False):
    m=beam_model(angle=angle)
    m['draft']['output']=deepcopy(DEFAULT)
    m['draft']['output'].update(mode='raw_stress',derived_rotation=True,
                               supports=[{'label':'고정단','ends':[0]}])
    if regional:
        ids=[r['id'] for r in m['elements']]
        m['draft']['axis_regions']=[{'id':f'R{i+1}','label':f'구간 {i+1}',
            'elements':[e],'rotation_deg':str(90*i),'rotation_id':f'Rotation{i+2}'} for i,e in enumerate(ids)]
        m['element_axes']={str(e):a for e,a in element_axes(m['draft'],m['axes']['tangent'],set(ids)).items()}
    return m


def write_sources(folder, m, *, end=True, dat=True, field_order=None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    nodes={r['id']:r['xyz_mm'] for r in m['nodes']}
    w=float(m['draft']['section']['width_mm']);h=float(m['draft']['section']['height_mm'])
    # (original station index, width fraction, height fraction), CCX HEX20 order.
    places=((0,-.5,.5),(2,-.5,.5),(2,-.5,-.5),(0,-.5,-.5),
            (0,.5,.5),(2,.5,.5),(2,.5,-.5),(0,.5,-.5),
            (1,-.5,.5),(2,-.5,0),(1,-.5,-.5),(0,-.5,0),
            (1,.5,.5),(2,.5,0),(1,.5,-.5),(0,.5,0),
            (0,0,.5),(2,0,.5),(2,0,-.5),(0,0,-.5))
    allocated=iter(random.Random(1703).sample(range(10001,999999),20*len(m['elements'])))
    xyz={};exp={};maps=[]
    for row in m['elements']:
        e=row['id'];conn=row['ccx_nodes'];a=axes_for(m,e);expanded=[]
        for station,u,v in places:
            n=next(allocated);p=nodes[conn[station]]
            xyz[n]=[p[k]+w*u*a['local1'][k]+h*v*a['local2'][k] for k in range(3)]
            expanded.append(n)
        exp[e]=expanded
        maps.append(f'ELEMENT {e} with label "B32R   R" and with nodes:\n'+
                    ' '.join(map(str,conn))+'\n is expanded into a "C3D20RBR" element with topology:\n'+
                    ' '.join(map(str,expanded))+'\n')
    (folder/'beam.12d').write_text('\n'.join(maps),encoding='ascii')
    lines=['    1C','    1UVERSION    Version 2.22',f'    2C {len(xyz)} 1']
    lines += [record(n,xyz[n]) for n in sorted(xyz)];lines+=[' -3',f'    3C {len(exp)} 1']
    for e in sorted(exp):
        lines.append(f' -1{e:10d}{4:5d}{0:5d}{1:5d}')
        conn=[exp[e][j] for j in FRD_FROM_C3D20]
        lines += [' -2'+''.join(f'{n:10d}' for n in conn[i:i+10]) for i in (0,10)]
    lines+=[' -3']
    labels={**LABELS,'FORC':('F1 1 2 1 0','F2 1 2 2 0','F3 1 2 3 0','ALL 1 2 0 0 1ALL')}
    def values(field,p):
        if field=='DISP':return [a+b for a,b in zip((.2,.3,.4),cross((.001,.002,.003),p))]
        if field=='FORC':return [1.,2.,3.]
        if field=='STRESS':return [2.,3.,4.,.5,.6,.7]
        return [2e-6,3e-6,4e-6,5e-7,6e-7,7e-7]
    for count,field in enumerate(field_order or ('DISP','STRESS','TOSTRAIN','FORC'),1):
        lines += ['    1PSTEP'+14*' '+f'{count:12d}{1:12d}{1:12d}',
                  '  100CL'+f'{101:5d}{1.:12.5E}{len(xyz):12d}'+f'{0:22d}{1:5d}'+11*' '+'1',
                  f' -4  {field} {len(labels[field])} 1']
        lines += [' -5 '+s for s in labels[field]]
        lines += [record(n,values(field,xyz[n])) for n in sorted(xyz)]
        lines += [' -3']
    if end:lines+=[' 9999']
    (folder/'beam.frd').write_text('\n'.join(lines)+'\n',encoding='ascii')
    if dat:
        from caelab.beam_gauss import B32R_RECT_GAUSS50
        natural=B32R_RECT_GAUSS50
        output=[]
        for title,labels2,field in (
            ('stresses','elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz','S'),
            ('strains','elem, integ.pnt.,exx,eyy,ezz,exy,exz,eyz','E'),
            ('global coordinates','elem, integ.pnt.,x,y,z','COORD')):
            output += [f' {title} ({labels2}) for set BEAM and time 1.0000000E+00','']
            for row in m['elements']:
                e=row['id'];a=axes_for(m,e);c=row['ccx_nodes'];mid=nodes[c[1]]
                length=sum((nodes[c[2]][k]-nodes[c[0]][k])*a['tangent'][k] for k in range(3))
                for i,(r,s,t) in enumerate(natural,1):
                    p=[mid[k]+r*length/2*a['tangent'][k]-s*h/2*a['local2'][k]+t*w/2*a['local1'][k] for k in range(3)]
                    v=p if field=='COORD' else [2.,3.,4.,.5,.7,.6]
                    if field=='E':v=[x*1e-6 for x in v]
                    output.append(f'{e} {i} '+' '.join(f'{x:.9E}' for x in v))
            output.append('')
        (folder/'beam.dat').write_text('\n'.join(output)+'\n',encoding='ascii')
    return xyz,exp
