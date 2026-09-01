"""Grading a table-per-concrete-subtype abstract read's `union all` against the layout.

An abstract read of a table-per-concrete-subtype position lowers to one `union all`
branch per concrete Table, and the golden text is where that lowering is witnessed. The
storage layout settles the physical facts — the branch count and order, the Table each
branch reads, the one logical contributor sequence every branch aligns to, and each
branch's slot-or-absence entry per contributor. What this module asserts is the SQL
layered over them: the collision-safe result aliases, a real column reference where a
branch owns the slot and a `cast(null as <declared type>)` placeholder in that dialect's
type where it does not, each branch's `familyVariant` literal, and the derived-table
wrap an ordered or limited read applies its tail against.

Every assertion is read from the golden text rather than from a sample row, so a
zero-row abstract read still witnesses a mis-ordered branch, a dropped superset column,
an untyped placeholder, or a wrong literal. The rows themselves are materialized by
:mod:`.materialize`, which owns the Relational Document Layout placements this module
does not derive and states them as arguments.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import sqlglot
from sqlglot import exp

from .._declared_contributor import DeclaredContributor
from ..case import Case, Model
from ..case_assertions import CaseFailure
from ..ddl_builder import declared_contributors, placeholder_cast_type
from ..inheritance import Family
from ..sql_canonical import NonCanonicalError, sqlglot_dialect
from ..sql_wrapped_union import WrapFacts, WrapOrderKey, wrapped_union_source
from ..storage_layout import (
    ColumnSlot,
    ColumnTier,
    DocumentPath,
    PositionBranch,
    PositionColumn,
    PositionLayoutView,
    ValueObjectContributor,
)
from .execute import (
    assert_union_all_only,
    document_presence_ordinals,
    projection_expr,
    string_literal_value,
    union_branch_selects,
)

# The projected output column that carries the table-per-concrete-subtype
# `familyVariant` literal per `union all` branch (the settled TPCS asymmetry,
# m-sql): unlike table-per-hierarchy — which projects the RAW tag column and
# derives `familyVariant` at materialization — TPCS has no tag column, so each
# branch projects a subtype-name literal aliased to this column, which the oracle
# renames to `familyVariant` after asserting the branch shape.
VARIANT_COLUMN = "family_variant"


def result_aliases(columns: list[str]) -> list[str]:
    """The output name each superset column is projected under, in column order.

    A column two concretes spell the same way stands for two different members, so it
    cannot be projected under that spelling by both branches: every occurrence of a
    repeated spelling — and any collision with :data:`VARIANT_COLUMN` — takes a
    generated ``parallax_attr_<n>`` alias instead, allocated so it can collide with no
    physical spelling in the position. A spelling only one column carries keeps it, so
    the ordinary read reads as it was authored.
    """
    counts = {column: columns.count(column) for column in set(columns)}
    allocated = set(columns) | {VARIANT_COLUMN}
    aliases: list[str] = []
    next_internal = 0
    for column in columns:
        if counts[column] == 1 and column != VARIANT_COLUMN:
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
) -> list[DeclaredContributor | None]:
    """Each position column's declared neutral type and length bound, in column order.

    The only declaration residue an abstract-read `union all` shape needs: the layout
    settles composition and never a SQL type, yet a branch owning no slot for a
    contributor must still render `cast(null as <declared type>)` in the same neutral
    type the branch that owns it was provisioned with.
    """
    declarations = declared_contributors(model)
    return [declarations.get(column.contributor) for column in columns]


def is_instance_form(case: Case) -> bool:
    """Whether a read case's authored result form is the object lane.

    `m-case-format` *Read result form*: a ``then.graph`` / ``then.graphs``
    observation is instance-form and ``then.rows`` is row-form, which is the same
    partition the read dispatch routes on.
    """
    return case.expected_graph is not None or case.expected_graphs is not None


def projected_position_ordinals(
    view: PositionLayoutView, *, instance_form: bool, document_resident: bool
) -> tuple[int, ...]:
    """The position-column ordinals a read of the given result form projects.

    Every non-`Document` contributor is projected in both result forms. A
    `Document` one is not: a top-level Value Object occurrence's own Structured
    Column reaches only an instance-form read (`m-sql` *Read projection*, rule 3),
    and a Relational Document Layout's shared Structured Column reaches a row-form
    read as well, but only to produce a member the layout placed inside it (rule
    5) — and in a row-form read the members requested are the Attributes alone,
    rule 3 having already omitted every occurrence. So the superset a `union all`
    branch aligns to, and the result aliases allocated over it, are form-dependent
    wherever the position holds a `Document` contributor.

    *document_resident* is that last fact — whether any branch's concrete places an
    Attribute of its own inside the shared Structured Column — and it is stated by the
    caller, because the layout's member placement is the materializer's vocabulary and
    the `union all` shape is this module's. *instance_form* is stated the same way: a
    read case states it through the result member it authored
    (:func:`is_instance_form`), while a navigated position is one by classification.
    """
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
    placeholder_types: list[DeclaredContributor | None],
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
            placeholder_cast_type(
                placeholder_type.neutral_type,
                placeholder_type.max_length,
                dialect,
            ),
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


def branch_variants(
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


def _order_keys(
    case: Case,
    view: PositionLayoutView,
    branch_variants: list[tuple[PositionBranch, str]],
    ordinals: tuple[int, ...],
    aliases: list[str],
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
        placements = [branch.placements[indices[0]] for branch, _ in branch_variants]
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
                aliases[index]
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


def assert_union_shape(
    case: Case,
    view: PositionLayoutView,
    branch_variants: list[tuple[PositionBranch, str]],
    *,
    document_resident: bool,
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
    case's own result form projects (:func:`projected_position_ordinals`), so a
    row-form read of a position holding a `Document` slot is graded on omitting it
    rather than on carrying it.

    An ordered or limited read additionally wraps its union, and the wrap's own shape
    is graded against the same facts: which result alias holds a `Document`, and the
    Sort Keys and cap the Object Query authored, each rendered as the dialect under
    test spells it.
    """
    ordinals = projected_position_ordinals(
        view, instance_form=is_instance_form(case), document_resident=document_resident
    )
    superset = [view.column_spellings[ordinal] for ordinal in ordinals]
    position_types = _placeholder_types(case.model, view.columns)
    placeholder_types = [position_types[ordinal] for ordinal in ordinals]
    aliases = result_aliases(superset)
    expected_columns = [*aliases, VARIANT_COLUMN]
    facts = WrapFacts(
        document_aliases=frozenset(
            alias
            for alias, ordinal in zip(aliases, ordinals, strict=True)
            if view.columns[ordinal].tier is ColumnTier.DOCUMENT
        ),
        order_keys=_order_keys(case, view, branch_variants, ordinals, aliases),
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
        if len(branches) != len(branch_variants):
            raise CaseFailure(
                f"{case.path.name}: table-per-concrete-subtype abstract read lowers to "
                f"{len(branch_variants)} `union all` branch(es) (the effective concrete "
                f"set {[name for _, name in branch_variants]}), but the {dialect} golden "
                f"has {len(branches)}."
            )
        for position, (branch, (position_branch, name)) in enumerate(
            zip(branches, branch_variants, strict=True)
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
