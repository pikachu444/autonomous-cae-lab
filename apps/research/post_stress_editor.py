"""Explicit same-reader F declarations inside the existing comparison dialog."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QFormLayout, QLabel, QCheckBox, QListWidget, QListWidgetItem


STRESS_LABELS = {
    'cauchy': 'Cauchy 응력', 'cauchy_stress': 'Cauchy 응력',
    'pk1': '제1 Piola 응력', 'first_piola': '제1 Piola 응력', 'first_piola_kirchhoff': '제1 Piola 응력',
    'pk2': '제2 Piola 응력', 'second_piola': '제2 Piola 응력', 'second_piola_kirchhoff': '제2 Piola 응력',
    'kirchhoff': 'Kirchhoff 응력', 'kirchhoff_stress': 'Kirchhoff 응력', 'tau': 'Kirchhoff 응력'}


def stress_page(editor, draft, tabs, combo, line, *, strain=False):
    key = 'strain_conversion' if strain else 'stress_conversion'
    target = 'green_lagrange' if strain else 'cauchy'
    labels = STRESS_LABELS
    if strain:
        from caelab.post_strain_measures import LABELS
        labels = LABELS
    definition = {'version': 1, 'target_measure': target}
    page = QWidget(); form = QFormLayout(page); tabs.addTab(page, '변형률 측도' if strain else '응력 측도')
    enabled = QCheckBox('원 변형률을 공통 기준 Green–Lagrange E로 변환' if strain else '원 응력을 공통 Cauchy 응력으로 변환')
    enabled.setObjectName('strainConversionEnabled' if strain else 'stressConversionEnabled')
    enabled.setChecked(draft.get(key) == definition)
    form.addRow(enabled)
    note = QLabel('원 A/B는 그대로 보존합니다. PK1·PK2·Kirchhoff는 같은 원 자료·시각·점/셀의 실제 F가 필요합니다. '
        'F의 행은 현재 기저, 열은 기준 기저입니다. 셀 평균·시간 보간 전에 변환하며 J=det(F)>0을 확인합니다.')
    if strain:
        note.setText('원 A/B는 보존합니다. Euler–Almansi는 실제 F가 필요합니다. E와 기준 Hencky는 F를 명시하면 C=FᵀF도 검사합니다. F는 현재 행 / 기준 열이며 셀 평균·시간 보간 전에 변환합니다.')
    note.setWordWrap(True); form.addRow(note)
    controls = {}; changed = [False]
    enabled.toggled.connect(lambda: changed.__setitem__(0, True))
    for side in ('a', 'b'):
        value = draft[side]; stored = value.get('deformation_gradient') or {}
        group = QWidget(); rows = QFormLayout(group); rows.setContentsMargins(0, 0, 0, 0)
        metadata, _ = editor.metadata(value['source_ref'])
        arrays = [r for r in metadata.get('arrays', []) if r.get('association') == value['association']]
        choices = [('F 배열 선택', None)] + [(r['name'], r['name']) for r in arrays if r.get('components') == 9 and r['name'] != value.get('array')]
        array = combo(choices, stored.get('array')); array.setObjectName(side + 'GradientArray')
        units = combo([('단위 미지정', None), ('무차원 [1]', '1')], stored.get('units'))
        orientation = combo([('행/열 방향 미지정', None), ('현재 행 / 기준 열', 'current_from_reference')], stored.get('orientation'))
        basis = combo([('기저 미지정', None), ('고정 직교 기저', 'fixed_cartesian')], stored.get('basis'))
        spatial = line(stored.get('spatial_frame')); material = line(stored.get('material_frame'))
        order = line(','.join(stored.get('layout', {}).get('components', [])))
        order.setPlaceholderText('실제 9성분 순서: xx,xy,xz,yx,yy,yz,zx,zy,zz')
        order.setToolTip('F의 실제 배열 순서를 입력하세요. 자동 전치나 대칭화를 하지 않습니다.')
        masks = QListWidget(); masks.setMaximumHeight(95)
        known_masks = list(stored.get('validity_masks', []))
        for name in dict.fromkeys([r['name'] for r in arrays if r.get('components') == 1] + known_masks):
            item = QListWidgetItem(name, masks); item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if name in known_masks else Qt.CheckState.Unchecked)
        pk1_material = line(value.get('material_frame')); pk1_material.setObjectName(side + 'StressMaterialFrame')
        rows.addRow('F 배열 (' + ('점 자료' if value['association'] == 'POINTS' else '셀 자료') + ')', array)
        for label, widget in [('F 단위', units), ('F 지표 방향', orientation), ('F 기저', basis),
                              ('현재 기저 이름', spatial), ('기준 기저 이름', material), ('F 성분 순서', order), ('F 유효성 배열', masks)]:
            rows.addRow(label, widget)
        if str(value.get('measure', '')).lower() in ('pk1', 'first_piola', 'first_piola_kirchhoff'):
            rows.addRow('원 PK1의 기준 열 기저', pk1_material)
        else:
            pk1_material.setParent(group); pk1_material.hide()
        is_cauchy = not strain and str(value.get('measure', '')).lower() in ('cauchy', 'cauchy_stress')
        heading = QLabel(side.upper() + ' 원 측도: ' + labels.get(str(value.get('measure', '')).lower(), str(value.get('measure') or '미지정')) + (' — F 불필요' if is_cauchy else ''))
        heading.setWordWrap(True); form.addRow(heading)
        use_f = None
        if strain:
            use_f = QCheckBox('실제 F와의 정합도 검사')
            use_f.setObjectName(side + 'UseGradient')
            use_f.setChecked(bool(stored) or value.get('measure') == 'euler_almansi')
            use_f.setEnabled(value.get('measure') != 'euler_almansi')
            form.addRow(use_f)
        form.addRow(group)
        def toggle(active, group=group, is_cauchy=is_cauchy, use_f=use_f):
            group.setVisible(not is_cauchy and (use_f is None or use_f.isChecked())); group.setEnabled(active and not is_cauchy)
        enabled.toggled.connect(toggle); toggle(enabled.isChecked())
        if use_f is not None: use_f.toggled.connect(lambda active, toggle=toggle: toggle(enabled.isChecked()))
        fields = {'array': array, 'units': units, 'orientation': orientation, 'basis': basis,
                  'spatial_frame': spatial, 'material_frame': material, 'order': order, 'masks': masks,
                  'pk1_material': pk1_material}
        def declared(name, fields=fields, arrays=arrays):
            row = next((r for r in arrays if r['name'] == name), {})
            for key, source in [('units', 'units'), ('orientation', 'orientation'), ('basis', 'basis'),
                                ('spatial_frame', 'frame'), ('material_frame', 'material_frame')]:
                widget = fields[key]; known = row.get(source)
                known = known if known not in ('', 'UNKNOWN') else None
                if known is not None:
                    if hasattr(widget, 'findData'):
                        index = widget.findData(known)
                        if index < 0: widget.addItem(str(known), known); index = widget.count() - 1
                        widget.setCurrentIndex(index)
                    else: widget.setText(str(known))
                widget.setEnabled(known is None)
            layout = row.get('layout')
            if layout: fields['order'].setText(','.join(layout.get('components', [])))
            fields['order'].setEnabled(not bool(layout))
            if 'validity_masks' in row or row.get('spatial_mask'):
                required = list(row.get('validity_masks') or [])
                if row.get('spatial_mask') and row['spatial_mask'] not in required:
                    required.append(row['spatial_mask'])
                for name in required:
                    if not any(fields['masks'].item(i).text() == name for i in range(fields['masks'].count())):
                        item = QListWidgetItem(name, fields['masks'])
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                for i in range(fields['masks'].count()):
                    item = fields['masks'].item(i)
                    item.setCheckState(Qt.CheckState.Checked if item.text() in required else Qt.CheckState.Unchecked)
            fields['masks'].setEnabled('validity_masks' not in row and not row.get('spatial_mask'))
        array.currentIndexChanged.connect(lambda i, a=array, apply=declared: apply(a.currentData()))
        # Stored values stay byte-for-byte draft values until explicit editing;
        # known declarations are enforced by the owner even for old invalid drafts.
        side_changed = [False]
        def edited(*args, flag=side_changed):
            flag[0] = True; changed[0] = True
        for widget in (array, units, orientation, basis):
            widget.currentIndexChanged.connect(edited)
        for widget in (spatial, material, order, pk1_material):
            widget.textEdited.connect(edited)
        masks.itemChanged.connect(edited)
        if use_f is not None:
            use_f.toggled.connect(edited)
            fields['use_f'] = use_f
        controls[side] = (fields, is_cauchy, side_changed)
    def commit():
        if not changed[0]: return
        if not enabled.isChecked():
            draft.pop(key, None); return
        draft[key] = definition
        for side, (fields, is_cauchy, edited) in controls.items():
            if is_cauchy or not edited[0]: continue
            if fields.get('use_f') is not None and not fields['use_f'].isChecked():
                draft[side].pop('deformation_gradient', None); continue
            selected = fields['array'].currentData()
            if selected is None:
                draft[side].pop('deformation_gradient', None); continue
            draft[side]['deformation_gradient'] = {
                'array': selected, 'association': draft[side]['association'], 'units': fields['units'].currentData(),
                'orientation': fields['orientation'].currentData(), 'basis': fields['basis'].currentData(),
                'spatial_frame': fields['spatial_frame'].text(), 'material_frame': fields['material_frame'].text(),
                'layout': {'kind': 'tensor', 'components': [p.strip() for p in fields['order'].text().split(',') if p.strip()],
                           'shear': 'tensor', 'indices': 'spatial_material_basis'},
                'validity_masks': [fields['masks'].item(i).text() for i in range(fields['masks'].count())
                                   if fields['masks'].item(i).checkState() == Qt.CheckState.Checked]}
            if str(draft[side].get('measure', '')).lower() in ('pk1', 'first_piola', 'first_piola_kirchhoff'):
                draft[side]['material_frame'] = fields['pk1_material'].text()
    return commit
