"""Small native-menu integration on the existing editors/ConnectionWindow.

No editor buffer is read, committed or harvested by a copy selection. Only the
explicit Save choice calls the editor's existing save/CAS/late-edit callbacks.
Qt is imported at the action boundary, keeping policy helpers directly testable.
"""
from copy import deepcopy


def local_rounds(document):
    from caelab.portable_research_owner import live_rounds
    return live_rounds(document or {})


def copy_allowed(window):
    return bool(getattr(window, 'document', None) and not getattr(window, '_busy', False)
                and not getattr(window, 'conflict', False) and not getattr(window, '_closed', False))


def prepare_copy(window):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout
    if not copy_allowed(window):
        window.message.setText('진행 중인 응답 또는 다른 창의 변경을 먼저 확인하세요. 현재 질문·판단은 유지됩니다.')
        return False
    owner_key = (window.document['id'], window.document['session_id'])
    dialog = QDialog(window)
    dialog.setWindowTitle('작업 사본 만들기')
    dialog.resize(540, 220)
    layout = QVBoxLayout(dialog)
    label = QLabel('포함할 내용을 선택하세요.\n편집한 내용을 포함하려면 먼저 저장하세요.')
    label.setWordWrap(True); layout.addWidget(label)
    save = QPushButton('저장 후 계속')
    kept = QPushButton('저장된 내용만')
    selected = []
    save.clicked.connect(lambda: (selected.append('save'), dialog.accept()))
    kept.clicked.connect(lambda: (selected.append('kept'), dialog.accept()))
    layout.addWidget(save); layout.addWidget(kept)
    cancel = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
    cancel.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
    cancel.rejected.connect(dialog.reject); layout.addWidget(cancel)
    if dialog.exec() != QDialog.DialogCode.Accepted or not selected:
        return False
    def open_selection():
        if not copy_allowed(window) or (window.document['id'], window.document['session_id']) != owner_key:
            return False
        from .connection_window import ConnectionWindow
        child = ConnectionWindow(window.client, document_id=window.document['id'],
            copy_draft_policy='saved_only' if selected[0] == 'kept' else 'acknowledged')
        child.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        children = getattr(window, '_portable_research_children', None)
        if children is None:
            children = window._portable_research_children = []
        children.append(child)
        child.destroyed.connect(lambda: children.remove(child) if child in children else None)
        child.show()
        window.message.setText('포함 목록에서 다른 연구 문서와 문헌을 확인하세요. 미적용 화면 내용은 복사하지 않았습니다.')
        return child
    # The existing callback runs only after durable Save, same owner and no late edit.
    return window.save_document(after=open_selection) if selected[0] == 'save' else open_selection()


def close_children(window):
    for child in list(getattr(window, '_portable_research_children', [])):
        child.close()  # Only windows created by this helper; no process/global close.


def install(window, menu, kind):
    action = menu.addAction('작업 사본 만들기…')
    action.triggered.connect(lambda: prepare_copy(window))
    window.portable_research_action = action
    if kind == 'expert':
        next_action = menu.addAction('현재 요청의 다음 역할 응답 받기')
        def advance():
            if copy_allowed(window):
                window._progress_command('expert.advance', after=window.refresh_document)
        next_action.triggered.connect(advance)
        window.portable_next_response_action = next_action


def append_knowledge_rows(table, inspection):
    from PySide6.QtWidgets import QTableWidgetItem
    for source in inspection.get('knowledge', []):
        row = table.rowCount(); table.insertRow(row)
        has_full = any(not ref.get('locator') for ref in source['references'])
        label = '개정 ' + str(source['revision']) + (' / 전체' if has_full else ' / 선택 구간')
        for column, text in enumerate((source['title'], label, str(sum(f['bytes'] for f in source['files'])))):
            table.setItem(row, column, QTableWidgetItem(text))
    for source in inspection.get('literature', []):
        row = table.rowCount(); table.insertRow(row)
        label = {'abstract_only': '공개 문헌 초록', 'metadata_only': '공개 문헌 서지정보',
                 'fulltext': '공개 문헌 추출 원문'}.get(source['read_status'], '공개 문헌 보관본')
        for column, text in enumerate((source['title'], label, str(sum(f['bytes'] for f in source['files'])))):
            item = QTableWidgetItem(text);item.setToolTip(text);table.setItem(row, column, item)


def navigation(document, reference):
    from caelab.storage import canonical_hash
    for row in (document or {}).get('portable_reference_navigation', []):
        if canonical_hash(row['reference']) == canonical_hash(reference):
            if row['navigation_reference'] is None:
                raise ValueError('현재 사본에서 이 원 근거를 열 수 없습니다. 원 보관소로 자동 연결하지 않습니다.')
            return deepcopy(row['navigation_reference'])
    return deepcopy(reference)


def source_locator_text(locator):
    place = [str(locator['section'])] if locator.get('section') else []
    if 'page' in locator: place.append('쪽 ' + str(locator['page']))
    if 'line_start' in locator: place.append('줄 ' + str(locator['line_start']) + '–' + str(locator.get('line_end', locator['line_start'])))
    return ' / '.join(place)


def source_description(payload):
    """Bibliography/location/limits in the existing reading pane, not raw JSON."""
    source = payload['source']; details = payload.get('source_metadata', {})
    metadata = details.get('metadata', {})
    heading = [', '.join(str(v) for v in metadata[key]) if isinstance(metadata[key], list) else str(metadata[key])
               for key in ('author', 'authors', 'year', 'source', 'doi', 'url') if metadata.get(key)]
    heading.append('문헌 개정 ' + str(source['revision']))
    paragraphs = [' · '.join(heading)]
    for row in source.get('segments', []):
        paragraphs.append(source_locator_text(row.get('locator', {})) + '\n' + row.get('text', ''))
        if row.get('limitations'): paragraphs.append('추출 한계: ' + '; '.join(row['limitations']))
    for failure in source.get('failed_segments', []):
        paragraphs.append('추출 실패: ' + str(failure.get('reason', failure)))
    return '\n\n'.join(paragraphs)
