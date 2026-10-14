"""Compact native research-variable table; the owner performs every edit."""
def make_panel(QtWidgets, QtCore, parameters, submit):
    class Panel(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.info, self.proof, self.busy = None, None, False
            layout = QtWidgets.QVBoxLayout(self)
            self.message = QtWidgets.QLabel('모델의 치수를 찾아 연구 변수로 등록하거나 연결을 복구합니다.')
            self.message.setWordWrap(True); layout.addWidget(self.message)
            controls = QtWidgets.QHBoxLayout()
            self.discover = QtWidgets.QPushButton('치수 새로 찾기')
            self.discover.clicked.connect(self.refresh)
            self.highlight = QtWidgets.QPushButton('모델에서 선택')
            self.highlight.clicked.connect(self.select_native)
            controls.addWidget(self.discover); controls.addWidget(self.highlight); controls.addStretch()
            layout.addLayout(controls)
            self.table = QtWidgets.QTableWidget(0, 7)
            self.table.setHorizontalHeaderLabels(['대상 치수', '현재 mm', '변수 이름', '하한 mm', '상한 mm', '모드', '상태'])
            self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            header = self.table.horizontalHeader()
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
            header.setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeToContents)
            for column in (1, 3, 4): self.table.setColumnWidth(column, 72)
            self.table.setColumnWidth(5, 60)
            self.table.setMinimumHeight(150)
            layout.addWidget(self.table, 1)
            form = QtWidgets.QFormLayout()
            self.effect = QtWidgets.QComboBox(); self.name = QtWidgets.QLineEdit()
            self.trial = QtWidgets.QLineEdit()
            form.addRow('영향을 확인할 솔리드', self.effect); form.addRow('시험 값 (mm)', self.trial)
            form.addRow('새 변수 식별자', self.name); layout.addLayout(form)
            actions = QtWidgets.QHBoxLayout()
            self.probe = QtWidgets.QPushButton('형상 영향 확인')
            self.probe.clicked.connect(self.check_effect)
            self.register = QtWidgets.QPushButton('변수 등록')
            self.register.clicked.connect(self.register_selected)
            self.apply = QtWidgets.QPushButton('변경 적용')
            self.apply.clicked.connect(self.update_selected)
            self.remove = QtWidgets.QPushButton('등록 해제')
            self.remove.clicked.connect(self.remove_selected)
            for button in (self.probe, self.register, self.apply, self.remove): actions.addWidget(button)
            layout.addLayout(actions)
            self.repair = QtWidgets.QPushButton('치수 연결 복구…')
            self.repair.clicked.connect(self.repair_selected)
            layout.addWidget(self.repair)
            self.table.itemSelectionChanged.connect(lambda: setattr(self, 'proof', None))

        def target_label(self, row):
            obj = parameters.owner.doc.getObject(row['object'])
            name = (obj.Label if obj is not None else row.get('object_label', row['object']))
            dimension = row.get('dimension', row.get('property', row.get('label', '치수')))
            return name + ' / ' + dimension

        def _send(self, operation, args, target=None, accepted=None):
            if self.busy: return
            self.busy = True; self.setEnabled(False)
            def done(result):
                self.busy = False; self.setEnabled(True)
                if result.get('status') == 'FAILED':
                    self.message.setText(result.get('error', {}).get('message', 'Native command failed')); return
                if accepted: accepted(result)
            try:
                submit(operation, args, target or {}, done)
            except Exception as error:
                done({'status': 'FAILED', 'error': {'message': str(error)}})

        def refresh(self):
            self._send('pre.parameters.discover', {}, accepted=self.populate)

        def populate(self, info):
            self.info, self.proof = info, None
            self.rows = [(False, row) for row in info['candidates']] + [(True, row) for row in info['parameters']]
            self.table.setRowCount(len(self.rows))
            for index, (registered, row) in enumerate(self.rows):
                value = row.get('current_value', row.get('value'))
                base = value if value is not None else 0.
                cells = [self.target_label(row), '—' if value is None else str(value), row.get('label', row.get('object_label', '')),
                         str(row.get('min', base - .2 * abs(base or 1.))),
                         str(row.get('max', base + .2 * abs(base or 1.))),
                         '자유' if row.get('mode') == 'free' else '고정', ('연결 복구 필요' if row.get('resolved') is False else
                         '편집 불가' if row.get('diagnostic') else '등록됨' if registered else '미등록')]
                for col, value in enumerate(cells):
                    item = QtWidgets.QTableWidgetItem(str(value))
                    if col in (0, 6) or col == 1 and not registered:
                        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                    if row.get('resolved') is False:
                        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                    if col == 6: item.setToolTip(row.get('diagnostic') or '')
                    if col == 0: item.setToolTip(row.get('key', '') + '\n' + row.get('name', ''))
                    self.table.setItem(index, col, item)
            self.effect.clear()
            for solid in info['effect_objects']: self.effect.addItem(solid['label'], solid['object_id'])
            self.message.setText('연결 복구가 필요한 변수를 선택하세요.' if any(row.get('resolved') is False for row in info['parameters'])
                                 else '치수 변경과 등록은 실행 취소할 수 있습니다. 형상 영향 확인 뒤 원래 모델로 돌아옵니다.')

        def repair_selected(self):
            try:
                _, (registered, row) = self.selected()
                if not registered or row.get('resolved') is not False:
                    raise ValueError('연결 복구가 필요한 등록 변수를 선택하세요.')
                dialog = QtWidgets.QDialog(self)
                dialog.setWindowTitle('치수 연결 복구')
                dialog.setMinimumWidth(460)
                layout = QtWidgets.QVBoxLayout(dialog)
                old = QtWidgets.QLabel(row.get('label', row['name']) + '\n이전 대상: ' + self.target_label(row))
                old.setWordWrap(True); layout.addWidget(old)
                form = QtWidgets.QFormLayout()
                replacement = QtWidgets.QComboBox()
                replacement.addItem('새 대상 치수를 선택하세요', None)
                for candidate in self.info['candidates']:
                    if candidate['writable']:
                        replacement.addItem(self.target_label(candidate) + ' (' + str(candidate['value']) + ' mm)', candidate['key'])
                solid = QtWidgets.QComboBox()
                for item in self.info['effect_objects']: solid.addItem(item['label'], item['object_id'])
                trial = QtWidgets.QLineEdit()
                form.addRow('새 대상', replacement); form.addRow('영향을 확인할 솔리드', solid)
                form.addRow('시험 값 (mm)', trial); layout.addLayout(form)
                status = QtWidgets.QLabel('기존 범위: ' + str(row['min']) + ' ~ ' + str(row['max']) + ' mm\n새 치수의 형상 영향을 확인한 뒤 연결을 적용하세요.')
                status.setWordWrap(True); layout.addWidget(status)
                check = QtWidgets.QPushButton('형상 영향 확인'); layout.addWidget(check)
                buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Apply | QtWidgets.QDialogButtonBox.Cancel)
                apply = buttons.button(QtWidgets.QDialogButtonBox.Apply); apply.setText('연결 적용'); apply.setEnabled(False)
                buttons.button(QtWidgets.QDialogButtonBox.Cancel).setText('취소')
                buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
                proof = [None]
                def reset(*unused):
                    proof[0] = None; apply.setEnabled(False)
                replacement.currentIndexChanged.connect(reset); solid.currentIndexChanged.connect(reset); trial.textChanged.connect(reset)
                def send(operation, args, accepted):
                    dialog.setEnabled(False)
                    def done(result):
                        dialog.setEnabled(True)
                        if result.get('status') == 'FAILED':
                            status.setText(result.get('error', {}).get('message', '연결 복구에 실패했습니다.')); return
                        accepted(result)
                    try: submit(operation, args, {}, done)
                    except Exception as error: done({'status': 'FAILED', 'error': {'message': str(error)}})
                def probe():
                    reset()
                    try:
                        if not replacement.currentData(): raise ValueError('새 대상 치수를 선택하세요.')
                        args = {'selector': replacement.currentData(), 'source_stamp': self.info['source_stamp'],
                                'effect_object_id': solid.currentData(), 'trial_value': float(trial.text()), 'unit': 'mm'}
                        def checked(result):
                            proof[0] = result
                            valid = result['changed'] and result['restored'] and not result['error']
                            apply.setEnabled(bool(valid))
                            status.setText('형상 변화를 확인했고 원래 모델로 복원했습니다. 연결을 적용할 수 있습니다.' if valid
                                           else '형상 변화를 확인하지 못했습니다. 다른 치수나 시험 값을 선택하세요.\n' + (result['error'] or ''))
                        send('pre.parameters.probe', args, checked)
                    except Exception as error: status.setText(str(error))
                def commit():
                    if not proof[0]: return
                    args = {'parameter_id': row['name'], 'selector': replacement.currentData(),
                            'source_stamp': self.info['source_stamp'], 'proof_id': proof[0]['proof_id']}
                    def repaired(result):
                        self.populate(result); dialog.accept()
                    send('pre.parameters.rebind', args, repaired)
                check.clicked.connect(probe); apply.clicked.connect(commit)
                self.repair_dialog = dialog
                dialog.exec()
            except Exception as error: self.message.setText(str(error))

        def selected(self):
            row = self.table.currentRow()
            if self.info is None or row < 0: raise ValueError('Select a discovered or registered native dimension')
            return row, self.rows[row]

        def select_native(self):
            try:
                _, (_, row) = self.selected()
                self._send('pre.select', {'objects': [{'object_id': row['object']}]})
            except Exception as error: self.message.setText(str(error))

        def check_effect(self):
            try:
                _, (_, row) = self.selected()
                args = {'selector': row['key'], 'source_stamp': self.info['source_stamp'],
                        'effect_object_id': self.effect.currentData(), 'trial_value': float(self.trial.text()), 'unit': 'mm'}
                def shown(result):
                    self.proof = result
                    self.message.setText('Restored original design. Geometry effect: ' + str(result['changed']) +
                                         ('; ' + result['error'] if result['error'] else ''))
                self._send('pre.parameters.probe', args, accepted=shown)
            except Exception as error: self.message.setText(str(error))

        def register_selected(self):
            try:
                index, (registered, row) = self.selected()
                if registered or not self.proof: raise ValueError('Probe this unregistered target first')
                args = {'selector': row['key'], 'source_stamp': self.info['source_stamp'], 'proof_id': self.proof['proof_id'],
                    'parameter_id': self.name.text().strip(), 'label': self.table.item(index, 2).text(),
                    'lower': float(self.table.item(index, 3).text()), 'upper': float(self.table.item(index, 4).text()),
                    'mode': {'고정': 'fixed', '자유': 'free'}.get(self.table.item(index, 5).text(), self.table.item(index, 5).text())}
                self._send('pre.parameters.register', args, accepted=self.populate)
            except Exception as error: self.message.setText(str(error))

        def update_selected(self):
            try:
                index, (registered, row) = self.selected()
                if not registered: raise ValueError('Explicitly register the discovered dimension first')
                args = {'parameter_id': row['name'], 'value': float(self.table.item(index, 1).text()), 'unit': 'mm',
                    'label': self.table.item(index, 2).text(), 'lower': float(self.table.item(index, 3).text()),
                    'upper': float(self.table.item(index, 4).text()),
                    'mode': {'고정': 'fixed', '자유': 'free'}.get(self.table.item(index, 5).text(), self.table.item(index, 5).text())}
                self._send('pre.parameters.update', args, accepted=self.populate)
            except Exception as error: self.message.setText(str(error))

        def remove_selected(self):
            try:
                _, (registered, row) = self.selected()
                if not registered: raise ValueError('Select a registered research ID')
                self._send('pre.parameters.remove', {'parameter_id': row['name']}, accepted=self.populate)
            except Exception as error: self.message.setText(str(error))
    return Panel()
