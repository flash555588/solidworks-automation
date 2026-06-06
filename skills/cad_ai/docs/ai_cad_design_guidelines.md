# AI-CAD Design Guidelines

**Project**: `solidworks-automation` (the `streetartist` repo)
**Module**: `skills/cad_ai/scripts/cad_ai/`
**Status**: v0/v1 production code, 366 tests passing, end-to-end verified
on real `SOLIDWORKS 2025` (`SLDWORKS.exe` rev 33.5.0).

---

## 1. Objective

Provide a reliable **AI → SOLIDWORKS** workflow that turns a structured
**CAD Intermediate Representation (CAD-IR)** into a real `SLDPRT` file
on disk. The pipeline is the only publicly available Python path that
goes from machine-readable geometry to an in-process COM-driven
SOLIDWORKS build without a GUI scripting step.

The current version handles the v0/v1 feature whitelist end-to-end:

* `extrude_add` (single body or stacked bodies)
* `extrude_cut` (blind + through)
* `hole_through`
* `fillet` / `chamfer`
* `sketch_circle`, `sketch_rectangle`, `sketch_polygon`,
  `sketch_circle_pattern`

Bicycle-class parts (wheels, frame tubes, handlebar, saddle, chainring)
build successfully on a real SOLIDWORKS host; the test suite proves
this for `hex_spacer`, `desk_lamp`, `bicycle`, and four other
fixtures.

---

## 2. Architecture

```
                      ┌─────────────────────┐
   text / DXF / AI ──▶│ CAD-IR (v0 JSON)    │  ←  schema/validate
                      └──────────┬──────────┘
                                 │
                                 ▼
                      ┌─────────────────────┐
                      │  Projection check   │  ←  projection_validator
                      └──────────┬──────────┘
                                 │
                                 ▼
                      ┌─────────────────────┐
                      │  Feature planner    │  ←  planner
                      └──────────┬──────────┘
                                 │
                                 ▼
                      ┌─────────────────────┐
                      │  SW ops compiler    │  ←  sw_compile
                      │  (resolve refs,     │
                      │   mm → m)           │
                      └──────────┬──────────┘
                                 │
                                 ▼
                      ┌─────────────────────┐
                      │  SW host (real)     │  ←  cad_ir_to_sw
                      │  SLDWORKS COM       │
                      └─────────────────────┘
                                 │
                                 ▼
                         bicycle.SLDPRT
```

### 2.1 The four files that matter most

| File | Role | Lines (current) |
|---|---|---|
| `ir_schema.py` | Single source of truth for v0 JSON shape | ~125 |
| `ir_validate.py` | Schema-level structural checks | ~280 |
| `projection_validator.py` | Semantic checks (refs, dimensions) | ~110 |
| `sw_compile.py` | CAD-IR → SW instruction stream | ~250 |

`solidworks_com/compiler/cad_ir_to_sw.py` is the **SW host**, not the
schema compiler.

---

## 3. CAD-IR contract (v0)

### 3.1 Top-level shape

```json
{
  "schema": "cad_ir.v0",
  "units": "mm" | "cm" | "in",
  "document": {"type": "part", "name": "..."},
  "coordinate_system": {
    "origin": "part_center",
    "up_axis": "X" | "Y" | "Z",
    "front_axis": "X" | "Y" | "Z"
  },
  "parameters": {"<name>": <number-or-string-ref>},
  "features": [...],
  "acceptance": {"bbox": [x, y, z], "tolerance_mm": n}
}
```

`units` are user-facing; the SW compiler converts to metres (the
unit swa accepts) so a fixture in mm produces a 5 mm extrusion, not
a 5 m one.

### 3.2 Feature types

| Type | Required fields |
|---|---|
| `extrude_add` | `sketch`, `depth`, `direction` |
| `extrude_cut` | `sketch`, `depth`, `direction`, `target` |
| `hole_through` | `diameter`, `axis`, `target`, `position` |
| `fillet` | `radius`, `selector`, `target` |
| `chamfer` | `size`, `selector`, `target` |

`target` is the id of the body feature the cut/finish is applied to.

### 3.3 Sketch entities

* `center_rectangle` — `center`, `size`
* `circle` — `center`, `diameter`
* `polygon` — `center`, `radius`, `sides`
* `circle_pattern` — `centers`, `diameter`

### 3.4 Validation

Two layers, both required before compilation:

* **Schema validation** (`ir_validate.validate_ir`) — every
  required field is present, types match, all `parameters` are
  actually referenced (no orphans).
* **Projection validation** (`projection_validator.validate_projection`) —
  every numeric dimension on a feature is positive; every `target`
  / `references` resolves to a known feature id; `acceptance.bbox`
  is internally consistent.

The combined `solidworks_compiler.validate()` runs both and
returns a single error list; downstream tools can render it as a
`{path, code, message}` table.

---

## 4. Compilation pipeline

