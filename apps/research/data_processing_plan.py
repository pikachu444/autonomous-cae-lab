"""Open retained processed observations in Numerical's public trial editor."""
from copy import deepcopy
from PySide6.QtCore import QTimer
from shiboken6 import isValid


def open_processing_plan(data_window, result, response_name):
    from .numerical_window import NumericalWindow
    from .data_material_document_dialog import DataMaterialDocumentDialog
    if not all(callable(getattr(NumericalWindow, method, None)) for method in
               ('stage_processed_trial', 'can_stage_processed_trial', 'processed_trial_stage_pending')):
        data_window.message.setText('현재 Numerical 창에서 처리 결과의 시험 연결을 지원하지 않습니다.')
        return False
    record = result.get('diagnostics', {}).get('processing_record')
    response = result.get('responses', {}).get(response_name)
    if not record or not response or response.get('measure') not in ('infinitesimal_Cauchy', 'first_Piola'):
        data_window.message.setText('보존한 응력 처리 결과를 선택하세요.'); return False
    source = {**deepcopy(record['source']), 'processing_revision': record['id'], 'response': response_name}
    frozen_result = deepcopy(result)

    def open_plan(document):
        target = NumericalWindow(data_window.client, document_id=document['id'])
        data_window._processed_plan_windows.append(target)
        target.show(); target.raise_()
        def stage():
            if not isValid(target) or getattr(target, '_closed', False): return
            if target.can_stage_processed_trial():
                if target.document['id'] != document['id']:
                    target.message.setText('열린 계획이 바뀌었습니다. 처리 결과를 다시 선택하세요.'); return
                try:
                    target.stage_processed_trial(deepcopy(source), deepcopy(frozen_result))
                except (ValueError, TypeError, KeyError) as error:
                    target.message.setText(str(error))
                return
            # Retained provenance can be large. The owner's read lifecycle,
            # rather than a second GUI timeout, decides when review is ready.
            if target.processed_trial_stage_pending(): QTimer.singleShot(50, stage)
        QTimer.singleShot(0, stage)

    def choose(payload):
        documents = payload['documents']
        def eligible(document):
            draft = document.get('draft', {})
            if not isinstance(draft, dict): return False
            reference = draft.get('material', {})
            material = reference.get('draft', {}) if isinstance(reference, dict) else {}
            return (document.get('kind') == 'numerical' and draft.get('mode') == 'fit'
                    and isinstance(material, dict) and material.get('backend') == 'material.felupe')
        plans = [document for document in documents if eligible(document)]
        dialog = DataMaterialDocumentDialog(plans, kind='numerical', parent=data_window)
        if dialog.exec() != dialog.DialogCode.Accepted: return
        if not dialog.create_requested:
            open_plan(dialog.selected_document); return
        materials = [document for document in documents if document.get('kind') == 'material'
                     and isinstance(document.get('draft'), dict)
                     and document['draft'].get('backend') == 'material.felupe']
        material_dialog = DataMaterialDocumentDialog(materials, kind='material', parent=data_window)
        material_dialog.setWindowTitle('피팅할 재료 선택')
        if material_dialog.exec() != material_dialog.DialogCode.Accepted: return
        material = material_dialog.selected_document
        from caelab.numerical_document import from_material_document
        data_window._call(lambda: data_window.client.document_open(kind='numerical',
            title=material['title'] + ' 피팅', draft=from_material_document(material)), open_plan)
    return data_window._call(data_window.client.documents, choose)
