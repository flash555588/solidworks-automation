# CAD Intent IR (CAD-IR) v0

## v1 limitations (read first)

The v1 schema accepts the same field set as v0, but the compiler
actually translates only a subset:

- **Sketch entities**: `center_rectangle`, `polygon`, `circle`,
  `circle_pattern`. Anything else is rejected at compile time.
- **Features**: `extrude_add` (the base), `hole_through` (axis must
  be `Z`; `X` and `Y` are explicitly rejected), `extrude_cut`
  (extrudes the cut sketch along the plane normal of its own
  sketch, not via an `axis` field), `fillet`, `chamfer`.
- **`extrude_add.direction`**: accepted by the validator but
  **ignored** by the v1 compiler.  The base extrude always goes
  along the plane normal.  This is by design (the canonical
  examples are Z-positive prismatic parts), but it is a real
  limitation: cut features on a slope cannot be expressed in v1.
- **Selector kinds for fillet/chamfer**: `all_edges` is the
  baseline and applies to every edge of the target body.
  `top_outer_edges` and `bottom_outer_edges` are translated by
  filtering on the body's bounding-box Z-extremum.  This works
  for prismatic solids (the v1 examples) but is **not yet
  verified** for sloped or compound targets.  Anything else is
  rejected.
- **At most one `extrude_add`**: the v1 compiler picks the first
  `extrude_add` in the feature list as the base body.  All other
  additive features are rejected.
- **Position expressions in `hole_through.position`**: the v1
  compiler only resolves parameter references; arithmetic
  expressions like `"-plate_length/2 + hole_edge_offset"` are
  rejected at the validator's `unused_parameter` check.  Pre-
  compute the position and store it as a parameter.

These limits are deliberately tight so that the compiler remains a
single readable function.  They will be relaxed in later versions;
for now, anything outside the list above is a schema violation.

## Overview

This document is the contract between an upstream text planner and the
build123d compiler.  It is intentionally narrow: only the subset of
features that the compiler can deterministically translate is
accepted.  Anything else is rejected at `validate_ir.py` so the
compiler never sees an ambiguous input.


## Top-level fields

| Field         | Type    | Required | Description |
|---------------|---------|----------|-------------|
| `schema`      | string  | yes      | Must be `cad_ir.v0`. |
| `units`       | string  | yes      | One of `mm`, `cm`, `in`. |
| `document`    | object  | yes      | `{type: "part", name: "..."}`. Only `part` in v0. |
| `coordinate_system` | object | yes | `{origin, up_axis, front_axis}`. v0 accepts `up_axis: "Z"`, `front_axis: "Y"` or `"X"`. |
| `parameters`  | object  | yes      | Map of `name -> number`. Names used in features must resolve here. |
| `features`    | array   | yes      | Ordered list of feature objects. The order is the construction order. |
| `acceptance`  | object  | no       | Verifier hints: `bbox`, `must_have`, `tolerance_mm`. |

## Feature types (v0 whitelist)

| `type`            | Sketch required | Notes |
|-------------------|-----------------|-------|
| `extrude_add`     | yes             | Add a solid by extruding a sketch along a direction. |
| `extrude_cut`     | yes             | Subtract a solid by extruding a sketch through the target. |
| `hole_through`    | no              | Through-hole along an axis. `target` must be a prior `extrude_add` id. |
| `fillet`          | no              | Edge fillet. `selector` chooses edges. |
| `chamfer`         | no              | Edge chamfer. Same selector rules as `fillet`. |

Anything else is rejected.

## Sketch entities (v0 whitelist)

| `type`              | Required fields |
|---------------------|-----------------|
| `center_rectangle`  | `center`, `size` (2-element list of parameter names or numbers). |
| `polygon`           | `center`, `radius`, `sides`. |
| `circle`            | `center`, `diameter`. |
| `circle_pattern`    | `centers` (list of [x, y] pairs). |

## Selector (for `fillet` / `chamfer`)

v0 supports:

- `top_outer_edges` -- all outer edges on the top face of the target.
- `bottom_outer_edges` -- analogous.
- `all_edges` -- all edges of the target.

Any other selector is rejected.

## Acceptance block

```json
{
  "bbox": [100, 60, 10],
  "must_have": ["single_solid", "four_through_holes"],
  "tolerance_mm": 0.05
}
```

`must_have` v0 vocabulary:

- `single_solid` -- the result must be a single closed solid.
- `n_through_holes` -- `n` may be a literal int; the validator emits a
  concrete check for the number of through-holes.

`tolerance_mm` is honored by the inspect step (post-generation). The
CAD-IR validator does not enforce it.

## Error model

`validate_ir.py` returns a non-zero exit and a JSON document on stdout
shaped like:

```json
{
  "ok": false,
  "errors": [
    {"path": "$.features[2].diameter", "code": "missing_field", "message": "..."},
    {"path": "$.features[5].target",  "code": "unknown_ref",   "message": "..."}
  ]
}
```

The compiler refuses to run when `ok: false`.

## Changelog

### v1 (2026-06)

Compiler surface area:

- **New sketch entities**: `polygon`, `circle`, `circle_pattern` (the
  schema already accepted them in v0; the compiler now emits them).
- **New feature**: `extrude_cut` (subtractive solid from a sketch).
- **Selector translation for `fillet` / `chamfer`**:
  - `all_edges` -- direct passthrough to `body.fillet(r)` /
    `body.chamfer(r)`.
  - `top_outer_edges` / `bottom_outer_edges` -- filtered on the
    body's bounding-box Z-extremum.  Verified on prismatic parts
    (the `plate_with_fillet` example); not yet verified on sloped
    or compound targets.
  - Any other selector kind is rejected.
- **`hole_through.axis`**: must be `"Z"`.  `"X"` and `"Y"` are
  explicitly rejected (v0 had no such guard and silently emitted
  broken code in those cases).

Example IRs in `examples/`:

- `mounting_plate.ir.json` -- v0 case (4 corner through-holes on a
  rectangular base).  Still passes validation and end-to-end.
- `plate_with_fillet.ir.json` -- v1 case (60 x 40 x 8 plate with a
  R2 fillet on the top outer edges).  End-to-end verified.

Known limits deferred to v2:

- `extrude_add.direction` is accepted by the validator but ignored
  by the compiler.
- A second `extrude_add` cannot be added to a v1 IR; the compiler
  only consumes the first.
- Arithmetic expressions in `position` are not resolved;
  pre-compute the position and store it as a parameter.
- `top_outer_edges` / `bottom_outer_edges` only test on Z-axis
  bbox extremes; needs generalisation to sloped/compound targets.
