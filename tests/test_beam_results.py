from copy import deepcopy
from pathlib import Path
import json
import pytest
from test_beam_support import model,frd
from caelab.beam_results import read_frd,channels,write_post,final_responses


def read(tmp_path,text,**options):
    path=tmp_path/'beam.frd';path.write_bytes(text.encode('ascii'))
    return read_frd(path,model(),**options)


def test_separate_units_axes_and_native_component_order(tmp_path):
    observed=read(tmp_path,frd(model()));ch=channels(observed['frames'][0])
    for key,expected,unit in [('V1',11,'N'),('V2',22,'N'),('N',33,'N'),('Mt',44,'Nmm'),('M1',55,'Nmm'),('M2',66,'Nmm')]:
        assert ch[key]['values'][101]==expected and ch[key]['unit']==unit
    assert ch['M1']['source_component']=='SYZ' and ch['M2']['source_component']=='SZX'
    responses=final_responses(observed,model());assert all(v['unit']!='MPa' for v in responses.values())
    assert not any('mises' in k.lower() or 'rotation' in k.lower() for k in responses)
    assert responses['M1']['metadata']['node_ids']==[101,207,408,509,913]
    assert observed['frd_elements']=={23:[207,509,913],88:[101,207,408]}


@pytest.mark.parametrize('ending',['','9','99','999'])
def test_torn_only_end_marker_retains_complete_frame_as_partial(tmp_path,ending):
    text=frd(model()).rsplit(' 9999',1)[0]+ending
    with pytest.raises(ValueError):read(tmp_path,text)
    observed=read(tmp_path,text,allow_partial=True)
    assert not observed['complete_file'] and len(observed['frames'])==1
    assert (tmp_path/'beam.frd').read_text()==text


@pytest.mark.parametrize('cut',['number','component','field','step','header'])
def test_torn_second_increment_never_mixes_fields(tmp_path,cut):
    text=frd(model(),(.5,1.));lines=text.splitlines(keepends=True)
    starts=[i for i,l in enumerate(lines) if l.split()[:1]==['1PSTEP']]
    i=starts[3] if cut in ('step','header') else starts[4]
    if cut=='step':text=''.join(lines[:i])+lines[i][:38]
    elif cut=='header':text=''.join(lines[:i+1])+lines[i+1][:33]
    elif cut=='field':text=''.join(lines[:i+2])+lines[i+2][:7]
    elif cut=='component':text=''.join(lines[:i+3])+lines[i+3][:11]
    else:
        j=next(j for j in range(i+3,len(lines)) if lines[j].startswith(' -1'))
        text=''.join(lines[:j+1])+lines[j+1][:22]
    observed=read(tmp_path,text,allow_partial=True)
    assert len(observed['frames'])==1 and observed['frames'][0]['static']['load_parameter']==.5


@pytest.mark.parametrize('damage',['version','foreign_node','topology','type3d','unit_label','nan','corrupt_middle','duplicate','footer_mid','incomplete_terminated'])
def test_corruption_is_not_admitted_as_partial(tmp_path,damage):
    text=frd(model())
    if damage=='version':text=text.replace('Version 2.22','Version 2.23')
    elif damage=='foreign_node':text=text.replace(' -1       101',' -1       102')
    elif damage=='topology':text=text.replace(' -2       207       509       913',' -2       207       913       509')
    elif damage=='type3d':text=text.replace('   12    0    1','    4    0    1')
    elif damage=='unit_label':text=text.replace('SZX 1 4 3 1','SZX 1 4 1 3')
    elif damage=='nan':text=text.replace(' 1.10000E+01','         NaN')
    elif damage=='corrupt_middle':text=text.replace(' 1.10000E+01',' 1.1XXXXX+01')
    elif damage=='duplicate':
        row=next(l for l in text.splitlines(True) if l.startswith(' -1       101'))
        text=text.replace(row,row+row,1)
    elif damage=='footer_mid':text=text.replace('    1PSTEP',' 999\n    1PSTEP',1)
    else:
        lines=text.splitlines(True);i=next(i for i,l in enumerate(lines) if ' -4 STRESS' in l);j=next(j for j in range(i,len(lines)) if lines[j].startswith(' -1'))
        del lines[j];text=''.join(lines)
    with pytest.raises(ValueError):read(tmp_path,text,allow_partial=True)


def test_vtk_real_reader_line_order_and_distinct_scalar_arrays(tmp_path):
    vtk=pytest.importorskip('vtk')
    observed=read(tmp_path,frd(model()));artifact=write_post(tmp_path/'post',observed,model(),source_status='SUCCEEDED')
    reader=vtk.vtkXMLUnstructuredGridReader();reader.SetFileName(str(tmp_path/'post'/'beam_0000.vtu'));reader.Update()
    grid=reader.GetOutput();assert grid.GetNumberOfCells()==2 and grid.GetCellType(0)==21
    ids=grid.GetPointData().GetArray('NativeNodeId')
    assert [int(ids.GetTuple1(grid.GetCell(0).GetPointId(j))) for j in range(3)]==[207,509,913]
    assert grid.GetPointData().GetArray('STRESS') is None
    assert grid.GetPointData().GetArray('M1').GetTuple1(0)==55
    metadata=artifact['native_metadata'];declared={r['name']:r['units'] for r in metadata['arrays']}
    assert declared['M1']=='Nmm' and declared['N']=='N' and declared['U_mm']=='mm'
    # JSON round-trip must not change node association (keys become strings).
    roundtrip=json.loads(json.dumps(observed));write_post(tmp_path/'again',roundtrip,model(),source_status='PARTIAL_FAILURE')
