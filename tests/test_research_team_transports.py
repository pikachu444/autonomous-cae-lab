"""Thin CLI/real stdio MCP → HTTP → existing research owner commands.

The existing C public fixture has controlled role/report text and an actual
numerical.analyze result. Set CAELAB_RESEARCH_TEAM_TRANSPORT_SOURCE to reuse a
preserved public fixture without regenerating it. Standalone CI can create the
same fixture with its existing runnable; transfers themselves never calculate.
"""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sys
import threading

import pytest

from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab.evaluation import file_hash
from caelab.research_team_followup import claim_rows
from caelab.storage import load_json, canonical_hash
from caelab.workbench_cli import main
from caelab.workbench_client import Client, WorkbenchHTTPError
from examples.research_team_followup_public import CONFIG, run_public


@pytest.fixture
def service(tmp_path, monkeypatch):
    output=tmp_path/'public transport'
    supplied=os.environ.get('CAELAB_RESEARCH_TEAM_TRANSPORT_SOURCE')
    original=None
    if supplied:
        source=Path(supplied).resolve()
        original={p.relative_to(source).as_posix():file_hash(p) for p in source.rglob('*') if p.is_file()}
        shutil.copytree(source,output)
        receipt=load_json(output/'receipt.json')
    else:
        receipt=run_public(output)
    server=LabHTTPServer(LabService(output),0,workbench_config=CONFIG)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True)
    thread.start()
    def forbidden(*a,**k):raise AssertionError('A transfer tried to ask a model or submit a calculation')
    bench=server.workbench
    monkeypatch.setattr(bench,'submit',forbidden)
    monkeypatch.setattr(bench.manager,'submit',forbidden)
    monkeypatch.setattr(bench.assistance().experts,'ask',forbidden)
    try:
        yield server,Client('http://127.0.0.1:'+str(server.server_port)),receipt
    finally:
        server.shutdown();server.server_close();thread.join(5)
        assert not thread.is_alive()
        closed=bench.shutdown();assert closed['joined'] and not closed['pending']
        if supplied:
            assert original=={p.relative_to(source).as_posix():file_hash(p) for p in source.rglob('*') if p.is_file()}


