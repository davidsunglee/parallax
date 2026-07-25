"""The raw-descriptor inheritance-family walk and invariant validator.

Every production frontend forms a descriptor into an accepted Metamodel before
asking any inheritance-family question, and answers it through the formed
model's Inheritance Facet (`parallax.core.inheritance.view`). This module is
the one exception: the corpus `rejected` grading path (`engine.run_rejected_case`)
must classify an inline `when.model` document that is EXPECTED to never form —
the descriptor documents `core/compatibility/cases/m-inheritance-*-rejected-*.yaml`
encode a malformed family on purpose, so grading it needs a validator that
walks the raw descriptor record graph directly, before and independently of
formation. The engine's other descriptor-level family reads (the version
column's declaring entity, the family-effective primary key for object-key
derivation, the default conflict/rejected target) share the same raw-descriptor
vocabulary and live here for the same reason: none of them can wait for a
model that may never form.
"""

from __future__ import annotations

from dataclasses import dataclass

from parallax.core.descriptor import (
    Attribute,
    Entity,
    Inheritance,
    Metamodel,
    family_root_name,
)
from parallax.core.inheritance import InheritanceError

__all__ = ["Family", "family_attributes", "family_of", "family_primary_key", "validate"]


@dataclass(frozen=True, slots=True)
class Family:
    """The inheritance participants of one descriptor, and its root if it has
    exactly one. Structural traversal below a position belongs to the descriptor
    scope (:func:`~parallax.core.descriptor.concrete_descendant_names`), not
    here."""

    participants: tuple[Entity, ...]
    root: Entity | None

    @property
    def strategy(self) -> str | None:
        """The family mapping strategy declared by its root (``None`` if no root)."""
        if self.root is None:
            return None
        return _inh(self.root).strategy


def _inh(entity: Entity) -> Inheritance:
    if entity.inheritance is None:  # pragma: no cover - callers guard on participation
        raise ValueError(f"{entity.name} is not an inheritance participant")
    return entity.inheritance


def _participants(metamodel: Metamodel) -> tuple[Entity, ...]:
    return tuple(entity for entity in metamodel.entities if entity.inheritance is not None)


def family_of(metamodel: Metamodel) -> Family:
    """The inheritance :class:`Family` of ``metamodel`` (empty when none participate).

    ``root`` is named only when the descriptor declares exactly one: a
    descriptor carrying several independent families (or none at all) has no
    single root to name, so ``root`` is ``None``.
    """
    participants = _participants(metamodel)
    roots = [entity for entity in participants if _inh(entity).role == "root"]
    root = roots[0] if len(roots) == 1 else None
    return Family(participants=participants, root=root)


def family_attributes(meta: Metamodel, entity: Entity) -> tuple[Attribute, ...]:
    """Every attribute declared anywhere in ``entity``'s inheritance family.

    Assumes attribute names are unique within one family (the shared-table /
    ancestry-derived column set is a disjoint union, m-inheritance).
    """
    root_name = family_root_name(meta, entity)
    if root_name is None:
        return entity.attributes
    attrs: list[Attribute] = []
    for candidate in meta.entities:
        if candidate.inheritance is not None and family_root_name(meta, candidate) == root_name:
            attrs.extend(candidate.attributes)
    return tuple(attrs)


def family_primary_key(meta: Metamodel, entity: Entity) -> tuple[Attribute, ...]:
    """``entity``'s FAMILY-EFFECTIVE primary key (m-inheritance "Inherited
    members"): declared on the root alone and inherited unchanged by every
    abstract and concrete descendant. ``Entity.primary_key`` is a bare LOCAL
    view (``self.attributes`` filtered): for a concrete subtype whose key is
    declared on an ancestor (every corpus family), that view is wrongly EMPTY,
    which would silently make a keyed write / observation / coalescing lookup
    unidentifiable. Composes with :func:`family_attributes` rather than
    re-deriving the family walk.
    """
    return tuple(attr for attr in family_attributes(meta, entity) if attr.primary_key)


