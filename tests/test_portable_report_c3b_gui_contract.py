"""CONTROLLED Python method boundaries, explicitly NOT an actual Qt test.

Compile the exact changed ReportWindow methods, without importing a substitute
product GUI. Controlled objects inspect command/late-reply behavior only. Actual
menu, focus, resizing, keyboard and Qt lifecycle require Windows/PySide6 tests.
"""
import ast
from copy import deepcopy
from enum import IntFlag
from pathlib import Path
from types import SimpleNamespace

import pytest


class Buttons(IntFlag):
    Save = 1
    Cancel = 2


class Question:
    StandardButton = Buttons
    answer = Buttons.Cancel
    calls = []

    @classmethod
    def question(cls, *args):
        cls.calls.append(args)
        return cls.answer


def method(name, **variables):
    path = Path(__file__).resolve().parents[1] / 'apps/research/report_window.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'ReportWindow')
    node = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == name)
    code = compile(ast.fix_missing_locations(ast.Module(body=[deepcopy(node)], type_ignores=[])), str(path), 'exec')
    scope = {'QMessageBox': Question, 'deepcopy': deepcopy, **variables}
    exec(code, scope)
    return scope[name]


def host():
    calls = []
    doc = {'id': 'Bcurrent', 'draft': {'title': '보고서', 'sections': [{'id': 'Efirst'}]}}
    result = SimpleNamespace(_busy=False, _pending=None, document=doc, draft=deepcopy(doc['draft']),
        _edit_buffers={}, calls=calls, message=SimpleNamespace(setText=lambda value: calls.append(('message', value))),
        edit_title=lambda: calls.append(('title',)), remember_editor=lambda: calls.append(('remember',)),
        sections=SimpleNamespace(setCurrentRow=lambda index: calls.append(('select', index)), currentRow=lambda: 0),
        edit_section=lambda: calls.append(('editor',)), save_document=lambda: calls.append(('save',)) or 'EXPLICIT_SAVE',
        read_assets=lambda: calls.append(('read',)), assets={}, _source_windows=[])
    return result


@pytest.mark.parametrize('state', ['busy', 'pending', 'missing'])
def test_copy_does_not_collect_or_commit_while_pending(state):
    current = host()
    if state == 'busy': current._busy = True
    if state == 'pending': current._pending = ('ORIGINAL_COMMAND_SAME_ID',)
    if state == 'missing': current.document = None
    old = deepcopy(current._pending)
    current._edit_buffers = {'Efirst': {'text': '아직 작성 중 {'}}
    assert method('prepare_portable_copy')(current) is False
    assert current._pending == old and current._edit_buffers['Efirst']['text'] == '아직 작성 중 {'
    assert all(row[0] == 'message' for row in current.calls)


def test_copy_routes_unapplied_description_without_apply_save_or_clearing():
    current = host(); current._edit_buffers = {'Efirst': {'text': '미완성 설명 {'}}
    before = deepcopy(current._edit_buffers)
    assert method('prepare_portable_copy')(current) is False
    assert current._edit_buffers == before
    assert ('select', 0) in current.calls and ('editor',) in current.calls
    assert ('save',) not in current.calls


@pytest.mark.parametrize('answer', [Buttons.Save, Buttons.Cancel])
def test_title_body_save_requires_explicit_choice_and_does_not_start_copy(answer):
    current = host(); current.draft['title'] = '새 제목 미적용'
    Question.answer = answer; Question.calls = []
    result = method('prepare_portable_copy')(current)
    assert Question.calls and Question.calls[-1][-1] == Buttons.Cancel
    assert current.draft['title'] == '새 제목 미적용'
    assert current.document['draft']['title'] == '보고서'
    assert bool(('save',) in current.calls) == (answer == Buttons.Save)
    assert result == ('EXPLICIT_SAVE' if answer == Buttons.Save else False)


@pytest.mark.parametrize('cached', [{}, {'navigation_reference': None, 'retained_preview_only': True}])
def test_copied_source_cannot_open_origin_before_current_read(cached):
    current = host(); current.draft['sections'][0]['asset'] = {'id': 'Aold', 'reference': {'kind': 'post_image'}}
    current.document['portable_report_assets'] = {'Aold': {'old': 'witness'}}
    current.assets['Aold'] = cached
    method('open_source')(current)
    assert ('read',) in current.calls  # No import of native/Qt module occurred.


def test_frozen_only_image_has_no_native_opener_authority():
    current = host(); current.draft['sections'][0]['asset'] = {'id': 'Aold', 'reference': {'kind': 'post_image'}}
    current.document['portable_report_assets'] = {'Aold': {}}
    current.assets['Aold'] = {'navigation_reference': None}
    method('open_source')(current)
    assert current.calls and all(row[0] == 'message' for row in current.calls)


def test_existing_late_save_reply_keeps_new_text_and_does_not_auto_copy():
    current = host()
    old = {'id': 'Bcurrent', 'draft': deepcopy(current.draft), 'session_id': 'Scurrent', 'generation': 3}
    submitted = deepcopy(current.draft)
    submitted['title'] = '보낸 제목'
    current._pending = (old, 'report.update', {'draft': submitted}, 'CsameOriginal', submitted,
                        lambda: current.calls.append(('auto_after',)))
    current.draft['title'] = '응답 기다리는 동안 입력한 제목'
    current.client = SimpleNamespace(document_command=lambda *a, **kw: current.calls.append(('sent', kw)) or
        {'document': {**old, 'draft': submitted, 'generation': 4}})
    current._call = lambda request, accepted: accepted(request())
    current._undo, current._redo = ['uncommitted'], []
    timer = SimpleNamespace(singleShot=lambda *a: current.calls.append(('timer',)))
    method('retry', QTimer=timer)(current)
    assert current.draft['title'] == '응답 기다리는 동안 입력한 제목'
    assert current.document['draft']['title'] == '보낸 제목'
    sent = next(row[1] for row in current.calls if row[0] == 'sent')
    assert sent['command_id'] == 'CsameOriginal' and sent['session_id'] == 'Scurrent'
    assert current._pending is None and current._undo == ['uncommitted']
    assert not any(row[0] in ('auto_after', 'timer') for row in current.calls)
