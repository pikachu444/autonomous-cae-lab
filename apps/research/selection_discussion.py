"""Shared explicit question entry; opening a discussion never invokes a model."""
import uuid
from pathlib import Path


def open_file_discussion(client, paths, discussion_id=None, *, selection=None, workbench=None):
    """Snapshot explicit local evidence and open its owner without sending a question."""
    from caelab.assist.knowledge import TEXT_EXTENSIONS
    from .expert_sources import snapshot_source, source_collection
    from .desktop import launch_tool
    files = list(dict.fromkeys(str(Path(path).resolve(strict=True)) for path in paths))
    live_model = isinstance(selection, dict) and isinstance(selection.get('model_snapshot'), dict)
    if (not files and not live_model) or len(files) > 32 or any(not Path(path).is_file() for path in files):
        raise ValueError('토론할 파일을 1개에서 32개까지 선택하세요.')
    readable = [path for path in files if Path(path).suffix.lower() in TEXT_EXTENSIONS | {'.pdf'}]
    collection = source_collection(client, discussion_id) if readable else None
    references = [snapshot_source(client, path, collection=collection) for path in readable]
    scope = selection if selection is not None else ({'path': files[0]} if len(files) == 1 else
                                                   {'sources': [{'path': path} for path in files]})
    arguments = dict(session_id=client.desktop_context()['service_session_id'],
        command_id='C' + uuid.uuid4().hex, selection=scope, source_refs=references,
        discussion_id=discussion_id)
    if workbench is not None:
        arguments['workbench'] = workbench
    receipt = client.selection_discussion(**arguments)
    if receipt.get('executed') is not False:
        raise ValueError('The discussion opener reported unexpected execution')
    identifier = receipt['document']['id']
    return {**receipt, 'document_id': identifier,
            'launch': launch_tool(client, 'expert', document_id=identifier)}


def open_discussion(client, *, document=None, job_id=None, selection=None):
    from .desktop import launch_tool
    session = document['session_id'] if document else client.desktop_context()['service_session_id']
    arguments = dict(session_id=session, command_id='C' + uuid.uuid4().hex,
        document_id=document['id'] if document else None,
        expected_generation=document['generation'] if document else None, job_id=job_id)
    if selection is not None:
        arguments['selection'] = selection
    receipt = client.selection_discussion(**arguments)
    if receipt.get('executed') is not False:
        raise ValueError('The discussion opener reported unexpected execution')
    return launch_tool(client, 'expert', document_id=receipt['document']['id'])


def main(argv=None):
    import argparse
    import json
    import sys
    from caelab.workbench_client import Client
    parser = argparse.ArgumentParser(description='Open selected evidence in its research discussion')
    parser.add_argument('--service', required=True)
    selected = parser.add_mutually_exclusive_group()
    selected.add_argument('--selection')
    selected.add_argument('--selection-stdin', action='store_true')
    parser.add_argument('--workbench')
    parser.add_argument('--discussion')
    parser.add_argument('paths', nargs='*')
    options = parser.parse_args(argv)
    payload = options.selection
    if options.selection_stdin:
        raw = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            parser.error('selection exceeds 2 MiB')
        payload = raw.decode('utf-8')
    selection = json.loads(payload) if payload else None
    if selection is not None and not isinstance(selection, dict):
        parser.error('selection must be a JSON object')
    workbench = json.loads(options.workbench) if options.workbench else None
    if workbench is not None and not isinstance(workbench, dict):
        parser.error('workbench must be a JSON object')
    receipt = open_file_discussion(Client(options.service), options.paths,
        options.discussion, selection=selection, workbench=workbench)
    print(json.dumps({'document_id': receipt['document_id'], 'executed': False}))


if __name__ == '__main__':
    main()
