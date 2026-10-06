"""Owned Gmsh worker: immutable STEP/FaceN catalog to declared surface loads.

No native face order or display triangle is used as a Gmsh selection. Surface
geometry is matched explicitly and an ambiguous or incomplete map is refused.
"""
from pathlib import Path
import hashlib
import json
import math
import sys

import gmsh
import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def match_faces(rows):
    surfaces = {}
    for _, tag in gmsh.model.getEntities(2):
        bbox = gmsh.model.occ.getBoundingBox(2, tag)
        surfaces[tag] = {'area_mm2': gmsh.model.occ.getMass(2, tag),
                         'center_mm': gmsh.model.occ.getCenterOfMass(2, tag),
                         'bounds_mm': {'min': bbox[:3], 'max': bbox[3:]}}
    matches, used = {}, set()
    for row in rows:
        length = max(1., *(b-a for a, b in zip(row['bounds_mm']['min'], row['bounds_mm']['max'])))
        candidates = []
        for tag, shape in surfaces.items():
            # OCCT STEP/BREP serialization tolerances, never solver acceptance.
            area_ok = abs(shape['area_mm2'] - row['area_mm2']) <= 1e-7 * max(1., row['area_mm2'])
            values = [*shape['center_mm'], *shape['bounds_mm']['min'], *shape['bounds_mm']['max']]
            declared = [*row['center_mm'], *row['bounds_mm']['min'], *row['bounds_mm']['max']]
            if area_ok and max(abs(a-b) for a, b in zip(values, declared)) <= 1e-6 * length:
                candidates.append(tag)
        if len(candidates) != 1 or candidates[0] in used:
            raise ValueError('Native face geometry has no unique STEP/Gmsh surface association: ' + row['id'])
        matches[row['id']] = candidates[0]
        used.add(candidates[0])
    if used != set(surfaces):
        raise ValueError('The native catalog does not cover the same complete STEP surface topology')
    return matches, surfaces


