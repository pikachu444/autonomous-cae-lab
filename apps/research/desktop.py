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

from caelab.storage import check_id, save_json
from caelab.workbench_client import Client


TOOLS = {'material', 'data', 'numerical', 'pde', 'expert', 'runner', 'simulation', 'evaluation', 'study'}


def _spawn(client, arguments):
    context = client.desktop_context()
    python, repository = Path(context['python']), Path(context['repo_root'])
    if not python.is_file() or not repository.is_dir():
        raise ValueError('The service primary Python or repository is unavailable')
    environment = dict(os.environ, CAELAB_SERVICE_URL=client.url)
    process = subprocess.Popen([str(python), '-m', 'apps.research.desktop', '--service', client.url, *arguments],
                               cwd=repository, env=environment)
    return {'status': 'LAUNCH_REQUESTED', 'pid': process.pid, 'service_url': client.url}


def launch_post(client, input_id, job_id=None, parent=None, *, research_source=None):
    """Open one registered result asynchronously; job_id enables return to design."""
    arguments = ['post', '--input-id', check_id(input_id)]
    if job_id:
        arguments += ['--job-id', check_id(job_id)]
    if research_source is not None:
        if not job_id:
            raise ValueError('A retained stage source requires its exact parent job')
        arguments += ['--research-source', json.dumps(research_source, ensure_ascii=False)]
    return _spawn(client, arguments)


def _post_result_sources(client, job_id, research_source=None):
    if research_source is None:
        result = client.job_navigation(check_id(job_id))
    else:
        if not isinstance(research_source, dict):
            raise ValueError('Select an exact retained stage source')
        keys = set(research_source)
        if keys == {'document_id', 'attempt_id'}:
            result = client.evaluation_stage_result(research_source['document_id'], job_id,
                research_source['attempt_id'], selection={'metadata_only': True})
        elif keys == {'document_id', 'candidate_id', 'evaluation_index', 'attempt_id'}:
            result = client.numerical_evaluation_result(research_source['document_id'], job_id,
                research_source['candidate_id'], evaluation_index=research_source['evaluation_index'],
                attempt_id=research_source['attempt_id'], selection={'metadata_only': True})
        else:
            raise ValueError('Choose the exact evaluation/stage or numerical candidate/stage')
    return [result.get('post_input') or {}, *result.get('post_inputs', [])]


def open_document_result(client, document_id, job_id, *, study_index=None):
    """Open an exact retained field set; mesh studies are separate results."""
    document = client.document_read(check_id(document_id))
    if not any(run['job_id'] == job_id for run in document.get('runs', [])):
        raise ValueError('Selected result does not belong to this document')
    result = client.document_result(document_id, check_id(job_id), selection={'metadata_only': True})
    choices = result.get('post_inputs', [])
    if study_index is not None:
        if type(study_index) is not int or study_index < 0:
            raise ValueError('Choose an exact retained mesh study index')
        post = next((item for item in choices if item.get('study_index') == study_index), None)
    else:
        post = result.get('post_input')
    if not post or not post.get('id'):
        raise ValueError('This selected result has no registered Post field set; inspect its actual diagnostics')
    native = client.native_input(check_id(post['id']))
    if native.get('sha256') != post.get('sha256'):
        raise ValueError('Registered Post input differs from the retained result')
    return launch_post(client,post['id'],job_id=job_id)


def open_discussion_plan(client, discussion_id, turn_id, proposal_index, *, command_id=None):
    document = client.document_read(check_id(discussion_id))
    receipt = client.discussion_plan(discussion_id,turn_id,proposal_index,
        session_id=document['session_id'],command_id=command_id or 'C'+uuid.uuid4().hex)
    target = receipt['document']
    if target.get('kind') != 'numerical' or receipt.get('executed') is not False:
        raise ValueError('The selected proposal did not produce an unexecuted Numerical document')
    result = launch_tool(client,'numerical',document_id=target['id'])
    return {**result,'document_id':target['id'],'executed':False}


def open_pde_plan(client, document_id, *, session_id, expected_generation, command_id=None):
    receipt = client.pde_plan(document_id,session_id=session_id,expected_generation=expected_generation,
        command_id=command_id or 'C'+uuid.uuid4().hex)
    target = receipt['document']
    if target.get('kind') != 'numerical' or receipt.get('executed') is not False:
        raise ValueError('The PDE input did not produce an unexecuted Numerical document')
    return {**launch_tool(client,'numerical',document_id=target['id']),'document_id':target['id'],'executed':False}


def open_domain_plan(client, document_id, *, session_id, expected_generation, command_id=None):
    receipt = client.domain_plan(document_id,session_id=session_id,expected_generation=expected_generation,
        command_id=command_id or 'C'+uuid.uuid4().hex)
    target=receipt['document']
    if target.get('kind')!='numerical' or receipt.get('executed') is not False:
        raise ValueError('The source did not produce an unexecuted Numerical Plan')
    return {**launch_tool(client,'numerical',document_id=target['id']),'document_id':target['id'],'executed':False}


