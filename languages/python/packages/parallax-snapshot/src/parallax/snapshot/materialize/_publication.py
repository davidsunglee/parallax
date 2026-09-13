"""The single refusal boundary for publishing issue-bearing read results."""

from __future__ import annotations

from typing import Final

from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.snapshot.materialize._page import StoredDataIssueInput
from parallax.snapshot.materialize._root import RootView

SNAPSHOT_DECODING_FAILED: Final[str] = "snapshot-decoding-failed"
"""The stable code used when classified stored data reaches publication."""


class SnapshotDecodingError(ValueError):
    """A classified stored-data issue that prevents atomic result publication."""

    code: Final[str] = SNAPSHOT_DECODING_FAILED

    def __init__(
        self,
        message: str,
        *,
        entity: EntityIdentity,
        member: AttributeIdentity | ValueObjectIdentity | ValueObjectAttributeIdentity | None,
    ) -> None:
        super().__init__(f"{SNAPSHOT_DECODING_FAILED}: {message}")
        self.message = message
        self.entity = entity
        self.member = member


def publication_issue(root_view: RootView) -> StoredDataIssueInput | None:
    """The first issue reachable from a requested root, in deterministic Root View order."""
    if root_view.invalid_roots:
        return root_view.invalid_roots[0].issues[0]
    if not root_view.has_issues:
        return None
    for index in range(len(root_view.order)):
        issues = root_view.issues(index)
        if issues:
            return issues[0]
    raise AssertionError("an issue-bearing Root View has no reachable issue")  # pragma: no cover


def require_publishable(root_view: RootView) -> None:
    """Refuse an issue-bearing Root View before identity or object derivation."""
    issue = publication_issue(root_view)
    if issue is not None:
        raise SnapshotDecodingError(
            f"{issue.entity.canonical} holds invalid stored data ({issue.code})",
            entity=issue.entity,
            member=issue.member,
        )
