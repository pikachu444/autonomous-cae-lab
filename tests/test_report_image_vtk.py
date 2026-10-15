"""REAL standalone VTK + public analytic meshes. NOT ParaView/solver/capture evidence."""
from pathlib import Path
import numpy as np
import pytest

vtk = pytest.importorskip('vtk')
from vtkmodules.util.numpy_support import numpy_to_vtk
from caelab.post_observation import file_pin
from apps.desktop_post.report_image_data import fingerprint, verify_displayed, read_saved


def analytic(data):
    if data.IsA('vtkDataSet'):
        values = np.array([sum((j+1)*x for j, x in enumerate(data.GetPoint(i)))
                           for i in range(data.GetNumberOfPoints())], dtype=np.float64)
        array = numpy_to_vtk(values, deep=1); array.SetName('stress'); data.GetPointData().AddArray(array)
    return data


def tetra():
    points = vtk.vtkPoints(); points.SetDataTypeToDouble()
    for row in [(0,0,0),(1,0,0),(0,1,0),(0,0,1)]: points.InsertNextPoint(*row)
    data = vtk.vtkUnstructuredGrid(); data.SetPoints(points)
    cell = vtk.vtkTetra()
    for i in range(4): cell.GetPointIds().SetId(i, i)
    data.InsertNextCell(cell.GetCellType(), cell.GetPointIds())
    return analytic(data)


def mesh(kind):
    if kind == 'unstructured': return tetra()
    if kind == 'poly':
        s = vtk.vtkSphereSource(); s.SetThetaResolution(5); s.SetPhiResolution(5); s.Update()
        return analytic(s.GetOutput())
    if kind == 'image':
        data = vtk.vtkImageData(); data.SetDimensions(3,2,2); data.SetOrigin(.1,.2,.3); data.SetSpacing(.5,.6,.7)
        matrix = vtk.vtkMatrix3x3(); matrix.Identity(); matrix.SetElement(0,0,-1); matrix.SetElement(1,1,-1)
        data.SetDirectionMatrix(matrix)
        return analytic(data)
    if kind == 'structured':
        data = vtk.vtkStructuredGrid(); data.SetDimensions(2,2,2)
        points = vtk.vtkPoints(); points.SetDataTypeToDouble()
        for z in range(2):
            for y in range(2):
                for x in range(2): points.InsertNextPoint(x + y*.1,y,z)
        data.SetPoints(points); return analytic(data)
    if kind == 'rectilinear':
        data = vtk.vtkRectilinearGrid(); data.SetDimensions(2,2,2)
        for i, axis in enumerate('XYZ'):
            a = numpy_to_vtk(np.array([0.,i+1.]), deep=1)
            getattr(data, 'Set'+axis+'Coordinates')(a)
        return analytic(data)
    if kind == 'multiblock':
        data = vtk.vtkMultiBlockDataSet(); data.SetNumberOfBlocks(3)
        data.SetBlock(0, tetra()); data.SetBlock(2, mesh('poly'))
        data.GetMetaData(0).Set(vtk.vtkCompositeDataSet.NAME(), '첫 블록')
        return data
    if kind == 'partitioned':
        data = vtk.vtkPartitionedDataSet(); data.SetPartition(0, tetra()); return data
    if kind == 'collection':
        data = vtk.vtkPartitionedDataSetCollection(); data.SetPartitionedDataSet(0, mesh('partitioned'))
        return data
    raise AssertionError(kind)


def saved(tmp_path, data):
    writers = {'vtkUnstructuredGrid':('vtkXMLUnstructuredGridWriter','.vtu'),
        'vtkPolyData':('vtkXMLPolyDataWriter','.vtp'), 'vtkImageData':('vtkXMLImageDataWriter','.vti'),
        'vtkStructuredGrid':('vtkXMLStructuredGridWriter','.vts'),
        'vtkRectilinearGrid':('vtkXMLRectilinearGridWriter','.vtr'),
        'vtkMultiBlockDataSet':('vtkXMLMultiBlockDataWriter','.vtm'),
        'vtkPartitionedDataSet':('vtkXMLPartitionedDataSetWriter','.vtpd'),
        'vtkPartitionedDataSetCollection':('vtkXMLPartitionedDataSetCollectionWriter','.vtpc')}
    name, extension = writers[data.GetClassName()]
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path/('보존 결과'+extension)
    writer = getattr(vtk, name)(); writer.SetFileName(str(path)); writer.SetInputData(data)
    assert writer.Write() == 1
    return {'result_file': str(path), 'result_files': [file_pin(f) for f in sorted(tmp_path.rglob('*')) if f.is_file()],
            'result_sha256': file_pin(path)['sha256']}


