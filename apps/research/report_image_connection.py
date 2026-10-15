"""Small, testable client coordinator. Existing native broker owns execution.

No Qt or provider dependency. A dispatched request is immutable; reconnect reads
that command ID only. User cancellation abandons report adoption, not a claim
that synchronous SaveScreenshot stopped.
"""
from copy import deepcopy
import uuid

from caelab.report_image import validate_content


def candidates(documents):
    rows = []
    for document in documents:
        if document.get('kind') != 'post' or not document.get('connected'):
            continue
        for obj in document.get('state', {}).get('analysis', {}).get('objects', []):
            position = obj.get('position', -1)
            history = obj.get('history', [])
            if (obj.get('kind') not in ('filter', 'comparison') or type(position) is not int
                    or not 0 <= position < len(history) or not history[position].get('view_name')):
                continue
            if obj.get('kind') == 'comparison' and history[position]['recipe'].get('version') == 3:
                continue
            rows.append({'document': deepcopy(document), 'object': deepcopy(obj),
                         'revision': history[position]['id'],
                         'label': document.get('title', 'Post') + ' / ' +
                                  str(obj.get('title') or obj.get('label') or
                                      history[position]['recipe'].get('filter') or '공간 비교')})
    return rows


class CaptureSession:
    """One candidate/command/result; the report is edited only by the caller."""
    def __init__(self, client, report_id, candidate):
        document = candidate['document']
        self.client, self.report_id = client, report_id
        self.request = {'document_id': document['id'], 'session_id': document['session_id'],
            'expected_generation': document['generation'], 'command_id': 'C' + uuid.uuid4().hex,
            'operation': 'post.export', 'arguments': {'object_ref': candidate['object']['id'],
                'format': 'png', 'report_snapshot': True}}
        self.revision = candidate['revision']
        self.stage, self.abandoned = 'NEW', False
        self.command = self.binding = self.asset = None

    def _open(self):
        if self.abandoned:
            raise ValueError('보고서 적용을 취소한 요청입니다.')

    def submit(self):
        self._open()
        if self.stage != 'NEW':
            raise ValueError('이미 전달한 요청입니다. 같은 명령의 상태만 확인하세요.')
        request = deepcopy(self.request)
        remote = self.client.document_read(request['document_id'])
        if (not remote.get('connected') or remote.get('session_id') != request['session_id']
                or remote.get('generation') != request['expected_generation']):
            raise ValueError('Post 원문서가 변경되거나 연결이 끊겼습니다. 명시적으로 목록을 다시 읽으세요.')
        rows = candidates([remote])
        if not any(row['object']['id'] == request['arguments']['object_ref'] and row['revision'] == self.revision
                   for row in rows):
            raise ValueError('선택한 적용 결과가 달라졌습니다.')
        self._open()
        self.stage = 'SUBMITTED_UNCONFIRMED'  # Set before transport; never auto-submit on error.
        command = self.client.document_command(request.pop('document_id'), request.pop('operation'),
            request.pop('arguments'), **request)
        self._open()
        return self._record(command)

    def _record(self, command):
        self._open()
        for key in ('command_id', 'document_id', 'session_id', 'operation', 'arguments'):
            if command.get(key) != self.request[key]:
                raise ValueError('다른 요청의 응답입니다. 현재 보고서는 유지됩니다.')
        self.command = deepcopy(command)
        self.stage = command['state']
        return command

    def poll(self):
        self._open()
        if self.stage == 'NEW':
            raise ValueError('먼저 캡처를 요청하세요.')
        return self._record(self.client.command_status(self.request['command_id']))

    def retain(self):
        self._open()
        if self.stage != 'SUCCEEDED':
            raise ValueError('실패/미확인 캡처는 보고서에 적용하지 않습니다.')
        binding = self.client.report_capture(self.report_id,
            {'kind': 'post_image_command', 'command_id': self.request['command_id']})
        self._open()
        receipt = self.client.report_content(self.report_id, [binding])
        rows = receipt['assets']
        if len(rows) != 1 or rows[0].get('id') != binding['id'] or rows[0].get('source_status') != 'AVAILABLE':
            raise ValueError('새 이미지의 정확한 출처를 확인하지 못했습니다. 이전 섹션은 유지됩니다.')
        validate_content(rows[0]['content'], binding['reference'])
        self._open()
        self.binding, self.asset = deepcopy(binding), deepcopy(rows[0])
        return self.binding, self.asset

    def abandon(self):
        self.abandoned = True
        self.binding = self.asset = None
        # Do not send a physical stop claim. Native broker only supports queued cancellation.
