"""Native quality rows linked to transient element display in the main view."""
import uuid

from .mesh_element_view import dispatch, get_view, selected_element_ids
from .mesh_quality_compare import _source_relationship


def make_dialog(W, C, owner, mesh, parent=None):
    existing = getattr(owner, '_mesh_element_dialog', None)
    if existing is not None:
        if existing.mesh is mesh:
            return existing
        existing.close()
    class Dialog(W.QDialog):
        def __init__(self):
            super().__init__(parent)
            self.owner, self.mesh = owner, mesh
            self._doc, self._session = owner.doc, owner.session_id
            self._quality, self._selected, self._offset, self._model_selection = None, [], 0, []
            self._populating = False
            self.view = get_view(owner, mesh)
            self.setWindowTitle('메시 품질 확인')
            self.resize(880, 620)
            self.setMinimumSize(650, 460)
            font = self.font(); font.setFamily('Malgun Gothic'); font.setPointSize(max(9, font.pointSize())); self.setFont(font)
            layout = W.QVBoxLayout(self)
            self.title = W.QLabel('선택 메시: ' + mesh.Label); self.title.setWordWrap(True)
            layout.addWidget(self.title)
            self.source_status = W.QLabel(); self.source_status.setWordWrap(True); layout.addWidget(self.source_status)
            row = W.QHBoxLayout()
            for label, callback in [('품질 다시 읽기', self.refresh), ('모델 선택 읽기', self.read_selection)]:
                button = W.QPushButton(label); button.clicked.connect(lambda checked=False, fn=callback: self._action(fn)); row.addWidget(button)
            row.addStretch(); layout.addLayout(row)
            self.summary = W.QLabel(); self.summary.setWordWrap(True); layout.addWidget(self.summary)
            self.table = W.QTableWidget(0, 5)
            self.table.setObjectName('meshElementQuality')
            self.table.setHorizontalHeaderLabels(['요소 번호', '종류', '최소 표본 J [mm³]', '최소 정규화 J', '확인 사항'])
            self.table.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
            self.table.setSelectionBehavior(W.QAbstractItemView.SelectRows)
            self.table.setSelectionMode(W.QAbstractItemView.ExtendedSelection)
            self.table.setAlternatingRowColors(True)
            self.table.horizontalHeader().setSectionResizeMode(W.QHeaderView.Stretch)
            self.table.verticalHeader().hide()
            self.table.itemSelectionChanged.connect(self._row_selected)
            layout.addWidget(self.table, 1)
            pages = W.QHBoxLayout()
            self.previous = W.QPushButton('이전 요소'); self.previous.clicked.connect(lambda: self._page(-200)); pages.addWidget(self.previous)
            self.page_status = W.QLabel(); pages.addWidget(self.page_status, 1)
            self.next = W.QPushButton('다음 요소'); self.next.clicked.connect(lambda: self._page(200)); pages.addWidget(self.next)
            layout.addLayout(pages)
            actions = W.QHBoxLayout(); self.view_buttons = []
            for label, mode in [('선택 요소 표시', 'show'), ('선택 요소만 보기', 'isolate'), ('선택 요소 확대', 'fit')]:
                button = W.QPushButton(label); button.clicked.connect(lambda checked=False, mode=mode: self._action(lambda: self.display(mode)))
                actions.addWidget(button); self.view_buttons.append(button)
            self.reset = W.QPushButton('격리 해제'); self.reset.clicked.connect(self.restore); actions.addWidget(self.reset)
            layout.addLayout(actions)
            self.status = W.QLabel('표의 요소 행 또는 원 모델의 요소 면을 선택하세요.'); self.status.setWordWrap(True); layout.addWidget(self.status)
            note = W.QLabel('사면체의 표본 Jacobian을 확인합니다. 기준 통과가 전체 요소의 품질 보증은 아닙니다. 격리 중에는 표에서 요소를 선택하며, 원 형상과 메시의 저장 내용은 바꾸지 않습니다.')
            note.setWordWrap(True); layout.addWidget(note)
            footer = W.QHBoxLayout(); footer.addStretch()
            close = W.QPushButton('닫기'); close.clicked.connect(self.close); footer.addWidget(close); layout.addLayout(footer)
            self.timer = C.QTimer(self); self.timer.setInterval(500); self.timer.timeout.connect(self.poll)
            self.refresh(); self.timer.start()

        def _context(self):
            owner.assert_thread()
            if owner.closed or owner.doc is not self._doc or owner.session_id != self._session or self._doc.getObject(mesh.Name) is not mesh:
                raise ValueError('문서 또는 메시가 바뀌었습니다. 현재 문서에서 품질 창을 다시 여세요.')

        def _action(self, callback):
            try:
                self._context(); callback()
                return True
            except Exception as error:
                text = str(error)
                self.status.setText(text if not text.isascii() else '요소를 표시하지 못했습니다. 현재 문서와 메시를 확인한 뒤 다시 읽으세요.')
                self.status.setToolTip(text)
                return False

        def refresh(self):
            self._action(self._read_quality)

        def _read_quality(self):
            self.view = get_view(owner, mesh)
            self.view.restore()
            self._quality, self._selected = None, []
            owner.refresh()
            response = owner.dispatch({'command_id': 'C' + uuid.uuid4().hex, 'document_id': owner.document_id,
                'session_id': self._session, 'expected_generation': owner.generation,
                'operation': 'pre.fem.mesh_quality', 'arguments': {'offset': self._offset, 'limit': 200},
                'target': {'object_id': mesh.Name}})
            if response.get('status') != 'COMPLETED':
                self.table.setRowCount(0); self._sync_actions()
                raise ValueError('품질을 읽지 못했습니다. 현재 문서와 메시를 확인한 뒤 다시 읽으세요.')
            self._quality = response['result']
            self._populating = True
            try:
                self.table.clearSelection(); self.table.setRowCount(len(self._quality['rows']))
                reasons = {'INVALID_OR_UNSUPPORTED_CONNECTIVITY': '절점 연결 확인', 'UNSUPPORTED_RUN_ELEMENT_TYPE': '실행 미지원 종류',
                    'NONFINITE_NATIVE_COORDINATES': '좌표 확인', 'DEGENERATE_COORDINATE_SCALE': '겹친 절점 확인',
                    'JACOBIAN_AT_OR_BELOW_1E_10_MM3': 'Jacobian 기준 미달', 'NORMALIZED_JACOBIAN_SINGULAR': '정규화 Jacobian 특이'}
                for i, row in enumerate(self._quality['rows']):
                    values = [row['element_id'], row['element_type'], row.get('minimum_sampled_jacobian_mm3'),
                              row.get('minimum_scaled_sampled_jacobian'), ', '.join(reasons.get(e, '확인 필요') for e in row['errors']) or '표본 기준 통과']
                    for j, value in enumerate(values):
                        text = '미확인' if value is None else format(value, '.6g') if isinstance(value, float) else str(value)
                        item = W.QTableWidgetItem(text); item.setToolTip(str(value)); self.table.setItem(i,j,item)
            finally:
                self._populating = False
            self.summary.setText('전체 요소 ' + str(self._quality['total_elements']) + '개 / 기준 미달 또는 확인 필요 ' + str(self._quality['bad_element_count']) + '개')
            self.page_status.setText(str(self._offset + 1 if self._quality['rows'] else 0) + '–' + str(self._offset + len(self._quality['rows'])) + '번째 요소')
            self.source_status.setText(_source_relationship(owner, mesh)['message'])
            self.status.setText('표의 요소 행 또는 원 모델의 요소 면을 선택하세요.')
            self._sync_actions()

        def _sync_actions(self):
            usable = bool(self._quality and self._quality.get('mesh_sha256') and self._selected)
            for button in self.view_buttons: button.setEnabled(usable)
            self.reset.setEnabled(self.view.active)
            self.previous.setEnabled(self._offset > 0)
            self.next.setEnabled(bool(self._quality and self._offset + 200 < self._quality['total_elements']))

        def _row_selected(self):
            if self._populating or not self._quality: return
            self._selected = [self._quality['rows'][index.row()]['element_id'] for index in self.table.selectionModel().selectedRows()]
            self.view = get_view(owner, mesh)
            if self.view.active:
                self.view.restore()
            if self._selected and self._quality.get('mesh_sha256'):
                if not self._action(lambda: self.view.select(self._selected, self._quality['mesh_sha256'])):
                    self._sync_actions(); return
            self._model_selection = list(self._selected)
            self.status.setText('선택 요소 ' + ', '.join(str(i) for i in self._selected) if self._selected else '표 또는 모델에서 요소를 선택하세요.')
            if not self._selected: self.view.restore()
            self._sync_actions()

        def _page(self, delta):
            self._offset = max(0, self._offset + delta); self.refresh()

        def read_selection(self):
            self._context()
            if not self._quality:
                raise ValueError('품질을 먼저 다시 읽으세요.')
            ids = selected_element_ids(owner, mesh)
            self._model_selection = ids
            if not ids:
                self.table.clearSelection(); self.status.setText('모델의 메시 요소 면을 선택하세요. 메시 전체 선택은 요소 선택과 구별합니다.'); return
            volumes = sorted(mesh.FemMesh.Volumes)
            offset = volumes.index(ids[0]) // 200 * 200
            if offset != self._offset:
                self._offset = offset; self._read_quality()
            self._populating = True
            try:
                self.table.clearSelection()
                for i, row in enumerate(self._quality['rows']):
                    if row['element_id'] in ids:
                        self.table.selectionModel().select(self.table.model().index(i,0), C.QItemSelectionModel.Select | C.QItemSelectionModel.Rows)
                self._selected = ids
            finally:
                self._populating = False
            self.status.setText('모델에서 선택한 요소 ' + ', '.join(str(i) for i in ids))
            self._sync_actions()

        def display(self, mode):
            if not self._quality: raise ValueError('품질을 먼저 읽으세요.')
            self.view = get_view(owner, mesh)
            result = dispatch(owner, {'mode': mode, 'element_ids': self._selected, 'mesh_sha256': self._quality.get('mesh_sha256')}, {'object_id': mesh.Name})
            self._model_selection = list(self._selected)
            self.status.setText('선택한 실제 요소 ' + ', '.join(str(i) for i in result['element_ids']) + ('만 격리했습니다.' if result['isolated'] else '를 모델에 표시했습니다.'))
            self._sync_actions()

        def restore(self):
            self.view.restore(); self._model_selection = selected_element_ids(owner, mesh) if not owner.closed else []
            self.status.setText('원 모델의 보기와 선택을 복원했습니다.'); self._sync_actions()

        def poll(self):
            try:
                self._context()
            except Exception:
                self.timer.stop(); self.view.close(); self._quality = None; self._selected = []; self._sync_actions()
                self.status.setText('원 문서 또는 메시가 닫혔습니다. 현재 문서에서 품질 창을 다시 여세요.')
                return
            if self.view._closed:
                self.reset.setEnabled(False)
                self.status.setText('다른 메시의 요소 보기로 전환했습니다. 이 메시를 보려면 요소를 선택해 다시 표시하세요.')
                return
            if not self.view.check_current():
                self._quality = None; self._selected = []; self.table.setRowCount(0)
                self.status.setText('문서 또는 메시가 바뀌어 요소 표시를 해제했습니다. 품질을 다시 읽으세요.'); self._sync_actions(); return
            try:
                self._context()
                ids = selected_element_ids(owner, mesh)
                if ids != self._model_selection and not self.view.active:
                    self.read_selection()
            except Exception:
                self.timer.stop(); self.view.close(); self._quality = None; self._selected = []; self._sync_actions()
                self.status.setText('원 문서 또는 메시가 닫혔습니다. 현재 문서에서 품질 창을 다시 여세요.')

        def closeEvent(self, event):
            self.timer.stop(); self.view.close()
            if getattr(owner, '_mesh_element_dialog', None) is self:
                owner._mesh_element_dialog = None
            super().closeEvent(event)

    owner._mesh_element_dialog = Dialog()
    return owner._mesh_element_dialog
