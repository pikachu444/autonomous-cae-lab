"""Native Qt read-only mesh comparison; bindings and the open owner are injected."""
import uuid


def make_dialog(QtWidgets, QtCore, owner, mesh, parent=None):
    """Return a modeless dialog; caller retains it and calls show().

    Uses only pre.fem.mesh_quality and pre.fem.mesh_compare owner commands.
    The bound document and native mesh are never replaced by a newer selection.
    """
    class Dialog(QtWidgets.QDialog):
        def __init__(self):
            super().__init__(parent)
            self.owner, self.mesh = owner, mesh
            self._doc, self._session = owner.doc, owner.session_id
            self._mesh_hash, self._result, self._generation = None, None, owner.generation
            self.setWindowTitle('메시 품질 비교')
            self.setModal(False)
            self.resize(850, 600)
            self.setMinimumSize(620, 460)
            font = self.font()
            font.setFamily('Malgun Gothic')
            font.setPointSize(max(9, font.pointSize()))
            self.setFont(font)
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(10)
            self.title = QtWidgets.QLabel('현재 선택 메시: ' + mesh.Label)
            self.title.setWordWrap(True)
            self.title.setStyleSheet('font-weight: 600;')
            layout.addWidget(self.title)
            row = QtWidgets.QHBoxLayout()
            row.addWidget(QtWidgets.QLabel('이전 메시'))
            self.history = QtWidgets.QComboBox()
            self.history.setMinimumWidth(200)
            row.addWidget(self.history, 1)
            self.refresh_button = QtWidgets.QPushButton('다시 조회')
            row.addWidget(self.refresh_button)
            layout.addLayout(row)
            self.source_status = QtWidgets.QLabel()
            self.source_status.setWordWrap(True)
            layout.addWidget(self.source_status)
            self.status = QtWidgets.QLabel()
            self.status.setWordWrap(True)
            layout.addWidget(self.status)
            self.tabs = QtWidgets.QTabWidget()
            self.summary = self._table(['지표', '이전', '현재', '변화'])
            self.summary.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
            self.tabs.addTab(self.summary, '비교 값')
            self.distributions = {}
            for key, label in [('absolute_jacobian_mm3', 'Jacobian 분포 [mm³]'),
                               ('normalized_jacobian', '정규화 Jacobian 분포')]:
                page = QtWidgets.QWidget()
                page_layout = QtWidgets.QVBoxLayout(page)
                split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
                tables = []
                for heading in ('이전 메시', '현재 메시'):
                    section = QtWidgets.QWidget()
                    section_layout = QtWidgets.QVBoxLayout(section)
                    section_layout.setContentsMargins(0, 0, 0, 0)
                    section_layout.addWidget(QtWidgets.QLabel(heading))
                    table = self._table(['구간 시작', '구간 끝', '요소 수'])
                    section_layout.addWidget(table)
                    split.addWidget(section)
                    tables.append(table)
                page_layout.addWidget(split, 1)
                note = QtWidgets.QLabel()
                note.setWordWrap(True)
                page_layout.addWidget(note)
                self.distributions[key] = (*tables, note)
                self.tabs.addTab(page, label)
            layout.addWidget(self.tabs, 1)
            scope = QtWidgets.QLabel('각 요소의 최소 표본값을 모은 최소·최대와 분포입니다. Jacobian 부호를 유지하며, 요소 전체의 품질 보증은 아닙니다.')
            scope.setWordWrap(True)
            layout.addWidget(scope)
            footer = QtWidgets.QHBoxLayout()
            footer.addStretch()
            close = QtWidgets.QPushButton('닫기')
            close.clicked.connect(self.close)
            footer.addWidget(close)
            layout.addLayout(footer)
            self.history.currentIndexChanged.connect(self.compare)
            self.refresh_button.clicked.connect(self.refresh)
            self.timer = QtCore.QTimer(self)
            self.timer.setInterval(500)
            self.timer.timeout.connect(self._check_changes)
            self.refresh()
            self.timer.start()

        def _table(self, headings):
            table = QtWidgets.QTableWidget(0, len(headings))
            table.setHorizontalHeaderLabels(headings)
            table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            table.setAlternatingRowColors(True)
            table.verticalHeader().hide()
            table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
            return table

        def _context(self):
            self.owner.assert_thread()
            if (self.owner.closed or self.owner.doc is not self._doc or
                    self.owner.session_id != self._session):
                raise ValueError('문서가 닫히거나 바뀌었습니다. 현재 문서에서 비교 창을 다시 여세요.')
            if self._doc.getObject(self.mesh.Name) is not self.mesh:
                raise ValueError('선택한 메시가 삭제되거나 바뀌었습니다. 메시를 다시 선택하세요.')

        def _call(self, operation, arguments):
            self._context()
            self.owner.refresh()
            response = self.owner.dispatch({'command_id': 'C' + uuid.uuid4().hex,
                'document_id': self.owner.document_id, 'session_id': self._session,
                'expected_generation': self.owner.generation, 'operation': operation,
                'arguments': arguments, 'target': {'object_id': self.mesh.Name}})
            if response.get('status') != 'COMPLETED':
                raise ValueError(response.get('error', {}).get('message', '메시를 읽지 못했습니다. 다시 조회하세요.'))
            return response['result']

        def _clear(self):
            self._result = None
            self.source_status.clear()
            self.summary.setRowCount(0)
            for previous, current, note in self.distributions.values():
                previous.setRowCount(0)
                current.setRowCount(0)
                note.clear()

        def _error(self, error):
            self._clear()
            text = str(error)
            if text.startswith(('STALE_', 'MESH_BUSY:', 'BUSY_EDIT:')) or text.isascii():
                text = '메시를 읽지 못했습니다. 문서와 보관 메시를 확인한 뒤 다시 조회하세요.'
            self.status.setText(text)

        def refresh(self):
            selected = self.history.currentData()
            self._clear()
            self._mesh_hash = None
            blocked = self.history.blockSignals(True)
            self.history.clear()
            self.history.setEnabled(False)
            try:
                self._context()
                records = self.owner.read_metadata().get('mesh_history', [])
                if not isinstance(records, list):
                    raise ValueError('보관 메시 기록을 읽지 못했습니다.')
                rows = [r for r in records if isinstance(r, dict) and
                        r.get('mesh_id') == self.mesh.Name and r.get('state') == 'SUCCEEDED']
                for index, record in reversed(list(enumerate(rows, 1))):
                    archive_id = record.get('previous_mesh_object_id')
                    archive = self._doc.getObject(archive_id) if isinstance(archive_id, str) and archive_id else None
                    label = getattr(archive, 'Label', self.mesh.Label)
                    if archive is None or label == archive.Name or ' — previous mesh ' in label:
                        label = self.mesh.Label
                    name = str(index) + '번째 재메시 전: ' + label
                    if archive is None:
                        name += ' (보관 메시 없음)'
                    self.history.addItem(name, record.get('id'))
                position = self.history.findData(selected)
                self.history.setCurrentIndex(position if position >= 0 else 0)
                self.history.setEnabled(bool(rows))
                self._generation = self.owner.generation
                if not rows:
                    self.status.setText('보관된 이전 메시가 없습니다. 재메시한 뒤 비교할 수 있습니다.')
                    return
                quality = self._call('pre.fem.mesh_quality', {'limit': 1})
                self._mesh_hash = quality.get('mesh_sha256')
                if self._mesh_hash is None:
                    raise ValueError('현재 메시의 좌표를 확인할 수 없습니다. 메시를 확인한 뒤 다시 조회하세요.')
            except Exception as error:
                self._error(error)
            finally:
                self.history.blockSignals(blocked)
            if self._mesh_hash is not None:
                self.compare()

        @staticmethod
        def _number(value):
            return '확인 불가' if value is None else format(value, '.6g')

        def _fill(self, table, rows):
            table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for j, value in enumerate(row):
                    item = QtWidgets.QTableWidgetItem(value if isinstance(value, str) else self._number(value))
                    if isinstance(value, str):
                        item.setToolTip(value)
                    if not isinstance(value, str):
                        item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                        item.setToolTip(str(value) if value is not None else '값이 없어 차이를 계산하지 않았습니다.')
                    table.setItem(i, j, item)

        def compare(self, *_):
            self._clear()
            if self._mesh_hash is None or self.history.currentData() is None:
                return
            try:
                result = self._call('pre.fem.mesh_compare', {'history_id': self.history.currentData(),
                                                         'mesh_sha256': self._mesh_hash})
                before, after, changes = result['previous'], result['current'], result['changes']
                relationship = result.get('current_source_relationship', {})
                confirmed = relationship.get('state') == 'MATCH'
                self.source_status.setText('메시와 현재 형상의 연결이 일치합니다. 해석 적합성 판정은 별도입니다.' if confirmed else
                    '현재 형상과 연결을 확인하지 못한 메시입니다. 값 비교는 가능하지만 현재 형상 해석에는 다시 메시를 생성하세요.')
                self.source_status.setStyleSheet('' if confirmed else
                    'font-weight: 600; color: #75440b; background: #fff2df; padding: 8px;')
                rows = [[label, before[key], after[key], changes[key]] for key, label in
                        [('total_elements', '요소 수'), ('bad_element_count', '불량 요소 수')]]
                for key, label in [('absolute_jacobian_mm3', '요소별 최소 Jacobian [mm³]'),
                                   ('normalized_jacobian', '요소별 최소 정규화 Jacobian')]:
                    for statistic, name in [('minimum', '최소'), ('maximum', '최대')]:
                        rows.append([label + ' ' + name, before[key][statistic],
                                     after[key][statistic], changes[key][statistic]])
                    old_table, new_table, note = self.distributions[key]
                    for table, values in [(old_table, before[key]), (new_table, after[key])]:
                        self._fill(table, [[b['lower'], b['upper'], b['count']] for b in values['bins']])
                    note.setText('각 요소의 최소 표본값을 모은 분포이며 부호를 유지합니다. ' +
                                 ('구간 경계가 같습니다.' if changes[key]['bin_boundaries_equal'] else
                                  '구간 경계가 서로 다릅니다. 각 분포를 별도로 표시합니다.'))
                self._fill(self.summary, rows)
                self._result = result
                self._generation = self.owner.generation
                self.status.setText('현재 값에서 이전 값을 뺀 변화입니다. 재메시한 요소 번호를 같은 위치로 연결하지 않습니다.')
            except Exception as error:
                self._error(error)

        def _check_changes(self):
            try:
                self._context()
                if self._result is not None and self.owner.generation != self._generation:
                    self._mesh_hash = None
                    self._clear()
                    self.status.setText('모델이 변경됐습니다. 다시 조회하여 현재 메시를 확인하세요.')
            except Exception as error:
                self._mesh_hash = None
                self._error(error)

        def closeEvent(self, event):
            self.timer.stop()
            super().closeEvent(event)

    return Dialog()
