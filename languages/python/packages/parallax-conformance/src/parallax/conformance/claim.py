"""``parallax.conformance.claim`` — the canonical ``slice-snapshot-1`` claim.

The exact ``describe`` capability envelope the Python target claims, copied
verbatim from the canonical claim in ``core/spec/slices.md`` (adapter identity
aside) except for the dialects, which are derived from the declared matrix
profiles rather than restated here. This is the single in-code source of truth
for the adapter's ``describe`` output and its unsupported-classification filters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from parallax.conformance.profile import profile_dialects

__all__ = ["ADAPTER", "SNAPSHOT_CLAIM", "Adapter", "Claim"]


@dataclass(frozen=True, slots=True)
class Adapter:
    """The adapter identity reported in every envelope's ``adapter`` field."""

    language: str
    name: str
    version: str

    def to_json(self) -> dict[str, str]:
        return {"language": self.language, "name": self.name, "version": self.version}


@dataclass(frozen=True, slots=True)
class Claim:
    """A conformance claim: the broad filters plus the ``caseTags`` selection.

    Every filter is authored except the dialects, which are derived from the
    declared matrix profiles — a claimed dialect is one some profile actually
    runs the suite against, so a claim no adapter backs is unwritable.
    """

    modules: tuple[str, ...]
    case_shapes: tuple[str, ...]
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    commands: tuple[str, ...]
    provisioning: str

    @property
    def dialects(self) -> tuple[str, ...]:
        """The dialects the declared profiles run the suite against."""
        return profile_dialects()

    def capabilities(self) -> dict[str, object]:
        """The ``capabilities`` block of a ``describe`` envelope."""
        case_tags: dict[str, list[str]] = {}
        if self.include:
            case_tags["include"] = list(self.include)
        if self.exclude:
            case_tags["exclude"] = list(self.exclude)
        capabilities: dict[str, object] = {
            "modules": list(self.modules),
            "dialects": list(self.dialects),
            "caseShapes": list(self.case_shapes),
        }
        if case_tags:
            capabilities["caseTags"] = case_tags
        capabilities["commands"] = list(self.commands)
        capabilities["provisioning"] = self.provisioning
        return capabilities


# The Python adapter identity (spec/python.md §1).
ADAPTER: Final[Adapter] = Adapter(language="python", name="parallax-core", version="0.1.0")

# The canonical slice-snapshot-1 claim (core/spec/slices.md, adapter aside).
SNAPSHOT_CLAIM: Final[Claim] = Claim(
    modules=(
        "m-api-conformance",
        "m-auto-retry",
        "m-batch-write",
        "m-bitemp-write",
        "m-case-format",
        "m-conformance-adapter",
        "m-core",
        "m-db-error",
        "m-deep-fetch",
        "m-descriptor",
        "m-dialect",
        "m-document-codec",
        "m-execution-lifecycle",
        "m-inheritance",
        "m-metamodel",
        "m-model-evolution",
        "m-model-formation",
        "m-navigate",
        "m-object-query",
        "m-opt-lock",
        "m-pk-gen",
        "m-predicate",
        "m-read-lock",
        "m-relationship",
        "m-snapshot-read",
        "m-sql",
        "m-storage-layout",
        "m-temporal-read",
        "m-txtime-write",
        "m-unit-work",
        "m-value-object",
        "m-wire",
    ),
    case_shapes=(
        "read",
        "writeSequence",
        "scenario",
        "conflict",
        "boundary",
        "error",
        "concurrencySuccess",
        "rejected",
        "evolution",
    ),
    include=("slice-snapshot-1",),
    exclude=(),
    commands=("describe", "compile", "run"),
    provisioning="self-managed",
)
