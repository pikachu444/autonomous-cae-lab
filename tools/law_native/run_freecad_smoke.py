"""Own two separate FreeCAD GUI processes: native apply/Undo then cold read.

No executable discovery, imported PID control, or taskkill by program name.
"""
from pathlib import Path
import argparse,json,os,secrets,sys
from owned_check import run
ROOT=Path(__file__).resolve().parents[2]

def main():
    p=argparse.ArgumentParser();p.add_argument('--freecad',required=True);p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();exe=Path(a.freecad).resolve();source=Path(a.source).resolve();out=Path(a.output).resolve()
    if not exe.is_file() or not source.is_file():p.error('Explicit existing FreeCAD executable and source snapshot required')
    out.mkdir(parents=True,exist_ok=False);summary={'status':'STARTING','FE_execution':'NOT_RUN','cases':[]}
    prior={k:os.environ.get(k) for k in ('CAELAB_LAW_SMOKE_CONFIG','CAELAB_LAW_SMOKE_TOKEN')}
    code=1
    try:
        for mode in ('apply','cold'):
            token=secrets.token_hex(24);cfg={'repo':str(ROOT),'token':token,'mode':mode,
                'output':str(out/mode),'source':str(source),'previous':str(out/'apply')}
            path=out/(mode+'-config.json');path.write_text(json.dumps(cfg),encoding='utf-8')
            os.environ.update(CAELAB_LAW_SMOKE_CONFIG=str(path),CAELAB_LAW_SMOKE_TOKEN=token)
            status=run([str(exe),str(ROOT/'tools/law_native/freecad_smoke.FCMacro')],out/(mode+'-process'),90)
            native_path=out/mode/'receipt.json'
            native=json.loads(native_path.read_text(encoding='utf-8')) if native_path.is_file() else {'status':'MISSING_RECEIPT'}
            summary['cases'].append({'mode':mode,'supervisor_exit':status,'native':native})
            if status!=0 or native['status']!='PASS':raise RuntimeError('Native execution/exit not confirmed: '+mode)
        summary['status']='PASS';code=0
    except BaseException as error:summary.update(status='FAIL',error_type=type(error).__name__,error=str(error))
    finally:
        for k,v in prior.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v
        (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return code

if __name__=='__main__':raise SystemExit(main())
