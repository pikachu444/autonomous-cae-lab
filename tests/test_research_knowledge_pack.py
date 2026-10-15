"""Real offline BM25/source/archive checks; no model or engineering execution."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import pytest

from examples import research_knowledge_public as pack


def no_network(*a,**kw):raise AssertionError('Official pack import/search/read must be offline')


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket,'connect',no_network)
    monkeypatch.setattr(socket,'create_connection',no_network)
    from caelab.assist.experts import ExpertRuntime
    monkeypatch.setattr(ExpertRuntime,'ask',no_network)


def test_official_pack_originals_licenses_versions_and_url_only():
    manifest=pack.load_pack()
    assert len(manifest['documents'])==5
    included=[d for d in manifest['documents'] if d['availability']=='BUNDLED']
    assert len(included)==3 and all(d['license']['redistribution_permitted'] for d in included)
    assert all(d['license']['local_notices'] for d in included)
    assert {d['license']['name'] for d in included}=={'CC-BY-3.0','CC-BY-4.0'}
    pv=next(d for d in included if d['id']=='paraview-basic')
    assert pv['document_version']=='5.13.3' and pv['installed_version_observed']=='6.2.0'
    assert pv['applicability']=='REFERENCE_ONLY_VERSION_MISMATCH'
    assert {d['id'] for d in manifest['documents'] if d['availability']=='URL_ONLY'}=={'calculix-manual','impact-inievo'}


def test_changed_original_or_missing_notice_blocks_before_any_import(tmp_path):
    copied=tmp_path/'pack';shutil.copytree(pack.PACK.parent,copied)
    target=copied/'sources/freecad-fem.md';old=target.read_bytes();target.write_bytes(old+b'\nchanged')
    with pytest.raises(ValueError,match='hash differs'):pack.import_pack(tmp_path/'never-created',copied/'manifest.json')
    assert not (tmp_path/'never-created').exists()
    target.write_bytes(old);(copied/'licenses/CC-BY-3.0.txt').unlink()
    with pytest.raises(ValueError,match='Missing'):pack.load_pack(copied/'manifest.json')


def test_cli_outputs_original_unicode_on_windows_legacy_redirected_encoding():
    env={**os.environ,'PYTHONIOENCODING':'cp949'}
    result=subprocess.run([sys.executable,'-m','examples.research_knowledge_public','list'],
                          capture_output=True,timeout=15,env=env)
    assert result.returncode==0,result.stderr.decode('utf-8',errors='replace')
    original=json.loads(result.stdout)
    assert any('—' in row['title'] for row in original['documents'])


def test_same_title_new_revision_does_not_replace_an_exact_source_search(tmp_path,offline):
    from caelab.assist.knowledge import KnowledgeStore
    original=(pack.PACK.parent/'sources/freecad-gmsh-mesh.md').read_bytes()
    file=tmp_path/'source.md';file.write_bytes(original)
    store=KnowledgeStore(tmp_path/'archive',source_roots=[tmp_path])
    first=store.ingest(file,'mesh-gmsh',{'title':'Same title','document_version':'official fixed snapshot'})
    file.write_bytes(original+b'\n# Local test annotation\nNOT an official newer release: LOCAL_TEST_VERSION_TWO.\n')
    second=store.ingest(file,'mesh-gmsh',{'title':'Same title','document_version':'local test annotation'},
                        document_id=first['document_id'])
    assert second['revision']==2 and first['sha256']!=second['sha256']
    ref={'document_id':first['document_id'],'revision':first['revision']}
    found=store.search('Nonpositive Jacobians',source_refs=[ref])
    assert found['hits'] and all(hit['revision']==1 for hit in found['hits'])
    old=store.source(**ref)
    assert old['sha256']==hashlib.sha256(original).hexdigest()
    assert 'LOCAL_TEST_VERSION_TWO' not in ''.join(s['text'] for s in old['segments'])
    assert store.revision_details(**ref)['metadata']['document_version']=='official fixed snapshot'


def test_real_ingest_bm25_exact_read_and_new_process_cold(tmp_path,offline):
    workspace=tmp_path/'공식 자료 연구'
    receipt=pack.import_pack(workspace)
    assert receipt['state']=='IMPORTED' and len(receipt['sources'])==3
    before=(workspace/pack.RECEIPT).read_bytes()
    from caelab.workbench import Workbench
    wb=Workbench(workspace,configuration={'workers':1})
    try:
        count=len(wb.manager.list())
        assert count==3 and {j['operation'] for j in wb.manager.list()}=={'knowledge.ingest'}
        knowledge=wb.assistance().knowledge
        for row in receipt['sources']:
            archive=knowledge.root/row['source']['document_id']/str(row['source']['revision'])
            assert hashlib.sha256(next(archive.glob('original.*')).read_bytes()).hexdigest()==row['sha256']
    finally:assert wb.shutdown()['joined']
    chosen=[]
    for row in receipt['sources']:
        entry=row['entry'];result=pack.search_pack(workspace,entry['example_query'],source=entry['id'])
        assert result['method']=='Haystack BM25L' and result['hits']
        hit=result['hits'][0]
        assert hit['document_id']==row['source']['document_id'] and hit['revision']==row['source']['revision']
        assert hit['title']==entry['library_title']
        read=pack.read_source(workspace,entry['id'],hit['locator']['segment_id'])
        assert read['read']['segments'][0]['text']==hit['text']
        assert read['read']['segments'][0]['locator']==hit['locator']
        assert read['official_document']['applicability']==entry['applicability']
        chosen.append({'entry':entry['id'],'segment_id':hit['locator']['segment_id'],
                       'query':entry['example_query'],'read':read})
    with pytest.raises(ValueError,match='receipt exists'):pack.import_pack(workspace)
    assert (workspace/pack.RECEIPT).read_bytes()==before
    with pytest.raises(ValueError,match='no imported body'):pack.read_source(workspace,'calculix-manual','0')
    with pytest.raises(ValueError,match='No such exact'):pack.read_source(workspace,'freecad-fem','missing')
    expected=tmp_path/'exact-reads.json';expected.write_text(json.dumps(chosen),encoding='utf-8')
    program="""
import json,socket,sys
from examples import research_knowledge_public as pack
from caelab.workbench import Workbench
from caelab.assist.experts import ExpertRuntime
def forbidden(*a,**k):raise AssertionError('No network/model/download/solver on cold read')
socket.socket.connect=forbidden
socket.create_connection=forbidden
ExpertRuntime.ask=forbidden
pack.import_pack=forbidden
old=pack.PACK
pack.PACK=None  # source pack is not consulted on archive reopen
for row in json.load(open(sys.argv[2],encoding='utf-8')):
    assert pack.read_source(sys.argv[1],row['entry'],row['segment_id'])==row['read']
    found=pack.search_pack(sys.argv[1],row['query'],source=row['entry'])
    assert found['method']=='Haystack BM25L' and found['hits']
wb=Workbench(sys.argv[1],configuration={'workers':1})
try:assert len(wb.manager.list())==3
finally:assert wb.shutdown()['joined']
print('Saved sources/exact locators unchanged; cold BM25 rebuilt; jobs=3; no import/model/network/solve')
"""
    cold=subprocess.run([sys.executable,'-c',program,str(workspace),str(expected)],
                        capture_output=True,text=True,timeout=60)
    assert cold.returncode==0,cold.stdout+cold.stderr
