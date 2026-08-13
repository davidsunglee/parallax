"""The single refusal boundary for publishing issue-bearing read results."""

from __future__ import annotations

from typing import Final

from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.snapshot.materialize._input import StoredDataIssueInput
from parallax.snapshot.materialize._merge import GraphMerge

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


def publication_issue(merge: GraphMerge) -> StoredDataIssueInput | None:
    """The first issue reachable from a requested root, in deterministic graph order."""
    if merge.invalid_roots:
        return merge.invalid_roots[0].issues[0]
    if not merge.has_issues:
        return None
    for index in range(len(merge.order)):
        node = merge.node(index)
        if node.issues:
            return node.issues[0]
    raise AssertionError("an issue-bearing graph merge has no reachable issue")  # pragma: no cover


def require_publishable(merge: GraphMerge) -> None:
    """Refuse an issue-bearing reachable graph before identity or object derivation."""
    issue = publication_issue(merge)
    if issue is not None:
        raise SnapshotDecodingError(
            f"{issue.entity.canonical} holds invalid stored data ({issue.code})",
            entity=issue.entity,
            member=issue.member,
        )
