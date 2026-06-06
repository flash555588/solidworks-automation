# Architecture: where cad_ai sits

The repository `text-to-cad-review` is a collection of skills for
generating CAD, robot descriptions, and fabrication data.  The
execution backbone is:

```
input -> skills/cad/scripts/step -> packages/cadpy (B-Rep + STEP + GLB) -> models/
                                      \
                                       -> scripts/inspect, scripts/snapshot (validation + review)
```

`skills/cad` is the only piece that produces STEP files today.  It
accepts `gen_step()` Python sources.  There is no
`skills/solidworks/` in this repository; SOLIDWORKS integration is
a separate, future skill.

## The cad_ai layer

`cad_ai` sits **above** `skills/cad`.  It owns the planning layer;
`skills/cad` owns the geometry layer; a future `skills/solidworks`
would own the native COM execution layer and live as a peer of
`skills/cad`, not inside `cad_ai`.

```
                    +----------------------+
text prompt   ----> | cad_ai.llm.text_to_ir  | --+
                    +----------------------+   |
                                                  \
                    +----------------------+     +--> CAD-IR
DXF 3 views   ----> | cad_ai.dxf_to_ir       | --+   (validated)
                    +----------------------+   /
                                                  /
hand-written  ---->  (already a CAD-IR)  ------+
                                |
                                v
                    cad_ai/scripts/validate_ir.py  (schema + error classification)
                                |
                                v
                    cad_ai/scripts/compile_ir.py  (IR -> build123d source)
                                |
                                v
                    skills/cad/scripts/step       (build123d -> STEP + sidecar GLB)
                                |
                                v
                    skills/cad/scripts/inspect     (bbox / faceCount / edgeCount / refs)
                                |
                                v
                               .step  /  .glb
                                |
                                +-- (parallel) --> cad_ai/scripts/sw_compile.py
                                |                  |
                                |                  v
                                |            sw_instructions.v0  (consumed by an
                                |             (JSON document)      out-of-tree SW
                                |                                 executor; or by
                                |                                 cad_ai/scripts/mock_sw.py
                                |                                 on hosts without SW)
                                v
                          models/*.step
```

The boundary is intentional:

- `cad_ai` owns **intent** (what to build, expressed in a
  portable IR).
- `skills/cad` owns **geometry** (how to build it, with
  build123d + OCP).
- A future `skills/solidworks` would own **native COM
  execution**.

The IR is the contract between `cad_ai` and `skills/cad`; the SW
instruction stream is the contract between `cad_ai` and the
(out-of-tree) SOLIDWORKS backend.

## Why a new skill, not a new packages/ entry

`packages/` in this repo holds shared Python runtimes (`cadpy`,
`cadpy_metadata`, `cadjs`).  `cad_ai` is not shared by other
skills today and it does not need its own runtime; it only writes
a Python string to disk.  So it lives under `skills/`, not
`packages/`.  If `cad_ai` later grows dependencies that other
skills want, that decision is revisitable.

## LLM integration: opt-in, never required

The default `cad_ai.text_to_ir.text_to_ir` is a network-free stub
that returns `None`.  The network-capable implementation lives in
the `cad_ai.llm` subpackage, which uses a stdlib HTTP client
speaking the OpenAI chat-completions protocol (works against
ollama, vLLM, OpenAI, and any compatible proxy).

The reason for this split:

- The IR is the source of truth.  The LLM is optional.
- Headless / CI / offline runs are possible without any API key.
- The validator is the contract.  A bad LLM output is rejected at
  the validator, never at geometry compile time.

A caller that wants the LLM-backed variant imports from
`cad_ai.llm` explicitly.  No other module in the skill makes a
network call.

## DXF integration: narrow but real

The DXF reader accepts only `LINE` and `CIRCLE` entities in three
views (front / top / right, third-angle projection).  It pairs
holes across views **by index** and emits a CAD-IR with an
`extrude_add` base and one `hole_through` per detected hole.