def execute(request):
    step = Path(request['step'])
    if sha(step) != request['step_sha256']:
        raise ValueError('Native STEP changed before mesh preparation')
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.NumThreads', 2)
        gmsh.option.setNumber('General.Terminal', 1)
        gmsh.option.setNumber('Geometry.OCCBoundsUseStl', 0)
        gmsh.model.add('revision_bound_native_solid')
        gmsh.model.occ.importShapes(str(step))
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise ValueError('This native mechanics worker requires one final solid')
        faces = [s for s in request['catalog']['selections'] if s.get('kind') == 'native_face']
        mapping, shapes = match_faces(faces)
        size = request['declaration']['mesh']['max_size_mm']
        if type(size) not in (int, float) or not math.isfinite(size) or size <= 0:
            raise ValueError('Mesh size must be finite and positive')
        gmsh.option.setNumber('Mesh.MeshSizeMin', size / 3)
        gmsh.option.setNumber('Mesh.MeshSizeMax', size)
        gmsh.option.setNumber('Mesh.Algorithm3D', 1)
        gmsh.model.mesh.generate(3)
        gmsh.model.mesh.setOrder(2)
        gmsh.model.mesh.optimize('HighOrder')
        types, tags, connectivity = gmsh.model.mesh.getElements(3)
        if list(types) != [11]:
            raise ValueError('Only a complete quadratic tetrahedral solid mesh is supported')
        _, dimension, order, count, reference, corners = gmsh.model.mesh.getElementProperties(11)
        if (dimension, order, count, corners) != (3, 2, 10, 4):
            raise ValueError('Unexpected native quadratic tetrahedral basis')
        reference = np.asarray(reference).reshape(10, 3)
        # CalculiX corner/edge ordering is explicit, rather than trusting Gmsh
        # API connectivity to equal its Abaqus writer's reordering.
        expected = [*reference[:4], *[(reference[a]+reference[b])/2 for a, b in
                    ((0,1),(1,2),(2,0),(0,3),(1,3),(2,3))]]
        permutation = []
        for point in expected:
            matches = np.where(np.max(np.abs(reference - point), axis=1) < 1e-14)[0]
            if len(matches) != 1:
                raise ValueError('Ambiguous native tetrahedral reference-node association')
            permutation.append(int(matches[0]))
        elements = {int(tag): [int(ns[index]) for index in permutation]
                    for tag, ns in zip(tags[0], np.asarray(connectivity[0]).reshape(-1, 10))}
        node_ids, xyz, _ = gmsh.model.mesh.getNodes()
        nodes = {int(tag): [float(x) for x in point]
                 for tag, point in zip(node_ids, np.asarray(xyz).reshape(-1, 3))}
        if not elements or not nodes or set(nodes) != {n for row in elements.values() for n in row}:
            raise ValueError('Incomplete native solid mesh connectivity')
        selected = {}
        boundary_triangles = []
        weights = {}
        for face_id, surface in mapping.items():
            ids, _, _ = gmsh.model.mesh.getNodes(2, surface, True, False)
            selected[face_id] = sorted(set(map(int, ids)))
            element_types, element_ids, surface_connectivity = gmsh.model.mesh.getElements(2, surface)
            if list(element_types) != [9]:
                raise ValueError('Native face mesh requires complete quadratic triangles')
            local, integration_weights = gmsh.model.mesh.getIntegrationPoints(9, 'Gauss4')
            components, basis, orientations = gmsh.model.mesh.getBasisFunctions(9, local, 'Lagrange')
            if components != 1 or orientations != 1:
                raise ValueError('Unexpected quadratic triangle basis definition')
            basis = np.asarray(basis).reshape(-1, 6)
            _, determinants, _ = gmsh.model.mesh.getJacobians(9, local, surface)
            determinant = np.asarray(determinants).reshape(-1, len(integration_weights))
            if np.any(~np.isfinite(determinant)) or np.any(determinant <= 0):
                raise ValueError('Nonpositive native surface Jacobian')
            nodal = (determinant * np.asarray(integration_weights)) @ basis
            face_weights = {}
            for index, (tag, row) in enumerate(zip(element_ids[0], np.asarray(surface_connectivity[0]).reshape(-1, 6))):
                ids = list(map(int, row))
                boundary_triangles.append({'element_id': int(tag), 'selection_id': face_id,
                                           'type': 'CPS6', 'node_ids': ids})
                for node, value in zip(ids, nodal[index]):
                    face_weights[node] = face_weights.get(node, 0.) + float(value)
            area = math.fsum(face_weights.values())
            if area <= 0 or not math.isfinite(area):
                raise ValueError('Native face has no positive integrated mesh area')
            weights[face_id] = {'mesh_area_mm2': area, 'native_area_mm2': shapes[surface]['area_mm2'],
                                'nodal_area_weights_mm2': {str(n): value for n, value in sorted(face_weights.items())}}
        if sha(step) != request['step_sha256']:
            raise ValueError('Native STEP changed during mesh preparation')
        gmsh.write(str(Path(request['output']) / 'native.msh'))
        return {'schema_version': 1, 'gmsh_version': gmsh.__version__, 'step_sha256': request['step_sha256'],
                'surface_map': mapping, 'surface_geometry': shapes,
                'nodes': {str(n): point for n, point in sorted(nodes.items())},
                'elements': {str(e): row for e, row in sorted(elements.items())},
                'gmsh_to_calculix_node_order': permutation,
                'boundary_triangles': boundary_triangles, 'face_nodes': selected, 'face_weights': weights,
                'cad_volume_mm3': gmsh.model.occ.getMass(3, volumes[0][1]),
                'load_distribution': 'consistent_quadratic_surface_shape_function_integration',
                'engineering_qualification': 'UNKNOWN'}
    finally:
        gmsh.finalize()


if __name__ == '__main__':
    request = json.loads(Path(sys.argv[1]).read_text())
    result = execute(request)
    Path(sys.argv[2]).write_text(json.dumps(result, allow_nan=False, indent=2) + '\n')
