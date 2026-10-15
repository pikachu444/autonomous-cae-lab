"""C1 pressure regressions. Native properties/geometry are explicit doubles.

The SHA-checked FreeCAD 1.1.4 Python writer functions themselves are executed;
this is not a FreeCAD process, a CalculiX solve, or Windows acceptance.
"""
from copy import deepcopy
import json
import pytest

from b13_shell_fixture import model
from test_shell_edit import OwnerDouble
from test_b13_native_boundaries import editor, Editor, reference_writers
from caelab.shell_model import validate_draft, prepare_mesh, ShellError
from caelab.shell_regions import reverse_region
from caelab.adapters.shell_deck import build, sections
from apps.desktop_pre.shell_freeze import _native_fragments


def source_mesh(m):
    return ({int(k): v for k, v in m['source_nodes'].items()},
            {int(k): v for k, v in m['source_elements'].items()})


def fragments(editor, monkeypatch):
    reference_writers(monkeypatch)
    aid = editor.m['draft']['analysis_id']
    editor.apply(aid)
    record, prepared, _ = editor.effective(aid)
    section, pressure, material = _native_fragments(editor, record['draft'], prepared)
    result = deepcopy(editor.m)
    result.update(draft=record['draft'], applied=record['applied'], native_sections=section,
                  native_pressure=pressure, native_material=material,
                  material_name=record['draft']['material_id'])
    return result, prepared


@pytest.mark.parametrize('zero', ['0', '-0'])
@pytest.mark.parametrize('load', ['0.001', '-0.001'])
@pytest.mark.parametrize('zero_row', [0, 1])
@pytest.mark.parametrize('flip_zero', [False, True])
def test_regional_zero_validate_prepare_apply_real_python_writer_build_and_fresh_owner(
        editor, monkeypatch, zero, load, zero_row, flip_zero):
    aid = editor.m['draft']['analysis_id']
    draft = editor.owner.data['shells'][aid]['draft']
    draft['regions'][zero_row]['pressure_MPa'] = zero
    draft['regions'][1-zero_row]['pressure_MPa'] = load
    if flip_zero:
        draft = reverse_region(draft, draft['regions'][zero_row]['id'])
        editor.owner.data['shells'][aid]['draft'] = draft
    before = deepcopy(draft)
    assert validate_draft(draft)[0] == []
    prepared = prepare_mesh(*source_mesh(editor.m), draft)
    assert draft == before
    assert len(prepared['values_by_element']) == 2
    result, prepared = fragments(editor, monkeypatch)
    text, checked = build(result)
    rows = sections(result['native_pressure'])[0][2]
    assert len(rows) == len(draft['elements'])
    loads = {int(r.split(',')[0]): float(r.split(',')[2]) for r in rows}
    for index, row in enumerate(draft['regions']):
        for e in row['elements']:
            assert loads[e] == -float(row['pressure_MPa'])
            assert checked['values_by_element'][e]['offset'] == float(row['offset'])
    assert set(loads) == set(draft['elements'])
    assert '*DLOAD' in text
    old = deepcopy(editor.owner.data)
    owner = OwnerDouble(json.loads(json.dumps(old)))
    owner.doc, owner.App = editor.owner.doc, editor.owner.App
    fresh = Editor(owner, editor.m)
    assert fresh.effective(aid)[0] == old['shells'][aid]
    assert fresh._record(aid)['draft']['regions'][zero_row]['pressure_MPa'] == before['regions'][zero_row]['pressure_MPa']
    assert owner.data == old


@pytest.mark.parametrize('zero', ['0', '-0'])
def test_all_regional_zero_and_legacy_uniform_zero_still_fail_validate_prepare(zero):
    m = model(); draft = m['draft']
    for row in draft['regions']:
        row['pressure_MPa'] = zero
    for d in (draft, {k: v for k, v in dict(draft, pressure_MPa=zero).items() if k != 'regions'}):
        assert validate_draft(d)[0]
        with pytest.raises(ShellError):
            prepare_mesh(*source_mesh(m), d)


def test_opposite_signed_loads_do_not_become_a_no_load_model():
    m = model(); draft = m['draft']
    draft['regions'][0]['pressure_MPa'] = '0.75'
    draft['regions'][1]['pressure_MPa'] = '-0.75'
    assert validate_draft(draft)[0] == []
    assert sum(float(r['pressure_MPa']) for r in draft['regions']) == 0
    assert prepare_mesh(*source_mesh(m), draft)


@pytest.mark.parametrize('raw', ['', '1e', 'NaN', 'Inf', '-Infinity', '1e999'])
def test_invalid_raw_pressure_survives_save_but_apply_prepare_and_effective_fail(editor, raw):
    aid = editor.m['draft']['analysis_id']; editor.apply(aid)
    original = deepcopy(editor._record(aid)['applied'])
    rows = deepcopy(editor._record(aid)['draft']['regions']); rows[0]['pressure_MPa'] = raw
    editor.save_draft(aid, {'regions': rows})
    assert editor._record(aid)['draft']['regions'][0]['pressure_MPa'] == raw
    assert editor._record(aid)['applied'] == original
    count = len(editor.owner.transactions)
    for action in (lambda: editor.apply(aid), lambda: editor.effective(aid),
                   lambda: prepare_mesh(*source_mesh(editor.m), editor._record(aid)['draft'])):
        with pytest.raises(ShellError):
            action()
    assert len(editor.owner.transactions) == count
    assert editor._record(aid)['applied'] == original


@pytest.mark.parametrize('fault', ['nonzero', 'missing', 'duplicate', 'wrong_element', 'wrong_sign'])
def test_exact_native_zero_and_nonzero_pressure_rows_cannot_be_tampered(editor, monkeypatch, fault):
    aid = editor.m['draft']['analysis_id']
    editor.owner.data['shells'][aid]['draft']['regions'][0]['pressure_MPa'] = '-0'
    result, _ = fragments(editor, monkeypatch)
    assert build(result)
    entries = sections(result['native_pressure'])[0][2]
    if fault == 'nonzero': entries[0] = entries[0].rsplit(',', 1)[0] + ', 1e-12'
    if fault == 'missing': entries.pop(0)
    if fault == 'duplicate': entries.append(entries[0])
    if fault == 'wrong_element': entries[0] = '99999,' + entries[0].split(',', 1)[1]
    if fault == 'wrong_sign':
        prefix, value = entries[1].rsplit(',', 1); entries[1] = prefix + ', ' + str(-float(value))
    result['native_pressure'] = '*DLOAD\n' + '\n'.join(entries) + '\n'
    with pytest.raises(ValueError): build(result)


def test_import_native_section_without_pressure_then_apply_keeps_explicit_zero(editor, monkeypatch):
    from apps.desktop_pre.shell_region_native import import_properties
    aid = editor.m['draft']['analysis_id']; editor.apply(aid)
    before = deepcopy(editor._record(aid))
    pid = before['draft']['regions'][0]['pressure_id']
    pressure = editor._object(pid)
    editor._object(aid).Group.remove(pressure)
    del editor.owner.doc.objects[pid]
    import_properties(editor, aid)
    imported = editor._record(aid)
    assert imported['draft']['regions'][0]['pressure_id'] == ''
    assert imported['draft']['regions'][0]['pressure_MPa'] == '0'
    assert imported['draft']['binding'] == before['draft']['binding']
    result, _ = fragments(editor, monkeypatch)
    assert result['draft']['regions'][0]['pressure_MPa'] == '0'
    assert result['applied']['native']['regions'][0]['pressure_MPa'] == 0
    assert build(result)
