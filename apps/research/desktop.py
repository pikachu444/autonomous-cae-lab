"""Desktop navigation through the existing service and native application owners.

Native workspace preparation runs in a separate primary-Python helper process.
Recorded CAD is passed to cae_prep, which makes an editable working copy.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from caelab.storage import check_id, save_json
from caelab.workbench_client import Client


TOOLS = {'material', 'data', 'numerical', 'pde', 'expert', 'runner', 'simulation', 'evaluation', 'study', 'report', 'connection'}


def _research_context(client):
    context = client.desktop_context()
    if os.name == 'nt' and str(context['python']).startswith('/'):
        # The solver service can live in WSL while its research windows stay
        # with this Windows client. Native preparation still uses the service.
        python = Path(sys.executable)
        repository = Path(__file__).resolve().parents[2]
        if not python.stem.lower().startswith('python') or not python.is_file():
            raise ValueError('Windows 연구 프로그램의 Python 환경에서 창을 열어 주세요.')
        if not (repository / 'apps/research/desktop.py').is_file():
            raise ValueError('Windows 연구 프로그램의 설치 폴더를 찾을 수 없습니다.')
        context = dict(context, python=str(python), repo_root=str(repository))
    return context


def _spawn(client, arguments):
    context = _research_context(client) if arguments and arguments[0] in TOOLS else client.desktop_context()
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
    context=_research_context(client)
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
    if reference.get('paper_id'):
        locator = reference.get('locator')
        if not isinstance(locator, dict) or not locator.get('archive_id'):
            raise ValueError('This citation has no retained literature archive; no replacement source was fetched')
        payload = client.request('/api/workbench/assist', {'operation': 'literature.read',
            'arguments': {'paper_id': reference['paper_id'], 'locator': deepcopy(locator)}})
        paper = payload.get('paper') or {}
        if any(key in reference and reference[key] != paper.get(key)
               for key in ('doi', 'url', 'title', 'authors', 'provider')):
            raise ValueError('This citation differs from its retained literature metadata')
        if ('read_status' in reference and reference['read_status'] != payload.get('status')
                or 'text' in reference and not any(row.get('text') == reference['text']
                    for row in payload.get('segments', []))):
            raise ValueError('This citation differs from the retained text or read scope')
        scope = {'abstract_only': 'abstract only; full text not read',
                 'metadata_only': 'bibliographic metadata only; abstract/full text not read'}.get(
                     payload.get('status'), payload.get('read_scope'))
        if 'read_scope' in reference and reference['read_scope'] != scope:
            raise ValueError('This citation claims a different source reading scope')
        source = deepcopy(payload)
        source['title'] = (source.get('paper') or {}).get('title') or 'Literature source'
        return {'status': 'SOURCE_READ', 'source': source}
    if reference.get('run_id'):
        selection = reference.get('response_selection')
        if (not isinstance(selection, list) or any(not isinstance(name, str) or not name for name in selection)):
            raise ValueError('Select the stored result citation and its explicit response channels')
        identifier = check_id(reference['run_id'])
        if not selection:
            job = client.request('/api/workbench/jobs/' + identifier)
            return {'status': 'RESULT_READ', 'reference': deepcopy(reference),
                    'payload': {'status': 'AVAILABLE', 'kind': 'job', 'job': job}}
        result = client.result(identifier, selection={'responses': selection, 'rows': [0, 256]})
        return {'status': 'RESULT_READ', 'reference': deepcopy(reference),
                'payload': {'status': 'AVAILABLE', 'kind': 'result', 'result': result}}
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
    if tool in {'expert', 'study'} and document_id:
        from .result_return import activate_existing
        receipt = activate_existing(client, check_id(document_id))
        if receipt.get('status') == 'ACTIVATED':
            return receipt
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
    if native.get('id') != retained or native.get('kind') not in {'frozen_fem', 'frozen_contact', 'frozen_shell', 'frozen_beam'} or not native.get('editable_path'):
        raise ValueError('The retained design receipt does not identify an editable FEM copy')
    return _spawn(client, ['pre', '--source', native['editable_path'], '--source-label',
                          'Retained design copy — ' + job_id])


def _native_pid_alive(pid):
    """Conservative local liveness; None means uncertain, never permission to launch."""
    if type(pid) is not int or pid <= 0:
        return None
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE, no process mutation.
        if not handle:
            return False if ctypes.get_last_error() == 87 else None
        try:
            state = kernel.WaitForSingleObject(handle, 0)
            return False if state == 0 else True if state == 258 else None
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return None


def open_post_observation(client, reference, *, launch_closed=True):
    """Reuse exact live measurement or reopen its verified saved native project."""
    payload = client.post_observation(reference)
    if not payload['source_available']:
        raise ValueError('Original Post is unavailable; the retained curve remains in Data. ' +
                         str(payload['source_error']))
    origin = payload['origin']
    # Do not transport the per-row mapping in a native broker command.
    source = {key: origin[key] for key in ('kind', 'document_id', 'session_id', 'pid',
        'project', 'workspace', 'object_ref', 'revision', 'recipe_sha256', 'result_files_sha256', 'result_sha256')}
    documents = client.documents()['documents']
    matches = [doc for doc in documents if doc.get('kind') == 'post' and doc['id'] == origin['document_id']]
    connected = [doc for doc in matches if doc.get('connected')]
    if len(connected) > 1:
        raise ValueError('More than one native owner claims this project; select/reconnect the original owner')
    if connected:
        native = connected[0]
        receipt = client.document_command(native['id'], 'post.measurement_open', {'origin': source},
            session_id=native['session_id'], expected_generation=native['generation'],
            command_id='C' + uuid.uuid4().hex)
        command = receipt.get('command', receipt)
        identifier = command.get('command_id', command.get('id'))
        deadline = time.monotonic() + 20
        while command.get('state') not in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'REJECTED', 'INTERRUPTED'}:
            if time.monotonic() >= deadline:
                raise RuntimeError('Native source selection is unconfirmed; reconnect before retrying')
            time.sleep(.05)
            command = client.command_status(identifier)
        envelope = command.get('outcome', {}).get('result', {})
        if command['state'] != 'SUCCEEDED' or envelope.get('status') != 'COMPLETED':
            raise RuntimeError('The live Post source was not changed: ' +
                               str(command.get('outcome', command.get('error'))))
        actual_pid = native.get('state', {}).get('pid')
        _confirm_post_launch(client, origin, actual_pid)
        return {'status': 'SHOWN', 'document_id': native['id'], 'command_id': identifier,
                'native_pid': actual_pid}
    pids = {origin.get('pid'), *[doc.get('state', {}).get('pid') for doc in matches]}
    if any(_native_pid_alive(pid) is not False for pid in pids):
        raise ValueError('Original Post is disconnected or its closure is uncertain; reconnect that window first')
    if not launch_closed:
        return None
    return _spawn(client, ['post', '--measurement-result', json.dumps(reference, ensure_ascii=False)])


def _confirm_post_launch(client, origin, native_pid):
    """A successful exact native command also reconciles a previously slow launch."""
    if type(native_pid) is not int or native_pid <= 0:
        return
    from .result_return import _route, _lock, service_identity
    _, path = _route(service_identity(client.url), 'post-launch-' + origin['document_id'])
    lock = _lock(path)
    if not lock.tryLock(0):
        return  # The launch helper holding this lock records its own confirmation.
    try:
        marker = path.with_suffix('.native-launch.json')
        if marker.exists():
            save_json(marker, {'state': 'CONFIRMED', 'native_pid': native_pid,
                               'project_sha256': origin['project']['sha256']})
    finally:
        lock.unlock()


def _post_launch_claim(client, origin):
    """Reuse the transient Qt lock mechanism for the native startup gap."""
    from .result_return import _route, _lock, service_identity
    _, path = _route(service_identity(client.url), 'post-launch-' + origin['document_id'])
    lock = _lock(path)
    if not lock.tryLock(0):
        raise ValueError('This saved Post project is already opening; wait for that native window')
    marker = path.with_suffix('.native-launch.json')
    try:
        if marker.exists():
            previous = json.loads(marker.read_text(encoding='utf-8'))
            alive = _native_pid_alive(previous.get('native_pid')) if previous.get('state') == 'CONFIRMED' else None
            if alive is not False:
                raise ValueError('A previous native launch is running or unconfirmed; reconnect it before another launch')
        return lock, marker
    except BaseException:
        lock.unlock()
        raise


def _choose_file(title, filters):
    from PySide6.QtWidgets import QApplication, QFileDialog
    application = QApplication.instance() or QApplication(sys.argv[:1])
    path, _ = QFileDialog.getOpenFileName(None, title, '', filters)
    if not path:
        raise ValueError('No file selected')
    return Path(path).resolve(strict=True)


def _executable(context, key, override=None, interactive=True):
    from caelab.native_tools import TOOLS, discover, saved_executable
    title, variable, _ = TOOLS[key]
    explicit = any(value is not None and value != '' for value in (override, context.get(key), os.environ.get(variable)))
    settings = None
    saved = None
    if not explicit:
        if interactive:
            settings = _native_settings()
            saved = settings.value(key, '', type=str)
        else:
            saved = saved_executable(key)
    result = discover(key, override=override, context=context, saved=saved)
    if result['status'] == 'INVALID':
        raise ValueError(result['source'] + '에 지정한 실행 파일이 없습니다: ' + result['path'] +
                         '\n해당 경로를 수정한 뒤 다시 여세요.')
    if result['status'] == 'FOUND':
        return Path(result['path'])
    if not interactive:
        paths = ', '.join(row['path'] for row in result['candidates'])
        raise ValueError(title + ' 실행 파일을 지정하세요 (--executable 또는 desktop.' + key + ').' +
                         (' 여러 설치가 있습니다: ' + paths if paths else ' 설치된 실행 파일을 찾지 못했습니다.'))
    if result['status'] == 'MULTIPLE':
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QInputDialog, QComboBox, QDialog
        application = QApplication.instance() or QApplication(sys.argv[:1])
        paths = [row['path'] for row in result['candidates']]
        other = '다른 실행 파일 선택…'
        labels = [(Path(path).parent.parent.name if Path(path).parent.name.lower() == 'bin'
                   else Path(path).parent.name) + ' — ' + path for path in paths]
        dialog = QInputDialog()
        dialog.setWindowTitle(title + ' 설치 선택')
        dialog.setLabelText('사용할 실행 파일')
        dialog.setComboBoxItems(labels + [other])
        dialog.setComboBoxEditable(False)
        dialog.setOkButtonText('선택')
        dialog.setCancelButtonText('취소')
        combo = dialog.findChild(QComboBox)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(28)
        for index, path in enumerate(paths):
            combo.setItemData(index, path, Qt.ItemDataRole.ToolTipRole)
        dialog.resize(640, 160)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        index = combo.currentIndex()
        dialog.deleteLater()
        if not accepted:
            raise ValueError('실행 파일 선택을 취소했습니다. 기존 경로는 유지됩니다.')
        candidate = Path(paths[index]) if index < len(paths) else _choose_file(title + ' 실행 파일 선택',
                                                                            'Application (*.exe);;All files (*)')
    else:
        candidate = _choose_file(title + (' 실행 파일 다시 선택' if result['stale_saved'] else ' 실행 파일 선택'),
                                 'Application (*.exe);;All files (*)')
    candidate = candidate.resolve(strict=True)
    if not candidate.is_file():
        raise ValueError('실행 파일을 선택하세요: ' + str(candidate))
    settings = settings or _native_settings()
    settings.setValue(key, str(candidate))
    settings.sync()
    return candidate


def _native_settings():
    from PySide6.QtCore import QSettings
    return QSettings('AutonomousCAELab', 'DesktopLaunchers')


def _folder(context, tool, output=None):
    folder = Path(output).absolute() if output else Path(context['export_root']) / 'desktop' / (tool + '-' + uuid.uuid4().hex)
    folder.mkdir(parents=True, exist_ok=True)
    if any(folder.iterdir()):
        raise ValueError('Use a new or empty desktop output directory; retained files are preserved')
    return folder


def _pre(client, args, *, _native_project_ticket=None, _local_context=None):
    ticket = _native_project_ticket
    if ticket is not None:
        from caelab.native_project_contract import NativeOpenTicket, require_open_binding, require_verified_input
        if type(ticket) is not NativeOpenTicket:
            raise ValueError('현재 검증된 모델 열기 요청을 선택하세요.')
        binding = require_open_binding(ticket.binding)
        verified = require_verified_input(ticket.verified_input)
        if (binding.reference != verified.reference or binding.context_session != verified.context_session
                or verified.snapshot['native_kind'] != 'pre' or ticket.status != 'PREPARED'):
            raise ValueError('선택한 모델의 현재 열기 요청이 다릅니다.')
        if any(getattr(args, key, None) for key in ('source', 'assembly', 'input_id')):
            raise ValueError('저장한 모델과 다른 원 입력을 함께 열 수 없습니다.')
    if client is None:
        if ticket is None or _local_context is None:
            raise ValueError('독립 열기에는 현재 설치와 검증된 모델 요청이 필요합니다.')
        context = dict(_local_context)
        if Path(context['repo_root']).resolve(strict=True) != Path(__file__).resolve().parents[2]:
            raise ValueError('사본에 기록된 경로 대신 현재 설치에서 열어 주세요.')
    else:
        context = client.desktop_context()
    executable = _executable(context, 'freecad_executable', args.executable, not args.prepare_only)
    folder = _folder(context, 'pre', args.output)
    config = {'output':str(folder), 'service_url':client.url if client is not None else None,
              'export_root':context['export_root'], 'python':context['python']}
    if ticket is not None:
        config['native_project_open'] = ticket.derived['launch_config']
    from caelab.native_tools import discover, saved_executable
    post_runtime = discover('paraview_executable', context=context,
                            saved=saved_executable('paraview_executable'))
    if post_runtime['status'] in {'FOUND', 'INVALID'}:
        config['paraview_executable'] = post_runtime['path']
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
        # Portable root launchers and bin/FreeCAD.exe share the same bundled mesher.
        for gmsh in (executable.parent / 'gmsh.exe', executable.parent / 'bin' / 'gmsh.exe',
                     executable.parent / 'gmsh'):
            if gmsh.is_file():
                config['gmsh'] = str(gmsh.resolve())
                break
    config_path = folder / 'config.json'
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    module = str(Path(context['repo_root']) / 'apps/desktop_pre')
    macro = folder / 'start.FCMacro'
    macro.write_text('import sys\nsys.path.insert(0, ' + repr(module) + ')\nimport cae_prep\ncae_prep.start(' + repr(str(config_path)) + ')\n', encoding='utf-8')
    if args.prepare_only:
        return {'status':'PREPARED', 'output':str(folder), 'config':str(config_path)}
    process = subprocess.Popen([str(executable), '-u', str(folder / 'user.cfg'), '-s', str(folder / 'system.cfg'), str(macro)], cwd=folder)
    return {'status':'LAUNCHED', 'pid':process.pid, 'output':str(folder), 'source_label':args.source_label}


def _register_post_inspection(client, selected):
    """Use approved folders and confirm the same selected manifest before opening."""
    import hashlib
    from PySide6.QtWidgets import QApplication, QInputDialog
    app = QApplication.instance() or QApplication(sys.argv[:1])
    key = {'contact-inspection.json':'contact_inspection','shell_inspection.json':'shell_inspection',
           'beam_inspection.json':'beam_inspection'}[selected.name]
    def pin():
        digest=hashlib.sha256()
        with selected.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
        return {'relative':selected.name,'bytes':selected.stat().st_size,'sha256':digest.hexdigest()}
    expected=pin();roots=client.local_roots().get('roots',[])
    if not roots:raise ValueError('결과를 읽을 등록 폴더를 먼저 설정하세요.')
    labels=[row.get('label',row['id']) for row in roots]
    name,ok=QInputDialog.getItem(None,'해석 결과 등록','선택한 파일이 있는 등록 폴더',labels,editable=False)
    if not ok:raise ValueError('결과 등록을 취소했습니다. 원파일은 그대로입니다.')
    root=roots[labels.index(name)]['id'];relative='';cursor=0
    while True:
        payload=client.local_inputs(root,relative,cursor=cursor)
        rows=[('상위 폴더','parent')] if relative else []
        rows += [('폴더: '+row['name'] if row['directory'] else row['name'],row) for row in payload['entries']
                 if row['directory'] or row['name']==selected.name]
        if payload.get('next_cursor') is not None:rows.append(('다음 파일 목록…','next'))
        if not rows:raise ValueError('선택한 결과 선언 파일을 이 등록 폴더에서 찾을 수 없습니다.')
        name,ok=QInputDialog.getItem(None,'해석 결과 등록','선택한 선언 파일: '+selected.name+' / '+(relative or '최상위'),
                                   [label for label,_ in rows],editable=False)
        if not ok:raise ValueError('결과 등록을 취소했습니다. 원파일은 그대로입니다.')
        row=next(item for label,item in rows if label==name)
        if row=='parent':relative=relative.rpartition('/')[0];cursor=0
        elif row=='next':cursor=payload['next_cursor']
        elif row['directory']:relative=row['relative'];cursor=0
        else:
            receipt=client.register_local_input(root,row['relative'])
            if pin()!=expected or (receipt.get('native_metadata') or {}).get(key)!=expected:
                raise ValueError('등록한 자료가 처음 선택한 파일과 다릅니다. 원파일을 확인하고 다시 선택하세요.')
            return check_id(receipt['id'])


def _post(client, args, *, _report_origin=None, _report_launch=None,
          _measurement_origin=None, _origin_launch=None,
          _native_project_ticket=None, _local_context=None):
    native_ticket = _native_project_ticket
    if native_ticket is not None:
        from caelab.native_project_contract import NativeOpenTicket, require_open_binding, require_verified_input
        from caelab.native_post_dependencies import verify_snapshot_members
        if type(native_ticket) is not NativeOpenTicket:
            raise ValueError('A verified current native project ticket is required')
        binding = require_open_binding(native_ticket.binding)
        verified = require_verified_input(native_ticket.verified_input)
        if (binding.reference != verified.reference or binding.context_session != verified.context_session
                or verified.snapshot['native_kind'] != 'post'):
            raise ValueError('The native Post ticket belongs to another registered source')
        if native_ticket.status != 'PREPARED' or verified.snapshot['format'] != 'post-project':
            raise ValueError('MANAGED_SAVE_REQUIRED: save this raw state as an analysis project first')
        if any(getattr(args, key, None) for key in ('job_id', 'input_path', 'input_id', 'research_source',
                'measurement_result', 'curve_origin', 'report_image')) or any(value is not None for value in
                (_report_origin, _report_launch, _measurement_origin, _origin_launch)):
            raise ValueError('A native project ticket cannot share a job, result or origin launch')
        verify_snapshot_members(verified.snapshot, verified.member_paths)
        project = Path(native_ticket.derived['project_path']).resolve(strict=True)
        if project != (binding.working_root / 'project.json').resolve(strict=True):
            raise ValueError('The native Post project is outside its exact current working ticket')
        args.project = str(project)
    if client is None:
        if native_ticket is None or _local_context is None:
            raise ValueError('Standalone Post launch requires a verified native project and current local installation context')
        context = dict(_local_context)
        installed_repository = Path(__file__).resolve().parents[2]
        if Path(context['repo_root']).resolve(strict=True) != installed_repository:
            raise ValueError('Use the current local installation, not a repository path from the copied project')
    else:
        context = client.desktop_context()
    service_url = client.url if client is not None else None
    if getattr(args, 'curve_origin', None):
        from .post_curve_origin import launch_saved_measurement
        return launch_saved_measurement(client, args)
    launch_progress = _report_launch if _report_launch is not None else _origin_launch
    if getattr(args, 'report_image', None):
        from .report_image_origin import launch_saved_project
        return launch_saved_project(client, args)
    executable = _executable(context, 'paraview_executable', args.executable, not args.prepare_only)
    exit_plugin = os.environ.get('CAE_POST_EXIT_PLUGIN')
    exit_runtime = os.environ.get('CAE_POST_PARAVIEW_ROOT')
    if exit_plugin and exit_runtime and not args.prepare_only:
        expected = Path(exit_runtime) / 'bin' / 'paraview.exe'
        if not expected.is_file() or executable != expected.resolve(strict=True):
            raise ValueError('종료 보호에 지정한 ParaView와 선택한 실행 파일이 다릅니다. '
                             '같은 설치의 paraview.exe를 선택하거나 종료 보호 연결을 해제하세요.')
    home = Path(context['repo_root']) / 'apps/desktop_post'
    source_text = getattr(args, 'research_source', None)
    research_source = json.loads(source_text) if source_text is not None else None
    if research_source is not None and not args.job_id:
        raise ValueError('A stage source requires the exact parent job')
    measurement_source = None
    if getattr(args, 'measurement_result', None):
        payload = client.post_observation(json.loads(args.measurement_result))
        if not payload['source_available']:
            raise ValueError('Saved Post source is unavailable: ' + str(payload['source_error']))
        measurement_source = payload['origin']
        if _native_pid_alive(measurement_source.get('pid')) is not False:
            raise ValueError('Original Post closure is unconfirmed; reconnect its existing window')
        args.project = measurement_source['project']['path']
    if not (args.project or args.input_path or args.input_id or args.job_id):
        if args.prepare_only:
            raise ValueError('Specify a Post project or VTU/PVD result for headless preparation')
        selected = _choose_file('후처리 프로젝트 또는 결과 열기',
            '후처리 파일 (*.json *.vtu *.pvd);;저장한 프로젝트 (*.json);;해석 결과 (*.vtu *.pvd)')
        if selected.suffix.lower() == '.json' and selected.name not in ('contact-inspection.json','shell_inspection.json','beam_inspection.json'):
            args.project = str(selected)
        else:
            args.input_path = str(selected)
    if args.input_path and Path(args.input_path).name in ('contact-inspection.json','shell_inspection.json','beam_inspection.json'):
        if args.prepare_only:raise ValueError('준비 모드에서는 결과를 먼저 등록하고 --input-id로 지정하세요.')
        args.input_id=_register_post_inspection(client,Path(args.input_path).resolve(strict=True))
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
            source = Path(args.input_path).resolve(strict=True)
            command += [str(source), str(workspace)]
        with (folder / 'prepare.stdout.log').open('wb') as stdout, (folder / 'prepare.stderr.log').open('wb') as stderr:
            completed = subprocess.run(command, cwd=folder, stdout=stdout, stderr=stderr, check=False)
        if completed.returncode:
            raise RuntimeError('Native Post preparation failed; inspect ' + str(folder / 'prepare.stderr.log'))
        project = workspace / 'project.json'
    document = json.loads(project.read_text(encoding='utf-8-sig'))
    if not isinstance(document.get('workspace_file'), str) or not document['workspace_file']:
        raise ValueError('저장한 후처리 프로젝트를 선택하세요. 해석 결과 선언 파일은 결과로 등록해서 열어야 합니다.')
    state = (project.parent / document['workspace_file']).resolve(strict=True)
    if not state.is_file():
        raise ValueError('The selected Post project has no native workspace state')
    origin_job_id = None if native_ticket is not None else args.job_id or document.get('origin_job_id')
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
        CAE_POST_HOME=str(home), CAE_POST_PROJECT=str(project),
        CAE_POST_LAUNCH_DIR=str(folder),
        CAELAB_DESKTOP_PYTHON=context['python'], CAELAB_REPO_ROOT=context['repo_root'])
    # Prevent an inherited Post origin from attaching itself to an unrelated input.
    environment.pop('CAELAB_ORIGIN_JOB_ID', None)
    environment.pop('CAE_POST_MEASUREMENT', None)
    environment.pop('CAE_POST_REPORT_ORIGIN', None)
    environment.pop('CAE_POST_NATIVE_OPEN', None)
    environment.pop('CAE_POST_SERVICE_URL', None)
    if service_url:
        environment['CAE_POST_SERVICE_URL'] = service_url
    else:
        environment.pop('CAELAB_SERVICE_URL', None)
    if native_ticket is not None:
        environment['CAE_POST_NATIVE_OPEN'] = native_ticket.derived['launch_config']
    if _report_origin is not None:
        from .report_image_origin import prepare_native_environment
        prepare_native_environment(_report_origin, project, folder, environment)
    selection_origin = measurement_source if measurement_source is not None else _measurement_origin
    if selection_origin is not None:
        selection_path = folder / 'measurement.json'
        save_json(selection_path, {key: selection_origin[key] for key in (
            'kind', 'document_id', 'session_id', 'pid', 'project', 'workspace', 'object_ref',
            'revision', 'recipe_sha256', 'result_files_sha256', 'result_sha256')})
        environment['CAE_POST_MEASUREMENT'] = str(selection_path)
    if origin_job_id:
        environment['CAELAB_ORIGIN_JOB_ID'] = origin_job_id
    # Reopening a retained revision updates only the launch environment. Neither
    # runtime metadata nor startup logs are written into that saved revision.
    claim = marker = None
    if measurement_source is not None:
        reference = json.loads(args.measurement_result)
        existing = open_post_observation(client, reference, launch_closed=False)
        if existing is not None:
            return existing
        claim, marker = _post_launch_claim(client, measurement_source)
    try:
        if measurement_source is not None:
            existing = open_post_observation(client, reference, launch_closed=False)
            if existing is not None:
                actual_pid = existing.get('native_pid')
                if type(actual_pid) is int and actual_pid > 0:
                    save_json(marker, {'state': 'CONFIRMED', 'native_pid': actual_pid,
                                       'project_sha256': measurement_source['project']['sha256']})
                return existing
            save_json(marker, {'state': 'STARTING', 'project_sha256': measurement_source['project']['sha256']})
        if _report_origin is not None:
            from caelab.report_image import verify_origin
            verify_origin(_report_origin)
        if _measurement_origin is not None:
            from caelab.post_observation import verify_origin as verify_measurement
            verify_measurement(_measurement_origin)
            if Path(args.project).resolve() != Path(_measurement_origin['project']['path']).resolve():
                raise ValueError('원측정의 정확 저장 프로젝트가 아닙니다.')
        if launch_progress is not None:
            launch_progress['phase'] = 'SPAWNING'
        try:
            process = subprocess.Popen([str(executable), '--disable-registry', '--script=' + str(home / 'startup.py'),
                                        '--log=' + str(folder / 'native_gui.log')], cwd=folder, env=environment)
        except OSError:
            # Confirmed process-creation failure. Interrupts remain ambiguous.
            if launch_progress is not None:
                launch_progress['phase'] = 'NOT_CREATED'
            if marker is not None:
                marker.unlink(missing_ok=True)
            raise
        if launch_progress is not None:
            launch_progress.update(phase='CREATED', pid=process.pid)
        if marker is not None:
            save_json(marker, {'state': 'LAUNCH_REQUESTED', 'launcher_pid': process.pid,
                               'project_sha256': measurement_source['project']['sha256']})
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                documents = client.documents()['documents']
                matches = [doc for doc in documents if doc.get('kind') == 'post'
                    and doc.get('id') == measurement_source['document_id'] and doc.get('connected')]
                if len(matches) == 1:
                    actual_pid = matches[0].get('state', {}).get('pid')
                    if type(actual_pid) is int and actual_pid > 0:
                        save_json(marker, {'state': 'CONFIRMED', 'native_pid': actual_pid,
                            'project_sha256': measurement_source['project']['sha256']})
                        break
                time.sleep(.1)
            else:
                raise RuntimeError('Native Post launch is unconfirmed; inspect ' +
                    str(folder / 'native_startup.jsonl') + ' and reconnect it before retrying')
        return {'status':'LAUNCHED', 'pid':process.pid, 'project':str(project), 'state':str(state)}
    finally:
        if claim is not None:
            claim.unlock()


def _arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--service', default=os.getenv('CAELAB_SERVICE_URL'))
    sub = parser.add_subparsers(dest='tool', required=True)
    pre = sub.add_parser('pre', allow_abbrev=False)
    pre.add_argument('--source'); pre.add_argument('--assembly'); pre.add_argument('--source-label'); pre.add_argument('--gmsh')
    pre.add_argument('--input-id')
    post = sub.add_parser('post', allow_abbrev=False)
    choice = post.add_mutually_exclusive_group()
    choice.add_argument('--measurement-result')
    choice.add_argument('--report-image')
    choice.add_argument('--curve-origin')
    choice.add_argument('--project'); choice.add_argument('--input-path'); choice.add_argument('--input-id')
    origin = sub.add_parser('origin', allow_abbrev=False); origin.add_argument('--job-id', required=True)
    for name in sorted(TOOLS):
        tool = sub.add_parser(name, allow_abbrev=False)
        tool.add_argument('--job-id' if name == 'runner' else '--document-id')
    for tool in (pre, post):
        tool.add_argument('--executable'); tool.add_argument('--output'); tool.add_argument('--prepare-only', action='store_true')
        tool.add_argument('--native-project-open-id')
    post.add_argument('--job-id')
    post.add_argument('--research-source')
    return parser.parse_args(argv)


def main(argv=None):
    args = _arguments(argv)
    if not args.service:
        raise ValueError('Specify the existing local service URL')
    client = Client(args.service)
    if args.tool in {'pre', 'post'} and args.native_project_open_id:
        if args.prepare_only or any(getattr(args, key, None) for key in ('source', 'assembly', 'input_id',
                'input_path', 'project', 'job_id', 'research_source', 'measurement_result', 'curve_origin', 'report_image')):
            raise ValueError('저장본 열기 요청과 다른 입력을 함께 지정할 수 없습니다.')
        from .native_project_actions import NativeProjectActions
        from caelab.portable_project_native import resume_open_ticket, claim_open_launch
        view = client.native_project_open_ticket(args.native_project_open_id)
        if view['native_kind'] != args.tool:
            raise ValueError('선택한 저장본의 프로그램이 다릅니다.')
        if view['status'] == 'PREPARED':
            context, ticket = resume_open_ticket(view['launch_config'])
            claim_open_launch(context, args.native_project_open_id)
            (_pre if args.tool == 'pre' else _post)(client, args, _native_project_ticket=ticket)
        result = NativeProjectActions(client).check_open(args.native_project_open_id)
    elif args.tool == 'pre': result = _pre(client, args)
    elif args.tool == 'post': result = _post(client, args)
    elif args.tool == 'origin': result = open_origin(client, args.job_id)
    else:
        from importlib import import_module
        arguments = ['--service', client.url]
        identifier = args.job_id if args.tool == 'runner' else args.document_id
        if identifier:
            arguments += ['--job-id' if args.tool == 'runner' else '--document-id', check_id(identifier)]
        from PySide6.QtWidgets import QApplication
        from .appearance import apply_appearance
        application = QApplication.instance() or QApplication(sys.argv[:1])
        apply_appearance(application)
        return import_module('apps.research.' + args.tool + '_window').main(arguments)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print('Desktop launch failed: ' + str(error), file=sys.stderr)
        # Native preparation is also used from headless launch helpers.
        if '--prepare-only' not in sys.argv[1:]:
            from PySide6.QtWidgets import QApplication, QMessageBox
            application = QApplication.instance() or QApplication(sys.argv[:1])
            QMessageBox.critical(None, 'Desktop launch failed', str(error))
        raise SystemExit(1)
