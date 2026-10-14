"""Verify a copied native shell result without importing FreeCAD or running ccx."""
import argparse
import json
from pathlib import Path
from caelab.shell_inspection import explicit_manifest,load,inspect


def main():
    parser=argparse.ArgumentParser(description='저장된 셸 상·하면 결과 원자료 확인. 솔버를 실행하지 않습니다.')
    parser.add_argument('manifest',type=Path,help='복사한 post/shell_inspection.json')
    parser.add_argument('--element',type=int)
    parser.add_argument('--node',type=int)
    args=parser.parse_args()
    view,metadata=explicit_manifest(args.manifest)
    bundle=load(view,metadata['shell_inspection'])
    locations=bundle['data']['surface']['locations']
    first=next((r for r in locations if args.element is None or r['element_id']==args.element),None)
    if first is None:parser.error('선택 요소의 실제 저장 위치가 없습니다.')
    element=args.element if args.element is not None else first['element_id']
    node=args.node if args.node is not None else first['shell_node_id']
    result={side:inspect(view,side=side,element_id=element,shell_node_id=node) for side in ('top','bottom')}
    print(json.dumps({'verified':True,'solver_execution':'NOT_PERFORMED',
                      'engineering_valid':False,'observations':result},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
