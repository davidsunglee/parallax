"""Closed-tree inheritance family resolution + semantic validation (m-inheritance).

A metamodel entity MAY declare an ``inheritance`` block placing it in a closed
class tree: exactly one abstract ``root`` (which alone declares the family
``strategy``), zero or more ``abstract-subtype`` interior nodes, and the
instantiable, row-owning ``concrete-subtype`` leaves. Two strategies are admitted
(``table-per-hierarchy`` — one shared table discriminated by the root's ``tag``
column carrying each concrete subtype's ``tagValue``; ``table-per-concrete-subtype``
— each concrete subtype maps to its own table, no tag).

Per-entity structure is validated by ``metamodel.schema.json``; the genuinely
CROSS-ENTITY family invariants (parent resolution, acyclicity, single root,
concrete-under-abstract-root, family-wide ``tagValue`` uniqueness, shared-table
consistency, tag placement) are semantic and live here — the same non-normative
grading pattern the value-object resolvers follow, raising the shared
:class:`~reference_harness.value_object_resolve.RejectionError` with the violated
``then.rejectedRule``.

This module also owns the **effective definition** derivation: a concrete subtype
does not repeat inherited attributes, so the harness derives the full inherited
attribute chain (root -> ... -> self) plus, for ``table-per-hierarchy``, the
synthesized framework-owned tag column, presenting each concrete subtype as a
flattened entity the DDL / write-derivation / fixture-load paths consume unchanged.
Abstract nodes are tableless and rowless, so they are excluded from physical
provisioning.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from .value_object_resolve import RejectionError

if TYPE_CHECKING:
    from .case import Model

# --- role / strategy vocabulary --------------------------------------------

ROLE_ROOT = "root"
ROLE_ABSTRACT = "abstract-subtype"
ROLE_CONCRETE = "concrete-subtype"
ABSTRACT_ROLES = frozenset({ROLE_ROOT, ROLE_ABSTRACT})

STRATEGY_TPH = "table-per-hierarchy"
STRATEGY_TPCS = "table-per-concrete-subtype"

# The synthesized tag column carries short discriminator literals; a bounded
# string keeps the shared-table DDL a plain ``varchar`` (m-inheritance / m-sql).
_TAG_COLUMN_MAX_LENGTH = 32

# --- rule vocabulary (kept in lockstep with the compatibility-case schema) --

INHERITANCE_UNKNOWN_PARENT = "inheritance-unknown-parent"
INHERITANCE_CYCLE = "inheritance-cycle"
INHERITANCE_MISSING_ROOT = "inheritance-missing-root"
INHERITANCE_MULTIPLE_ROOTS = "inheritance-multiple-roots"
INHERITANCE_CONCRETE_WITHOUT_ABSTRACT_ROOT = "inheritance-concrete-without-abstract-root"
INHERITANCE_ABSTRACT_NODE_WITH_TABLE = "inheritance-abstract-node-with-table"
INHERITANCE_ABSTRACT_NODE_FIXTURE_ROWS = "inheritance-abstract-node-fixture-rows"
INHERITANCE_STRATEGY_REDECLARED = "inheritance-strategy-redeclared"
INHERITANCE_MISSING_TAG_VALUE = "inheritance-missing-tag-value"
INHERITANCE_DUPLICATE_TAG_VALUE = "inheritance-duplicate-tag-value"
INHERITANCE_INCONSISTENT_HIERARCHY_TABLE = "inheritance-inconsistent-hierarchy-table"
INHERITANCE_TAG_ON_CONCRETE_SUBTYPE_STRATEGY = "inheritance-tag-on-concrete-subtype-strategy"

MODEL_REJECTED_RULES: frozenset[str] = frozenset(
    {
        INHERITANCE_UNKNOWN_PARENT,
        INHERITANCE_CYCLE,
        INHERITANCE_MISSING_ROOT,
        INHERITANCE_MULTIPLE_ROOTS,
        INHERITANCE_CONCRETE_WITHOUT_ABSTRACT_ROOT,
        INHERITANCE_ABSTRACT_NODE_WITH_TABLE,
        INHERITANCE_ABSTRACT_NODE_FIXTURE_ROWS,
        INHERITANCE_STRATEGY_REDECLARED,
        INHERITANCE_MISSING_TAG_VALUE,
        INHERITANCE_DUPLICATE_TAG_VALUE,
        INHERITANCE_INCONSISTENT_HIERARCHY_TABLE,
        INHERITANCE_TAG_ON_CONCRETE_SUBTYPE_STRATEGY,
    }
)

# Operation-level rules (m-op-algebra x m-inheritance): a SCHEMA-VALID operation a
# model-aware validator MUST refuse pre-SQL because it narrows or references
# subtypes incompatibly with the polymorphic position it queries (Phase 4).
NARROW_OUTSIDE_POSITION = "narrow-outside-position"
NARROW_EMPTY_EFFECTIVE_SET = "narrow-empty-effective-set"
SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE = "subtype-attribute-outside-narrow-scope"

OPERATION_REJECTED_RULES: frozenset[str] = frozenset(
    {
        NARROW_OUTSIDE_POSITION,
        NARROW_EMPTY_EFFECTIVE_SET,
        SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE,
    }
)

# Attribute-bearing single-entity predicate tags (they all carry an `attr` ref) —
# the sites a concrete-subtype-attribute reference surfaces in a narrow walk.
_ATTR_BEARING_TAGS = frozenset(
    {
        "eq",
        "notEq",
        "greaterThan",
        "greaterThanEquals",
        "lessThan",
        "lessThanEquals",
        "between",
        "isNull",
        "isNotNull",
        "like",
        "notLike",
        "startsWith",
        "endsWith",
        "contains",
        "in",
        "notIn",
    }
)


# --- per-definition accessors ----------------------------------------------


def inheritance_of(definition: dict[str, Any]) -> dict[str, Any] | None:
    """The ``inheritance`` block of an entity definition, or ``None``."""
    block = definition.get("inheritance")
    return block if isinstance(block, dict) else None


def role_of(definition: dict[str, Any]) -> str | None:
    block = inheritance_of(definition)
    return block.get("role") if block else None


def parent_of(definition: dict[str, Any]) -> str | None:
    block = inheritance_of(definition)
    return block.get("parent") if block else None


def is_abstract(definition: dict[str, Any]) -> bool:
    """True for a tableless/rowless abstract node (``root`` / ``abstract-subtype``)."""
    return role_of(definition) in ABSTRACT_ROLES


def is_concrete(definition: dict[str, Any]) -> bool:
    """True for a row-owning entity: a concrete subtype OR a non-inheritance entity."""
    role = role_of(definition)
    return role is None or role == ROLE_CONCRETE


def tag_of(definition: dict[str, Any]) -> tuple[str, Any] | None:
    """The ``(column, value)`` a table-per-hierarchy INSERT writes for this entity.

    Reads the resolved inheritance block (a concrete subtype's flattened definition
    carries both the root's ``tag`` column and its own ``tagValue``); returns
    ``None`` for a table-per-concrete-subtype subtype or a non-inheritance entity.
    """
    block = inheritance_of(definition)
    if not block:
        return None
    tag = block.get("tag")
    value = block.get("tagValue")
    if not isinstance(tag, dict) or value is None:
        return None
    return tag["column"], value


# --- family resolution ------------------------------------------------------


class Family:
    """A read-only view of the inheritance participants in a descriptor.

    Built from the raw entity definitions (a list of dicts), so it is safe to run
    on an *invalid* inline family (a ``when.model`` rejected case) before any
    flattening — the walks are cycle-guarded.
    """

    def __init__(self, entity_defs: list[dict[str, Any]]) -> None:
        self.defs: dict[str, dict[str, Any]] = {
            d["name"]: d for d in entity_defs if isinstance(d, dict) and "name" in d
        }
        self.order: list[str] = [
            d["name"] for d in entity_defs if isinstance(d, dict) and "name" in d
        ]

    def children_of(self, name: str) -> list[str]:
        """Direct subtypes of *name*, in descriptor declaration order."""
        return [child for child in self.order if parent_of(self.defs[child]) == name]

    def ancestry(self, name: str) -> list[str]:
        """The chain root -> ... -> *name*, or a best-effort prefix if malformed.

        Cycle-guarded: a revisited name stops the walk (the cycle is reported by
        :func:`validate_family`).
        """
        chain: list[str] = []
        seen: set[str] = set()
        current: str | None = name
        while current is not None and current in self.defs and current not in seen:
            seen.add(current)
            chain.append(current)
            current = parent_of(self.defs[current])
        chain.reverse()
        return chain

    def root_of(self, name: str) -> str | None:
        chain = self.ancestry(name)
        return chain[0] if chain else None

    def strategy_of(self, name: str) -> str | None:
        root = self.root_of(name)
        if root is None:
            return None
        block = inheritance_of(self.defs[root])
        return block.get("strategy") if block else None

    def tag_column_of(self, name: str) -> str | None:
        root = self.root_of(name)
        if root is None:
            return None
        block = inheritance_of(self.defs[root])
        tag = block.get("tag") if block else None
        return tag.get("column") if isinstance(tag, dict) else None

    def concrete_descendants(self, name: str) -> list[str]:
        """The concrete subtypes reachable from *name*, in descriptor order.

        A concrete node resolves to itself; an abstract node to its concrete
        descendants (depth-first, cycle-guarded, deduplicated preserving order).
        """
        result: list[str] = []
        seen: set[str] = set()

        def visit(node: str) -> None:
            if node in seen or node not in self.defs:
                return
            seen.add(node)
            if is_concrete(self.defs[node]):
                if node not in result:
                    result.append(node)
            for child in self.children_of(node):
                visit(child)

        visit(name)
        return result

    def effective_concrete_set(self, name: str) -> list[str]:
        """The concrete subtype set a query at position *name* resolves over.

        Abstract root = the whole family; abstract subtype = its concrete
        descendants; concrete subtype (or a non-inheritance entity) = itself.
        """
        if name not in self.defs:
            return [name]
        if is_concrete(self.defs[name]):
            return [name]
        return self.concrete_descendants(name)

    def resolve_to_set(self, to_list: list[str]) -> list[str]:
        """The effective concrete set a ``narrow.to`` list resolves to.

        Each entry resolves to its own effective concrete set (a concrete subtype
        to itself, an abstract subtype to its concrete descendants); the union is
        deduplicated preserving DESCRIPTOR order — an entry appearing first keeps
        its concretes in descriptor order, so ``[Pet]`` and ``[Cat, Dog]`` may
        differ in authored spelling yet resolve to the same set.
        """
        result: list[str] = []
        for name in to_list:
            for concrete in self.effective_concrete_set(name):
                if concrete not in result:
                    result.append(concrete)
        return result

    def declaring_entity(self, cls: str, attr_name: str) -> str | None:
        """The NEAREST entity in *cls*'s ancestry that literally declares *attr_name*.

        An attribute referenced as ``Class.attr`` may be inherited; this returns the
        entity where it is actually declared (``Payment`` for an inherited
        ``CardPayment.amount``, ``Dog`` for a subtype-declared ``Dog.barkVolume``),
        walking from *cls* up toward the root. ``None`` when no ancestor declares it.
        """
        for name in reversed(self.ancestry(cls)):
            for attribute in self.defs.get(name, {}).get("attributes", []) or []:
                if attribute.get("name") == attr_name:
                    return name
        return None


def _entity_defs(descriptor: dict[str, Any]) -> list[dict[str, Any]]:
    """Lift a descriptor (single ``entity`` or ``entities`` list) to a flat list."""
    if "entities" in descriptor:
        entities = descriptor.get("entities")
        return list(entities) if isinstance(entities, list) else []
    entity = descriptor.get("entity")
    return [entity] if isinstance(entity, dict) else []


# --- effective (flattened) definition derivation ---------------------------


def _merge_ancestry_attributes(family: Family, name: str) -> list[dict[str, Any]]:
    """Attributes of *name*'s ancestry (root -> ... -> self), deduplicated by column."""
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ancestor in family.ancestry(name):
        for attribute in family.defs[ancestor].get("attributes", []) or []:
            column = attribute.get("column")
            if column in seen:
                continue
            seen.add(column)
            merged.append(attribute)
    return merged


def _synthesize_tag_attribute(column: str) -> dict[str, Any]:
    """A framework-owned tag column, presented as a non-null string attribute.

    The tag is NOT a declared entity attribute (m-inheritance); the harness
    synthesizes it into a concrete subtype's flattened attribute list so the
    shared-table DDL creates it and the write derivation can slot its
    ``tagValue`` (resolved Q6). Its name equals its column: fixtures never author
    it (it is derived from ``tagValue``).
    """
    return {
        "name": column,
        "type": "string",
        "column": column,
        "maxLength": _TAG_COLUMN_MAX_LENGTH,
        "nullable": False,
    }


def resolve_effective_definition(entity_defs: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """Return the flattened definition the harness consumes for entity *name*.

    A non-inheritance entity is returned unchanged. An inheritance participant's
    ``attributes`` are replaced with the full inherited chain (root -> ... ->
    self); a ``table-per-hierarchy`` concrete subtype additionally gains the
    synthesized tag column (slotted just after the last primary-key attribute) and
    the resolved root ``tag`` metadata on its inheritance block, so ``tag_of`` and
    the shared-table DDL see the same shape a pre-migration model authored inline.
    Abstract nodes keep their (tableless) definition with the inherited attribute
    chain surfaced for introspection.
    """
    definition = next((d for d in entity_defs if d.get("name") == name), None)
    if definition is None:
        raise KeyError(f"no entity {name!r} in descriptor")
    if inheritance_of(definition) is None:
        return definition

    family = Family(entity_defs)
    merged = _merge_ancestry_attributes(family, name)

    resolved = copy.deepcopy(definition)
    resolved["attributes"] = merged

    role = role_of(definition)
    strategy = family.strategy_of(name)
    if role == ROLE_CONCRETE and strategy == STRATEGY_TPH:
        tag_column = family.tag_column_of(name)
        if tag_column is not None and all(a.get("column") != tag_column for a in merged):
            last_pk = -1
            for index, attribute in enumerate(merged):
                if attribute.get("primaryKey"):
                    last_pk = index
            merged.insert(last_pk + 1, _synthesize_tag_attribute(tag_column))
            block = inheritance_of(resolved)
            if block is not None:
                block["tag"] = {"column": tag_column}
    return resolved


# --- semantic family validation (raises RejectionError) --------------------


def assert_no_abstract_fixture_rows(model: Model) -> None:
    """Reject a model whose abstract node carries fixture rows (m-inheritance).

    An abstract root / abstract subtype is rowless — only concrete subtypes own
    rows — so fixture rows keyed to an abstract entity are invalid.
    """
    for entity in model.entities:
        if is_abstract(entity.definition) and entity.rows:
            raise RejectionError(
                INHERITANCE_ABSTRACT_NODE_FIXTURE_ROWS,
                f"abstract node {entity.name!r} carries {len(entity.rows)} fixture row(s); "
                f"only concrete subtypes own rows",
            )


def validate_family(descriptor: dict[str, Any]) -> None:
    """Reject a descriptor whose inheritance family violates a closed-tree invariant.

    Runs the cross-entity checks the per-entity metamodel schema cannot express
    (resolved Q3/Q4), raising :class:`RejectionError` with the first violated rule.
    Operates on the raw descriptor so it is safe on a malformed (cyclic / schema-
    invalid) inline family — the checks are ordered structural-first so a case that
    pins one defect fires exactly that rule.
    """
    defs = _entity_defs(descriptor)
    validate_family_defs(defs)


def validate_family_defs(entity_defs: list[dict[str, Any]]) -> None:
    """The list-of-definitions form of :func:`validate_family`."""
    # Phase constraint (Finding 3): every inheritance participant in the descriptor
    # is treated as ONE family — this validator does NOT split the participants into
    # connected components by ancestry, so two INDEPENDENT valid families declared in
    # a single descriptor would be wrongly rejected (e.g. as multiple roots). This
    # matches the current corpus (one inheritance family per model) and is a
    # deliberate scope limit; multi-family-per-descriptor support is out of scope for
    # now (see the outline's Open Questions).
    participants = [d for d in entity_defs if inheritance_of(d) is not None]
    if not participants:
        return

    by_name = {d["name"]: d for d in entity_defs if isinstance(d, dict) and "name" in d}

    # 1. Every declared parent resolves to an entity in the descriptor.
    for definition in participants:
        parent = parent_of(definition)
        if parent is not None and parent not in by_name:
            raise RejectionError(
                INHERITANCE_UNKNOWN_PARENT,
                f"{definition['name']!r} names parent {parent!r}, which the descriptor "
                f"does not declare",
            )

    # 2. Parent links are acyclic.
    for definition in participants:
        seen: set[str] = set()
        current: str | None = definition["name"]
        while current is not None:
            if current in seen:
                raise RejectionError(
                    INHERITANCE_CYCLE,
                    f"parent links from {definition['name']!r} form a cycle at {current!r}",
                )
            seen.add(current)
            current = parent_of(by_name[current]) if current in by_name else None

    # 3. The inheritance participants form exactly one family with one root.
    roots = [d["name"] for d in participants if role_of(d) == ROLE_ROOT]
    if len(roots) > 1:
        raise RejectionError(
            INHERITANCE_MULTIPLE_ROOTS,
            f"the descriptor declares more than one inheritance root {sorted(roots)}; a "
            f"family has exactly one root",
        )

    # 4. A non-root participant MUST NOT redeclare the family strategy.
    for definition in participants:
        if role_of(definition) != ROLE_ROOT and "strategy" in inheritance_of(definition):  # type: ignore[operator]
            raise RejectionError(
                INHERITANCE_STRATEGY_REDECLARED,
                f"non-root {definition['name']!r} redeclares the family strategy; only the "
                f"root declares it",
            )

    # 5. An abstract node (root / abstract-subtype) is tableless.
    for definition in participants:
        if is_abstract(definition) and "table" in definition:
            raise RejectionError(
                INHERITANCE_ABSTRACT_NODE_WITH_TABLE,
                f"abstract node {definition['name']!r} declares a physical table; abstract "
                f"roots and subtypes are tableless",
            )

    family = Family(entity_defs)

    # 6. Every concrete subtype reaches an abstract root through its ancestry.
    for definition in participants:
        if role_of(definition) != ROLE_CONCRETE:
            continue
        chain = family.ancestry(definition["name"])
        top = chain[0] if chain else None
        if top is None or role_of(by_name.get(top, {})) != ROLE_ROOT:
            raise RejectionError(
                INHERITANCE_CONCRETE_WITHOUT_ABSTRACT_ROOT,
                f"concrete subtype {definition['name']!r} has no abstract root ancestor "
                f"(ancestry top is {top!r})",
            )

    # 7. Exactly one root: check #3 rejects the >1 shape; this rejects the zero-root
    #    shape. A family with a CONCRETE participant and no root is already caught by
    #    check #6 (concrete-without-abstract-root), which runs first, so reaching this
    #    point with no root means every participant is an abstract orphan whose
    #    ancestry never tops out at a `root` (participants exist, zero roots, no
    #    concrete) — a family that can never be instantiated or discriminated.
    if not roots:
        raise RejectionError(
            INHERITANCE_MISSING_ROOT,
            "the descriptor declares inheritance participants but no root; a family has "
            "exactly one root",
        )

    # Strategy-scoped checks (the strategy is the root's; exactly one root is now
    # guaranteed by checks #3 and #7).
    root_block = inheritance_of(by_name[roots[0]])
    strategy = root_block.get("strategy") if root_block else None

    if strategy == STRATEGY_TPCS:
        # 8. A table-per-concrete-subtype family declares no tag / tagValue anywhere.
        for definition in participants:
            block = inheritance_of(definition)
            if block is not None and ("tag" in block or "tagValue" in block):
                raise RejectionError(
                    INHERITANCE_TAG_ON_CONCRETE_SUBTYPE_STRATEGY,
                    f"table-per-concrete-subtype family carries a tag/tagValue on "
                    f"{definition['name']!r}; only table-per-hierarchy uses a tag",
                )

    if strategy == STRATEGY_TPH:
        concretes = [d for d in participants if role_of(d) == ROLE_CONCRETE]
        # 9. Every concrete subtype declares a tagValue: table-per-hierarchy rows share
        #    one table and are told apart ONLY by the tag column, so a concrete subtype
        #    with no tagValue would be indistinguishable in the shared table. The
        #    per-entity metamodel schema leaves tagValue optional (its presence is a
        #    cross-entity rule the root's strategy owns), so it is enforced here, before
        #    the family-wide uniqueness check below (which then sees only real values).
        tagged: list[tuple[str, str]] = []
        for definition in concretes:
            value = inheritance_of(definition).get("tagValue")  # type: ignore[union-attr]
            if value is None:
                raise RejectionError(
                    INHERITANCE_MISSING_TAG_VALUE,
                    f"table-per-hierarchy concrete subtype {definition['name']!r} declares "
                    f"no tagValue; the shared table cannot discriminate its rows without one",
                )
            tagged.append((definition["name"], value))
        # 10. tagValue values are unique across the whole family (presence is #9).
        seen_values: dict[str, str] = {}
        for name, value in tagged:
            if value in seen_values:
                raise RejectionError(
                    INHERITANCE_DUPLICATE_TAG_VALUE,
                    f"concrete subtypes {seen_values[value]!r} and {name!r} "
                    f"share tagValue {value!r}",
                )
            seen_values[value] = name
        # 11. All concrete subtypes map to one shared physical table.
        tables = {d.get("table") for d in concretes if d.get("table") is not None}
        if len(tables) > 1:
            raise RejectionError(
                INHERITANCE_INCONSISTENT_HIERARCHY_TABLE,
                f"table-per-hierarchy concrete subtypes map to different tables "
                f"{sorted(t for t in tables if t is not None)}; they share one table",
            )


# --- operation-level narrow / subtype-scope validation (raises RejectionError) --


def _has_inheritance(entity_defs: list[dict[str, Any]]) -> bool:
    return any(inheritance_of(d) is not None for d in entity_defs if isinstance(d, dict))


def _root_name(entity_defs: list[dict[str, Any]]) -> str | None:
    for definition in entity_defs:
        if isinstance(definition, dict) and role_of(definition) == ROLE_ROOT:
            return definition["name"]
    return None


def validate_operation_inheritance(
    entity_defs: list[dict[str, Any]],
    operation: Any,
    position: str | None = None,
) -> None:
    """Reject an operation that narrows / references subtypes incompatibly (Phase 4).

    The read-side counterpart of the write-derivation oracle: it walks the operation
    tree of an inheritance family and raises :class:`RejectionError` with the
    violated ``m-op-algebra`` narrow rule. A no-op for a descriptor with no
    inheritance family. *position* is the polymorphic position the operation starts
    from (a read's ``targetEntity``); a rejected operation case carries no
    ``targetEntity``, so *position* defaults to the family root. Each ``narrow``'s
    subset check binds to this ACTIVE position (threaded and re-narrowed at every
    hop) intersected with the narrow's own ``entity``-declared position — NOT to
    ``effective_concrete_set(narrow.entity)`` alone — so a narrow cannot broaden
    beyond the position actually in scope even when its ``entity`` names a broader
    one.
    """
    if not _has_inheritance(entity_defs):
        return
    family = Family(entity_defs)
    start = position if position is not None else _root_name(entity_defs)
    if start is None:
        return
    _walk_narrow(family, family.effective_concrete_set(start), operation)


def _walk_narrow(family: Family, current_set: list[str], node: Any) -> None:
    """Walk *node*, tracking the current effective concrete set (narrowed per hop)."""
    if not isinstance(node, dict) or len(node) != 1:
        return
    tag, body = next(iter(node.items()))
    if tag == "narrow":
        entity = body.get("entity")
        to_list = body.get("to", []) or []
        # The effective polymorphic position this narrow operates on is the
        # `entity`-declared position CLAMPED to the active position threaded into
        # this walk (`current_set`): the read's `targetEntity` at top level, or the
        # enclosing narrow's narrowed set when nested. `entity` names the position
        # the author intends to narrow, but a narrow can only ever CONSTRAIN the
        # active position, never broaden it — so an `entity` naming a position
        # BROADER than the one in scope is clamped (not rejected), while a narrow
        # whose `entity` names a NARROWER sub-position (e.g. a top-level rejected
        # case, positioned at the family root, that narrows an intermediate abstract
        # subtype) is honored. When `entity` equals the active position — the normal
        # case, where a top-level narrow's `entity` equals the read's targetEntity —
        # the intersection is a no-op. Binding the subset check to this intersection
        # (rather than to `effective_concrete_set(entity)` alone) is what stops a
        # nested narrow, or a top-level narrow whose `entity` is broader than the
        # threaded position, from broadening back out.
        entity_set = family.effective_concrete_set(entity) if isinstance(entity, str) else []
        current = set(current_set)
        position_set = [c for c in entity_set if c in current]
        to_set = family.resolve_to_set([t for t in to_list if isinstance(t, str)])
        if not to_set:
            raise RejectionError(
                NARROW_EMPTY_EFFECTIVE_SET,
                f"narrow to {to_list!r} resolves to the empty concrete-subtype set",
            )
        if not set(to_set) <= set(position_set):
            raise RejectionError(
                NARROW_OUTSIDE_POSITION,
                f"narrow of {entity!r} to {to_list!r} resolves to {sorted(to_set)}, "
                f"which is not a subset of the active position's effective set "
                f"{sorted(position_set)} (the entity position {sorted(entity_set)} "
                f"clamped to the threaded position {sorted(current_set)})",
            )
        _walk_narrow(family, to_set, body.get("operand"))
    elif tag in ("and", "or"):
        for operand in body.get("operands", []) or []:
            _walk_narrow(family, current_set, operand)
    elif tag in ("not", "group", "distinct", "limit", "asOf", "asOfRange", "history"):
        _walk_narrow(family, current_set, body.get("operand"))
    elif tag == "orderBy":
        _walk_narrow(family, current_set, body.get("operand"))
        for key in body.get("keys", []) or []:
            if isinstance(key, dict):
                _check_subtype_attr(family, current_set, key.get("attr"))
    elif tag in _ATTR_BEARING_TAGS:
        _check_subtype_attr(family, current_set, body.get("attr"))
    # navigate / exists / notExists / deepFetch / nested* / all / none carry no
    # queried-position subtype-attribute reference to validate in this phase.


def _check_subtype_attr(family: Family, current_set: list[str], attr_ref: Any) -> None:
    """Reject a concrete-subtype-declared attribute used outside a compatible narrow.

    An attribute is available only to the concrete descendants of the entity that
    DECLARES it; if the current (possibly narrowed) position's effective set is not
    a subset of those concretes, the reference is out of scope.
    """
    if not isinstance(attr_ref, str) or "." not in attr_ref:
        return
    cls, _, attr_name = attr_ref.partition(".")
    if cls not in family.defs or inheritance_of(family.defs[cls]) is None:
        return  # a non-inheritance entity has no polymorphic scoping
    declaring = family.declaring_entity(cls, attr_name)
    if declaring is None:
        return  # unknown attribute — other validation owns this
    possessing = set(family.concrete_descendants(declaring))
    if not set(current_set) <= possessing:
        raise RejectionError(
            SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE,
            f"attribute {attr_ref!r} is declared on {declaring!r}; the current "
            f"position {sorted(current_set)} is not narrowed to its concrete-subtype "
            f"set {sorted(possessing)}, so the attribute is not available to every "
            f"concrete in scope",
        )


# --- abstract-read materialization oracle (familyVariant + projection) ---------


def tag_value_to_subtype(entity_defs: list[dict[str, Any]]) -> dict[Any, str]:
    """Map each concrete subtype's ``tagValue`` to its NAME (the ``familyVariant``).

    The table-per-hierarchy materialization map (resolved Q6): a returned row's raw
    tag value resolves to the concrete subtype name the harness reports as
    ``familyVariant``. Non-inheritance and table-per-concrete-subtype entities
    contribute nothing.
    """
    mapping: dict[Any, str] = {}
    for definition in entity_defs:
        if not isinstance(definition, dict):
            continue
        block = inheritance_of(definition)
        if block and block.get("role") == ROLE_CONCRETE and block.get("tagValue") is not None:
            mapping[block["tagValue"]] = definition["name"]
    return mapping


def concrete_superset_columns(
    entity_defs: list[dict[str, Any]], effective_set: list[str]
) -> list[str]:
    """The ordered union of flattened columns over *effective_set* (incl. the tag).

    Each concrete subtype's flattened definition carries its full inherited chain
    plus, for table-per-hierarchy, the synthesized tag column
    (:func:`resolve_effective_definition`), so this is exactly the superset an
    abstract-target read MUST project — inherited columns first, then each
    concrete's declared columns in descriptor order, and the tag column.
    """
    columns: list[str] = []
    for name in effective_set:
        resolved = resolve_effective_definition(entity_defs, name)
        for attribute in resolved.get("attributes", []) or []:
            column = attribute.get("column")
            if column is not None and column not in columns:
                columns.append(column)
    return columns
