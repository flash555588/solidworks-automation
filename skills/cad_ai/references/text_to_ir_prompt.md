# Text -> CAD-IR prompt template

The prompt is intentionally short. It does not ask the model to write
SOLIDWORKS calls. It asks for the canonical CAD-IR JSON envelope only.

```
You are a CAD planning assistant. Given a natural-language description
of a mechanical part, emit a single JSON object that matches the
CAD-IR v0 schema (see references/cad_intent_schema.md). No commentary,
no markdown, no code blocks: the entire response must be a single JSON
object starting with `{` and ending with `}`.

Constraints:
- All numeric values must be expressed in millimeters.
- Every dimension mentioned in the description must appear either as a
  literal in a feature or as a named entry in `parameters`.
- If a dimension is missing or ambiguous, choose a reasonable default,
  add it to `parameters` with a name prefixed `assumed_`, and list it
  under the field `assumptions` at the top level.
- Only use feature types from the v0 whitelist: extrude_add,
  extrude_cut, hole_through, fillet, chamfer.
- Do not invent feature types. The validator will reject the output
  if you do.
- Re-check that every parameter name you reference is declared in
  `parameters`. Mismatched names are the most common failure.

User request:
<<<
{prompt}
>>>
```

## Stubs (no LLM, deterministic)

`scripts/cad_ai/text_to_ir.py` is a stub: it returns `None` and writes a
short message. The orchestrator is responsible for calling the LLM
itself (so the orchestrator can choose the model and the API key
provider). The skill stays network-free.

## When the prompt fails validation

Run `validate_ir.py`. If it returns errors, the most common patterns are:

- Field path `$.features[*].target` and `code: unknown_ref` -> you
  referenced a feature id that was not yet created. Move the feature
  later in the list, or rename the reference.
- Field path `$.parameters` and `code: unused_parameter` -> you declared
  a parameter that is never referenced. Drop it or use it.
- Field path `$.features[*].type` and `code: unsupported_type` -> you
  used a feature type outside the v0 whitelist.
