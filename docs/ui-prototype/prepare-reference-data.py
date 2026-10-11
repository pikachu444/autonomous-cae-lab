"""Prepare display data from retained local artifacts; never run or alter a solver."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "src" / "replicas"
ASSEMBLY = ROOT / "runs/cae-assembly-conditions-20261006-01/experiments/E-assembly-default/cad/surface.json"
RESULT = ROOT / "runs/desktop-post-20261008-03/B_200N_U.vtu"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    before = {str(p.relative_to(ROOT)): digest(p) for p in (ASSEMBLY, RESULT)}
    surface = json.loads(ASSEMBLY.read_text(encoding="utf-8"))
    grouped = {}
    colors = ["#799bc7", "#d6af60", "#b7816a", "#8eafa7", "#bb7590", "#93ac6e"]
    for face in surface["faces"]:
        identity = face["component_id"]
        if identity not in grouped:
            pretty = identity.replace("metal_", "").replace("printed_", "").replace("_", " ").title()
            color = "#9aabc0" if "bolt" in identity or "washer" in identity else colors[len(grouped) % len(colors)]
            grouped[identity] = dict(id=identity, name=pretty, color=color,
                kind="Fastener" if "bolt" in identity or "washer" in identity else "Solid component",
                faces=0, triangles=0, positions=[], faceIds=[])
        item = grouped[identity]
        item["faces"] += 1
        item["triangles"] += len(face["triangles"])
        for triangle in face["triangles"]:
            assert len(triangle) == 9
            item["positions"].extend(triangle)
            item["faceIds"].append(face["id"])
    assembly = list(grouped.values())

    root = ET.parse(RESULT).getroot()
    piece = root.find(".//Piece")
    arrays = {el.attrib.get("Name"): el for el in root.findall(".//DataArray")}
    array = lambda name: [float(x) for x in arrays[name].text.split()]
    integers = lambda name: [int(x) for x in arrays[name].text.split()]
    xyz, ux, uy, uz, magnitudes = [array(name) for name in ("Position_mm", "UX_mm", "UY_mm", "UZ_mm", "U_magnitude_mm")]
    ids = integers("NativeNodeId")
    connectivity, offsets, types = [integers(name) for name in ("connectivity", "offsets", "types")]
    assert len(ids) == int(piece.attrib["NumberOfPoints"]) == len(ux) == len(uy) == len(uz) == len(magnitudes)
    assert len(xyz) == len(ids) * 3 and len(set(ids)) == len(ids)
    faces, previous = [], 0
    patterns = [(0, 2, 1, 6, 5, 4), (0, 1, 3, 4, 8, 7), (1, 2, 3, 5, 9, 8), (2, 0, 3, 6, 7, 9)]
    for offset, cell_type in zip(offsets, types):
        cell = connectivity[previous:offset]
        previous = offset
        assert cell_type == 24 and len(cell) == 10, "Only the retained quadratic tetrahedral source is expected"
        faces.extend(tuple(cell[i] for i in face) for face in patterns)
    counts = Counter(tuple(sorted(face[:3])) for face in faces)
    triangles = []
    for face in faces:
        if counts[tuple(sorted(face[:3]))] != 1:
            continue
        a, b, c, ab, bc, ca = face
        triangles.extend([a, ab, ca, ab, b, bc, ca, bc, c, ab, bc, ca])
    fixed, loaded = integers("FixedXYZ_input"), integers("LoadedNode_input")
    nodes = [dict(id=node_id, x=xyz[i*3], y=xyz[i*3+1], z=xyz[i*3+2],
                  ux=ux[i], uy=uy[i], uz=uz[i], magnitude=magnitudes[i],
                  fixed=bool(fixed[i]), loaded=bool(loaded[i])) for i, node_id in enumerate(ids)]
    assert max(triangles) < len(nodes) and min(triangles) >= 0
    data = dict(nodes=nodes, triangles=triangles,
                info=dict(nodes=len(ids), elements=len(offsets), unit="mm",
                          source="Retained CalculiX 2.21 · 200 N static load · support",
                          maxMagnitude=max(magnitudes), minUz=min(uz), maxUz=max(uz)))
    OUT.mkdir(parents=True, exist_ok=True)
    for filename, value in (("assembly-data.json", assembly), ("result-data.json", data)):
        (OUT / filename).write_text(json.dumps(value, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    after = {str(p.relative_to(ROOT)): digest(p) for p in (ASSEMBLY, RESULT)}
    assert before == after, "Input source was changed"
    record = dict(source_sha256=before, component_count=len(assembly),
                  display_triangles=sum(x["triangles"] for x in assembly),
                  result_nodes=len(nodes), result_elements=len(offsets),
                  result_boundary_triangles=len(triangles)//3,
                  solver_executions=0, engineering_verdict="UNKNOWN_NOT_RELEASED")
    (OUT / "data-origin.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items() if k != "source_sha256"}))


if __name__ == "__main__":
    prepare()
