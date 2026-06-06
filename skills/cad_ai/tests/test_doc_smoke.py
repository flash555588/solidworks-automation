"""Document smoke tests for cad_ai.

The SKILL.md, the cad_ai overview, and the references/architecture
documents mention specific files and example IRs by name.  This
test extracts those references and checks each one exists on
disk.  It does not validate content; it only validates that the
documentation is in sync with the actual layout.

Run with:

    python -m unittest skills/cad_ai/tests/test_doc_smoke.py
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

# Path resolution: this file is .../skills/cad_ai/tests/test_doc_smoke.py
# so the skill root is parents[1] and the repo root is parents[3].
_SKILL_ROOT = Path(__file__).resolve().parents[1]      # .../skills/cad_ai
_REPO_ROOT = Path(__file__).resolve().parents[3]      # .../text-to-cad-review


# All paths the docs claim to live under `skills/cad_ai/`.  If a
# path here is missing, either the doc got out of sync or the
# file was deleted without updating the doc.
SKILL_RELATIVE_PATHS = [
    # Modules
    "scripts/cad_ai/ir_schema.py",
    "scripts/cad_ai/ir_validate.py",
    "scripts/cad_ai/ir_compile.py",
    "scripts/cad_ai/text_to_ir.py",
    "scripts/cad_ai/dxf_to_ir.py",
    "scripts/cad_ai/sw_compile.py",
    "scripts/cad_ai/mock_sw.py",
    "scripts/cad_ai/llm/client.py",
    "scripts/cad_ai/llm/errors.py",
    "scripts/cad_ai/llm/text_to_ir.py",
    # CLI wrappers
    "scripts/compile_ir.py",
    "scripts/validate_ir.py",
    "scripts/dxf_to_ir.py",
    "scripts/sw_compile.py",
    "scripts/mock_sw.py",
    "scripts/text_to_ir.py",
    # References
    "references/architecture.md",
    "references/cad_intent_schema.md",
    "references/text_to_ir_prompt.md",
    "references/dxf_reader.md",
    # Contracts
    "contracts/cad_ir_to_sw_contract.md",
    # Examples
    "examples/mounting_plate.ir.json",
    "examples/plate_with_fillet.ir.json",
    "examples/mounting_plate_three_views/generate.py",
    "examples/mounting_plate_three_views/front.dxf",
    "examples/mounting_plate_three_views/top.dxf",
    "examples/mounting_plate_three_views/right.dxf",
    # Tests
    "tests/test_ir_validate.py",
    "tests/test_llm_text_to_ir.py",
    "tests/test_dxf_to_ir.py",
    "tests/test_sw_compile.py",
    "tests/test_doc_smoke.py",
    # Onboarding
    "docs/cad_ai_overview.md",
    "SKILL.md",
]

# Things the docs say do NOT exist.  If one of these is created
# in the future, the docs need to be re-examined.

OUT_OF_TREE_ABSENT = [
    _REPO_ROOT / "skills" / "solidworks",
]


def _gather_markdown_files():
    md = []
    for sub in ("", "references", "contracts", "docs"):
        base = _SKILL_ROOT / sub if sub else _SKILL_ROOT
        if base.is_dir():
            md.extend(base.rglob("*.md"))
    return sorted(set(md))


# Regex used to detect references to skill-internal files in
# markdown.  We accept any path that begins with one of the
# known top-level directories (scripts/, references/, contracts/,
# examples/, tests/, docs/) or with `SKILL.md`.
_INTERNAL_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_/.])"
    r"((?:scripts|references|contracts|examples|tests|docs)/"
    r"[A-Za-z0-9_./-]+\.[A-Za-z0-9]+|SKILL\.md)"
)


def _extract_referenced_paths(md_text):
    return {m.group(1) for m in _INTERNAL_PATH_RE.finditer(md_text)}


class DocLayoutConsistencyTests(unittest.TestCase):
    def test_skill_relative_paths_exist(self):
        missing = []
        for rel in SKILL_RELATIVE_PATHS:
            p = _SKILL_ROOT / rel
            if not p.exists():
                missing.append(rel)
        self.assertEqual(missing, [],
                          msg="doc-referenced paths missing on disk: "
                              + ", ".join(missing))

    def test_out_of_tree_doc_claims_match_actual_layout(self):
        for p in OUT_OF_TREE_ABSENT:
            self.assertFalse(
                p.exists(),
                msg=f"doc claims {p.name!r} does not exist, but it does: "
                    f"the docs need to be updated",
            )

    def test_every_markdown_referenced_path_also_exists(self):
        """Cross-check: pick up paths that the .md files actually
        mention, and assert each one is on the SKILL_RELATIVE_PATHS
        allowlist.  Catches "doc mentions a file that the smoke
        list missed" and "doc mentions a file that does not exist"
        in one go.

        Note: the regex matches paths under `references/`, etc.,
        that may also exist in OTHER skills.  The allowlist
        implicitly scopes us to the cad_ai skill; we trust the
        maintainer to have made a SKILL.md that does not reference
        another skill's files by relative path.
        """
        allowlist = set(SKILL_RELATIVE_PATHS)
        referenced = set()
        for md in _gather_markdown_files():
            referenced |= _extract_referenced_paths(md.read_text(encoding="utf-8"))
        rel_referenced = {p.replace("\\", "/") for p in referenced}
        unknown = sorted(p for p in rel_referenced if p not in allowlist)
        self.assertEqual(unknown, [],
                          msg="docs reference paths that are not in the "
                              "allowlist (add them or update the docs): "
                              + ", ".join(unknown))


if __name__ == "__main__":
    unittest.main()
