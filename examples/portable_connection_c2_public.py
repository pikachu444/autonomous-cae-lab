"""Public C2 file/owner acceptance; fixture algebra is not a physical solver.

Creation reuses the exact Numerical C2 test fixtures. No evaluator is allowed in
cold mode. Run from the source root; pytest is an existing test dependency.
"""
from pathlib import Path
import argparse
import json
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    parser.add_argument('--cold',type=Path)
    parser.add_argument('--request',type=Path)
    parser.add_argument('--result',type=Path)
    parser.add_argument('--inspect-only',action='store_true')
    parser.add_argument('--no-adopt',action='store_true')
    parser.add_argument('--no-recopy',action='store_true')
    args=parser.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
    from _portable_connection_c2_support import make_pending,make_bound,copied,run_cold,cold_actions,persisted_check
    from caelab.storage import load_json,save_json
    if args.cold:
        request=load_json(args.request) if args.request else None
        result=(persisted_check(args.cold,request) if args.inspect_only else
                cold_actions(args.cold,request,adopt=not args.no_adopt,recopy=not args.no_recopy))
        save_json(args.result,result);print(json.dumps(result,ensure_ascii=False));return
    if args.output is None:parser.error('--output is required')
    args.output.mkdir(parents=True,exist_ok=False)
    results=[]
    for name,builder in [('pending_evidence',make_pending),('bound_adoption',make_bound)]:
        folder=args.output/name;folder.mkdir()
        origin=folder/'원본 보관소'; wb,chosen,request=builder(origin)
        try:copied(wb,chosen,folder/'이동 전 사본')
        finally:wb.shutdown()
        origin.rename(folder/'원본 보존 연결 해제')
        target=folder/'한글 공백 작업 사본';(folder/'이동 전 사본').rename(target)
        assert not origin.exists()
        results.append(run_cold(target,request,folder/'cold'))
    save_json(args.output/'acceptance.json',results)
    print(json.dumps(results,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
