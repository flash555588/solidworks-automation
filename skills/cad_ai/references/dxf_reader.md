# DXF three-view reader (v1)

`scripts/cad_ai/dxf_to_ir.py` translates three DXF views into a
CAD-IR v1 document.  This document is the contract.

## View convention

Third-angle projection (ISO).  This is not auto-detected; the reader
assumes it.  The three views are:

- `front.dxf` -- the front view, in the world XZ plane (looking in
  the -Y direction).
- `top.dxf` -- the top view, in the world XY plane (looking in the
  -Z direction).
- `right.dxf` -- the right view, in the world YZ plane (looking in
  the -X direction).

Each view is a 2D sketch in the corresponding plane.  Coordinates
inside a view are interpreted in view-local 2D; the reader maps:

- front view (x, y) -> (world x, world z)
- top view (x, y) -> (world x, world y)
- right view (x, y) -> (world y, world z)

## Entity whitelist

The v1 reader accepts only:

- `LINE` -- for the body outline.
- `CIRCLE` -- for through-holes.

Any other entity type (ARC, LWPOLYLINE, SPLINE, HATCH, DIMENSION,
MTEXT, etc.) raises `DXFReaderError` with a clear message.

## Body outline

The first view's outer outline is taken to be the base body
rectangle.  The reader expects **exactly four** LINE entities
forming a closed rectangle.  The X bound is the union of the front
and top rectangles; the Y bound comes from the top rectangle; the
Z bound comes from the front rectangle.  The right view's
rectangle must agree with the Y and Z bounds of the others, but
its outline is otherwise redundant.

If the views disagree on any bound, the reader raises
`DXFReaderError` (this is a sanity check against mis-drawn
drawings).

## Through-holes

The reader treats every CIRCLE entity in each view as a
through-hole.  Holes are paired **by index**: the first CIRCLE in
front pairs with the first CIRCLE in top and the first CIRCLE in
right, and so on.  If the counts disagree, the reader raises
`DXFReaderError`.

The 3D centre of a hole is recovered by taking the X from the
front (and top) view, the Y from the top (and right) view, and
the Z from the front (and right) view.  Each pair of views must
agree on the shared axis within `1e-6`.  The radius must also
match across all three views.

## Output

The reader emits a CAD-IR v1 document with:

- One `extrude_add` feature for the base body.
- One `hole_through` feature per detected hole, each referencing
  the base by id and lying on the Z axis.
- An `acceptance` block whose `bbox` is the base body dimensions
  and whose `must_have` includes `single_solid` and
  `N_through_holes` for the detected count.

The IR is fed to the existing `compile_ir.py` + `scripts/step`
pipeline.  No special post-processing is required.

## What the v1 reader does NOT do

- Layer / colour / linetype / block / xref parsing.
- ARC, LWPOLYLINE, SPLINE, HATCH, DIMENSION, MTEXT, TEXT, INSERT
  -- all rejected.
- View-convention auto-detection (first vs third angle).
- Unit detection from `$INSUNITS`.
- Non-rectangular outlines (the body must be a rectangle; the
  reader has no concept of chamfers, fillets, or rounded corners
  in the outline).
- Holes that are not through (the reader always emits
  `hole_through`; counterbore / countersunk / blind holes are
  out of scope for v1).

These are all on the v2 roadmap.  See `SKILL.md` -> "Future work".
