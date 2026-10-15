"""C3A CLI over the SAME existing loopback Client. Starts no service or owner.

Request files hold metadata tokens/selections, never raw file uploads. Read
outputs can contain original engineering content and use explicit new files.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .portable_project_io import json_file
from .workbench_client import Client


def main(argv=None):
    parser=argparse.ArgumentParser(description='이동 사본: 명시 보관 원문 선택·읽기·현재 편집 이어가기')
    parser.add_argument('action',choices=['catalog','read','inspect','create','preview','resume'])
    parser.add_argument('--service',required=True)
    parser.add_argument('--request',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--approved',action='store_true')
    parser.add_argument('--overwrite-approved',action='store_true')
    args=parser.parse_args(argv)
    request=json_file(args.request)
    if not isinstance(request,dict): parser.error('정확한 요청 객체를 선택하세요.')
    fields={
        'catalog':({'document_ids'},'portable_recovery_catalog'),
        'read':({'archive_id','facet','selection'},'portable_recovery_read'),
        'inspect':({'selections','recovery_archives','draft_policy'},'portable_inspect'),
        'create':({'inspection','destination','command_id','session_id'},'portable_create'),
        'preview':({'archive_id','target_identity','buffer'},'portable_recovery_preview'),
        'resume':({'preview','live_buffer','command_id'},'portable_recovery_resume')}
    expected,method=fields[args.action]
    if set(request)!=expected: parser.error('요청 필드가 다릅니다: '+', '.join(sorted(expected)))
    if args.action in {'resume','create'}:
        if not args.approved: parser.error('현재 대상과 자료 목록을 확인한 --approved가 필요합니다.')
        request['approved']=True
    if args.action=='resume':
        if not args.overwrite_approved: parser.error('현재 편집 buffer 검토 후 --overwrite-approved가 필요합니다.')
        request['overwrite_approved']=True
    if len(json.dumps(request,ensure_ascii=False,allow_nan=False).encode('utf-8'))>(8*1024*1024 if args.action=='create' else 128*1024):
        parser.error('기존 요청 한도를 넘습니다. 원문 대신 정확한 현재 buffer token과 명시 파일 기반 검토를 사용하세요.')
    result=getattr(Client(args.service),method)(**request)
    text=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if args.output:
        with args.output.open('x',encoding='utf-8') as stream: stream.write(text)
    else:
        # Machine-readable output has the same encoding as request/output files,
        # including when Windows redirects stdout through its legacy code page.
        if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
        print(text,end='')
    return 0


if __name__=='__main__': raise SystemExit(main())
