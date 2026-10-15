"""Native Qt editor for periodic BCs using the existing FEM command gateway.

No new document/mesh/solver owner. The buffered form is never persisted by poll.
An unacknowledged command can be retried with its exact operation/request id.
"""
from copy import deepcopy
import uuid


def add_periodic_page(panel, W, C):
    from .periodic_native import read

    class Page(W.QWidget):
        def __init__(self):
            super().__init__()
            self.info, self.record = {}, None
            self.loaded_analysis, self.modified, self.loading = None, False, False
            self.pending_retry = None
            layout = W.QVBoxLayout(self)
            info = W.QLabel('정적·소변형·선형 탄성 C3D10 고체의 주기 변위 구속입니다. '
                'B의 병진 자유도 1·2·3을 A에 연결합니다. 회전 주기는 좌표와 변위 벡터의 회전이며 회전 자유도 4·5·6이 아닙니다.')
            info.setWordWrap(True); layout.addWidget(info)
            self.records = W.QComboBox(); self.records.setObjectName('periodicConstraints')
            self.records.currentIndexChanged.connect(self.choose)
            row = W.QHBoxLayout(); row.addWidget(self.records, 1)
            panel._button('새 주기 구속', self.new, row)
            layout.addLayout(row)
            self.label = W.QLineEdit(); self.label.setObjectName('periodicLabel')
            layout.addWidget(self.label)
            self.regions = {}
            for side, text in [('a', 'A 기준 경계'), ('b', 'B 종속 경계')]:
                line = W.QHBoxLayout(); line.addWidget(W.QLabel(text))
                combo = W.QComboBox(); combo.setObjectName('periodicRegion'+side.upper())
                self.regions[side] = combo
                combo.currentIndexChanged.connect(self.mark); line.addWidget(combo, 1)
                panel._button('선택 면 영역 저장', lambda s=side: self.capture(s), line)
                layout.addLayout(line)
            self.kind = W.QComboBox()
            self.kind.addItem('병진 주기', 'translation'); self.kind.addItem('회전 주기', 'rotation')
            self.kind.currentIndexChanged.connect(self.kind_changed); layout.addWidget(self.kind)
            self.vectors = W.QTableWidget(3, 3); self.vectors.setObjectName('periodicTransform')
            self.vectors.setHorizontalHeaderLabels(['X', 'Y', 'Z'])
            self.vectors.setVerticalHeaderLabels(['이동량 [mm]', '축 방향', '축 기준점 [mm]'])
            self.vectors.horizontalHeader().setStretchLastSection(True)
            self.vectors.setMaximumHeight(160); layout.addWidget(self.vectors)
            row = W.QHBoxLayout(); row.addWidget(W.QLabel('주기각 [°]'))
            self.angle = W.QLineEdit('90'); row.addWidget(self.angle)
            row.addWidget(W.QLabel('대응 허용오차 [mm]'))
            self.tolerance = W.QLineEdit('1e-6'); row.addWidget(self.tolerance)
            layout.addLayout(row)
            self.state = W.QLabel(); self.state.setWordWrap(True); layout.addWidget(self.state)
            actions = W.QHBoxLayout()
            panel._button('주기 구속 적용', self.apply, actions, name='periodicApply')
            panel._button('수정 취소 / 다시 읽기', self.discard, actions, mutate=False)
            panel._button('삭제', self.remove, actions, name='periodicRemove')
            layout.addLayout(actions)
            actions = W.QHBoxLayout()
            panel._button('A/B 면 강조', self.highlight, actions, mutate=False)
            panel._button('응답 유실 요청 재조회/재시도', self.retry, actions, name='periodicRetry')
            layout.addLayout(actions)
            note = W.QLabel('적용 후 기존 모델 입력 생성에서 모든 면 절점의 일대일 대응·중복·고정 조건 충돌을 검사합니다. '
                '문서의 저장, 실행 취소/다시 실행을 그대로 사용하세요. 해석 실행은 기존 Runner에서 명시적으로 요청합니다.')
            note.setWordWrap(True); layout.addWidget(note); layout.addStretch()
            for field in (self.label, self.angle, self.tolerance):
                field.textChanged.connect(self.mark)
            self.vectors.itemChanged.connect(self.mark)
            panel.tabs.addTab(self, '주기 구속')
            panel.analysis.currentIndexChanged.connect(lambda *_: self.refresh(load_forms=True))

        def mark(self, *_):
            if not self.loading:
                self.modified = True; panel._edited(); self.state.setText('미적용 초안 — 원 문서는 그대로입니다.')

        def refresh(self, *, load_forms):
            aid = panel.analysis.currentData()
            if not aid or self.modified or (not load_forms and aid == self.loaded_analysis):
                return
            self.loaded_analysis = aid
            self.info = read(panel.editor, panel.editor.owner._object(aid))
            identifier = self.record['id'] if self.record else None
            self.loading = True
            try:
                self.records.clear()
                for record in self.info['constraints']:
                    self.records.addItem(record['draft']['label'] or '이름 없는 주기 구속', record['id'])
                index = self.records.findData(identifier)
                self.records.setCurrentIndex(max(0, index) if self.records.count() else -1)
                for combo in self.regions.values():
                    combo.clear(); combo.addItem('선택한 면 집합을 지정하세요', '')
                    for region in self.info['regions']:
                        combo.addItem(region['label'], region['id'])
            finally:
                self.loading = False
            self.choose()

        def choose(self, *_):
            if self.loading:
                return
            identifier = self.records.currentData()
            if self.modified:
                self.state.setText('미적용 초안을 유지합니다. 수정 취소 후 다른 주기 구속을 선택하세요.')
                self.loading = True
                self.records.setCurrentIndex(self.records.findData(self.record['id']) if self.record else -1)
                self.loading = False
                return
            self.record = next((deepcopy(r) for r in self.info.get('constraints', []) if r['id'] == identifier), None)
            if self.record is None:
                self.new()
            else:
                self.populate(self.record['draft'])
                problems = self.record.get('errors', [])
                self.state.setText('; '.join({'Enter a complete finite number': '숫자를 끝까지 입력하고 유한한 값인지 확인하세요.',
                    'Enter a finite number': '유한한 숫자를 입력하세요.'}.get(error, error) for error in problems)
                    or '적용된 경계와 변환입니다. 메시 대응 검사는 입력 생성에서 수행합니다.')
                self.state.setToolTip('\n'.join(problems))

        def new(self):
            if self.modified:
                raise ValueError('현재 미적용 초안을 적용하거나 수정 취소한 뒤 새 구속을 만드세요.')
            self.record = None
            self.loading = True; self.records.setCurrentIndex(-1); self.loading = False
            self.populate({'label': '새 주기 경계', 'a_region_id': '', 'b_region_id': '',
                'transform': {'kind': 'translation', 'translation_mm': [0, 0, 0]},
                'tolerance_mm': '1e-6', 'dofs': [1, 2, 3]})
            self.state.setText('A/B 경계와 변환을 지정하세요. 아직 문서를 수정하지 않았습니다.')

        def populate(self, draft):
            self.loading = True
            try:
                self.label.setText(str(draft['label']))
                for side, combo in self.regions.items():
                    value = draft[side+'_region_id']; index = combo.findData(value)
                    if index < 0:
                        combo.addItem('다시 지정할 경계', value); index = combo.count()-1
                    combo.setCurrentIndex(index)
                transform = draft['transform']
                self.kind.setCurrentIndex(self.kind.findData(transform.get('kind')))
                rows = [transform.get('translation_mm', [0, 0, 0]), transform.get('axis', [0, 0, 1]),
                        transform.get('origin_mm', [0, 0, 0])]
                for i, row in enumerate(rows):
                    for j, value in enumerate(row):
                        self.vectors.setItem(i, j, W.QTableWidgetItem(str(value)))
                self.angle.setText(str(transform.get('angle_deg', 90)))
                self.tolerance.setText(str(draft['tolerance_mm']))
                self.kind_changed()
            finally:
                self.loading = False

        def kind_changed(self, *_):
            rotation = self.kind.currentData() == 'rotation'
            self.vectors.setRowHidden(0, rotation)
            for row in (1, 2): self.vectors.setRowHidden(row, not rotation)
            self.angle.setEnabled(rotation)
            self.mark()

        def draft(self):
            def values(i):
                return [self.vectors.item(i, j).text() if self.vectors.item(i, j) else '' for j in range(3)]
            transform = ({'kind': 'translation', 'translation_mm': values(0)} if self.kind.currentData() == 'translation'
                         else {'kind': 'rotation', 'axis': values(1), 'origin_mm': values(2), 'angle_deg': self.angle.text()})
            return {'label': self.label.text(), 'a_region_id': self.regions['a'].currentData(),
                    'b_region_id': self.regions['b'].currentData(), 'transform': transform,
                    'tolerance_mm': self.tolerance.text(), 'dofs': [1, 2, 3]}

        def capture(self, side):
            if panel.analysis.currentData() != self.loaded_analysis:
                raise ValueError('편집하던 해석을 다시 선택하세요.')
            obj, names = panel._selection()
            if not names or any(not name.startswith('Face') for name in names):
                raise ValueError('3D에서 같은 물체의 면을 하나 이상 선택하세요.')
            aid = self.loaded_analysis
            def accepted(result):
                if panel.analysis.currentData() != aid:
                    return
                combo = self.regions[side]
                combo.addItem(result['label'], result['id']); combo.setCurrentIndex(combo.count()-1)
                self.mark()
            panel._send('pre.fem.region_set', {'label': self.label.text()+' '+side.upper(), 'subelements': names}, obj, on_done=accepted)

        def discard(self):
            self.modified = False
            self.refresh(load_forms=True)
            if self.pending_retry:
                self.state.setText('현재 문서를 다시 읽었습니다. 이전 미확인 요청은 재시도 버튼으로 대조할 수 있습니다.')

        def submit(self, operation, args):
            aid = self.loaded_analysis
            serial = self.pending_retry[3] if self.pending_retry else panel._edit_serial
            if aid != panel.analysis.currentData():
                raise ValueError('편집하던 해석을 다시 선택하세요.')
            self.pending_retry = (operation, deepcopy(args), aid, serial)
            def accepted(result):
                self.pending_retry = None
                if aid == panel.analysis.currentData() and panel._edit_serial == serial:
                    self.modified = False
                    self.record = next((deepcopy(r) for r in result['state']['constraints'] if r['id'] == result['id']), None)
                    self.refresh(load_forms=True)
                else:
                    self.state.setText('이전 요청이 적용됐습니다. 현재 편집 초안은 유지합니다.')
            def failed(error):
                if getattr(error, 'native_terminal', False):
                    self.pending_retry = None
                    self.state.setText('문서가 요청을 거부했습니다. 초안을 수정하거나 현재 문서를 다시 읽으세요. '+str(error))
                    return
                self.state.setText('적용 확인 실패. 초안과 동일 요청을 유지합니다. 현재 문서를 읽거나 동일 요청을 재시도하세요. '+str(error))
            panel._send(operation, args, aid, on_done=accepted, on_error=failed)

        def apply(self):
            if self.pending_retry:
                raise ValueError('이전 요청의 완료 여부를 재시도로 먼저 확인하세요. 현재 초안은 유지됩니다.')
            identifier = self.record['id'] if self.record else 'P'+uuid.uuid4().hex
            self.submit('pre.fem.periodic_set', {'id': identifier,
                'expected_revision': self.record['revision'] if self.record else None,
                'request_id': uuid.uuid4().hex, 'draft': self.draft()})

        def remove(self):
            if not self.record or self.pending_retry:
                raise ValueError('저장된 주기 구속을 선택하고 미확인 요청부터 확인하세요.')
            self.submit('pre.fem.periodic_remove', {'id': self.record['id'],
                'expected_revision': self.record['revision'], 'request_id': uuid.uuid4().hex})

        def retry(self):
            if not self.pending_retry:
                raise ValueError('완료를 확인하지 못한 요청이 없습니다.')
            operation, args, aid, _ = self.pending_retry
            if aid != self.loaded_analysis:
                raise ValueError('미확인 요청의 원래 해석을 선택하세요.')
            self.submit(operation, args)

        def highlight(self):
            if not self.record:
                raise ValueError('저장된 주기 구속을 선택하세요.')
            panel._send('pre.fem.periodic_highlight', {'id': self.record['id'], 'side': 'both'}, self.loaded_analysis)

    return Page()
