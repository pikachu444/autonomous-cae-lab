"""Contextual native Qt material table/curve, sharing the FEM typed command owner."""
from copy import deepcopy
import importlib
import math

from caelab.calculix_material import J2, LINEAR, default_plasticity, finite
from . import nonlinear_material as service


def add_material_page(panel, W, C):
    G = importlib.import_module(W.__package__ + '.QtGui')

    class Plot(W.QWidget):
        def __init__(self):
            super().__init__()
            self.rows, self.stress_unit, self.strain_unit, self.selected = [], 'MPa', '1', -1
            self.setMinimumSize(190, 190)
            self.setAccessibleName('입력한 진응력과 등가 소성변형률 곡선')
        def paintEvent(self, event):
            painter = G.QPainter(self)
            painter.setRenderHint(G.QPainter.RenderHint.Antialiasing)
            painter.fillRect(self.rect(), self.palette().base())
            points = []
            for row in self.rows:
                try:
                    points.append((finite(row[1]), finite(row[0])))
                except (ValueError, TypeError, IndexError, KeyError):
                    points.append(None)  # Do not join across an invalid editing row.
            valid = [point for point in points if point is not None]
            metrics = painter.fontMetrics(); line = metrics.height()
            xmin, xmax, ymin, ymax = 0., 1., 0., 1.
            if valid:
                xmin, xmax = min(p[0] for p in valid), max(p[0] for p in valid)
                ymin, ymax = min(p[1] for p in valid), max(p[1] for p in valid)
                if xmin == xmax: xmax = xmin + max(abs(xmin) * .1, .001)
                if ymin == ymax: ymax = ymin + max(abs(ymin) * .1, 1.)
            # Avoid overflowing a preview of still-invalid input; export validates separately.
            if not math.isfinite(xmax-xmin) or not math.isfinite(ymax-ymin):
                painter.drawText(self.rect(), C.Qt.AlignmentFlag.AlignCenter, '표의 값 범위를 확인하세요.')
                return
            labels = [format(ymin, '.4g'), format(ymax, '.4g')]
            left = max(42, max(metrics.horizontalAdvance(v) for v in labels)+10)
            r = self.rect().adjusted(left, line+18, -14, -(line*3+9))
            if r.width() < 20 or r.height() < 20: return
            painter.setPen(self.palette().text().color())
            painter.drawText(8, line, '진응력 ['+self.stress_unit+']')
            painter.drawText(8, self.height()-8, '등가 소성변형률 ['+self.strain_unit+']')
            painter.drawLine(r.bottomLeft(), r.bottomRight()); painter.drawLine(r.bottomLeft(), r.topLeft())
            painter.drawText(r.left()-metrics.horizontalAdvance(labels[0])-6, r.bottom(), labels[0])
            painter.drawText(r.left()-metrics.horizontalAdvance(labels[1])-6, r.top()+metrics.ascent(), labels[1])
            painter.drawText(r.left(), r.bottom()+line+2, format(xmin, '.4g'))
            end = format(xmax, '.4g')
            painter.drawText(r.right()-metrics.horizontalAdvance(end), r.bottom()+line+2, end)
            if not valid:
                painter.drawText(r, C.Qt.AlignmentFlag.AlignCenter, '표에 항복점을 입력하세요.')
                return
            pen = G.QPen(self.palette().highlight().color()); pen.setWidthF(1.8); painter.setPen(pen)
            previous = None
            for index, point in enumerate(points):
                if point is None:
                    previous = None; continue
                x, y = point
                p = C.QPointF(r.left()+(x-xmin)*r.width()/(xmax-xmin), r.bottom()-(y-ymin)*r.height()/(ymax-ymin))
                if previous is not None: painter.drawLine(previous, p)
                painter.drawEllipse(p, 4.5 if index == self.selected else 2.7, 4.5 if index == self.selected else 2.7)
                previous = p

    class NumericDisplay(W.QStyledItemDelegate):
        """Fit the exponent as well as the mantissa; leave the edit value literal."""
        def initStyleOption(self, option, index):
            super().initStyleOption(option, index)
            literal = option.text
            try:
                value = finite(literal)
            except ValueError:
                return
            width = max(24, option.rect.width()-12)
            if option.fontMetrics.horizontalAdvance(literal) <= width:
                return
            for precision in range(12, 2, -1):
                text = format(value, '.'+str(precision)+'g')
                if option.fontMetrics.horizontalAdvance(text) <= width:
                    option.text = text
                    return

    class Table(W.QTableWidget):
        def keyPressEvent(self, event):
            if event.matches(G.QKeySequence.StandardKey.Paste):
                self.page.paste(); event.accept(); return
            super().keyPressEvent(event)

    class Page(W.QWidget):
        def __init__(self):
            super().__init__()
            self.loading, self.modified, self.info = False, False, None
            self.loaded, self.buffer = None, None
            self.validation_errors, self.admission_busy = [], False
            self.preserved_rows = {}
            self.geometry_source = None
            self.setObjectName('ns1MaterialPage')
            layout = W.QVBoxLayout(self); layout.setContentsMargins(8, 6, 8, 6); layout.setSpacing(8)
            form = W.QFormLayout(); form.setRowWrapPolicy(W.QFormLayout.RowWrapPolicy.WrapLongRows)
            self.analysis = W.QComboBox(); self.analysis.setObjectName('ns1MaterialAnalysis')
            panel.material = W.QComboBox(); panel.material.setObjectName('femMaterial')
            form.addRow('해석', self.analysis); form.addRow('기본 재료', panel.material)
            self.scope = W.QLabel(); self.scope.setWordWrap(True); self.scope.setMinimumWidth(0)
            form.addRow('적용 영역', self.scope)
            layout.addLayout(form)
            elastic = W.QHBoxLayout()
            panel.modulus = panel._number('femYoungModulus', minimum=0, value=0); panel.modulus.setSpecialValueText('미입력')
            panel.poisson = panel._number('femPoissonRatio', minimum=-1, maximum=.499999999, value=-1); panel.poisson.setSpecialValueText('미입력')
            ef = W.QFormLayout(); ef.addRow('E [MPa]', panel.modulus); ef.addRow('포아송비', panel.poisson)
            elastic.addLayout(ef, 1)
            actions = W.QVBoxLayout()
            panel._button('탄성 적용', panel.apply_material, actions, name='femApplyMaterial')
            panel._button('선택 따라가기', self.follow_selection, actions, mutate=False)
            elastic.addLayout(actions); layout.addLayout(elastic)
            row = W.QHBoxLayout(); self.law = W.QComboBox(); self.law.setObjectName('ns1MaterialLaw')
            self.law.addItem('등방 탄성', LINEAR); self.law.addItem('J2 등방 경화', J2); row.addWidget(self.law, 1)
            self.stress_unit, self.strain_unit = W.QComboBox(), W.QComboBox()
            for unit in ('Pa', 'kPa', 'MPa', 'GPa'): self.stress_unit.addItem(unit, unit)
            for label, unit in (('무차원 [1]', '1'), ('퍼센트 [%]', '%')): self.strain_unit.addItem(label, unit)
            self.stress_unit.setAccessibleName('진응력 단위'); self.strain_unit.setAccessibleName('등가 소성변형률 단위')
            row.addWidget(self.stress_unit); row.addWidget(self.strain_unit); layout.addLayout(row)
            self.confirm = W.QCheckBox('진응력–등가 소성변형률 표임을 확인')
            self.confirm.setObjectName('ns1ConfirmMeasures')
            self.confirm.setToolTip('공칭응력이나 전체변형률을 자동 변환하지 않습니다. 단위만 MPa와 무차원으로 변환합니다.')
            layout.addWidget(self.confirm)
            split = W.QSplitter(C.Qt.Orientation.Horizontal)
            left = W.QWidget(); ll = W.QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(5)
            self.table = Table(0, 2); self.table.page = self; self.table.setObjectName('ns1YieldPoints')
            self.table.setItemDelegate(NumericDisplay(self.table))
            self.table.setSelectionMode(W.QAbstractItemView.SelectionMode.ExtendedSelection)
            self.table.horizontalHeader().setSectionResizeMode(W.QHeaderView.ResizeMode.Stretch)
            self.table.verticalHeader().setDefaultSectionSize(26)
            self.table.setAlternatingRowColors(True); self.table.setMinimumWidth(175)
            ll.addWidget(self.table, 1)
            buttons = W.QHBoxLayout()
            panel._button('행 추가', self.add_row, buttons, mutate=False)
            panel._button('행 삭제', self.remove_rows, buttons, mutate=False)
            ll.addLayout(buttons); split.addWidget(left)
            self.plot = Plot(); split.addWidget(self.plot); split.setSizes([260, 360]); layout.addWidget(split, 1)
            self.errors = W.QLabel(); self.errors.setWordWrap(True); self.errors.setMinimumWidth(0)
            self.errors.setSizePolicy(W.QSizePolicy.Policy.Ignored, W.QSizePolicy.Policy.Preferred)
            self.errors.setTextInteractionFlags(C.Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(self.errors)
            buttons = W.QHBoxLayout()
            self.save_button = panel._button('초안 저장', lambda: self.send(False), buttons, name='ns1SaveDraft')
            self.save_button.setShortcut('Alt+S')
            self.apply_button = panel._button('재료 적용', lambda: self.send(True), buttons, name='ns1ApplyMaterial')
            self.apply_button.setShortcut('Ctrl+Return')
            panel._button('저장본 읽기', self.discard, buttons, mutate=False)
            self.error_button = panel._button('오류 행', self.focus_error, buttons, mutate=False, name='ns1ErrorRow')
            layout.addLayout(buttons)
            settings = W.QHBoxLayout()
            self.nlgeom = W.QCheckBox('기하 비선형 (NLGEOM)'); self.nlgeom.setObjectName('ns1Nlgeom')
            settings.addWidget(self.nlgeom, 1)
            panel._button('기하 설정 적용', self.apply_geometry, settings, name='ns1ApplyGeometry')
            layout.addLayout(settings)
            self.strain_meaning = W.QLabel(); self.strain_meaning.setWordWrap(True); layout.addWidget(self.strain_meaning)
            self.analysis.currentIndexChanged.connect(self.selection_changed)
            panel.material.currentIndexChanged.connect(self.selection_changed)
            self.table.itemChanged.connect(self.row_changed)
            self.table.itemSelectionChanged.connect(self.highlight)
            for widget in (self.law, self.stress_unit, self.strain_unit): widget.currentIndexChanged.connect(self.changed)
            self.confirm.toggled.connect(self.changed)
            self.nlgeom.toggled.connect(self.geometry_caption)
            panel.tabs.addTab(self, '재료')

        def selected(self):
            return self.analysis.currentData(), panel.material.currentData()

        def refresh(self, *, load_forms=True):
            if self.pending_changes() or not load_forms: return
            self.loading = True
            try:
                old = self.analysis.currentData()
                self.analysis.clear()
                for obj in panel.editor.owner.doc.Objects:
                    if service.native_type(obj) == 'Fem::FemAnalysis': self.analysis.addItem(obj.Label, obj.Name)
                if self.analysis.findData(old) >= 0: self.analysis.setCurrentIndex(self.analysis.findData(old))
                self.fill_materials()
            finally:
                self.loading = False
            self.load()

        def fill_materials(self):
            old = panel.material.currentData(); panel.material.clear()
            aid = self.analysis.currentData()
            if not aid: return
            analysis = panel.editor.owner._object(aid)
            for obj in analysis.Group:
                if service.native_type(obj) == 'Fem::MaterialCommon' and getattr(obj, 'Category', None) == 'Solid' and not getattr(obj, 'Suppressed', False):
                    panel.material.addItem(obj.Label, obj.Name)
            if panel.material.findData(old) >= 0: panel.material.setCurrentIndex(panel.material.findData(old))

        def selection_changed(self, *_):
            if self.loading: return
            if self.pending_changes() and self.loaded != self.selected():
                self.loading = True
                self.analysis.setCurrentIndex(self.analysis.findData(self.loaded[0]))
                panel.material.setCurrentIndex(panel.material.findData(self.loaded[1]))
                self.loading = False
                self.errors.setText('현재 표를 초안 저장하거나 저장본을 읽은 뒤 대상을 바꾸세요.')
                return
            if self.loaded and self.loaded[0] != self.analysis.currentData():
                self.loading = True; self.fill_materials(); self.loading = False
            self.load()

        def load(self):
            if self.loading or self.modified: return
            aid, mid = self.selected()
            self.loaded = (aid, mid)
            if not aid or not mid:
                self.info = self.buffer = None; self.table.setRowCount(0); self.scope.setText('선택 없음'); return
            base = panel.editor.owner._object(mid)
            try:
                self.info = service.read(panel.editor, base, aid)
                self.buffer = deepcopy(self.info['draft'])
                panel._load_material()
                refs = getattr(base, 'References', [])
                self.scope.setText(', '.join(obj.Label for obj, names in refs) if refs else '해석의 전체 고체 (명시 기본 재료)')
                self.populate()
                solvers = self.solvers()
                self.geometry_source = bool(len(solvers) == 1 and solvers[0].GeometricalNonlinearity == 'nonlinear')
                self.nlgeom.setChecked(self.geometry_source)
                self.geometry_caption()
            except Exception as error:
                self.errors.setText(str(error)); self.buffer = self.info = None
                self.table.setRowCount(0); self.plot.rows = []; self.plot.update(); self.sync_actions()

        def populate(self):
            self.loading = True
            try:
                d = self.buffer; curve = d.get('plasticity') or default_plasticity()
                self.law.setCurrentIndex(self.law.findData(d.get('law')))
                for combo, key in ((self.stress_unit, 'stress_unit'), (self.strain_unit, 'strain_unit')):
                    index = combo.findData(curve.get(key))
                    if index < 0:
                        combo.addItem('미지원: '+str(curve.get(key)), curve.get(key)); index = combo.count()-1
                    combo.setCurrentIndex(index)
                self.confirm.setChecked(d.get('definitions_confirmed', self.info.get('source') == 'native_material' and d.get('law') == J2))
                rows = curve.get('yield_points') or []
                self.preserved_rows = {i: deepcopy(row) for i, row in enumerate(rows)
                                       if not isinstance(row, (list, tuple)) or len(row) != 2}
                self.table.setRowCount(len(rows))
                for i, row in enumerate(rows):
                    for j in range(2):
                        self.table.setItem(i, j, W.QTableWidgetItem(str(row[j]) if isinstance(row, (list, tuple)) and len(row) > j else ''))
            finally:
                self.loading = False
            self.update_state()

        def current_draft(self):
            value = deepcopy(self.buffer) if self.buffer else {'plasticity': default_plasticity()}
            curve = value.setdefault('plasticity', default_plasticity())
            if not isinstance(curve, dict):
                curve = value['plasticity'] = default_plasticity()
            value['law'] = self.law.currentData(); value['definitions_confirmed'] = self.confirm.isChecked()
            curve.update(stress_unit=self.stress_unit.currentData(), strain_unit=self.strain_unit.currentData())
            curve['yield_points'] = [[self.table.item(i, j).text() if self.table.item(i, j) else '' for j in range(2)]
                                      for i in range(self.table.rowCount())]
            for i, row in self.preserved_rows.items():
                if i < len(curve['yield_points']): curve['yield_points'][i] = deepcopy(row)
            return value

        def changed(self, *_):
            if self.loading or self.buffer is None: return
            self.modified = True; panel._edited(); self.buffer = self.current_draft(); self.update_state()

        def row_changed(self, item):
            if not self.loading: self.preserved_rows.pop(item.row(), None)
            self.changed()

        def update_state(self):
            if self.buffer is None: return
            draft = self.current_draft()
            errors = self.validation_errors = service.draft_errors(draft)
            self.table.setHorizontalHeaderLabels(['진응력\n['+str(self.stress_unit.currentData())+']', '소성변형률\n['+str(self.strain_unit.currentData())+']'])
            self.plot.rows = draft.get('plasticity', {}).get('yield_points', [])
            self.plot.stress_unit, self.plot.strain_unit = str(self.stress_unit.currentData()), str(self.strain_unit.currentData())
            self.plot.update()
            self.table.blockSignals(True)
            try:
                for i in range(self.table.rowCount()):
                    self.table.setVerticalHeaderItem(i, W.QTableWidgetItem(str(i+1)))
                    for j in range(2):
                        item = self.table.item(i, j)
                        if item: item.setBackground(G.QBrush()); item.setToolTip(item.text())
                for error in errors:
                    fields = error['path'].split('.')
                    if 'yield_points' in fields:
                        k = fields.index('yield_points')+1
                        if k < len(fields) and fields[k].isdigit():
                            i = int(fields[k]); columns = [int(fields[k+1])] if k+1 < len(fields) and fields[k+1].isdigit() else [0,1]
                            if i < self.table.rowCount():
                                self.table.setVerticalHeaderItem(i, W.QTableWidgetItem(str(i+1)+' !'))
                                for j in columns:
                                    item = self.table.item(i, j)
                                    if item:
                                        item.setBackground(self.palette().alternateBase()); item.setToolTip('오류: '+error['message'])
            finally:
                self.table.blockSignals(False)
            prefix = str(self.table.rowCount())+'점 / 실행 최대 200점'
            self.errors.setText(prefix+' — '+(errors[0]['message'] if errors else ('미저장 편집' if self.modified else ('적용됨' if self.info and self.info.get('applied') else '초안 / native 원본'))))
            self.errors.setToolTip('\n'.join(e['path']+': '+e['message'] for e in errors))
            self.sync_actions()

        def sync_actions(self, busy=None):
            if busy is not None: self.admission_busy = bool(busy)
            self.error_button.setEnabled(self.first_error_item() is not None)
            self.apply_button.setEnabled(self.buffer is not None and not self.validation_errors and
                not self.admission_busy and not panel._command_busy and self.loaded == self.selected())

        def first_error_item(self):
            for error in self.validation_errors:
                fields = error['path'].split('.')
                if 'yield_points' in fields:
                    k = fields.index('yield_points')+1
                    if k < len(fields) and fields[k].isdigit():
                        row = int(fields[k]); col = int(fields[k+1]) if k+1 < len(fields) and fields[k+1].isdigit() else 0
                        if row < self.table.rowCount() and col < 2: return self.table.item(row, col)
            return None

        def focus_error(self):
            item = self.first_error_item()
            if item is not None:
                self.table.setCurrentItem(item); self.table.scrollToItem(item); self.table.setFocus()

        def highlight(self):
            self.plot.selected = self.table.currentRow(); self.plot.update()

        def add_row(self):
            if self.buffer is None: return
            i = self.table.rowCount()
            if i >= 10000: raise ValueError('편집 표는 10,000점까지 보존합니다. 실행 한도는 200점입니다.')
            self.table.blockSignals(True); self.table.insertRow(i)
            for j in range(2): self.table.setItem(i, j, W.QTableWidgetItem(''))
            self.table.blockSignals(False); self.table.setCurrentCell(i, 0); self.changed(); self.table.editItem(self.table.item(i, 0))

        def remove_rows(self):
            selected = sorted({item.row() for item in self.table.selectedItems()}, reverse=True)
            self.table.blockSignals(True)
            for i in selected:
                self.table.removeRow(i)
                self.preserved_rows = {(j-1 if j > i else j): row for j, row in self.preserved_rows.items() if j != i}
            self.table.blockSignals(False); self.changed()

        def paste(self):
            if self.buffer is None: return
            text = W.QApplication.clipboard().text()
            rows = [line.split('\t') if '\t' in line else line.split(',') for line in text.splitlines() if line.strip()]
            if not rows or any(len(row) != 2 for row in rows):
                self.errors.setText('진응력, 소성변형률의 두 열을 복사하세요. 소수점은 점(.)을 사용합니다.'); return
            start = max(self.table.currentRow(), 0)
            if start+len(rows) > 10000:
                self.errors.setText('편집 표의 10,000점 한도를 초과합니다. 원 표는 변경하지 않았습니다.'); return
            self.table.blockSignals(True); self.table.setRowCount(max(self.table.rowCount(), start+len(rows)))
            for i, row in enumerate(rows, start):
                self.preserved_rows.pop(i, None)
                for j, text in enumerate(row): self.table.setItem(i, j, W.QTableWidgetItem(text))
            self.table.blockSignals(False); self.changed()

        def send(self, apply):
            aid, mid = self.loaded or (None, None)
            if not aid or not mid or self.selected() != self.loaded: raise ValueError('현재 해석과 기본 재료를 선택하세요.')
            draft = self.current_draft(); serial = panel._edit_serial
            errors = service.draft_errors(draft) if apply else []
            if errors:
                self.update_state(); self.errors.setFocus(); return
            def done(value):
                if self.selected() != (aid, mid): raise ValueError('STALE_SELECTION: 재료 선택이 변경됐습니다.')
                if panel._edit_serial != serial:
                    self.errors.setText('제출한 표는 저장됐습니다. 이후 편집은 그대로 남아 있습니다.'); return
                self.modified = False; self.info = value; self.buffer = deepcopy(value['draft']); self.populate()
                panel.status.setPlainText('재료를 적용했습니다. 계산은 실행하지 않았습니다.' if apply else '초안을 보존했습니다. 파일 재열기는 프로젝트 저장 후 가능합니다.')
            panel._send('pre.fem.plasticity_apply' if apply else 'pre.fem.plasticity_save',
                        {'analysis_id': aid, 'draft': draft}, mid, on_done=done)

        def discard(self):
            self.modified = False; self.load()

        def solvers(self):
            aid = self.analysis.currentData()
            return [obj for obj in panel.editor.owner._object(aid).Group if service.native_type(obj) == 'Fem::SolverCcxTools' and not getattr(obj, 'Suppressed', False)] if aid else []

        def geometry_pending(self):
            return self.geometry_source is not None and self.nlgeom.isChecked() != self.geometry_source

        def elastic_pending(self):
            if not self.loaded or not self.loaded[1] or self.buffer is None: return False
            try:
                base = panel.editor.owner._object(self.loaded[1])
                young = panel.editor.owner.App.Units.Quantity(base.Material['YoungsModulus']).getValueAs('MPa').Value
                poisson = float(base.Material['PoissonRatio'])
                return not (math.isclose(panel.modulus.value(), young, rel_tol=5e-15, abs_tol=1e-9) and
                            math.isclose(panel.poisson.value(), poisson, rel_tol=5e-15, abs_tol=1e-9))
            except (AttributeError, KeyError, TypeError, ValueError):
                return False  # Unresolved native values still fail the owner run gate.

        def pending_changes(self):
            return self.modified or self.geometry_pending() or self.elastic_pending()

        def geometry_caption(self, *_):
            prefix = '미적용 설정 — ' if self.geometry_pending() else ''
            self.strain_meaning.setText(prefix+('E 출력: Green–Lagrange 변형률' if self.nlgeom.isChecked() else 'E 출력: 미소 변형률'))
            self.strain_meaning.setToolTip('선택한 기하 설정을 적용한 뒤 실행합니다. 정적 단계 진행값은 초(s)가 아닙니다. STABILIZE와 범용 line search는 지원하지 않습니다.')

        def apply_geometry(self):
            solvers = self.solvers()
            if len(solvers) != 1: raise ValueError('활성 CalculiX 설정 하나를 지정하세요.')
            submitted = self.nlgeom.isChecked()
            def done(value):
                self.geometry_source = submitted
                self.geometry_caption()
                panel.status.setPlainText('기하 설정을 적용했습니다. 증분은 해석 단계에서 편집하세요.')
            panel._send('pre.fem.nonlinear_settings', {'nlgeom': submitted}, solvers[0].Name, on_done=done)

        def follow_selection(self):
            if self.pending_changes(): raise ValueError('미적용 재료와 기하 설정을 확인한 뒤 선택을 바꾸세요.')
            identifier, names = panel._selection(); obj = panel.editor.owner._object(identifier)
            candidates = []
            aid = self.analysis.currentData()
            if not aid: raise ValueError('해석을 선택하세요.')
            for base in panel.editor.owner._object(aid).Group:
                if service.native_type(base) != 'Fem::MaterialCommon' or getattr(base, 'Category', None) != 'Solid': continue
                if base is obj or any(source is obj for source, refs in getattr(base, 'References', [])): candidates.append(base)
            if not candidates and hasattr(obj, 'Shape'):
                candidates = [base for base in panel.editor.owner._object(aid).Group if service.native_type(base) == 'Fem::MaterialCommon' and not getattr(base, 'References', [])]
            if len(candidates) != 1: raise ValueError('선택한 body에 기본 재료를 하나 명시 지정하거나 재료 객체를 선택하세요.')
            panel.material.setCurrentIndex(panel.material.findData(candidates[0].Name))

    return Page()
