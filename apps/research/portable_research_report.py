"""Current Report literature read/export gates; existing renderer and atomic write.

A missing image can retain its previously verified preview (R1). A denied
knowledge scope cannot. No new store, authority service or exporter is created.
"""
from copy import deepcopy
from caelab.storage import canonical_hash
from caelab.report_image import merge_read_assets


def scope_denied(rows):
    return any(row.get('snapshot_status') == 'SCOPE_REQUIRED' for row in rows)


def apply_read_assets(window, rows):
    window.assets = merge_read_assets(window.assets, rows)
    if scope_denied(rows):
        # Even an invalid authored draft must not leave the old sensitive page
        # visible when compose fails. This never deletes the original A bytes.
        window._page = None
        window._page_stale = True
        window.preview.setVisible(False)
    window.render()
    if window._page is not None and not getattr(window, '_page_stale', False):
        window.preview.setVisible(True)


def export_selection(document, draft):
    chosen = {row['asset']['id']: deepcopy(row['asset']) for row in draft.get('sections', [])
              if row.get('include') and row.get('asset')}
    return {'document_id': document['id'], 'session_id': document['session_id'],
        'generation': document['generation'], 'draft_sha256': canonical_hash(draft),
        'bindings': list(chosen.values())}


def unchanged(window, selection):
    doc = window.document or {}
    return (not getattr(window, '_closed', False)
        and (doc.get('id'), doc.get('session_id'), doc.get('generation')) ==
            (selection['document_id'], selection['session_id'], selection['generation'])
        and canonical_hash(window.draft) == selection['draft_sha256'])


def read_export_sources(client, selection):
    """Real existing owner/current source read, usable from the existing worker."""
    current = client.document_read(selection['document_id'])
    if (current['id'], current['session_id'], current['generation']) != (
            selection['document_id'], selection['session_id'], selection['generation']):
        raise ValueError('다른 창 또는 새 세션에서 보고서가 변경되었습니다. 현재 편집과 이전 출력은 유지합니다.')
    receipt = client.report_content(selection['document_id'], deepcopy(selection['bindings']))
    expected = {b['id'] for b in selection['bindings']}
    actual = [row.get('id') for row in receipt['assets']]
    if receipt.get('document_id') != selection['document_id'] or set(actual) != expected or len(actual) != len(expected):
        raise ValueError('현재 보고서의 선택 자료를 모두 재확인하지 못했습니다.')
    return receipt


def publish_checked(window, selection, reviewed, current, write):
    """No write on late edits, denied scope or changed review. Not a permission cache."""
    if not unchanged(window, selection):
        window.message.setText('확인 중 보고서 편집이 바뀌었습니다. 현재 편집과 이전 출력은 유지합니다.')
        return False
    apply_read_assets(window, current['assets'])
    if scope_denied(current['assets']):
        window.message.setText('현재 문헌 읽기 권한이 부족하여 내보내지 않았습니다. 질문·본문과 원 보존본은 유지합니다.')
        return False
    if canonical_hash(reviewed) != canonical_hash(current):
        window.message.setText('내보내기 확인 이후 원자료 상태가 바뀌었습니다. 새로 확인한 뒤 다시 내보내세요.')
        return False
    if window._page is None or getattr(window, '_page_stale', False):
        raise ValueError('페이지 오류를 먼저 고치세요. 이전 출력은 유지합니다.')
    write()
    return True


def export_checked(window, format):
    """Keep the native file dialog, page renderer, async client and atomic export."""
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from .report_pages import atomic_export, pdf_document, markdown
    if format not in {'pdf', 'md'} or not window.document or window._pending:
        window.message.setText('진행 중인 저장과 출력 형식을 먼저 확인하세요.')
        return False
    selection = export_selection(window.document, window.draft)
    path, _ = QFileDialog.getSaveFileName(window, '보고서 내보내기', '보고서.' + format,
        'PDF (*.pdf)' if format == 'pdf' else 'Markdown (*.md)')
    if not path or not unchanged(window, selection):
        return False
    def read():
        return read_export_sources(window.client, selection)
    def reviewed(receipt):
        if not unchanged(window, selection):
            window.message.setText('확인 중 편집이 바뀌었습니다. 현재 편집과 이전 출력은 유지합니다.')
            return
        apply_read_assets(window, receipt['assets'])
        if scope_denied(receipt['assets']):
            window.message.setText('현재 문헌 읽기 권한이 부족하여 내보내지 않았습니다. 원 보존본은 유지합니다.')
            return
        if any(a.get('source_status') != 'AVAILABLE' for a in receipt['assets']):
            if QMessageBox.question(window, '원자료 확인 필요',
                '확인되지 않은 섹션에 표시를 남겨 초안으로 내보낼까요?',
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Ok:
                return
        def commit(current):
            try:
                def write():
                    if format == 'pdf':
                        atomic_export(path, lambda p: pdf_document(window._page, p))
                    else:
                        atomic_export(path, lambda p: p.write_text(markdown(window.draft, window.assets), encoding='utf-8'))
                if publish_checked(window, selection, receipt, current, write):
                    window.message.setText('보고서를 내보냈습니다.')
            except Exception as error:
                window.message.setText('내보내지 못했습니다. 이전 파일은 유지됩니다. ' + str(error))
        # A modal choice is not a lasting source grant. This second read checks
        # the same selected sources after all dialogs, without dispatch or save.
        window._call(read, commit)
    return window._call(read, reviewed)
