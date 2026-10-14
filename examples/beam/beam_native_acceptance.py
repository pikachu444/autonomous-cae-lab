"""Native FreeCAD acceptance + separate read-only analytical comparison.

No solver is created here. Run calculations through the product's existing
Runner; comparison consumes those saved run folders. Numerical limits below
are declared before any native execution, not tuned to synthetic fixtures.
"""
from copy import deepcopy
from pathlib import Path
import json
import math
import uuid
from caelab.storage import save_json

LIMITS={'tip_displacement_relative':.02,'tip_displacement_absolute_mm':1e-8,
        'interior_section_moment_relative':.01,'interior_section_moment_absolute_Nmm':1e-4,
        'interior_station_fraction':[.2,.8]}
REFERENCES={
    'moment_1':{'tip_component':'UZ','tip_mm':-1000*1000**2/(2*210000*(10*20**3/12)),
                'theta1_rad':1000*1000/(210000*(10*20**3/12)),'section_component':'M1','section_Nmm':1000},
    'moment_2':{'tip_component':'UY','tip_mm':1000*1000**2/(2*210000*(20*10**3/12)),
                'theta2_rad':1000*1000/(210000*(20*10**3/12)),'section_component':'M2','section_Nmm':1000},
    'section_90':{'tip_component':'UZ','tip_mm':-1000*1000**2/(2*210000*(20*10**3/12)),
                  'theta2_rad':-1000*1000/(210000*(20*10**3/12)),'section_component':'M2','section_Nmm':-1000},
    'end_force':{'tip_component':'UZ','tip_mm':-1000**3/(3*210000*(10*20**3/12))},
    'rotation':{'tip_component':'UZ','tip_mm':-math.radians(.01)*1000},
}


def _require(condition,message):
    if not condition:raise ValueError(message)


def _command(owner,operation,arguments):
    owner.refresh()
    result=owner.dispatch({'command_id':'C'+uuid.uuid4().hex,'document_id':owner.document_id,
        'session_id':owner.session_id,'expected_generation':owner.generation,
        'operation':operation,'arguments':arguments,'target':{}})
    if result.get('status')!='COMPLETED':raise RuntimeError(str(result.get('error',result)))
    return result['result']


