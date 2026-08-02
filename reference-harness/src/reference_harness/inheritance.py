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
consistency, tag placement, temporal-axis root ownership) are semantic and live
here — the same non-normative grading pattern the value-object resolvers
follow, raising the shared
:class:`~reference_harness.value_object_resolve.RejectionError` with the violated
``then.rejectedRule``.

Temporality is a FAMILY-WIDE property, not an ordinary inherited member: only
the root may declare ``asOfAxes``, and every descendant inherits the
root's complete axis set unchanged (never redeclaring, adding, removing,
overriding, or shadowing one), regardless of whether the root itself is
temporal.

This module also owns the **effective definition** derivation: a concrete subtype
does not repeat inherited attributes, so the harness derives the full inherited
attribute chain (root -> ... -> self) plus, for ``table-per-hierarchy``, the
synthesized framework-owned tag column, presenting each concrete subtype as a
flattened entity the DDL / write-derivation / fixture-load paths consume unchanged.
Abstract nodes are rowless. Under table-per-hierarchy the root nevertheless owns
the shared table mapping; concrete definitions resolve to that table for physical
DDL and write derivation.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from .naming import default_column_name
from .operation_references import (
    ATTRIBUTE_REFERENCE_TAGS,
    OPERAND_ROW_WRAPPER_TAGS,
    PATH_REFERENCE_TAGS,
)
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


def _short_entity_name(reference: str) -> str:
    return reference.rsplit(".", 1)[-1]


def effective_column(attribute: dict[str, Any]) -> str:
    """The storage column a raw declared Attribute binds to.

    A canonical descriptor omits ``column`` when it equals the portable derived
    default (m-descriptor), so the effective location is the explicit ``column``
    when present, else ``defaultColumn(attribute.name)``. Use this for any raw
    (uncompiled) attribute dict; compiled ``Entity.attributes`` already carry the
    resolved ``column``.
    """
    return attribute.get("column", default_column_name(attribute["name"]))


# The synthesized tag column carries short discriminator literals; a bounded
# string keeps the shared-table DDL a plain ``varchar`` (m-inheritance / m-sql).
_TAG_COLUMN_MAX_LENGTH = 32

# --- rule vocabulary (kept in lockstep with the compatibility-case schema) --

INHERITANCE_UNKNOWN_PARENT = "inheritance-unknown-parent"
INHERITANCE_CYCLE = "inheritance-cycle"
INHERITANCE_MISSING_ROOT = "inheritance-missing-root"
INHERITANCE_CONCRETE_WITHOUT_ABSTRACT_ROOT = "inheritance-concrete-without-abstract-root"
# Only concrete subtypes own rows, so a family of a root and abstract subtypes
# alone resolves every one of its positions to the EMPTY effective concrete set.
INHERITANCE_MISSING_CONCRETE_SUBTYPE = "inheritance-missing-concrete-subtype"
INHERITANCE_TPH_ROOT_TABLE_REQUIRED = "inheritance-tph-root-table-required"
INHERITANCE_TPH_DESCENDANT_TABLE_FORBIDDEN = "inheritance-tph-descendant-table-forbidden"
INHERITANCE_TPCS_ABSTRACT_TABLE_FORBIDDEN = "inheritance-tpcs-abstract-table-forbidden"
INHERITANCE_TPCS_CONCRETE_TABLE_REQUIRED = "inheritance-tpcs-concrete-table-required"
INHERITANCE_ABSTRACT_NODE_FIXTURE_ROWS = "inheritance-abstract-node-fixture-rows"
INHERITANCE_STRATEGY_REDECLARED = "inheritance-strategy-redeclared"
INHERITANCE_MISSING_TAG_VALUE = "inheritance-missing-tag-value"
INHERITANCE_DUPLICATE_TAG_VALUE = "inheritance-duplicate-tag-value"
INHERITANCE_TAG_ON_CONCRETE_SUBTYPE_STRATEGY = "inheritance-tag-on-concrete-subtype-strategy"
# Temporality is a family-wide property: only the root may declare `asOfAxes`;
# an `abstract-subtype` or `concrete-subtype` that declares its own — whether
# the root is itself non-temporal or temporal — is rejected.
INHERITANCE_TEMPORAL_AXES_NOT_ROOT_OWNED = "inheritance-temporal-axes-not-root-owned"
# Optimistic locking is likewise a family-wide property (D-25 / ADR 0027): only
# the root may declare an `optimisticLocking` attribute; an `abstract-subtype`
# or `concrete-subtype` that declares its own — whether the root is itself
# versioned or not — is rejected. A family is versioned together or not at all.
INHERITANCE_OPTIMISTIC_LOCKING_NOT_ROOT_OWNED = "inheritance-optimistic-locking-not-root-owned"
INHERITANCE_PERSISTENCE_NOT_ROOT_OWNED = "inheritance-persistence-not-root-owned"
INHERITANCE_MATERIALIZATION_KEY_COLLISION = "inheritance-materialization-key-collision"

MODEL_REJECTED_RULES: frozenset[str] = frozenset(
    {
        INHERITANCE_UNKNOWN_PARENT,
        INHERITANCE_CYCLE,
        INHERITANCE_MISSING_ROOT,
        INHERITANCE_CONCRETE_WITHOUT_ABSTRACT_ROOT,
        INHERITANCE_MISSING_CONCRETE_SUBTYPE,
        INHERITANCE_TPH_ROOT_TABLE_REQUIRED,
        INHERITANCE_TPH_DESCENDANT_TABLE_FORBIDDEN,
        INHERITANCE_TPCS_ABSTRACT_TABLE_FORBIDDEN,
        INHERITANCE_TPCS_CONCRETE_TABLE_REQUIRED,
        INHERITANCE_ABSTRACT_NODE_FIXTURE_ROWS,
        INHERITANCE_STRATEGY_REDECLARED,
        INHERITANCE_MISSING_TAG_VALUE,
        INHERITANCE_DUPLICATE_TAG_VALUE,
        INHERITANCE_TAG_ON_CONCRETE_SUBTYPE_STRATEGY,
        INHERITANCE_TEMPORAL_AXES_NOT_ROOT_OWNED,
        INHERITANCE_OPTIMISTIC_LOCKING_NOT_ROOT_OWNED,
        INHERITANCE_PERSISTENCE_NOT_ROOT_OWNED,
        INHERITANCE_MATERIALIZATION_KEY_COLLISION,
    }
)

