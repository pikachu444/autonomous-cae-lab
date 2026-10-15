"""Existing owned-command transport; no host setup, SCP, shell=True or credentials."""
import base64
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys

if __package__:
    from .execution_control import run_owned_command


class SSHTransport:
    def __init__(self, host):
        self.host = host

    def request(self, action, payload, folder):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=False)
        helper = Path(__file__).with_name('remote_schedulers.py').read_bytes()
        envelope = base64.b64encode(json.dumps(dict(payload, action=action),
            ensure_ascii=False, allow_nan=False).encode()).decode('ascii')
        script = helper + ('\n_entry(' + repr(envelope) + ')\n').encode()
        source = folder / 'request.py'
        source.write_bytes(script)
        executable = self.host.get('ssh_executable', 'ssh')
        if not shutil.which(executable):
            raise ValueError('기존 OpenSSH 실행 파일을 찾지 못했습니다. 원격 연결 설정을 확인하세요.')
        target = self.host['target']
        if not re.fullmatch(r'(?:[A-Za-z0-9_.-]+@)?[A-Za-z0-9][A-Za-z0-9_.-]*', target):
            raise ValueError('Use an operator-registered SSH host or alias')
        argv = [executable, '-T', '-oBatchMode=yes', '-oStrictHostKeyChecking=yes',
                '-oForwardAgent=no', '-oClearAllForwardings=yes', '-oConnectTimeout=15',
                '-p', str(self.host.get('port', 22)), '--', target,
                shlex.join([self.host.get('python', 'python3'), '-'])]
        # Connection settings stay in the live child's environment, never in artifacts.
        environment = dict(os.environ)
        environment['CAELAB_REMOTE_SSH_ARGV'] = json.dumps(argv)
        # The tiny pipe child inherits the existing owned Windows Job/POSIX group.
        launcher = str(Path(__file__).resolve())
        run_owned_command([sys.executable, launcher, str(source)], folder, 'ssh',
            timeout=self.host.get('command_timeout', 45), env=environment, owned_tree=True).check_returncode()
        stdout = (folder / 'ssh.stdout.log').read_text(encoding='utf-8')
        if len(stdout.encode()) > 2 * self.host.get('transfer_limit', 16 * 1024**2) + 65536:
            raise ValueError('Remote response exceeds the configured transfer budget')
        response = json.loads(stdout)
        if not isinstance(response, dict) or response.get('ok') is not True:
            message = response.get('message', 'Remote command did not return a valid receipt')
            raise ValueError(message)
        return response['value']


def _pipe(source):
    import subprocess
    argv = json.loads(os.environ.pop('CAELAB_REMOTE_SSH_ARGV'))
    completed = subprocess.run(argv, input=Path(source).read_bytes(),
                               stdout=sys.stdout.buffer, stderr=subprocess.PIPE, check=False)
    if completed.returncode:
        sys.stderr.write('OpenSSH command failed; check the existing connection in your SSH client.\n')
    return completed.returncode


if __name__ == '__main__':
    raise SystemExit(_pipe(*sys.argv[1:]))
