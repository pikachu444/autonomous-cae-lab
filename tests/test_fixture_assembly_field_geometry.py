"""Independent rational/topological source controls; no native/assembly evidence."""
from copy import deepcopy
from fractions import Fraction as F
import math
from pathlib import Path
from types import ModuleType
import unittest

_path = Path(__file__).resolve().parents[1] / "caelab/adapters/fixture_assembly_field_geometry.py"
g = ModuleType("_private_fixture_assembly_field_geometry")
g.__file__ = str(_path)
exec(compile(_path.read_bytes(), str(_path), "exec", dont_inherit=True), g.__dict__)

# Manually transcribed reference nodes/shapes, independent of the production
# constants/polynomial evaluator and source conventions of other FEM tools.
NODES = [[0, 1, 0], [0, 0, 1], [0, 0, 0], [1, 0, 0],
         [0, .5, .5], [0, 0, .5], [0, .5, 0], [.5, .5, 0],
         [.5, 0, .5], [.5, 0, 0]]
POINTS = [[F(1, 4)]*3, [F(1, 6)]*3,
          [F(1, 6), F(1, 6), F(1, 2)], [F(1, 6), F(1, 2), F(1, 6)],
          [F(1, 2), F(1, 6), F(1, 6)]]
SHAPES = [
    [F(-1, 8)]*4 + [F(1, 4)]*6,
    [F(-1, 9), F(-1, 9), 0, F(-1, 9), F(1, 9), F(1, 3), F(1, 3), F(1, 9), F(1, 9), F(1, 3)],
    [F(-1, 9), 0, F(-1, 9), F(-1, 9), F(1, 3), F(1, 3), F(1, 9), F(1, 9), F(1, 3), F(1, 9)],
    [0, F(-1, 9), F(-1, 9), F(-1, 9), F(1, 3), F(1, 9), F(1, 3), F(1, 3), F(1, 9), F(1, 9)],
    [F(-1, 9), F(-1, 9), F(-1, 9), 0, F(1, 9), F(1, 9), F(1, 9), F(1, 3), F(1, 3), F(1, 3)],
]
WEIGHTS = [F(-2, 15)] + [F(3, 40)]*4


def topology(tetrahedra, triangles, component="body"):
    # This constructor assigns IDs only. It does not enumerate tetra faces or
    # manufacture the expected boundary/interior sets used by the assertions.
    cells = [{"index": i, "type": "TETRA10", "node_indices": list(nodes)}
             for i, nodes in enumerate(tetrahedra)]
    offset = len(cells)
    cells += [{"index": offset+i, "type": "TRIA6", "node_indices": list(nodes)}
              for i, nodes in enumerate(triangles)]
    bodies = [{"component_id": component, "volume_cell_indices": list(range(offset)),
               "face_cell_indices": list(range(offset, len(cells)))}]
    return cells, bodies


SINGLE_TETRA = list(range(10))
SINGLE_FACES = [[0, 1, 2, 4, 5, 6], [0, 1, 3, 4, 8, 7],
                [0, 2, 3, 6, 9, 7], [1, 2, 3, 5, 9, 8]]
TWO_TETRA = [SINGLE_TETRA, [0, 1, 2, 10, 4, 5, 6, 11, 12, 13]]
TWO_FACES = [[0, 1, 3, 4, 8, 7], [0, 2, 3, 6, 9, 7], [1, 2, 3, 5, 9, 8],
             [0, 1, 10, 4, 12, 11], [0, 2, 10, 6, 13, 11], [1, 2, 10, 5, 13, 12]]
FOUR_TETRA = [[0, 1, 2, 4, 5, 6, 7, 11, 12, 13],
              [0, 1, 3, 4, 5, 9, 8, 11, 12, 14],
              [0, 2, 3, 4, 7, 10, 8, 11, 13, 14],
              [1, 2, 3, 4, 6, 10, 9, 12, 13, 14]]
FOUR_FACES = [[0, 1, 2, 5, 6, 7], [0, 1, 3, 5, 9, 8],
              [0, 2, 3, 7, 10, 8], [1, 2, 3, 6, 10, 9]]
