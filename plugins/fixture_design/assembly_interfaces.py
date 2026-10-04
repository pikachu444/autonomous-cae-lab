"""Intended roles of the pinned original bending fixture, before mechanics.

These declarations identify components whose actual native faces the CAD
adapter must find. They prescribe no contact law, preload or strength rule.
Existing fixturelab engineering gates remain authoritative.
"""


def component_roles() -> dict[str, str]:
    return {
        "printed_base": "printed",
        "printed_support_left": "printed",
        "printed_support_right": "printed",
        "metal_roller_left": "metal",
        "metal_roller_right": "metal",
        "metal_loading_nose": "metal",
        "specimen": "specimen",
        **{f"metal_bolt_{side}_{dx}_{y}": "metal"
           for side in ("left", "right") for dx in (-10, 10) for y in (-12, 12)},
    }


def intended_interfaces() -> list[dict[str, str]]:
    pairs = []
    for side in ("left", "right"):
        support, roller = f"printed_support_{side}", f"metal_roller_{side}"
        pairs.extend([
            {"id": "base_to_support_" + side, "kind": "base_support",
             "a": "printed_base", "b": support},
            {"id": "support_cradle_to_roller_" + side, "kind": "cradle_roller",
             "a": support, "b": roller},
            {"id": "roller_to_specimen_" + side, "kind": "roller_specimen",
             "a": roller, "b": "specimen"},
        ])
        for dx in (-10, 10):
            for y in (-12, 12):
                bolt = f"metal_bolt_{side}_{dx}_{y}"
                pairs.append({"id": bolt + "_head_to_support_seat", "kind": "bolt_head_seat",
                              "a": bolt, "b": support})
    pairs.append({"id": "loading_nose_to_specimen", "kind": "nose_specimen",
                  "a": "metal_loading_nose", "b": "specimen"})
    return pairs
