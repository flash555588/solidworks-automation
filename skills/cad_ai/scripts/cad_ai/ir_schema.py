"""CAD-IR v0 schema (Python literals).

This module is a thin, dependency-free schema description.  It does not
use pydantic or jsonschema because the build environment for cad_ai must
remain a single standard-library Python (no third-party deps at this
layer; the build123d dependency comes from skills/cad, not cad_ai).

The validator (`ir_validate.py`) walks the schema literally; the
schema itself is a constant so the validator and the docs (in
`references/cad_intent_schema.md`) cannot drift silently.
"""

from __future__ import annotations

# Schema constants
SCHEMA_NAME = "cad_ir.v0"
SUPPORTED_UNITS = ("mm", "cm", "in")
SUPPORTED_UP_AXES = ("X", "Y", "Z")
SUPPORTED_FRONT_AXES = ("X", "Y", "Z")
SUPPORTED_DOCUMENT_TYPES = ("part", "assembly", "drawing")
SUPPORTED_FEATURE_TYPES = (
    "extrude_add",
    "extrude_cut",
    "hole_through",
    "fillet",
    "chamfer",
    "join_bodies",      # v0.2: boolean union all bodies into one
    "sweep",            # v0.2: build123d-only; SW unsupported
    "revolve",          # v0.4: revolve boss / cut
    "loft",             # v0.4: loft boss / cut
    "mirror",           # v0.4: mirror features
    "linear_pattern",   # v0.4: linear feature pattern
    "circular_pattern", # v0.4: circular feature pattern
    "shell",            # v0.4: shell / hollow
    "draft",            # v0.4: draft / taper
    "loft_surface",     # v0.5: loft surface
    "thicken",          # v0.5: thicken surface
    "fill_surface",     # v0.5: fill surface
    "knit",             # v0.5: knit surfaces
    "add_component",    # v0.6: assembly component
    "mate_coincident",  # v0.6: coincident mate
    "mate_concentric",  # v0.6: concentric mate
    "mate_distance",    # v0.6: distance mate
    "new_drawing",      # v0.6: drawing sheet
    "add_view",         # v0.6: drawing view
    "add_dimension",    # v0.6: drawing dimension
    "equation",         # v0.8: design equation
    "generate_bom",     # v0.8: BOM generation
    "add_configuration", # v0.9: add configuration
    "set_configuration", # v0.9: switch configuration
    "suppress_feature",  # v0.9: suppress feature in config
    "design_table",      # v0.9: design table (family table)
)
SUPPORTED_SKETCH_ENTITY_TYPES = (
    "center_rectangle",
    "polygon",
    "circle",
    "circle_pattern",
)
SUPPORTED_SELECTOR_TYPES = (
    "top_outer_edges",
    "bottom_outer_edges",
    "all_edges",
)


# Field requirements (path -> required_type)
# Validator uses these to emit structured error paths.
TOP_LEVEL_FIELDS = {
    "schema": str,
    "units": str,
    "document": dict,
    "coordinate_system": dict,
    "parameters": dict,
    "features": list,
    "acceptance": dict,
    "assumptions": list,  # optional
}

DOCUMENT_FIELDS = {
    "type": str,
    "name": str,
}

COORDINATE_SYSTEM_FIELDS = {
    "origin": str,
    "up_axis": str,
    "front_axis": str,
}

# Feature field requirements (subset of the union of all feature types).
# Each feature's actual type-specific fields are checked by the validator
# at runtime; here we only list the always-present fields.
FEATURE_BASE_FIELDS = {
    "id": str,
    "type": str,
}

# Per-type required fields. The validator consults this table to know
# which fields must be present.
FEATURE_TYPE_FIELDS = {
    "extrude_add": {"sketch": dict, "depth": (int, float, str), "direction": str},
    "extrude_cut": {"sketch": dict, "depth": (int, float, str), "direction": str,
                    "target": str},
    "hole_through": {"diameter": (int, float, str), "axis": str, "target": str,
                      "position": (list, str)},
    "fillet": {"radius": (int, float, str), "selector": dict, "target": str},
    "chamfer": {"size": (int, float, str), "selector": dict, "target": str},
    "join_bodies": {},  # v0.2: no additional fields required
    "sweep": {"profile": dict, "path": dict},
    "revolve": {"sketch": dict, "angle": (int, float, str), "axis": str},
    "loft": {"profiles": list, "closed": bool},
    "mirror": {"features": list, "plane": str},
    "linear_pattern": {"features": list, "direction": str, "spacing": (int, float, str), "count": int},
    "circular_pattern": {"features": list, "axis": str, "count": int, "angle": (int, float, str)},
    "shell": {"thickness": (int, float, str), "faces": (list, str)},
    "draft": {"faces": (list, str), "angle": (int, float, str), "direction": str},
    "loft_surface": {"profiles": list, "closed": bool},
    "thicken": {"surface": str, "thickness": (int, float, str), "direction": str},
    "fill_surface": {"boundary": list},
    "knit": {"surfaces": list},
    "add_component": {"path": str, "x": (int, float, str), "y": (int, float, str), "z": (int, float, str)},
    "mate_coincident": {"component_a": str, "feature_a": str, "component_b": str, "feature_b": str},
    "mate_concentric": {"component_a": str, "feature_a": str, "component_b": str, "feature_b": str},
    "mate_distance": {"component_a": str, "feature_a": str, "component_b": str, "feature_b": str, "distance": (int, float, str)},
    "new_drawing": {"sheet_size": str},
    "add_view": {"model": str, "orientation": str, "scale": (int, float, str)},
    "add_dimension": {"entity_a": str, "entity_b": str, "value": (int, float, str)},
    "add_view": {"model": str, "view_type": str, "x": (int, float, str), "y": (int, float, str), "scale": (int, float, str)},
}

SKETCH_BASE_FIELDS = {
    "plane": str,
    "entities": list,
}

SKETCH_ENTITY_FIELDS = {
    "center_rectangle": {"center": list, "size": list},
    "polygon": {"center": list, "radius": (int, float, str), "sides": int},
    "circle": {"center": list, "diameter": (int, float, str)},
    "circle_pattern": {"centers": list, "diameter": (int, float, str)},
}

SELECTOR_FIELDS = {
    "kind": str,
    "target": str,
}
