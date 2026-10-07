"""A suggested layout must round-trip through the actual numeric reader."""
import pytest

from caelab.adapters.file_table import preview_table, read_table
from caelab.workbench import Workbench


@pytest.mark.parametrize('body,delimiter,skip', [
    ('시간 (s),측정 힘 (N)\n0,1\n1,2\n2,3\n', ',', 1),
    ('# measured public example\n시간;힘\n0;1\n1;2\n2;3\n', ';', 2),
    ('0\t1\n1\t2\n2\t3\n', '\t', 0),
    ('0 1D+00\n1 2D+00\n2 3D+00\n', None, 0),
    ('\ufeff0,1\n1,2\n2,3\n', ',', 0),
    ('0,1 # first\n1,2\n# comment\n2,3\n', ',', 0),
])
def test_confirmed_preview_indices_read_original_numeric_data(tmp_path, body, delimiter, skip):
    bench=Workbench(tmp_path/'workspace')
    try:
        receipt=bench.upload('시험 자료.csv', body.encode('utf-8'))
        preview=bench.input_preview(receipt['id'])['table_preview']
        assert preview['column_keys']==[0,1]
        assert preview['skip_rows']==skip
        # Units/meaning are supplied by the user, never inferred by preview.
        assert not {'units','component','location'} & preview.keys()
        mapping={'delimiter':delimiter,'skip_header':preview['skip_rows'],'columns':{
            'force':{'column':preview['column_keys'][1],'unit':'N','component':'Fz',
                     'location':'sensor','axis':{'column':preview['column_keys'][0],
                                                'name':'time','unit':'s'}}}}
        actual=read_table(bench.input_path(receipt['id']),mapping)['responses']['force']
        assert actual['value'].tolist()==[1.,2.,3.]
        assert actual['axes'][0]['values'].tolist()==[0.,1.,2.]
    finally:
        bench.shutdown()


def test_bounded_preview_does_not_advertise_cut_row_or_document_as_numeric():
    assert preview_table('A research document\nNo numeric measurements here\n') is None
    sample=preview_table('time,force\n0,1\n1,234',truncated=True)
    assert sample['rows']==[['0','1']]
    assert sample['truncated'] is True
    sample=preview_table('time,force\n'+''.join(f'{i},{i+1}\n' for i in range(30)))
    assert len(sample['rows'])==8 and sample['truncated']


def test_input_preview_is_bounded_and_preserves_stored_source(tmp_path):
    bench=Workbench(tmp_path/'workspace')
    try:
        payload=b'\xef\xbb\xbftime,force\n'+b'0,1\n'*6000
        receipt=bench.upload('large.csv',payload)
        result=bench.input_preview(receipt['id'])
        assert len(result['text'])<=16384 and result['truncated']
        assert result['table_preview']['headers']==['time','force']
        assert bench.input_path(receipt['id']).read_bytes()==payload
    finally:
        bench.shutdown()


@pytest.mark.parametrize('invalid', ['nan', 'inf', '-inf'])
def test_nonfinite_first_record_is_never_discarded_as_header(tmp_path, invalid):
    body=f'0,{invalid}\n1,2\n2,3\n'
    preview=preview_table(body)
    assert preview['skip_rows']==0 and not preview['has_header']
    path=tmp_path/'invalid.csv'
    path.write_text(body,encoding='utf-8')
    with pytest.raises(ValueError,match='nonfinite'):
        read_table(path,{'delimiter':',','skip_header':preview['skip_rows'],'columns':{
            'force':{'column':1,'unit':'N','component':'Fz','location':'sensor'}}})


@pytest.mark.parametrize('body', [
    '0,broken\n1,2\n2,3\n',
    '"0","1"\n"1","2"\n',
    '0,1\n$ unsupported comment\n1,2\n',
    '0,1\n! unsupported comment\n1,2\n',
])
def test_unsupported_or_broken_records_receive_no_automatic_layout(body):
    assert preview_table(body) is None
