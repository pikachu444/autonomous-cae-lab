"""Pinned new Post declarations, real VTU parsing, and read-only table builders.

The ParaView proxy is an explicit existing test double; vtk is the installed
VTK XML reader, not ParaView/FreeCAD/CalculiX or Windows native acceptance.
"""
from copy import deepcopy
from xml.etree import ElementTree as ET
import pytest
from test_desktop_post_external import native, Array, Source
from test_b13_beam_bundle import produced
from caelab.adapters.beam_fem import read_saved_run
from apps.desktop_pre.b13_result_window import beam_tables, shell_tables
from caelab.shell_inspection import explicit_manifest,load
from caelab.adapters.shell_fem import collect
from b13_shell_fixture import model as shell_model,write_sources


class WrittenArray(Array):
    def __init__(self, element):
        super().__init__(int(element.get('NumberOfComponents','1')))
        self.element=element
    def GetComponentName(self,index):
        return self.element.get('ComponentName'+str(index),'')


def source_proxy(view):
    source=Source('PVDReader',str(view));source.TimestepValues=[1.]
    source.PointData={};source.CellData={};source.FieldData={}
    for dataset in ET.parse(view).findall('.//DataSet'):
        tree=ET.parse(view.parent/dataset.get('file'))
        for section in ('PointData','CellData','FieldData'):
            getattr(source,section).update({a.get('Name'):WrittenArray(a)
                for a in tree.findall('.//'+section+'/DataArray')})
    return source


def test_raw_beam_exact_post_admission_and_blocks(native,monkeypatch,tmp_path):
    run,result=produced(monkeypatch,tmp_path)
    _,_,external=native;view=run/'post'/'beam.pvd';metadata=result['post_artifact']['native_metadata']
    source=source_proxy(view)
    assert external.validate_declared_metadata(source,metadata)==metadata
    assert {d['part'] for d in metadata['beam']['blocks']}=={0,1}
    ip=next(a for a in metadata['arrays'] if a['name']=='S_internal')
    assert ip['association']=='CELLS' and ip['source_blocks']==[{'group':'internal_native_DAT','part':1}]
    assert any(p.name=='beam.12d' for p in external.source_files(view,metadata))


@pytest.mark.parametrize('change',['units','recovery','basis','blocks','association','shear'])
def test_raw_meaning_cannot_be_changed_even_with_valid_source(native,monkeypatch,tmp_path,change):
    run,result=produced(monkeypatch,tmp_path);_,_,external=native
    view=run/'post'/'beam.pvd';metadata=deepcopy(result['post_artifact']['native_metadata'])
    row=next(r for r in metadata['arrays'] if r['name']=='S_internal')
    if change=='units':row['units']='Nmm'
    elif change=='recovery':row['recovery']='native_section_force_output'
    elif change=='basis':row['frame']='native_IP_material'
    elif change=='blocks':row['source_blocks']=[{'group':'expanded_recovered','part':0}]
    elif change=='association':row['association']='POINTS'
    else:row['shear_convention']='engineering_gamma'
    with pytest.raises(ValueError):external.validate_declared_metadata(source_proxy(view),metadata)


def test_real_vtk_reads_separate_beam_volume_and_50_point_ip_cells(monkeypatch,tmp_path):
    vtk=pytest.importorskip('vtk');run,_=produced(monkeypatch,tmp_path)
    for name,points,cells,kind in [('beam_raw_0000.vtu',40,2,25),('beam_ip_0000.vtu',100,100,1)]:
        reader=vtk.vtkXMLUnstructuredGridReader();reader.SetFileName(str(run/'post'/name));reader.Update()
        data=reader.GetOutput()
        assert data.GetNumberOfPoints()==points and data.GetNumberOfCells()==cells
        assert data.GetCellType(0)==kind
        if kind==1:
            assert data.GetCellData().GetArray('S_internal').GetNumberOfComponents()==6
            assert data.GetPointData().GetArray('S_internal') is None


def test_beam_readonly_tables_keep_locations_units_and_unavailable(monkeypatch,tmp_path):
    run,_=produced(monkeypatch,tmp_path)
    saved=read_saved_run(run);before=deepcopy(saved)
    tables=beam_tables(saved,0,quantity='S',local=False)
    assert saved==before
    assert len(tables)==4
    assert len(tables['확장 절점'][1])==40 and len(tables['내부 적분점'][1])==100
    assert all(len(row)==len(headers) for headers,rows,_ in tables.values() for row in rows)
    assert any('MPa' in h for h in tables['확장 절점'][0])
    assert 'native 회전 DOF가 아닙니다' in tables['유도 회전'][2]
    local=beam_tables(saved,0,quantity='S',local=True)
    assert 'native IP 재료축 아님' in local['내부 적분점'][2]
    assert local['내부 적분점'][1][0][:5]==tables['내부 적분점'][1][0][:5]
    assert saved==before


def test_shell_readonly_tables_keep_real_surface_and_internal_separate(tmp_path):
    m=shell_model();mesh,_,_=write_sources(tmp_path/'solver',m)
    collect(tmp_path,m,mesh,execution_status='SUCCEEDED')
    view,_=explicit_manifest(tmp_path/'post'/'shell_inspection.json');checked=load(view)
    tables=shell_tables(checked,0,quantity='S',local=False)
    assert len(tables['상·하면 복원값'][1])==32 and len(tables['내부 적분점'][1])==54
    assert all(len(row)==len(headers) for headers,rows,_ in tables.values() for row in rows)


def test_table_csv_is_hash_bound_to_frame_basis_and_exact_source(tmp_path):
    import hashlib,json
    from apps.desktop_pre.b13_result_window import export_table
    path=tmp_path/'observation.csv'
    provenance={'worksheet':'내부 적분점','quantity':'S','frame':{'step':1,'increment':1,'load_parameter':1.},
        'display_basis':'global','source_pins':[{'relative':'beam.dat','sha256':'a'*64,'bytes':10}],
        'association':'CELLS','recovery':'native integration point'}
    original=deepcopy(provenance)
    result=export_table(path,headers=['요소','IP','SXX [MPa]'],rows=[[1,1,None],[1,2,0.]],provenance=provenance)
    assert provenance==original
    assert result['table_csv']['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert json.loads(path.with_name(path.name+'.provenance.json').read_text(encoding='utf-8'))==result
    assert '1,1,\r\n' in path.read_bytes().decode('utf-8-sig')
    assert result['missing_value_encoding']=='empty field; not zero'
    assert result['source_pins']==provenance['source_pins']