def export_and_reopen(root):
    """Run inside ordinary FreeCAD 1.1.4, not alongside another CAD broker owner.

    Tests actual native objects, native writers, native FCStd save/open, and
    explicit Undo/Redo of invalid drafts. Retains per-case failures unchanged.
    """
    import FreeCAD as App,FreeCADGui as Gui
    from apps.desktop_pre import cae_prep
    from apps.desktop_pre.bridge import Owner
    from examples.beam.beam_example import create
    if getattr(cae_prep,'CONNECTION',None) is not None:
        raise ValueError('별도 일반 FreeCAD에서 native 검사를 실행하세요. 실행 중인 제품 owner를 복제하지 않습니다.')
    root=Path(root).absolute()/('native-'+uuid.uuid4().hex);root.mkdir(parents=True)
    report={'kind':'beam-native-acceptance','freecad_version':list(map(str,App.Version())),
        'declared_limits':LIMITS,'cases':{},'solver_executed':False,'gui_acceptance':'NOT_RUN'}
    for case in ('moment_1','moment_2','section_90','end_force','rotation','zero_draft','oblique_torsion'):
        owner=None;row={'status':'FAILED'}
        try:
            owner,key=create(case,output_root=root/'exchange',attach=False)
            original=deepcopy(owner.beam.inspect(key)['record'])
            if case=='zero_draft':
                _require(original['draft']['section']['width_mm']=='0', "Native acceptance condition failed: original['draft']['section']['width_mm']=='0'")
                _require(not owner.beam.inspect(key)['can_freeze'], "Native acceptance condition failed: not owner.beam.inspect(key)['can_freeze']")
                failed=owner.dispatch({'command_id':'C'+uuid.uuid4().hex,'document_id':owner.document_id,
                    'session_id':owner.session_id,'expected_generation':owner.generation,
                    'operation':'pre.beam.freeze','arguments':{'analysis_id':key},'target':{}})
                _require(failed['status']=='FAILED', "Native acceptance condition failed: failed['status']=='FAILED'")
                draft=deepcopy(original['draft']);draft['section']['width_mm']='1e'
                _command(owner,'pre.beam.draft',{'analysis_id':key,'draft':draft})
                _command(owner,'document.undo',{})
                _require(owner.beam._get(key)['draft']['section']['width_mm']=='0','Undo must restore the raw zero-width draft')
                _command(owner,'document.redo',{})
                _require(owner.beam._get(key)['draft']['section']['width_mm']=='1e','Redo must restore the unfinished numeric draft')
                original=deepcopy(owner.beam._get(key));_command(owner,'document.save',{})
                from apps.desktop_pre.projects import save_native_copy
                path=root/'invalid-draft.FCStd';save_native_copy(owner.doc,path,App=App)
            else:
                frozen=_command(owner,'pre.beam.freeze',{'analysis_id':key})
                manifest=owner.export_root/frozen['snapshot_relative'];path=manifest.parent/'editable.FCStd'
                row['snapshot']=str(manifest);row['input']=str(manifest.parent/'beam.inp')
                data=json.loads((manifest.parent/'mesh.json').read_text())
                row['axes']=data['axes'];row['loads']=data['loads'];row['boundaries']=data['boundaries']
            old_session=owner.session_id;name=owner.doc.Name;owner.close();App.closeDocument(name);owner=None
            reopened=App.openDocument(str(path));reopened.recompute()
            owner=Owner(reopened,root/'exchange',App=App,Gui=Gui)
            restored=owner.beam.inspect(key)
            _require(owner.session_id!=old_session and restored['record']['draft']==original['draft'], "Native acceptance condition failed: owner.session_id!=old_session and restored['record']['draft']==original['draft']")
            _require(restored['can_freeze']==(case!='zero_draft'), "Native acceptance condition failed: restored['can_freeze']==(case!='zero_draft')")
            row.update(status='PASS',fresh_native_owner_reopen=True,raw_draft=restored['record']['draft'],
                       calculation_started_by_reopen=False)
        except Exception as exc:
            row.update(error_type=type(exc).__name__,message=str(exc))
        finally:
            if owner is not None:
                name=owner.doc.Name;owner.close();App.closeDocument(name)
            report['cases'][case]=row;save_json(root/'native_acceptance.json',report)
    return root/'native_acceptance.json'