def open_stage_result(client, document_id, job_id, attempt_id):
    result=client.evaluation_stage_result(document_id,job_id,attempt_id,selection={'metadata_only':True})
    post=result.get('post_input')
    if not post:
        raise ValueError('This actual stage has no registered field set; its retained response/diagnostics remain in Evaluation')
    native=client.native_input(post['id'])
    if native.get('sha256')!=post['sha256']:
        raise ValueError('Stage field registration differs from the retained result')
    return launch_post(client,post['id'],job_id=job_id,
        research_source={'document_id':document_id,'attempt_id':attempt_id})


def open_saved_reference(client, reference):
    if reference.get('kind') in {'material','pde','simulation','evaluation'}:
        reference={**reference,'document_kind':reference['kind'],'kind':'document'}
    # Read exact ownership before launching a read-only reference view. Its
    # original owner draft remains editable and is never replaced by old input.
    client.research_reference(reference)
    context=client.desktop_context()
    process=subprocess.Popen([context['python'],'-m','apps.research.reference_window',
        '--service',client.url,'--reference',json.dumps(reference,ensure_ascii=False)],cwd=context['repo_root'],
        env=dict(os.environ,CAELAB_SERVICE_URL=client.url))
    return {'status':'LAUNCH_REQUESTED','pid':process.pid,'reference':reference}


def open_study_followup(client, context, kind):
    document=client.document_read(context['study_id'])
    receipt=client.study_followup(context,kind,session_id=document['session_id'],command_id='C'+uuid.uuid4().hex)
    if receipt.get('executed') is not False:
        raise ValueError('The Study handoff did not confirm an unexecuted editor')
    return {**launch_tool(client,kind,document_id=receipt['document']['id']),'executed':False}


def open_evidence_reference(client, reference):
    """Resolve the selected source identity without widening its access scope."""
    if not isinstance(reference,dict):
        raise ValueError('Choose an explicit retained reference')
    job_id = reference.get('job_id')
    if job_id:
        document = client.document_read(check_id(reference['document_id']))
        run = next((row for row in document.get('runs', []) if row['job_id'] == job_id),None)
        if run is None or any(run.get(key) != reference.get(key) for key in ('input_revision','input_sha256')):
            raise ValueError('Source job and exact submitted input do not match this reference')
        client.document_result(document['id'],job_id,selection=reference.get('selection', []))
        return launch_tool(client,'runner',job_id=job_id)
    if reference.get('document_id'):
        source = {key:reference[key] for key in ('document_id','revision','locator') if key in reference}
        return {'status':'SOURCE_READ','source':client.request('/api/workbench/assist',
            {'operation':'knowledge.source','arguments':source})}
    raise ValueError('This reference has no supported saved document/result locator; its citation remains visible')


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
        raise ValueError('Choose an independently supported research editor or Runner')
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
    if getattr(args, 'input_id', None):
        if args.source or args.assembly:
            raise ValueError('Choose a registered design input or a direct native source')
        receipt = client.native_input(args.input_id)
        if receipt.get('kind') != 'native_design':
            raise ValueError('Choose a registered editable FCStd/CAEPRE input')
        config['input_receipt'] = receipt
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
    source_text = getattr(args, 'research_source', None)
    research_source = json.loads(source_text) if source_text is not None else None
    if research_source is not None and not args.job_id:
        raise ValueError('A stage source requires the exact parent job')
    if args.project:
        project = Path(args.project).resolve(strict=True)
        folder = _folder(context, 'post', args.output)
    else:
        if args.job_id:
            selected = _post_result_sources(client, check_id(args.job_id), research_source)
            if not args.input_id or args.input_id not in {item.get('id') for item in selected}:
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
    origin_job_id = args.job_id or document.get('origin_job_id')
    if args.job_id:
        if args.project and research_source is None:
            research_source = document.get('origin_research_source')
        selected = _post_result_sources(client, check_id(args.job_id), research_source)
        expected = {item.get('id') for item in selected} - {None}
        actual = {record.get('input_id') for record in document.get('sources', {}).values()}
        if not expected.intersection(actual) or (args.input_id and (args.input_id not in expected or args.input_id not in actual)):
            raise ValueError('The requested Post project does not belong to the selected job')
    if origin_job_id:
        document['origin_job_id'] = check_id(origin_job_id)
        if research_source is not None:
            document['origin_research_source'] = research_source
    # Native save_project preserves these top-level fields, allowing an explicit
    # saved/reopened analysis to return to its design through the same helper.
    if not args.project:
        document.update(desktop_python=context['python'], repo_root=context['repo_root'], service_url=client.url)
        save_json(project, document)
    if args.prepare_only:
        return {'status':'PREPARED', 'project':str(project), 'state':str(state)}
    environment = dict(os.environ, PV_MACRO_PATH=str(home / ('macros_external' if document.get('kind') == 'external-result' else 'macros')),
        CAE_POST_HOME=str(home), CAE_POST_PROJECT=str(project), CAE_POST_SERVICE_URL=client.url,
        CAE_POST_LAUNCH_DIR=str(folder),
        CAELAB_DESKTOP_PYTHON=context['python'], CAELAB_REPO_ROOT=context['repo_root'])
    # Prevent an inherited Post origin from attaching itself to an unrelated input.
    environment.pop('CAELAB_ORIGIN_JOB_ID', None)
    if origin_job_id:
        environment['CAELAB_ORIGIN_JOB_ID'] = origin_job_id
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
    pre.add_argument('--input-id')
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
    post.add_argument('--research-source')
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
