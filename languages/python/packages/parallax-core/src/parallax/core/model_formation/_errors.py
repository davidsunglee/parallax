"""The two disjoint Model Formation failure families (m-model-formation).

An invalid model and a broken implementation are different facts about
different authors, so they never share a type.
:class:`MetamodelValidationError` says the supplied model is invalid and carries
every issue that makes it so; :class:`FormationContractError` says a
contributor, profile, or manifest violated its own contract. A contract failure
is never silently deduplicated into an issue, and neither publishes an accepted
Metamodel, facet set, or any other formation output.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from parallax.core.metamodel import MetamodelIssue
from parallax.core.model_formation._manifest import ModuleIdentity

__all__ = [
    "FORMATION_COMPILER_FAILED",
    "FORMATION_CONTRACT_CODES",
    "FORMATION_FACET_DUPLICATE",
    "FORMATION_FACET_MISSING",
    "FORMATION_ISSUE_CODE_INVALID",
    "FORMATION_ISSUE_DUPLICATE",
    "FORMATION_ISSUE_UNDECLARED",
    "FORMATION_PROFILE_DRIFT",
    "FORMATION_RESOLVER_FAILED",
    "FORMATION_RESOLVER_RESULT_INVALID",
    "FORMATION_RULE_SET_FAILED",
    "FORMATION_RULE_SET_RESULT_INVALID",
    "FormationContractCode",
    "FormationContractError",
    "MetamodelValidationError",
]

type FormationContractCode = str
"""A stable ``formation-*`` token naming one implementation-contract boundary."""

FORMATION_PROFILE_DRIFT: Final[FormationContractCode] = "formation-profile-drift"
"""The profile does not match the manifest, or reading a contributor's own
contract raised. The residual code: a mismatch a more specific code below names
is reported under that code instead."""

FORMATION_ISSUE_CODE_INVALID: Final[FormationContractCode] = "formation-issue-code-invalid"
"""A declared or emitted Issue Code is malformed or carries a foreign owner's
stem. Concerns the code's spelling only; a well-formed owner-local code that the
owner never declared is ``formation-issue-undeclared``."""

FORMATION_ISSUE_UNDECLARED: Final[FormationContractCode] = "formation-issue-undeclared"
"""An emitter produced a well-formed code of its own that is outside the complete
set its manifest row declares."""

FORMATION_ISSUE_DUPLICATE: Final[FormationContractCode] = "formation-issue-duplicate"
"""Two emitted issues share one ``(code, location, related)`` identity, whether
from one emitter or two. Aggregation never silently collapses them."""

FORMATION_FACET_MISSING: Final[FormationContractCode] = "formation-facet-missing"
"""A required facet key has no compiler: the profile supplies none for a manifest
row, or a row requires a key no row compiles."""

FORMATION_FACET_DUPLICATE: Final[FormationContractCode] = "formation-facet-duplicate"
"""One facet key is installed by more than one supplied compiler. A compiler
installing a key another module owns is drift, not this."""

FORMATION_RESOLVER_FAILED: Final[FormationContractCode] = "formation-resolver-failed"
"""The fixed resolver raised instead of returning a resolution result."""

FORMATION_RESOLVER_RESULT_INVALID: Final[FormationContractCode] = (
    "formation-resolver-result-invalid"
)
"""The fixed resolver returned something outside its closed result type: not a
resolution result, a rejection whose issues are empty or mutable, or a resolution
whose candidate is not a Candidate Metamodel."""

FORMATION_RULE_SET_FAILED: Final[FormationContractCode] = "formation-rule-set-failed"
"""A Rule Set raised instead of returning its issue sequence."""

FORMATION_RULE_SET_RESULT_INVALID: Final[FormationContractCode] = (
    "formation-rule-set-result-invalid"
)
"""A Rule Set returned a mutable collection or an element that is not a Metamodel
Issue. An issue it had no right to emit is an issue-code failure instead."""

FORMATION_COMPILER_FAILED: Final[FormationContractCode] = "formation-compiler-failed"
"""The Metadata Compiler or a Model Compiler raised, reached an impossible state,
or returned a value that is not the facet or metadata it promised. Compilation
runs only on an accepted candidate, so nothing here is ever a model issue."""

FORMATION_CONTRACT_CODES: Final[frozenset[FormationContractCode]] = frozenset(
    {
        FORMATION_PROFILE_DRIFT,
        FORMATION_ISSUE_CODE_INVALID,
        FORMATION_ISSUE_UNDECLARED,
        FORMATION_ISSUE_DUPLICATE,
        FORMATION_FACET_MISSING,
        FORMATION_FACET_DUPLICATE,
        FORMATION_RESOLVER_FAILED,
        FORMATION_RESOLVER_RESULT_INVALID,
        FORMATION_RULE_SET_FAILED,
        FORMATION_RULE_SET_RESULT_INVALID,
        FORMATION_COMPILER_FAILED,
    }
)
"""The closed contract-failure vocabulary. Every raise names one of these."""


class MetamodelValidationError(ValueError):
    """The supplied model is invalid, reported as every issue that makes it so.

    ``issues`` is nonempty and canonically ordered, so two runs over the same
    model produce the same report regardless of frontend, rule, profile, or
    scheduling order. Constructing one with no issue raises :class:`ValueError`:
    a validation failure that names no defect is not a report.
    """

    issues: tuple[MetamodelIssue, ...]

    def __init__(self, issues: Sequence[MetamodelIssue]) -> None:
        reported = tuple(issues)
        if not reported:
            raise ValueError("a Metamodel validation failure reports at least one issue")
        self.issues = reported
        summary = ", ".join(sorted({issue.code for issue in reported}))
        super().__init__(f"{len(reported)} model issue(s): {summary}")


class FormationContractError(RuntimeError):
    """A contributor, Formation Profile, or Formation Manifest broke its contract.

    ``owner`` names the responsible module where one is identifiable, and
    ``cause`` retains the original exception when the failure was a contributor
    raising rather than returning; that exception is also chained natively. This
    is never a statement about the model under formation.
    """

    code: FormationContractCode
    owner: ModuleIdentity | None
    cause: BaseException | None

    def __init__(
        self,
        code: FormationContractCode,
        message: str,
        *,
        owner: ModuleIdentity | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.code = code
        self.owner = owner
        self.cause = cause
        responsible = "" if owner is None else f" [{owner}]"
        super().__init__(f"{code}{responsible}: {message}")
