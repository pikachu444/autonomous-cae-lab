"""Controlled Windows stdin transport; no real profile, CLI or provider invocation."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from hashlib import sha256
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
import time

import pytest


CLI_STUB=r'''
using System; using System.Collections.Generic; using System.Diagnostics;
using System.IO; using System.Security.Cryptography; using System.Text;
using System.Threading; using System.Web.Script.Serialization;
class ControlledStdinCli {
 static void Main(string[] args) {
  if(args.Length==1 && args[0]=="--owned-descendant") { Thread.Sleep(60000); return; }
  string mode=Environment.GetEnvironmentVariable("CAELAB_STDIN_TEST_MODE");
  string output=Environment.GetEnvironmentVariable("CAELAB_STDIN_TEST_OUTPUT");
  var row=new Dictionary<string,object>{{"controlled_cli",true},{"argv",args},{"pid",Process.GetCurrentProcess().Id}};
  var json=new JavaScriptSerializer();
  if(mode!="success") {
   var child=Process.Start(new ProcessStartInfo(Process.GetCurrentProcess().MainModule.FileName,"--owned-descendant") {UseShellExecute=false,CreateNoWindow=true});
   row["child_pid"]=child.Id; File.WriteAllText(output,json.Serialize(row),new UTF8Encoding(false));
   Thread.Sleep(60000); return; // Deliberately never read stdin: cancellation must remain responsive.
  }
  Console.SetIn(new StreamReader(Console.OpenStandardInput(),new UTF8Encoding(false,true),false));
  string text=Console.In.ReadToEnd(); byte[] bytes=new UTF8Encoding(false,true).GetBytes(text);
  row["eof"]=true; row["utf8_bytes"]=bytes.Length;
  using(var hash=SHA256.Create()) row["sha256"]=BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();
  File.WriteAllText(output,json.Serialize(row),new UTF8Encoding(false));
  Console.OutputEncoding=new UTF8Encoding(false);
  Console.WriteLine("{\"type\":\"text\",\"part\":{\"text\":\"controlled Unicode 전달 완료\"}}");
  Console.WriteLine("{\"type\":\"done\",\"status\":\"completed\"}");
 }
}
'''


@pytest.mark.skipif(os.name!='nt',reason='Actual Windows ProcessStartInfo/pipe cleanup check')
def test_long_unicode_stdin_eof_cancel_deadline_and_owned_children(tmp_path):
    from caelab.expert_connection import powershell_command
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.is_file():pytest.skip('Existing Windows .NET compiler unavailable; no installation performed')
    profile=tmp_path/'controlled-profile';config=profile/'config';config.mkdir(parents=True)
    runtime=tmp_path/'controlled-runtime';binary=runtime/'node_modules/@synsci/openscience-windows-x64/bin/openscience.exe'
    binary.parent.mkdir(parents=True)
    source=tmp_path/'controlled_stdin_cli.cs';source.write_text(CLI_STUB,encoding='utf-8')
    subprocess.run([str(compiler),'/nologo','/codepage:65001','/target:exe','/reference:System.Web.Extensions.dll',
        '/out:'+str(binary),str(source)],capture_output=True,text=True,check=True,timeout=20)
    marker={'kind':'autonomous-cae-lab.chatgpt-auth-profile','provider':'openai-codex',
        'profile_root':str(profile),'runtime_version':'2.0.146','runtime_pin':{
            'NativeBinaries':[{'Path':str(binary),'Sha256':sha256(binary.read_bytes()).hexdigest()}]}}
    (profile/'caelab-profile-owner.json').write_text(json.dumps(marker),encoding='utf-8')
    # Deliberately synthetic deny-all fixture: no existing auth/config is opened.
    (config/'openscience.json').write_text(json.dumps({'permission':{'*':'deny'},'enabled_providers':['openai-codex']}),encoding='utf-8')
    baseline={str(p):sha256(p.read_bytes()).hexdigest() for p in profile.rglob('*') if p.is_file()}
    prompt='A'*35000+('한글 α🙂 "quote" \\\n'*1500)
    assert len(prompt.encode())<100000 and len(prompt)>32767
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT];kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    observed=[]
    for mode in ('success','cancel','deadline'):
        output=tmp_path/(mode+'-controlled.json');handles=[];cancel_gate=threading.Event()
        class Status(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                payload=json.dumps({'cancel_requested':mode=='cancel' and cancel_gate.is_set()}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        server=ThreadingHTTPServer(('127.0.0.1',0),Status)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        url='http://127.0.0.1:'+str(server.server_port)
        request={'model':'openai-codex/gpt-6-astra','bridge_url':url,'mcp_url':url+'/mcp',
            'bridge_token':'controlled_test_token_12345678','deadline':1 if mode=='deadline' else 30,
            'max_steps':2,'profile_path':str(profile),'runtime_prefix':str(runtime),
            'tool_names':['knowledge_source'],'prompt':prompt}
        process=None
        try:
            environment={**os.environ,'CAELAB_STDIN_TEST_MODE':mode,'CAELAB_STDIN_TEST_OUTPUT':str(output)}
            environment.pop('PSMODULEPATH',None)
            process=subprocess.Popen(powershell_command(Path('caelab/assist/openscience_host.ps1')),
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                text=True,encoding='utf-8',errors='strict',env=environment)
            if mode=='success':
                stdout,stderr=process.communicate(json.dumps(request,ensure_ascii=False),timeout=20)
            else:
                # Deliver the wrapper request, then keep handles to its exact children before cleanup.
                process.stdin.write(json.dumps(request,ensure_ascii=False));process.stdin.close();process.stdin=None
                end=time.monotonic()+12
                while not output.exists() and process.poll() is None and time.monotonic()<end:time.sleep(.02)
                assert output.exists(),'Controlled CLI did not start'
                started=json.loads(output.read_text(encoding='utf-8'))
                for pid in (started['pid'],started['child_pid']):
                    handle=kernel.OpenProcess(0x100001,False,pid)
                    assert handle,'The exact controlled child must still be available before cancellation'
                    handles.append(handle)
                cancel_gate.set()
                stdout,stderr=process.communicate(timeout=20)
            (tmp_path/(mode+'-wrapper-stdout.json')).write_text(stdout,encoding='utf-8')
            (tmp_path/(mode+'-wrapper-stderr.log')).write_text(stderr,encoding='utf-8')
            assert process.returncode==0,stderr
            result=json.loads(stdout)
            receipt=json.loads(output.read_text(encoding='utf-8'))
            assert receipt['controlled_cli'] is True
            assert receipt['argv']==['run','--format','json','--workspace','isolated','--delegation','off',
                '--deny-prompts','--model',request['model'],'--variant','high','--deadline',str(request['deadline']),'--']
            assert all(len(arg)<100 for arg in receipt['argv']) and result['cleanup_confirmed'] is True
            if mode=='success':
                assert result['status']=='completed' and result['text']=='controlled Unicode 전달 완료'
                assert receipt['eof'] is True and receipt['utf8_bytes']==len(prompt.encode())
                assert receipt['sha256']==sha256(prompt.encode()).hexdigest()
            else:
                assert result['status']=='stopped'
                assert ('cancellation' if mode=='cancel' else 'deadline') in result['reason'].lower()
                assert all(kernel.WaitForSingleObject(handle,2000)==0 for handle in handles)
            assert not list((profile/'temp').glob('caelab-expert-*'))
            observed.append({'mode':mode,'status':result['status'],'child_cleanup_confirmed':True})
        finally:
            if process is not None and process.poll() is None:
                process.kill();process.communicate(timeout=5)
            for handle in handles:
                if kernel.WaitForSingleObject(handle,0)!=0:
                    kernel.TerminateProcess(handle,1);kernel.WaitForSingleObject(handle,5000)
                kernel.CloseHandle(handle)
            server.shutdown();server.server_close();worker.join(2)
    assert all(sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in baseline.items())
    print(json.dumps({'controlled':observed,'original_utf8_bytes':len(prompt.encode()),
        'original_sha256':sha256(prompt.encode()).hexdigest(),'official_expected_lf_prefix_bytes':len(prompt.encode())+1,
        'provider_calls':0,'actual_openscience_cli_invocations':0,'real_profile_files_opened':0}))