@pytest.mark.parametrize('kind', ['unstructured','poly','image','structured','rectilinear','multiblock','partitioned','collection'])
def test_exact_geometry_and_all_arrays_round_trip(tmp_path, kind):
    data = mesh(kind); record = saved(tmp_path/'한글 공간', data)
    assert verify_displayed(data, record) == fingerprint(data)


@pytest.mark.parametrize('kind', ['unstructured','poly','image','structured','rectilinear'])
def test_exact_saved_data_time_not_nearest(tmp_path, kind):
    data = mesh(kind); data.GetInformation().Set(vtk.vtkDataObject.DATA_TIME_STEP(), .125)
    record = saved(tmp_path, data)
    assert verify_displayed(data, record)['data_time'] == .125
    data.GetInformation().Set(vtk.vtkDataObject.DATA_TIME_STEP(), .12500000001)
    with pytest.raises(ValueError, match='시각'): verify_displayed(data, record)


@pytest.mark.parametrize('change', ['coordinate','order','array','cell','field','component','type','time'])
def test_same_counts_ranges_or_center_cannot_hide_changed_result(tmp_path, change):
    data = tetra(); record = saved(tmp_path, data)
    if change == 'coordinate': data.GetPoints().SetPoint(1, 1.00000000001,0,0)
    elif change == 'order':
        a, b = data.GetPoint(0),data.GetPoint(1)
        data.GetPoints().SetPoint(0,b);data.GetPoints().SetPoint(1,a)
    elif change == 'array': data.GetPointData().GetArray('stress').SetTuple1(2,2.000000000001)
    elif change == 'cell': data.GetCells().GetConnectivityArray().SetTuple1(0,3)
    elif change == 'field':
        a=vtk.vtkStringArray();a.SetName('Failure');a.InsertNextValue('UNKNOWN');data.GetFieldData().AddArray(a)
    elif change == 'component': data.GetPointData().GetArray('stress').SetComponentName(0, 'new meaning')
    elif change == 'type':
        a=numpy_to_vtk(np.array([0,1,2,3],dtype=np.float32),deep=1);a.SetName('stress');data.GetPointData().AddArray(a)
    else: data.GetInformation().Set(vtk.vtkDataObject.DATA_TIME_STEP(),1.)
    with pytest.raises(ValueError):verify_displayed(data,record)


def test_nonfinite_and_signed_zero_are_not_zero_filled(tmp_path):
    data=tetra();a=data.GetPointData().GetArray('stress')
    for i,v in enumerate([np.nan,np.inf,-np.inf,-0.]):a.SetTuple1(i,v)
    record=saved(tmp_path,data);verify_displayed(data,record)
    a.SetTuple1(0,0.)
    with pytest.raises(ValueError):verify_displayed(data,record)


def test_changed_saved_file_and_unpinned_piece_rejected(tmp_path):
    data=mesh('multiblock');record=saved(tmp_path,data)
    missing={**record,'result_files':record['result_files'][:1]}
    with pytest.raises(ValueError): read_saved(missing)
    piece=next(Path(p['path']) for p in record['result_files'] if Path(p['path']).suffix=='.vtu')
    piece.write_bytes(piece.read_bytes()+b'changed')
    with pytest.raises(ValueError):read_saved(record)


def test_unsupported_data_is_not_relabelled_as_3d():
    with pytest.raises(ValueError):fingerprint(vtk.vtkTable())


def test_fetch_without_information_uses_actual_native_time_not_requested_time(tmp_path):
    data=tetra();data.GetInformation().Set(vtk.vtkDataObject.DATA_TIME_STEP(),.125)
    record=saved(tmp_path,data)
    data.GetInformation().Remove(vtk.vtkDataObject.DATA_TIME_STEP())
    assert verify_displayed(data,record,actual_time=.125)['data_time']==.125
    with pytest.raises(ValueError):verify_displayed(data,record,actual_time=.126)
