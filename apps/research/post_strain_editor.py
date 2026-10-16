"""Finite strain declarations inside the existing comparison detail dialog."""
from PySide6.QtWidgets import QLabel, QCheckBox, QWidget, QFormLayout
from .post_stress_editor import stress_page
from caelab.post_strain_measures import LABELS


def strain_page(editor, draft, tabs, combo, line):
    if not any(draft[s].get('quantity') == 'strain' for s in ('a', 'b')) and 'strain_conversion' not in draft:
        return lambda: None
    commit_gradient = stress_page(editor, draft, tabs, combo, line, strain=True)
    form = tabs.widget(tabs.count() - 1).layout()
    fields = {}
    for side in ('a', 'b'):
        value = draft[side]; stored = value.get('strain_precision') or {}
        metadata, _ = editor.metadata(value['source_ref'])
        row = next((r for r in metadata.get('arrays', [])
            if (r['name'], r['association']) == (value['array'], value['association'])), {})
        measure = combo([('원 측도 미지정', None)] + [(label, key) for key, label in LABELS.items()], value.get('measure'))
        measure.setObjectName(side + 'StrainMeasure'); measure.setEnabled(not bool(row.get('measure')))
        role = QCheckBox('동일 전체 변형의 total strain')
        role.setChecked(value.get('strain_role') == 'total'); role.setObjectName(side + 'StrainTotal')
        role.setEnabled(row.get('strain_role') is None)
        reference = line(value.get('reference_configuration')); reference.setObjectName(side + 'StrainReference')
        reference.setReadOnly(row.get('reference_configuration') is not None)
        form.addRow(QLabel(side.upper() + ' 원 변형률 정의'))
        form.addRow('원 측도', measure); form.addRow(role); form.addRow('기준 배치 이름', reference)
        if row.get('strain_role') not in (None, 'total'):
            text = QLabel('원 자료의 변형률 종류: ' + str(row['strain_role']) + ' — 전체 변형 F와 비교할 수 없습니다.')
            text.setWordWrap(True); form.addRow(text)
        changed = [False, False, False, False]
        measure.currentIndexChanged.connect(lambda *args, flag=changed: flag.__setitem__(0, True))
        role.toggled.connect(lambda *args, flag=changed: flag.__setitem__(1, True))
        reference.textEdited.connect(lambda *args, flag=changed: flag.__setitem__(2, True))
        precision_group = QWidget(); precision_form = QFormLayout(precision_group)
        precision_form.setContentsMargins(0, 0, 0, 0)
        heading = QLabel(side.upper() + ' C 정합 오차 근거 (F 선택 시 필수)')
        heading.setWordWrap(True); precision_form.addRow(heading)
        controls = {}
        for key, label in [('absolute_tolerance', 'C 절대 허용값 [1]'),
                ('relative_tolerance', 'C 상대 허용값 [1]'), ('producer', '원 출력 프로그램'),
                ('format', '배열과 출력 형식'), ('reference', '오차 근거 참조')]:
            field = line(stored.get(key)); field.setObjectName(side + 'Strain' + key)
            field.setReadOnly(row.get('strain_precision') is not None)
            precision_form.addRow(label, field); controls[key] = field
            field.textEdited.connect(lambda *args, flag=changed: flag.__setitem__(3, True))
        form.addRow(precision_group)
        use_f = tabs.widget(tabs.count()-1).findChild(QCheckBox, side+'UseGradient')
        precision_group.setVisible(use_f.isChecked()); use_f.toggled.connect(precision_group.setVisible)
        def require_f(*args, measure=measure, use_f=use_f):
            required = measure.currentData() == 'euler_almansi'
            use_f.setEnabled(not required)
            if required: use_f.setChecked(True)
        measure.currentIndexChanged.connect(require_f)
        fields[side] = (measure, role, reference, controls, changed)
    note = QLabel('F와의 정합은 기준 C의 Frobenius 오차 <= 절대값 + 상대값 × 두 C의 큰 norm으로 검사합니다. 원 출력의 정합 보증 오차와 근거를 명시하며 native 검증으로 간주하지 않습니다. C 허용값으로 비대칭이나 평균된 F를 통과시키지 않습니다. F 없는 E/H 변환은 이 오차 입력이 불필요합니다.')
    note.setWordWrap(True); form.addRow(note)
    def commit():
        commit_gradient()
        for side, (measure, role, reference, controls, changed) in fields.items():
            if changed[0]: draft[side]['measure'] = measure.currentData()
            if changed[1]: draft[side]['strain_role'] = 'total' if role.isChecked() else None
            if changed[2]: draft[side]['reference_configuration'] = reference.text()
            if not changed[3]: continue
            precision = {'kind': 'declared_C_bound'}
            for key, field in controls.items():
                value = field.text()
                if key in ('absolute_tolerance', 'relative_tolerance'):
                    try: value = float(value)
                    except ValueError: pass
                precision[key] = value
            draft[side]['strain_precision'] = precision
    return commit
