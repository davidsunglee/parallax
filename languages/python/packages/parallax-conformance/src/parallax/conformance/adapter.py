"""``parallax.conformance.adapter`` — the in-process conformance adapter core.

Plain functions returning **envelope** dicts: the JSON documents
``m-conformance-adapter`` defines as the wire surface (validated against
``core/schemas/conformance-adapter.schema.json``). ``describe`` reports the
claim; ``compile_case`` / ``run_case`` classify the request against the claim's
filters in contract order and, for a claimed case, emit an ``error`` envelope
until the compile/run lanes come online (COR-3 Phase 5+).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from parallax.conformance import case_format
from parallax.conformance.claim import ADAPTER, SNAPSHOT_CLAIM, Adapter, Claim

__all__ = [
    "SCHEMA_VERSION",
    "Diagnostic",
    "Envelope",
    "classify",
    "compile_case",
    "describe",
    "error",
    "run_case",
    "unsupported_command",
]

SCHEMA_VERSION: Final[str] = "1"

Envelope = dict[str, Any]

# Exit codes are owned by the CLI; the adapter reports status only.
_STUB_MESSAGE: Final[str] = "compile/run is not implemented until COR-3 Phase 5+"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One envelope diagnostic naming the failed filter (or the failure)."""

    code: str
    message: str

    def to_json(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def _common(command: str, status: str, adapter: Adapter) -> Envelope:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "command": command,
        "status": status,
        "adapter": adapter.to_json(),
    }


def _non_ok(command: str, status: str, diagnostic: Diagnostic, adapter: Adapter) -> Envelope:
    envelope = _common(command, status, adapter)
    envelope["diagnostics"] = [diagnostic.to_json()]
    return envelope


def describe(claim: Claim = SNAPSHOT_CLAIM, adapter: Adapter = ADAPTER) -> Envelope:
    """The ``describe`` envelope: the adapter's claimed capability set."""
    envelope = _common("describe", "ok", adapter)
    envelope["capabilities"] = claim.capabilities()
    return envelope


def classify(
    command: str,
    dialect: str,
    case: case_format.Case,
    claim: Claim = SNAPSHOT_CLAIM,
) -> Diagnostic | None:
    """Classify a case command against the claim's filters in contract order.

    Returns ``None`` when the case command is within the claim, or the
    diagnostic naming the **first** failed filter otherwise (command → dialect
    → shape → module tags → include → exclude).
    """
    if command not in claim.commands:
        return Diagnostic("unsupported-command", f"command {command!r} is not claimed")
    if dialect not in claim.dialects:
        return Diagnostic("unsupported-dialect", f"dialect {dialect!r} is not claimed")
    if case.shape not in claim.case_shapes:
        return Diagnostic("unsupported-case-shape", f"case shape {case.shape!r} is not claimed")
    unclaimed = sorted(case.module_tags - set(claim.modules))
    if unclaimed:
        return Diagnostic("unsupported-module", f"module tags outside the claim: {unclaimed}")
    include = set(claim.include)
    if include and set(case.tags).isdisjoint(include):
        return Diagnostic("unsupported-case-tag", f"case carries none of {sorted(include)}")
    exclude = set(claim.exclude)
    if exclude and not set(case.tags).isdisjoint(exclude):
        offending = sorted(set(case.tags) & exclude)
        return Diagnostic("unsupported-case-tag", f"case carries excluded tags: {offending}")
    return None


def unsupported_command(command: str, adapter: Adapter = ADAPTER) -> Envelope:
    """An ``unsupported`` envelope for a command the adapter never claims."""
    diagnostic = Diagnostic("unsupported-command", f"command {command!r} is not claimed")
    return _non_ok(command, "unsupported", diagnostic, adapter)


def error(command: str, diagnostic: Diagnostic, adapter: Adapter = ADAPTER) -> Envelope:
    """An ``error`` envelope carrying ``diagnostic`` (e.g. an unreadable case)."""
    return _non_ok(command, "error", diagnostic, adapter)


def _classified(
    command: str,
    case_path: str | Path,
    dialect: str,
    claim: Claim,
    adapter: Adapter,
) -> Envelope:
    case = case_format.load_case(Path(case_path))
    diagnostic = classify(command, dialect, case, claim)
    if diagnostic is not None:
        return _non_ok(command, "unsupported", diagnostic, adapter)
    # Claimed case command: the compile/run lanes are not wired yet.
    return _non_ok(command, "error", Diagnostic("not-implemented", _STUB_MESSAGE), adapter)


def compile_case(
    case_path: str | Path,
    dialect: str,
    claim: Claim = SNAPSHOT_CLAIM,
    adapter: Adapter = ADAPTER,
) -> Envelope:
    """Classify then (for a claimed case) stub the ``compile`` command."""
    return _classified("compile", case_path, dialect, claim, adapter)


def run_case(
    case_path: str | Path,
    dialect: str,
    claim: Claim = SNAPSHOT_CLAIM,
    adapter: Adapter = ADAPTER,
) -> Envelope:
    """Classify then (for a claimed case) stub the ``run`` command."""
    return _classified("run", case_path, dialect, claim, adapter)
