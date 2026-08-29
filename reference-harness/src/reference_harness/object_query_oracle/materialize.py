"""Turning the physical rows a golden statement returned into the logical result.

The golden SQL projects storage: a raw discriminator column, a shared Structured
Column, a per-branch ``family_variant`` literal, typed ``null`` placeholders. None
of those is a result field. This module derives the result the case authored from
them — ``familyVariant`` from the tag metadata map, a Relational Document Layout's
members from the document it was stored in — and asserts the projection shape each
derivation depends on, reading that shape from the golden text so a zero-row read
still witnesses a dropped column.

The physical facts themselves are never re-derived here: family topology comes
from :mod:`..inheritance`, column placement from :mod:`..storage_layout`, and the
JSON codec from :mod:`..document_codec`.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, NamedTuple

import sqlglot
from sqlglot import exp

from ..case import Case, Entity, Model
from ..case_assertions import CaseFailure
from ..ddl_builder import contributor_types, placeholder_cast_type
from ..document_codec import decode_leaf, decode_stored
from ..inheritance import (
    STRATEGY_TPCS,
    STRATEGY_TPH,
    Family,
    is_abstract,
    tag_value_to_subtype,
)
from ..sql_canonical import NonCanonicalError, sqlglot_dialect
from ..sql_wrapped_union import WrapFacts, WrapOrderKey, wrapped_union_source
from ..storage_layout import (
    ColumnSlot,
    ColumnTier,
    DocumentPath,
    MemberAddress,
    PositionBranch,
    PositionColumn,
    PositionLayoutView,
    RelationalDocument,
    TableLayout,
    ValueObjectContributor,
    member_address,
    position_projection,
    position_view,
)
from .execute import (
    assert_union_all_only,
    document_presence_ordinals,
    golden_projection_columns,
    projection_expr,
    string_literal_value,
    union_branch_selects,
)

# --- materialized rows ------------------------------------------------------


class MaterializedRow(dict[str, Any]):
    """A result row that still remembers which of its columns are raw VO blobs.

    ``value_object_columns`` are the columns carrying an undecoded Value Object
    occurrence; ``consumed_value_object_columns`` are the ones a projection has
    already taken, so an identity-only comparison can drop the rest.
    """

    __slots__ = ("consumed_value_object_columns", "value_object_columns")

    def __init__(
        self,
        values: dict[str, Any],
        *,
        value_object_columns: dict[str, Any] | None = None,
        consumed_value_object_columns: set[str] | None = None,
    ) -> None:
        super().__init__(values)
        self.value_object_columns = value_object_columns or {}
        self.consumed_value_object_columns = consumed_value_object_columns or set()


def _materialized_row(row: dict[str, Any]) -> MaterializedRow:
    """A writable copy of *row* preserving any Value Object bookkeeping it carries."""
    if isinstance(row, MaterializedRow):
        return MaterializedRow(
            dict(row),
            value_object_columns=dict(row.value_object_columns),
            consumed_value_object_columns=set(row.consumed_value_object_columns),
        )
    return MaterializedRow(dict(row))


# --- the read's family position ---------------------------------------------


class AbstractFamilyPosition(NamedTuple):
    """The abstract family node a query reads, with the family it belongs to.

    *target* keeps the QUERY's own spelling of that position — every :class:`Family`
    lookup resolves an unambiguous local alias itself, so carrying the authored
    spelling keeps a consumer's diagnostics in the case's own words.
    """

    family: Family
    target: str
    strategy: str | None


def abstract_family_position(case: Case, query: Any) -> AbstractFamilyPosition | None:
    """Classify *query*'s target position: the abstract family node it reads, or
    ``None`` for every other read.

    One classifier for every consumer whose behavior turns on the distinction,
    because they all ask the same question of the same field. An ABSTRACT position
    resolves over more than one concrete subtype, so its SQL partitions per branch
    and its result carries a variant tag (`m-sql`); a CONCRETE-target read — and any
    read of a non-inheritance entity — carries neither, having already named the one
    variant it returns. What differs between consumers is only the storage
    *strategy* they then project that behavior from.

    Abstractness is read off the definition's inheritance role, which only a family
    participant carries, so a non-inheritance target answers ``None`` by the same
    test.
    """
    target = query.get("target") if isinstance(query, dict) else None
    if not isinstance(target, str):
        return None
    family = Family(case.model.entity_defs)
    if target not in family.defs:
        return None
    if not is_abstract(family.defs[target]):
        return None
    return AbstractFamilyPosition(family, target, family.strategy_of(target))


def read_effective_set(case: Case, family: Family, target_name: str) -> list[str]:
    """The effective concrete-subtype set an abstract-target read resolves over.

    The queried position is *target_name*, further constrained by the query's own
    ``narrowTo`` clause — then the narrowed selection drives the projection
    superset. A ``narrow`` inside the predicate (grouped branch predicates) leaves
    the target's full family in scope, as does an Include Path's own source guard,
    which qualifies a path's source objects rather than the read's result.
    """
    narrow_to = case.object_query.get("narrowTo")
    if isinstance(narrow_to, list):
        return family.resolve_to_set(narrow_to)
    return family.effective_concrete_set(target_name)


# --- Relational Document Layout ---------------------------------------------


class DocumentMember(NamedTuple):
    """One member a Relational Document Layout keeps inside the shared Structured
    Column: where it sits in the document and — for a leaf — the declared type its
    stored spelling decodes through.

    ``address`` identifies the member — by its declaring owner, so two disjoint
    inheritance siblings sharing a Table may reuse a member name and still be told
    apart — and ``column`` only spells it: a member inside a document claims no
    Column, so its spelling is free to collide with the Column a direct member
    really holds."""

    address: MemberAddress
    column: str
    path: tuple[str, ...]
    type_spelling: str | None

    @property
    def name(self) -> str:
        return self.address.path[0]


def document_layout_members(case: Case, entity: Entity) -> tuple[str, tuple[DocumentMember, ...]]:
    """*entity*'s Structured Column and the top-level members it carries.

    Answers ``("", ())`` for a conventional ``Columns`` entity, which is what makes
    the fan-out below inert rather than conditional at its call sites. Residency
    comes from the independently compiled Member Placements, never from the
    declaration, and each member is asked for at its own address: a Table shared by
    disjoint inheritance siblings holds a placement per declaration, so the member
    one of them reaches under a reused name is the one its own declaration owns. A
    leaf inside an occurrence is addressed under that occurrence and is left to the
    occurrence's own document, which already carries it.
    """
    layout = case.model.storage_layout.table(entity.table)
    if layout is None:
        return "", ()
    slot = next(
        (slot for slot in layout.columns if isinstance(slot.contributor, RelationalDocument)), None
    )
    if slot is None:
        return "", ()
    family = Family(case.model.entity_defs)

    def resident(declaration: dict[str, Any], type_spelling: str | None) -> DocumentMember | None:
        address = member_address(family, entity.canonical_name, declaration["name"])
        placement = layout.placement(address)
        if not (isinstance(placement, DocumentPath) and placement.slot == slot):
            return None
        return DocumentMember(address, declaration["column"], placement.path, type_spelling)

    declared = (
        *((attribute, attribute["type"]) for attribute in entity.attributes),
        *((occurrence, None) for occurrence in entity.value_objects),
    )
    return slot.column, tuple(
        member
        for declaration, type_spelling in declared
        if (member := resident(declaration, type_spelling)) is not None
    )


def _document_value(document: Any, path: tuple[str, ...]) -> Any:
    """The raw stored value at *path*, or ``None`` where the walk stops."""
    current = document
    for name in path:
        if not isinstance(current, dict) or name not in current:
            return None
        current = current[name]
    return current


def _materialize_document_layout(
    case: Case,
    entity: Entity,
    rows: list[dict[str, Any]],
    *,
    include_value_objects: bool,
) -> list[dict[str, Any]]:
    """Fan a Relational Document Layout read's Structured Column out into the members
    it was asked for, under the result names a ``Columns`` layout would have used.

    The same shape as :func:`materialize_family_variant`: the golden SQL projects a
    raw column and the logical result is derived from it here, because the Structured
    Column is never itself a result field (`m-sql`). Which members a read asked for
    is the result form's answer — a row-form read takes the scalars alone while an
    instance form additionally carries every applicable occurrence — so the caller
    states it rather than this deriving a second projection rule of its own.

    ``entity`` owns ``rows``, which is the level of a deep fetch they came from
    rather than always the case's read target: every level projects its own
    Structured Column and decodes its own members out of it.

    Each leaf decodes by its DECLARED type (:func:`decode_leaf`), not by the JSON
    value's own shape, and an absent key and an explicit JSON null both read as one
    absence — the single not-present state a NULL Column has.

    An owner with a Structured Column and no member inside it fans out nothing and
    still drops the column: an observation-bearing read projects it for the stored
    document itself (`m-sql` *Read projection*, rule 5), which is provenance rather
    than a result field.
    """
    column, members = document_layout_members(case, entity)
    if not column:
        return rows
    selected = [
        member for member in members if include_value_objects or member.type_spelling is not None
    ]
    materialized: list[dict[str, Any]] = []
    for row in rows:
        if column not in row:
            return rows
        document = decode_stored(row[column])
        node = {key: value for key, value in row.items() if key != column}
        for member in selected:
            stored = _document_value(document, member.path)
            node[member.column] = (
                stored
                if member.type_spelling is None
                else decode_leaf(member.type_spelling, stored)
            )
        materialized.append(node)
    return materialized


def _materialize_target_document_layout(
    case: Case, rows: list[dict[str, Any]], *, include_value_objects: bool
) -> list[dict[str, Any]]:
    """:func:`_materialize_document_layout` over the case's own read target.

    A top-level read's rows belong to its query's own ``target``; a deep fetch's
    child level does not, which is why the entity is an argument there and resolved
    here.
    """
    target_name = case.object_query.get("target")
    if not isinstance(target_name, str):
        return rows
    return _materialize_document_layout(
        case,
        case.model.entity(target_name),
        rows,
        include_value_objects=include_value_objects,
    )


def materialize_target_tph_document_layout(
    case: Case, rows: list[dict[str, Any]], *, include_value_objects: bool
) -> list[dict[str, Any]]:
    """Decode an abstract TPH document only after its raw tag resolves the variant."""
    position = abstract_family_position(case, case.object_query)
    if position is None or position.strategy != STRATEGY_TPH:
        return _materialize_target_document_layout(
            case, rows, include_value_objects=include_value_objects
        )
    family, target_name = position.family, position.target
    target = case.model.entity(target_name)
    column, _members = document_layout_members(case, target)
    if not column:
        return _materialize_target_document_layout(
            case, rows, include_value_objects=include_value_objects
        )

    tagged = materialize_family_variant(case, rows)
    effective = read_effective_set(case, family, target_name)
    scalar_superset = {
        member.column
        for concrete in effective
        for member in document_layout_members(case, case.model.entity(concrete))[1]
        if member.type_spelling is not None
    }
    materialized: list[dict[str, Any]] = []
    for row in tagged:
        variant = row.get("familyVariant")
        if not isinstance(variant, str):
            materialized.append(row)
            continue
        (decoded,) = _materialize_document_layout(
            case,
            case.model.entity(variant),
            [row],
            include_value_objects=include_value_objects,
        )
        if not include_value_objects:
            for column_name in scalar_superset:
                decoded.setdefault(column_name, None)
        materialized.append(decoded)
    return materialized


# --- familyVariant ----------------------------------------------------------


def materialize_family_variant(case: Case, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Materialize ``familyVariant`` for an abstract-target table-per-hierarchy read.

    A non-inheritance / concrete-target read (or a non-TPH strategy) returns *rows*
    unchanged. For an abstract target the golden SQL projects the raw tag column and
    the full concrete superset; this asserts that projection shape, then replaces the
    tag column with the derived ``familyVariant`` (``tagValue`` -> concrete subtype
    name) so the materialized rows can be compared to ``then.rows``.
    """
    position = abstract_family_position(case, case.object_query)
    if position is None:
        return rows  # concrete-target (or non-inheritance) read carries no familyVariant
    family, target_name = position.family, position.target
    if position.strategy == STRATEGY_TPCS:
        return _materialize_tpcs_family_variant(case, rows, family, target_name)
    if position.strategy != STRATEGY_TPH:
        return rows

    tag_column = family.tag_column_of(target_name)
    if tag_column is None:
        return rows
    if rows and all("familyVariant" in row and tag_column not in row for row in rows):
        return rows
    effective = read_effective_set(case, family, target_name)
    expected_columns = set(position_projection(case.model.storage_layout, family, effective))

    # Projection-shape assertion, derived from the GOLDEN SQL projection rather than a
    # sample row, so it is row-count-INDEPENDENT: a zero-row abstract read still
    # witnesses a golden that drops the raw tag column or a concrete-superset column
    # (an empty result set carries no keys to inspect, but the golden text always does).
    # The tag column is checked first so a tag-only omission reports the specific tag
    # diagnostic (the superset set below also contains the tag).
    projected = golden_projection_columns(case)
    if tag_column not in projected:
        raise CaseFailure(
            f"{case.path.name}: abstract-target read does not project the tag "
            f"column {tag_column!r}; an abstract read MUST project the raw tag column "
            f"so familyVariant can be materialized (m-sql / m-inheritance, resolved Q6)."
        )
    missing = expected_columns - projected
    if missing:
        raise CaseFailure(
            f"{case.path.name}: abstract-target read projection is missing "
            f"concrete-superset column(s) {sorted(missing)}; an abstract read MUST "
            f"project the full concrete superset PLUS the raw tag column "
            f"(m-sql / m-inheritance, resolved Q6)."
        )

    return _materialize_tph_family_variant(case, family, target_name, rows)


