"""Pinned Code_Aster 17.4 continuous contact; standalone inside existing SIF.

All field tables are saved before product interpretation. Labels, not spatial
nearest neighbours, bind coincident independent bodies to the native mesh.
"""
from pathlib import Path
import json, hashlib, math

if __package__:
    from .codeaster_worker import _runtime_versions, _save
else:
    from codeaster_worker import _runtime_versions, _save

VERSION='17.4.0'
SOURCE='50ebc13c70ee9df62faf93ddcb746a3757b3042a'
DISPLACEMENT=('DX','DY','DZ')
CONTACT_COMPONENTS=('CONT','JEU','RNX','RNY','RNZ','RTAX','RTAY','RTAZ','RTGX','RTGY','RTGZ')
MULTIPLIERS=('LAGS_C','LAGS_F1','LAGS_F2')

def command_text():
    return "import sys\nsys.path.insert(0, '/work')\nfrom contact_aster_worker import solve\nsolve('/work/solver/input.json')\n"

def mesh_text(model):
    from .contact_aster_model import face_slots
    nodes=sorted(model['nodes'],key=lambda r:r['node_id'])
    elements=sorted(model['elements'],key=lambda r:r['element_id'])
    if not nodes or len(nodes)>200000 or not elements or len(elements)>500000:
        raise ValueError('기존 Aster 입력 크기 한도를 넘었습니다. 원 모델은 보존되며 메시를 자동 축소하지 않습니다.')
    labels={r['node_id']:'N'+str(r['node_id']) for r in nodes}
    catalog={'nodes':{labels[r['node_id']]:dict(id=r['node_id'],xyz=r['position_mm']) for r in nodes},'cells':{},'groups':{},'pairs':{}}
    lines=['TITRE','CAE Lab user-body CONTINUE hard contact mm N MPa','FINSF','COOR_3D']
    for r in nodes:
        lines += [labels[r['node_id']]+' '+' '.join(format(v,'.17g') for v in r['position_mm'][:2]),format(r['position_mm'][2],'.17g')]
    lines+=['FINSF']
    for kind,native in (('C3D10','TETRA10'),('C3D8','HEXA8')):
        rows=[r for r in elements if r['type']==kind]
        if not rows:continue
        lines.append(native)
        for r in rows:
            name='M'+str(r['element_id']);conn=[labels[n] for n in r['node_ids']]
            lines += [name+' '+' '.join(conn[:5]),' '.join(conn[5:])]
            catalog['cells'][name]=dict(type=native,nodes=conn,element_id=r['element_id'])
        lines.append('FINSF')
    catalog['groups']['BODY']=['M'+str(r['element_id']) for r in elements]
    for index,body in enumerate(sorted(model['body_maps']),1):
        catalog['groups']['B'+str(index)]=['M'+str(r['element_id']) for r in elements if r['body_id']==body]
    byid={r['element_id']:r for r in elements};facenum=0
    for index,pair in enumerate(model['contacts'],1):
        groups={}
        for side in ('a','b'):
            names=[];native_nodes=set()
            for e,f in pair[side]['element_faces']:
                r=byid[e];conn=[labels[r['node_ids'][i]] for i in face_slots(r)[f]]
                facenum+=1;name='F'+str(facenum);native='TRIA6' if len(conn)==6 else 'QUAD4'
                lines += [native,name+' '+' '.join(conn[:5])]
                if len(conn)>5:lines.append(' '.join(conn[5:]))
                lines.append('FINSF');names.append(name);native_nodes.update(conn)
                catalog['cells'][name]=dict(type=native,nodes=conn,element_id=e,face=f)
            group='P'+str(index)+side.upper();groups[side]=group
            catalog['groups'][group]=names
            lines+=['GROUP_NO',group,*sorted(native_nodes,key=lambda n:int(n[1:])),'FINSF']
        catalog['pairs'][pair['object_id']]={'groups':groups,'slave_node_ids':sorted(int(n[1:]) for n in {
            n for c in catalog['groups'][groups['a']] for n in catalog['cells'][c]['nodes']})}
    for name,cells in catalog['groups'].items():lines+=['GROUP_MA',name,*cells,'FINSF']
    lines+=['FIN','']
    return '\n'.join(lines),labels,catalog

