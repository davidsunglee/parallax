"""Descriptor-scope errors (m-descriptor): the three-phase ingestion failure
family and the canonical violation-ordering law phases 2 and 3 share.

Ingestion is judged in a fixed order — syntax, then schema, then value — and
each phase fails with its own error; no phase ever reports another phase's
failures. Model Formation is beyond ingestion: every failure past the
Unresolved Metamodel seam is a representation-independent
``MetamodelValidationError``, never a :class:`DescriptorError`.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

__all__ = [
    "DESCRIPTOR_INVALID_SYNTAX",
    "DESCRIPTOR_SCHEMA_INVALID",
    "DESCRIPTOR_VALUE_INVALID",
    "DescriptorError",
    "DescriptorFormat",
    "DescriptorPath",
    "DescriptorSchemaError",
    "DescriptorSchemaViolation",
    "DescriptorSyntaxError",
    "DescriptorValueError",
    "DescriptorValueViolation",
    "canonical_schema_violations",
    "canonical_value_violations",
]

DESCRIPTOR_INVALID_SYNTAX: Literal["descriptor-invalid-syntax"] = "descriptor-invalid-syntax"
"""Phase 1 (syntax) failure code: :class:`DescriptorSyntaxError`'s ``code``."""
DESCRIPTOR_SCHEMA_INVALID: Literal["descriptor-schema-invalid"] = "descriptor-schema-invalid"
"""Phase 2 (schema) failure code: :class:`DescriptorSchemaError`'s ``code``."""
DESCRIPTOR_VALUE_INVALID: Literal["descriptor-value-invalid"] = "descriptor-value-invalid"
"""Phase 3 (value) failure code: :class:`DescriptorValueError`'s ``code``."""

DescriptorFormat = Literal["json", "yaml"]
"""The two concrete-syntax formats descriptor ingestion accepts."""

type DescriptorPath = tuple[str | int, ...]
"""A document path from the document root: a sequence of object member names
and array indices in authoring order. The empty path is the document root."""


class DescriptorError(ValueError):
    """A descriptor document fails one phase of the three-phase ingestion
    contract (syntax, schema, or value), or a directly constructed record
    graph (the class frontend's native assembly, outside text ingestion)
    refuses to adapt into a declaration.

    Within the three-phase text-ingestion pipeline (:mod:`parallax.core.
    descriptor.ingest`), the base class is never raised directly — one of the
    three concrete subtypes below always names the failing phase and carries
    its ``code``. A direct-record caller outside that pipeline (for example
    :func:`~parallax.core.entity._declaration.native_metamodel`) MAY raise
    this base class directly for a record the declaration contract refuses;
    no phase applies there, so ``code`` is unset rather than borrowing one of
    the three reserved phase codes.
    """

    code: str


@dataclass(frozen=True, slots=True)
class DescriptorSchemaViolation:
    """One canonical-schema keyword failure (ingestion phase 2).

    ``path`` is the document path the failing keyword applied to; ``rule`` is
    the failing JSON-Schema keyword — the schema is the sole rule vocabulary,
    so no second spec-owned rule-name set exists. ``message`` is explanatory
    text excluded from equality, hashing, and ordering: violation identity is
    ``(path, rule)`` alone, so a reworded diagnostic can never change identity
    or canonical order.
    """

    path: DescriptorPath
    rule: str
    message: str = field(compare=False)


@dataclass(frozen=True, slots=True)
class DescriptorValueViolation:
    """One value-phase semantic rejection (ingestion phase 3).

    Mirrors :class:`DescriptorSchemaViolation` exactly except ``rule`` is drawn
    from the closed value-phase rejection vocabulary this module owns (for
    example ``type-spelling-invalid``) rather than from a JSON-Schema keyword.
    """

    path: DescriptorPath
    rule: str
    message: str = field(compare=False)


def _path_key(path: DescriptorPath) -> tuple[tuple[int, object], ...]:
    """A kind-tagged comparison key for one document path.

    Two paths that diverge at one segment always address the same document
    node (the canonical violation-ordering law), so real ingestion paths never
    compare a member name against an array index at the same position; tagging
    each segment by kind keeps the key comparable even so, and member names
    still compare by codepoint and array indices still compare numerically
    within their own kind.
    """
    return tuple((1, segment) if isinstance(segment, int) else (0, segment) for segment in path)


