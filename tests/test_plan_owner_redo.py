"""The embedded editor transports Undo/Redo to the same retained Plan owner."""
from copy import deepcopy

import pytest

from caelab.numerical_document import from_material_document
from caelab.plan_variables_api import PlanOwnerAdapter
from caelab.workbench import Workbench


def test_applied_plan_redo_and_stale_retry_preserve_exact_owner(tmp_path):
    wb = Workbench(tmp_path)
    try:
        material = wb.document_open(kind='material')
        plan = wb.document_open(kind='numerical', draft=from_material_document(material))
        adapter = PlanOwnerAdapter(wb, plan['id'])
        original = plan['draft']['variables'][0]['value']
        draft = deepcopy(plan['draft'])
        draft['variables'][0]['value'] = original * 1.5
        changed = wb.document_command(plan['id'], 'numerical.update', {'draft': draft},
            session_id=plan['session_id'], expected_generation=plan['generation'],
            command_id='Cupdate')['document']
        undone = adapter.undo(changed, command_id='Cundo')['document']
        assert undone['draft']['variables'][0]['value'] == original
        assert undone['can_redo']
        redone = adapter.redo(undone, command_id='Credo')['document']
        assert redone['draft']['variables'][0]['value'] == original * 1.5
        before = wb.document_read(plan['id'])
        with pytest.raises(ValueError, match='generation changed'):
            adapter.redo(undone, command_id='Cstaleredo')
        assert wb.document_read(plan['id']) == before
        assert wb.document_read(material['id'])['draft'] == material['draft']
        assert wb.manager.list() == []
    finally:
        wb.shutdown()