def capture_import(mesh,catalog):
    coords=mesh.getCoordinates().toNumpy().tolist()
    if mesh.getNumberOfNodes()!=len(catalog['nodes']) or mesh.getNumberOfCells()!=len(catalog['cells']):
        raise ValueError('Native contact mesh count differs')
    node_order=[];node_names=[]
    for i in mesh.getNodes():
        label=mesh.getNodeName(i).strip();node_names.append(label)
        if label not in catalog['nodes']:raise ValueError('Native node label is not in exact input')
        row=catalog['nodes'][label];node_order.append(row['id'])
        if len(coords[i])!=3 or any(not math.isclose(a,b,rel_tol=1e-13,abs_tol=1e-13) for a,b in zip(coords[i],row['xyz'])):
            raise ValueError('Native node coordinate changed')
    if len(set(node_names))!=len(node_names):raise ValueError('Native node labels merged or duplicated')
    cell_names=[];connectivity=mesh.getConnectivity()
    for i in range(mesh.getNumberOfCells()):
        label=mesh.getCellName(i).strip();cell_names.append(label)
        row=catalog['cells'].get(label)
        if row is None or row['type']!=mesh.getCellTypeName(i) or row['nodes']!=[node_names[n] for n in connectivity[i]]:
            raise ValueError('Native ordered element/face connectivity changed')
    if len(set(cell_names))!=len(cell_names):raise ValueError('Native cell labels duplicated')
    for group,wanted in catalog['groups'].items():
        if set(wanted)!={cell_names[i] for i in mesh.getCells(group)}:raise ValueError('Native body/contact surface group changed')
    return dict(status='PASS',node_ids_in_native_order=node_order,cell_names_in_native_order=cell_names,
        coordinates_in_native_order=coords,source_commit=SOURCE,gate='BEFORE_STAT_NON_LINE')