def validate(metamodel: Metamodel) -> None:
    """Validate every inheritance family invariant, raising :class:`InheritanceError`.

    The check order pins each corpus ``rejectedRule``: parent resolution,
    acyclicity, strategy and family-owned-fact locality, ancestry-reaches-a-root,
    missing-root detection, then the selected strategy's table/tag formation
    rules. The last three are asked once per independent family, so a descriptor
    declaring several never has one family's root or strategy answer for another.
    """
    participants = _participants(metamodel)
    if not participants:
        return
    by_name = {entity.name: entity for entity in metamodel.entities}

    _reject_unknown_parent(participants, by_name)
    _reject_cycles(participants)
    _reject_strategy_redeclared(participants)
    _reject_descendant_temporal_axes(participants)
    _reject_descendant_optimistic_locking(participants)
    _reject_concrete_without_root(participants, by_name)
    rooted = [
        (_reject_missing_root(root, members), members)
        for root, members in _families(participants, by_name)
    ]
    for root, members in rooted:
        _reject_strategy_storage(root, members)
    for root, members in rooted:
        _reject_tph_tag_values(root, members)


def _families(
    participants: tuple[Entity, ...], by_name: dict[str, Entity]
) -> list[tuple[Entity | None, tuple[Entity, ...]]]:
    """Each independent inheritance family of ``participants``: the topmost
    position its members' parent links reach (``None`` when that position is not
    a root), paired with the members themselves in declaration order.

    A position has at most one parent, so two roots can never share an ancestry
    and every participant belongs to exactly one family. Valid only once unknown
    parents and cycles are rejected: either would leave the upward walk without
    a terminating top.
    """
    grouped: dict[str, list[Entity]] = {}
    for entity in participants:
        grouped.setdefault(_family_top(entity, by_name).name, []).append(entity)
    families: list[tuple[Entity | None, tuple[Entity, ...]]] = []
    for name, members in grouped.items():
        top = by_name[name]
        families.append((top if _inh(top).role == "root" else None, tuple(members)))
    return families


def _family_top(entity: Entity, by_name: dict[str, Entity]) -> Entity:
    """The highest participant ``entity``'s parent links reach — itself when it
    declares no parent, and the last participant on the chain when the chain
    leaves the family (a parent that declares no inheritance of its own)."""
    top = entity
    while True:
        parent = _inh(top).parent
        if parent is None:
            return top
        ancestor = by_name.get(parent)
        if ancestor is None or ancestor.inheritance is None:
            return top
        top = ancestor


def _reject_unknown_parent(participants: tuple[Entity, ...], by_name: dict[str, Entity]) -> None:
    for entity in participants:
        parent = _inh(entity).parent
        if parent is not None and parent not in by_name:
            raise InheritanceError(
                "inheritance-unknown-parent",
                f"{entity.name} names parent {parent!r}, which the descriptor does not declare",
                entity=entity.name,
            )


def _reject_cycles(participants: tuple[Entity, ...]) -> None:
    by_name = {entity.name: entity for entity in participants}
    for start in participants:
        seen: set[str] = set()
        current: str | None = start.name
        while current is not None and current in by_name:
            if current in seen:
                raise InheritanceError(
                    "inheritance-cycle",
                    f"parent links form a cycle through {current!r}",
                    entity=current,
                )
            seen.add(current)
            current = _inh(by_name[current]).parent


def _reject_strategy_redeclared(participants: tuple[Entity, ...]) -> None:
    for entity in participants:
        inh = _inh(entity)
        if inh.role != "root" and inh.strategy is not None:
            raise InheritanceError(
                "inheritance-strategy-redeclared",
                f"non-root {entity.name} redeclares the family strategy",
                entity=entity.name,
            )


def _reject_descendant_temporal_axes(participants: tuple[Entity, ...]) -> None:
    """Reject any ``abstract-subtype`` or ``concrete-subtype`` that declares its
    own ``asOfAttributes``.

    Temporality is a family-wide property: only the family ROOT may declare
    as-of axes, and every descendant inherits exactly that set (never
    redeclares, adds, removes, overrides, or shadows an axis) — regardless of
    whether the root itself is temporal. A non-temporal root with a temporal
    descendant would leave the family's root-owned coordinate system
    ill-defined (mixed temporality is not supported); a temporal root whose
    descendant redeclares or adds an axis would make the descendant's own
    temporal profile diverge from the family it belongs to. Both shapes are
    rejected here, uniformly, before any SQL.
    """
    for entity in participants:
        if _inh(entity).role != "root" and entity.as_of_axes:
            raise InheritanceError(
                "inheritance-temporal-axes-not-root-owned",
                f"non-root {entity.name} declares its own as-of axes; temporal axes are a "
                "family-wide property and MUST be declared only on the root",
                entity=entity.name,
            )


