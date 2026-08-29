"""Observing one accepted ordinary read, from its first refusal to its last comparison."""

from __future__ import annotations

from typing import Any

import sqlglot
from sqlglot import exp

from ..case import Case
from ..case_assertions import CaseFailure, rows_equal
from ..inheritance import STRATEGY_TPCS, STRATEGY_TPH
from ..sql_canonical import sqlglot_dialect
from . import execute, materialize
from .executor import ReadExecutor


def assert_case_read(case: Case, reader: ReadExecutor) -> None:
    """Assert every observable an accepted read case authored.

    Requires
        the case is accepted and read-shaped; the runner has already asserted
        schema, normalization, serde, equivalent encodings, query inheritance, and
        round-trip count; the database *reader* reads has been provisioned.
    Guarantees
        every authored observable has been compared before this returns. Raises
        :class:`CaseFailure` on any authored or local interface violation, with the
        case path in the message. A driver exception raised by *reader* propagates
        unchanged, so infrastructure failure is never reported as a mismatch.

    Delivery is chosen here and stated nowhere else: a caller supplies a case and a
    reader, never a strategy.
    """
    # The branch order is a precedence declaration: streaming wins over Includes,
    # Includes over milestone sets, milestone sets over single graphs, and everything
    # over flat rows. Delivery precedes every result member because the delivery, not
    # the member, decides how `then.statements` reads.
    if case.is_streamed:
        raise NotImplementedError("streamed delivery")
    if case.object_query.get("includes"):
        raise NotImplementedError("deep fetch")
    if case.expected_graphs is not None:
        raise NotImplementedError("milestone-set graphs")
    if case.expected_graph is not None:
        raise NotImplementedError("single-statement graph")
    _assert_flat_equivalence(case, reader)


def _assert_flat_equivalence(case: Case, reader: ReadExecutor) -> None:
    """Assert a row-form read: one golden statement, materialized, against ``then.rows``.

    The two shape refusals run first and issue no SQL: an authored golden whose
    lowering is already wrong must fail the case rather than reach a database.
    """
    dialect = reader.dialect
    (golden,) = case.golden_statements(dialect)

    _assert_tph_document_partition_shape(case, dialect)

    # Temporal composition (m-sql / m-temporal-read): the dedicated temporal-only
    # table-per-concrete-subtype witness carries each branch's selected temporal
    # contribution, while history contributes no predicate or bind.
    _assert_temporal_only_union_binds(case, dialect)

    golden_rows = execute.query_rows(case, reader, golden, case.statement_binds(0, dialect))
    # Relational Document Layout (m-storage-layout / m-sql): the golden projects the
    # shared Structured Column once and the row-form result is the scalars it
    # carries, under the names a Column of each would have had.
    golden_rows = materialize.materialize_target_tph_document_layout(
        case, golden_rows, include_value_objects=False
    )
    expected = case.expected_rows
    tolerance = case.tolerance

    # Abstract-target inheritance read oracle (m-inheritance / m-sql, resolved Q6):
    # the golden SQL projects the RAW tag column; `familyVariant` is materialized
    # from the tag metadata map, never projected as SQL.
    golden_rows = materialize.materialize_family_variant(case, golden_rows)

    if not rows_equal(golden_rows, expected, tolerance):
        raise CaseFailure(
            f"{case.path.name}: then.statements ({dialect}) rows != then.rows.\n"
            f"  golden:   {golden_rows!r}\n"
            f"  expected: {expected!r}"
        )

    reference_sql = case.reference_sql_for(dialect)
    if reference_sql is not None:
        reference = materialize.materialize_target_tph_document_layout(
            case, execute.reference_rows(reader, reference_sql), include_value_objects=False
        )
        reference = materialize.materialize_family_variant(case, reference)
        if not rows_equal(reference, expected, tolerance):
            raise CaseFailure(
                f"{case.path.name}: referenceSql rows != then.rows.\n"
                f"  reference: {reference!r}\n"
                f"  expected:  {expected!r}"
            )


