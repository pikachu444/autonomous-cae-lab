"""Start the primary-Python navigator without loading its Qt into ParaView."""
import os
from pathlib import Path
import subprocess
import json


def discuss_selection(document, selection, *, environment=None):
    """Open a question with the displayed native selection in the primary runtime."""
    environment = dict(os.environ if environment is None else environment)
    from caelab.workbench_client import Client
    service = environment.get('CAE_POST_SERVICE_URL') or document.get('service_url')
    Client(service)
    python = Path(environment.get('CAELAB_DESKTOP_PYTHON') or document.get('desktop_python') or '')
    repository = Path(environment.get('CAELAB_REPO_ROOT') or document.get('repo_root') or '')
    if not python.is_file() or not repository.is_dir():
        raise ValueError('Workbench에서 결과를 열어 토론에 연결하세요.')
    for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'LD_LIBRARY_PATH'):
        environment.pop(key, None)
    command = [str(python), '-m', 'apps.research.selection_discussion', '--service', service,
               '--selection', json.dumps(selection, ensure_ascii=False, allow_nan=False)]
    discussion = document.get('discussion_id') or environment.get('CAELAB_DISCUSSION_ID')
    if discussion:
        command.extend(['--discussion', discussion])
    command.append(selection['path'])
    process = subprocess.Popen(command, cwd=repository, env=environment)
    return {'status': 'DISCUSSION_LAUNCH_REQUESTED', 'pid': process.pid}


def open_analysis_editor(document, document_id, session_id, *, environment=None):
    """Open editing controls for this exact live native owner, never another viewer."""
    environment=dict(os.environ if environment is None else environment)
    from caelab.storage import check_id
    from caelab.workbench_client import Client
    document_id,session_id=check_id(document_id),check_id(session_id)
    service=environment.get('CAE_POST_SERVICE_URL') or document.get('service_url')
    Client(service)
    python=Path(environment.get('CAELAB_DESKTOP_PYTHON') or document.get('desktop_python') or '')
    repository=Path(environment.get('CAELAB_REPO_ROOT') or document.get('repo_root') or '')
    if not python.is_file() or not repository.is_dir():
        raise ValueError('Open this project with the CAE Post launcher to connect the Research controls')
    for key in ('PYTHONHOME','PYTHONPATH','QT_PLUGIN_PATH','QML2_IMPORT_PATH','LD_LIBRARY_PATH'):
        environment.pop(key,None)
    process=subprocess.Popen([str(python),'-m','apps.research.post_window','--service',service,
        '--document-id',document_id,'--session-id',session_id],cwd=repository,env=environment)
    return {'status':'CONTROLS_LAUNCH_REQUESTED','document_id':document_id,'session_id':session_id,'pid':process.pid}


def return_to_design(document, *, environment=None):
    environment = dict(os.environ if environment is None else environment)
    job_id = environment.get('CAELAB_ORIGIN_JOB_ID') or document.get('origin_job_id')
    if not job_id:
        raise ValueError('This independent result has no recorded design job. Its analysis remains open.')
    from caelab.storage import check_id
    from caelab.workbench_client import Client
    check_id(job_id)
    service = environment.get('CAE_POST_SERVICE_URL') or document.get('service_url')
    Client(service)  # Validate loopback scope; no network/native access on this thread.
    python = Path(environment.get('CAELAB_DESKTOP_PYTHON') or document.get('desktop_python') or '')
    repository = Path(environment.get('CAELAB_REPO_ROOT') or document.get('repo_root') or '')
    if not python.is_file() or not repository.is_dir():
        raise ValueError('Open this saved Post project through the CAE Post launcher to reconnect its desktop tools.')
    for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'LD_LIBRARY_PATH'):
        environment.pop(key, None)
    process = subprocess.Popen([str(python), '-m', 'apps.research.desktop', '--service', service,
                                'origin', '--job-id', job_id], cwd=repository, env=environment)
    return {'status': 'NAVIGATION_REQUESTED', 'job_id': job_id, 'pid': process.pid}
