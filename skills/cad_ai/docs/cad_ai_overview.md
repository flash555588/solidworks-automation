# cad_ai -- onboarding overview

This document is the long-form onboarding guide for the
`skills/cad_ai/` skill.  Read this if you want to understand the
whole picture in one sitting.  The other documents in this skill
(`SKILL.md`, the entries under `references/`, `contracts/`) are
the per-feature specifications; this one is the narrative.

## What cad_ai is for

`cad_ai` is the AI-planning layer of the repository.  It does not
own geometry execution -- that belongs to the `skills/cad`
pipeline (build123d + cadpy + `scripts/step`).  It owns:

- **CAD Intent IR (CAD-IR)** -- a versioned, schema-validated
  envelope that says "make a 100 x 60 x 10 mm plate with four
  6 mm corner holes" in a form that the rest of the pipeline
  can deterministically translate.
- **The validators and compilers** that turn an IR into a
  build123d Python source.
- **Three input adapters** so the IR can come from three
  different places.
- **One output adapter** (mock) so the SOLIDWORKS layer can be
  validated without a SOLIDWORKS install.

The big idea, lifted from the broader text-to-CAD literature
(see `references/architecture.md` for the survey), is to keep
the AI in the *planning* lane, never in the *execution* lane.
The LLM proposes; the validator decides; the build123d/OCC
kernel proves; the SOLIDWORKS executor finalises.

## What cad_ai is NOT for

It is not a text-to-mesh pipeline, not a stable-diffusion-for-CAD
toy, and not a one-shot answer to "make this picture into a 3D
part."  It is the *contract layer* above the existing
`skills/cad/` execution pipeline.  Without a valid IR, no output
is produced.

The repository does not ship a SOLIDWORKS wrapper, so the
SOLIDWORKS story is contract-only.  See
`contracts/cad_ir_to_sw_contract.md` for the interface.

## Pipeline at a glance

```
                  +--------------------+
text prompt  ---->| cad_ai.llm         |--- cad_ir.v0 doc
                  |  .text_to_ir       |    (validated)
                  +--------------------+              |
                                                     v
DXF 3 views ----->| cad_ai.dxf_to_ir   |--- cad_ir.v0 doc
                  |  .read_three_views |    (validated)
                  +--------------------+              |
                                                     v
hand-written  ---->  (already an IR)    --- cad_ir.v0 doc
                                                     |
                                                     v
                                  +------------------+------------------+
                                  |                  |                  |
                                  v                  v                  v
                          ir_compile.py    sw_compile.py         validate_ir.py
                                  |                  |                  |
                                  v                  v                  v
                         build123d source  sw_instructions.json    {ok, errors}
                                  |
                                  v
                          skills/cad/scripts/step
                                  |
                                  v
                                 .step
```