def test_cli_and_stdio_mcp_use_same_transfer_owner_retry_edit_and_gates(service,capfd,monkeypatch,tmp_path):
    mcp=pytest.importorskip('mcp')
    from mcp.client.stdio import stdio_client
    server,client,receipt=service;bench=server.workbench
    source=client.document_read(receipt['discussion_id'])
    source_draft=canonical_hash(source['draft']);jobs=len(bench.manager.list())
    calls=[];transfer=bench.research_team_transfer
    def captured(**request):
        calls.append(deepcopy(request));return transfer(**request)
    monkeypatch.setattr(bench,'research_team_transfer',captured)
    def arguments(kind,selection,command):
        return {'document_id':source['id'],'kind':kind,'selection':deepcopy(selection),
                'session_id':source['session_id'],'expected_generation':source['generation'],'command_id':command}
    def cli(request,*,file=False):
        selection=json.dumps(request['selection'],ensure_ascii=False)
        if file:
            path=tmp_path/(request['command_id']+'.json');path.write_text(selection,encoding='utf8');selection=str(path)
        assert main(['documents','research-transfer',request['document_id'],'--url',client.url,
            '--kind',request['kind'],'--selection',selection,'--session',request['session_id'],
            '--generation',str(request['expected_generation']),'--command-id',request['command_id']])==0
        return json.loads(capfd.readouterr().out)
    selected=arguments('study',{'claim_ids':[claim_rows(source)[0]['id']]},'CtransportStudy')
    first=cli(selected)
    assert calls[-1]==selected and first['executed'] is False
    study=first['document'];draft=deepcopy(study['draft']);draft['question']='사용자가 이어 쓴 판단 질문'
    client.document_command(study['id'],'study.update',{'draft':draft},session_id=study['session_id'],
        expected_generation=study['generation'],command_id='CtransportStudyEdit')
    assert client.research_team_transfer(**selected)['document']['id']==study['id']
    async def exercise():
        params=mcp.StdioServerParameters(command=sys.executable,args=['-m','openscience.workbench_mcp'],
                                        env={**os.environ,'CAELAB_SERVICE_URL':client.url})
        async with stdio_client(params,errlog=sys.stderr) as (reader,writer):
            async with mcp.ClientSession(reader,writer) as session:
                await session.initialize()
                tools={tool.name:tool for tool in (await session.list_tools()).tools}
                assert {'expert_research_transfer','document_command','expert_plan_open'}<=set(tools)
                schema=tools['expert_research_transfer'].inputSchema
                assert set(schema['properties'])==set(selected)
                assert set(schema['required'])==set(selected)
                assert schema['properties']['kind']['enum']==['study','result_review','report']
                async def invoke(request):
                    response=await session.call_tool('expert_research_transfer',request)
                    assert not response.isError,response
                    return response.structuredContent or json.loads(response.content[0].text)
                again=await invoke(selected)
                assert calls[-1]==selected
                assert again['document']['id']==study['id'] and again['document']['draft']==draft
                report_request=arguments('report',{'action_id':'DpublicReport'},'CtransportReport')
                report=(await invoke(report_request))['document'];assert calls[-1]==report_request
                report_draft=deepcopy(report['draft']);report_draft['title']='사용자가 고친 보고서 제목'
                client.document_command(report['id'],'report.update',{'draft':report_draft},
                    session_id=report['session_id'],expected_generation=report['generation'],command_id='CtransportReportEdit')
                repeated=cli(report_request,file=True)
                assert repeated['document']['id']==report['id'] and repeated['document']['draft']==report_draft
                assert calls[-1]==report_request
                review_request=arguments('result_review',{'turn_id':receipt['source_turn_id'],'proposal_index':0,
                    'plan_document_id':receipt['plan_id'],'job_id':receipt['result_reference']['job_id'],
                    'selector':{'metadata_only':True,'channels':[]},'actor_ids':['public-role']},'CtransportReview')
                preview=cli(review_request,file=True);assert calls[-1]==review_request
                assert preview['executed'] is False and preview['new_ask'] is False
                assert await invoke(review_request)==preview and calls[-1]==review_request
                # Owner gates apply equally to the thin tool and CLI. No caller
                # receipt/path/payload becomes read or transmission authority.
                wrong={**selected,'expected_generation':source['generation']+1,'command_id':'CstaleTransport'}
                assert (await session.call_tool('expert_research_transfer',wrong)).isError
                with pytest.raises(WorkbenchHTTPError):cli(wrong)
                wrong={**selected,'session_id':'SotherOwner','command_id':'CwrongTransportSession'}
                assert (await session.call_tool('expert_research_transfer',wrong)).isError
                for name,value in [('receipt',{'verified':True}),('path','C:/not-an-input'),('raw_project',{})]:
                    wrong={**selected,'selection':{**selected['selection'],name:value},'command_id':'Cextra'+name}
                    assert (await session.call_tool('expert_research_transfer',wrong)).isError
                    with pytest.raises(WorkbenchHTTPError):cli(wrong,file=True)
                missing={k:v for k,v in selected.items() if k!='command_id'}
                assert (await session.call_tool('expert_research_transfer',missing)).isError
                runtime=bench.assistance().experts
                monkeypatch.setattr(runtime,'_transmission_check',lambda *a,**k: (_ for _ in ()).throw(PermissionError('Controlled current denial')))
                assert (await session.call_tool('expert_research_transfer',report_request)).isError
                with pytest.raises(WorkbenchHTTPError):cli(report_request,file=True)
                assert client.document_read(report['id'])['draft']==report_draft
    asyncio.run(exercise())
    assert client.document_read(source['id'])['draft']==source['draft']
    assert canonical_hash(client.document_read(source['id'])['draft'])==source_draft
    assert client.document_read(study['id'])['draft']==draft
    assert len(bench.manager.list())==jobs


def test_cli_research_transfer_requires_explicit_identity_and_known_kind():
    valid=['documents','research-transfer','Xsource','--kind','study','--selection','{}',
           '--session','Ssession','--generation','0']
    with pytest.raises(SystemExit) as error:main(valid)
    assert error.value.code==2
    with pytest.raises(SystemExit) as error:main([*valid,'--command-id','Cexplicit','--kind','calculate'])
    assert error.value.code==2
