from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from parallax.core._stored_data import RESULT_DATA_INVALID, InvalidData, InvalidDataError
from parallax.core.internal.metamodel import (
    AttributeIdentity,
    MemberIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.internal.read_delivery._page._rows import StoredDataIssueInput

__all__ = [
    "STORED_DATA_DECODING_FAILED",
    "invalid_result_refusal",
    "member_spelling",
    "undecodable_data_refusal",
]


def invalid_result_refusal(
    invalid_data: Iterable[InvalidData[object]], *, edition: str
) -> InvalidDataError:
    """A result accessor's refusal of ``invalid_data``, read under ``edition``."""
    records = tuple(invalid_data)
    codes = sorted({issue.code for record in records for issue in record.issues})
    return InvalidDataError(
        RESULT_DATA_INVALID,
        f"{len(records)} result root(s) hold invalid stored data ({', '.join(codes)})",
        invalid_data=records,
        edition=edition,
    )


STORED_DATA_DECODING_FAILED: Final = "stored-data-decoding-failed"
"""The code of a stored-data refusal that interrupts an atomic operation."""


def undecodable_data_refusal(issue: StoredDataIssueInput) -> InvalidDataError:
    """The refusal ``issue`` raises where invalid stored data cannot travel in
    band: atomic publication and evidence acquisition both refuse the first
    issue they reach, and have no result to report it in."""
    where = "" if issue.member is None else f" at {member_spelling(issue.member)}"
    return InvalidDataError(
        STORED_DATA_DECODING_FAILED,
        f"{issue.entity.canonical} holds invalid stored data{where} ({issue.code})",
    )


def member_spelling(member: MemberIdentity) -> str:
    """``member``'s dotted name within its Entity."""
    match member:
        case AttributeIdentity(name=name):
            return name
        case ValueObjectIdentity(path=path):
            return ".".join(path)
        case ValueObjectAttributeIdentity(value_object=occurrence, name=name):
            return ".".join((*occurrence.path, name))
