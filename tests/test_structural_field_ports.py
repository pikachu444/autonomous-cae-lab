"""Producer identity/component/reference gates on literal VTU software fixtures."""
from copy import deepcopy
import hashlib,json
from xml.etree import ElementTree as ET
import pytest
from caelab.structural_field_ports import read_ccx_vtu,receiver_from_capture
from caelab.adapters.frozen_fem import CCX_FROM_NATIVE_TET10
from test_structural_field_transfer import source


def fixture(tmp_path):
    field=source();native=[None]*10
    for deck_slot,native_slot in enumerate(CCX_FROM_NATIVE_TET10):native[native_slot]=deck_slot+1
    mesh={'kind':'freecad-contact-mesh','units':{'position':'mm','displacement':'mm'},
        'native_to_deck_slots':list(CCX_FROM_NATIVE_TET10),
        'nodes':[{'node_id':n,'position_mm':p} for n,p in zip(field['node_ids'],field['coordinates'])],
        'elements':[{**field['elements'][0],'native_node_ids':native}]}
    frame={'static':deepcopy(field['static']),'step_location':{'index':1,'coordinate':1.,'axis':field['axis']}}
    xml=ET.Element('VTKFile',type='UnstructuredGrid');grid=ET.SubElement(xml,'UnstructuredGrid')
    piece=ET.SubElement(grid,'Piece',NumberOfPoints='10',NumberOfCells='1')
    def array(parent,name,values,components=1,integer=False):
        attributes={'type':'Int64' if integer else 'Float64','format':'ascii'}
        if name is not None:attributes['Name']=name
        if components!=1:attributes['NumberOfComponents']=str(components)
        item=ET.SubElement(parent,'DataArray',**attributes);item.text=' '.join(map(str,values));return item
    data=ET.SubElement(piece,'PointData');array(data,'NativeNodeId',range(1,11),integer=True)
    array(data,'U_mm',[v for row in field['values'] for v in row],3)
    array(ET.SubElement(piece,'Points'),None,[v for row in field['coordinates'] for v in row],3)
    cells=ET.SubElement(piece,'Cells');array(cells,'connectivity',range(10),integer=True)
    array(cells,'offsets',[10],integer=True);array(cells,'types',[24],integer=True)
    array(ET.SubElement(piece,'CellData'),'NativeElementId',[1],integer=True)
    paths=[tmp_path/'frame0001.vtu',tmp_path/'mesh.json',tmp_path/'frame0001.json']
    paths[0].write_bytes(ET.tostring(xml));paths[1].write_text(json.dumps(mesh),encoding='utf-8');paths[2].write_text(json.dumps(frame),encoding='utf-8')
    return paths,field,xml,mesh,frame


def read(paths,**kwargs):
    v,m,f=paths;sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    return read_ccx_vtu(v,m,f,expected_vtu_sha256=kwargs.get('vtu_sha',sha(v)),expected_mesh_sha256=sha(m),
        expected_frame_sha256=sha(f),source_reference={'document_id':'Vcontrolled','job_id':'Jcontrolled'})


def test_actual_declared_arrays_are_read_without_id_interpolation_or_time_relabel(tmp_path):
    paths,field,*_=fixture(tmp_path);before=[p.read_bytes() for p in paths];result=read(paths)
    assert result['node_ids']==field['node_ids'] and result['values']==field['values']
    assert result['static']==field['static'] and result['axis']['unit']=='1'
    assert result['engineering_valid'] is False and result['qualification']=='UNKNOWN'
    assert [p.read_bytes() for p in paths]==before


def test_receiver_capture_extracts_actual_boundary_without_replacing_conditions(tmp_path):
    _,field,_,model,_=fixture(tmp_path)
    model['boundary_dofs']=[{'node_id':1,'component':1,'value_mm':0.}]
    before=deepcopy(model)
    receiver=receiver_from_capture(model,[[1,1]],[1,3],coordinate_frame='explicit_target_global')
    assert receiver['node_ids']==field['node_ids'] and receiver['elements']==model['elements']
    assert receiver['boundary_node_ids']==[1,2,3,5,6,7]
    assert receiver['components']==[1,3] and receiver['coordinate_frame']=='explicit_target_global'
    assert model==before
    receiver['elements'][0]['node_ids'][0]=999
    assert model==before
    with pytest.raises(ValueError):receiver_from_capture(model,[[1,9]],[1],coordinate_frame='x')
    with pytest.raises(ValueError):receiver_from_capture(model,[[1,1]],[True],coordinate_frame='x')
    with pytest.raises(ValueError):receiver_from_capture(model,[[1,1]],[1],coordinate_frame='')


@pytest.mark.parametrize('mutation',['changed_pin','wrong_ids','missing_component','nonfinite','deformed','wrong_order','clock','physical_time','native_order'])
def test_wrong_source_components_geometry_order_clock_and_pins_fail_closed(tmp_path,mutation):
    paths,_,xml,mesh,frame=fixture(tmp_path);original_sha=hashlib.sha256(paths[0].read_bytes()).hexdigest()
    if mutation=='changed_pin':paths[0].write_bytes(paths[0].read_bytes()+b' ')
    elif mutation=='wrong_ids':xml.find('.//PointData/DataArray[@Name="NativeNodeId"]').text='11 2 3 4 5 6 7 8 9 10'
    elif mutation=='missing_component':xml.find('.//PointData/DataArray[@Name="U_mm"]').set('NumberOfComponents','2')
    elif mutation=='nonfinite':xml.find('.//PointData/DataArray[@Name="U_mm"]').text='nan '+'0 '*29
    elif mutation=='deformed':
        point=xml.find('.//Points/DataArray');point.text='0.1 '+point.text.split(' ',1)[1]
    elif mutation=='wrong_order':xml.find('.//Cells/DataArray[@Name="connectivity"]').text='0 1 2 3 5 4 6 7 8 9'
    elif mutation=='clock':frame['step_location']['coordinate']=2.
    elif mutation=='physical_time':frame['step_location']['axis']={'name':'time','semantics':'PHYSICAL_TIME','unit':'s'}
    elif mutation=='native_order':mesh['native_to_deck_slots']=list(range(10))
    if mutation!='changed_pin':paths[0].write_bytes(ET.tostring(xml))
    paths[1].write_text(json.dumps(mesh),encoding='utf-8');paths[2].write_text(json.dumps(frame),encoding='utf-8')
    with pytest.raises(ValueError):read(paths,**({'vtu_sha':original_sha} if mutation=='changed_pin' else {}))