def solve(input_path):
    from code_aster.Commands import (DEBUT,FIN,LIRE_MAILLAGE,MODI_MAILLAGE,AFFE_MODELE,
        DEFI_MATERIAU,AFFE_MATERIAU,AFFE_CHAR_MECA,DEFI_CONTACT,STAT_NON_LINE,
        DEFI_LIST_REEL,DEFI_LIST_INST,DEFI_FONCTION,CALC_CHAMP,CREA_TABLE,IMPR_RESU)
    from code_aster.Cata.Syntax import _F
    path=Path(input_path);root=path.parent;config=json.loads(path.read_text(encoding='utf-8'))
    raw_mesh=root/'mesh.json'
    if hashlib.sha256(raw_mesh.read_bytes()).hexdigest()!=config['mesh_record_sha256']:
        raise ValueError('Prepared body model changed')
    expected=json.loads(raw_mesh.read_text(encoding='utf-8'))
    DEBUT()
    versions,runtime=_runtime_versions()
    if versions.get('code_aster')!=VERSION:raise ValueError('Configured Code_Aster17.4.0 required')
    if hashlib.sha256(Path('fort.20').read_bytes()).hexdigest()!=config['mail_sha256']:
        raise ValueError('Native linked mesh changed')
    mesh=LIRE_MAILLAGE(FORMAT='ASTER',UNITE=20)
    guard=capture_import(mesh,config['catalog']);_save(root/'native_mesh_checks.json',guard)
    surfaces=tuple(g for p in config['catalog']['pairs'].values() for g in p['groups'].values())
    # Reorient only the explicitly emitted skin cells against unchanged volumes.
    mesh=MODI_MAILLAGE(reuse=mesh,MAILLAGE=mesh,ORIE_PEAU_3D=_F(GROUP_MA=surfaces,GROUP_MA_VOLU='BODY'))
    oriented={};connectivity=mesh.getConnectivity()
    for group in surfaces:
        oriented[group]=[dict(cell_name=mesh.getCellName(i).strip(),type=mesh.getCellTypeName(i),
            node_names=[mesh.getNodeName(n).strip() for n in connectivity[i]]) for i in mesh.getCells(group)]
    _save(root/'native_oriented_skin.json',oriented)
    native_policy=dict(source_commit=SOURCE,FORMULATION='CONTINUE',ALGO_CONT='STANDARD',
        ALGO_FROT='STANDARD' if expected['contacts'][0]['draft']['tangential_law']=='coulomb' else None,
        INTEGRATION='AUTO',REAC_GEOM='SANS',CONTACT_INIT='INTERPENETRE',
        initial_active_set='native 1e-6 * shortest nonzero mesh edge; not a physical acceptance tolerance',
        oriented_skin=oriented,source_order='FreeCAD raw -> explicit producer slots -> Aster; no coordinate welding')
    _save(root/'native_contact_policy.json',native_policy)
    model=AFFE_MODELE(MAILLAGE=mesh,AFFE=_F(TOUT='OUI',PHENOMENE='MECANIQUE',MODELISATION='3D'))
    material=[]
    for i,body in enumerate(sorted(expected['body_maps']),1):
        row=next(m for m in expected['materials'] if m['body_id']==body)
        material.append(_F(GROUP_MA='B'+str(i),MATER=DEFI_MATERIAU(ELAS=_F(E=row['young_modulus_MPa'],NU=row['poisson_ratio']))))
    assigned=AFFE_MATERIAU(MAILLAGE=mesh,AFFE=tuple(material))
    ddl=[]
    for row in expected['boundary_dofs']:
        ddl.append(_F(NOEUD='N'+str(row['node_id']),**{DISPLACEMENT[row['component']-1]:row['value_mm']}))
    forces=[]
    for row in expected['loads']:
        forces.append(_F(NOEUD='N'+str(row['node_id']),**{('FX','FY','FZ')[row['component']-1]:row['force_N']}))
    loadkw=dict(MODELE=model,DDL_IMPO=tuple(ddl))
    if forces:loadkw['FORCE_NODALE']=tuple(forces)
    load=AFFE_CHAR_MECA(**loadkw)
    zones=[]
    # DEFI_CONTACT FROTTEMENT is global. Mixed frictionless/Coulomb is encoded
    # with a verified zero Coulomb coefficient only when every pair is Coulomb.
    laws={p['draft']['tangential_law'] for p in expected['contacts']}
    if len(laws)!=1:raise ValueError('One continuous contact definition requires the same friction formulation for all pairs')
    friction=next(iter(laws))=='coulomb'
    for pair in expected['contacts']:
        groups=config['catalog']['pairs'][pair['object_id']]['groups']
        zone=dict(GROUP_MA_ESCL=groups['a'],GROUP_MA_MAIT=groups['b'],ALGO_CONT='STANDARD',
            INTEGRATION='AUTO',CONTACT_INIT='INTERPENETRE',NORMALE='MAIT',VECT_MAIT='AUTO',VECT_ESCL='AUTO')
        if friction:zone.update(COULOMB=float(pair['draft']['friction_coefficient']),ALGO_FROT='STANDARD',GRAND_GLIS='NON')
        zones.append(_F(**zone))
    policy=dict(FORMULATION='CONTINUE',MODELE=model,FROTTEMENT='COULOMB' if friction else 'SANS',
        ALGO_RESO_GEOM='POINT_FIXE',REAC_GEOM='SANS',
        ALGO_RESO_CONT='POINT_FIXE',VERI_NORM='OUI',LISSAGE='NON',ZONE=tuple(zones))
    if friction:policy['ALGO_RESO_FROT']='POINT_FIXE'
    contact=DEFI_CONTACT(**policy)
    step=expected['step'];end=float(step['period']);initial=float(step['initial'])
    # The captured increment is an input, not a synthetic output clock.
    n=max(1,math.ceil(end/min(initial,float(step['maximum']))))
    if n>step['increments']:raise ValueError('Requested increment count exceeds captured maximum')
    listing=DEFI_LIST_REEL(DEBUT=0.,INTERVALLE=_F(JUSQU_A=end,NOMBRE=n))
    increments=DEFI_LIST_INST(DEFI_LIST=_F(LIST_INST=listing),ECHEC=_F(EVENEMENT='ERREUR',ACTION='DECOUPE',
        SUBD_METHODE='MANUEL',SUBD_PAS=2,SUBD_PAS_MINI=float(step['minimum']))) if step['automatic'] else listing
    ramp=DEFI_FONCTION(NOM_PARA='INST',VALE=(0.,0.,end,1.))
    result=STAT_NON_LINE(MODELE=model,CHAM_MATER=assigned,CONTACT=contact,
        EXCIT=_F(CHARGE=load,FONC_MULT=ramp),COMPORTEMENT=_F(GROUP_MA='BODY',RELATION='ELAS',DEFORMATION='PETIT'),
        INCREMENT=_F(LIST_INST=increments),SOLVEUR=_F(METHODE='MUMPS'))
    result=CALC_CHAMP(reuse=result,RESULTAT=result,FORCE='REAC_NODA')
    orders=list(result.getIndexes());tables=[]
    for order in orders:
        fields={}
        for field,components in (('DEPL',DISPLACEMENT),('REAC_NODA',DISPLACEMENT)):
            table=CREA_TABLE(RESU=_F(RESULTAT=result,NOM_CHAM=field,NUME_ORDRE=order,NOM_CMP=components,TOUT='OUI'))
            fields[field]=table.EXTR_TABLE().values();_save(root/(field+'-'+str(order)+'.json'),fields[field])
        pair_fields={}
        for name,pair in config['catalog']['pairs'].items():
            scope=dict(RESULTAT=result,NUME_ORDRE=order,GROUP_NO=pair['groups']['a'])
            contact_table=CREA_TABLE(RESU=_F(NOM_CHAM='CONT_NOEU',NOM_CMP=CONTACT_COMPONENTS,**scope))
            multiplier_table=CREA_TABLE(RESU=_F(NOM_CHAM='DEPL',NOM_CMP=MULTIPLIERS if friction else ('LAGS_C',),**scope))
            pair_fields[name]={'CONT_NOEU':contact_table.EXTR_TABLE().values(),'MULTIPLIERS':multiplier_table.EXTR_TABLE().values()}
            _save(root/(name+'-'+str(order)+'.json'),pair_fields[name])
        tables.append(dict(order=order,fields=fields,pairs=pair_fields))
    IMPR_RESU(FORMAT='MED',UNITE=80,RESU=_F(RESULTAT=result,NOM_CHAM=('DEPL','REAC_NODA','CONT_NOEU'),TOUT_ORDRE='OUI'))
    _save(root/'worker_result.json',dict(solver_status='COMPLETED',converged=True,versions=versions,
        code_aster_runtime=runtime,source_commit=SOURCE,native_mesh_checks=guard,available_orders=orders,
        access_parameters=result.getAccessParameters(),tables=tables,native_contact_policy=native_policy,
        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),mail_sha256=config['mail_sha256']))
    FIN()
