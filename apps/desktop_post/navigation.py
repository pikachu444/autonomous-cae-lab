"""Start the primary-Python navigator without loading its Qt into ParaView."""
import os
from pathlib import Path
import subprocess


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
