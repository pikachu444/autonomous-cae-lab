"""Actual HTTP/owner routing; the native command producer is controlled."""
from pathlib import Path
import json,shutil,threading
from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from caelab.workbench_client import Client
from caelab.storage import save_json
from caelab.native_cad import sha


def test_explicit_pretension_freeze_opens_same_simulation_without_running(tmp_path):
 server=LabHTTPServer(LabService(tmp_path/'workspace'),0)
 thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
 client=Client('http://127.0.0.1:'+str(server.server_port));wb=server.workbench
 try:
  fixture=Path(__file__).parent/'fixtures/pretension';model=json.loads((fixture/'mesh.json').read_text(encoding='utf-8'))
  folder=wb.desktop.root/'Pbolt'/'Ffixture';folder.mkdir(parents=True)
  for name in ('mesh.json','contact.inp'):shutil.copyfile(fixture/name,folder/name)
  # No CAD runtime in this transport test; do not claim this placeholder is editable native geometry.
  (folder/'editable.FCStd').write_bytes(b'CONTROLLED_NATIVE_EXPORT_FOR_HTTP_ROUTING_ONLY')
  save_json(folder/'snapshot.json',{'kind':'freecad-contact-frozen','schema_version':'1','id':'Ffixture',
    'input_file':'contact.inp','bodies':[{'body_id':b} for b in sorted({r['body_id'] for r in model['nodes']})],
    'files':[{'relative':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in folder.iterdir()]})
  descriptor={'id':'Pbolt','kind':'pre','generation':3,'view_generation':0,'title':'체결 입력',
              'capabilities':['pre.pretension.freeze']}
  auth=wb.native_commands.register(host_id='Hpre',session_id='Snative',application='freecad',version='CONTROLLED',
    execution_mode='headless',documents=[descriptor],registration_nonce='p'*32)
  wb.document_command('Pbolt','pre.pretension.freeze',{'analysis_id':'Analysis','solver_id':'Solver'},
    session_id='Snative',expected_generation=3,command_id='Cpretension')
  wb.native_commands.next('Hpre',session_id='Snative',host_token=auth['host_token'])
  wb.native_commands.event('Hpre',session_id='Snative',host_token=auth['host_token'],event='finished',command_id='Cpretension',
    documents=[descriptor],outcome={'state':'SUCCEEDED','result':{'status':'COMPLETED','result':{
    'snapshot_relative':(folder/'snapshot.json').relative_to(wb.desktop.root).as_posix(),'label':'체결 조임'},
    'generation':3,'view_generation':0}})
  first=client.native_open_simulation('Cpretension');doc=first['document']
  assert doc['draft']['backend']=='structure.calculix.pretension' and first['executed'] is False
  assert set(doc['draft']['settings'])=={'data_id'}
  draft={'backend':'structure.calculix.pretension','settings':{'data_id':'DuserDraft'}}
  wb.document_command(doc['id'],'simulation.update',{'draft':draft},session_id=wb.session_id,expected_generation=doc['generation'])
  again=client.native_open_simulation('Cpretension')
  assert again['document']['id']==doc['id'] and again['document']['draft']==draft
  assert len(wb.manager.list())==0 and len(list((wb.root/'inputs').iterdir()))==1
 finally:
  server.shutdown();server.server_close();thread.join(timeout=2)
  assert not thread.is_alive()