def _assert_tph_document_partition_shape(case: Case, dialect: str) -> None:
    """Grade a TPH document `union all` as one tag-filtered branch per variant."""
    position = materialize.abstract_family_position(case, case.object_query)
    if position is None or position.strategy != STRATEGY_TPH:
        return
    family, target_name = position.family, position.target
    target = case.model.entity(target_name)
    if not materialize.document_layout_members(case, target)[0]:
        return
    statements = case.golden_statements(dialect)
    if not statements or " union all " not in statements[0]:
        return

    tree = sqlglot.parse_one(statements[0], read=sqlglot_dialect(dialect))
    execute.assert_union_all_only(case, tree)
    partition = next(tree.find_all(exp.SetOperation), tree)
    branches = execute.union_branch_selects(partition)
    effective = family.canonical_concrete_order(
        materialize.read_effective_set(case, family, target_name)
    )
    if len(branches) != len(effective):
        raise CaseFailure(
            f"{case.path.name}: variant-partitioned table-per-hierarchy document read "
            f"has {len(branches)} branches, expected one for each selected concrete "
            f"variant {effective} (m-sql)."
        )
    tag_column = family.tag_column_of(target_name)
    table = target.table
    if case.path.stem.startswith("m-read-lock-"):
        outer_tables = [source.name for source in tree.find_all(exp.Table)]
        base_occurrences = [name for name in outer_tables if name == table]
        if (
            not outer_tables
            or outer_tables[0] != table
            or len(base_occurrences) != len(branches) + 1
        ):
            raise CaseFailure(
                f"{case.path.name}: locking TPH partition must join one outer base Table "
                f"{table!r} to its {len(branches)} derived variant branches, got "
                f"{outer_tables!r} (m-sql / m-read-lock)."
            )
    for position_index, (branch, concrete) in enumerate(zip(branches, effective, strict=True)):
        tables = [source.name for source in branch.find_all(exp.Table)]
        if not tables or tables[0] != table:
            raise CaseFailure(
                f"{case.path.name}: TPH document branch {position_index} ({concrete}) reads "
                f"{tables[0] if tables else None!r}, expected shared Table {table!r}."
            )
        guarded = any(
            any(
                isinstance(predicate, exp.EQ)
                and any(
                    isinstance(column, exp.Column) and column.name == tag_column
                    for column in predicate.find_all(exp.Column)
                )
                for predicate in where.find_all(exp.EQ)
            )
            for where in branch.find_all(exp.Where)
        )
        if not guarded:
            raise CaseFailure(
                f"{case.path.name}: TPH document branch {position_index} ({concrete}) has no "
                f"equality guard on discriminator {tag_column!r}; its casts could evaluate "
                "against a sibling variant (m-sql)."
            )


def _is_temporal_only_read(query: Any) -> bool:
    """Whether a query selects and shapes on nothing but its Temporal Selections.

    Every clause that contributes a bind of its own disqualifies it, because the
    per-branch bind vector this predicate gates is derived from the Temporal
    Selections alone: a user predicate, result narrowing, an ordering, and the cap
    each add binds the derivation does not model.
    """
    if not isinstance(query, dict):
        return False
    return (
        query.get("predicate") == {"all": {}}
        and not query.get("narrowTo")
        and not query.get("orderBy")
        and query.get("limit") is None
    )


def _assert_temporal_only_union_binds(case: Case, dialect: str) -> None:
    """Assert the temporal contributions of the abstract-TPCS temporal witness.

    This deliberately narrow m-sql / m-temporal-read oracle applies only to
    ``m-inheritance-093`` while its query filters on nothing but Temporal Selections.
    It derives each branch's temporal predicates in Valid-Time-first order; ``history``
    contributes none. Canonical SQL/bind goldens, compile sweeps, execution checks, and
    focused compatibility cases own complete predicate, projection, and result-clause
    bind vectors. A no-op for every case outside that temporal-only boundary.
    """
    if not case.path.stem.startswith("m-inheritance-093-") or not _is_temporal_only_read(
        case.object_query
    ):
        return
    position = materialize.abstract_family_position(case, case.object_query)
    if position is None or position.strategy != STRATEGY_TPCS:
        return
    family = position.family
    ordered = family.canonical_concrete_order(
        materialize.read_effective_set(case, family, position.target)
    )
    branch_entities = [case.model.entity(name) for name in ordered]
    if not any(entity.is_temporal for entity in branch_entities):
        return
    selections = execute.query_temporal_selections(case.object_query)
    expected: list[Any] = []
    for entity in branch_entities:
        expected.extend(execute.expected_temporal_suffix(case, entity, selections))
    actual = case.statement_binds(0, dialect)
    if len(actual) != len(expected) or not all(
        execute.bind_value_equal(want, got) for want, got in zip(expected, actual, strict=False)
    ):
        raise CaseFailure(
            f"{case.path.name}: temporal-only table-per-concrete-subtype abstract read binds "
            f"{actual!r} != temporal contributions {expected!r} — selected temporal "
            f"predicates apply per branch in Valid-Time-first order, history contributes "
            f"none, and branches repeat in alphabetical order {ordered} "
            "(m-sql / m-temporal-read)."
        )
