"""Byte parity with the writer retained from 9c001eb before extraction."""
import math
import os
from pathlib import Path
import tempfile
import unittest


def writer_input():
    ids = [21, 3, 17, 8, 42, 9, 16, 5, 33, 2]
    raw = {
        'nodes': [
            {'node_id': node_id, 'position_mm': [float(i), -0., i / 4],
             'displacement_mm': [i / 8, -i / 16, .125]}
            for i, node_id in enumerate(ids)
        ],
        'elements': [
            {'element_id': 91, 'node_ids': ids},
            {'element_id': 7, 'node_ids': list(reversed(ids))},
        ],
        'fixed_node_ids': [3, 16],
        'loads': [{'node_id': 33}],
    }
    extra = {
        'Finite_mm': [0., -0., 1.2e-105, -4.25, 1., 2., 3., 4., 5., 6.],
        'Unavailable_MPa': [math.nan, math.inf, -math.inf, -0., 0., 1., 2., 3., 4., 5.],
        'Unavailable_valid': [0, 0, 0, 1, 1, 1, 1, 1, 1, 1],
    }
    return raw, extra


class WriterBoundaryTests(unittest.TestCase):
    def test_neutral_writer_matches_retained_bytes_and_old_public_path(self):
        from apps.desktop_post import prepare
        from caelab.adapters.vtu import data_array, write_vtu

        self.assertIs(prepare.data_array, data_array)
        self.assertIs(prepare.write_vtu, write_vtu)
        raw, extra = writer_input()
        expected = Path(__file__).with_name('fixtures') / 'post_writer_9c001eb.vtu'
        with tempfile.TemporaryDirectory() as directory:
            actual = Path(directory) / 'result.vtu'
            write_vtu(actual, raw, extra)
            # The retained Windows output has a CRLF XML declaration. Both the
            # original and extracted ElementTree writers use the host newline;
            # preserve every array byte and adapt only that declaration break.
            retained = expected.read_bytes()
            self.assertEqual(retained.count(b'\r\n'), 1)
            host_bytes = retained.replace(b'?>\r\n<VTKFile', b'?>' + os.linesep.encode('ascii') + b'<VTKFile', 1)
            self.assertEqual(actual.read_bytes(), host_bytes)


if __name__ == '__main__':
    unittest.main()
