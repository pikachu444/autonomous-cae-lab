"""Pure VTK arrays and retained C3D10 displacement-field serialization."""
import base64
import math
import struct
from xml.etree import ElementTree as ET


def data_array(parent, name, values, components=1, integer=False):
    attrs = {"type": "Int64" if integer else "Float64", "Name": name, "format": "ascii"}
    if components != 1:
        attrs["NumberOfComponents"] = str(components)
    if integer:
        text = " ".join(str(v) for v in values)
    else:
        numbers = [float(v) for v in values]
        if any(not math.isfinite(v) for v in numbers):
            # VTK's ASCII extraction can reject its own nan/inf spellings.
            # Inline uncompressed binary: UInt32 byte count + Float64 payload,
            # both little-endian, encoded as one contiguous base64 stream.
            if len(numbers) > 0xffffffff // 8:
                raise ValueError("VTK inline array exceeds the UInt32 byte-length header")
            payload = struct.pack("<" + str(len(numbers)) + "d", *numbers)
            text = base64.b64encode(struct.pack("<I", len(payload)) + payload).decode("ascii")
            attrs["format"] = "binary"
        else:
            text = " ".join(format(v, ".17g") for v in numbers)
    child = ET.SubElement(parent, "DataArray", attrs)
    child.text = text
    return child


def write_vtu(path, raw, extra=None):
    nodes = raw["nodes"]
    index = {row["node_id"]: i for i, row in enumerate(nodes)}
    vtk = ET.Element("VTKFile", type="UnstructuredGrid", version="0.1", byte_order="LittleEndian", header_type="UInt32")
    grid = ET.SubElement(vtk, "UnstructuredGrid")
    piece = ET.SubElement(grid, "Piece", NumberOfPoints=str(len(nodes)), NumberOfCells=str(len(raw["elements"])))
    points = ET.SubElement(piece, "Points")
    data_array(points, "Position_mm", (v for row in nodes for v in row["position_mm"]), 3)
    cells = ET.SubElement(piece, "Cells")
    # CalculiX C3D10 and VTK_QUADRATIC_TETRA use the same six midside-edge order.
    data_array(cells, "connectivity", (index[n] for row in raw["elements"] for n in row["node_ids"]), integer=True)
    data_array(cells, "offsets", (10 * (i + 1) for i in range(len(raw["elements"]))), integer=True)
    data_array(cells, "types", (24 for _ in raw["elements"]), integer=True)
    point_data = ET.SubElement(piece, "PointData", Scalars="U_magnitude_mm", Vectors="U_mm")
    data_array(point_data, "NativeNodeId", (row["node_id"] for row in nodes), integer=True)
    vector = data_array(point_data, "U_mm", (v for row in nodes for v in row["displacement_mm"]), 3)
    for i, name in enumerate(("UX", "UY", "UZ")):
        vector.set(f"ComponentName{i}", name)
        data_array(point_data, name + "_mm", (row["displacement_mm"][i] for row in nodes))
    data_array(point_data, "U_magnitude_mm", (math.hypot(*row["displacement_mm"]) for row in nodes))
    fixed = set(raw["fixed_node_ids"])
    loaded = {row["node_id"] for row in raw["loads"]}
    data_array(point_data, "FixedXYZ_input", (int(row["node_id"] in fixed) for row in nodes), integer=True)
    data_array(point_data, "LoadedNode_input", (int(row["node_id"] in loaded) for row in nodes), integer=True)
    for name, values in (extra or {}).items():
        data_array(point_data, name, values)
    cell_data = ET.SubElement(piece, "CellData")
    data_array(cell_data, "NativeElementId", (row["element_id"] for row in raw["elements"]), integer=True)
    ET.ElementTree(vtk).write(path, encoding="utf-8", xml_declaration=True)
