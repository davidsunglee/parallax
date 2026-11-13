from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Literal, cast

from parallax.core.internal.base import UsageError

if TYPE_CHECKING:
    from parallax.core.internal.database_binding._authored import DatabaseBinding

__all__ = [
    "BINDING_DEFINITION_REJECTED",
    "BINDING_REQUIRED",
    "BINDING_RESOLUTION_REJECTED",
    "REQUIRED",
    "BindingError",
    "BindingErrorCode",
    "BindingIssue",
    "BindingPath",
    "require_binding",
]

type BindingErrorCode = Literal["binding-definition-rejected", "binding-resolution-rejected"]
"""The phase a :class:`BindingError` failed: its ``code``."""

BINDING_DEFINITION_REJECTED: Final = "binding-definition-rejected"
"""The binding's own shape is wrong, whatever model it is later resolved for."""
BINDING_RESOLUTION_REJECTED: Final = "binding-resolution-rejected"
"""The binding cannot place the model it is resolved for."""

type BindingPath = tuple[str, ...]
"""A path into the binding document, spelled in its artifact vocabulary."""


@dataclass(frozen=True, slots=True)
class BindingIssue:
    """One binding problem, located by its path into the binding document.

    ``path`` uses the artifact's own keys, such as
    ``("entities", "commerce.Customer", "table")``, whether the binding was
    written as a document or constructed in code. ``related`` names other
    entries the problem involves. ``message`` is excluded from equality.
    """

    code: str
    path: BindingPath
    related: tuple[BindingPath, ...] = ()
    message: str = field(default="", compare=False)


class BindingError(UsageError):
    """A database binding was refused; `issues` lists every problem.

    ``code`` is ``binding-definition-rejected`` when the binding's own shape is
    wrong and ``binding-resolution-rejected`` when it cannot place a model.
    ``issues`` is nonempty, free of repeats, and canonically ordered by path,
    then code, then related paths.
    """

    issues: tuple[BindingIssue, ...]

    def __init__(self, code: BindingErrorCode, issues: Iterable[BindingIssue]) -> None:
        unique = {(issue.path, issue.code, issue.related): issue for issue in reversed([*issues])}
        reported = tuple(unique[key] for key in sorted(unique))
        if not reported:
            raise ValueError("a binding refusal reports at least one issue")
        self.issues = reported
        lines = "".join(
            f"\n  {issue.code} at {issue.path!r}" + (f": {issue.message}" if issue.message else "")
            for issue in reported
        )
        super().__init__(code, f"{len(reported)} issue(s){lines}")


BINDING_REQUIRED: Final = "binding-required"
"""A model was prepared, connected, or evolved without the binding that places it."""

_BINDING_GUIDE: Final = "docs/guide/02-modeling.md#database-bindings"


class _Required:
    __slots__ = ()

    def __repr__(self) -> str:
        return "<binding required>"


REQUIRED: Final = _Required()
"""The default a binding parameter carries only to name its omission in a refusal."""


def require_binding(binding: object, verb: str) -> DatabaseBinding:
    """``binding`` itself, refusing an omitted one with migration guidance.

    No connection default, ``search_path``, or current database places a
    model, so omitting the binding is refused rather than defaulted.
    """
    if isinstance(binding, _Required):
        raise UsageError(
            BINDING_REQUIRED,
            f"{verb} requires binding=, the Database Binding that places the model's tables "
            f"and sequences, such as parallax.postgres.PostgresBinding; see {_BINDING_GUIDE}",
        )
    return cast("DatabaseBinding", binding)
