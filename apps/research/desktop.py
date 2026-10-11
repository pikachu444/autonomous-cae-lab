"""Desktop navigation through the existing service and native application owners.

Native workspace preparation runs in a separate primary-Python helper process.
Recorded CAD is passed to cae_prep, which makes an editable working copy.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from caelab.storage import check_id
from caelab.workbench_client import Client


TOOLS = {'material', 'data', 'numerical', 'runner'}


def _spawn(client, arguments):
    context = client.desktop_context()
    python, repository = Path(context['python']), Path(context['repo_root'])
    if not python.is_file() or not repository.is_dir():
        raise ValueError('The service primary Python or repository is unavailable')
    environment = dict(os.environ, CAELAB_SERVICE_URL=client.url)
    process = subprocess.Popen([str(python), '-m', 'apps.research.desktop', '--service', client.url, *arguments],
                               cwd=repository, env=environment)
    return {'status': 'LAUNCH_REQUESTED', 'pid': process.pid, 'service_url': client.url}


def launch_post(client, input_id, job_id=None, parent=None):
    """Open one registered result asynchronously; job_id enables return to design."""
    arguments = ['post', '--input-id', check_id(input_id)]
    if job_id:
        arguments += ['--job-id', check_id(job_id)]
    return _spawn(client, arguments)


def launch_pre(client, source=None, parent=None):
    """Start a new editable Pre document, optionally from an exact local source."""
    arguments = ['pre']
    if source:
        arguments += ['--source', str(Path(source).resolve(strict=True))]
    return _spawn(client, arguments)


def launch_tool(client, tool, job_id=None, document_id=None, parent=None):
    if tool == 'pre':
        if job_id:
            return open_origin(client, job_id, parent=parent)
        if document_id:
            origin = client.document_read(check_id(document_id))
            if origin.get('kind') != 'pre' or not origin.get('connected'):
                raise ValueError('The selected native Pre document is not connected')
            return _activate(client, origin)
        return launch_pre(client, parent=parent)
    if tool == 'post':
        if document_id:
            origin = client.document_read(check_id(document_id))
            if origin.get('kind') != 'post' or not origin.get('connected'):
                raise ValueError('The selected native Post document is not connected')
            if 'document.activate' not in origin.get('capabilities', []):
                raise ValueError('This Post owner does not support live activation; open its retained result or saved project')
            return _activate(client, origin)
        if job_id:
            post = client.job_navigation(check_id(job_id)).get('post_input') or {}
            if not post.get('id'):
                raise ValueError('The selected job has no retained Post input')
            return launch_post(client, post['id'], job_id=job_id, parent=parent)
        return _spawn(client, ['post'])
    if tool not in TOOLS:
        raise ValueError('Choose Material, Data, Numerical or Runner')
    if (tool == 'runner' and document_id) or (tool != 'runner' and job_id):
        raise ValueError('Runner selects a job; research editors select a document')
    arguments = [tool]
    if job_id:
        arguments += ['--job-id', check_id(job_id)]
    if document_id:
        arguments += ['--document-id', check_id(document_id)]
    return _spawn(client, arguments)


def _activate(client, origin):
    receipt = client.document_command(check_id(origin['id']), 'document.activate', {},
        session_id=origin['session_id'], expected_generation=origin['generation'],
        command_id='C' + uuid.uuid4().hex)
    command = receipt.get('command', receipt)
    identifier = command.get('id', command.get('command_id'))
    if not identifier:
        raise RuntimeError('Activation has no command receipt; inspect the owner before retrying')
    deadline = time.monotonic() + 30
    while command.get('state') not in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'REJECTED', 'INTERRUPTED'}:
        if time.monotonic() >= deadline:
            raise RuntimeError(f'Activation {identifier} is pending or unconfirmed; no retained copy was opened')
        time.sleep(.1)
        command = client.command_status(identifier)
    if command['state'] != 'SUCCEEDED':
        raise RuntimeError(f'Native source activation {identifier} {command["state"]}: {command.get("outcome", command.get("error", ""))}')
    return {'status': 'ACTIVATED', 'document_id': origin['id'], 'command_id': identifier}


def open_origin(client, job_id, parent=None):
    """Activate the exact live source or explicitly open its retained design copy.

    An ambiguous/failed live command never falls back to opening a new copy.
    Call from a worker when a GUI needs to wait for native command completion.
    """
    navigation = client.job_navigation(check_id(job_id))
    origin = navigation.get('origin_document')
    if origin and origin.get('kind') in TOOLS - {'runner'}:
        return launch_tool(client, origin['kind'], document_id=origin['id'], parent=parent)
    if origin and origin.get('kind') == 'pre' and origin.get('connected'):
        return _activate(client, origin)
    retained = navigation.get('retained_design_input_id')
    if not retained:
        raise ValueError('This job has no available source document or retained design copy')
    native = client.native_input(check_id(retained))
    if native.get('id') != retained or native.get('kind') != 'frozen_fem' or not native.get('editable_path'):
        raise ValueError('The retained design receipt does not identify an editable FEM copy')
    return _spawn(client, ['pre', '--source', native['editable_path'], '--source-label',
                          'Retained design copy — ' + job_id])


def _choose_file(title, filters):
    from PySide6.QtWidgets import QApplication, QFileDialog
    application = QApplication.instance() or QApplication(sys.argv[:1])
    path, _ = QFileDialog.getOpenFileName(None, title, '', filters)
    if not path:
        raise ValueError('No file selected')
    return Path(path).resolve(strict=True)


def _executable(context, key, override=None, interactive=True):
    value = override or context.get(key)
    candidate = Path(value) if value else None
    if override and not candidate.is_file():
        raise ValueError('The specified installed executable is unavailable: ' + str(candidate))
    if candidate is None or not candidate.is_file():
        if not interactive:
            raise ValueError('Configure ' + key + ' or pass its installed executable')
        candidate = _choose_file('Choose installed ' + ('FreeCAD' if key == 'freecad_executable' else 'ParaView'),
                                 'Application (*.exe);;All files (*)')
    return candidate.resolve(strict=True)


def _folder(context, tool, output=None):
    folder = Path(output).absolute() if output else Path(context['export_root']) / 'desktop' / (tool + '-' + uuid.uuid4().hex)
    folder.mkdir(parents=True, exist_ok=True)
    if any(folder.iterdir()):
        raise ValueError('Use a new or empty desktop output directory; retained files are preserved')
    return folder


def _pre(client, args):
    context = client.desktop_context()
    executable = _executable(context, 'freecad_executable', args.executable, not args.prepare_only)
    folder = _folder(context, 'pre', args.output)
    config = {'output':str(folder), 'service_url':client.url,
              'export_root':context['export_root'], 'python':context['python']}
    for name in ('source', 'assembly'):
        value = getattr(args, name)
        if value:
            source = Path(value).resolve(strict=True)
            if not source.is_file():
                raise ValueError('Native source must be a local file')
            config[name] = str(source)
    if args.source_label:
        config['source_label'] = args.source_label
    if args.gmsh:
        config['gmsh'] = str(Path(args.gmsh).resolve(strict=True))
    else:
        gmsh = executable.parent / 'bin' / 'gmsh.exe'
        if gmsh.is_file(): config['gmsh'] = str(gmsh)
    config_path = folder / 'config.json'
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    module = str(Path(context['repo_root']) / 'apps/desktop_pre')
    macro = folder / 'start.FCMacro'
    macro.write_text('import sys\nsys.path.insert(0, ' + repr(module) + ')\nimport cae_prep\ncae_prep.start(' + repr(str(config_path)) + ')\n', encoding='utf-8')
    if args.prepare_only:
        return {'status':'PREPARED', 'output':str(folder), 'config':str(config_path)}
    process = subprocess.Popen([str(executable), '-u', str(folder / 'user.cfg'), '-s', str(folder / 'system.cfg'), str(macro)], cwd=folder)
    return {'status':'LAUNCHED', 'pid':process.pid, 'output':str(folder), 'source_label':args.source_label}


def _post(client, args):
    context = client.desktop_context()
    executable = _executable(context, 'paraview_executable', args.executable, not args.prepare_only)
    home = Path(context['repo_root']) / 'apps/desktop_post'
    if args.project:
        project = Path(args.project).resolve(strict=True)
        folder = _folder(context, 'post', args.output)
    else:
        if args.job_id:
            selected = client.job_navigation(check_id(args.job_id)).get('post_input') or {}
            if not args.input_id or selected.get('id') != args.input_id:
                raise ValueError('Open the selected job using its exact registered Post input')
        folder = _folder(context, 'post', args.output)
        pvpython = executable.with_name('pvpython.exe' if executable.suffix.lower() == '.exe' else 'pvpython')
        if not pvpython.is_file():
            raise ValueError('The selected ParaView installation has no adjacent pvpython executable')
        workspace = folder / 'workspace'
        command = [str(pvpython), '--force-offscreen-rendering', str(home / 'external.py')]
        if args.input_id:
            command += [str(workspace), '--registered-input', check_id(args.input_id), '--service-url', client.url]
        else:
            source = Path(args.input_path).resolve(strict=True) if args.input_path else _choose_file('Open retained VTU/PVD result', 'Result files (*.vtu *.pvd)')
            command += [str(source), str(workspace)]
        with (folder / 'prepare.stdout.log').open('wb') as stdout, (folder / 'prepare.stderr.log').open('wb') as stderr:
            completed = subprocess.run(command, cwd=folder, stdout=stdout, stderr=stderr, check=False)
        if completed.returncode:
            raise RuntimeError('Native Post preparation failed; inspect ' + str(folder / 'prepare.stderr.log'))
        project = workspace / 'project.json'
    document = json.loads(project.read_text(encoding='utf-8-sig'))
    state = (project.parent / document['workspace_file']).resolve(strict=True)
    if not state.is_file():
        raise ValueError('The selected Post project has no native workspace state')
    if args.prepare_only:
        return {'status':'PREPARED', 'project':str(project), 'state':str(state)}
    environment = dict(os.environ, PV_MACRO_PATH=str(home / ('macros_external' if document.get('kind') == 'external-result' else 'macros')),
        CAE_POST_HOME=str(home), CAE_POST_PROJECT=str(project), CAE_POST_SERVICE_URL=client.url,
        CAE_POST_LAUNCH_DIR=str(folder),
        CAELAB_DESKTOP_PYTHON=context['python'], CAELAB_REPO_ROOT=context['repo_root'])
    # Prevent an inherited Post origin from attaching itself to an unrelated input.
    environment.pop('CAELAB_ORIGIN_JOB_ID', None)
    origin_job_id = args.job_id or document.get('origin_job_id')
    if args.job_id:
        navigation = client.job_navigation(check_id(args.job_id))
        expected = (navigation.get('post_input') or {}).get('id')
        actual = {record.get('input_id') for record in document.get('sources', {}).values()}
        if not expected or expected not in actual or (args.input_id and expected != args.input_id):
            raise ValueError('The requested Post project does not belong to the selected job')
    if origin_job_id:
        environment['CAELAB_ORIGIN_JOB_ID'] = check_id(origin_job_id)
        document['origin_job_id'] = origin_job_id
    # Native save_project preserves these top-level fields, allowing an explicit
    # saved/reopened analysis to return to its design through the same helper.
    if not args.project:
        document.update(desktop_python=context['python'], repo_root=context['repo_root'], service_url=client.url)
        temporary = project.with_name('launch-' + uuid.uuid4().hex + '.json')
        try:
            temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
            temporary.replace(project)
        finally:
            if temporary.exists(): temporary.unlink()
    # Reopening a retained revision updates only the launch environment. Neither
    # runtime metadata nor startup logs are written into that saved revision.
    process = subprocess.Popen([str(executable), '--disable-registry', '--script=' + str(home / 'startup.py'),
                                '--log=' + str(folder / 'native_gui.log')], cwd=folder, env=environment)
    return {'status':'LAUNCHED', 'pid':process.pid, 'project':str(project), 'state':str(state)}


def _arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', default=os.getenv('CAELAB_SERVICE_URL'))
    sub = parser.add_subparsers(dest='tool', required=True)
    pre = sub.add_parser('pre')
    pre.add_argument('--source'); pre.add_argument('--assembly'); pre.add_argument('--source-label'); pre.add_argument('--gmsh')
    post = sub.add_parser('post')
    choice = post.add_mutually_exclusive_group()
    choice.add_argument('--project'); choice.add_argument('--input-path'); choice.add_argument('--input-id')
    origin = sub.add_parser('origin'); origin.add_argument('--job-id', required=True)
    for name in sorted(TOOLS):
        tool = sub.add_parser(name)
        tool.add_argument('--job-id' if name == 'runner' else '--document-id')
    for tool in (pre, post):
        tool.add_argument('--executable'); tool.add_argument('--output'); tool.add_argument('--prepare-only', action='store_true')
    post.add_argument('--job-id')
    return parser.parse_args(argv)


def main(argv=None):
    args = _arguments(argv)
    if not args.service:
        raise ValueError('Specify the existing local service URL')
    client = Client(args.service)
    if args.tool == 'pre': result = _pre(client, args)
    elif args.tool == 'post': result = _post(client, args)
    elif args.tool == 'origin': result = open_origin(client, args.job_id)
    else:
        from importlib import import_module
        arguments = ['--service', client.url]
        identifier = args.job_id if args.tool == 'runner' else args.document_id
        if identifier:
            arguments += ['--job-id' if args.tool == 'runner' else '--document-id', check_id(identifier)]
        return import_module('apps.research.' + args.tool + '_window').main(arguments)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print('Desktop launch failed: ' + str(error), file=sys.stderr)
        from PySide6.QtWidgets import QApplication, QMessageBox
        application = QApplication.instance() or QApplication(sys.argv[:1])
        QMessageBox.critical(None, 'Desktop launch failed', str(error))
        raise SystemExit(1)
