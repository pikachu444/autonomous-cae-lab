"""Explicit synthetic records. NEVER evidence of a native solve or real .rout.

Record order is transcribed independently from the supplied official native
writer. Models use one positive-Jacobian C3D10 with sparse SOURCE labels.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import struct
from caelab.contact import separate_meshes
from caelab.contact_deck import UNITS, render, validate_model
from caelab.contact_steps import default_program, compile_program
from caelab.dynamic_model import default_draft, attach


def base_model():
    xyz=[(1,0,0),(0,0,0),(0,1,0),(0,0,1),(.5,0,0),(0,.5,0),(.5,.5,0),(.5,0,.5),(0,0,.5),(0,.5,.5)]
    source=[11,23,37,51,62,74,89,97,104,119]
    m=separate_meshes([{'body_id':'Solid','nodes':[{'node_id':n,'position_mm':list(p)} for n,p in zip(source,xyz)],
        'elements':[{'element_id':73,'type':'C3D10','native_node_ids':source}]}],minimum_bodies=1)
    for n in m['nodes']:n['native_position_mm']=list(n['position_mm'])
    for e in m['elements']:e['type']='C3D10'
    fixed=[{'node_id':n,'component':d,'value_mm':0.} for n in (1,2,3) for d in (1,2,3)]
    m.update(kind='freecad-contact-mesh',schema_version='1',units=dict(UNITS),analysis_scope='single_solid_static',
        materials=[{'body_id':'Solid','object_id':'Material','law':'isotropic_linear_elastic',
                    'young_modulus_MPa':1000.,'poisson_ratio':.3,'native_values':{'Density':'7800 kg/m^3'}}],
        contacts=[],boundary_dofs=fixed,loads=[{'node_id':4,'component':3,'force_N':-10.}],
        conditions=[{'object_id':'Support','label':'받침','type':'Fem::ConstraintFixed','body_id':'Solid','boundary_dofs':deepcopy(fixed)},
                    {'object_id':'Force','label':'하중','type':'Fem::ConstraintForce','body_id':'Solid','total_force_N':10.,
                     'force_weights':[{'node_id':4,'component':3,'weight':-1.}]}],
        step={'initial':.2,'period':1.,'minimum':1e-6,'maximum':.5,'increments':100,'geometry':'linear',
              'automatic':True,'matrix_solver':'default','controls':None},
        output={'frequency':1,'nodal':['U','RF','S','E'],'pair':[]})
    return m


def draft_for(m):
    return default_draft('Analysis','Solver',default_program(m['step'],m['conditions']),
                         [{'body_id':x['body_id'],'material_id':x['object_id'],'kg_m3':'7800'} for x in m['materials']])


def dynamic_model(*, mixed=False, two=False):
    m=base_model();d=draft_for(m)
    if mixed or two:
        a=d['program']['steps'][0]
        b=deepcopy(a);b.update(id='Step2',label='진동',procedure='dynamic')
        b['curves'][0]['mode']='release'
        d['program']['steps'].append(b)
    if mixed:
        d['program']['procedure']='mixed';d['program']['steps'][0]['procedure']='static'
    return attach(m,d)


def snapshot(m,folder):
    folder=Path(folder);folder.mkdir()
    (folder/'editable.FCStd').write_bytes(b'EXPLICIT_DOCUMENT_DOUBLE_NOT_FREECAD')
    (folder/'mesh.json').write_text(json.dumps(m),encoding='utf-8')
    (folder/'contact.inp').write_text(render(m),encoding='ascii',newline='\n')
    data={'kind':'freecad-contact-frozen','schema_version':'1','id':'FdynamicFixture',
        'analysis_id':'Analysis','solver_id':'Solver','input_file':'contact.inp','bodies':[{'body_id':b} for b in m['body_maps']],
        'files':[{'relative':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(folder.iterdir())]}
    path=folder/'snapshot.json';path.write_text(json.dumps(data),encoding='utf-8');return path


LABELS={
 'DISP':('D1 1 2 1 0','D2 1 2 2 0','D3 1 2 3 0','ALL 1 2 0 0 1ALL'),
 'VELO':('V1 1 2 1 0','V2 1 2 2 0','V3 1 2 3 0','ALL 1 2 0 0 1ALL'),
 'FORC':('F1 1 2 1 0','F2 1 2 2 0','F3 1 2 3 0','ALL 1 2 0 0 1ALL'),
 'STRESS':('SXX 1 4 1 1','SYY 1 4 2 2','SZZ 1 4 3 3','SXY 1 4 1 2','SYZ 1 4 2 3','SZX 1 4 3 1'),
 'TOSTRAIN':('EXX 1 4 1 1','EYY 1 4 2 2','EZZ 1 4 3 3','EXY 1 4 1 2','EYZ 1 4 2 3','EZX 1 4 3 1'),
 'ENER':('ENER 1 1 0 0',),
 'CONTACT':('COPEN 1 1 0 0','CSLIP1 1 1 0 0','CSLIP2 1 1 0 0','CPRESS 1 1 0 0','CSHEAR1 1 1 0 0','CSHEAR2 1 1 0 0')}


def outputs(m, *, omit=None, stop_step=None):
    nodes,elements,bodies=validate_model(m);names={b:i for i,b in enumerate(sorted(bodies),1)}
    lines=['    1C','    1UPGM               CalculiX','    1UVERSION           Version 2.22']
    lines += [f'    1UMAT{i:5d}{("M"+str(i)):<58}' for i in names.values()]
    lines += [f'    1UMAT{len(names)+i:5d}{("INT"+p["object_id"].upper()):<58}' for i,p in enumerate(m['contacts'],1)]
    lines.append(f'    2C{len(nodes):30d}{1:38d}')
    def record(n,v):return ' -1'+f'{n:10d}'+''.join(f'{x:12.5E}' for x in v)
    lines += [record(n,p) for n,p in nodes.items()]+[' -3',f'    3C{len(elements):30d}{1:38d}']
    for e in m['elements']:
        lines += [' -1'+f'{e["element_id"]:10d}{6:5d}{0:5d}{names[e["body_id"]]:5d}',
                  ' -2'+''.join(f'{n:10d}' for n in e['node_ids'])]
    lines.append(' -3');dat=[];sta=['SUMMARY OF JOB INFORMATION'];count=0;output_count=0
    for s in compile_program(m['analysis_steps'],m['conditions']):
        if s['index'] < m.get('restart',{}).get('checkpoint',{}).get('step',0)+1:continue
        if stop_step is not None and s['index']>stop_step:break
        last=0.
        for inc,fraction in enumerate((.2,.5,1.),1):
            local=s['duration']*fraction;t=s['start']+local;output_count+=1
            sta.append(f" {s['index']} {inc} 1 2 {t:.7E} {local:.7E} {local-last:.7E}");last=local
            fields=['DISP','FORC','STRESS','TOSTRAIN','ENER']+(['VELO'] if s['procedure']=='dynamic' else [])
            if m['contacts']:fields.append('CONTACT')
            for field in fields:
                if field==omit:continue
                count+=1
                lines += ['    1PSTEP'+' '*14+f"{count:12d}{inc:12d}{s['index']:12d}"+' '*10,
                    '  100CL'+f'{100+output_count:5d}{t:12.9f}{len(nodes):12d}'+' '*21+('1' if s['procedure']=='dynamic' else '0')+f'{output_count:5d}'+' '*11+'1',
                    f' -4  {field:<12}{len(LABELS[field])}    1']
                lines += [' -5  '+label for label in LABELS[field]]
                width=6 if field in ('STRESS','TOSTRAIN','CONTACT') else 1 if field=='ENER' else 3
                for n in nodes:
                    v=[0.]*width
                    if field=='VELO':v=[t*t,2*t,0.]
                    elif field=='DISP':v=[.001*t,0.,0.]
                    elif field=='FORC':v=[-t,0.,0.]
                    elif field=='ENER':v=[t]
                    lines.append(record(n,v))
                lines.append(' -3')
            for q,label in [('ELKE','kinetic energy (elem, energy)'),('ELSE','internal energy (element, energy)'),
                            ('ENER','internal energy density (elem, integ.pnt.,energy)')]:
                dat += ['',f' {label} for set CAELAB_DYNAMIC_ALL and time {t:.7E}','']
                for e in elements:
                    dat += [f' {e} {ip} {t:.7E}' for ip in (1,2,3,4)] if q=='ENER' else [f' {e} {t:.7E}']
                dat.append('')
            for pair in m['contacts']:
                for _ in ('CF','CFN','CFS'):
                    dat += [f" statistics for slave set DEP{pair['object_id'].upper()}, master set IND{pair['object_id'].upper()} and time {t:.7E}",
                      '', ' total surface force (fx,fy,fz) and moment about the origin (mx,my,mz)', '', ' 0 0 0 0 0 0', '',
                      ' center of gravity and mean normal', '', ' 0 0 0 0 0 -1', '',
                      ' moment about the center of gravity(mx,my,mz)', '', ' 0 0 0', '',
                      ' area,  normal force (+ = tension) and shear force (size)', '', ' 1 0 0']
    lines.append(' 9999')
    return '\n'.join(lines)+'\n','\n'.join(dat)+'\n','\n'.join(sta)+'\n'


def synthetic_rout(m, *, steps=None, order='<', delta=0.):
    """Independent minimal Fortran sequential record double, 4-byte integers.

    No material/contact solver state is solved: all non-identity arrays are zero
    except the deliberate comparison delta. This is NOT a reusable native file.
    """
    stages=compile_program(m['analysis_steps'],m['conditions']);allbytes=[]
    for s in stages:
        if steps is not None and s['index'] not in steps:continue
        records=[]
        def rec(b):records.append(struct.pack(order+'I',len(b))+b+struct.pack(order+'I',len(b)))
        def ints(*v):rec(struct.pack(order+str(len(v))+'i',*v))
        def doubles(n,v=None):rec(struct.pack(order+str(n)+'d',*([0.]*n if v is None else v)))
        def empty(n=1):
            for _ in range(n):rec(b'')
        nk=len(m['nodes']);ne=len(m['elements']);assert ne==1 and not m['contacts']
        rec(b'Version DEVELOPMENT'.ljust(80));ints(s['index'])
        for v in (0,0,0,0,0,0,0,nk,ne,0,10):ints(v)
        ints(4,3,1)
        # nmpc ... ne2d. One native material, one temperature row.
        for v in (0,0,0,0,0,0,1,1,0,2,0,0,0,0,0,0,0,0,0,0,0,0):ints(v)
        ints(0,0,0,0);ints(4 if s['procedure']=='dynamic' else 1);ints(0,0)
        for v in (1,0,0,0,0,0,0,0,0):ints(v)
        empty(4)  # sets, start/end, heading (nalset=0)
        doubles(3*nk,[x for n in m['nodes'] for x in n['position_mm']])
        ints(*m['elements'][0]['node_ids']);ints(0);rec(b'C3D10   ')
        empty(6+3+5+2)  # boundary old, MPC, nodempc/coefmpc
        empty(6)  # force: nodes, dirs, value, sort, inverse, old
        empty(4+4)  # surface loads + body loads
        empty(3)  # prlab, prset, filab
        doubles(3);ints(2,1);doubles(2);ints(1);doubles(4);ints(0)
        doubles(7);ints(0,0);doubles(7);ints(0,0);doubles(1)
        doubles(14);doubles(11)
        rec(b'M1'.ljust(80));ints(1)
        doubles(4*nk,[delta]*(4*nk))
        if s['procedure']=='dynamic':doubles(4*nk)
        doubles(24*ne);doubles(24*ne);doubles(8*ne)
        doubles(52);doubles(2);ints(0);doubles(1,[s['end']]);ints(1,1)
        allbytes.append(b''.join(records))
    return b''.join(allbytes)
