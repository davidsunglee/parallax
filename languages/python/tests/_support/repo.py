"""Repository locations, and the canonical core artifacts read from them."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PY_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PY_ROOT.parents[1]


def adapter_schema() -> dict[str, Any]:
    """The conformance-adapter JSON Schema (the adapter wire contract)."""
    schema_path = REPO_ROOT / "core" / "schemas" / "conformance-adapter.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def canonical_snapshot_claim() -> dict[str, Any]:
    """The canonical ``slice-snapshot-1`` describe claim from ``slices.md``."""
    text = (REPO_ROOT / "core" / "spec" / "slices.md").read_text(encoding="utf-8")
    section = text.split("## Snapshot Conformance Slice", 1)[1]
    match = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)
    assert match is not None, "no fenced json claim under the Snapshot Conformance Slice heading"
    return json.loads(match.group(1))
