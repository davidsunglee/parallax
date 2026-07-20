"""``parallax.snapshot.handle._family`` — the shared family-descriptor leaf.

Every question of the form "what shape does this entity's FAMILY declare?"
answers here: the temporal axes (:func:`processing_axis` / :func:`business_axis`),
the optimistic-lock version attribute (:func:`version_attribute`), and the
writable member-to-column map (:func:`members`), plus the small
``Class.member`` reference split (:func:`assignment_member`) that resolves an
authored assignment against those members.

This is the package's bottom leaf: it imports no other handle module, so every
write-side module (`_keyed_sql`, `_write_lowering`, `_write_inputs`,
`_transaction`, `_predicate_writes`) may import it freely without any risk of a
cycle. Each helper is read from at least two of those, which is precisely why
the module exists — an inheritance participant declares its as-of axes and its
version column on the family ROOT alone (ADR 0026 / ADR 0027), so the lowering
side and the verb-input side must resolve them the SAME way or they disagree
about the shape of the row they are writing.

Every name here is spelled bare: privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, not by per-name underscores
(an underscored name imported across a module boundary is a Pyright strict
``reportPrivateUsage`` error, and this leaf exists only to be imported).
Mirrors :mod:`parallax.core.entity._annotations`.
"""

from __future__ import annotations

from parallax.core import inheritance
from parallax.core.descriptor import AsOfAttribute, Attribute, Entity, Metamodel

__all__ = [
    "assignment_member",
    "business_axis",
    "members",
    "processing_axis",
    "version_attribute",
]


def processing_axis(declaring: Entity) -> AsOfAttribute:
    return next(aoa for aoa in declaring.as_of_attributes if aoa.axis == "processing")


def business_axis(declaring: Entity) -> AsOfAttribute:
    return next(aoa for aoa in declaring.as_of_attributes if aoa.axis == "business")


def version_attribute(declaring: Entity) -> Attribute | None:
    """``declaring``'s own ``optimisticLocking`` version attribute, if any.

    ``declaring`` is already the FAMILY-EFFECTIVE declaring entity (the root for
    an inheritance participant, `inheritance.declaring_entity` — the version
    column is family-wide metadata declared only there, `m-opt-lock` "The
    version column"; ADR 0027), so a plain local scan of its own attributes is
    correct without a further family walk.
    """
    return next((attr for attr in declaring.attributes if attr.optimistic_locking), None)


def assignment_member(attr: str) -> str:
    """The declared member name of an assignment's ``Class.member`` reference."""
    _, _, member = attr.partition(".")
    return member


def members(meta: Metamodel, entity: Entity) -> dict[str, tuple[str, bool]]:
    """Map each writable member name to `(column, is_value_object)`, FAMILY-WIDE
    (`inheritance.family_attributes` / `.superset_value_objects` — both already
    degrade to ``entity``'s own declarations for a non-participant)."""
    resolved: dict[str, tuple[str, bool]] = {
        attr.name: (attr.column, False) for attr in inheritance.family_attributes(meta, entity)
    }
    for value_object in inheritance.superset_value_objects(meta, (entity.name,)):
        resolved[value_object.name] = (value_object.column, True)
    return resolved
