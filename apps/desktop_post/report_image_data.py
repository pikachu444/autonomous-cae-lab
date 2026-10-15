"""Read-only equality of the displayed VTK data and an existing saved result.

Uses the VTK already shipped with native ParaView. Does not register a proxy,
create a view, run a solver, resample, or write another result. Full coordinates,
connectivity and arrays are compared, not ranges, centers or volumes.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from caelab.post_observation import check_pin
from caelab.storage import canonical_hash

MAX_DATA_BYTES = 512 * 1024 * 1024
MAX_FILES = 4096
SUPPORTED = {'.vtu', '.vtp', '.vtr', '.vti', '.vts', '.vtm', '.vtpc', '.vtpd'}
CONTAINERS = {'.vtm', '.vtpc', '.vtpd'}
_UNSET = object()


def _array(array):
    if array is None:
        return None
    import numpy as np
    from vtkmodules.util.numpy_support import vtk_to_numpy
    if array.IsA('vtkDataArray'):
        values = np.asarray(vtk_to_numpy(array))
        if values.nbytes > MAX_DATA_BYTES:
            raise ValueError('배열이 이미지 연결 검사의 512 MiB 범위를 넘습니다.')
        values = values.astype(values.dtype.newbyteorder('<'), copy=True)
        if values.dtype.kind == 'f':
            values[np.isnan(values)] = np.nan  # Canonical NaN payload only; never zero-fill.
        checksum = hashlib.sha256(values.tobytes()).hexdigest()
        dtype = values.dtype.str
    elif array.IsA('vtkStringArray'):
        strings = [array.GetValue(i) for i in range(array.GetNumberOfValues())]
        checksum, dtype = canonical_hash(strings), 'string'
    else:
        raise ValueError('정확한 비교를 지원하지 않는 VTK 배열입니다: ' + array.GetClassName())
    return {'type': dtype, 'components': array.GetNumberOfComponents(),
            'component_names': [array.GetComponentName(i) for i in range(array.GetNumberOfComponents())],
            'tuples': array.GetNumberOfTuples(), 'sha256': checksum}


def data_time(data):
    from vtkmodules.vtkCommonDataModel import vtkDataObject
    key = vtkDataObject.DATA_TIME_STEP()
    info = data.GetInformation()
    value = float(info.Get(key)) if info.Has(key) else None
    if value is not None and not math.isfinite(value):
        raise ValueError('실제 VTK 데이터 시각이 유효하지 않습니다.')
    return value


def _attributes(attributes, *, clock=None, field=False):
    arrays = []
    seen = set()
    for i in range(attributes.GetNumberOfArrays()):
        array = attributes.GetAbstractArray(i)
        name = array.GetName()
        if name in seen:
            raise ValueError('같은 이름의 배열이 중복되어 정확히 대응할 수 없습니다.')
        seen.add(name)
        # vtkXMLWriter stores DATA_TIME_STEP as a single TimeValue field. Remove
        # only that redundant clock value after checking its exact semantics.
        if field and name == 'TimeValue' and clock is not None:
            if (not array.IsA('vtkDataArray') or array.GetNumberOfTuples() != 1
                    or array.GetNumberOfComponents() != 1 or array.GetTuple1(0) != clock):
                raise ValueError('TimeValue 필드와 실제 데이터 시각이 충돌합니다.')
            continue
        arrays.append({'name': name, **_array(array)})
    return sorted(arrays, key=lambda row: row['name'] or '')


def _cells(cells):
    return {'offsets': _array(cells.GetOffsetsArray()),
            'connectivity': _array(cells.GetConnectivityArray())}


def fingerprint(data, *, depth=0, actual_time=_UNSET):
    """Stable exact-data fingerprint; signed zero/Inf and array types are retained."""
    if data is None:
        return None
    if depth > 16 or data.GetActualMemorySize() * 1024 > MAX_DATA_BYTES:
        raise ValueError('이미지 연결 검사의 데이터 크기/중첩 범위를 넘습니다.')
    kind, clock = data.GetClassName(), data_time(data)
    if actual_time is not _UNSET:
        if clock is not None and clock != actual_time:
            raise ValueError('Fetch 데이터와 native 실제 시각이 다릅니다.')
        if actual_time is not None and (type(actual_time) not in (int, float) or not math.isfinite(actual_time)):
            raise ValueError('실제 native 시각이 유효하지 않습니다.')
        # Fetch may omit pipeline information keys. The caller supplies the
        # actual vtkPVDataInformation time, never a requested/nearest time.
        clock = actual_time
    result = {'type': kind, 'data_time': clock,
              'fields': _attributes(data.GetFieldData(), clock=clock, field=True)}
    children = None
    if kind == 'vtkMultiBlockDataSet':
        children = [data.GetBlock(i) for i in range(data.GetNumberOfBlocks())]
    elif kind == 'vtkPartitionedDataSetCollection':
        children = [data.GetPartitionedDataSet(i) for i in range(data.GetNumberOfPartitionedDataSets())]
    elif kind == 'vtkPartitionedDataSet':
        children = [data.GetPartition(i) for i in range(data.GetNumberOfPartitions())]
    if children is not None:
        if len(children) > MAX_FILES:
            raise ValueError('복합 데이터의 블록이 너무 많습니다.')
        from vtkmodules.vtkCommonDataModel import vtkCompositeDataSet
        key = vtkCompositeDataSet.NAME()
        result['blocks'] = [{'name': (data.GetMetaData(i).Get(key)
            if data.HasMetaData(i) and data.GetMetaData(i).Has(key) else None),
            'data': fingerprint(child, depth=depth + 1)} for i, child in enumerate(children)]
        if kind == 'vtkPartitionedDataSetCollection':
            assembly = data.GetDataAssembly()
            result['assembly'] = assembly.SerializeToXML(0) if assembly is not None else None
        return result
    if kind not in ('vtkUnstructuredGrid', 'vtkPolyData', 'vtkImageData',
                    'vtkRectilinearGrid', 'vtkStructuredGrid'):
        raise ValueError('현재 지원하지 않는 3D 저장 형식입니다: ' + kind)
    result.update(points=data.GetNumberOfPoints(), cells=data.GetNumberOfCells(),
        point_arrays=_attributes(data.GetPointData()), cell_arrays=_attributes(data.GetCellData()))
    if kind in ('vtkImageData', 'vtkRectilinearGrid', 'vtkStructuredGrid'):
        result['extent'] = list(data.GetExtent())
    if kind == 'vtkImageData':
        result.update(origin=list(data.GetOrigin()), spacing=list(data.GetSpacing()),
            direction=[data.GetDirectionMatrix().GetElement(i, j) for i in range(3) for j in range(3)])
    elif kind == 'vtkRectilinearGrid':
        result['coordinates'] = [_array(getattr(data, 'Get' + axis + 'Coordinates')()) for axis in 'XYZ']
    else:
        result['coordinates'] = _array(data.GetPoints().GetData()) if data.GetPoints() else None
    if kind == 'vtkUnstructuredGrid':
        result['topology'] = _cells(data.GetCells())
        result['cell_types'] = _array(data.GetCellTypesArray())
        # Preserve polyhedron face topology, including order. Ordinary tetra /
        # hex / quadratic cells use the complete connectivity above.
        faces = []
        for i in range(data.GetNumberOfCells()):
            if data.GetCellType(i) == 42:  # VTK_POLYHEDRON
                cell = data.GetCell(i)
                faces.append([i, [[cell.GetFace(j).GetPointId(k)
                    for k in range(cell.GetFace(j).GetNumberOfPoints())]
                    for j in range(cell.GetNumberOfFaces())]])
        result['polyhedra'] = faces
    elif kind == 'vtkPolyData':
        result['topology'] = {key: _cells(getattr(data, 'Get' + key)())
                              for key in ('Verts', 'Lines', 'Polys', 'Strips')}
    return result


def read_saved(record):
    """Use only pinned local XML results; validate every composite dependency."""
    files = record['result_files']
    if not 0 < len(files) <= MAX_FILES or sum(pin['bytes'] for pin in files) > MAX_DATA_BYTES:
        raise ValueError('저장 결과가 이미지 연결 검사의 4096파일/512 MiB 범위를 넘습니다.')
    pins = {str(Path(pin['path']).resolve()): pin for pin in files}
    if len(pins) != len(files):
        raise ValueError('저장 결과의 파일 참조가 중복됩니다.')
    seen = set()
    root = Path(record['result_file']).resolve().parent
    def visit(path, depth=0):
        if depth > 16 or path.suffix.lower() not in SUPPORTED or not path.is_relative_to(root):
            raise ValueError('저장된 XML 결과의 참조 범위를 벗어났습니다.')
        pin = pins.get(str(path))
        if pin is None:
            raise ValueError('저장되지 않은 결과 조각은 읽지 않습니다: ' + path.name)
        check_pin(pin)
        if path in seen:
            return
        seen.add(path)
        if path.suffix.lower() in CONTAINERS:
            if pin['bytes'] > 4 * 1024 * 1024:
                raise ValueError('복합 데이터 참조 파일이 너무 큽니다.')
            raw = path.read_bytes()
            if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
                raise ValueError('외부 XML 선언은 결과 참조로 읽지 않습니다.')
            for element in ET.fromstring(raw).iter():
                relative = element.get('file')
                if relative:
                    visit((path.parent / relative).resolve(), depth + 1)
    entry = Path(record['result_file']).resolve()
    visit(entry)
    from vtkmodules import vtkIOXML
    readers = {'.vtu': 'vtkXMLUnstructuredGridReader', '.vtp': 'vtkXMLPolyDataReader',
        '.vti': 'vtkXMLImageDataReader', '.vtr': 'vtkXMLRectilinearGridReader',
        '.vts': 'vtkXMLStructuredGridReader', '.vtm': 'vtkXMLMultiBlockDataReader',
        '.vtpc': 'vtkXMLPartitionedDataSetCollectionReader', '.vtpd': 'vtkXMLPartitionedDataSetReader'}
    reader = getattr(vtkIOXML, readers[entry.suffix.lower()])()
    errors = []
    reader.AddObserver('ErrorEvent', lambda *_: errors.append('VTK XML 읽기 실패'))
    if not reader.CanReadFile(str(entry)):
        raise ValueError('저장 결과의 실제 VTK XML 형식을 읽을 수 없습니다.')
    reader.SetFileName(str(entry)); reader.UpdateInformation()
    from vtkmodules.vtkCommonExecutionModel import vtkStreamingDemandDrivenPipeline
    key = vtkStreamingDemandDrivenPipeline.TIME_STEPS()
    info = reader.GetOutputInformation(0)
    if info.Has(key):
        times = info.Get(key)
        if len(times) != 1 or not math.isfinite(times[0]):
            raise ValueError('저장 결과가 단일 정확 프레임이 아닙니다.')
        reader.UpdateTimeStep(times[0])
    else:
        reader.Update()
    if errors or reader.GetErrorCode() or reader.GetOutput() is None:
        raise ValueError('저장 결과를 온전히 읽지 못했습니다.')
    for path in seen:
        check_pin(pins[str(path)])
    return reader.GetOutput()


def verify_displayed(data, saved, *, expected=None, actual_time=_UNSET):
    """Check again after screenshot using the same saved-data fingerprint."""
    original = expected if expected is not None else fingerprint(read_saved(saved))
    actual = fingerprint(data, actual_time=actual_time)
    if actual != original:
        raise ValueError('표시 데이터의 좌표·연결·배열·시각이 저장 결과와 다릅니다. 정확한 프레임을 저장한 뒤 캡처하세요.')
    return original
