"""Controlled transport invocation; no SSH binary or authentication file is used."""
import json
from pathlib import Path
import subprocess

from caelab.remote_transport import SSHTransport
from test_remote_execution import host


def test_connection_arguments_remain_in_live_environment_not_artifacts(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr('caelab.remote_transport.shutil.which',lambda _:r'C:\Windows\System32\OpenSSH\ssh.exe')
    def controlled(argv,cwd,label,**kwargs):
        calls.append((argv,kwargs))
        (Path(cwd)/'ssh.stdout.log').write_text(json.dumps({'ok':True,'value':{'state':'UNKNOWN','terminated':False}}),encoding='utf-8')
        return subprocess.CompletedProcess(argv,0)
    monkeypatch.setattr('caelab.remote_transport.run_owned_command',controlled)
    value=SSHTransport(host()).request('query',{'token':'R'+'1'*32},tmp_path/'command')
    assert value['terminated'] is False
    argv,options=calls[0];native=json.loads(options['env']['CAELAB_REMOTE_SSH_ARGV'])
    assert '-oBatchMode=yes' in native and '-oStrictHostKeyChecking=yes' in native
    assert '-oForwardAgent=no' in native and options['owned_tree'] is True
    assert not (tmp_path/'command'/'ssh-argv.json').exists()
    assert all(b'public-fixture.invalid' not in path.read_bytes() for path in (tmp_path/'command').rglob('*') if path.is_file())
    assert not any('public-fixture.invalid' in arg for arg in argv)
