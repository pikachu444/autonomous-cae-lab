"""Duplicate document names retain exact row selection without visible IDs."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication, QDialogButtonBox
from apps.research.data_material_document_dialog import DataMaterialDocumentDialog


def test_duplicate_names_select_exact_owner_and_filter_blocks_hidden_selection():
    app = QApplication.instance() or QApplication([])
    documents = [{'id': identifier, 'title': '인장 시험', 'kind': 'material',
                  'draft': {'settings': {'model': 'linear_elastic', 'stress_unit': 'MPa',
                                        'parameters': {'E': E, 'nu': .25}}}}
                 for identifier, E in (('Mfirst', 1000), ('Msecond', 2000))]
    dialog = DataMaterialDocumentDialog(documents, kind='material')
    dialog.table.selectRow(1)
    assert all(document['id'] not in dialog.table.item(row, column).text()
               for document in documents for row in range(2) for column in range(3))
    assert 'ν=0.25 [1]' in dialog.table.item(1, 1).text()
    dialog.search.setText('1000')
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Open).isEnabled()
    dialog._choose()
    assert dialog.selected_document is None
    dialog.search.clear()
    dialog.table.selectRow(1)
    dialog._choose()
    assert dialog.selected_document['id'] == 'Msecond'
    dialog.close(); app.processEvents()


@pytest.mark.parametrize('kind,draft', [('material', {'settings': None}), ('data', {'mapping': None})])
def test_invalid_preserved_document_can_still_be_selected(kind, draft):
    app = QApplication.instance() or QApplication([])
    dialog = DataMaterialDocumentDialog([{'id': 'Mexample' if kind == 'material' else 'Texample',
        'title': '편집 중', 'kind': kind, 'draft': draft, 'dirty': True}], kind=kind)
    dialog.table.selectRow(0)
    dialog._choose()
    assert dialog.selected_document['draft'] == draft
    assert dialog.table.item(0, 2).text() == '저장하지 않은 변경'
    dialog.close(); app.processEvents()
