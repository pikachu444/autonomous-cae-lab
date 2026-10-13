"""Portable XML checks, plus an explicit installed-VTK reader command.

python -m pytest tests/test_post_serialization.py
pvpython tests/test_post_serialization.py --native-file NEW_POST/contact.pvd

The native command imports only stdlib + that interpreter's existing VTK.
It neither imports a solver nor installs a Python VTK package.
"""
import argparse
import base64
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
from xml.etree import ElementTree as ET


def values_of(element):
    if element.get('format') == 'ascii':
        return [float(v) for v in (element.text or '').split()]
    if element.get('format') != 'binary':
        raise AssertionError('This focused check requires inline arrays')
    raw = base64.b64decode(element.text, validate=True)
    size, = struct.unpack('<I', raw[:4])
    assert size == len(raw) - 4 and size % 8 == 0
    return list(struct.unpack('<' + str(size // 8) + 'd', raw[4:]))


class SerializationTests(unittest.TestCase):
    def test_finite_ascii_and_integer_identity_stay_compatible(self):
        from apps.desktop_post.prepare import data_array
        parent = ET.Element('PointData')
        finite = data_array(parent, 'finite', (v for v in [0., -0., 1.2e-105, -4.25]))
        integer = data_array(parent, 'ids', [1, 2**60 + 1], integer=True)
        self.assertEqual(finite.get('format'), 'ascii')
        self.assertEqual(values_of(finite), [0., -0., 1.2e-105, -4.25])
        self.assertEqual(integer.get('format'), 'ascii')
        self.assertEqual(integer.text, '1 1152921504606846977')

    def test_binary_float64_keeps_nonfinite_zero_order_and_components(self):
        from apps.desktop_post.prepare import data_array
        source = [0., math.nan, math.inf, -math.inf, -0., 1.2e-105]
        element = data_array(ET.Element('PointData'), 'pair', iter(source), components=2)
        self.assertEqual(element.get('format'), 'binary')
        self.assertEqual(element.get('type'), 'Float64')
        self.assertEqual(element.get('NumberOfComponents'), '2')
        raw = base64.b64decode(element.text, validate=True)
        self.assertEqual(raw[:4], struct.pack('<I', 48))
        self.assertEqual(raw[4:], struct.pack('<6d', *source))
        actual = values_of(element)
        self.assertTrue(math.isnan(actual[1]))
        self.assertEqual(actual[2:4], [math.inf, -math.inf])
        self.assertEqual(actual[0], 0.)
        self.assertEqual(math.copysign(1., actual[4]), -1.)

    def test_vtu_keeps_unavailable_values_and_masks_without_losing_other_arrays(self):
        from apps.desktop_post.prepare import write_vtu
        raw = {'nodes': [{'node_id': n, 'position_mm': [float(n), 0., 0.],
                          'displacement_mm': [0., 0., .1 * n]} for n in range(1, 11)],
               'elements': [{'element_id': 7, 'node_ids': list(range(1, 11))}],
               'fixed_node_ids': [], 'loads': []}
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory)/'probe.vtu'
            write_vtu(file, raw, extra={
                'GeomGap_mm': [math.nan] * 9 + [0.],
                'GeomGap_valid': [0] * 9 + [1],
                'CPRESS': [math.nan, math.inf, -math.inf] + [0.] * 7})
            root = ET.parse(file).getroot()
            self.assertEqual(root.get('byte_order'), 'LittleEndian')
            self.assertEqual(root.get('header_type'), 'UInt32')
            self.assertNotIn('compressor', root.attrib)
            arrays = {el.get('Name'): el for el in root.findall('./UnstructuredGrid/Piece/PointData/DataArray')}
            gap = values_of(arrays['GeomGap_mm'])
            self.assertEqual(sum(math.isnan(v) for v in gap), 9)
            self.assertEqual(gap[-1], 0.)
            self.assertEqual(values_of(arrays['GeomGap_valid']), [0.] * 9 + [1.])
            self.assertEqual(len(values_of(arrays['U_mm'])), 30)
            self.assertEqual(arrays['U_mm'].get('ComponentName2'), 'UZ')


def verify_native_file(path):
    """Read retained XML with installed native VTK and compare every point value."""
    from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader
    path = Path(path).resolve(strict=True)
    root = ET.parse(path).getroot()
    if root.get('type') == 'Collection':
        files = [(path.parent / row.attrib['file']).resolve(strict=True)
                 for row in root.findall('./Collection/DataSet')]
        assert files, 'Empty collection'
        rows = [verify_native_file(file) for file in files]
        return {'frames': len(rows), 'files': rows}
    assert root.get('type') == 'UnstructuredGrid'
    piece = root.find('./UnstructuredGrid/Piece')
    errors = []
    reader = vtkXMLUnstructuredGridReader()
    reader.AddObserver('ErrorEvent', lambda *args: errors.append('VTK ErrorEvent'))
    reader.SetFileName(str(path))
    reader.Update()
    assert not errors, str(path) + ': ' + str(errors)
    output = reader.GetOutput()
    count = int(piece.attrib['NumberOfPoints'])
    assert output.GetNumberOfPoints() == count
    assert output.GetNumberOfCells() == int(piece.attrib['NumberOfCells'])
    counts = {}
    for element in piece.findall('./PointData/DataArray'):
        name = element.attrib['Name']
        expected = values_of(element)
        components = int(element.get('NumberOfComponents', '1'))
        array = output.GetPointData().GetArray(name)
        assert array is not None, 'Missing native array: ' + name
        assert array.GetNumberOfTuples() == count and array.GetNumberOfComponents() == components
        assert len(expected) == count * components
        for i, value in enumerate(expected):
            actual = array.GetComponent(i // components, i % components)
            assert (math.isnan(actual) if math.isnan(value) else actual == value), (name, i, value, actual)
            if value == 0.:
                assert math.copysign(1., actual) == math.copysign(1., value)
        counts[name] = {'values': len(expected),
                        'nan': sum(math.isnan(v) for v in expected),
                        'positive_inf': sum(v == math.inf for v in expected),
                        'negative_inf': sum(v == -math.inf for v in expected)}
    return {'file': str(path), 'points': count, 'arrays': counts}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--native-file', type=Path)
    args = parser.parse_args()
    if args.native_file:
        print(json.dumps(verify_native_file(args.native_file), allow_nan=False))
    else:
        unittest.main(argv=[__file__])