Why so narrow?  Because the geometric matching across three
views is already a hard problem.  Once it works on a clean DXF
rectangle with 4 holes, the next problems are arc-to-line
approximation, view-convention auto-detection, and unit
detection.  Those are v2.

The reader does not replace the LLM adapter; it sits beside it as
another input shape.  Both feed into the same IR validator.

## SOLIDWORKS: contract, not code

This repository does not ship a `skills/solidworks/` skill.  The
host this skill was written on does not have SOLIDWORKS
installed.  So the SOLIDWORKS story is contract-only:

- `cad_ai/scripts/sw_compile.py` translates an IR into a
  versioned SW instruction stream (a JSON document).
- `cad_ai/scripts/mock_sw.py` is a reference implementation that
  re-runs the IR through `ir_compile.py` and writes STEP via
  OCP.  This is what we use on hosts without SOLIDWORKS to
  verify the contract; a real SOLIDWORKS backend must produce
  a STEP that matches the mock's within `tolerance_mm` from
  the IR's `acceptance` block.
- `contracts/cad_ir_to_sw_contract.md` is the interface a
  SOLIDWORKS author on a different host implements against.

Adding `skills/solidworks/` later would not require changes to
`cad_ai` -- it would just be a new consumer of the SW
instruction stream.

## What is the IR for?

The IR is the single source of truth.  Once an IR exists:

- It is *validated* (`scripts/validate_ir.py`) so we know it
  describes something the compiler can deterministically build.
- It is *compiled* to build123d source (`scripts/compile_ir.py`)
  and fed to `scripts/step` for STEP output.
- It is *translated* to a SW instruction stream
  (`scripts/sw_compile.py`) and either fed to a real SOLIDWORKS
  backend or to the mock.
- It is *inspectable* by humans; the JSON is small and stable.

A bad LLM output is caught at the validator.  A bad DXF input is
caught at the reader.  A bad SOLIDWORKS implementation is caught
by the contract tests.  Nothing reaches `scripts/step` that has
not been validated.

## Subsystem inventory

| Subsystem | Files | What it does | Test file |
|---|---|---|---|
| Schema constants | `scripts/cad_ai/ir_schema.py` | Whitelist of feature types, sketch entity types, selector kinds. | (no direct test; covered transitively) |
| Validator | `scripts/cad_ai/ir_validate.py` | Walk a JSON dict, return `{ok, errors}`. | `tests/test_ir_validate.py` |
| build123d compiler | `scripts/cad_ai/ir_compile.py` | IR -> Python source. | (covered by example-driven end-to-end checks; no unit test for the compiler yet) |
| LLM stub (default) | `scripts/cad_ai/text_to_ir.py` | Network-free `None` returner. | (implicit; tests don't import the stub) |
| LLM client (real) | `scripts/cad_ai/llm/{client,errors,text_to_ir}.py` | OpenAI-compatible HTTP + retry loop. | `tests/test_llm_text_to_ir.py` |
| DXF reader | `scripts/cad_ai/dxf_to_ir.py` | 3 views -> IR. | `tests/test_dxf_to_ir.py` |
| SW instruction compiler | `scripts/cad_ai/sw_compile.py` | IR -> versioned SW instruction stream. | (covered by `contracts/cad_ir_to_sw_contract.md`; no automated test yet) |
| Mock SW backend | `scripts/cad_ai/mock_sw.py` | SW instruction stream -> STEP via OCP. | (covered by `contracts/cad_ir_to_sw_contract.md`; no automated test yet) |

## Where to look for the contract

- `references/cad_intent_schema.md` -- the IR contract (v0 schema,
  v1 limitations, changelog).
- `references/text_to_ir_prompt.md` -- the LLM prompt template.
- `references/dxf_reader.md` -- the DXF reader contract.
- `contracts/cad_ir_to_sw_contract.md` -- the SOLIDWORKS
  contract.
- `docs/cad_ai_overview.md` -- this skill's onboarding guide.
