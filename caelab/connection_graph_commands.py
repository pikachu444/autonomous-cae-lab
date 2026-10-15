"""Headless commands on the SAME loopback service used by the Qt connection window.

No service/process/daemon is started. Metadata commands never include source-file
bytes. Run --help for explicit catalog -> preview -> reviewed apply/view workflow.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from .portable_project_io import json_file
from .workbench_client import Client


def main(argv=None):
    parser = argparse.ArgumentParser(description='선택 연결: 실제 owner 참조와 프로젝트 배치 명령')
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('graph','catalog','impact','preview','apply','view','view-save'):
        command = sub.add_parser(action)
        command.add_argument('--service', required=True, help='실행 중인 같은 loopback 제품 서비스')
        command.add_argument('--output', type=Path, help='새 로컬 결과 파일. 기존 파일은 덮어쓰지 않음')
        if action in ('catalog','impact'): command.add_argument('--target',required=True)
        if action == 'impact': command.add_argument('--port',required=True)
        if action == 'graph': command.add_argument('--document',action='append')
        if action in ('preview','apply','view-save'): command.add_argument('--request',type=Path,required=True)
        if action in ('apply','view-save'):
            command.add_argument('--confirmed',action='store_true')
    args = parser.parse_args(argv)
    client = Client(args.service)
    if args.action == 'graph': result = client.connection_graph(args.document)
    elif args.action == 'catalog': result = client.connection_catalog(args.target)
    elif args.action == 'impact': result = client.connection_impact(args.target,args.port)
    elif args.action == 'view': result = client.connection_view_read()
    else:
        request = json_file(args.request)
        if not isinstance(request,dict): parser.error('요청은 객체여야 합니다.')
        if args.action == 'preview':
            if set(request) != {'target','port','action','source'}: parser.error('target/port/action/source만 지정하세요.')
            result = client.connection_preview(**request)
        elif args.action == 'apply':
            if not args.confirmed: parser.error('확인한 원본/대상/영향 반영에는 --confirmed가 필요합니다.')
            if set(request) != {'proposal','command_id'}: parser.error('확인한 proposal과 같은 재시도용 command_id만 지정하세요.')
            result = client.connection_apply(**request,confirmed=True)
        else:
            if not args.confirmed: parser.error('배치 저장에는 --confirmed가 필요합니다.')
            if set(request) != {'state','scope','expected_revision','expected_sha256','command_id'}:
                parser.error('view 응답의 상태/정확 개정/식별값과 command_id를 사용하세요.')
            result = client.connection_view_save(**request)
    text = json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if args.output:
        with args.output.open('x',encoding='utf-8') as stream: stream.write(text)
    else: print(text,end='')
    return 0


if __name__ == '__main__': raise SystemExit(main())
