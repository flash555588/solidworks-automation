# CAD-IR v0/v1 -> SOLIDWORKS execution contract

This document is the **interface contract** between `cad_ai` and any
SOLIDWORKS executor.  It is written without a SOLIDWORKS installation
on hand; the intent is that an executor author can implement against
this contract on a Windows + SOLIDWORKS host and then have the rest
of the cad_ai pipeline already work.

## Scope of this contract

`cad_ai` emits a CAD Intent IR (`*.ir.json`).  A SOLIDWORKS executor
takes that IR and produces:

- A SOLIDWORKS part (`.SLDPRT`).
- The same body in STEP form (`.STEP`).
- An `execution_report.json` describing what succeeded, what failed,
  and the IDs the executor used internally.

The contract does not cover assemblies, drawings, sheet metal, or
weldments.  The v0/v1 IR is part-only.

## How the contract is expressed

We do **not** call `SldWorks.exe` directly.  We translate the IR to
a **SW instruction stream**: a JSON document listing the COM calls a
backend must make, in order, with the right arguments.  A
SOLIDWORKS executor (e.g. one based on `pywin32` + the SOLIDWORKS
COM type library) consumes that instruction stream and executes it.

`skills/cad_ai/scripts/cad_ai/sw_compile.py` produces the
instruction stream from a CAD-IR.  A reference implementation of
the executor (called `mock_sw`) lives in
`skills/cad_ai/scripts/cad_ai/mock_sw.py` and uses `build123d` to
re-derive the geometry.  That mock is what we use on hosts without
SOLIDWORKS to verify the contract; the real SOLIDWORKS executor
should produce a `.SLDPRT` that, when re-exported to STEP, matches
the mock output within `tolerance_mm` from `acceptance`.

## IR feature -> SW instruction mapping

| CAD-IR feature | SW instruction(s) | SOLIDWORKS API call(s) (notes) |
|---|---|---|
| `extrude_add` (base) | `NewPart`, `InsertSketch` on `XY` plane, sketch entities, `FeatureExtrusion` (thin, depth) | `ISldWorks::NewDocument`, `IModelDoc2::InsertSketch`, sketch segment APIs (e.g. `IModelDoc2::CreateLine2`, `CreateCircle2`), `IFeatureManager::FeatureExtrusion2` with `swEndCondBlind` and `swExtrudeInwardDirection = false` for `+Z`. |
| `extrude_cut` | `InsertSketch`, sketch entities, `FeatureCut` | Same sketch APIs as above; `IFeatureManager::FeatureCut4` with `swEndCondBlind`. |
| `hole_through` (axis=`Z`) | `InsertSketch` on the top face, `Circle`, `FeatureCut` through the body | Sketch plane selection must target the body's top face.  In practice, this is `IModelDoc2::SelectByID` + a face selection. |
| `fillet` | `FeatureFillet3` with selected edges | Edge selection uses `IModelDoc2::SelectByID` on the bounding-box-Z extremum edges.  The mock backend uses `body.edges() | body.fillet(r)`. |
| `chamfer` | `FeatureChamfer` with selected edges | Same selection strategy as fillet. |

## Instruction stream shape

Every IR produces exactly one `Part` document.  The instruction
stream is a JSON document of this shape:

```json
{
  "schema": "sw_instructions.v0",
  "document": "part",
  "operations": [
    {"op": "new_part", "name": "mounting_plate"},
    {"op": "select_plane", "plane": "XY"},
    {"op": "sketch_begin"},
    {"op": "sketch_rectangle", "center": [0, 0], "size": [60.0, 40.0]},
    {"op": "sketch_end"},
    {"op": "extrude", "depth": 8.0, "direction": "+Z"},
    {"op": "select_face", "selector": {"kind": "top_face"}},
    {"op": "sketch_begin"},
    {"op": "sketch_circle", "center": [-30.0, -20.0], "diameter": 6.0},
    {"op": "sketch_end"},
    {"op": "extrude_cut", "depth": "through"},
    {"op": "fillet", "radius": 2.0, "selector": {"kind": "top_outer_edges"}}
  ]
}
```

Operation set (v0):

- `new_part` (with `name`)
- `select_plane` (with `plane` in `XY / XZ / YZ`)
- `select_face` (with `selector.kind`)
- `sketch_begin`, `sketch_end`
- `sketch_rectangle` (with `center`, `size`)
- `sketch_circle` (with `center`, `diameter`)
- `sketch_polygon` (with `center`, `radius`, `sides`)
- `sketch_circle_pattern` (with `centers`, `diameter`)
- `extrude` (with `depth`, `direction` in `+Z / -Z`; in v1 only `+Z`
  is emitted; `direction` is also emitted in the instruction stream
  for forward compatibility)
- `extrude_cut` (with `depth` or `"through"`)
- `fillet` (with `radius`, `selector.kind`)
- `chamfer` (with `size`, `selector.kind`)

Anything outside this set is rejected at `sw_compile.compile_sw`
time.  The mock backend honours the same set.

## Backward compatibility policy

- The instruction stream has a `schema` field.  Bumping it
  (e.g. `sw_instructions.v1`) is a breaking change.
- Adding new operations to a given schema version is allowed.
  Removing or re-purposing an existing operation requires a new
  schema version.
- The mock backend must remain in lock-step with the production
  SOLIDWORKS backend; contract tests run both backends against the
  same IR fixture and assert equivalent STEP output.

## Authoring a real SOLIDWORKS backend

1. Install SOLIDWORKS (2022 SP4 or later recommended; older
   versions may lack `IFeatureManager::FeatureCut4`).
2. `pip install pywin32` and either bind to `SLDWORKS.tlb` via
   `makepy` or use the `comtypes` typed wrapper.
3. Implement an executor that consumes the instruction stream
   shape above and produces a `.SLDPRT` and a `.STEP`.
4. Run the contract tests (see `tests/test_sw_compile.py`):
   `cd skills/cad_ai/tests && python -m unittest test_sw_compile`.
5. Compare the real backend's STEP with the mock backend's STEP
   using `scripts/inspect` and the IR's `acceptance.bbox` plus
   `tolerance_mm`.

## Out of scope for v0/v1

- `extrude_add.direction` is honoured in the instruction stream but
  the v0 SOLIDWORKS backend only supports `+Z`.  This matches the
  cad_ai v0 compiler.
- No support for `loft`, `sweep`, `revolve`, `shell`, or any free-
  form feature.  The IR schema rejects them.
- No support for derived configurations, configurations, or
  display states.
