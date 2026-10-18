"""Confirmed owner refusals remain distinct from lost adoption acknowledgements."""
from copy import deepcopy
from urllib.error import HTTPError

import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication

from caelab.workbench_client import WorkbenchHTTPError
from test_research_adoption_receipt_ui import app, LostReceipt, setup, wait, close


def begin(window, kind):
    # Exercise the receipt boundary directly; candidate-evidence admission is
    # independently exercised by the actual HTTP preview/confirmation workflow.
    wait(QApplication.instance(), lambda: not window._busy and not window._callbacks)
    return window._submit_adoption_receipt(kind, dict(document_id='Noriginal', job_id='Joriginal',
        candidate_id='Cactual', material_document_id='Moriginal', session_id='Sowner',
        expected_generation=4, command_id='Ccontrolled'))


def refusal(code=400):
    message = 'ValueError: Material changed after this Plan was bound; rebind explicitly before adoption'
    return WorkbenchHTTPError(HTTPError('http://127.0.0.1/adopt', code, 'Refused', {}, None),
                              b'{}', message)


def test_confirmed_http400_refusal_has_rebind_instruction_without_uncertain_retry(app, monkeypatch):
    client = LostReceipt('material')
    original = deepcopy(client.target)
    def reject(**request):
        client.requests.append(deepcopy(request))
        raise refusal()
    client.numerical_adopt = reject
    window = setup(client, monkeypatch)
    try:
        begin(window, 'material')
        wait(app, lambda: len(client.requests) == 1 and not window._busy)
        assert window._adoption_receipt is None
        assert window.retry_adoption_button.isHidden()
        assert '적용이 거절됐습니다' in window.message.text()
        assert '원 재료가 변경' in window.message.text()
        assert '다시 연결' in window.message.text()
        assert '아직 확인하지 못했습니다' not in window.message.text()
        assert 'HTTP 400' in window.message.toolTip()
        assert client.target == original and client.applications == 0
    finally:
        close(app, window, client)


@pytest.mark.parametrize('error', [refusal(500), ConnectionError('HTTP 400: acknowledgement lost')])
def test_transport_or_non400_error_keeps_uncertain_frozen_request(app, monkeypatch, error):
    client = LostReceipt('material')
    def reject(**request):
        client.requests.append(deepcopy(request))
        raise error
    client.numerical_adopt = reject
    window = setup(client, monkeypatch)
    try:
        begin(window, 'material')
        wait(app, lambda: len(client.requests) == 1 and not window._busy)
        assert window._adoption_receipt is not None
        assert window.retry_adoption_button.isEnabled()
        assert '아직 확인하지 못했습니다' in window.message.text()
    finally:
        close(app, window, client)


def test_http400_after_lost_ack_does_not_erase_uncertainty_about_first_application(app, monkeypatch):
    client = LostReceipt('material')
    window = setup(client, monkeypatch)
    try:
        begin(window, 'material')
        wait(app, lambda: len(client.requests) == 1 and not window._busy)
        pending = window._adoption_receipt
        frozen = deepcopy(client.requests[0])
        def reject(**request):
            client.requests.append(deepcopy(request))
            raise refusal()
        client.numerical_adopt = reject
        assert window.retry_adoption_receipt()
        wait(app, lambda: len(client.requests) == 2 and not window._busy)
        assert window._adoption_receipt is pending
        assert client.requests == [frozen, frozen] and client.applications == 1
        assert window.retry_adoption_button.isEnabled()
        assert '아직 확인하지 못했습니다' in window.message.text()
    finally:
        close(app, window, client)


@pytest.mark.parametrize('failure', ['lost', 'wrong_id'])
def test_exact_retry_still_recovers_applied_receipt_once(app, monkeypatch, failure):
    client = LostReceipt('material')
    client.first_failure = failure
    window = setup(client, monkeypatch)
    try:
        begin(window, 'material')
        wait(app, lambda: len(client.requests) == 1 and not window._busy)
        frozen = deepcopy(client.requests[0])
        assert window._adoption_receipt is not None
        assert window.retry_adoption_receipt()
        wait(app, lambda: window._adoption_receipt is None and not window._busy)
        assert client.requests == [frozen, frozen] and client.applications == 1
        assert window.retry_adoption_button.isHidden()
        assert '적용했습니다' in window.message.text()
    finally:
        close(app, window, client)