def _reject_descendant_optimistic_locking(participants: tuple[Entity, ...]) -> None:
    """Reject any ``abstract-subtype`` or ``concrete-subtype`` that declares its
    own ``optimisticLocking`` attribute.

    The version attribute is a family-wide property (ADR 0027): only the
    family ROOT may declare it, and every descendant inherits exactly that
    column — regardless of whether the root itself is versioned. This is
    structural per-entity (it does not need to look at the root's own
    attributes), so it fires uniformly for both malformed shapes: a
    non-versioned root with a version-declaring descendant, and a versioned
    root whose descendant redeclares or adds a second version attribute.
    """
    for entity in participants:
        if _inh(entity).role == "root":
            continue
        if any(attribute.optimistic_locking for attribute in entity.attributes):
            raise InheritanceError(
                "inheritance-optimistic-locking-not-root-owned",
                f"non-root {entity.name} declares its own optimisticLocking attribute; "
                "the version attribute is family-wide and MUST be declared only on the "
                "root",
                entity=entity.name,
            )


def _reject_concrete_without_root(
    participants: tuple[Entity, ...], by_name: dict[str, Entity]
) -> None:
    for entity in participants:
        if _inh(entity).role != "concrete-subtype":
            continue
        current: str | None = entity.name
        reached_root = False
        while current is not None:
            node = by_name.get(current)
            if node is None or node.inheritance is None:
                break
            if node.inheritance.role == "root":
                reached_root = True
                break
            current = node.inheritance.parent
        if not reached_root:
            raise InheritanceError(
                "inheritance-concrete-without-abstract-root",
                f"concrete subtype {entity.name} has no abstract root ancestor",
                entity=entity.name,
            )


def _reject_missing_root(root: Entity | None, members: tuple[Entity, ...]) -> Entity:
    """``root`` itself once it is one, so a family that reaches no root is
    rejected here rather than surfacing as a missing strategy downstream."""
    if root is None:
        raise InheritanceError(
            "inheritance-missing-root",
            f"inheritance participants {sorted(member.name for member in members)} declare no root",
        )
    return root


def _reject_strategy_storage(root: Entity, participants: tuple[Entity, ...]) -> None:
    strategy = _inh(root).strategy
    if strategy == "table-per-hierarchy":
        if root.table is None:
            raise InheritanceError(
                "inheritance-tph-root-table-required",
                f"table-per-hierarchy root {root.name} declares no shared table",
                entity=root.name,
            )
        for entity in participants:
            if entity is not root and entity.table is not None:
                raise InheritanceError(
                    "inheritance-tph-descendant-table-forbidden",
                    f"table-per-hierarchy descendant {entity.name} repeats the root-owned "
                    "shared table",
                    entity=entity.name,
                )
        return

    if strategy != "table-per-concrete-subtype":
        return
    for entity in participants:
        role = _inh(entity).role
        if role in ("root", "abstract-subtype") and entity.table is not None:
            raise InheritanceError(
                "inheritance-tpcs-abstract-table-forbidden",
                f"table-per-concrete-subtype abstract position {entity.name} declares a table",
                entity=entity.name,
            )
        if role == "concrete-subtype" and entity.table is None:
            raise InheritanceError(
                "inheritance-tpcs-concrete-table-required",
                f"table-per-concrete-subtype concrete {entity.name} declares no table",
                entity=entity.name,
            )
    if _inh(root).tag_column is not None:
        raise InheritanceError(
            "inheritance-tag-on-concrete-subtype-strategy",
            f"table-per-concrete-subtype root {root.name} declares a tag column",
            entity=root.name,
        )
    for entity in participants:
        if _inh(entity).tag_value is not None:
            raise InheritanceError(
                "inheritance-tag-on-concrete-subtype-strategy",
                f"table-per-concrete-subtype subtype {entity.name} declares a tagValue",
                entity=entity.name,
            )


def _reject_tph_tag_values(root: Entity, participants: tuple[Entity, ...]) -> None:
    if _inh(root).strategy != "table-per-hierarchy":
        return
    concretes = [entity for entity in participants if _inh(entity).role == "concrete-subtype"]
    seen_values: dict[str, str] = {}
    for entity in concretes:
        tag_value = _inh(entity).tag_value
        if tag_value is None:
            raise InheritanceError(
                "inheritance-missing-tag-value",
                f"table-per-hierarchy concrete subtype {entity.name} declares no tagValue",
                entity=entity.name,
            )
        if tag_value in seen_values:
            raise InheritanceError(
                "inheritance-duplicate-tag-value",
                f"tagValue {tag_value!r} is shared by {seen_values[tag_value]} and {entity.name}",
                entity=entity.name,
            )
        seen_values[tag_value] = entity.name
