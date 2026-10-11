"""Saved method edit buffers and a usable native candidate curve, no solver."""
from copy import deepcopy

import pytest
pytest.importorskip('PySide6')
from apps.research.request_plan_window import RequestPlanWindow
from caelab.workbench import Workbench
from caelab.numerical_document import request_draft
from caelab.material_document import default_draft
from test_research_request_plan_ui import app, workbench, InProcessClient, wait
from test_candidate_native_curves_ui import RetainedNative, open_window, close


def switch(window, method):
    window.operation.setCurrentIndex(window.operation.findData(method))


def test_save_apply_undo_and_reopen_preserve_each_method_input_buffer(app, workbench):
    doc = workbench.document_open(kind='numerical', draft=request_draft({
        'purpose': 'Keep edited trial plans', 'operation': 'evaluate',
        'inputs': default_draft(), 'budget': {'evaluations': 4}}))
    window = RequestPlanWindow(InProcessClient(workbench), auto_open=False, poll_interval=0)
    window._opened(doc)
    try:
        switch(window, 'doe')
        window._edit_structure(lambda value: value.update(
            variables=[{'id':'E','unit':'MPa','value':1000.,'lower':800.,'upper':1600.}],
            responses=['stress_xx'], candidates=[{'values':{'E':1000.}}, {'values':{'E':1500.}}]))
        doe = deepcopy(window.edited_draft()['request']['inputs'])
        switch(window, 'fit')
        # An unfinished trial remains an editable invalid draft and is saved;
        # saving it must not destroy the independent, valid DOE coordinates.
        fit = deepcopy(window.edited_draft()['request']['inputs'])
        window.save_document()
        wait(app, lambda: not window._busy and not window.local_dirty)
        identifier = window.document['id']
        assert window.document['draft']['request']['inputs'] == fit
        assert window.document['draft']['method_inputs']['doe'] == doe
        assert window.document['diagnostics']
        assert not workbench.manager.list()
        switch(window, 'doe')
        assert window.edited_draft()['request']['inputs'] == doe
        window._edit_structure(lambda value: value.update(responses=['stress_xx', 'strain_xx']))
        window.apply_button.click()
        wait(app, lambda: not window._busy and not window.local_dirty)
        window.command('document.undo')
        wait(app, lambda: not window._busy)
        assert window.document['draft']['request']['operation'] == 'fit'
        switch(window, 'doe')
        assert window.edited_draft()['request']['inputs'] == doe
        window.save_document()
        wait(app, lambda: not window._busy and not window.local_dirty)
        saved = deepcopy(window.document['draft'])
        window._allow_close = True; window.close()
        assert workbench.shutdown()['joined']
        reopened = Workbench(workbench.workspace)
        other = RequestPlanWindow(InProcessClient(reopened), auto_open=False, poll_interval=0)
        try:
            other._opened(reopened.document_open(kind='numerical', document_id=identifier))
            assert other.edited_draft() == saved
            switch(other, 'fit')
            assert other.edited_draft()['request']['inputs'] == fit
            switch(other, 'doe')
            assert other.edited_draft()['request']['inputs'] == doe
            assert not reopened.manager.list()
        finally:
            other._allow_close = True; other.close(); reopened.shutdown()
    finally:
        wait(app, lambda: not window._busy)
        window._allow_close = True; window.close()


def test_long_retained_metadata_does_not_shrink_curve_and_is_still_accessible(app):
    client = RetainedNative()
    original = client.numerical_evaluation_result
    def read(*args, **kwargs):
        result = original(*args, **kwargs)
        for response in result.get('responses', {}).values():
            if isinstance(response, dict) and response.get('kind') == 'series':
                response['source']['diagnostic_details'] = 'retained file / exact bytes / details\n' * 250
        return result
    client.numerical_evaluation_result = read
    window = open_window(app, client)
    window.show()
    try:
        window.curve_read.click()
        wait(app, lambda: not window._busy and window._curve_result is not None)
        app.processEvents()
        assert window.curve_metadata.isHidden()
        assert window.curve_canvas.height() > window.curve_values.height()
        assert window.curve_canvas.height() > window.curve_detail.height() * 3
        assert 'retained file / exact bytes' in window.curve_metadata.toPlainText()
        window.curve_metadata_toggle.click(); app.processEvents()
        assert window.curve_metadata.isVisible()
        window.curve_metadata_toggle.click(); app.processEvents()
        assert window.curve_metadata.isHidden()
        window.native_channel.setCurrentIndex(1)
        assert not window.curve_metadata.toPlainText()
    finally:
        close(app, window, client)
