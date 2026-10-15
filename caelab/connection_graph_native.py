"""Read registered native owner descriptors without expiring or activating them.

These are last-reported descriptors, not verified FCStd/PVSM files. No host
credential, arbitrary native filename, VTK proxy ID or fixture tool key becomes
an inferred relationship. Only Pre's actual project.links contract is followed.
"""
from copy import deepcopy
import time

from .storage import check_id


def native_snapshots(workbench):
    native = workbench.native_commands
    result = {}
    with native._lock:
        for host in native._hosts.values():
            for identifier, value in host['documents'].items():
                # Only explicit document fields are returned; no host_token or
                # registration nonce enters the graph, even diagnostic data.
                doc = deepcopy(value)
                doc.update(connected=host['connected'], host_id=host['host_id'],
                           session_id=host['session_id'],
                           report_fresh=bool(host['connected'] and time.monotonic() - host['_seen'] <= native.timeout))
                previous = result.get(identifier)
                if previous is None or doc['report_fresh']:
                    result[identifier] = doc
    return result


def recorded_jobs(workbench, document):
    if document['kind'] != 'pre':
        return
    for index, link in enumerate(document.get('project', {}).get('links', [])):
        job_id, error, current = None, None, None
        try:
            job_id = check_id(link['job_id'])
            origin = link['origin']
            if origin.get('kind') != 'pre' or origin.get('document_id') != document['id']:
                raise ValueError('저장한 계산의 원문서가 선택한 Pre 문서와 다릅니다.')
            current = workbench.manager.status(job_id)
            if current['arguments'].get('origin') != origin or current['operation'] != link['operation']:
                raise ValueError('계산 기록의 원입력/작업이 저장 연결과 다릅니다.')
            state = current['state']
        except (KeyError, ValueError, OSError, TypeError) as failure:
            state, error = 'BROKEN', str(failure)
        yield {'key': 'native-job/' + document['id'] + '/' + (job_id or str(index)),
               'job_id': job_id, 'status': state, 'record': deepcopy(link),
               'error': error, 'current_job': deepcopy(current)}
