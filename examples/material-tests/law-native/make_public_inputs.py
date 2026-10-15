"""Emit public inputs and independent expected values; this does NOT run FE."""
from pathlib import Path
import sys,json,argparse
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from caelab.law_native_fe import default_settings
from plugins.material_point import law_native as law,viscoelastic_reference as original
from reference_cases import protocols,neo_reference

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
    def write(name,obj):(out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    for model in law.MODELS:
        s=default_settings(model);write(model+'-point.json',{'backend':law.POINT,'settings':s['law']})
        write(model+'-fe.json',{'backend':law.FE,'settings':s})
    cases=protocols()
    for case in cases:write('dp-'+case['id']+'.json',{'backend':law.POINT,'settings':case['settings']})
    write('dp-independent-expected.json',{'evidence':'INDEPENDENT_EXPECTED_NOT_FE_EXECUTION','cases':cases})
    for refined in (False,True):
        settings=original.canonical_settings(refined=refined);s=default_settings('single_branch_maxwell')
        s['law']=law.from_saved_legacy({'backend':'material.mfront.viscoelastic','settings':settings})
        label='refined17' if refined else 'canonical9'
        write('sls-'+label+'-fe.json',{'backend':law.FE,'settings':s})
        write('sls-'+label+'-expected.json',{'evidence':'ORIGINAL_INDEPENDENT_REFERENCE_NOT_NEW_NATIVE_EXECUTION',
            'settings':settings,'expected':original.analytical_reference(settings)})
    s=law.default_settings('neo_hooke')
    write('neo-independent-expected.json',{'evidence':'ANALYTIC_EXPECTED_NOT_FELUPE_EXECUTION',
        'settings':s,'states':[neo_reference(F,**s['parameters']) for F in s['deformation_gradient']]})
    write('README.json',{'native_execution':'NOT_RUN_BY_INPUT_GENERATOR','units':'mm, MPa, s, N',
         'physical_measurement':False,'required_runtime':{'felupe':law.FELUPE_VERSION},
         'source_kind':'PUBLIC_SYNTHETIC','approval':'UNKNOWN'})

if __name__=='__main__':main()
