---
name: cad-ai
description: AI-planning layer that turns a free-form text prompt, a structured CAD Intent JSON, or three DXF views into a build123d Python generator. It does not own geometry execution. It owns intent representation, validation, and prompt scaffolding for an upstream LLM. The execution backend is the existing `skills/cad` pipeline (build123d + cadpy + `scripts/step`). A SOLIDWORKS instruction-stream contract is shipped but the SOLIDWORKS executor itself is out of tree.
---

# cad_ai

## What this skill does

Converts a **user-provided CAD intent** into a **deterministic Python generator** that the existing `cad` skill can execute.

Three input shapes are supported:

1. **Plain text** (natural-language description of the part). The skill
   ships a prompt template; the caller fills it and feeds the model's
   output through the validator before it is treated as a generator.  A
   real LLM client is in `cad_ai.llm.text_to_ir` (network-capable,
   OpenAI-compatible HTTP); the stand-alone stub at
   `cad_ai.text_to_ir.text_to_ir` is the network-free default.
2. **CAD Intent JSON** (a versioned, schema-validated envelope). This
   is the canonical machine-readable form.  The validator accepts it
   directly.
3. **DXF three views** (a `front.dxf` + `top.dxf` + `right.dxf` set in
   third-angle projection).  A reader in
   `cad_ai.dxf_to_ir.read_three_views` extracts the base body and
   through-holes from the three views and emits a CAD-IR.  See
   `references/dxf_reader.md` for the contract.

All three shapes are normalized into a single **CAD Intent IR (CAD-IR)**,
then compiled to a build123d Python source that the existing `cad` skill
runs.

## What this skill does NOT do

- It does not import or use SOLIDWORKS. There is no `skills/solidworks/`
  in this repository.  See `contracts/cad_ir_to_sw_contract.md` for the
  out-of-tree backend interface.
- It does not execute build123d itself. It only emits the Python source
  string and writes it to disk; running `python scripts/step ...` is
  the caller's job.
- The default `text_to_ir` is a network-free stub.  The network-capable
  client lives in the `llm/` subpackage and is opt-in.

## Layout

```
skills/cad_ai/
  SKILL.md
  references/
    architecture.md        # why this layer exists; relationship to skills/cad
    cad_intent_schema.md   # documented JSON envelope, field-by-field
    text_to_ir_prompt.md   # the prompt template (no API key required)
    dxf_reader.md          # DXF three-view contract and limits
  contracts/
    cad_ir_to_sw_contract.md  # IR -> SW instruction stream (out-of-tree
                                # SOLIDWORKS backend interface)
  scripts/
    cad_ai/
      __init__.py
      ir_schema.py         # schema constants
      ir_validate.py       # JSON envelope validator with error classification
      ir_compile.py        # CAD-IR -> build123d Python source string
      text_to_ir.py        # LLM stub (no network); returns None
      dxf_to_ir.py         # DXF three-view reader
      sw_compile.py        # CAD-IR -> SW instruction stream
      mock_sw.py           # reference SW backend (re-runs the IR
                            # through ir_compile and writes STEP via OCP)
      llm/                 # network-capable LLM client
        __init__.py
        client.py          # OpenAI-compatible HTTP client (no SDK)
        errors.py          # LLMError hierarchy
        text_to_ir.py      # real text -> IR with retry on validation
    compile_ir.py          # CLI: cad-ir.json -> generator.py
    validate_ir.py         # CLI: cad-ir.json -> ok/err
    dxf_to_ir.py           # CLI: front.dxf top.dxf right.dxf -> IR
    sw_compile.py          # CLI: cad-ir.json -> sw_instructions.json
    mock_sw.py             # CLI: cad-ir.json -> STEP via OCP (mock)
    text_to_ir.py          # CLI: text -> cad-ir.json (network)
  examples/
    mounting_plate.ir.json
    plate_with_fillet.ir.json
    mounting_plate_three_views/
      generate.py
      front.dxf
      top.dxf
      right.dxf
  tests/
    test_ir_validate.py
    test_llm_text_to_ir.py
    test_dxf_to_ir.py
```

## How to use it

### 1) Hand-written CAD-IR (no LLM, deterministic)

