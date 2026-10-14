"""Required beam fields and optional native ERROR stay distinct."""
import json
import pytest

from caelab.beam_deck import render, matches_saved_input
from caelab.beam_results import read_frd, channels, post_metadata
from caelab.adapters.beam_fem import validate_snapshot
from caelab.storage import save_json
from test_beam_support import model, frd, snapshot


def with_error(value=None, times=(1.,)):
    value = value or model()
    lines = frd(value, times).splitlines(keepends=True)
    count = 0
    for i, line in enumerate(lines):
        if line.split()[:1] == ['1PSTEP']:
            count += 1
    header = next(line for line in reversed(lines) if line.split()[:1] == ['100CL'])
    inc = len(times)
    block = ['    1PSTEP' + ' '*14 + f'{count+1:12d}{inc:12d}{1:12d}' + ' '*10 + '\n',
             header, ' -4 ERROR 1 1\n', ' -5 STR(%) 1 1 0 0\n']
    block += [' -1' + f"{node['id']:10d}{65.:12.5E}\n" for node in sorted(value['nodes'], key=lambda n:n['id'])]
    block.append(' -3\n')
    return ''.join(lines[:-1] + block + lines[-1:])


def read(tmp_path, text, **options):
    path = tmp_path/'beam.frd'
    path.write_bytes(text.encode('ascii'))
    return read_frd(path, model(), **options)


def test_optional_error_preserves_raw_values_without_becoming_stress_or_a_verdict(tmp_path):
    observed = read(tmp_path, with_error())
    frame = observed['frames'][0]
    assert observed['complete_file'] and frame['native_fields']['ERROR'][101] == [65.]
    assert set(channels(frame)) == set(channels(read(tmp_path, frd(model()))['frames'][0]))
    metadata = post_metadata(observed, model(), source_status='FAILED')
    assert metadata['beam']['observation_status'] == 'PARTIAL'
    assert metadata['beam']['engineering_valid'] is False


def test_optional_error_on_final_increment_does_not_merge_prior_frame(tmp_path):
    observed = read(tmp_path, with_error(times=(.5,1.)))
    first, final = observed['frames']
    assert first['static']['load_parameter'] == .5 and 'ERROR' not in first['native_fields']
    assert final['static']['load_parameter'] == 1. and final['native_fields']['ERROR'][101] == [65.]
    assert channels(first)['M1']['values'][101] == 27.5
    assert channels(final)['M1']['values'][101] == 55.


@pytest.mark.parametrize('cut', ['header', 'label', 'value', 'terminator'])
def test_torn_optional_final_block_keeps_complete_required_frame_partial(tmp_path, cut):
    text = with_error()
    if cut == 'header':
        text = text[:text.index(' -4 ERROR')] + ' -4 ER'
    elif cut == 'label':
        text = text[:text.index(' -5 STR(%)')] + ' -5 STR'
    elif cut == 'value':
        start = text.index(' -4 ERROR')
        index = text.index(' -1', start)
        text = text[:index] + ' -1       101 6.5'
    else:
        text = text[:text.rindex(' -3')]
    with pytest.raises(ValueError):
        read(tmp_path, text)
    observed = read(tmp_path, text, allow_partial=True)
    assert not observed['complete_file'] and len(observed['frames']) == 1
    assert 'ERROR' not in observed['frames'][0]['native_fields']


@pytest.mark.parametrize('damage', ['label', 'duplicate', 'foreign', 'nonfinite', 'parameter', 'unknown'])
def test_optional_field_corruption_is_never_admitted_as_partial(tmp_path, damage):
    text = with_error()
    start = text.index(' -4 ERROR')
    head, tail = text[:start], text[start:]
    if damage == 'label': tail = tail.replace('STR(%) 1 1 0 0', 'STR(%) 1 1 1 0')
    elif damage == 'duplicate':
        row = next(line for line in tail.splitlines(keepends=True) if line.startswith(' -1'))
        tail = tail.replace(row, row+row, 1)
    elif damage == 'foreign': tail = tail.replace(' -1       101', ' -1       102', 1)
    elif damage == 'nonfinite': tail = tail.replace(' 6.50000E+01', '         NaN', 1)
    elif damage == 'parameter': head = head[:head.rindex('  100CL')] + head[head.rindex('  100CL'):].replace(' 1.000000000', ' 0.900000000', 1)
    else: tail = tail.replace('ERROR', 'OTHER', 1)
    with pytest.raises(ValueError):
        read(tmp_path, head+tail, allow_partial=True)


def test_original_static_deck_remains_readable_and_only_that_exact_legacy_form(tmp_path):
    source = snapshot(tmp_path/'frozen')
    value = json.loads((source.parent/'mesh.json').read_text(encoding='utf-8'))
    current = render(value)
    legacy = current.replace('*STATIC\n1.,1.,1.e-6,1.e30\n', '*STATIC\n1.,1.\n')
    assert matches_saved_input(current, value) and matches_saved_input(legacy, value)
    assert not matches_saved_input(legacy.replace('1000', '2000'), value)
    assert not matches_saved_input(current.replace('1.e-6', '1.e-5'), value)
    path = source.parent/'beam.inp'; path.write_bytes(legacy.encode('ascii'))
    from caelab.beam_results import sha
    manifest = json.loads(source.read_text(encoding='utf-8'))
    entry = next(row for row in manifest['files'] if row['relative'] == 'beam.inp')
    entry.update(bytes=path.stat().st_size, sha256=sha(path))
    save_json(source, manifest)
    assert validate_snapshot(source)[1] == value