def _canonical[V: (DescriptorSchemaViolation, DescriptorValueViolation)](
    violations: Iterable[V],
) -> tuple[V, ...]:
    """``violations`` deduplicated by ``(path, rule)`` identity and sorted in
    canonical ``(path, rule)`` order.

    A strict path prefix orders before its extensions, paths order by their
    first differing segment, and equal paths order by ``rule``. Frontend,
    validator, and emission order never participate, and several violations
    equal under ``(path, rule)`` collapse to the one kept first.
    """
    by_identity: dict[tuple[DescriptorPath, str], V] = {}
    for violation in violations:
        by_identity.setdefault((violation.path, violation.rule), violation)
    return tuple(sorted(by_identity.values(), key=lambda v: (_path_key(v.path), v.rule)))


def canonical_schema_violations(
    violations: Iterable[DescriptorSchemaViolation],
) -> tuple[DescriptorSchemaViolation, ...]:
    """The canonically ordered, duplicate-free form of ``violations``."""
    return _canonical(violations)


def canonical_value_violations(
    violations: Iterable[DescriptorValueViolation],
) -> tuple[DescriptorValueViolation, ...]:
    """The canonically ordered, duplicate-free form of ``violations``."""
    return _canonical(violations)


class DescriptorSyntaxError(DescriptorError):
    """Phase 1 (syntax) ingestion failure: the text is not well-formed in its
    declared format.

    ``line``/``column`` are one-based source coordinates when the parser
    supplies them, absent (``None``) otherwise — source coordinates are
    parser-dependent, so a conforming adapter MAY omit them. ``cause`` is the
    original parser failure, preserved both as this attribute and through
    native exception chaining (``raise ... from cause``) at the raise site.
    """

    format: DescriptorFormat
    line: int | None
    column: int | None
    cause: BaseException | None

    def __init__(
        self,
        format: DescriptorFormat,
        *,
        line: int | None = None,
        column: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.code = DESCRIPTOR_INVALID_SYNTAX
        self.format = format
        self.line = line
        self.column = column
        self.cause = cause
        where = "" if line is None else f" at line {line}, column {column}"
        super().__init__(f"invalid {format} syntax{where}")


class DescriptorSchemaError(DescriptorError):
    """Phase 2 (schema) ingestion failure: the decoded document violates
    ``core/schemas/metamodel.schema.json``.

    ``violations`` is the nonempty, immutable, canonically ordered sequence of
    every failing keyword the whole document evaluation found — a conforming
    adapter never stops at the first failure. Constructing one with no
    violation raises :class:`ValueError`: a schema failure that names no
    keyword is not a report.
    """

    violations: tuple[DescriptorSchemaViolation, ...]

    def __init__(self, violations: Sequence[DescriptorSchemaViolation]) -> None:
        reported = tuple(violations)
        if not reported:
            raise ValueError("a descriptor schema failure reports at least one violation")
        self.code = DESCRIPTOR_SCHEMA_INVALID
        self.violations = reported
        rules = ", ".join(sorted({violation.rule for violation in reported}))
        super().__init__(f"{len(reported)} schema violation(s): {rules}")


class DescriptorValueError(DescriptorError):
    """Phase 3 (value) ingestion failure: a schema-valid document carries a
    value this specification names as semantically unconstructible (for
    example a ``type`` spelling whose ``decimal`` parameters break the
    ``m-core`` bounds or carry non-canonical digits).

    ``violations`` is the nonempty, immutable, canonically ordered sequence of
    every such rejection the whole document evaluation found. Constructing one
    with no violation raises :class:`ValueError`, mirroring
    :class:`DescriptorSchemaError`.
    """

    violations: tuple[DescriptorValueViolation, ...]

    def __init__(self, violations: Sequence[DescriptorValueViolation]) -> None:
        reported = tuple(violations)
        if not reported:
            raise ValueError("a descriptor value failure reports at least one violation")
        self.code = DESCRIPTOR_VALUE_INVALID
        self.violations = reported
        rules = ", ".join(sorted({violation.rule for violation in reported}))
        super().__init__(f"{len(reported)} value violation(s): {rules}")