def _materialize_tph_family_variant(
    case: Case, family: Family, target_name: str, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Replace each row's raw tag column with the derived ``familyVariant``.

    The row-level half of the table-per-hierarchy materialization, shared by the
    whole-read path (which asserts the golden projection shape first) and the
    per-step one (whose shape its own step golden fixes).
    """
    tag_column = family.tag_column_of(target_name)
    if tag_column is None:
        return rows
    if rows and all("familyVariant" in row and tag_column not in row for row in rows):
        return rows
    variant_map = tag_value_to_subtype(case.model.entity_defs)
    materialized: list[dict[str, Any]] = []
    for row in rows:
        new_row = _materialized_row(row)
        if tag_column not in new_row:
            raise CaseFailure(
                f"{case.path.name}: abstract-target read does not project the tag "
                f"column {tag_column!r}; familyVariant cannot be materialized."
            )
        tag_value = new_row.pop(tag_column)
        variant = variant_map.get(tag_value)
        if variant is None:
            raise CaseFailure(
                f"{case.path.name}: tag value {tag_value!r} maps to no concrete subtype "
                f"in the family (tag metadata {sorted(variant_map)})."
            )
        if "familyVariant" in new_row:
            new_row.consumed_value_object_columns.add("familyVariant")
        new_row["familyVariant"] = variant
        materialized.append(new_row)
    return materialized


# --- the table-per-concrete-subtype `union all` -----------------------------

# The projected output column that carries the table-per-concrete-subtype
# `familyVariant` literal per `union all` branch (the settled TPCS asymmetry,
# m-sql): unlike table-per-hierarchy — which projects the RAW tag column and
# derives `familyVariant` at materialization — TPCS has no tag column, so each
# branch projects a subtype-name literal aliased to this column, which the oracle
# renames to `familyVariant` after asserting the branch shape.
_TPCS_VARIANT_COLUMN = "family_variant"


def _tpcs_result_aliases(columns: list[str]) -> list[str]:
    counts = {column: columns.count(column) for column in set(columns)}
    allocated = set(columns) | {_TPCS_VARIANT_COLUMN}
    aliases: list[str] = []
    next_internal = 0
    for column in columns:
        if counts[column] == 1 and column != _TPCS_VARIANT_COLUMN:
            aliases.append(column)
            continue
        while f"parallax_attr_{next_internal}" in allocated:
            next_internal += 1
        alias = f"parallax_attr_{next_internal}"
        allocated.add(alias)
        aliases.append(alias)
        next_internal += 1
    return aliases


def _placeholder_types(
    model: Model, columns: tuple[PositionColumn, ...]
) -> list[tuple[str, int | None] | None]:
    """Each position column's declared neutral type and length bound, in column order.

    The only declaration residue an abstract-read `union all` shape needs: the layout
    settles composition and never a SQL type, yet a branch owning no slot for a
    contributor must still render `cast(null as <declared type>)` in the same neutral
    type the branch that owns it was provisioned with.
    """
    types = contributor_types(model)
    return [types.get(column.contributor) for column in columns]


def _has_document_resident_attribute(case: Case, entity: Entity) -> bool:
    """Whether the layout placed any of *entity*'s own Attributes inside its
    Structured Column — the one need that reaches a Relational Document Layout's
    shared Column from a row-form read (`m-sql` *Read projection*, rule 5)."""
    resident = {member.name for member in document_layout_members(case, entity)[1]}
    return any(attribute["name"] in resident for attribute in entity.attributes)


def _is_instance_form(case: Case) -> bool:
    """Whether a read case's authored result form is the object lane.

    `m-case-format` *Read result form*: a ``then.graph`` / ``then.graphs``
    observation is instance-form and ``then.rows`` is row-form, which is the same
    partition the read dispatch routes on.
    """
    return case.expected_graph is not None or case.expected_graphs is not None


def _projected_position_ordinals(
    case: Case, view: PositionLayoutView, position_branches: list[tuple[PositionBranch, str]]
) -> tuple[int, ...]:
    """The position-column ordinals a read of *case*'s result form projects.

    Every non-`Document` contributor is projected in both result forms. A
    `Document` one is not: a top-level Value Object occurrence's own Structured
    Column reaches only an instance-form read (`m-sql` *Read projection*, rule 3),
    and a Relational Document Layout's shared Structured Column reaches a row-form
    read as well, but only to produce a member the layout placed inside it (rule
    5) — and in a row-form read the members requested are the Attributes alone,
    rule 3 having already omitted every occurrence. So the superset a `union all`
    branch aligns to, and the result aliases allocated over it, are form-dependent
    wherever the position holds a `Document` contributor.
    """
    instance_form = _is_instance_form(case)
    document_resident = any(
        _has_document_resident_attribute(case, case.model.entity(name))
        for _branch, name in position_branches
    )
    return tuple(
        ordinal
        for ordinal, column in enumerate(view.columns)
        if column.tier is not ColumnTier.DOCUMENT
        or (
            instance_form
            if isinstance(column.contributor, ValueObjectContributor)
            else instance_form or document_resident
        )
    )


def _union_all_body(case: Case, tree: Any, dialect: str, facts: WrapFacts) -> Any:
    """The `union all` *tree* asserts its branches against.

    A `union all` has no clause tail of its own, so an ordered or limited
    table-per-concrete-subtype read wraps it as a derived table and applies the
    tail against the union's alias (m-sql). The branch facts — count, order, the
    Table each reads, its per-column shape, its `familyVariant` literal — are the
    same either way, so unwrapping here keeps one oracle for both forms rather
    than forking it by whether the read declared a result shape.

    The wrap is VERIFIED by the normalizer's own verifier rather than merely
    recognized, so the outer shape this walk does not itself grade — the alias,
    the tail, each result alias projected through, the ordering terms — is graded
    there. A golden wrapping its union in any other shape is refused here instead
    of being unwrapped and graded on its branches alone. *facts* carry what the
    statement alone cannot settle and this caller does know: the layout tier behind
    each result alias, the Sort Keys and cap the read authored, and this dialect's
    bind list, without which the outer tail is graded only for shape, a presence pair
    over a scalar reads as the Document read pair, and any same-arity tail bind passes.
    """
    if isinstance(tree, exp.Select):
        try:
            wrapped = wrapped_union_source(tree, dialect, facts)
        except NonCanonicalError as error:
            raise CaseFailure(
                f"{case.path.name}: table-per-concrete-subtype abstract read does not wrap "
                f"its `union all` in the canonical derived table: {error}"
            ) from error
        if wrapped is not None:
            return wrapped
    return tree


def _assert_branch_projection_shape(
    case: Case,
    branch: Any,
    position: int,
    name: str,
    superset: list[str],
    slots: tuple[ColumnSlot | None, ...],
    placeholder_types: list[tuple[str, int | None] | None],
    dialect: str,
) -> None:
    """Assert one `union all` branch's per-column projection SHAPE (m-sql).

    For every superset column (all but the trailing `familyVariant` literal): a column
    the branch OWNS A SLOT for MUST be a real column reference (``t0.<col>``); a column
    it owns no slot for MUST be exactly ``cast(null as <type>)`` in the column's
    declared type mapped to *dialect* (`placeholder_cast_type`, m-dialect). This closes
    the gap where a bare `null <col>` (no cast) or a wrong-typed cast shares the owned
    column's output name and would otherwise pass the name-only check.
    """
    engine = sqlglot_dialect(dialect)
    for column_index, (column, slot, placeholder_type) in enumerate(
        zip(superset, slots, placeholder_types, strict=True)
    ):
        node = projection_expr(branch.expressions[column_index])
        if slot is not None:
            if not isinstance(node, exp.Column):
                raise CaseFailure(
                    f"{case.path.name}: `union all` branch {position} ({name!r}) "
                    f"projects column {column!r} as {node.sql(dialect=engine)!r}, but "
                    f"{column!r} is APPLICABLE to {name!r} (its branch owns the slot) "
                    f"and MUST be a real column reference (m-sql)."
                )
            continue
        # Slotless in this branch: exactly `cast(null as <declared type>)` for this dialect.
        if placeholder_type is None:
            raise CaseFailure(
                f"{case.path.name}: framework-owned column {column!r} is absent from "
                f"the concrete branch {name!r}"
            )
        expected = exp.DataType.build(
            placeholder_cast_type(*placeholder_type, dialect),
            dialect=engine,
        )
        if not (isinstance(node, exp.Cast) and isinstance(node.this, exp.Null)):
            raise CaseFailure(
                f"{case.path.name}: `union all` branch {position} ({name!r}) projects "
                f"NON-applicable column {column!r} as {node.sql(dialect=engine)!r}, but "
                f"it MUST be a `cast(null as {expected.sql(dialect=engine)})` placeholder "
                f"(a bare `null` gives the union an untyped column; m-sql / m-dialect)."
            )
        if node.to != expected:
            raise CaseFailure(
                f"{case.path.name}: `union all` branch {position} ({name!r}) casts the "
                f"NON-applicable column {column!r} placeholder to "
                f"{node.to.sql(dialect=engine)!r}, expected the declared type "
                f"{expected.sql(dialect=engine)!r} for dialect {dialect!r} "
                f"(m-sql / m-dialect)."
            )


def _tpcs_position_branches(
    case: Case, family: Family, ordered: list[str], view: PositionLayoutView
) -> list[tuple[PositionBranch, str]]:
    """The position's branches paired with the subtype name each one's literal spells.

    A table-per-concrete-subtype position owns exactly one branch per concrete Table,
    so the layout's branch sequence IS the `union all` branch order; each branch is
    paired with the family's rendered spelling of its single row owner, which is what
    the golden's `familyVariant` literal carries.
    """
    rendered = {family.defs.canonical_key(name): name for name in ordered}
    pairs = [
        (branch, rendered[branch.concrete_entities[0]])
        for branch in view.branches
        if len(branch.concrete_entities) == 1 and branch.concrete_entities[0] in rendered
    ]
    if len(pairs) != len(ordered):
        raise CaseFailure(
            f"{case.path.name}: the storage layout maps the effective concrete set "
            f"{ordered} onto {len(view.branches)} branch table(s); a table-per-concrete-"
            f"subtype abstract read requires exactly one branch per concrete Table."
        )
    return pairs


def _tpcs_order_keys(
    case: Case,
    view: PositionLayoutView,
    position_branches: list[tuple[PositionBranch, str]],
    ordinals: tuple[int, ...],
    result_aliases: list[str],
) -> tuple[WrapOrderKey, ...]:
    """The read's authored Sort Keys as the wrap's `order by` must render them.

    An ordered abstract read applies its tail against the union alias, so each key
    names the result alias its member reaches rather than any branch's own spelling
    (m-sql). The positional rule (m-object-query) admits a Sort Key only over a member
    applicable to every concrete in the position, so every branch places it and the
    branches agree on how: in a Column of its own, or at one path inside the Structured
    Column, which is what decides whether the key is the alias or the extraction over
    it. The nullability that selects its Null Placement term (m-dialect) is the
    DECLARED one, which is why the key never meets a branch's typed `NULL` placeholder.
    """
    keys: list[WrapOrderKey] = []
    for sort_key in case.object_query.get("orderBy") or []:
        attr = sort_key.get("attr")
        member = str(attr).rpartition(".")[2]
        indices = [index for index, address in enumerate(view.members) if address.path == (member,)]
        if len(indices) != 1:
            raise CaseFailure(
                f"{case.path.name}: `orderBy` key {attr!r} resolves to {len(indices)} member(s) "
                f"of the read's position, so the `union all` wrap's `order by` cannot be "
                f"graded against it (m-object-query)."
            )
        address = view.members[indices[0]]
        placements = [branch.placements[indices[0]] for branch, _ in position_branches]
        placed = {
            (
                placement.slot.contributor,
                placement.path if isinstance(placement, DocumentPath) else (),
            )
            for placement in placements
            if placement is not None
        }
        if any(placement is None for placement in placements) or len(placed) != 1:
            raise CaseFailure(
                f"{case.path.name}: `orderBy` key {attr!r} is placed differently across the "
                f"`union all` branches, so the wrap's `order by` has no one spelling against "
                f"the union alias (m-sql / m-object-query)."
            )
        contributor, document_path = placed.pop()
        alias = next(
            (
                result_aliases[index]
                for index, ordinal in enumerate(ordinals)
                if view.columns[ordinal].contributor == contributor
            ),
            None,
        )
        if alias is None:
            raise CaseFailure(
                f"{case.path.name}: `orderBy` key {attr!r} reaches a Column the read does not "
                f"project, so the wrap's `order by` names no result alias for it (m-sql)."
            )
        declared = next(
            item for item in case.model.entity(address.owner).attributes if item["name"] == member
        )
        keys.append(
            WrapOrderKey(
                alias=alias,
                descending=sort_key.get("direction", "asc") == "desc",
                nulls_first=sort_key.get("nulls", "last") == "first",
                nullable=bool(declared.get("nullable", False)),
                document_path=document_path,
                neutral_type=declared["type"],
            )
        )
    return tuple(keys)


def _assert_tpcs_union_shape(
    case: Case,
    view: PositionLayoutView,
    position_branches: list[tuple[PositionBranch, str]],
) -> None:
    """Assert the table-per-concrete-subtype abstract-read `union all` shape (m-sql).

    The read-side inheritance oracle for TPCS (the counterpart of the TPH
    projection-shape check). The layout position settles the physical facts — the
    branch count and order, the Table each branch reads, the one logical contributor
    sequence every branch aligns to, and each branch's slot-or-absence entry per
    contributor. This asserts the SQL renderings layered over them, which are never
    layout concerns: the collision-safe result aliases, each branch's per-column shape
    (an owned slot is a real reference; a slotless position is a
    `cast(null as <declared type>)` placeholder in that dialect's type), and each
    branch's `familyVariant` literal (the concrete subtype NAME). EVERY declared golden
    dialect is checked (so a MariaDB `char` cast is asserted with the MariaDB type
    mapping, not the Postgres one). Parsed from the golden text, so it is
    row-count-independent — a zero-row abstract read still witnesses a mis-ordered
    branch, a dropped superset column, a bare/mis-typed placeholder, or a wrong literal.

    The superset is the position's contributor sequence restricted to what the
    case's own result form projects (:func:`_projected_position_ordinals`), so a
    row-form read of a position holding a `Document` slot is graded on omitting it
    rather than on carrying it.

    An ordered or limited read additionally wraps its union, and the wrap's own shape
    is graded against the same facts: which result alias holds a `Document`, and the
    Sort Keys and cap the Object Query authored, each rendered as the dialect under
    test spells it.
    """
    ordinals = _projected_position_ordinals(case, view, position_branches)
    superset = [view.column_spellings[ordinal] for ordinal in ordinals]
    position_types = _placeholder_types(case.model, view.columns)
    placeholder_types = [position_types[ordinal] for ordinal in ordinals]
    result_aliases = _tpcs_result_aliases(superset)
    expected_columns = [*result_aliases, _TPCS_VARIANT_COLUMN]
    facts = WrapFacts(
        document_aliases=frozenset(
            alias
            for alias, ordinal in zip(result_aliases, ordinals, strict=True)
            if view.columns[ordinal].tier is ColumnTier.DOCUMENT
        ),
        order_keys=_tpcs_order_keys(case, view, position_branches, ordinals, result_aliases),
        limit=case.object_query.get("limit"),
    )
    for dialect in sorted(case.golden_dialects):
        statements = case.golden_statements(dialect)
        if not statements:
            continue
        tree = sqlglot.parse_one(statements[0], read=sqlglot_dialect(dialect))
        assert_union_all_only(case, tree)
        dialect_facts = replace(facts, binds=tuple(case.statement_binds(0, dialect)))
        branches = union_branch_selects(_union_all_body(case, tree, dialect, dialect_facts))
        if len(branches) != len(position_branches):
            raise CaseFailure(
                f"{case.path.name}: table-per-concrete-subtype abstract read lowers to "
                f"{len(position_branches)} `union all` branch(es) (the effective concrete "
                f"set {[name for _, name in position_branches]}), but the {dialect} golden "
                f"has {len(branches)}."
            )
        for position, (branch, (position_branch, name)) in enumerate(
            zip(branches, position_branches, strict=True)
        ):
            table = position_branch.layout.table
            branch_tables = [source.name for source in branch.find_all(exp.Table)]
            if not branch_tables or branch_tables[0] != table:
                raise CaseFailure(
                    f"{case.path.name}: `union all` branch {position} must read from "
                    f"{table!r} (the alphabetical-order concrete subtype {name!r}), got "
                    f"{branch_tables[0] if branch_tables else None!r}."
                )
            presence_ordinals = set(document_presence_ordinals(branches, case.model, dialect))
            logical_projections = [
                projection
                for ordinal, projection in enumerate(branch.expressions)
                if ordinal not in presence_ordinals
            ]
            out_columns = [projection.output_name for projection in logical_projections]
            if out_columns != expected_columns:
                raise CaseFailure(
                    f"{case.path.name}: `union all` branch {position} ({name!r}) projects "
                    f"{out_columns}, not the stable superset + familyVariant literal "
                    f"{expected_columns} (the position's one contributor sequence, then "
                    f"familyVariant; m-sql)."
                )
            logical_branch = branch.copy()
            logical_branch.set("expressions", logical_projections)
            _assert_branch_projection_shape(
                case,
                logical_branch,
                position,
                name,
                superset,
                tuple(position_branch.slots[ordinal] for ordinal in ordinals),
                placeholder_types,
                dialect,
            )
            literal = string_literal_value(logical_projections[-1])
            if literal != name:
                raise CaseFailure(
                    f"{case.path.name}: `union all` branch {position} projects familyVariant "
                    f"literal {literal!r}, expected the concrete subtype name {name!r} "
                    f"(TPCS projects familyVariant as a per-branch literal; m-sql)."
                )


def _materialize_tpcs_family_variant(
    case: Case, rows: list[dict[str, Any]], family: Family, target_name: str
) -> list[dict[str, Any]]:
    """Rename the projected `familyVariant` literal column for a TPCS abstract read.

    Asserts the `union all` branch/projection shape, then renames each row's
    ``family_variant`` (the per-branch subtype-name literal) to ``familyVariant`` so
    the materialized rows compare against ``then.rows`` — the TPCS counterpart of the
    TPH tag-to-variant materialization (m-inheritance / m-sql). A row observed through
    a collision-safe internal alias is restored to the physical spelling its OWN
    branch's slot carries, and an alias standing for a slot that branch does not own is
    dropped.
    """
    effective = read_effective_set(case, family, target_name)
    ordered = family.canonical_concrete_order(effective)
    view = position_view(case.model.storage_layout, family, effective)
    if view is None:
        raise CaseFailure(
            f"{case.path.name}: the storage layout resolves no position for the effective "
            f"concrete set {ordered}; a table-per-concrete-subtype abstract read must map "
            f"onto one family's canonical concrete selection."
        )
    position_branches = _tpcs_position_branches(case, family, ordered, view)
    _assert_tpcs_union_shape(case, view, position_branches)
    ordinals = _projected_position_ordinals(case, view, position_branches)
    superset = [view.column_spellings[ordinal] for ordinal in ordinals]
    result_aliases = _tpcs_result_aliases(superset)
    column_counts = {column: superset.count(column) for column in set(superset)}
    slots_by_variant = {
        name: tuple(branch.slots[ordinal] for ordinal in ordinals)
        for branch, name in position_branches
    }
    layouts_by_variant = {name: branch.layout for branch, name in position_branches}

    materialized: list[dict[str, Any]] = []
    for row in rows:
        new_row = _materialized_row(row)
        if _TPCS_VARIANT_COLUMN not in new_row:
            raise CaseFailure(
                f"{case.path.name}: table-per-concrete-subtype abstract read does not "
                f"project the {_TPCS_VARIANT_COLUMN!r} literal; familyVariant cannot be "
                f"materialized (m-sql)."
            )
        if "familyVariant" in new_row:
            new_row.consumed_value_object_columns.add("familyVariant")
        variant = new_row.pop(_TPCS_VARIANT_COLUMN)
        slots = slots_by_variant.get(variant)
        if slots is None:
            raise CaseFailure(
                f"{case.path.name}: {_TPCS_VARIANT_COLUMN!r} literal {variant!r} names no "
                f"branch of the effective concrete set {sorted(slots_by_variant)}."
            )
        for slot, column, result_alias in zip(slots, superset, result_aliases, strict=True):
            if (
                result_alias in new_row
                and result_alias != column
                and (column_counts[column] == 1 or slot is not None)
            ):
                new_row[column] = new_row.pop(result_alias)
            elif column_counts[column] > 1 and slot is None:
                new_row.pop(result_alias, None)
        new_row["familyVariant"] = variant
        new_row = _materialize_tpcs_document_row(case, layouts_by_variant[variant], new_row)
        materialized.append(new_row)
    return materialized


def _materialize_tpcs_document_row(
    case: Case, layout: TableLayout, row: dict[str, Any]
) -> dict[str, Any]:
    """Decode one concrete TPCS branch through that branch's placements."""
    slot = next(
        (slot for slot in layout.columns if isinstance(slot.contributor, RelationalDocument)), None
    )
    if slot is None or slot.column not in row:
        return row
    document = decode_stored(row[slot.column])
    materialized = {key: value for key, value in row.items() if key != slot.column}
    entities = {entity.canonical_name: entity for entity in case.model.entities}
    for candidate in case.model.storage_layout.tables:
        if candidate.contribution(slot.contributor) is None:
            continue
        for address, placement in candidate.placements.items():
            if len(address.path) != 1 or not isinstance(placement, DocumentPath):
                continue
            declaration = entities[address.owner]
            name = address.path[0]
            attribute = next(
                (item for item in declaration.attributes if item["name"] == name), None
            )
            if attribute is not None:
                materialized.setdefault(attribute["column"], None)
    for address, placement in layout.placements.items():
        if len(address.path) != 1 or not isinstance(placement, DocumentPath):
            continue
        entity = entities[address.owner]
        name = address.path[0]
        attribute = next((item for item in entity.attributes if item["name"] == name), None)
        occurrence = next((item for item in entity.value_objects if item["name"] == name), None)
        stored = _document_value(document, placement.path)
        if attribute is not None:
            materialized[attribute["column"]] = decode_leaf(attribute["type"], stored)
        elif occurrence is not None:
            materialized[occurrence["column"]] = stored
    return materialized
