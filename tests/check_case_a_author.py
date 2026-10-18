"""One explicitly declared, owned FreeCAD authoring process; never run FE."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.native_check import run_native_check
from caelab.storage import canonical_hash,save_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--packet-sha256',required=True)
    parser.add_argument('--freecad',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    packet=json.loads(args.packet.read_text(encoding='utf-8'))
    assert canonical_hash(packet)==args.packet_sha256
    token=uuid.uuid4().hex
    config=dict(repo=str(ROOT),packet=str(args.packet.resolve()),packet_sha256=args.packet_sha256,
                output=str((args.output/'native').resolve()),token=token)
    path=args.output/'config.json';save_json(path,config)
    keys=('CAELAB_CASE_A_CONFIG','CAELAB_CASE_A_TOKEN','CAELAB_CASE_A_REPO',
          'PYTHONHOME','PYTHONPATH','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','QT_QPA_PLATFORM','QML2_IMPORT_PATH')
    prior={key:os.environ.get(key) for key in keys}
    try:
        for key in keys:os.environ.pop(key,None)
        os.environ.update(CAELAB_CASE_A_CONFIG=str(path.resolve()),CAELAB_CASE_A_TOKEN=token,
                          CAELAB_CASE_A_REPO=str(ROOT))
        receipt=run_native_check([str(args.freecad.resolve()),'-u',str((args.output/'user.cfg').resolve()),
            '-s',str((args.output/'system.cfg').resolve()),str(ROOT/'tests/law_native/author_case_a.FCMacro')],
            args.output/'process',150,ROOT)
        save_json(args.output/'receipt.json',asdict(receipt))
        report=json.loads((args.output/'native'/'author.json').read_text(encoding='utf-8'))
        print(json.dumps(report,ensure_ascii=False))
        assert receipt.exit_code==0 and receipt.cleanup=='job_empty'
        assert report['status']=='PASS',report
        assert report['solver_calls']==0 and len(report['cases'])==3
    finally:
        for key,value in prior.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value


if __name__=='__main__':main()
