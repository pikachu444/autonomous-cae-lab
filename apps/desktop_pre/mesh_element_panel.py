"""Native quality rows linked to transient element display in the main view."""
import importlib
import uuid

from .mesh_element_view import dispatch, get_view, selected_element_ids
from .mesh_quality_compare import _source_relationship


def make_dialog(W, C, owner, mesh, parent=None):
    G = importlib.import_module(W.__package__ + '.QtGui')
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
            self.setMinimumSize(600, 460)
            self.setObjectName('meshElementDialog')
            font = self.font(); font.setFamily('Malgun Gothic'); font.setPointSize(max(9, font.pointSize())); self.setFont(font)
            self.setStyleSheet('''
                QDialog#meshElementDialog { background: palette(window); }
                QLabel#meshHeading { font-size: 15px; font-weight: bold; }
                QLabel#qualitySummary { font-weight: bold; }
                QLabel#meshSourceWarning { background: #fff3e3; color: #754518; padding: 6px; }
                QTableWidget#meshElementQuality { background: palette(base); alternate-background-color: #f4f7fa;
                    gridline-color: #dbe2e8; selection-background-color: #d7e8f8; selection-color: #153c60; }
                QHeaderView::section { padding: 7px 6px; border: none; border-bottom: 1px solid #bdcad6;
                    background: #edf2f7; color: #253b52; }
                QPushButton#isolateElements { background: #245f9e; color: white; border: 1px solid #245f9e;
                    border-radius: 3px; padding: 5px 14px; }
                QPushButton#isolateElements:hover { background: #1d528c; }
                QPushButton#isolateElements:pressed { background: #143f6d; }
                QPushButton#isolateElements:focus { border: 2px solid #102f4f; padding: 4px 13px; }
                QPushButton#isolateElements:disabled { background: #e9eef4; color: #778697; border-color: #c8d2dc; }
            ''')
            layout = W.QVBoxLayout(self)
            layout.setContentsMargins(16, 14, 16, 12); layout.setSpacing(10)
            heading = W.QHBoxLayout()
            self.title = W.QLabel(mesh.Label); self.title.setObjectName('meshHeading')
            self.title.setTextFormat(C.Qt.PlainText); self.title.setWordWrap(True)
            heading.addWidget(self.title, 1)
            self.refresh_button = W.QPushButton('다시 읽기'); self.refresh_button.clicked.connect(self.refresh)
            self.refresh_button.setAutoDefault(False)
            heading.addWidget(self.refresh_button); layout.addLayout(heading)
            self.summary = W.QLabel(); self.summary.setObjectName('qualitySummary')
            self.summary.setWordWrap(True); layout.addWidget(self.summary)
            self.source_status = W.QLabel(); self.source_status.setWordWrap(True); layout.addWidget(self.source_status)
            row = W.QHBoxLayout()
            row.addWidget(W.QLabel('요소 품질'), 1)
            self.model_selection_button = W.QPushButton('모델 선택 읽기')
            self.model_selection_button.setAutoDefault(False)
            self.model_selection_button.clicked.connect(lambda: self._action(self.read_selection))
            row.addWidget(self.model_selection_button); layout.addLayout(row)
            self.table = W.QTableWidget(0, 5)
            self.table.setObjectName('meshElementQuality')
            self.table.setHorizontalHeaderLabels(['요소 번호', '종류', '최소 표본 J [mm³]', '최소 정규화 J', '확인 사항'])
            self.table.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
            self.table.setSelectionBehavior(W.QAbstractItemView.SelectRows)
            self.table.setSelectionMode(W.QAbstractItemView.ExtendedSelection)
            self.table.setAlternatingRowColors(True)
            self.table.setShowGrid(False); self.table.setWordWrap(True)
            self.table.setTextElideMode(C.Qt.ElideNone)
            header = self.table.horizontalHeader()
            for column in range(4): header.setSectionResizeMode(column, W.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(4, W.QHeaderView.Stretch)
            self.table.verticalHeader().setSectionResizeMode(W.QHeaderView.ResizeToContents)
            self.table.verticalHeader().hide()
            self.table.itemSelectionChanged.connect(self._row_selected)
            self.contents = W.QStackedWidget(); self.contents.addWidget(self.table)
            self.empty = W.QLabel('표시할 입체 요소가 없습니다.\n현재 문서의 메시를 확인하세요.')
            self.empty.setAlignment(C.Qt.AlignCenter); self.empty.setWordWrap(True)
            self.contents.addWidget(self.empty); layout.addWidget(self.contents, 1)
            pages = W.QHBoxLayout()
            self.previous = W.QPushButton('이전'); self.previous.clicked.connect(lambda: self._page(-200)); pages.addWidget(self.previous)
            self.page_status = W.QLabel(); pages.addWidget(self.page_status, 1)
            self.next = W.QPushButton('다음'); self.next.clicked.connect(lambda: self._page(200)); pages.addWidget(self.next)
            layout.addLayout(pages)
            actions = W.QHBoxLayout(); self.view_buttons = []
            for label, mode, tooltip in [('표시', 'show', '선택 요소를 원 모델 위에 표시'),
                                         ('격리', 'isolate', '선택 요소만 보기'), ('확대', 'fit', '선택 요소의 기하에 화면 맞춤')]:
                button = W.QPushButton(label); button.clicked.connect(lambda checked=False, mode=mode: self._action(lambda: self.display(mode)))
                button.setAutoDefault(False)
                button.setToolTip(tooltip); button.setAccessibleName(tooltip)
                if mode == 'isolate': button.setObjectName('isolateElements')
                actions.addWidget(button); self.view_buttons.append(button)
            self.reset = W.QPushButton('복원'); self.reset.setToolTip('원 모델의 보기와 선택 복원')
            self.reset.setAutoDefault(False)
            self.reset.clicked.connect(self.restore); actions.addWidget(self.reset)
            actions.addStretch()
            layout.addLayout(actions)
            self.status = W.QLabel('표의 요소 행 또는 원 모델의 요소 면을 선택하세요.'); self.status.setWordWrap(True); layout.addWidget(self.status)
            self.status.setTextFormat(C.Qt.PlainText)
            self.criteria = W.QToolButton(); self.criteria.setText('표본 품질 기준')
            self.criteria.setToolButtonStyle(C.Qt.ToolButtonTextBesideIcon); self.criteria.setArrowType(C.Qt.RightArrow)
            self.criteria.setCheckable(True)
            self.criteria_detail = W.QLabel(); self.criteria_detail.setWordWrap(True)
            self.criteria_detail.setTextFormat(C.Qt.PlainText); self.criteria_detail.hide()
            self.criteria.toggled.connect(self._show_criteria)
            footer = W.QHBoxLayout(); footer.addWidget(self.criteria); footer.addStretch()
            close = W.QPushButton('닫기'); close.clicked.connect(self.close); footer.addWidget(close); layout.addLayout(footer)
            close.setAutoDefault(False)
            layout.addWidget(self.criteria_detail)
            self.timer = C.QTimer(self); self.timer.setInterval(500); self.timer.timeout.connect(self.poll)
            self.refresh(); self.timer.start()

        def _show_criteria(self, shown):
            self.criteria_detail.setVisible(shown)
            self.criteria.setArrowType(C.Qt.DownArrow if shown else C.Qt.RightArrow)

        def _selection_text(self, ids):
            text = ', '.join(str(i) for i in ids[:5])
            return text if len(ids) <= 5 else str(len(ids)) + '개 (' + text + ' 등)'

        def _empty_quality(self, message):
            self.empty.setText(message); self.table.setRowCount(0)
            self.contents.setCurrentWidget(self.empty)
            self.summary.clear(); self.source_status.clear(); self.page_status.clear(); self.criteria_detail.clear()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if hasattr(self, 'table'): self.table.resizeRowsToContents()

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
                if not self._quality:
                    self._empty_quality('품질을 읽지 못했습니다.\n현재 문서와 메시를 확인한 뒤 다시 읽으세요.')
                    self._sync_actions()
                return False

        def refresh(self):
            self._action(self._read_quality)

        def _read_quality(self):
            self.view = get_view(owner, mesh)
            self.view.restore()
            self._quality, self._selected = None, []
            self.summary.clear(); self.source_status.clear(); self.criteria_detail.clear(); self.page_status.clear()
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
                        if j in (0, 2, 3): item.setTextAlignment(C.Qt.AlignRight | C.Qt.AlignVCenter)
                        if row['errors']:
                            item.setBackground(G.QColor('#fff1ef'))
                            if j == 4:
                                item.setForeground(G.QColor('#9c3128'))
                                item.setIcon(self.style().standardIcon(W.QStyle.SP_MessageBoxWarning))
            finally:
                self._populating = False
            self.contents.setCurrentWidget(self.table if self._quality['rows'] else self.empty)
            self.empty.setText('표시할 입체 요소가 없습니다.\n현재 문서의 메시를 확인하세요.')
            self.table.resizeRowsToContents()
            self.summary.setText('전체 ' + str(self._quality['total_elements']) + '개    확인 필요 ' + str(self._quality['bad_element_count']) + '개')
            self.page_status.setText((str(self._offset + 1) + '–' + str(self._offset + len(self._quality['rows'])) + '번째 요소') if self._quality['rows'] else '요소 없음')
            source = _source_relationship(owner, mesh)
            self.source_status.setText('현재 형상과 연결됨' if source['state'] == 'MATCH' else
                '현재 형상과 연결을 확인하지 못한 메시입니다. 품질은 읽을 수 있지만 현재 형상 해석에는 다시 메시를 생성하세요.')
            self.source_status.setToolTip(source['message'])
            self.source_status.setObjectName('meshSourceWarning' if source['state'] != 'MATCH' else 'meshSourceMatch')
            self.source_status.style().unpolish(self.source_status); self.source_status.style().polish(self.source_status)
            self.source_status.setTextFormat(C.Qt.PlainText)
            gates = self._quality.get('gates') or {}
            criteria = []
            if 'absolute_jacobian_floor_mm3' in gates:
                criteria.append('최소 표본 J > ' + format(gates['absolute_jacobian_floor_mm3'], '.6g') + ' mm³')
            if 'normalized_jacobian_floor' in gates:
                criteria.append('최소 정규화 J > ' + format(gates['normalized_jacobian_floor'], '.6g'))
            self.criteria_detail.setText((' / '.join(criteria) + '\n' if criteria else '') +
                '음수도 원값 그대로 표시합니다. C3D10은 네 적분점 표본의 검사이며, 요소 전체의 품질 보증이나 해석 적합성 승인이 아닙니다.\n'
                '요소 표시는 C3D4·C3D10 사면체를 지원합니다. 격리 중에는 표에서 선택하며 원 형상과 메시를 변경하지 않습니다.')
            self.status.setText('요소를 선택하면 표시·격리·확대할 수 있습니다.' if self._quality['rows'] else '입체 요소가 없어 선택할 수 없습니다.')
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
            self.status.setText('선택 요소 ' + self._selection_text(self._selected) if self._selected else '표 또는 모델에서 요소를 선택하세요.')
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
            self.status.setText('모델에서 선택한 요소 ' + self._selection_text(ids))
            self._sync_actions()

        def display(self, mode):
            if not self._quality: raise ValueError('품질을 먼저 읽으세요.')
            self.view = get_view(owner, mesh)
            result = dispatch(owner, {'mode': mode, 'element_ids': self._selected, 'mesh_sha256': self._quality.get('mesh_sha256')}, {'object_id': mesh.Name})
            self._model_selection = list(self._selected)
            self.status.setText('선택 요소 ' + self._selection_text(result['element_ids']) + (' 격리됨' if result['isolated'] else ' 표시됨'))
            self._sync_actions()

        def restore(self):
            self.view.restore(); self._model_selection = selected_element_ids(owner, mesh) if not owner.closed else []
            self.status.setText('원 모델의 보기와 선택을 복원했습니다.'); self._sync_actions()

        def poll(self):
            try:
                self._context()
            except Exception:
                self.timer.stop(); self.view.close(); self._quality = None; self._selected = []; self._sync_actions()
                self._empty_quality('원 문서 또는 메시가 닫혔습니다.\n현재 문서에서 품질 창을 다시 여세요.')
                self.status.setText('원 문서 또는 메시가 닫혔습니다. 현재 문서에서 품질 창을 다시 여세요.')
                return
            if self.view._closed:
                self.reset.setEnabled(False)
                self.status.setText('다른 메시의 요소 보기로 전환했습니다. 이 메시를 보려면 요소를 선택해 다시 표시하세요.')
                return
            if not self.view.check_current():
                self._quality = None; self._selected = []; self.table.setRowCount(0)
                self._empty_quality('메시가 바뀌었습니다.\n다시 읽기로 현재 요소를 확인하세요.')
                self.status.setText('문서 또는 메시가 바뀌어 요소 표시를 해제했습니다. 품질을 다시 읽으세요.'); self._sync_actions(); return
            try:
                self._context()
                ids = selected_element_ids(owner, mesh)
                if ids != self._model_selection and not self.view.active:
                    self.read_selection()
            except Exception:
                self.timer.stop(); self.view.close(); self._quality = None; self._selected = []; self._sync_actions()
                self._empty_quality('원 문서 또는 메시가 닫혔습니다.\n현재 문서에서 품질 창을 다시 여세요.')
                self.status.setText('원 문서 또는 메시가 닫혔습니다. 현재 문서에서 품질 창을 다시 여세요.')

        def closeEvent(self, event):
            self.timer.stop(); self.view.close()
            if getattr(owner, '_mesh_element_dialog', None) is self:
                owner._mesh_element_dialog = None
            super().closeEvent(event)

    owner._mesh_element_dialog = Dialog()
    return owner._mesh_element_dialog
