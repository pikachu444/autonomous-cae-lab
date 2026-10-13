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
    assert '3DELEM_DAMAGE' not in values
    assert read_vtk(path)['CELLS']['3DELEM_DAMAGE']['values']==[0.,.75]
    assert metadata['time']['values']==[.25]
    assert all(a['name']!='3DELEM_DAMAGE' for a in metadata['arrays']) # unknown law/units stay unknown
    assert 'NOT_RECORDED_BY_CONVERTER' in (tmp_path/'post/frames.json').read_text(encoding='utf-8')


def test_truncated_and_fake_cell_identity_rejected(tmp_path):
    p=tmp_path/'bad.vtk';p.write_text(vtk().replace('0 0.75','0'),encoding='ascii')
    with pytest.raises(ValueError,match='Truncated'):read_vtk(p)


def test_middle_native_gap_retains_quality_and_disconnected_segments(tmp_path):
    path=tmp_path/'gaps.csv'
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['time',*GLOBAL_NAMES])
        for i in range(3):writer.writerow([i*.001,*( ['nan' if i==1 else 1.]+[1.]*22)])
    responses,_=history(path);response=responses['global_1']
    assert response['source_rows']==[2,4] and response['has_calculation_gaps']
    assert [s['rows'] for s in response['segments']]==[[0,1],[1,2]]
    assert response['raw_samples']['quality_valid']==[True,False,True]
    assert response['raw_samples']['raw_values'][1]=='nan'


def test_native_element_identity_cannot_be_reassigned_by_membership_only(tmp_path):
    from caelab.adapters.impact_results import validate_frame_identity
    path=tmp_path/'f.vtk';path.write_text(vtk(),encoding='ascii')
    raw=read_vtk(path)
    raw['CELLS']['PART_ID']={'components':1,'values':[1.,2.]}
    model={'nodes':{i:[] for i in range(1,9)},
           'elements':{11:{'nodes':[1,2]},12:{'nodes':[5,6,7,8]}}}
    with pytest.raises(ValueError,match='connectivity'):
        validate_frame_identity(raw,model,{'part_by_element':{'11':1,'12':2}})
