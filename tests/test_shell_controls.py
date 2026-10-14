"""Native Save routing uses explicit connection/owner doubles; no Qt assertion."""
from types import SimpleNamespace as NS
from copy import deepcopy
import pytest
from apps.desktop_pre.shell_panel import DraftBuffer
from apps.desktop_pre.shell_controls import flush_before_save,has_unsaved_editor,editor_token,ShellActions
if __package__:
    from .test_shell_support import model
else:
    from test_shell_support import model

@pytest.mark.parametrize('offline',[False,True])
@pytest.mark.parametrize('save_fails',[False,True])
def test_native_save_flushes_literal_draft_then_existing_document_save(offline,save_fails):
    b=DraftBuffer();b.read('Analysis',model()['draft']);b.fields['thickness_mm']='1e'
    panel=NS(buffer=b,busy=False,pending_changes=b.pending_changes,update_enabled=lambda:None,show_errors=lambda:None)
    dock=NS(widget=lambda:NS(shell_controller=panel));sent=[];answers=[];writes=[]
    owner=NS(doc=NS(Name='Document'),document_id='Ptest',session_id='Stest',generation=7,refresh=lambda:None)
    def dispatch(command):
        writes.append(command);return {'command_id':command['command_id'],'status':'COMPLETED','result':{'records':[]}}
    owner.dispatch=dispatch
    broker=NS(stop=NS(is_set=lambda:offline),registered=NS(is_set=lambda:not offline))
    conn=NS(owners={'Document':(owner,None,broker)},panels={'Document':{'shell':dock}})
    def submit(op,args,target=None,on_done=None,**kwargs):
        sent.append((op,deepcopy(args),kwargs))
        if op=='pre.shell.save_draft':on_done({'records':[]})
        else:on_done({'status':'FAILED','error':{'message':'TEST_DOUBLE save failure'}} if save_fails else {'saved':True})
        return {'command_id':'Ctest','queued':True}
    conn.submit_native=submit
    token=editor_token(conn,owner)
    result=flush_before_save(conn,owner,{},None,answers.append)
    assert b.fields['thickness_mm']=='1e' and not panel.busy and answers
    assert sent[-1][0]=='document.save' and sent[-1][2]['_capture_shell'] is False
    raw=writes[0]['arguments'] if offline else sent[0][1]
    assert raw=={'analysis_id':'Analysis','fields':b.fields}
    assert has_unsaved_editor(conn,owner)==save_fails
    assert editor_token(conn,owner)==token

def test_run_prepared_reuses_exact_reviewed_command_without_freeze():
    data=model();from caelab.shell_model import digest
    prepared={'command_id':'Cprepared','applied_sha256':digest(data['applied']),'analysis_id':'ShellAnalysis'}
    owner=NS(document_id='Ptest');editor=NS(owner=owner,effective=lambda aid:(data,{},[]))
    calls=[]
    panel=NS(prepared=prepared,busy=False,pending_changes=lambda:False,update_enabled=lambda:None,set_status=lambda s:None,safe=lambda fn:fn())
    def submit(identifier):
        calls.append(identifier);return {'origin':{'document_id':'Ptest'},'job':{'id':'Jtest'}}
    conn=NS(client=NS(native_submit=submit),submit_native=lambda op,args,**kwargs:calls.append((op,args)),
        request=lambda key,fn,done:done(fn()),open_runner=lambda jid:calls.append(('runner',jid)))
    action=ShellActions(conn,panel,editor);action.run_prepared();action.run_prepared()
    assert calls.count('Cprepared')==1
    assert not any(isinstance(row,tuple) and 'freeze' in row[0] for row in calls)
    assert prepared['job_id']=='Jtest'
