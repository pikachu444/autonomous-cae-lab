"""Shared explicit question entry; opening a discussion never invokes a model."""
import uuid


def open_discussion(client, *, document=None, job_id=None):
    from .desktop import launch_tool
    session = document['session_id'] if document else client.desktop_context()['service_session_id']
    receipt = client.selection_discussion(session_id=session, command_id='C' + uuid.uuid4().hex,
        document_id=document['id'] if document else None,
        expected_generation=document['generation'] if document else None, job_id=job_id)
    if receipt.get('executed') is not False:
        raise ValueError('The discussion opener reported unexpected execution')
    return launch_tool(client, 'expert', document_id=receipt['document']['id'])