The **only** output that ends up in the build123d + cadpy world
is the .step file.  Everything else (the IR, the SW instruction
stream, the validator's `ok`/`errors` list) is text and lives in
this skill.

## Subsystems

The skill is split into four loosely-coupled subsystems.  Each
subsystem is independently testable; the only thing that ties
them together is the IR.

### A. The IR schema and validator

Files:

- `scripts/cad_ai/ir_schema.py` -- schema constants (whitelist of
  feature types, sketch entity types, selector kinds).
- `scripts/cad_ai/ir_validate.py` -- the validator itself.  Walks
  a JSON dict and returns `{ok: bool, errors: [{path, code, message}]}`.
- `references/cad_intent_schema.md` -- the prose contract for
  every field, with v1 limitations called out explicitly.

The validator is **strict** but not **picky**: it catches
schema violations, missing fields, unknown feature types, and
forward references that have no prior feature.  It also runs
an "unused parameter" check so that the IR is self-consistent.
A full description of the contract is in
`references/cad_intent_schema.md`.

The validator is also the contract surface for the LLM
adapter: every retry carries the validator's `errors` list back
into the prompt, so the model can correct itself.

### B. The build123d compiler

Files:

- `scripts/cad_ai/ir_compile.py` -- emits a build123d Python
  source from a CAD-IR.  The output is fed to
  `skills/cad/scripts/step`.

The compiler is the heart of the v0/v1 cycle.  It supports:

- Sketch entities: `center_rectangle`, `polygon`, `circle`,
  `circle_pattern`.
- Features: `extrude_add` (the base), `hole_through` (along Z),
  `extrude_cut`, `fillet`, `chamfer`.
- Selectors for fillet/chamfer: `all_edges`,
  `top_outer_edges`, `bottom_outer_edges`.  Anything else is
  rejected.

It is **deliberately narrow**.  Things it does not yet support
(loft, sweep, revolve, shell, freeform surfaces, multi-extrude
bases, etc.) are out of scope for v1.  See
`references/cad_intent_schema.md` -> "v1 limitations" for the
full list.

### C. The LLM adapter

Files:

- `scripts/cad_ai/llm/client.py` -- a stdlib-only OpenAI-compatible
  HTTP client.
- `scripts/cad_ai/llm/errors.py` -- `LLMError` and friends.
- `scripts/cad_ai/llm/text_to_ir.py` -- the retry loop: send
  the prompt, parse the JSON, validate the IR, re-prompt with
  the validator's error list if needed, give up after
  `max_retries` (default 2).
- `scripts/cad_ai/text_to_ir.py` -- the network-free stub that
  the rest of the skill depends on by default.
- `references/text_to_ir_prompt.md` -- the prompt template.

The LLM adapter is **opt-in**: the rest of the skill is
network-free, and a caller that wants the LLM-backed variant
imports from `cad_ai.llm` explicitly.

Why an OpenAI-compatible HTTP client instead of a vendor SDK?
The same code path works against OpenAI, ollama, vLLM, Azure
OpenAI (with the right URL), and any proxy that speaks the chat
completions protocol.  We do not import any third-party SDK, so
the runtime dependency surface of this skill is unchanged.

The LLM output is never trusted.  Every IR is validated before
it is handed to the compiler; the compiler refuses non-LF
identifiers and unknown feature types with a clear error.  The
combination of "validator + compiler" is what makes the LLM
adapter safe to run unattended.

### D. The DXF three-view reader

Files:

- `scripts/cad_ai/dxf_to_ir.py` -- reads three DXFs and emits a
  CAD-IR.
- `references/dxf_reader.md` -- the contract (view convention,
  entity whitelist, pairing rules, output format).
- `examples/mounting_plate_three_views/` -- a hand-built DXF
  sample.

The reader is the second of the three input adapters (after the
LLM adapter).  It accepts only `LINE` and `CIRCLE` entities,
assumes third-angle projection, and pairs holes across views
**by index**.  The rectangle outline is read from the front and
top views; the right view's outline is a sanity check.

Why so narrow?  Because the geometric matches across three views
is already a hard problem.  Once it works on a clean DXF
rectangle with 4 holes, the next problems are arc-to-line
approximation, view-convention auto-detection, and unit
detection.  Those are v2.

### E. The SOLIDWORKS instruction stream

Files:

- `scripts/cad_ai/sw_compile.py` -- IR -> versioned SW
  instruction stream (a JSON document).
- `scripts/cad_ai/mock_sw.py` -- a reference SOLIDWORKS backend
  that re-runs the IR through `ir_compile.py` and writes STEP
  via OCP.  This is what we use on hosts without SOLIDWORKS.
- `contracts/cad_ir_to_sw_contract.md` -- the contract.

The SOLIDWORKS executor is **out of tree** for two reasons:
this repository does not contain a `skills/solidworks/`
directory, and the host this is being written on does not have
SOLIDWORKS installed.  The contract document is written so a
SOLIDWORKS author on a different host can implement against it
and have the rest of `cad_ai` already work.

The mock backend is not a toy.  It produces a real STEP file
using OCP, with the same metadata that `scripts/step` produces.
A real SOLIDWORKS backend must produce a STEP that matches the
mock's within `tolerance_mm` from the IR's `acceptance` block.

## How to use each subsystem

The five CLI entry points are listed under "How to use it" in
`SKILL.md`.  The typical flow is:

```
1.  Pick an input source (text / IR / DXF).
2.  Produce a CAD-IR (via the LLM, by hand, or via the DXF reader).
3.  Validate:    python scripts/validate_ir.py ir.json
4.  Compile:     python scripts/compile_ir.py ir.json -o gen.py
5.  Execute:     python ../cad/scripts/step gen.py
6.  Verify:      python ../cad/scripts/inspect refs --facts *.step
```

Steps 3-6 are the same regardless of the input source.  Step 2
varies.

## How the tests are organised

`tests/` is a flat directory.  Each file is a `unittest` module
that can be run standalone or via `unittest discover`.  The tests
are stdlib-only; the LLM and DXF tests use `unittest.mock` to
fake the network and the filesystem respectively.

The current tally is 16 tests:

- 5 in `test_ir_validate.py` (3 contract + 2 example-on-disk).
- 6 in `test_llm_text_to_ir.py` (3 JSON extraction + 3 retry loop).
- 5 in `test_dxf_to_ir.py` (1 happy path + 4 reject paths).

Adding a new test file is the same as adding a new feature:
write the feature, write a test, run `unittest discover` and
expect one more green dot.

## What is *not* in this skill

- A real SOLIDWORKS executor.  Out of tree.
- A raster / VLM drawing reader.  v2.
- A freeform surface / NURBS pipeline.  v2+.
- A assembly / drawing / sheet-metal / weldment pipeline.  v3+.
- An evaluation harness.  We are a planning layer, not an
  evaluator.  `wgpatrick/cadeval` would be the right place to
  add this.

## Where to go from here

If you want to extend the skill, here is the cheapest path that
adds real value:

1. **Run an LLM through the adapter and save the IR it
   produces.** Add one example IR to `examples/`.  This
   exercises the retry loop end to end.
2. **Add an `ARC` reader to the DXF path.** This is the most
   common DXF entity that v1 rejects.  Map it to a polyline
   approximation; the IR validator already accepts
   `circle_pattern` for the simpler case.
3. **Implement a SOLIDWORKS backend on a host that has
   SOLIDWORKS.** Follow `contracts/cad_ir_to_sw_contract.md`,
   bind to `SLDWORKS.tlb` via `comtypes` or `pywin32`, and run
   the contract tests.

If you want to verify the skill, run:

```
python -m unittest discover -s skills/cad_ai/tests -v
```

and read the per-test `msg=` strings when something fails.
