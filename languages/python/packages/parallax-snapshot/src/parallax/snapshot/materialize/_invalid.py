"""The in-band invalid-result surface a classified read publishes (m-snapshot-read).

A result element is ``T | InvalidData[T]``: a root whose whole requested include
tree conforms is delivered as itself, and a root some stored state contradicted
is delivered as the record here. Classification is root-granular — an issue
anywhere in a root's requested include tree makes that root invalid — so nothing
below a root is ever pruned or unioned.

The record carries diagnoses and positions, never authority: no raw stored value,
no decoding cause, no mutable details, and no observation address. Its locators
answer *which* result element is invalid, not what a caller may then write.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from parallax.core.metamodel import EntityIdentity, MemberIdentity
from parallax.core.temporal_read import Edge
from parallax.core.unit_work import ObjectKey
from parallax.snapshot.materialize._input import StoredDataIssueCode

__all__ = ["InvalidData", "InvalidDataError", "StoredDataIssue"]


@dataclass(frozen=True, slots=True)
class StoredDataIssue:
    """One stored state that contradicts the model, as the public diagnosis of it.

    ``entity`` is the concrete Entity the violation was judged against, which for
    an unresolved family tag is the queried family root — the only case with no
    ``member``, because a discriminator is no declared domain member.

    ``object_key`` names the affected root or included Entity and is absent
    exactly where no identity decoded: an invalid primary key, or a family tag
    naming no concrete subtype. It is deliberately unlike
    :attr:`InvalidData.object_key`, which always names the RESULT root: reaching
    one included Entity from several roots repeats this diagnosis in each root's
    record while identifying the same affected object.
    """

    code: StoredDataIssueCode
    entity: EntityIdentity
    member: MemberIdentity | None = None
    object_key: ObjectKey | None = None


@dataclass(frozen=True, slots=True)
class InvalidData[T]:
    """One result root some stored state contradicted, in the position it occupied.

    ``data`` is the complete hydrated root wherever every value could be produced
    without inventing one, and ``None`` where it could not — a leaf outside its
    declared type, a non-nullable Attribute holding SQL NULL, an unknown family
    tag, or an undecodable primary key. Hydration never repairs: a caller may
    author a corrective write from a hydrated root, and Parallax authors none.

    ``issues`` is unordered because a diagnosis is a fact rather than a sequence:
    reaching one affected object through several include paths does not duplicate
    it, and two identical diagnoses whose affected object cannot be identified
    collapse because nothing distinguishes them. Human-readable formatting sorts
    codes for presentation only.

    ``object_key`` identifies this result root across its states when its primary
    key decoded; ``version`` is present for a decoded explicitly versioned root
    and ``edge`` for a decoded temporal one, so the two never appear together.
    ``ordinal`` is always this element's zero-based position in the ordered
    result, including when the other locators are available.
    """

    issues: frozenset[StoredDataIssue]
    data: T | None
    object_key: ObjectKey | None
    version: int | None
    edge: Edge | None
    ordinal: int


class InvalidDataError(RuntimeError):
    """A default accessor's refusal of a result carrying invalid stored data.

    :attr:`invalid_data` is nonempty, in result order, and is the exception's
    sole machine-readable report: there is no singular code, no flattened issue
    collection, no cause, and no second name for the same tuple. The message
    derives its count and issue-code summary from that tuple rather than being
    supplied beside it, so there is no second authority to keep in step.
    """

    invalid_data: tuple[InvalidData[object], ...]

    def __init__(self, invalid_data: Iterable[InvalidData[object]]) -> None:
        records = tuple(invalid_data)
        if not records:
            raise ValueError("an invalid-data refusal carries at least one record")
        codes = sorted({issue.code for record in records for issue in record.issues})
        super().__init__(
            f"{len(records)} result root(s) hold invalid stored data ({', '.join(codes)})"
        )
        self.invalid_data = records
