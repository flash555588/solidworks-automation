"""Build a flashlight with full internal structure in SOLIDWORKS.

External shape
--------------
  Tail cap    : Ø26 mm x 15 mm
  Grip body   : Ø25 mm x 92 mm  (knurled)
  Head/bezel  : Ø38 mm x 33 mm
  Total length: 140 mm

Internal structure
------------------
  Battery bore     : Ø21 mm x 107 mm from tail (fits 18650)
  Tail spring seat : Ø14 mm x 4 mm counterbore  (negative contact)
  Tail switch hole : Ø8  mm through tail cap centre
  Reflector cavity : Ø10->Ø33 mm tapered cone, 22 mm deep from head front
  LED board seat   : Ø10 mm x 3 mm flat pocket
  Lens seat        : Ø28->Ø34 mm x 3 mm step at head front

Detail features
---------------
  Grip knurling : 4 circumferential V-grooves on body

Run with SOLIDWORKS open::

    py examples/model_flashlight.py
    py examples/model_flashlight.py --output-dir C:\\temp\\flashlight
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from solidworks_com import SolidWorks, mm

# ---------------------------------------------------------------------------
# Axial positions (Y = 0 at tail face, increases toward head front)
# ---------------------------------------------------------------------------
Y0               = mm(0.0)      # tail face
Y_TAIL_END       = mm(15.0)     # tail/body shoulder start
Y_TAPER_END      = mm(17.0)     # tail/body shoulder end
Y_GRIP_END       = mm(109.0)    # body/head shoulder start
Y_HEAD_SHOULDER  = mm(112.0)    # body/head shoulder end
Y_HEAD_END       = mm(140.0)    # head front face (total length)

# Outer radii
R_TAIL  = mm(13.0)   # Ø26
R_BODY  = mm(12.5)   # Ø25
R_HEAD  = mm(19.0)   # Ø38

# Internal
R_BORE       = mm(10.5)   # battery bore  Ø21
BORE_DEPTH   = mm(107.0)

R_SPRING     = mm(7.0)    # spring seat   Ø14
SPRING_DEPTH = mm(4.0)

R_SWITCH     = mm(4.0)    # switch hole   Ø8
SWITCH_DEPTH = mm(16.0)

REFL_DEPTH   = mm(22.0)
R_REFL_FRONT = mm(16.5)   # Ø33  at head front face
R_REFL_BACK  = mm(5.0)    # Ø10  at LED end

R_LED        = mm(5.0)    # LED seat Ø10
LED_DEPTH    = mm(3.0)

R_LENS_INNER = mm(14.0)   # lens seat inner  Ø28
R_LENS_OUTER = mm(17.0)   # lens seat outer  Ø34
LENS_DEPTH   = mm(3.0)

GROOVE_W     = mm(1.2)    # knurl groove width
GROOVE_D     = mm(0.8)    # knurl groove depth
GROOVE_Y     = [mm(30.0), mm(51.0), mm(72.0), mm(93.0)]


# ---------------------------------------------------------------------------
# Core helper – revolve a half-profile 360° around the Y-axis.
#
# KEY RULE: do NOT include a closing line along X=0.  The profile must start
# and end on the centerline (X=0); SOLIDWORKS closes it automatically.
# Including a coincident line on the axis prevents solid creation.
# ---------------------------------------------------------------------------
def _revolve(part, lines, name, *, cut=False):
    part.select_plane("Front Plane")
    with part.sketch() as sk:
        # Revolve axis: vertical centerline at X=0
        sk.centerline(mm(0), Y0 - mm(5), 0,
                      mm(0), Y_HEAD_END + mm(5), 0)
        for x1, y1, x2, y2 in lines:
            sk.line(x1, y1, 0, x2, y2, 0)
    part.features.revolve(cut=cut)
    part.rename_last_feature(name)


# ---------------------------------------------------------------------------
# Feature builders
# ---------------------------------------------------------------------------

def outer_shell(part):
    """External envelope – open profile, starts/ends on axis (X=0)."""
    _revolve(part, [
        # bottom face (tail end):  axis → outer radius
        (mm(0),  Y0,             R_TAIL,  Y0),
        # tail outer wall
        (R_TAIL, Y0,             R_TAIL,  Y_TAIL_END),
        # taper tail→body
        (R_TAIL, Y_TAIL_END,     R_BODY,  Y_TAPER_END),
        # body outer wall
        (R_BODY, Y_TAPER_END,    R_BODY,  Y_GRIP_END),
        # taper body→head
        (R_BODY, Y_GRIP_END,     R_HEAD,  Y_HEAD_SHOULDER),
        # head outer wall
        (R_HEAD, Y_HEAD_SHOULDER, R_HEAD, Y_HEAD_END),
        # head front face:  outer radius → axis
        (R_HEAD, Y_HEAD_END,     mm(0),   Y_HEAD_END),
        # NOTE: no closing line along axis – SOLIDWORKS closes via centerline
    ], "Outer shell")


def battery_bore(part):
    """Main cylindrical bore from tail inward (Ø21 x 107 mm)."""
    y_end = Y0 + BORE_DEPTH
    _revolve(part, [
        (mm(0),  Y0,    R_BORE, Y0),
        (R_BORE, Y0,    R_BORE, y_end),
        (R_BORE, y_end, mm(0),  y_end),
    ], "Battery bore", cut=True)


def spring_seat(part):
    """Wider counterbore at tail for the negative spring (Ø14 x 4 mm)."""
    y_end = Y0 + SPRING_DEPTH
    _revolve(part, [
        (mm(0),    Y0,    R_SPRING, Y0),
        (R_SPRING, Y0,    R_SPRING, y_end),
        (R_SPRING, y_end, mm(0),    y_end),
    ], "Spring seat", cut=True)


def switch_hole(part):
    """Central through-hole for power button boot (Ø8 x 16 mm)."""
    y_end = Y0 + SWITCH_DEPTH
    _revolve(part, [
        (mm(0),    Y0,    R_SWITCH, Y0),
        (R_SWITCH, Y0,    R_SWITCH, y_end),
        (R_SWITCH, y_end, mm(0),    y_end),
    ], "Tail switch hole", cut=True)


def reflector_cavity(part):
    """Tapered reflector cone from head front face inward."""
    y_front = Y_HEAD_END
    y_back  = Y_HEAD_END - REFL_DEPTH
    _revolve(part, [
        (mm(0),        y_back,  R_REFL_BACK,  y_back),
        (R_REFL_BACK,  y_back,  R_REFL_FRONT, y_front),
        (R_REFL_FRONT, y_front, mm(0),         y_front),
    ], "Reflector cavity", cut=True)


def led_seat(part):
    """Flat pocket behind reflector for LED board (Ø10 x 3 mm)."""
    y_front = Y_HEAD_END - REFL_DEPTH
    y_back  = y_front - LED_DEPTH
    _revolve(part, [
        (mm(0),  y_back,  R_LED, y_back),
        (R_LED,  y_back,  R_LED, y_front),
        (R_LED,  y_front, mm(0), y_front),
    ], "LED board seat", cut=True)


def lens_seat(part):
    """Ring step at head front for glass lens and O-ring (Ø28-Ø34 x 3 mm)."""
    y_front = Y_HEAD_END
    y_back  = Y_HEAD_END - LENS_DEPTH
    # Ring profile: from inner radius to outer radius, open at both ends (ring)
    _revolve(part, [
        (R_LENS_INNER, y_back,  R_LENS_OUTER, y_back),
        (R_LENS_OUTER, y_back,  R_LENS_OUTER, y_front),
        (R_LENS_OUTER, y_front, R_LENS_INNER, y_front),
        (R_LENS_INNER, y_front, R_LENS_INNER, y_back),
    ], "Lens seat", cut=True)


def knurling(part):
    """Four circumferential V-grooves on the grip body."""
    hw = GROOVE_W / 2.0
    d  = GROOVE_D
    for idx, yc in enumerate(GROOVE_Y):
        # Isoceles-triangle cross-section: tip at (R_BODY-d, yc),
        # base corners at (R_BODY, yc-hw) and (R_BODY, yc+hw)
        _revolve(part, [
            (R_BODY - d, yc,      R_BODY, yc - hw),
            (R_BODY,     yc - hw, R_BODY, yc + hw),
            (R_BODY,     yc + hw, R_BODY - d, yc),
        ], f"Knurl {idx + 1}", cut=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_flashlight(output_dir, *, name="flashlight",
                     export_step=True, visible=True):
    output_dir.mkdir(parents=True, exist_ok=True)
    sw   = SolidWorks.connect(visible=visible)
    part = sw.new_part()

    steps = [
        ("Outer shell",        outer_shell),
        ("Battery bore",       battery_bore),
        ("Spring seat",        spring_seat),
        ("Switch hole",        switch_hole),
        ("Reflector cavity",   reflector_cavity),
        ("LED board seat",     led_seat),
        ("Lens seat",          lens_seat),
        ("Knurling (x4)",      knurling),
    ]
    for idx, (label, fn) in enumerate(steps, 1):
        print(f"  [{idx}/{len(steps)}] {label} ...")
        fn(part)

    part.rebuild()
    errors = part.feature_errors()
    if errors:
        print(f"\nWarning: {len(errors)} feature error(s):")
        for feat, err in errors:
            print(f"  - {part.feature_name(feat)}: {err}")
    else:
        print("\nAll features rebuilt cleanly.")

    sldprt = output_dir / f"{name}.SLDPRT"
    step   = (output_dir / f"{name}.step") if export_step else None
    if export_step:
        sldprt, step = part.save_and_export(sldprt, step)
    else:
        part.save_as(sldprt)
    return sldprt, step


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, default=Path(r"C:\temp\flashlight"))
    p.add_argument("--name",    default="flashlight")
    p.add_argument("--no-step", action="store_true")
    p.add_argument("--hidden",  action="store_true")
    args = p.parse_args()

    print(f"Building flashlight -> {args.output_dir}")
    sldprt, step = build_flashlight(
        args.output_dir,
        name=args.name,
        export_step=not args.no_step,
        visible=not args.hidden,
    )
    print(f"Saved : {sldprt}")
    if step:
        print(f"STEP  : {step}")


if __name__ == "__main__":
    main()
