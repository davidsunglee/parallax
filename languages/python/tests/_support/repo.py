"""Repository locations, and the canonical core artifacts read from them."""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import Any, cast

from jsonschema import exceptions
from jsonschema.protocols import Validator
from jsonschema.validators import validator_for

PY_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PY_ROOT.parents[1]


@functools.cache
def _adapter_validator() -> Validator:
    schema_path = REPO_ROOT / "core" / "schemas" / "conformance-adapter.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = validator_for(schema)
    validator.check_schema(schema)
    return validator(schema)


def validate_adapter_envelope(envelope: Any) -> None:
    """Validate ``envelope`` against the conformance-adapter JSON Schema (the
    adapter wire contract), raising the error ``jsonschema.validate`` would.

    The schema is checked against its meta-schema once per process rather than
    once per envelope.
    """
    errors = _adapter_validator().iter_errors(envelope)
    # The stub leaves the return of `best_match` unannotated.
    error = cast(
        "exceptions.ValidationError | None",
        exceptions.best_match(errors),  # pyright: ignore[reportUnknownMemberType]
    )
    if error is not None:
        raise error


def canonical_snapshot_claim() -> dict[str, Any]:
    """The canonical ``slice-snapshot-1`` describe claim from ``slices.md``."""
    text = (REPO_ROOT / "core" / "spec" / "slices.md").read_text(encoding="utf-8")
    section = text.split("## Snapshot Conformance Slice", 1)[1]
    match = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)
    assert match is not None, "no fenced json claim under the Snapshot Conformance Slice heading"
    return json.loads(match.group(1))
