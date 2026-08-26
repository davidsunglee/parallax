"""The core both edit surfaces are built from (spec §3).

``Entity.edit(**changes)`` and ``ValueObject.edit(**changes)`` derive an edited
copy the same way: every authored name is resolved against the declaring class,
every resolved member's value is judged by the one shared assignment judgement,
and the value is rebuilt with everything the caller did not author carried
forward. Only the resolution differs — what a name may resolve to, and where a
refusal locates — so each frontend owns that alone and neither carries a second
copy of the rest.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Final

from parallax.core.entity._errors import EditError, EditViolation
from parallax.core.entity._instance_state import named_state

if TYPE_CHECKING:
    from collections.abc import Container

    from pydantic import BaseModel

    from parallax.core.metamodel import ModelLocation

__all__ = [
    "partition_declared",
    "unresolved_member_violation",
    "use_edit",
]

_UNBOUND: Final = object()
"""Distinguishes a class that binds a name to ``None`` from one that binds it not
at all."""


def _is_derived_cache(cls: type, key: str) -> bool:
    """Whether ``cls`` declares the instance slot ``key`` a derived cache.

    A ``functools.cached_property`` memoizes an answer computed from the value it
    was read through, so the class itself declares that slot derived and the rule
    needs no registry. The first ancestor that binds the name decides, exactly as
    attribute lookup would, so a subtype that rebinds the name to something else
    is not taken to have inherited the declaration.
    """
    for ancestor in cls.__mro__:
        attribute = ancestor.__dict__.get(key, _UNBOUND)
        if attribute is not _UNBOUND:
            return isinstance(attribute, functools.cached_property)
    return False


def partition_declared(
    value: BaseModel, declared: Container[str]
) -> tuple[dict[str, object], dict[str, object]]:
    """``value``'s declared member state and everything an edit carries, split.

    An edit replaces the first half and preserves the second unchanged, which is
    what keeps a materialized node's relationship views readable on the copy it
    derives. The second half is a complement rather than an enumerated key list,
    so a new kind of instance state travels correctly without either caller
    learning its name.

    That complement reaches what a value holds under a NAME and nothing else, so
    it is one of the two parts an edit carries. The object layout holds the
    other, and
    :func:`~parallax.core.entity._instance_state.carry_slots_beside_state` is
    where every slot of it travels: the container slots Pydantic keeps private
    attributes and extra fields in, and the lifecycle slot a materialized Entity
    holds the record of its own read in. No key of this mapping names any of
    them.

    A derived cache is the one thing that complement drops: a slot the class
    declares a ``functools.cached_property`` (:func:`_is_derived_cache`) holds an
    answer computed from declared state an edit may replace, so it is left out
    and recomputed on next access rather than carried into a copy whose own
    declared state contradicts it. That reads a declaration, so it reaches only
    names a declaration may author: the framework's own ``__parallax_`` prefix is
    reserved from every class body, which is what keeps a Change Record outside
    anything a class can declare derived.

    Both halves are read through the backing
    (:func:`~parallax.core.entity._instance_state.named_state`) rather than
    through an attribute lookup for ``__dict__``, so a class body answering that
    lookup with ``__getattribute__`` can neither drop the relationship views a
    copy must carry forward nor invent a Change Record the value never earned —
    and a
    published value is partitioned out of its row, its loaded relationship tails,
    and its author-owned state, so editing one neither loses what those hold nor
    creates the instance dictionary it exists without.

    Every branch of both edit surfaces partitions here, so none of them can hold
    its own opinion of the boundary.
    """
    declared_state: dict[str, object] = {}
    carried: dict[str, object] = {}
    for key, member in named_state(value).items():
        if key in declared:
            declared_state[key] = member
        elif not _is_derived_cache(type(value), key):
            carried[key] = member
    return declared_state, carried


def unresolved_member_violation(
    authored: str, *, owner: str, location: ModelLocation
) -> EditViolation:
    """The refusal of an authored name that reached no declared member.

    A dotted name is refused as what it is rather than as an unknown one: it
    spells a path below a member's own boundary, and an edit assigns whole
    members — a Value Object binds its whole document, so there is no sparse
    write beneath an occurrence through this door either. Every other unresolved
    name is simply one the declaration does not carry.

    Both locate at the declaration that was searched and carry the name as
    authored, because a member location would have to name a member that
    declaration does not declare.
    """
    if "." in authored:
        return EditViolation(
            code="edit-nested-path",
            location=location,
            member_name=authored,
            message=(
                f"{owner}.{authored}: only a whole declared member is assignable via "
                "edit(...) — a value object binds its whole document, never a nested path "
                "(m-value-object)"
            ),
        )
    return EditViolation(
        code="edit-unknown-member",
        location=location,
        member_name=authored,
        message=f"{owner}.{authored}: unknown member name",
    )


def use_edit(cls_name: str, door: str, *, location: ModelLocation, remedy: str) -> EditError:
    """The refusal of an inherited copy path (spec §3).

    It examines no argument and names no member, so it carries no member name and
    locates wherever the refusing class's own violations locate. ``remedy`` is the
    clause naming why ``edit`` is the one door, which differs by surface: an
    Entity's copy door would forge provenance, and a Value Object's would skip
    validation.
    """
    return EditError(
        [
            EditViolation(
                code="edit-use-edit",
                location=location,
                message=f"{cls_name}.{door}(...) creates no value: {remedy}",
            )
        ]
    )
