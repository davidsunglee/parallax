"""The facts a conformance lane reads off a case's DOCUMENT: its compile
eligibility, its ``when`` and the scenario steps or write-sequence entries
under it, its unit-of-work Concurrency Preference, a step's streamed page
size, and the translations of an authored step into the canonical shapes the
core ingresses accept.

Every reader here is a pure read of the case document that names the case
file in its refusal, so a mis-authored corpus reports the case rather than an
engine frame. No reader consults a model or a database: what a case SAYS is
settled here, and what it means against its model is the lanes' and
:mod:`~parallax.conformance._mechanism.model_facts`'s.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from parallax.conformance import case_format
from parallax.conformance._mechanism.envelope import EngineError
from parallax.core.unit_work import Concurrency

__all__ = [
    "RunOnly",
    "batch_size_of",
    "canonical_predicate_doc",
    "concurrency",
    "eligibility",
    "has_action_step",
    "scenario_steps",
    "when",
    "write_sequence_entries",
]


@dataclass(frozen=True, slots=True)
class RunOnly:
    """A case the corpus declares compile-ineligible (`compileEligibility: run-only`)."""

    reason: str


def eligibility(case: case_format.Case) -> RunOnly | None:
    """The case's compile eligibility: ``None`` when compile-eligible, else run-only."""
    raw = case.document.get("compileEligibility")
    if not isinstance(raw, Mapping):
        return None
    declaration = cast("Mapping[str, object]", raw)
    if declaration.get("mode") != "run-only":
        return None
    reason = declaration.get("reason")
    return RunOnly(reason=str(reason) if isinstance(reason, str) else "run-only")


def when(case: case_format.Case) -> Mapping[str, object]:
    """The case's ``when`` block, refused by name when the case carries none."""
    raw = case.document.get("when")
    if not isinstance(raw, Mapping):
        raise EngineError(f"{case.path.name}: case has no `when`")
    return cast("Mapping[str, object]", raw)


def scenario_steps(case: case_format.Case) -> list[Mapping[str, object]]:
    """The case's ``when.scenario`` steps, in order."""
    steps = when(case).get("scenario")
    if not isinstance(steps, list):
        raise EngineError(f"{case.path.name}: scenario case has no `when.scenario` list")
    return [cast("Mapping[str, object]", step) for step in cast("list[object]", steps)]


def write_sequence_entries(case: case_format.Case) -> list[Mapping[str, object]]:
    """The case's ``when.writeSequence`` entries, in order."""
    entries = when(case).get("writeSequence")
    if not isinstance(entries, list):
        raise EngineError(f"{case.path.name}: writeSequence case has no `when.writeSequence` list")
    return [cast("Mapping[str, object]", entry) for entry in cast("list[object]", entries)]


def concurrency(case: case_format.Case) -> Concurrency:
    """The case's declared unit-of-work Concurrency Preference
    (`when.uow.concurrency`; `m-unit-work` "Strategy selection"), defaulting to
    `optimistic` when the case declares none — the SAME default
    `m-unit-work.TransactionSettings` resolves and the one `m-case-format`
    states for the `when.uow` block.

    A preference is not a strategy: what each step's own Entity participates
    under is derived from this value and that Entity's Optimistic Lock Facet, so
    an unversioned Non-Temporal target still locks and still writes ungated
    under the default. A case whose golden SQL depends on that choice declares
    the preference explicitly (`m-case-format`); `when.uow` is schema-legal on
    writeSequence shape (`compatibility-case.schema.json`'s writeSequence
    `propertyNames` admits `uow` alongside `writeSequence`)."""
    raw = case.document.get("when")
    if isinstance(raw, Mapping):
        uow = cast("Mapping[str, object]", raw).get("uow")
        if isinstance(uow, Mapping):
            value = cast("Mapping[str, object]", uow).get("concurrency")
            if value == "locking":
                return "locking"
    return "optimistic"


def batch_size_of(carrier: Mapping[str, object], where: str) -> int | None:
    """The page size the `stream` context member on ``carrier`` requests, or
    ``None`` where it carries no such member and the read is therefore eager.

    One reader for the member's two placements (`m-case-format` *Streamed
    reads*): a `read` case's own ``when``, and a scenario READ step. The member
    means one thing in both, so a page size is read one way in both, and
    ``where`` names the placement a malformed one is reported at.
    """
    stream = carrier.get("stream")
    if stream is None:
        return None
    size = (
        cast("Mapping[str, object]", stream).get("batchSize")
        if isinstance(stream, Mapping)
        else None
    )
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise EngineError(
            f"{where}: a streamed delivery declares a positive integer "
            f"`stream.batchSize` (got {size!r})"
        )
    return int(size)


def has_action_step(steps: Sequence[Mapping[str, object]]) -> bool:
    """Whether a scenario carries at least one lifecycle **action** step
    (m-case-format "Lifecycle action steps") — the discriminator between the
    engine's two scenario paths, which are never mixed.

    A scenario carrying one runs on the snapshot-read path, which holds each
    find's materialized view across the steps that follow it so a `mutate` and
    an `access` have something to name; every other scenario runs on the keyed
    unit-of-work path, which holds `uow` groups instead and sees no action step
    at all. **Both** paths execute `write:` steps: the shapes overlap in the
    write step alone, which is why the split is drawn on the action step."""
    return any("action" in step for step in steps)


def canonical_predicate_doc(raw_write: Mapping[str, object]) -> dict[str, object]:
    """A scenario predicate-write step's own ``write`` field, translated to the
    canonical ``write-instruction.schema.json`` predicate shape
    (`m-case-format` "Predicate-selected write instruction"): ``at`` (the
    Clock-context Transaction-Time instant) is DROPPED — never an instruction
    field, ADR 0010. ``validFrom`` and ``until`` already use the canonical
    spelling. Every caller that hands a raw case document to
    :func:`~parallax.core.unit_work.instructions.deserialize` routes through
    this first — the canonical deserializer rejects ``at``/``until`` outright
    as unexpected keys.
    """
    doc = dict(raw_write)
    doc.pop("at", None)
    return doc
