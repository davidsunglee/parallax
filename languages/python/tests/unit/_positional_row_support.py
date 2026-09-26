"""The positional row a resolving read materializes over a ``MemberShape``,
built from a keyed document.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from parallax.core.metamodel import DocumentMember, Leaf, MemberShape, Multiplicity

__all__ = ["positional_row"]


def positional_row(
    shape: MemberShape, members: Mapping[str, object], *, absent: object
) -> tuple[object, ...]:
    """``members`` positional over ``shape``: a member it does not name is
    ``absent``, and each occurrence is positional over its own shape."""
    return tuple(
        _cell(member, members[member.name], absent) if member.name in members else absent
        for member in shape.members
    )


def _cell(member: DocumentMember, value: object, absent: object) -> object:
    if isinstance(member, Leaf) or value is None or value is absent:
        return value
    if member.multiplicity is Multiplicity.MANY:
        return tuple(
            positional_row(member.shape, cast("Mapping[str, object]", element), absent=absent)
            for element in cast("Sequence[object]", value)
        )
    return positional_row(member.shape, cast("Mapping[str, object]", value), absent=absent)