```bash
python skills/cad_ai/scripts/validate_ir.py \
  skills/cad_ai/examples/mounting_plate.ir.json
python skills/cad_ai/scripts/compile_ir.py \
  skills/cad_ai/examples/mounting_plate.ir.json \
  -o models/mounting_plate.gen.py
python skills/cad/scripts/step models/mounting_plate.gen.py
```

### 2) Text via the prompt template

```bash
cat skills/cad_ai/references/text_to_ir_prompt.md
# Fill the placeholder with the user's request, call your LLM,
# pipe the JSON output through validate_ir.py, then compile_ir.py.
```

### 3) Real LLM-backed text -> IR (network)

Requires an OpenAI-compatible HTTP endpoint (default: ollama at
`http://localhost:11434/v1`).

```bash
python skills/cad_ai/scripts/text_to_ir.py \
  "Mounting plate 100x60x10 with four 6mm corner holes" \
  -o /tmp/ir.json
# Then validate / compile / step as in case (1).
```

Configuration via env: `CADPY_AI_LLM_BASE_URL`, `CADPY_AI_LLM_MODEL`,
`CADPY_AI_LLM_API_KEY` (see `scripts/cad_ai/llm/client.py`).

### 4) DXF three views -> IR

```bash
python skills/cad_ai/scripts/dxf_to_ir.py \
  skills/cad_ai/examples/mounting_plate_three_views/front.dxf \
  skills/cad_ai/examples/mounting_plate_three_views/top.dxf \
  skills/cad_ai/examples/mounting_plate_three_views/right.dxf \
  -o /tmp/ir.json
# Then validate / compile / step as in case (1).
```

### 5) IR -> SOLIDWORKS instruction stream

The SOLIDWORKS backend is out of tree (this repo has no
`skills/solidworks/` and the host does not have SOLIDWORKS
installed).  Instead, the IR is translated to a versioned SW
instruction stream that an out-of-tree backend can consume.

```bash
python skills/cad_ai/scripts/sw_compile.py /tmp/ir.json -o /tmp/sw.json
python skills/cad_ai/scripts/mock_sw.py /tmp/ir.json -o /tmp/mock.step
```

See `contracts/cad_ir_to_sw_contract.md` for the instruction stream
shape and the contract tests in `tests/`.

## Validation contract

`scripts/validate_ir.py` exits non-zero with a structured error list when:

- required fields are missing
- a referenced parameter name is not declared in `parameters`
- a sketch entity uses an unsupported type
- a feature's target selector does not resolve to a known prior feature
- acceptance criteria reference a metric that the compiler cannot verify

See `references/cad_intent_schema.md` for the full contract.

## Tests

`python -m unittest discover -s skills/cad_ai/tests` runs:

- `test_ir_validate.py` -- CAD-IR contract tests + example IR tests.
- `test_llm_text_to_ir.py` -- JSON extraction + retry loop (mock LLM).
- `test_dxf_to_ir.py` -- DXF three-view reader contract tests
  (positive path, count mismatch, boundary mismatch, radius
  mismatch, unsupported entity).

All tests run with the standard library only; the LLM test mocks the
HTTP client with `unittest.mock`.  16 tests pass in roughly 0.1 s on a
developer workstation.

## Future work (out of scope for v1)

- DXF `ARC` / `LWPOLYLINE` / `SPLINE` / `HATCH` / `DIMENSION` entity
  types are rejected by `dxf_to_ir`.  A v2 reader would either add the
  missing types or auto-approximate them to lines.
- Layer / colour / linetype / block / xref parsing is not in scope.
  The v1 reader ignores layers entirely.
- View-convention auto-detection (first-angle vs third-angle) is not
  implemented; the reader assumes third-angle.
- Unit detection from `$INSUNITS` is not implemented; the reader
  assumes millimetres.
- The SOLIDWORKS backend is out of tree.  The mock backend
  (`mock_sw.py`) gives a host without SOLIDWORKS a way to verify the
  contract; a real implementation is left to a host that has the COM
  type library.
- A non-LLM drawing parser (raster PNG / PDF / SVG -> IR) is not in
  scope; the current pipeline is text-or-DXF-or-hand-IR.