# Two tetrahedra meet only along edge(0,1), whose native midside is4.
# These eight faces and complete exterior0..16 are manually listed, not
# generated with production face/edge slots.
EDGE_ONLY_TETRA = [SINGLE_TETRA, [0, 1, 10, 11, 4, 12, 13, 14, 15, 16]]
EDGE_ONLY_FACES = SINGLE_FACES + [[0, 1, 10, 4, 12, 13], [0, 1, 11, 4, 15, 14],
                                [0, 10, 11, 13, 16, 14], [1, 10, 11, 12, 16, 15]]


class TestTetra10Gauss(unittest.TestCase):
    def near_vector(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a, float(e), delta=2e-13)

    def test_all_ten_shape_vectors_at_every_source_point(self):
        for node in range(10):
            basis = [[0., 0., 0.] for _ in range(10)]
            basis[node][0] = 1.
            actual = g.tetra10_gauss(basis)
            for p in range(5):
                with self.subTest(local_node=node+1, source_point=p+1):
                    self.near_vector(actual[p]["xyz_mm"], [SHAPES[p][node], 0, 0])
                    self.assertEqual(actual[p]["reference_xyz"], [float(v) for v in POINTS[p]])
                    self.assertEqual(actual[p]["reference_weight"], float(WEIGHTS[p]))
                    self.assertEqual(actual[p]["point"], p+1)

    def test_curved_midside_coordinate_and_jacobian_manual_oracle(self):
        nodes = deepcopy(NODES)
        nodes[9][0] = .6
        actual = g.tetra10_gauss(nodes)
        # X=x+(2/5)*x*a; the exact determinant is 1+(2/5)*(a-x).
        x = [F(11, 40), F(1, 5), F(8, 45), F(8, 45), F(8, 15)]
        det = [F(1), F(17, 15), F(1), F(1), F(13, 15)]
        weights = [F(-2, 15), F(17, 200), F(3, 40), F(3, 40), F(13, 200)]
        for p, row in enumerate(actual):
            with self.subTest(point=p+1):
                self.near_vector(row["xyz_mm"], [x[p], POINTS[p][1], POINTS[p][2]])
                self.assertAlmostEqual(row["signed_jacobian_mm3"], float(det[p]), delta=2e-14)
                self.assertAlmostEqual(row["native_expected_weight_mm3"], float(weights[p]), delta=2e-15)
        self.assertLess(actual[0]["native_expected_weight_mm3"], 0)

    def test_nondiagonal_affine_map_and_manual_signed_weights(self):
        nodes = [[10+2*x+y+z, -7+3*y+z, 2+4*z] for x, y, z in NODES]
        expected = [[11, -6, 3], [F(32, 3), F(-19, 3), F(8, 3)],
                    [11, -6, 4], [11, F(-16, 3), F(8, 3)],
                    [F(34, 3), F(-19, 3), F(8, 3)]]
        for p, row in enumerate(g.tetra10_gauss(nodes)):
            with self.subTest(point=p+1):
                self.near_vector(row["xyz_mm"], expected[p])
                self.assertAlmostEqual(row["signed_jacobian_mm3"], 24, delta=2e-12)
                self.assertAlmostEqual(row["native_expected_weight_mm3"], -16/5 if p == 0 else 9/5, delta=2e-13)

    def test_translation_and_scale_are_consistent(self):
        nodes = [[2*x-4, 2*y+8, 2*z-1] for x, y, z in NODES]
        for p, row in enumerate(g.tetra10_gauss(nodes)):
            with self.subTest(point=p+1):
                self.near_vector(row["xyz_mm"], [2*POINTS[p][0]-4, 2*POINTS[p][1]+8, 2*POINTS[p][2]-1])
                self.assertAlmostEqual(row["signed_jacobian_mm3"], 8, delta=2e-13)
                self.assertAlmostEqual(row["native_expected_weight_mm3"], float(8*WEIGHTS[p]), delta=2e-14)

    def test_reversed_and_zero_geometry_retain_invalid_metrics(self):
        for mode, nodes in (('reversed', [[-x, y, z] for x, y, z in NODES]),
                            ('zero', [[x, y, 0] for x, y, z in NODES])):
            for p, row in enumerate(g.tetra10_gauss(nodes)):
                with self.subTest(mode=mode, point=p+1):
                    self.assertAlmostEqual(row["signed_jacobian_mm3"], -1 if mode == 'reversed' else 0, delta=2e-15)
                    self.assertAlmostEqual(row["native_expected_weight_mm3"], float(WEIGHTS[p]) if mode == 'reversed' else 0, delta=2e-15)
                    self.assertNotIn('status', row)
                    self.assertNotIn('observed_weight_mm3', row)

    def test_json_coordinate_shape_type_and_finite_refusal(self):
        for bad in (None, (), {}, [], NODES[:-1], NODES+[NODES[0]], tuple(NODES)):
            with self.subTest(outer=repr(bad)[:70]):
                with self.assertRaises(ValueError): g.tetra10_gauss(bad)
        for bad in (True, False, "0", None, float('nan'), float('inf'), -float('inf'), 10**400):
            nodes = deepcopy(NODES); nodes[-1][2] = bad
            with self.subTest(coordinate_type=type(bad).__name__, value=repr(bad)[:30]):
                with self.assertRaises(ValueError): g.tetra10_gauss(nodes)
        for bad in ([0, 1], [0, 1, 2, 3], (0, 1, 2), {'x': 0, 'y': 1, 'z': 2}):
            nodes = deepcopy(NODES); nodes[-1] = bad
            with self.subTest(row=bad):
                with self.assertRaises(ValueError): g.tetra10_gauss(nodes)

    def test_finite_input_overflow_is_rejected(self):
        nodes = [[v*1e150 for v in row] for row in NODES]
        with self.assertRaises(ValueError): g.tetra10_gauss(nodes)

    def test_input_nonmutation_and_deep_independent_result(self):
        nodes = deepcopy(NODES); original = deepcopy(nodes)
        rows = g.tetra10_gauss(nodes)
        self.assertEqual(nodes, original)
        self.assertEqual(set(rows[0]), {'point', 'reference_xyz', 'reference_weight', 'xyz_mm',
                                       'signed_jacobian_mm3', 'native_expected_weight_mm3'})
        rows[0]['reference_xyz'][0] = 99; rows[0]['xyz_mm'][1] = 88
        self.assertEqual(g.tetra10_gauss(nodes)[0]['reference_xyz'], [.25]*3)
        self.near_vector(g.tetra10_gauss(nodes)[0]['xyz_mm'], [.25]*3)