# Operation-level rules (m-op-algebra x m-inheritance): a SCHEMA-VALID operation a
# model-aware validator MUST refuse pre-SQL because it narrows or references
# subtypes incompatibly with the polymorphic position it queries.
NARROW_OUTSIDE_POSITION = "narrow-outside-position"
NARROW_EMPTY_EFFECTIVE_SET = "narrow-empty-effective-set"
SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE = "subtype-attribute-outside-narrow-scope"
# The non-family half of the same positional rule: the referenced entity shares no
# inheritance family with the active position, so no narrow is a remedy.
ATTRIBUTE_OUTSIDE_ACTIVE_POSITION = "attribute-outside-active-position"
# A narrow in a navigation filter's `op` (or a deep-fetch path segment) that
# resolves outside the relationship target's effective concrete set.
NARROW_OUTSIDE_RELATIONSHIP_TARGET = "narrow-outside-relationship-target"
# The resolution half of the positional rules: a reference position spells its
# entity BARE, so a local name two namespaces of the model declare names no single
# entity and the reference resolves nowhere.
REFERENCE_AMBIGUOUS_ENTITY_NAME = "reference-ambiguous-entity-name"

OPERATION_REJECTED_RULES: frozenset[str] = frozenset(
    {
        NARROW_OUTSIDE_POSITION,
        NARROW_EMPTY_EFFECTIVE_SET,
        SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE,
        ATTRIBUTE_OUTSIDE_ACTIVE_POSITION,
        NARROW_OUTSIDE_RELATIONSHIP_TARGET,
        REFERENCE_AMBIGUOUS_ENTITY_NAME,
    }
)

# Write-scope rules (m-inheritance x concrete-subtype writes): a
# SCHEMA-VALID neutral write input (1) a model-aware validator MUST refuse pre-SQL
# because it violates the concrete-subtype write protocol — it is keyless
# (set-based), carries framework-owned metadata, references a sibling / unrelated
# branch's attribute, or aims at an abstract handle. These mirror the value-object
# WRITE rules (`write-required-attribute-missing`, ...) wired through
# ``value_object_resolve.REJECTED_RULES``, and join the runner's closed rejection
# vocabulary via :data:`WRITE_REJECTED_RULES`.
SUBTYPE_WRITE_SIBLING_ATTRIBUTE = "subtype-write-sibling-attribute"
SUBTYPE_WRITE_METADATA_FIELD = "subtype-write-metadata-field"
ABSTRACT_WRITE_TARGET = "abstract-write-target"
SUBTYPE_WRITE_SET_BASED_UNSUPPORTED = "subtype-write-set-based-unsupported"

