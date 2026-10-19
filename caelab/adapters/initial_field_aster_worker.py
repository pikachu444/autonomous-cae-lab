"""Actual Aster command consumer; imports native modules only inside solve."""
from pathlib import Path
import json,hashlib
try:
    from .codeaster_frozen_worker import mesh_text,check_import
    from .codeaster_worker import _runtime_versions,_save,VECTOR_COMPONENTS,STRESS_COMPONENTS
except ImportError:
    from codeaster_frozen_worker import mesh_text,check_import
    from codeaster_worker import _runtime_versions,_save,VECTOR_COMPONENTS,STRESS_COMPONENTS


def solve(input_path):
    from code_aster.Commands import (DEBUT,FIN,LIRE_MAILLAGE,AFFE_MODELE,DEFI_MATERIAU,AFFE_MATERIAU,
        AFFE_CHAR_MECA,CREA_CHAMP,DEFI_LIST_REEL,DEFI_FONCTION,STAT_NON_LINE,CALC_CHAMP,CREA_TABLE,IMPR_RESU)
    from code_aster.Cata.Syntax import _F
    path=Path(input_path);config=json.loads(path.read_text(encoding='utf-8'));root=path.parent
    meshpath=root/'mesh.json';meshrecord=json.loads(meshpath.read_text(encoding='utf-8'))
    if hashlib.sha256(meshpath.read_bytes()).hexdigest()!=config['mesh_record_sha256'] or hashlib.sha256(Path('fort.20').read_bytes()).hexdigest()!=config['mail_sha256']:
        raise ValueError('Retained initial-state mesh changed before native import')
    DEBUT();versions,runtime=_runtime_versions()
    if versions.get('code_aster')!='17.4.0':raise ValueError('Configured Code_Aster 17.4.0 is required')
    mesh=LIRE_MAILLAGE(FORMAT='ASTER',UNITE=20);guard=check_import(mesh,meshrecord);_save(root/'native_mesh_checks.json',guard)
    model=AFFE_MODELE(MAILLAGE=mesh,AFFE=_F(TOUT='OUI',PHENOMENE='MECANIQUE',MODELISATION='3D'))
    mat=DEFI_MATERIAU(ELAS=_F(E=config['material']['young_modulus_MPa'],NU=config['material']['poisson_ratio']))
    assigned=AFFE_MATERIAU(MAILLAGE=mesh,AFFE=_F(TOUT='OUI',MATER=mat))
    definition=config['initial_field_definition'];initial=definition['compatible'];labels={int(k):v for k,v in config['node_labels'].items()}
    u0=CREA_CHAMP(OPERATION='AFFE',TYPE_CHAM='NOEU_DEPL_R',MAILLAGE=mesh,PROL_ZERO='NON',
        AFFE=tuple(_F(NOEUD=labels[r['node_id']],NOM_CMP=VECTOR_COMPONENTS,VALE=tuple(r['value'])) for r in initial['displacements_mm']))
    sig0=CREA_CHAMP(OPERATION='AFFE',TYPE_CHAM='ELGA_SIEF_R',MODELE=model,PROL_ZERO='NON',
        AFFE=_F(TOUT='OUI',NOM_CMP=STRESS_COMPONENTS,VALE=tuple(initial['stress_MPa'])))
    initial_tables={}
    for key,field,components in (('DEPL',u0,VECTOR_COMPONENTS),('SIGM',sig0,STRESS_COMPONENTS)):
        initial_tables[key]=CREA_TABLE(RESU=_F(CHAM_GD=field,TOUT='OUI',NOM_CMP=components)).EXTR_TABLE().values()
    _save(root/'provided_initial_fields.table.json',initial_tables)
    bc={}
    for row in meshrecord['fixed_dofs']:bc.setdefault(row['node_id'],{})[VECTOR_COMPONENTS[row['component']-1]]=row['value_mm']
    support=AFFE_CHAR_MECA(MODELE=model,DDL_IMPO=tuple(_F(NOEUD=labels[n],**v) for n,v in bc.items()))
    loads={}
    for row in meshrecord['loads']:loads.setdefault(row['node_id'],{})[('FX','FY','FZ')[row['component']-1]]=row['force_N']
    excit=[_F(CHARGE=support)]
    if loads:
        force=AFFE_CHAR_MECA(MODELE=model,FORCE_NODALE=tuple(_F(NOEUD=labels[n],**v) for n,v in loads.items()))
        times=[0.,definition['states'][0]['load_factor']]
        for state in definition['states']:times.extend((state['parameter'],state['load_factor']))
        func=DEFI_FONCTION(NOM_PARA='INST',VALE=tuple(times))
        excit.append(_F(CHARGE=force,FONC_MULT=func))
    inst=DEFI_LIST_REEL(DEBUT=0.,INTERVALLE=tuple(_F(JUSQU_A=s['parameter'],NOMBRE=1) for s in definition['states']))
    result=STAT_NON_LINE(MODELE=model,CHAM_MATER=assigned,COMPORTEMENT=_F(RELATION='ELAS',DEFORMATION='PETIT'),
        ETAT_INIT=_F(DEPL=u0,SIGM=sig0),INCREMENT=_F(LIST_INST=inst,NUME_INST_INIT=0),EXCIT=tuple(excit),
        NEWTON=_F(MATRICE='TANGENTE',REAC_ITER=1),CONVERGENCE=_F(RESI_GLOB_RELA=1e-8,ITER_GLOB_MAXI=30),
        SOLVEUR=_F(METHODE='MUMPS'))
    result=CALC_CHAMP(reuse=result,RESULTAT=result,FORCE='REAC_NODA')
    indexes=list(result.getIndexes());access=result.getAccessParameters();states=[]
    for order in indexes:
        tables={}
        for field,components in (('DEPL',VECTOR_COMPONENTS),('REAC_NODA',VECTOR_COMPONENTS),('SIEF_ELGA',STRESS_COMPONENTS)):
            table=CREA_TABLE(RESU=_F(RESULTAT=result,NOM_CHAM=field,NUME_ORDRE=order,NOM_CMP=components,TOUT='OUI'))
            tables[field]=table.EXTR_TABLE().values();_save(root/(str(order)+'_'+field.lower()+'.json'),tables[field])
        position=access['NUME_ORDRE'].index(order)
        states.append({'order':order,'available_orders':[order],
            'access_parameters':{'NUME_ORDRE':[order],'INST':[access['INST'][position]]},'tables':tables,
            'native_mesh_checks':guard,'versions':versions,'solver_status':'COMPLETED','converged':True})
    IMPR_RESU(FORMAT='MED',UNITE=80,RESU=_F(RESULTAT=result,NOM_CHAM=('DEPL','REAC_NODA','SIEF_ELGA')))
    _save(root/'worker_result.json',{'solver_status':'COMPLETED','converged':True,'versions':versions,
        'code_aster_runtime':runtime,'states':states,'provided_initial':initial,
        'native_initial_snapshot_status':'CREATED_BY_CREA_CHAMP; retained provided field, not an equilibrated order',
        'native_initial_tables':initial_tables,'native_mesh_checks':guard,'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'mail_sha256':config['mail_sha256']})
    FIN()