End-to-end on real SOLIDWORKS 2025: 15.3 s, 650×334×345 mm.  The
``acceptance.bbox`` declared in the IR is the *target envelope*,
not the produced bbox — when multiple bodies merge, the final
bbox is the union of all body extents and is therefore larger
than any single declared envelope.  The acceptance check
compares against the union, not the smallest declared bbox.

### 4.1 sw_compile

`swa` (the COM wrapper) accepts SI units (metres). The IR lives in
the user-facing unit. The compiler therefore:
2. For each numeric `depth` / `diameter` / `radius` / `size` /
   `center` coordinates, multiplies by `to_metres`.
3. Substitutes parameter references in-place (so the stream
   never carries unresolved parameter names).
4. Emits a deterministic op sequence, one feature at a time:
```
new_part
  ├─ extrude_add   (select_plane, sketch_*, extrude)
  ├─ extrude_cut   (select_face, sketch_*, extrude_cut)
  ├─ hole_through  (select_face, sketch_circle, extrude_cut)
  ├─ fillet / chamfer
  └─ ...
```

### 4.2 The planner

`planner.plan_feature_sequence` re-orders a `CADIR`'s features so
downstream compilers receive them in build-safe order:

1. `extrude_add` / `loft_base`
2. `extrude_cut` / `hole_through`
3. `fillet` / `chamfer`
4. `pattern`

The original ordering **inside a bucket** is preserved (stable
ordering); the planner never invents new features, only shuffles
existing ones.

### 4.3 The SW host

`solidworks_com/compiler/cad_ir_to_sw.py::CadIrToSw` walks the
emitted op stream and dispatches to the SW API:

```
extrude        →  features.extrude_blind(depth, merge, reverse)
extrude_cut   →  features.cut_blind(depth, reverse, normal_cut)
fillet        →  features.fillet_selected(radius)
chamfer       →  features.chamfer_selected(distance, chamfer_type)
```

`reverse` is derived from the IR `direction` (`+Z` ⇒ `False`,
`-Z` ⇒ `True`). The actual extrusion axis is determined by the
SW plane normal: `Top Plane` (XY) ⇒ +Z, `Front Plane` (XZ) ⇒ +Y,
`Right Plane` (YZ) ⇒ +X. **The IR's `direction` field is a
hint, not a true vector** — the planner's `+X` / `+Y` / `+Z`
labels match the swa plane selection.

---

## 5. Primitives (the bicycle)

`primitives.bicycle_skeleton()` returns a fully populated `CADIR`
for a parameterised bicycle:

* two wheels (`front_wheel_outer` + `front_wheel_inner` cut,
  `rear_wheel_outer` + `rear_wheel_inner` cut)
* frame tubes (`down_tube`, `seat_tube`, `chainstay`, `seatstay`,
  `head_tube`, `stem`)
* handlebar, saddle, chainring (flat discs)

Each tube uses an **explicit `depth` parameter** — the compiler
never has to evaluate arithmetic in the IR. This keeps the
bicycle IR honest against the v0 schema.

```
bicycle_skeleton()  →  CADIR(name="bicycle", 17 parameters, 13 features)
  .to_dict()        →  validated v0 JSON
  sw_compile       →  66 ops
  cad_ir_to_sw     →  SLDPRT
```

End-to-end on real SOLIDWORKS 2025: 15.3 s, 650×334×345 mm.

---

## 6. Critical v0 design decisions

### 6.1 Why mm at the IR, m at the API

The IR is meant to be **human-readable**. A designer writing a
fixture in mm expects `5` to mean 5 mm, not 5 m. The compiler owns
the conversion, **not** the IR or the API. This decision was made
after a first end-to-end test produced a 5000 mm part because
the value `5.0` was passed straight through.

### 6.2 Why `target` on subtractive features

`extrude_cut` and `hole_through` carry a `target` field that names
the body feature they cut from. **In the current v0 sw host this
target is *advisory***: the SW side applies cuts to the active
body, which is the most recent `extrude_add`. A v0.2 host will
walk `part.bodies()` and select the body whose name matches
`target` before issuing `cut_blind`. The `target` field is part
of the IR contract from day one so v0.2 callers don't have to
rewrite their fixtures.

### 6.3 Why the planner is a pure re-order

`planner.plan_feature_sequence` does not invent or modify
features. It only assigns a deterministic order to the ones the
caller provided. The reason: a planner that "fixes" the caller's
order is a planner that hides bugs. When a fixture misbehaves
the user can compare the planner's output against the IR to see
exactly what changed.

### 6.4 Why projection validation is separate from schema
validation

Schema validation is cheap and runs first: it walks the IR and
finds missing fields, wrong types, and dangling parameter
references. Projection validation is semantic: it answers
"are these numbers physically plausible?". The two layers can be
run independently and a future LLM-retry loop can branch on the
error code (`type_mismatch` vs `non_positive` vs `unknown_reference`)
to decide which prompt to use next.

---

## 7. Best practices for fixture authors

1. **Always carry a units field.** `mm` is the default, but be
   explicit. The compiler checks this; a missing `units` field
   falls back to mm and silently keeps going.