class TestExteriorTopology(unittest.TestCase):
    def test_single_tetra_complete_boundary(self):
        cells, bodies = topology([SINGLE_TETRA], SINGLE_FACES)
        self.assertEqual(g.exterior_nodes(cells, bodies), [{'component_id': 'body',
            'exterior_node_indices': list(range(10)), 'interior_node_indices': [], 'boundary_face_count': 4}])

    def test_two_tetra_conforming_internal_face(self):
        cells, bodies = topology(TWO_TETRA, TWO_FACES)
        self.assertEqual(g.exterior_nodes(cells, bodies), [{'component_id': 'body',
            'exterior_node_indices': list(range(14)), 'interior_node_indices': [], 'boundary_face_count': 6}])

    def test_four_tetra_preserve_interior_vertex_and_edge_midsides(self):
        cells, bodies = topology(FOUR_TETRA, FOUR_FACES)
        self.assertEqual(g.exterior_nodes(cells, bodies), [{'component_id': 'body',
            'exterior_node_indices': [0, 1, 2, 3, 5, 6, 7, 8, 9, 10],
            'interior_node_indices': [4, 11, 12, 13, 14], 'boundary_face_count': 4}])

    def test_distinct_body_ids_never_merge_and_body_order_is_retained(self):
        # Physical coincidence is intentionally not a topology input: separate
        # native node identities must remain separate for identical connectivity.
        first, first_body = topology([SINGLE_TETRA], SINGLE_FACES, 'first')
        second, second_body = topology([[n+100 for n in SINGLE_TETRA]],
                                      [[n+100 for n in face] for face in SINGLE_FACES], 'second')
        for cell in second: cell['index'] += 5
        second_body[0]['volume_cell_indices'] = [5]
        second_body[0]['face_cell_indices'] = [6, 7, 8, 9]
        actual = g.exterior_nodes(first+second, second_body+first_body)
        self.assertEqual([row['component_id'] for row in actual], ['second', 'first'])
        self.assertEqual(actual[0]['exterior_node_indices'], list(range(100, 110)))
        self.assertEqual(actual[1]['exterior_node_indices'], list(range(10)))
        self.assertEqual([row['interior_node_indices'] for row in actual], [[], []])

    def test_same_set_shared_face_midside_permutations_refuse(self):
        # Independent review's counterexample: both full shared faces contain
        # exactly0,1,2,4,5,6, but edge0-1 is4 versus5 and edge1-2 is5 versus4.
        tetrahedra = [SINGLE_TETRA, [0, 1, 2, 10, 5, 4, 6, 11, 12, 13]]
        triangles = [[0, 1, 3, 4, 8, 7], [0, 2, 3, 6, 9, 7], [1, 2, 3, 5, 9, 8],
                     [0, 1, 10, 5, 12, 11], [0, 2, 10, 6, 13, 11], [1, 2, 10, 4, 13, 12]]
        for reversed_volume_order in (False, True):
            with self.subTest(reversed_volume_order=reversed_volume_order):
                cells, bodies = topology(tetrahedra, triangles)
                for nodes in tetrahedra:
                    self.assertEqual(sorted(nodes[i] for i in (0, 1, 2, 4, 5, 6)), [0, 1, 2, 4, 5, 6])
                if reversed_volume_order:
                    bodies[0]['volume_cell_indices'].reverse()
                with self.assertRaisesRegex(ValueError, '^Nonconforming native edge midside identity$'):
                    g.exterior_nodes(cells, bodies)

    def test_same_set_boundary_tria_midside_permutations_refuse(self):
        for triangle_number, slots in ((0, (3, 4)), (1, (4, 5))):
            with self.subTest(triangle_number=triangle_number, swapped_slots=slots):
                triangles = deepcopy(SINGLE_FACES)
                before = list(triangles[triangle_number])
                left, right = slots
                triangles[triangle_number][left], triangles[triangle_number][right] = before[right], before[left]
                self.assertEqual(sorted(triangles[triangle_number]), sorted(before))
                cells, bodies = topology([SINGLE_TETRA], triangles)
                with self.assertRaisesRegex(ValueError, '^Boundary face native edge midside identity differs$'):
                    g.exterior_nodes(cells, bodies)

    def test_edge_only_shared_identity_is_complete_and_inconsistent_mid_refuses(self):
        for inconsistent in (False, True):
            with self.subTest(inconsistent=inconsistent):
                tetrahedra, triangles = deepcopy((EDGE_ONLY_TETRA, EDGE_ONLY_FACES))
                self.assertEqual(set(tetrahedra[0][:4]) & set(tetrahedra[1][:4]), {0, 1})
                if inconsistent:
                    tetrahedra[1][4] = 99
                    triangles[4][3] = 99
                    triangles[5][3] = 99
                cells, bodies = topology(tetrahedra, triangles)
                if inconsistent:
                    with self.assertRaisesRegex(ValueError, '^Nonconforming native edge midside identity$'):
                        g.exterior_nodes(cells, bodies)
                else:
                    self.assertEqual(g.exterior_nodes(cells, bodies), [{'component_id': 'body',
                        'exterior_node_indices': list(range(17)), 'interior_node_indices': [], 'boundary_face_count': 8}])

    def test_midside_alias_and_corner_role_conflicts_refuse(self):
        for fault in ('midside_alias', 'corner_role'):
            with self.subTest(fault=fault):
                tetrahedra, triangles = deepcopy((EDGE_ONLY_TETRA, EDGE_ONLY_FACES))
                if fault == 'midside_alias':
                    # Node5 already names edge1-2; it cannot also name1-10.
                    tetrahedra[1][5] = 5
                    triangles[4][4] = 5
                    triangles[7][3] = 5
                    error = '^Native midside identity may not name different corner edges$'
                else:
                    # Node5 is an existing midside, now used as another cell's
                    # corner with otherwise unique complete local connectivity.
                    tetrahedra[1][2] = 5
                    triangles[4][2] = 5
                    triangles[6][1] = 5
                    triangles[7][1] = 5
                    error = '^Native node identity may not be both corner and midside$'
                self.assertEqual(len(set(tetrahedra[1])), 10)
                cells, bodies = topology(tetrahedra, triangles)
                with self.assertRaisesRegex(ValueError, error):
                    g.exterior_nodes(cells, bodies)

    def test_correct_native_corner_and_midside_permutations_preserve_full_output(self):
        cases = [
            ('tria_orientations', [SINGLE_TETRA],
             [[2, 0, 1, 6, 4, 5], [1, 0, 3, 4, 7, 8], [3, 2, 0, 9, 6, 7], [2, 1, 3, 5, 8, 9]],
             {'component_id': 'body', 'exterior_node_indices': list(range(10)),
              'interior_node_indices': [], 'boundary_face_count': 4}),
            ('tetra_orientation', [[1, 0, 2, 3, 4, 6, 5, 8, 7, 9]], SINGLE_FACES,
             {'component_id': 'body', 'exterior_node_indices': list(range(10)),
              'interior_node_indices': [], 'boundary_face_count': 4}),
            ('shared_face_corner_order', [SINGLE_TETRA, [2, 0, 1, 10, 6, 4, 5, 13, 11, 12]], TWO_FACES,
             {'component_id': 'body', 'exterior_node_indices': list(range(14)),
              'interior_node_indices': [], 'boundary_face_count': 6}),
        ]
        for name, tetrahedra, triangles, expected in cases:
            with self.subTest(permutation=name):
                cells, bodies = topology(tetrahedra, triangles)
                self.assertEqual(g.exterior_nodes(cells, bodies), [expected])

    def test_missing_wrong_duplicate_internal_and_nonmanifold_faces_refuse(self):
        cases = []
        cells, bodies = topology([SINGLE_TETRA], SINGLE_FACES[:-1]); cases.append(('missing_last', cells, bodies))
        cells, bodies = topology([SINGLE_TETRA], SINGLE_FACES)
        cells[-1]['node_indices'][-1] = 99; cases.append(('wrong_boundary_midside', cells, bodies))
        cells, bodies = topology([SINGLE_TETRA], SINGLE_FACES+[SINGLE_FACES[0]])
        cases.append(('duplicate_boundary', cells, bodies))
        cells, bodies = topology(TWO_TETRA, TWO_FACES)
        cells[1]['node_indices'][4] = 99; cases.append(('nonconforming_internal_midside', cells, bodies))
        cells, bodies = topology(TWO_TETRA, TWO_FACES+[SINGLE_FACES[0]])
        cases.append(('internal_face_supplied_as_exterior', cells, bodies))
        cells, bodies = topology([SINGLE_TETRA, SINGLE_TETRA], SINGLE_FACES)
        cases.append(('duplicate_tetra_topology', cells, bodies))
        third = [0, 1, 2, 14, 4, 5, 6, 15, 16, 17]
        cells, bodies = topology(TWO_TETRA+[third], [SINGLE_FACES[1]])
        cases.append(('nonmanifold_shared_face', cells, bodies))
        cells, bodies = topology([SINGLE_TETRA], SINGLE_FACES)
        cells[-1]['node_indices'] = [20, 21, 22, 23, 24, 25]
        cases.append(('foreign_boundary_face', cells, bodies))
        for name, cells, bodies in cases:
            with self.subTest(fault=name):
                with self.assertRaises(ValueError): g.exterior_nodes(cells, bodies)

    def test_strict_cell_json_integer_and_key_controls(self):
        for fault in ('cell_extra', 'cell_missing', 'bool_index', 'float_index', 'negative_index', 'duplicate_index',
                      'foreign_index', 'wrong_volume_type', 'wrong_face_type', 'short_connectivity', 'duplicate_node',
                      'bool_node', 'float_node', 'negative_node', 'tuple_nodes', 'tuple_cells'):
            cells, bodies = topology([SINGLE_TETRA], SINGLE_FACES)
            if fault == 'cell_extra': cells[0]['extra'] = 'bad'
            elif fault == 'cell_missing': cells[0].pop('type')
            elif fault == 'bool_index': cells[0]['index'] = False
            elif fault == 'float_index': cells[0]['index'] = 0.
            elif fault == 'negative_index': cells[0]['index'] = -1
            elif fault == 'duplicate_index': cells[1]['index'] = 0
            elif fault == 'foreign_index': cells[0]['index'] = 99
            elif fault == 'wrong_volume_type': cells[0]['type'] = 'TRIA6'
            elif fault == 'wrong_face_type': cells[1]['type'] = 'TRIA3'
            elif fault == 'short_connectivity': cells[0]['node_indices'].pop()
            elif fault == 'duplicate_node': cells[0]['node_indices'][1] = 0
            elif fault == 'bool_node': cells[0]['node_indices'][1] = True
            elif fault == 'float_node': cells[0]['node_indices'][1] = 1.
            elif fault == 'negative_node': cells[0]['node_indices'][1] = -1
            elif fault == 'tuple_nodes': cells[0]['node_indices'] = tuple(cells[0]['node_indices'])
            elif fault == 'tuple_cells': cells = tuple(cells)
            with self.subTest(fault=fault):
                with self.assertRaises(ValueError): g.exterior_nodes(cells, bodies)

    def test_strict_body_scope_and_cross_body_identity_controls(self):
        for fault in ('body_extra', 'body_missing', 'empty_component', 'component_type', 'empty_volume', 'empty_faces',
                      'bool_volume', 'float_face', 'foreign_volume', 'duplicate_face_index', 'face_as_volume',
                      'missing_cell_owner', 'overlapping_owner', 'duplicate_component', 'shared_nodes', 'tuple_bodies'):
            cells, bodies = topology([SINGLE_TETRA], SINGLE_FACES)
            if fault == 'body_extra': bodies[0]['extra'] = 1
            elif fault == 'body_missing': bodies[0].pop('component_id')
            elif fault == 'empty_component': bodies[0]['component_id'] = ' '
            elif fault == 'component_type': bodies[0]['component_id'] = True
            elif fault == 'empty_volume': bodies[0]['volume_cell_indices'] = []
            elif fault == 'empty_faces': bodies[0]['face_cell_indices'] = []
            elif fault == 'bool_volume': bodies[0]['volume_cell_indices'] = [False]
            elif fault == 'float_face': bodies[0]['face_cell_indices'][0] = 1.
            elif fault == 'foreign_volume': bodies[0]['volume_cell_indices'] = [99]
            elif fault == 'duplicate_face_index': bodies[0]['face_cell_indices'].append(1)
            elif fault == 'face_as_volume': bodies[0]['volume_cell_indices'] = [1]
            elif fault == 'missing_cell_owner': bodies[0]['face_cell_indices'].pop()
            elif fault == 'overlapping_owner': bodies.append({**deepcopy(bodies[0]), 'component_id': 'other'})
            elif fault in ('duplicate_component', 'shared_nodes'):
                other, declared = topology([SINGLE_TETRA], SINGLE_FACES, 'body' if fault == 'duplicate_component' else 'other')
                for cell in other: cell['index'] += 5
                declared[0]['volume_cell_indices'] = [5]; declared[0]['face_cell_indices'] = [6, 7, 8, 9]
                cells += other; bodies += declared
            elif fault == 'tuple_bodies': bodies = tuple(bodies)
            with self.subTest(fault=fault):
                with self.assertRaises(ValueError): g.exterior_nodes(cells, bodies)

    def test_full_identity_nonmutation_and_unordered_cell_rows(self):
        cells, bodies = topology(FOUR_TETRA, FOUR_FACES)
        original = deepcopy((cells, bodies))
        expected = g.exterior_nodes(cells, bodies)
        self.assertEqual((cells, bodies), original)
        self.assertEqual(g.exterior_nodes(list(reversed(cells)), bodies), expected)
        self.assertEqual(set(expected[0]), {'component_id', 'exterior_node_indices',
                                          'interior_node_indices', 'boundary_face_count'})
        expected[0]['exterior_node_indices'].append(99)
        self.assertEqual(g.exterior_nodes(cells, bodies)[0]['exterior_node_indices'], [0, 1, 2, 3, 5, 6, 7, 8, 9, 10])


if __name__ == '__main__':
    unittest.main()
