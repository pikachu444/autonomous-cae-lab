"""Regional S8 native-shaped SYNTHETIC records; not a FreeCAD/CalculiX solve.

Reuses the baseline S8 grid, fixed-width encoder, Gauss order and connectivity.
Nonshared expansion IDs at a thickness jump are deliberately arbitrary.
"""
from copy import deepcopy
from pathlib import Path
from test_shell_support import model as uniform_model,record
from caelab.shell_model import shape8,GAUSS27
from caelab.shell_regions import uniform_region,reverse_region
from caelab.adapters.shell_deck import build
from caelab.adapters.shell_results import BOTTOM,TOP,FRD_FROM_C3D20,LABELS


def model(*,curved=True,flipped=True):
    m=uniform_model();d=m['draft'];ids=d['elements']
    if curved:
        for p in m['source_nodes'].values():p[2]=p[0]*p[0]/2000+p[1]*p[1]/5000
    left=uniform_region(d,region_id='R1',label='좌측 2 mm')
    left['elements']=[ids[0]]
    right=uniform_region(d,region_id='R2',label='우측 3 mm')
    right.update(elements=[ids[1]],thickness_mm='3',offset='0.25',geometry_id='Section2',pressure_id='Pressure2')
    d['regions']=[left,right]
    if flipped:d=reverse_region(d,'R2');m['draft']=d
    m['applied']['draft']=deepcopy(d)
    m['native_sections']=''.join(f'*SHELL SECTION, ELSET=ES{e}, MATERIAL=Mat, OFFSET={float(r["offset"]):.13G}\n{float(r["thickness_mm"]):.13G}\n'
        for r in d['regions'] for e in r['elements'])
    m['native_pressure']='*DLOAD\n'+''.join(f'{e}, P, {-float(r["pressure_MPa"]):.13G}\n' for r in d['regions'] for e in r['elements'])
    return m


def write_sources(folder, data, *,fields=('DISP','STRESS','TOSTRAIN'),end=True,increment=1,time=1.):
    """Synthetic geometry/reader fixture, NOT solver output or a numerical acceptance."""
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    deck,mesh=build(data); (folder/'shell.inp').write_bytes(deck.encode('ascii'))
    expanded={}; xyz={}; identifiers={}; next_id=1001; log=[]
    for e,conn in mesh['elements'].items():
        values=mesh['section_values_by_element'][e]
        thickness=values['thickness_mm'];offset=values['offset']
        out=[None]*20; normal=mesh['normals'][e]
        for j,n in enumerate(conn):
            for slot,zeta in ((BOTTOM[j],-1),(TOP[j],1)):
                key=(e,n,zeta)
                if key not in identifiers:
                    identifiers[key]=next_id; next_id+=1
                    xyz[identifiers[key]]=[x+thickness*(zeta/2-offset)*v for x,v in zip(mesh['nodes'][n],normal)]
                out[slot]=identifiers[key]
            if j<4:
                key=(e,n,0)
                if key not in identifiers:
                    identifiers[key]=next_id; next_id+=1
                    xyz[identifiers[key]]=[x-thickness*offset*v for x,v in zip(mesh['nodes'][n],normal)]
                out[16+j]=identifiers[key]
        expanded[e]=out
        log+=[f'ELEMENT {e} with label "S8      " and with nodes:', ' '.join(map(str,conn)),
              ' is expanded into a "C3D20 L " element with topology:',
              ' '.join(map(str,out[:10])),' '.join(map(str,out[10:])),'']
    (folder/'shell.12d').write_text('\n'.join(log),encoding='ascii')
    lines=['    1C','    1UVERSION    Version 2.22',f'    2C {len(xyz)} 1']
    lines += [record(n,p) for n,p in sorted(xyz.items())]+[' -3',f'    3C {len(expanded)} 1']
    for e,conn in expanded.items():
        lines += [' -1'+f'{e:10d}{4:5d}{0:5d}{1:5d}']
        order=[conn[j] for j in FRD_FROM_C3D20]
        lines += [' -2'+''.join(f'{n:10d}' for n in order[i:i+10]) for i in (0,10)]
    lines += [' -3']
    def field_values(name,p):
        x,y,z=p
        return {'DISP':[z*x*.0001,0.,x*.001], 'STRESS':[10*z,2*z,0.,3*z,4*z,5*z],
                'TOSTRAIN':[1e-4*z,2e-4*z,3e-4*z,4e-4*z,5e-4*z,6e-4*z]}[name]
    for counter,name in enumerate(fields,1):
        lines+=['    1PSTEP'+' '*14+f'{counter:12d}{increment:12d}{1:12d}']
        header='  100CL'+f'{101:5d}{time:12.5E}{len(xyz):12d}{0:22d}{1:5d}'+' '*11+'1'
        assert len(header)==75
        lines += [header,' -4 '+name+' '+str(len(LABELS[name]))+' 1']
        lines += [' -5 '+label for label in LABELS[name]]
        lines += [record(n,field_values(name,p)) for n,p in sorted(xyz.items())]+[' -3']
    if end:lines+=[' 9999']
    (folder/'shell.frd').write_text('\n'.join(lines)+'\n',encoding='ascii')
    tables=[]
    for kind,labels in [('stresses','sxx,syy,szz,sxy,sxz,syz'),('strains','exx,eyy,ezz,exy,exz,eyz'),
                        ('global coordinates','x,y,z')]:
        tables+=['',f' {kind} (elem, integ.pnt.,{labels}) for set LABSHELL and time {time:.7E}','']
        for e,conn in mesh['elements'].items():
            values=mesh['section_values_by_element'][e]
            thickness=values['thickness_mm'];offset=values['offset']
            for point,(r,s,zeta) in enumerate(GAUSS27,1):
                position=[sum(N*mesh['nodes'][n][c] for N,n in zip(shape8(r,s),conn))+
                          thickness*(zeta/2-offset)*mesh['normals'][e][c] for c in range(3)]
                vals=position if kind=='global coordinates' else [float(point+i) for i in range(6)]
                tables.append(f'{e} {point} '+' '.join(f'{v:.7E}' for v in vals))
        tables+=['']
    (folder/'shell.dat').write_text('\n'.join(tables),encoding='ascii')
    return mesh,xyz,expanded
