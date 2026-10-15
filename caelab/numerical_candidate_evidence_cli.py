"""Explicit C03 commands through the existing loopback document-command service.

This client never starts a controller, solver, provider, search or detail_eval.
A request includes the exact owner session/generation and command ID, so a lost
reply can be retried with the same file instead of silently rebasing an action.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .numerical_candidate_evidence import EVIDENCE_COMMANDS
from .storage import check_id
from .workbench_client import Client


def execute_request(client, request: dict):
    required = {'document_id', 'operation', 'arguments', 'session_id', 'expected_generation', 'command_id'}
    if not isinstance(request, dict) or set(request) != required:
        raise ValueError('Supply the exact document_id/operation/arguments/session_id/expected_generation/command_id')
    if request['operation'] not in EVIDENCE_COMMANDS | {'numerical.evidence.adopt'}:
        raise ValueError('This client accepts only evidence read/capture/compare/adoption commands')
    if not isinstance(request['arguments'], dict) or type(request['expected_generation']) is not int:
        raise ValueError('Arguments must be an object and expected_generation an integer')
    if request['expected_generation'] < 0:
        raise ValueError('expected_generation cannot be negative')
    for key in ('document_id', 'session_id', 'command_id'):
        check_id(request[key])
    if not request['document_id'].startswith('N'):
        raise ValueError('Select the Numerical owner of this evidence')
    return client.document_command(request['document_id'], request['operation'], request['arguments'],
        session_id=request['session_id'], expected_generation=request['expected_generation'],
        command_id=request['command_id'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', required=True, help='Existing local Workbench URL')
    parser.add_argument('--request', type=Path, required=True, help='Exact JSON command; UTF-8 or UTF-8 BOM')
    parser.add_argument('--output', type=Path, help='Write the verified service response, never a guessed success')
    args = parser.parse_args(argv)
    try:
        if args.request.stat().st_size > 4 * 1024 * 1024:
            raise ValueError('Evidence command exceeds 4 MiB; pass references, not result arrays')
        request = json.loads(args.request.read_text(encoding='utf-8-sig'))
        response = execute_request(Client(args.service), request)
        encoded = json.dumps(response, ensure_ascii=False, allow_nan=False, indent=2) + '\n'
        if args.output:
            args.output.write_text(encoded, encoding='utf-8')
        else:
            sys.stdout.write(encoded)
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        sys.stderr.write(type(error).__name__ + ': ' + str(error) + '\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
