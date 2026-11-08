from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

from parallax.core.base import UsageError

__all__ = [
    "DESCRIPTOR_INVALID_SYNTAX",
    "DESCRIPTOR_SCHEMA_INVALID",
    "DESCRIPTOR_VALUE_INVALID",
    "DescriptorCode",
    "DescriptorError",
    "DescriptorFormat",
    "DescriptorSchemaError",
    "DescriptorSyntaxError",
    "DescriptorValueError",
    "DescriptorViolation",
    "canonical_violations",
]

type DescriptorCode = Literal[
    "descriptor-invalid-syntax", "descriptor-schema-invalid", "descriptor-value-invalid"
]
"""The ingestion phase a :class:`DescriptorError` failed: its ``code``."""

DESCRIPTOR_INVALID_SYNTAX: Final = "descriptor-invalid-syntax"
"""Phase 1 (syntax): the text is not well-formed in its declared format."""
DESCRIPTOR_SCHEMA_INVALID: Final = "descriptor-schema-invalid"
"""Phase 2 (schema): the document's shape is not the canonical schema's."""
DESCRIPTOR_VALUE_INVALID: Final = "descriptor-value-invalid"
"""Phase 3 (value): a well-shaped document carries a value no model can hold."""

DescriptorFormat = Literal["json", "yaml"]
"""The two concrete-syntax formats descriptor ingestion accepts."""

type DescriptorPath = tuple[str | int, ...]
"""A document path from the document root: a sequence of object member names
and array indices in authoring order. The empty path is the document root."""


@dataclass(frozen=True, slots=True)
class DescriptorViolation:
    """One failure of a schema-phase keyword or a value-phase rule.

    ``path`` is the document path the failure applies to. ``rule`` is the
    failing JSON-Schema keyword in the schema phase — the schema is the sole
    rule vocabulary there, so no second spec-owned rule-name set exists — and a
    member of the closed value-phase rejection vocabulary this package owns
    (for example ``type-spelling-invalid``) in the value phase. ``message`` is
    explanatory text excluded from equality, hashing, and ordering: violation
    identity is ``(path, rule)`` alone, so a reworded diagnostic can never
    change identity or canonical order.
    """

    path: DescriptorPath
    rule: str
    message: str = field(compare=False)


class DescriptorError(UsageError):
    """A descriptor document fails one phase of the three-phase ingestion
    contract, or a record graph refuses to adapt into a declaration.

    ``code`` names the phase. ``format``, ``line``, and ``column`` are set by
    the syntax phase only: the format attempted, and one-based source
    coordinates where the parser supplies them; the parser failure is the
    native ``__cause__``. ``violations`` is the canonically ordered sequence of
    every keyword or rule the schema or value phase judged failing, and is
    empty for a syntax failure and for a refusal that judged no keyword or rule:
    a record whose shape the parser refuses, or one that adapting into a
    declaration refuses, whether those records were parsed or assembled in
    memory.
    """

    format: DescriptorFormat | None
    line: int | None
    column: int | None
    violations: tuple[DescriptorViolation, ...]

    def __init__(
        self,
        code: DescriptorCode,
        message: str,
        *,
        format: DescriptorFormat | None = None,
        line: int | None = None,
        column: int | None = None,
        violations: Sequence[DescriptorViolation] = (),
    ) -> None:
        super().__init__(code, message)
        self.format = format
        self.line = line
        self.column = column
        self.violations = tuple(violations)


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


def canonical_violations(
    violations: Iterable[DescriptorViolation],
) -> tuple[DescriptorViolation, ...]:
    """``violations`` deduplicated by ``(path, rule)`` identity and sorted in
    canonical ``(path, rule)`` order.

    A strict path prefix orders before its extensions, paths order by their
    first differing segment, and equal paths order by ``rule``. Frontend,
    validator, and emission order never participate, and several violations
    equal under ``(path, rule)`` collapse to the one kept first.
    """
    by_identity: dict[tuple[DescriptorPath, str], DescriptorViolation] = {}
    for violation in violations:
        by_identity.setdefault((violation.path, violation.rule), violation)
    return tuple(sorted(by_identity.values(), key=lambda v: (_path_key(v.path), v.rule)))


class DescriptorSyntaxError(DescriptorError):
    """Phase 1 (syntax) ingestion failure: the text is not well-formed in its
    declared format.

    ``cause`` is the original parser failure, preserved both as this attribute
    and through native exception chaining (``raise ... from cause``) at the
    raise site.
    """

    cause: BaseException | None

    def __init__(
        self,
        format: DescriptorFormat,
        *,
        line: int | None = None,
        column: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        where = "" if line is None else f" at line {line}, column {column}"
        super().__init__(
            DESCRIPTOR_INVALID_SYNTAX,
            f"invalid {format} syntax{where}",
            format=format,
            line=line,
            column=column,
        )
        self.cause = cause


class DescriptorSchemaError(DescriptorError):
    """Phase 2 (schema) ingestion failure: the decoded document violates
    ``core/schemas/metamodel.schema.json``.

    ``violations`` is nonempty: every failing keyword the whole document
    evaluation found, since a conforming adapter never stops at the first
    failure. Constructing one with no violation raises :class:`ValueError`: a
    schema failure that names no keyword is not a report.
    """

    def __init__(self, violations: Sequence[DescriptorViolation]) -> None:
        reported = tuple(violations)
        if not reported:
            raise ValueError("a descriptor schema failure reports at least one violation")
        rules = ", ".join(sorted({violation.rule for violation in reported}))
        super().__init__(
            DESCRIPTOR_SCHEMA_INVALID,
            f"{len(reported)} schema violation(s): {rules}",
            violations=reported,
        )


class DescriptorValueError(DescriptorError):
    """Phase 3 (value) ingestion failure: a schema-valid document carries a
    value this specification names as semantically unconstructible (for
    example a ``type`` spelling whose ``decimal`` parameters break the
    ``m-core`` bounds or carry non-canonical digits).

    ``violations`` is nonempty: every such rejection the whole document
    evaluation found. Constructing one with no violation raises
    :class:`ValueError`, mirroring :class:`DescriptorSchemaError`.
    """

    def __init__(self, violations: Sequence[DescriptorViolation]) -> None:
        reported = tuple(violations)
        if not reported:
            raise ValueError("a descriptor value failure reports at least one violation")
        rules = ", ".join(sorted({violation.rule for violation in reported}))
        super().__init__(
            DESCRIPTOR_VALUE_INVALID,
            f"{len(reported)} value violation(s): {rules}",
            violations=reported,
        )
