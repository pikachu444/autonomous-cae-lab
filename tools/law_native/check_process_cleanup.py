"""Exercise exact child finally cleanup for success, failure and timeout."""
from pathlib import Path
import argparse,json,sys
from owned_check import run

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    root=Path(a.output);root.mkdir(parents=True,exist_ok=False);rows=[]
    for name,source,timeout,expected in [('success','print("owned success")',3,'PASS'),
            ('failure','raise RuntimeError("intentional owned failure")',3,'FAIL'),
            ('timeout','import time; time.sleep(20)',.2,'TIMEOUT')]:
        code=run([sys.executable,'-c',source],root/name,timeout)
        receipt=json.loads((root/name/'receipt.json').read_text())
        rows.append({'case':name,'supervisor_exit':code,'receipt':receipt})
        assert receipt['status']==expected and receipt['cleanup']=='CONFIRMED_REAPED',receipt
    (root/'summary.json').write_text(json.dumps({'status':'PASS','intentional_failure_and_timeout_preserved':True,'cases':rows},indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