WRITE_REJECTED_RULES: frozenset[str] = frozenset(
    {
        SUBTYPE_WRITE_SIBLING_ATTRIBUTE,
        SUBTYPE_WRITE_METADATA_FIELD,
        ABSTRACT_WRITE_TARGET,
        SUBTYPE_WRITE_SET_BASED_UNSUPPORTED,
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


def _qualified_name(definition: dict[str, Any]) -> str:
    namespace = definition.get("namespace")
    return definition["name"] if namespace is None else f"{namespace}.{definition['name']}"


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


class _IdentityDefinitions(dict[str, dict[str, Any]]):
    def __init__(self, definitions: dict[str, dict[str, Any]]) -> None:
        super().__init__(definitions)
        local_keys: dict[str, list[str]] = {}
        for key, definition in definitions.items():
            local_keys.setdefault(definition["name"], []).append(key)
        self._local_keys = local_keys

    def canonical_key(self, name: str) -> str:
        if dict.__contains__(self, name):
            return name
        matches = self._local_keys.get(name, [])
        return matches[0] if len(matches) == 1 else name

    def ambiguous_spellings(self, name: str) -> tuple[str, ...]:
        """The canonical spellings ``name`` would name when more than one namespace
        declares it, else empty — an exact identity and an unambiguous local alias
        both resolve, so both answer empty."""
        if dict.__contains__(self, name):
            return ()
        matches = self._local_keys.get(name, [])
        return tuple(sorted(matches)) if len(matches) > 1 else ()

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and dict.__contains__(self, self.canonical_key(name))

    def __getitem__(self, name: str) -> dict[str, Any]:
        return dict.__getitem__(self, self.canonical_key(name))

    def get(self, name: str, default: Any = None) -> Any:
        return dict.get(self, self.canonical_key(name), default)


class Family:
    """A read-only view of the inheritance participants in a descriptor.

    Built from the raw entity definitions (a list of dicts), so it is safe to run
    on an *invalid* inline family (a ``when.model`` rejected case) before any
    flattening — the walks are cycle-guarded.
    """

    def __init__(self, entity_defs: list[dict[str, Any]]) -> None:
        definitions = [d for d in entity_defs if isinstance(d, dict) and "name" in d]
        self._keys = {id(definition): _qualified_name(definition) for definition in definitions}
        self.defs = _IdentityDefinitions(
            {self._keys[id(definition)]: definition for definition in definitions}
        )
        self.order = [self._keys[id(definition)] for definition in definitions]
        identities = {
            _qualified_name(definition): self._keys[id(definition)] for definition in definitions
        }
        self.parents: dict[str, str | None] = {}
        for key, definition in self.defs.items():
            parent = parent_of(definition)
            if parent is None:
                self.parents[key] = None
            elif "." in parent:
                self.parents[key] = identities.get(parent, parent)
            else:
                namespace = definition.get("namespace")
                qualified = parent if namespace is None else f"{namespace}.{parent}"
                self.parents[key] = identities.get(qualified, parent)

    def key_of(self, definition: dict[str, Any]) -> str:
        return self._keys[id(definition)]

    def _render_key(self, key: str) -> str:
        definition = self.defs[key]
        local_name = definition["name"]
        local_matches = [item for item in self.order if self.defs[item]["name"] == local_name]
        return key if len(local_matches) > 1 else local_name

    def children_of(self, name: str) -> list[str]:
        """Direct subtypes of *name*, in descriptor declaration order.

        This is a structural tree edge used only for traversal (it may yield abstract
        interior nodes as well as concretes); it is NOT the canonical sibling-set
        ordering. The canonical concrete-subtype order is alphabetical
        (:func:`concrete_descendants` / :func:`canonical_concrete_order`).
        """
        key = self.defs.canonical_key(name)
        return [child for child in self.order if self.parents[child] == key]

    def ancestry(self, name: str) -> list[str]:
        """The chain root -> ... -> *name*, or a best-effort prefix if malformed.

        Cycle-guarded: a revisited name stops the walk (the cycle is reported by
        :func:`validate_family`).
        """
        chain: list[str] = []
        seen: set[str] = set()
        current: str | None = self.defs.canonical_key(name)
        while current is not None and current in self.defs and current not in seen:
            seen.add(current)
            chain.append(current)
            current = self.parents[current]
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
        """The concrete subtypes reachable from *name*, in CANONICAL sibling-set order.

        A concrete node resolves to itself; an abstract node to its concrete
        descendants (collected depth-first, cycle-guarded, deduplicated). The
        returned set is presented in the family's **canonical sibling-set order** —
        ALPHABETICAL by concrete-subtype entity name, ordinal (Unicode codepoint)
        ascending — a total order independent of the descriptor's file layout
        (m-inheritance). This is the order every canonical enumeration of a family's
        concretes uses: the table-per-hierarchy tag ``in`` list + binds, the
        table-per-concrete-subtype ``union all`` branch order, the grouped-``OR``
        per-branch ``EXISTS`` order, the narrowed view keys, and the per-subtype
        OWN-column blocks of an abstract-read superset projection.
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

        visit(self.defs.canonical_key(name))
        return self.canonical_concrete_order(result)

    def effective_concrete_set(self, name: str) -> list[str]:
        """The concrete subtype set a query at position *name* resolves over.

        Abstract root = the whole family; abstract subtype = its concrete
        descendants; concrete subtype (or a non-inheritance entity) = itself. A
        multi-member set is in the family's canonical sibling-set order (ALPHABETICAL
        by entity name, :func:`concrete_descendants`).
        """
        if name not in self.defs:
            return [name]
        key = self.defs.canonical_key(name)
        if is_concrete(self.defs[key]):
            return [self._render_key(key)]
        return self.concrete_descendants(key)

    def resolve_to_set(self, to_list: list[str]) -> list[str]:
        """The effective concrete set a ``narrow.to`` list resolves to.

        Each entry resolves to its own effective concrete set (a concrete subtype
        to itself, an abstract subtype to its concrete descendants); the union is
        deduplicated by first appearance. The RESULTING SET — not this transient
        order — is what matters: callers canonicalize it to the family's alphabetical
        sibling-set order (:func:`canonical_concrete_order`) before it drives any
        golden artifact, so ``[Pet]`` and ``[Cat, Dog]`` resolve to the same set and
        therefore the same canonical order.
        """
        result: list[str] = []
        for name in to_list:
            for concrete in self.effective_concrete_set(name):
                if concrete not in result:
                    result.append(concrete)
        return result

    def relationship_target(self, rel_ref: str) -> str | None:
        """The target a canonical ``Class.relationship`` declaration reaches.

        Used to resolve the polymorphic position a navigation filter (or deep-fetch
        hop) reaches: ``Person.pets`` -> ``Pet``. Returns ``None`` when the class or
        relationship is absent (the caller then treats the target as non-polymorphic).
        """
        if not isinstance(rel_ref, str) or "." not in rel_ref:
            return None
        cls, rel_name = rel_ref.rsplit(".", 1)
        definition = self.defs.get(cls)
        if definition is None:
            return None
        for relationship in definition.get("relationships", []) or []:
            if relationship.get("name") != rel_name:
                continue
            join = relationship.get("join")
            if isinstance(join, dict):
                target = join.get("target")
                if isinstance(target, dict) and isinstance(target.get("entity"), str):
                    return self.defs.canonical_key(target["entity"])
            reverse_of = relationship.get("reverseOf")
            if isinstance(reverse_of, str) and "." in reverse_of:
                owner, _relationship_name = reverse_of.rsplit(".", 1)
                return self.defs.canonical_key(owner)
        return None

    def canonical_concrete_order(self, concretes: list[str]) -> list[str]:
        """*concretes* re-sorted into the family's CANONICAL sibling-set order.

        The canonical order is ALPHABETICAL by concrete-subtype entity name, ordinal
        (Unicode codepoint) ascending (m-inheritance) — a total order independent of
        the authored spelling and of the descriptor's file layout, so ``[Cat, Dog]``
        and ``[Pet]`` both yield ``[Cat, Dog]``.
        """

        def identity(name: str) -> tuple[str, str]:
            key = self.defs.canonical_key(name)
            namespace, separator, local_name = key.rpartition(".")
            return (namespace if separator else "", local_name if separator else name)

        return [
            self._render_key(self.defs.canonical_key(name))
            for name in sorted(concretes, key=identity)
        ]


def _entity_defs(descriptor: dict[str, Any]) -> list[dict[str, Any]]:
    """Lift a descriptor (single ``entity`` or ``entities`` list) to a flat list."""
    if "entities" in descriptor:
        entities = descriptor.get("entities")
        return list(entities) if isinstance(entities, list) else []
    entity = descriptor.get("entity")
    return [entity] if isinstance(entity, dict) else []


# --- effective (flattened) definition derivation ---------------------------


def _merge_ancestry_attributes(family: Family, name: str) -> list[dict[str, Any]]:
    """Attributes of *name*'s ancestry (root -> ... -> self), deduplicated by their
    effective storage column — the explicit ``column`` or the portable derived
    default when omitted (m-descriptor)."""
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ancestor in family.ancestry(name):
        for attribute in family.defs[ancestor].get("attributes", []) or []:
            column = effective_column(attribute)
            if column in seen:
                continue
            seen.add(column)
            merged.append(attribute)
    return merged


def _merge_ancestry_value_objects(family: Family, name: str) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for ancestor in family.ancestry(name):
        merged.extend(family.defs[ancestor].get("valueObjects", []) or [])
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
    exact = [d for d in entity_defs if _qualified_name(d) == name]
    local = [d for d in entity_defs if d.get("name") == name]
    matches = exact or local
    definition = matches[0] if len(matches) == 1 else None
    if definition is None:
        raise KeyError(f"no entity {name!r} in descriptor")
    if inheritance_of(definition) is None:
        return definition

    family = Family(entity_defs)
    key = family.key_of(definition)
    merged = _merge_ancestry_attributes(family, key)

    resolved = copy.deepcopy(definition)
    resolved["attributes"] = merged
    resolved["valueObjects"] = _merge_ancestry_value_objects(family, key)

    # Inherit As-Of Axes from
    # the family ROOT ALONE (the binding root-ownership decision: temporality is
    # family-wide, not an ordinary inherited member — `validate_family_defs`
    # check 4a rejects any OTHER participant that declares its own axes, so a
    # valid descriptor's non-root `resolved` never carries them locally). The
    # harness surfaces the root's axes here, exactly as it derives the inherited
    # attribute chain, so the DDL builds the milestone key, is_temporal is true,
    # and the milestone-write / as-of-read oracles treat the concrete as the
    # milestone-owning row it is. A per-entity metamodel reader (which does not
    # flatten inheritance) still classifies the concrete non-temporal from its
    # own empty axes — this is the inheritance-aware view.
    if "asOfAxes" not in resolved:
        root_name = family.root_of(key)
        root_def = family.defs.get(root_name, {}) if root_name is not None else {}
        if "asOfAxes" in root_def:
            resolved["asOfAxes"] = copy.deepcopy(root_def["asOfAxes"])

    role = role_of(definition)
    strategy = family.strategy_of(key)
    if role == ROLE_CONCRETE and strategy == STRATEGY_TPH:
        root_name = family.root_of(key)
        root_def = family.defs.get(root_name, {}) if root_name is not None else {}
        if "table" in root_def:
            resolved["table"] = root_def["table"]
        tag_column = family.tag_column_of(key)
        if tag_column is not None and all(effective_column(a) != tag_column for a in merged):
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


def _validate_materialization_keys(
    definitions: list[dict[str, Any]], *, family_variant: bool
) -> None:
    """Reject provenance-distinct contributors that render one node key."""
    claimed: dict[str, str] = {}

    def claim(key: str, contributor: str) -> None:
        existing = claimed.get(key)
        if existing is not None:
            raise RejectionError(
                INHERITANCE_MATERIALIZATION_KEY_COLLISION,
                f"materialized key {key!r} is claimed by both {existing} and {contributor}",
            )
        claimed[key] = contributor

    if family_variant:
        claim("familyVariant", "polymorphic family variant")
    relationships: list[tuple[str, str]] = []
    attributes: list[tuple[str, str]] = []
    for definition in definitions:
        entity = definition["name"]
        for attribute in definition.get("attributes", []) or []:
            if isinstance(attribute, dict):
                attributes.append(
                    (effective_column(attribute), f"Attribute {entity}.{attribute['name']}")
                )
        for value_object in definition.get("valueObjects", []) or []:
            if isinstance(value_object, dict):
                claim(value_object["name"], f"Value Object {entity}.{value_object['name']}")
        for relationship in definition.get("relationships", []) or []:
            if isinstance(relationship, dict):
                pair = (relationship["name"], f"Relationship {entity}.{relationship['name']}")
                relationships.append(pair)
    for key, contributor in attributes:
        claim(key, contributor)
    for key, contributor in relationships:
        claim(key, contributor)
    for key, contributor in attributes:
        for relationship, relationship_contributor in relationships:
            if key.startswith(f"{relationship}["):
                raise RejectionError(
                    INHERITANCE_MATERIALIZATION_KEY_COLLISION,
                    f"materialized key {key!r} from {contributor} occupies the narrowed-view "
                    f"namespace of {relationship_contributor}",
                )


def _independent_families(
    participants: list[dict[str, Any]], family: Family
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Each independent inheritance family among *participants*: the name of the
    topmost declared position its members' ancestry reaches, paired with those
    members in declaration order.

    A position declares at most one parent, so two roots can never share an
    ancestry and every participant falls in exactly one family. Meaningful only
    once unknown parents and cycles are rejected, which is what makes each
    upward walk terminate at a single top.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for definition in participants:
        top = family.ancestry(family.key_of(definition))[0]
        grouped.setdefault(top, []).append(definition)
    return list(grouped.items())


def validate_family_defs(entity_defs: list[dict[str, Any]]) -> None:
    """The list-of-definitions form of :func:`validate_family`.

    A descriptor may declare several independent families; the root-scoped and
    strategy-scoped checks below are therefore asked once per family, so one
    family's root never answers for another's.
    """
    for definition in entity_defs:
        if inheritance_of(definition) is None:
            _validate_materialization_keys([definition], family_variant=False)

    participants = [d for d in entity_defs if inheritance_of(d) is not None]
    if not participants:
        return

    family = Family(entity_defs)

    # 1. Every declared parent resolves to an entity in the descriptor.
    for definition in participants:
        key = family.key_of(definition)
        parent = family.parents[key]
        if parent is not None and parent not in family.defs:
            raise RejectionError(
                INHERITANCE_UNKNOWN_PARENT,
                f"{definition['name']!r} names parent {parent!r}, which the descriptor "
                f"does not declare",
            )

    # 2. Parent links are acyclic.
    for definition in participants:
        seen: set[str] = set()
        current: str | None = family.key_of(definition)
        while current is not None:
            if current in seen:
                raise RejectionError(
                    INHERITANCE_CYCLE,
                    f"parent links from {definition['name']!r} form a cycle at {current!r}",
                )
            seen.add(current)
            current = family.parents[current] if current in family.defs else None

    # 4. A non-root participant MUST NOT redeclare the family strategy.
    for definition in participants:
        if role_of(definition) != ROLE_ROOT and "strategy" in inheritance_of(definition):  # type: ignore[operator]
            raise RejectionError(
                INHERITANCE_STRATEGY_REDECLARED,
                f"non-root {definition['name']!r} redeclares the family strategy; only the "
                f"root declares it",
            )

    # 4a. A non-root participant MUST NOT declare its own temporal axes (the
    #     binding root-ownership decision): temporality is family-wide, so only
    #     the root may declare `asOfAxes`, regardless of whether the root
    #     itself is temporal.
    for definition in participants:
        if role_of(definition) != ROLE_ROOT and "asOfAxes" in definition:
            raise RejectionError(
                INHERITANCE_TEMPORAL_AXES_NOT_ROOT_OWNED,
                f"non-root {definition['name']!r} declares its own as-of axes; temporal axes "
                f"are family-wide and MUST be declared only on the root",
            )

    # 4b. A non-root participant MUST NOT declare its own `optimisticLocking`
    #     attribute (D-25 / ADR 0027): the version attribute is family-wide, so
    #     only the root may declare one, regardless of whether the root itself
    #     is versioned. Fires for BOTH malformed shapes (a non-versioned root
    #     with a version-declaring descendant, and a versioned root whose
    #     descendant redeclares or adds a second version attribute) — the check
    #     is structural per-entity and does not care what the root declares.
    for definition in participants:
        if role_of(definition) == ROLE_ROOT:
            continue
        attributes = definition.get("attributes", []) or []
        if any(
            isinstance(attribute, dict) and attribute.get("optimisticLocking")
            for attribute in attributes
        ):
            raise RejectionError(
                INHERITANCE_OPTIMISTIC_LOCKING_NOT_ROOT_OWNED,
                f"non-root {definition['name']!r} declares its own optimisticLocking "
                f"attribute; the version attribute is family-wide and MUST be declared "
                f"only on the root",
            )

    # 4c. Persistence is family-wide and root-owned.
    for definition in participants:
        if role_of(definition) != ROLE_ROOT and "persistence" in definition:
            raise RejectionError(
                INHERITANCE_PERSISTENCE_NOT_ROOT_OWNED,
                f"non-root {definition['name']!r} declares persistence; persistence is "
                f"family-wide and MUST be declared only on the root",
            )

    # 6. Every concrete subtype reaches an abstract root through its ancestry.
    for definition in participants:
        if role_of(definition) != ROLE_CONCRETE:
            continue
        chain = family.ancestry(family.key_of(definition))
        top = chain[0] if chain else None
        if top is None or role_of(family.defs.get(top, {})) != ROLE_ROOT:
            raise RejectionError(
                INHERITANCE_CONCRETE_WITHOUT_ABSTRACT_ROOT,
                f"concrete subtype {definition['name']!r} has no abstract root ancestor "
                f"(ancestry top is {top!r})",
            )

    families = _independent_families(participants, family)

    # 7. Every family reaches exactly one root. Its members share one ancestry, so
    #    "more than one" is unrepresentable and only the zero-root shape remains.
    #    A family with a CONCRETE participant and no root is already caught by check
    #    #6 (concrete-without-abstract-root), which runs first, so reaching this
    #    point rootless means every member is an abstract orphan whose ancestry never
    #    tops out at a `root` — a family that can never be instantiated or
    #    discriminated.
    for top, members in families:
        if role_of(family.defs.get(top, {})) != ROLE_ROOT:
            raise RejectionError(
                INHERITANCE_MISSING_ROOT,
                f"the inheritance participants "
                f"{sorted(member['name'] for member in members)} declare no root; a "
                f"family has exactly one root",
            )

    # 7a. Every family contains at least one concrete subtype. Only concrete
    #     subtypes own rows, so a family of a root and abstract subtypes alone
    #     resolves every one of its positions to the EMPTY effective concrete set:
    #     no read selects a row and no write names a target. Asked after the root
    #     rules (a rootless family has no position to ask this of) and before the
    #     strategy-scoped mapping rules (this is a question about the family's
    #     membership, not about how that membership maps to storage).
    for top, members in families:
        if any(role_of(member) == ROLE_CONCRETE for member in members):
            continue
        raise RejectionError(
            INHERITANCE_MISSING_CONCRETE_SUBTYPE,
            f"the family rooted at {family.defs[top]['name']!r} declares no concrete "
            f"subtype, so every position in it owns no rows",
        )

    # Strategy-scoped checks, asked of each family under ITS OWN root's strategy.
    for top, members in families:
        root_definition = family.defs[top]
        root_block = inheritance_of(root_definition)
        strategy = root_block.get("strategy") if root_block else None

        if strategy == STRATEGY_TPCS:
            # 8. Abstract positions are tableless; every concrete owns one table.
            for definition in members:
                if role_of(definition) in ABSTRACT_ROLES and "table" in definition:
                    raise RejectionError(
                        INHERITANCE_TPCS_ABSTRACT_TABLE_FORBIDDEN,
                        f"table-per-concrete-subtype abstract position "
                        f"{definition['name']!r} declares a table",
                    )
                if role_of(definition) == ROLE_CONCRETE and "table" not in definition:
                    raise RejectionError(
                        INHERITANCE_TPCS_CONCRETE_TABLE_REQUIRED,
                        f"table-per-concrete-subtype concrete {definition['name']!r} "
                        f"declares no table",
                    )
            # 8. A table-per-concrete-subtype family declares no tag / tagValue anywhere.
            for definition in members:
                block = inheritance_of(definition)
                if block is not None and ("tag" in block or "tagValue" in block):
                    raise RejectionError(
                        INHERITANCE_TAG_ON_CONCRETE_SUBTYPE_STRATEGY,
                        f"table-per-concrete-subtype family carries a tag/tagValue on "
                        f"{definition['name']!r}; only table-per-hierarchy uses a tag",
                    )
            for definition in members:
                if role_of(definition) != ROLE_CONCRETE:
                    continue
                chain = [family.defs[name] for name in family.ancestry(family.key_of(definition))]
                _validate_materialization_keys(chain, family_variant=True)

        if strategy == STRATEGY_TPH:
            concretes = [d for d in members if role_of(d) == ROLE_CONCRETE]
            if "table" not in root_definition:
                raise RejectionError(
                    INHERITANCE_TPH_ROOT_TABLE_REQUIRED,
                    f"table-per-hierarchy root {root_definition['name']!r} declares no "
                    f"shared table",
                )
            for definition in members:
                if role_of(definition) != ROLE_ROOT and "table" in definition:
                    raise RejectionError(
                        INHERITANCE_TPH_DESCENDANT_TABLE_FORBIDDEN,
                        f"table-per-hierarchy descendant {definition['name']!r} repeats "
                        f"the root-owned shared table",
                    )
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
            for definition in concretes:
                chain = [family.defs[name] for name in family.ancestry(family.key_of(definition))]
                _validate_materialization_keys(chain, family_variant=True)


# --- operation-level narrow / attribute-position validation (RejectionError) ----


def _default_position(entity_defs: list[dict[str, Any]]) -> str | None:
    """The position an operation carrying no ``targetEntity`` starts from.

    ``m-op-algebra``'s model-aware default: the inheritance family root when the
    descriptor declares one, else its first declared entity — the position a
    single-entity case queries.
    """
    for definition in entity_defs:
        if isinstance(definition, dict) and role_of(definition) == ROLE_ROOT:
            return definition["name"]
    for definition in entity_defs:
        if isinstance(definition, dict) and "name" in definition:
            return str(definition["name"])
    return None


def narrowed_view_key(family: Family, rel_ref: str, effective_set: list[str]) -> str:
    """The deterministic graph key of a NARROWED deep-fetch hop (m-deep-fetch).

    ``<relationshipName>[<Concrete>,<Concrete>]`` — the LOCAL relationship name
    (never the qualified ref), the effective concrete-subtype set in the family's
    CANONICAL sibling-set order (ALPHABETICAL by entity name, m-inheritance; never
    abstract names, never a ``tagValue``), no spaces inside the brackets. Equivalent
    authored spellings (``to: [Pet]`` vs ``to: [Cat, Dog]``) resolve to the same
    effective set and therefore the same key. A BROAD hop uses the ordinary
    relationship name and never calls this.
    """
    rel_name = rel_ref.split(".", 1)[1] if "." in rel_ref else rel_ref
    return f"{rel_name}[{','.join(effective_set)}]"


def resolve_hop_effective_set(
    family: Family, rel_ref: str, narrow_to: list[str] | None
) -> tuple[list[str], bool]:
    """The (canonically-ordered effective concrete set, is_narrowed) of a deep-fetch hop.

    A BROAD hop (``narrow_to`` is ``None``) resolves to the relationship target's own
    effective concrete set; a NARROWED hop resolves ``narrow_to`` (each entry to its
    concretes) and CLAMPS it to the target's set. Raises
    :class:`RejectionError` (``narrow-outside-relationship-target``) when a narrowed
    hop resolves outside the target's reachable concretes or to the empty set. The
    returned set is always in the family's canonical sibling-set order (ALPHABETICAL
    by entity name) so the view key is canonical.
    """
    target = family.relationship_target(rel_ref)
    target_set = family.effective_concrete_set(target) if target is not None else []
    if narrow_to is None:
        return family.canonical_concrete_order(target_set) if target else target_set, False
    resolved = family.resolve_to_set([t for t in narrow_to if isinstance(t, str)])
    if not resolved:
        raise RejectionError(
            NARROW_OUTSIDE_RELATIONSHIP_TARGET,
            f"deep-fetch narrow of {rel_ref!r} to {narrow_to!r} resolves to the empty "
            f"concrete-subtype set",
        )
    if not set(resolved) <= set(target_set):
        raise RejectionError(
            NARROW_OUTSIDE_RELATIONSHIP_TARGET,
            f"deep-fetch narrow of {rel_ref!r} to {narrow_to!r} resolves to "
            f"{sorted(resolved)}, which is not a subset of the relationship target's "
            f"effective concrete set {sorted(target_set)}",
        )
    # Reaching here, `resolved` is a non-empty subset of `target_set`, so `target` is
    # non-None (a None target yields target_set == [], failing the subset check above).
    ordered = family.canonical_concrete_order(resolved) if target is not None else resolved
    return ordered, True


def _check_reference_entity_name(family: Family, reference: Any, name: Any) -> None:
    """Reject a reference position whose entity spelling names more than one entity.

    Every reference position spells its entity BARE — the operation grammars admit
    no namespace segment — so a local name two namespaces of the model declare names
    no single entity there and the reference resolves nowhere. Refusing it is a
    REFERENCE-site rule: both entities stay declarable, and each stays reachable
    through a position that names it unambiguously.
    """
    if not isinstance(name, str):
        return
    canonical = family.defs.ambiguous_spellings(name)
    if canonical:
        raise RejectionError(
            REFERENCE_AMBIGUOUS_ENTITY_NAME,
            f"{reference!r}: the bare entity spelling {name!r} is shared by "
            f"{list(canonical)}, so it names no single entity in this model and the "
            f"reference resolves nowhere",
        )


def _check_member_reference(family: Family, reference: Any) -> None:
    """Check the entity spelling of a ``Class.member`` reference (an ``attr`` or a
    ``rel``), whose class part is the spelling up to its LAST dot."""
    if isinstance(reference, str) and "." in reference:
        _check_reference_entity_name(family, reference, reference.rpartition(".")[0])


def _check_path_reference(family: Family, reference: Any) -> None:
    """Check the entity spelling of a nested value-object ``path``, whose class
    part is its FIRST segment — every trailing segment is a declared
    value-object member rather than one member name."""
    if isinstance(reference, str) and "." in reference:
        _check_reference_entity_name(family, reference, reference.split(".", 1)[0])


def resolve_clamped_narrow(
    family: Family,
    current_set: list[str],
    entity: Any,
    to_list: Any,
    outside_rule: str = NARROW_OUTSIDE_POSITION,
) -> list[str]:
    """The resolved effective set of an ``{entity, to}`` narrow at a NAMED position.

    Shared by the operation-position ``narrow`` node and a deep-fetch path's ROOT
    guard, which resolve identically: the ``entity``-declared position is CLAMPED to
    (intersected with) *current_set* — the active position threaded into the walk —
    and ``to`` is accepted iff it resolves NON-EMPTY and within that clamp. Naming a
    broader position is therefore constrained rather than rejected, while a ``to``
    reaching outside the active position raises *outside_rule* and a ``to``
    resolving to nothing raises ``narrow-empty-effective-set``. Binding the subset
    check to the intersection (rather than to ``effective_concrete_set(entity)``
    alone) is what stops a nested narrow, or one whose ``entity`` is broader than
    the threaded position, from broadening back out.

    ``entity`` and every ``to`` entry are reference positions, so a spelling that
    names no single entity is refused there before either subset check: unresolved,
    it would otherwise contribute nothing and surface as the empty or
    outside-position set the narrow rules classify.
    """
    names = [t for t in to_list if isinstance(t, str)] if isinstance(to_list, list) else []
    for name in [entity, *names]:
        _check_reference_entity_name(family, name, name)
    entity_set = family.effective_concrete_set(entity) if isinstance(entity, str) else []
    current = set(current_set)
    position_set = [c for c in entity_set if c in current]
    to_set = family.resolve_to_set(names)
    if not to_set:
        raise RejectionError(
            NARROW_EMPTY_EFFECTIVE_SET,
            f"narrow to {to_list!r} resolves to the empty concrete-subtype set",
        )
    if not set(to_set) <= set(position_set):
        raise RejectionError(
            outside_rule,
            f"narrow of {entity!r} to {to_list!r} resolves to {sorted(to_set)}, "
            f"which is not a subset of the active position's effective set "
            f"{sorted(position_set)} (the entity position {sorted(entity_set)} "
            f"clamped to the threaded position {sorted(current_set)})",
        )
    return to_set


def resolve_root_source_set(
    family: Family, position: str | None, path: Any
) -> tuple[str, ...] | None:
    """The concrete source set ONE deep-fetch path starts from, or ``None``.

    A path's root position is the read's own queried position: absent a root
    ``narrow`` the path starts from every root object, so the source set is
    *position*'s whole effective concrete set; a root ``narrow`` guards it down to
    the guard's resolved set. ``None`` is a non-polymorphic root, which has no
    source set to distinguish hops by. The returned set is in the family's
    canonical sibling-set order, so two guards resolving to the same concretes
    yield the SAME tuple and therefore the same hop — which is what makes a
    full-set guard indistinguishable from a broad path (m-deep-fetch).
    """
    if position is None or inheritance_of(family.defs.get(position, {})) is None:
        return None
    narrow = path.get("narrow") if isinstance(path, dict) else None
    if isinstance(narrow, dict):
        resolved = resolve_clamped_narrow(
            family, family.effective_concrete_set(position), narrow.get("entity"), narrow.get("to")
        )
    else:
        resolved = family.effective_concrete_set(position)
    return tuple(family.canonical_concrete_order(resolved))


def validate_operation_inheritance(
    entity_defs: list[dict[str, Any]],
    operation: Any,
    position: str | None = None,
) -> None:
    """Reject an operation that narrows or references entities outside its position.

    The read-side counterpart of the write-derivation oracle: it walks the operation
    tree and raises :class:`RejectionError` with the violated ``m-op-algebra`` narrow
    or positional-attribute rule. It runs on EVERY descriptor, not only one declaring
    an inheritance family: a standalone entity's effective concrete set is itself, so
    the same subset test rejects a reference naming an unrelated entity
    (``attribute-outside-active-position``) with no special case.

    *position* is the polymorphic position the operation starts from (a read's
    ``targetEntity``); a rejected operation case carries no ``targetEntity``, so
    *position* defaults to what ``m-op-algebra`` fixes — the inheritance family root
    when the descriptor declares one, else its first declared entity.

    Each ``narrow``'s subset check binds to the ACTIVE position (threaded and
    re-narrowed at every hop) intersected with the narrow's own ``entity``-declared
    position — NOT to ``effective_concrete_set(narrow.entity)`` alone — so a narrow
    cannot broaden beyond the position actually in scope even when its ``entity``
    names a broader one.
    """
    family = Family(entity_defs)
    start = position if position is not None else _default_position(entity_defs)
    if start is None:
        return
    _walk_active_position(family, family.effective_concrete_set(start), operation)


def _walk_active_position(
    family: Family,
    current_set: list[str],
    node: Any,
    outside_rule: str = NARROW_OUTSIDE_POSITION,
    expected_entity: str | None = None,
) -> None:
    """Walk *node*, judging every positional rule against the active position.

    The position is *current_set*, the active polymorphic position's effective
    concrete set, threaded down the whole operation tree and re-narrowed per hop.
    Two rules are asked of it — a ``narrow``'s subset check and every attribute
    reference's applicability — and the second runs for a standalone descriptor
    too, so this walk is not narrow-specific.

    *outside_rule* is the rejected rule a broadening narrow raises: at the queried
    (top-level) position a broadening narrow is ``narrow-outside-position``; inside a
    navigation filter's ``op`` (where the active position is the RELATIONSHIP TARGET)
    it is ``narrow-outside-relationship-target`` (resolved Q10).

    *expected_entity* is the entity a positional ``narrow`` at THIS position MUST name
    (``m-navigate``): inside a navigation filter's ``op`` the active position is the
    relationship target, so a narrow there MUST set ``narrow.entity`` to that target
    exactly — narrowing to subtypes is always via ``to``, never by declaring a broader
    (or narrower) ``entity``. A mismatch is ``narrow-outside-relationship-target``. It
    is ``None`` at the queried (top-level) position and inside a narrow's ``operand``,
    where the general CLAMP (``m-op-algebra``) governs instead; it is carried through
    the position-preserving wrappers (``and`` / ``or`` / ``not`` / …) and re-seeded
    per hop at each nested navigation filter, and cleared when descending through a
    narrow's ``operand`` (the position becomes the narrowed set — a same-position
    narrow, clamped, not name-checked).
    """
    if not isinstance(node, dict) or len(node) != 1:
        return
    tag, body = next(iter(node.items()))
    if tag in ("navigate", "exists", "notExists"):
        # A navigation filter re-roots the active polymorphic position at the
        # relationship TARGET; a narrow in its `op` narrows THAT position, MUST NAME
        # the target as its `entity`, and a broadening narrow there is
        # `narrow-outside-relationship-target`. A non-polymorphic (or unresolved)
        # target contributes its own singleton set. Re-seeds `expected_entity` to the
        # new hop's target (never inherits the enclosing position's).
        _check_member_reference(family, body.get("rel"))
        op = body.get("op")
        if op is None:
            return
        target = family.relationship_target(body.get("rel"))
        target_set = family.effective_concrete_set(target) if target is not None else []
        _walk_active_position(family, target_set, op, NARROW_OUTSIDE_RELATIONSHIP_TARGET, target)
        return
    if tag == "narrow":
        entity = body.get("entity")
        to_list = body.get("to", []) or []
        # A spelling that names no single entity fails to resolve before it can be
        # compared to the relationship target or clamped to the active position.
        _check_reference_entity_name(family, entity, entity)
        # Relationship-scope naming (m-navigate): when this narrow sits at a navigation
        # filter's relationship-target position, its `entity` MUST NAME that target
        # exactly — subtypes are reached via `to`, not by renaming (or broadening) the
        # position. `expected_entity` is None at the queried / nested same-position
        # levels, where the CLAMP below is the whole rule.
        if expected_entity is not None and (
            not isinstance(entity, str) or family.defs.canonical_key(entity) != expected_entity
        ):
            raise RejectionError(
                NARROW_OUTSIDE_RELATIONSHIP_TARGET,
                f"narrow at the relationship-target position names entity {entity!r}, "
                f"but the relationship target is {expected_entity!r}; narrow to subtypes "
                f"with `to`, not by naming a different position",
            )
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
        to_set = resolve_clamped_narrow(family, current_set, entity, to_list, outside_rule)
        # Descending into `operand`: the position becomes the narrowed set, so a
        # nested narrow is a SAME-POSITION narrow governed by the clamp — clear
        # `expected_entity` (the naming requirement was this narrow's alone).
        _walk_active_position(family, to_set, body.get("operand"), outside_rule, None)
    elif tag in ("and", "or"):
        # Position-preserving: a narrow directly under `and` / `or` is still the
        # target-position narrow, so it inherits the naming requirement.
        for operand in body.get("operands", []) or []:
            _walk_active_position(family, current_set, operand, outside_rule, expected_entity)
    elif tag in ("not", "group", "distinct", "limit", "asOf", "asOfRange", "history"):
        _walk_active_position(
            family, current_set, body.get("operand"), outside_rule, expected_entity
        )
    elif tag == "orderBy":
        operand = body.get("operand")
        _walk_active_position(family, current_set, operand, outside_rule, expected_entity)
        ordered_set = _ordered_position(family, current_set, operand, outside_rule)
        for key in body.get("keys", []) or []:
            if isinstance(key, dict):
                _check_attribute_position(family, ordered_set, key.get("attr"))
    elif tag == "deepFetch":
        # A deep-fetch path narrows at two positions with two different rules. Its
        # ROOT `{entity, to}` guard names the queried position and is clamped to the
        # active one exactly as an operation-position `narrow` node is
        # (`narrow-outside-position`). Each SEGMENT's `{to}` narrows that hop's
        # (polymorphic) relationship target and must resolve within it
        # (`narrow-outside-relationship-target`). The operand is the root query,
        # walked at the queried position.
        for path in body.get("paths", []) or []:
            root_narrow = path.get("narrow") if isinstance(path, dict) else None
            if isinstance(root_narrow, dict):
                resolve_clamped_narrow(
                    family,
                    current_set,
                    root_narrow.get("entity"),
                    root_narrow.get("to"),
                    outside_rule,
                )
            segments = path.get("segments") if isinstance(path, dict) else None
            for segment in segments if isinstance(segments, list) else []:
                rel = segment.get("rel") if isinstance(segment, dict) else None
                _check_member_reference(family, rel)
                if isinstance(rel, str) and isinstance(segment.get("narrow"), dict):
                    to_list = segment["narrow"].get("to")
                    for name in to_list if isinstance(to_list, list) else []:
                        _check_reference_entity_name(family, name, name)
                    resolve_hop_effective_set(family, rel, to_list)
        _walk_active_position(
            family, current_set, body.get("operand"), outside_rule, expected_entity
        )
    elif tag == "groupBy":
        # An aggregation names entities in three further reference positions —
        # each group key, each projected aggregate's `attr`, and the `attr` of
        # every aggregate a `having` leaf compares — and `m-op-algebra` "Entity
        # spellings in a reference position" governs all of them. Only the
        # resolution half applies here: a group key and an aggregate `attr` are
        # not subtype-attribute references at the queried position, so their
        # applicability is `m-agg`'s question rather than this walk's.
        _walk_active_position(
            family, current_set, body.get("operand"), outside_rule, expected_entity
        )
        for key in body.get("keys", []) or []:
            _check_member_reference(family, key)
        for aggregate in body.get("aggregates", []) or []:
            _check_aggregate_reference(family, aggregate)
        _check_having_references(family, body.get("having"))
    elif tag in ATTRIBUTE_REFERENCE_TAGS:
        _check_attribute_position(family, current_set, body.get("attr"))
    elif tag in PATH_REFERENCE_TAGS:
        # A nested value-object `path` spells its entity as the FIRST segment
        # rather than the part before the last dot, because every trailing
        # segment is a declared value-object member. Its resolution is checked
        # here so an ambiguous entity spelling is refused as such, rather than
        # reaching the value-object resolver and being reported as an unknown
        # member of a path that names no entity at all. The path's own
        # applicability to the active position stays that resolver's question.
        _check_path_reference(family, body.get("path"))
    # all / none carry no reference to a queried position here.


def _check_aggregate_reference(family: Family, aggregate: Any) -> None:
    """Check the entity spelling of one aggregate function's ``attr``.

    ``count`` alone may omit ``attr`` (``count(*)``), which names nothing.
    """
    if isinstance(aggregate, dict) and len(aggregate) == 1:
        body = next(iter(aggregate.values()))
        if isinstance(body, dict):
            _check_member_reference(family, body.get("attr"))


def _check_having_references(family: Family, node: Any) -> None:
    """Check every aggregate reference a ``having`` expression compares."""
    if not isinstance(node, dict) or len(node) != 1:
        return
    tag, body = next(iter(node.items()))
    if not isinstance(body, dict):
        return
    if tag in ("and", "or"):
        for operand in body.get("operands", []) or []:
            _check_having_references(family, operand)
        return
    _check_aggregate_reference(family, body.get("agg"))


def _ordered_position(
    family: Family, current_set: list[str], node: Any, outside_rule: str
) -> list[str]:
    """The position an ``orderBy``'s ordered rows occupy.

    A whole-result narrowing lowers to a TOP-LEVEL ``narrow`` under the ordering
    wrapper, so an order key is asked of that narrow's resolved set, reached
    through the wrappers that return their operand's own rows
    (:data:`OPERAND_ROW_WRAPPER_TAGS`) and no other node. A ``narrow`` inside a
    boolean combinator is a predicate term over the same position and moves
    nothing (m-op-algebra).
    """
    if not isinstance(node, dict) or len(node) != 1:
        return current_set
    tag, body = next(iter(node.items()))
    if not isinstance(body, dict):
        return current_set
    if tag == "narrow":
        return resolve_clamped_narrow(
            family, current_set, body.get("entity"), body.get("to", []) or [], outside_rule
        )
    if tag in OPERAND_ROW_WRAPPER_TAGS:
        return _ordered_position(family, current_set, body.get("operand"), outside_rule)
    return current_set


def _check_attribute_position(family: Family, current_set: list[str], attr_ref: Any) -> None:
    """Reject an attribute reference that is not applicable to the active position.

    The rule is measured against the entity the reference NAMES, not the ancestor
    that declares the member: ``m-op-algebra`` states it as "the active position's
    effective set is a subset of the referenced Entity's". A reference is a claim
    about which rows it addresses, so ``Dog.name`` addresses dogs whether or not
    ``name`` is inherited — at a broader position it would lower to the shared
    column and answer for cats and boars too, exactly the mis-answer the sibling
    rules exist to prevent. The subset test is the whole rule and generalizes to a
    standalone entity, whose effective set is itself; only the classification
    splits, on whether a narrow could ever be the remedy — within the reference's
    own inheritance family it can (``subtype-attribute-outside-narrow-scope``), and
    outside it nothing can (``attribute-outside-active-position``).

    The class part is the reference's spelling up to its LAST dot, so a canonically
    spelled position (``<namespace>.<Entity>.<attribute>``) resolves to the entity it
    names rather than to its leading namespace segment. A bare class part two
    namespaces share resolves to no single entity and is refused before the position
    is asked about at all.
    """
    if not isinstance(attr_ref, str) or "." not in attr_ref:
        return
    _check_member_reference(family, attr_ref)
    cls, _, _attr_name = attr_ref.rpartition(".")
    if cls not in family.defs:
        return  # an unknown entity — other validation owns this
    referenced = family.defs.canonical_key(cls)
    possessing = set(family.effective_concrete_set(referenced))
    if set(current_set) <= possessing:
        return
    root = family.root_of(referenced) or referenced
    if set(current_set) <= set(family.effective_concrete_set(root)):
        raise RejectionError(
            SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE,
            f"attribute {attr_ref!r} names {referenced!r}, whose concrete-subtype set "
            f"is {sorted(possessing)}; the current position {sorted(current_set)} is "
            f"not narrowed within it, so the reference is not applicable to every "
            f"concrete in scope",
        )
    raise RejectionError(
        ATTRIBUTE_OUTSIDE_ACTIVE_POSITION,
        f"attribute {attr_ref!r} names {referenced!r}, which shares no inheritance "
        f"family with the active position {sorted(current_set)}, so no narrow makes "
        f"it addressable here",
    )


# --- abstract-read materialization oracle (familyVariant + projection) ---------


def tag_value_to_subtype(entity_defs: list[dict[str, Any]]) -> dict[Any, str]:
    """Map each concrete subtype's ``tagValue`` to its NAME (the ``familyVariant``).

    The table-per-hierarchy materialization map (resolved Q6): a returned row's raw
    tag value resolves to the concrete subtype name the harness reports as
    ``familyVariant``. Non-inheritance and table-per-concrete-subtype entities
    contribute nothing.
    """
    family = Family(entity_defs)
    mapping: dict[Any, str] = {}
    for definition in entity_defs:
        if not isinstance(definition, dict):
            continue
        block = inheritance_of(definition)
        if block and block.get("role") == ROLE_CONCRETE and block.get("tagValue") is not None:
            mapping[block["tagValue"]] = family._render_key(family.key_of(definition))
    return mapping
