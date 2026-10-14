"""Deterministic synthetic data for format/logic tests; NOT a native solve log."""
from copy import deepcopy
import struct
from pathlib import Path
import json

from caelab.shell_model import DEFAULTS, prepare_mesh, reverse, shape8, GAUSS27
from caelab.adapters.shell_deck import build, MESH_KIND, KIND, sha
from caelab.adapters.shell_results import BOTTOM, TOP, FRD_FROM_C3D20, LABELS
from examples.shell.generate_plate import grid


def model(*,thickness='2',offset='0',flipped=False,nx=2,ny=1):
    nodes,elements,fixed=grid(100.,40.,nx,ny)
    draft={**deepcopy(DEFAULTS),'thickness_mm':thickness,'offset':offset,'orientation':'native',
           'analysis_id':'ShellAnalysis','mesh_id':'ShellMesh','solver_id':'Solver',
           'material_id':'Mat','geometry_id':'Section','pressure_id':'Pressure',
           'face_refs':[],'elements':list(elements),'fixed_nodes':fixed,'binding':{}}
    if flipped: draft=reverse(draft)
    sections=''.join(f'*SHELL SECTION, ELSET=ES{e}, MATERIAL=Mat, OFFSET={float(draft["offset"]):.13G}\n{float(thickness):.13G}\n' for e in elements)
    pressure='*DLOAD\n'+''.join(f'{e}, P, {-float(draft["pressure_MPa"])}\n' for e in elements)
    elastic='*MATERIAL, NAME=Mat\n*ELASTIC\n210000, 0.3\n'
    result={'schema_version':'1','kind':MESH_KIND,'units':{'position':'mm','stress':'MPa','force':'N'},
            'source_nodes':{str(n):p for n,p in nodes.items()},'source_elements':{str(e):c for e,c in elements.items()},
            'draft':draft,'applied':{'draft':deepcopy(draft),'native':{}},'fixed_nodes':fixed,
            'material_name':'Mat','native_material':elastic,'native_sections':sections,'native_pressure':pressure}
    return result


def mesh_text(data):
    return '*NODE\n'+''.join(str(n)+', '+', '.join(map(str,p))+'\n' for n,p in data['source_nodes'].items())+\
           '*ELEMENT, TYPE=S8, ELSET=Eall\n'+''.join(str(e)+', '+', '.join(map(str,c))+'\n' for e,c in data['source_elements'].items())


def snapshot(folder, data=None):
    from caelab.shell_model import digest
    folder=Path(folder); folder.mkdir(parents=True)
    data=data or model()
    (folder/'editable.FCStd').write_bytes(b'EXPLICIT_TEST_DOUBLE_NOT_A_FREECAD_DOCUMENT')
    (folder/'mesh.json').write_text(json.dumps(data),encoding='utf-8')
    (folder/'native_mesh.inp').write_text(mesh_text(data),encoding='ascii')
    (folder/'shell.inp').write_bytes(build(data)[0].encode('ascii'))
    document={'schema_version':'1','kind':KIND,'id':'Ftest','native_version':['1','1','4'],
              'input_file':'shell.inp','applied_sha256':digest(data['applied']),
              'files':[{'relative':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(folder.iterdir())]}
    path=folder/'snapshot.json'; path.write_text(json.dumps(document),encoding='utf-8')
    return path


def record(n,values):
    vals=[struct.unpack('<f',struct.pack('<f',v))[0] for v in values]
    return ' -1'+f'{n:10d}'+''.join(f'{v:12.5E}' for v in vals)


def raw_sources(folder, data, *,fields=('DISP','STRESS','TOSTRAIN'),end=True,increment=1,time=1.):
    """Synthetic native-format records, with shared expanded IDs across S8 edges."""
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    deck,mesh=build(data); (folder/'shell.inp').write_bytes(deck.encode('ascii'))
    expanded={}; xyz={}; identifiers={}; next_id=1001; log=[]
    thickness=mesh['section_values']['thickness_mm']; offset=mesh['section_values']['offset']
    for e,conn in mesh['elements'].items():
        out=[None]*20; normal=mesh['normals'][e]
        for j,n in enumerate(conn):
            for slot,zeta in ((BOTTOM[j],-1),(TOP[j],1)):
                key=(n,zeta)
                if key not in identifiers:
                    identifiers[key]=next_id; next_id+=1
                    xyz[identifiers[key]]=[x+thickness*(zeta/2-offset)*v for x,v in zip(mesh['nodes'][n],normal)]
                out[slot]=identifiers[key]
            if j<4:
                key=(n,0)
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
            for point,(r,s,zeta) in enumerate(GAUSS27,1):
                position=[sum(N*mesh['nodes'][n][c] for N,n in zip(shape8(r,s),conn))+
                          thickness*(zeta/2-offset)*mesh['normals'][e][c] for c in range(3)]
                vals=position if kind=='global coordinates' else [float(point+i) for i in range(6)]
                tables.append(f'{e} {point} '+' '.join(f'{v:.7E}' for v in vals))
        tables+=['']
    (folder/'shell.dat').write_text('\n'.join(tables),encoding='ascii')
    return mesh,xyz,expanded