2. **Use parameter references for any value that might change.**
   Even the smallest dimension — a fillet radius, a saddle
   thickness — should be a parameter, not a literal. This is
   what makes the IR editable without recompiling.

3. **Reference real feature ids in `target`.** The compiler
   doesn't enforce uniqueness in v0, but a v0.2 host will. Use
   semantic ids (`front_wheel_outer`, not `feature_07`).

4. **Run the validators before the compiler.** Both
   `ir_validate.validate_ir` and
   `projection_validator.validate_projection` return
   `{ok, errors}` and never raise. Wrap them in a CI step.

5. **End-to-end tests need a real SW host.** Mock-based tests
   are necessary but not sufficient. The `test_cad_ir_to_sw_e2e`
   module is `pytest.mark.solidworks` and only runs when
   `win32com` is available.

6. **Use the primitives for repeated parts.** The bicycle
   skeleton, the hex spacer, the lamp body — all of them have
   primitive factories in `primitives.py`. The factories accept
   keyword arguments so the user can override any dimension
   without editing the factory.

---

## 8. Roadmap (v0.2)

| Gap | Impact | Plan |
|---|---|---|
| Edge selection for fillet/chamfer | Fillet/chamfer on the real body works for hand-selected edges; body-feature selection is the v0 fallback | Walk `Body.GetEdges`, `SelectByID2("EDGE", ...)` each |
| `extrude_cut.target` resolution | Cuts apply to the active body, not the targeted body | Add a `select_body(target_id)` step before `cut_blind` |
| Sweep (loft) | Non-axis-aligned bicycle tubes are silently skipped | Add `create_tube_between_points(...)` swa adapter and a `sweep` IR type |
| Boolean assembly | Bicycle parts (wheels + frame) need to be **one body** | Multi-body part support + a `join_bodies` op |
| Real projection geometry | "Front / top / side" views for review reports | Reuse `solidworks_com.analysis.validate_model` and surface per-projection metrics |

The v0 design leaves room for all of these without breaking the
v0 IR contract. The contract is the spine; the implementation is
the muscle.

---

## 10. Roadmap (v0.4) -- Core modelling enhancement

| Feature | SW API | IR type | Status |
|---|---|---|---|
| Revolve |  |  | FeatureTools ready |
| Loft boss / cut |  /  |  | FeatureTools ready |
| Mirror |  |  | Needs FeatureTools wrapper |
| Linear pattern |  |  | Needs FeatureTools wrapper |
| Shell |  |  | Needs FeatureTools wrapper |
| Draft |  |  | Needs FeatureTools wrapper |
| Circular pattern |  |  | FeatureTools ready |
| Thicken |  |  | FeatureTools ready |
| Fill surface |  |  | FeatureTools ready |
| Knit surface |  |  | FeatureTools ready |

The v0.4 goal is **100% coverage of SOLIDWORKS core part-modelling
operations** (everything in the Part Design toolbar). After v0.4,
the remaining gaps are surfacing sweep (perpendicular-plane
creation), assemblies (mates), and drawings (views + annotations).

---

## 11. Roadmap (v0.5-v0.9) -- Surface, Assembly, Drawing, Equation, Config

| Feature | SW API | IR type | Status |
|---|---|---|---|
| Loft surface | InsertLoftRefSurface2 | loft_surface | ✅ v0.5 |
| Thicken | FeatureBossThicken | thicken | ✅ v0.5 |
| Fill surface | InsertFillSurface | fill_surface | ✅ v0.5 |
| Knit surface | InsertSewRefSurface | knit | ✅ v0.5 |
| Sweep (SW backend) | InsertProtrusionSweep / InsertCutSweep | sweep | ✅ v0.7 |
| Drawing view | CreateDrawView / InsertModelInPrefPosition | add_view | ✅ v0.7 |
| Drawing dimension | CreateText2 | add_dimension | ✅ v0.7 |
| Equation | EquationManager.Add2 | equation | ✅ v0.8 |
| BOM generation | BOMGenerator | generate_bom | ✅ v0.8 |
| Add configuration | ConfigurationManager.AddConfiguration3 | add_configuration | ✅ v0.9 |
| Set configuration | ShowConfiguration2 | set_configuration | ✅ v0.9 |
| Suppress feature | Feature.SetSuppression2 | suppress_feature | ✅ v0.9 |
| Design table | Extension.InsertDesignTable | design_table | ✅ v0.9 |

---

## 9. Acceptance criteria for new contributions

A new op or IR feature is acceptable when:

1. It round-trips through `ir_validate` and
2. The mock contract tests cover the new op.  Each ``op_*``
   dispatch has at least one positive case and (where the op
   can fail) one negative case.
3. The real-SW end-to-end test exercises the new op against a
   real ``SLDWORKS`` instance with a passing ``assertAlmostEqual``
   on ``part.size()``.
4. The full suite (``pytest`` over ``tests/`` and the
   ``skills/cad_ai/tests/`` tree) passes — 366 / 366 as of
   this writing.

If a new op fails any of these, it does not ship.
