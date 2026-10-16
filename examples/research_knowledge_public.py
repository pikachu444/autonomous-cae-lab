"""Explicit, offline official-document import using existing KnowledgeStore APIs.

Run from the repository root with ``python -m examples.research_knowledge_public``.
This example never downloads, configures a model or starts an engineering solver.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from caelab.research_knowledge_pack import PACK, load_pack
RECEIPT='research-knowledge-import.json'


def _json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write(path,data):
    path=Path(path);temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(path)


def import_pack(workspace,manifest=PACK):
    """Upload and ingest only explicitly bundled text into the existing owner."""
    pack=load_pack(manifest);workspace=Path(workspace);receipt_path=workspace/RECEIPT
    if receipt_path.exists():raise ValueError('Import receipt exists; reopen/search it instead of importing again')
    from caelab.workbench import Workbench
    receipt={'pack_title':pack['title'],'manifest_sha256':hashlib.sha256(Path(manifest).read_bytes()).hexdigest(),
             'state':'IMPORTING','sources':[],
             'url_only':[deepcopy(v) for v in pack['documents'] if v['availability']=='URL_ONLY']}
    wb=Workbench(workspace,configuration={'workers':1})
    try:
        receipt['workspace_id']=wb.workspace_id;_write(receipt_path,receipt)
        for entry in pack['documents']:
            if entry['availability']!='BUNDLED':continue
            source=Path(manifest).resolve().parent/entry['file'];raw=source.read_bytes()
            expected=next(a for a in pack['assets'] if a['path']==entry['file'])
            if hashlib.sha256(raw).hexdigest()!=expected['sha256']:raise ValueError('Source changed after review')
            upload=wb.upload(source.name,raw)
            job=wb.submit('knowledge.ingest',{'data_id':upload['id'],'collection':entry['collection'],
                'metadata':{'title':entry.get('library_title',entry['title']),'official_document':deepcopy(entry)}},
                request_id='official-pack-'+entry['id']+'-'+receipt['manifest_sha256'][:16])
            deadline=time.monotonic()+60
            while True:
                state=wb.manager.status(job['id'])['state']
                if state in {'SUCCEEDED','FAILED','CANCELLED','INTERRUPTED','PARTIAL_FAILURE'}:break
                if time.monotonic()>deadline:raise TimeoutError('Import job is still pending; inspect existing jobs before a new import')
                time.sleep(.01)
            if state!='SUCCEEDED':raise RuntimeError('Source import failed; retained job '+job['id'])
            result=wb.manager.result(job['id'])
            if result['sha256']!=expected['sha256'] or result['failed_segments'] or not result['segments_read']:
                raise ValueError('Original hash or text extraction differs')
            receipt['sources'].append({'entry':deepcopy(entry),'source':{
                'document_id':result['document_id'],'revision':result['revision']},
                'sha256':result['sha256'],'segments_read':result['segments_read'],'import_job':job['id']})
            _write(receipt_path,receipt)
        receipt['state']='IMPORTED';_write(receipt_path,receipt)
        return receipt
    except Exception as error:
        receipt.update(state='INCOMPLETE',failure_type=type(error).__name__)
        _write(receipt_path,receipt);raise
    finally:
        if not wb.shutdown()['joined']:raise RuntimeError('Owned import worker cleanup unconfirmed')


def _saved(workspace):
    return _json(Path(workspace)/RECEIPT)


def search_pack(workspace,query,*,source=None,top_k=5):
    """Actual BM25L over exact imported revisions; no remote/public search."""
    receipt=_saved(workspace)
    selected=[r for r in receipt['sources'] if source is None or r['entry']['id']==source]
    if not selected:raise ValueError('No imported text for this source; URL-only is not a readable archive')
    from caelab.workbench import Workbench
    wb=Workbench(workspace,configuration={'workers':1})
    try:
        result=wb.assistance_call('knowledge.search',{'query':query,'source_refs':[r['source'] for r in selected],
            'collections':list({r['entry']['collection'] for r in selected}),'top_k':top_k})
        entries={r['source']['document_id']:r['entry'] for r in selected}
        for hit in result['hits']:hit['official_document']=deepcopy(entries[hit['document_id']])
        return result
    finally:
        if not wb.shutdown()['joined']:raise RuntimeError('Owned reader cleanup unconfirmed')


def read_source(workspace,source,segment_id):
    """Read precisely the chosen saved revision and segment, independently of search."""
    receipt=_saved(workspace)
    row=next((r for r in receipt['sources'] if r['entry']['id']==source),None)
    if row is None:raise ValueError('This document has no imported body; use its official URL/manual import instructions')
    from caelab.workbench import Workbench
    wb=Workbench(workspace,configuration={'workers':1})
    try:
        result=wb.assistance_call('knowledge.source',{**row['source'],'locator':{'segment_id':str(segment_id)}})
        if result['sha256']!=row['sha256']:raise ValueError('Saved original differs from import receipt')
        if not result['segments']:raise ValueError('No such exact source segment; do not substitute a different locator')
        return {'official_document':deepcopy(row['entry']),'read':result}
    finally:
        if not wb.shutdown()['joined']:raise RuntimeError('Owned reader cleanup unconfirmed')


def main(argv=None):
    import sys
    # Redirected Windows consoles may otherwise reject original document glyphs.
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description='공식 자료 목록·명시 반입·로컬 검색·보존 원문 읽기 (모델/계산/다운로드 없음)')
    commands=parser.add_subparsers(dest='command',required=True)
    listing=commands.add_parser('list');listing.add_argument('--manifest',type=Path,default=PACK)
    importing=commands.add_parser('import');importing.add_argument('--workspace',type=Path,required=True)
    importing.add_argument('--manifest',type=Path,default=PACK)
    search=commands.add_parser('search');search.add_argument('--workspace',type=Path,required=True)
    search.add_argument('--query',required=True);search.add_argument('--source')
    reading=commands.add_parser('read');reading.add_argument('--workspace',type=Path,required=True)
    reading.add_argument('--source',required=True);reading.add_argument('--segment-id',required=True)
    args=parser.parse_args(argv)
    if args.command=='list':value=load_pack(args.manifest)
    elif args.command=='import':value=import_pack(args.workspace,args.manifest)
    elif args.command=='search':
        value=search_pack(args.workspace,args.query,source=args.source)
        for hit in value['hits']:
            hit['excerpt']=hit.pop('text')[:400]
    else:value=read_source(args.workspace,args.source,args.segment_id)
    print(json.dumps(value,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