def compare_saved(case,folder):
    """Compare actual native fields, never generate a substitute analytical result."""
    from caelab.adapters.beam_fem import read_saved_run
    from caelab.beam_model import validate_model,section_properties,number
    from caelab.beam_results import channels
    saved=read_saved_run(folder);m=saved['model'];r=saved['execution'];observed=saved['observed']
    report={'case':case,'limits':LIMITS,'source_folder':str(Path(folder).absolute()),
        'execution_status':r['execution_status'],'rotation_output':'NOT_AVAILABLE',
        'support_reaction_moment':'NOT_AVAILABLE','engineering_release':'UNKNOWN','checks':[]}
    if case=='oblique_torsion':
        report.update(status='DIAGNOSTIC_ONLY',axes=m['axes'] if m else None,diagnostics=r['diagnostics'])
        return report
    if case not in REFERENCES:raise ValueError('Select a declared physical comparison case')
    if r['execution_status']!='SUCCEEDED' or not observed:raise ValueError('A complete successful native run is required for physical comparison')
    d=m['draft'];_,_,stations=validate_model(m)
    _require(m['length_mm']==1000 and number(d['section']['width_mm'])==10 and number(d['section']['height_mm'])==20, "Native acceptance condition failed: m['length_mm']==1000 and number(d['section']['width_mm'])==10 and number(d['section']['height_mm'])==20")
    _require(number(d['material']['young_MPa'])==210000 and number(d['material']['poisson'])==.3, "Native acceptance condition failed: number(d['material']['young_MPa'])==210000 and number(d['material']['poisson'])==.3")
    _require(m['axes']['tangent']==[1.,0.,0.] and number(d['section']['rotation_deg'])==(90 if case=='section_90' else 0), "Native acceptance condition failed: m['axes']['tangent']==[1.,0.,0.] and number(d['section']['rotation_deg'])==(90 if case=='section_90' else 0)")
    # Explicitly reject a different saved load case before comparing any result.
    loaded=d['ends'][1];fixed=d['ends'][0]
    _require(m['end_node_ids'][0]==min(stations,key=stations.get) and loaded['system']=='global' and fixed['system']=='global', "Native acceptance condition failed: m['end_node_ids'][0]==min(stations,key=stations.get) and loaded['system']=='global' and fixed['system']=='global'")
    expected_force=[0,0,-1] if case=='end_force' else [0,0,0]
    expected_moment=[0,1000,0] if case in ('moment_1','section_90') else ([0,0,1000] if case=='moment_2' else [0,0,0])
    _require(list(map(number,loaded['force_N']))==expected_force and list(map(number,loaded['moment_Nmm']))==expected_moment, "Native acceptance condition failed: list(map(number,loaded['force_N']))==expected_force and list(map(number,loaded['moment_Nmm']))==expected_moment")
    _require(list(map(number,fixed['force_N']))==[0,0,0] and list(map(number,fixed['moment_Nmm']))==[0,0,0], "Native acceptance condition failed: list(map(number,fixed['force_N']))==[0,0,0] and list(map(number,fixed['moment_Nmm']))==[0,0,0]")
    _require(list(map(number,fixed['translation_mm']))==[0,0,0], "Native acceptance condition failed: list(map(number,fixed['translation_mm']))==[0,0,0]")
    _require(list(map(number,fixed['rotation_deg']))==([0,.01,0] if case=='rotation' else [0,0,0]), "Native acceptance condition failed: list(map(number,fixed['rotation_deg']))==([0,.01,0] if case=='rotation' else [0,0,0])")
    _require(all(v in ('',None) for v in loaded['translation_mm']+loaded['rotation_deg']), "Native acceptance condition failed: all(v in ('',None) for v in loaded['translation_mm']+loaded['rotation_deg'])")
    ref=REFERENCES[case];values=channels(observed['frames'][-1]);tip=max(stations,key=stations.get)
    actual=values[ref['tip_component']]['values'][tip];expected=ref['tip_mm']
    tolerance=LIMITS['tip_displacement_absolute_mm']+abs(expected)*LIMITS['tip_displacement_relative']
    report['checks'].append({'quantity':ref['tip_component'],'unit':'mm','node':tip,'actual':actual,
        'reference':expected,'absolute_limit':tolerance,'pass':abs(actual-expected)<=tolerance})
    if 'section_component' in ref:
        ch=values[ref['section_component']];expected=ref['section_Nmm']
        tolerance=LIMITS['interior_section_moment_absolute_Nmm']+abs(expected)*LIMITS['interior_section_moment_relative']
        for n,s in sorted(stations.items(),key=lambda item:item[1]):
            if .2<=s/m['length_mm']<=.8:
                actual=ch['values'][n]
                report['checks'].append({'quantity':ref['section_component'],'unit':'Nmm','node':n,
                    'station_mm':s,'actual':actual,'reference':expected,'absolute_limit':tolerance,'pass':abs(actual-expected)<=tolerance})
    report.update(status='PASS' if all(row['pass'] for row in report['checks']) else 'FAIL',
        analytical_reference=ref,section_properties=section_properties(d))
    return report


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Read-only physical check of an existing beam calculation')
    parser.add_argument('case',choices=[*REFERENCES,'oblique_torsion']);parser.add_argument('folder');parser.add_argument('--output',required=True)
    args=parser.parse_args();target=Path(args.output)
    if target.exists():raise FileExistsError('Do not overwrite a previous acceptance report')
    save_json(target,compare_saved(args.case,args.folder))
