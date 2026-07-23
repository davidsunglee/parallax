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
FORMATION_ISSUE_CODE_INVALID: Final[FormationContractCode] = "formation-issue-code-invalid"
FORMATION_ISSUE_UNDECLARED: Final[FormationContractCode] = "formation-issue-undeclared"
FORMATION_ISSUE_DUPLICATE: Final[FormationContractCode] = "formation-issue-duplicate"
FORMATION_FACET_MISSING: Final[FormationContractCode] = "formation-facet-missing"
FORMATION_FACET_DUPLICATE: Final[FormationContractCode] = "formation-facet-duplicate"
FORMATION_RESOLVER_FAILED: Final[FormationContractCode] = "formation-resolver-failed"
FORMATION_RESOLVER_RESULT_INVALID: Final[FormationContractCode] = (
    "formation-resolver-result-invalid"
)
FORMATION_RULE_SET_FAILED: Final[FormationContractCode] = "formation-rule-set-failed"
FORMATION_RULE_SET_RESULT_INVALID: Final[FormationContractCode] = (
    "formation-rule-set-result-invalid"
)
FORMATION_COMPILER_FAILED: Final[FormationContractCode] = "formation-compiler-failed"

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
