import csv
from pathlib import Path
import pytest
from caelab.adapters.impact_results import history,GLOBAL_NAMES,read_vtk,write_post


def test_actual_rows_and_invalid_energy_are_not_zero(tmp_path):
    file=tmp_path/'history.csv'
    with file.open('w',encoding='utf-8',newline='') as stream:
        w=csv.writer(stream);w.writerow(['time',*GLOBAL_NAMES])
        for t in (0.,.001):
            values=[1.]*23
            if t==.001:values[0]='nan'
            w.writerow([t,*values])
    responses,raw=history(file)
    assert responses['global_1']['value']==[.001]
    assert responses['global_1']['metadata']['invalid_source_rows']==[3]
    assert responses['global_6']['value']==[1000.,1000.]
    assert raw['rows'][1]['tokens'][1]=='nan'
    assert 'global_23' not in responses


def vtk():
    return """# vtk DataFile Version 3.0
synthetic converter contract test double
ASCII
DATASET UNSTRUCTURED_GRID
FIELD FieldData 2
TIME 1 1 double
0.25
CYCLE 1 1 int
0
POINTS 4 float
0 0 0 1 0 0 0 1 0 0 0 1
CELLS 2 8
2 0 1
4 0 1 2 3
CELL_TYPES 2
3 10
POINT_DATA 4
SCALARS NODE_ID int 1
LOOKUP_TABLE default
1 2 3 4
CELL_DATA 2
SCALARS ELEMENT_ID int 1
LOOKUP_TABLE default
11 12
SCALARS EROSION_STATUS int 1
LOOKUP_TABLE default
1 0
SCALARS 3DELEM_DAMAGE float 1
LOOKUP_TABLE default
0 0.75
"""


def test_padding_mask_and_eroded_cell_raw_value_survive_vtu(tmp_path):
    path=tmp_path/'frame.vtk';path.write_text(vtk(),encoding='ascii')
    raw=read_vtk(path);metadata=write_post(tmp_path/'post',[(path,raw)])
    from xml.etree import ElementTree as ET
    doc=ET.parse(tmp_path/'post/frame0000.vtu')
    values={a.get('Name'):a.text for a in doc.findall('.//CellData/DataArray')}
    assert values['3DELEM_DAMAGE_Applicable']=='0 1'
    assert values['EROSION_STATUS']=='1 0'
    assert values['3DELEM_DAMAGE']=='0 0.75'
    assert metadata['time']['values']==[.25]
    assert all(a['name']!='3DELEM_DAMAGE' for a in metadata['arrays']) # unknown law/units stay unknown
    assert 'NOT_RECORDED_BY_CONVERTER' in (tmp_path/'post/frames.json').read_text(encoding='utf-8')


def test_truncated_and_fake_cell_identity_rejected(tmp_path):
    p=tmp_path/'bad.vtk';p.write_text(vtk().replace('0 0.75','0'),encoding='ascii')
    with pytest.raises(ValueError,match='Truncated'):read_vtk(p)
