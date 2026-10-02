"""Bounded public synthetic MSH syntax controls; native execution is absent."""

from copy import deepcopy
import hashlib

import pytest

from caelab.adapters import fenicsx_gmsh as syntax
from caelab.adapters.fenicsx_imported import manufactured_settings
from caelab.adapters.fenicsx_worker import PDEInputError


def rehash(row, data):
    row["data"] = data
    row["sha256"] = hashlib.sha256(data.encode("ascii")).hexdigest()


def test_sparse_original_ids_crlf_and_permuted_rows_survive_distinct_dense_copy():
    row = syntax.manufactured_mesh("l_shape", 2)
    lines = row["data"].splitlines()
    for name in ("Nodes", "Elements"):
        start, end = lines.index("$"+name)+2, lines.index("$End"+name)
        lines[start:end] = list(reversed(lines[start:end]))
    rehash(row, "\r\n".join(lines)+"\r\n")
    original_bytes, original = row["data"].encode("ascii"), deepcopy(row)
    mesh = syntax.parse_msh(row["data"], row["sha256"])
    before = deepcopy(mesh)
    data, table = syntax.dense_import(mesh)
    assert row == original and row["data"].encode("ascii") == original_bytes and mesh == before
    assert table["original_node_ids"] == [node["id"] for node in mesh["nodes"]]
    assert table["dense_node_ids"] == list(range(1, len(mesh["nodes"])+1))
    assert table["original_node_ids"] != table["dense_node_ids"]
    derived = syntax.parse_msh(data, table["dense_sha256"])
    assert derived["body"] == mesh["body"] and set(derived["boundaries"]) == set(mesh["boundaries"])
    inverse = dict(zip(table["dense_node_ids"], table["original_node_ids"]))
    for actual, expected in zip(derived["cells"], mesh["cells"]):
        assert actual["id"] == expected["id"] and [inverse[node] for node in actual["node_ids"]] == expected["node_ids"]
    assert hashlib.sha256(original_bytes).hexdigest() == table["original_sha256"]
    assert syntax.dense_import(mesh) == (data, table)


@pytest.mark.parametrize("kind", ["hash", "extra_section", "binary", "count", "truncated", "duplicate_node", "nonfinite", "z", "id", "high_order", "tags", "missing_name", "cross_dimension_name", "mixed_entity"])
def test_malformed_backend_syntax_refuses_before_any_native_api(kind):
    row = syntax.manufactured_mesh("l_shape", 1)
    data = row["data"]
    if kind == "hash":
        row["sha256"] = "0"*64
    elif kind == "extra_section": data += "$Comments\nunsupported\n$EndComments\n"
    elif kind == "binary": data = data.replace("2.2 0 8", "2.2 1 8")
    elif kind == "count": data = data.replace("$Nodes\n8\n", "$Nodes\n9\n")
    elif kind == "truncated": data = data.replace("$EndElements\n", "")
    elif kind in ("duplicate_node", "nonfinite", "z", "id"):
        lines = data.splitlines()
        index = lines.index("$Nodes")+2
        tokens = lines[index].split()
        if kind == "duplicate_node": tokens[0] = lines[index+1].split()[0]
        elif kind == "nonfinite": tokens[1] = "nan"
        elif kind == "z": tokens[3] = "1e-100"
        else: tokens[0] = str(2**31)
        lines[index] = " ".join(tokens)
        data = "\n".join(lines)+"\n"
    elif kind in ("high_order", "tags"):
        lines = data.splitlines()
        index = lines.index("$Elements")+2
        tokens = lines[index].split()
        tokens[1 if kind == "high_order" else 2] = "9" if kind == "high_order" else "3"
        lines[index] = " ".join(tokens)
        data = "\n".join(lines)+"\n"
    elif kind == "missing_name": data = data.replace('1 2 "west"', '1 99 "west"')
    elif kind == "cross_dimension_name": data = data.replace('1 2 "west"', '1 2 "body"')
    else:
        mesh = syntax.parse_msh(data, row["sha256"])
        # west and south use one elementary entity, which Gmsh treats entity-wide.
        mesh["boundaries"]["south"]["elements"][0]["entity_tag"] = 2
        data = syntax._format(mesh)
    if kind != "hash": rehash(row, data)
    with pytest.raises(PDEInputError): syntax.parse_msh(row["data"], row["sha256"])


def test_total_inline_bound_exact_shape_labels_and_ascii_are_checked():
    settings = manufactured_settings()
    assert sum(len(row["data"].encode("ascii")) for row in settings["mesh"]["levels"]) < syntax.MAX_BYTES
    wrong = deepcopy(settings)
    wrong["mesh"]["levels"] *= 2
    with pytest.raises(PDEInputError, match="Total original"): syntax.prepare(wrong)
    for mutate in (lambda s: s["mesh"]["levels"][0].update(path="/tmp/mesh.msh"),
                   lambda s: s["mesh"]["levels"][0].update(source="x"*257),
                   lambda s: s["mesh"]["levels"][0].update(data="한글"),
                   lambda s: s["mesh"].update(degree=True)):
        wrong = deepcopy(settings)
        mutate(wrong)
        with pytest.raises(PDEInputError): syntax.prepare(wrong)


def test_dense_mapping_does_not_change_physical_names_or_element_entity_ids():
    original = syntax.manufactured_mesh("rectangle", 3)
    mesh = syntax.parse_msh(original["data"], original["sha256"])
    data, table = syntax.dense_import(mesh)
    copy = syntax.parse_msh(data, table["dense_sha256"])
    for name in mesh["boundaries"]:
        assert copy["boundaries"][name]["tag"] == mesh["boundaries"][name]["tag"]
        assert [(row["id"], row["entity_tag"]) for row in copy["boundaries"][name]["elements"]] == [(row["id"], row["entity_tag"]) for row in mesh["boundaries"][name]["elements"]]


def test_derived_round_trip_expansion_never_changes_original_inline_size_gate():
    row = syntax.manufactured_mesh("rectangle", 24)
    lines = row["data"].splitlines()
    start, stop = lines.index("$Nodes")+2, lines.index("$EndNodes")
    for i in range(start, stop):
        tokens = lines[i].split()
        # A legal compact decimal source can expand on full-precision transport.
        lines[i] = f"{tokens[0]} {round(float(tokens[1]), 2)!r} {round(float(tokens[2]), 2)!r} 0"
    rehash(row, "\n".join(lines)+"\n")
    assert len(row["data"]) < syntax.MAX_BYTES
    mesh = syntax.parse_msh(row["data"], row["sha256"])
    before = deepcopy(mesh)
    data, table = syntax.dense_import(mesh)
    assert len(data) > syntax.MAX_BYTES and mesh == before
    assert syntax._parse_msh(data, table["dense_sha256"], len(data))["nodes"][0]["coordinates"] == mesh["nodes"][0]["coordinates"]
    with pytest.raises(PDEInputError, match="byte count"): syntax.parse_msh(data, table["dense_sha256"])
    oversized = row["data"].replace("$Nodes\n", "$Nodes\n"+"0"*syntax.MAX_BYTES)
    with pytest.raises(PDEInputError): syntax.parse_msh(oversized, hashlib.sha256(oversized.encode("ascii")).hexdigest())
