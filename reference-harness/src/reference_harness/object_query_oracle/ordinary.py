"""Observing one accepted ordinary read, from its first refusal to its last comparison."""

from __future__ import annotations

from typing import Any

import sqlglot
from sqlglot import exp

from ..case import Case, Entity
from ..case_assertions import CaseFailure, rows_equal
from ..inheritance import STRATEGY_TPCS, STRATEGY_TPH
from ..sql_canonical import sqlglot_dialect
from . import execute, graph, includes, materialize, stream
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
        _assert_stream(case, reader)
        return
    if includes.query_has_includes(case.object_query):
        _assert_deep_fetch(case, reader)
        return
    if case.expected_graphs is not None:
        _assert_graphs(case, reader)
        return
    if case.expected_graph is not None:
        _assert_single_statement_graph(case, reader)
        return
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


def _assert_stream(case: Case, reader: ReadExecutor) -> None:
    """Assert a streamed READ CASE: the delivery its pages state, then its result.

    The delivery itself — the page partition and the properties derived from it —
    is :func:`..stream.deliver_stream`'s; what this adds is the case-level result
    oracle a `read` shape carries. The published roots are the concatenation of
    the pages', compared to the case's own result member exactly as an eager
    read's are, and to the independent ``then.referenceSql`` row set beside it.

    A milestone-set delivery states ``then.graphs`` instead, and is graded by the
    same partition oracle the eager milestone-set read is: a delivery publishes
    roots rather than graphs, each standing at its own edge pin, so the graphs are
    recovered from the delivered roots' own edge coordinates and every
    disjointness rule the eager form states holds unchanged.
    """
    dialect = reader.dialect
    delivered = stream.deliver_stream(case, reader, "then.statements")
    root_entity = _graphs_root_entity(case)
    graph_specs = case.expected_graphs
    if graph_specs is not None:
        graph.assert_milestone_partition(
            case, root_entity, delivered.root_rows, delivered.nodes, graph_specs
        )
    else:
        assembled = {root_entity.name: delivered.nodes}
        expected = case.expected_graph or {}
        if not graph.graphs_equal(assembled, expected, case.model):
            raise CaseFailure(
                f"{case.path.name}: delivered graph != then.graph.\n"
                f"  delivered: {assembled!r}\n"
                f"  expected:  {expected!r}"
            )

    reference_sql = case.reference_sql_for(dialect)
    if reference_sql is not None:
        reference = materialize.materialize_family_variant(
            case, execute.reference_rows(reader, reference_sql)
        )
        root_projection = [execute.project_like(row, delivered.root_rows) for row in reference]
        if not rows_equal(root_projection, delivered.root_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: referenceSql root rows != the delivered root rows.\n"
                f"  reference: {reference!r}\n"
                f"  delivered: {delivered.root_rows!r}"
            )


def _assert_deep_fetch(case: Case, reader: ReadExecutor) -> None:
    """Assert an Include-bearing read: one root statement, one per level, one graph.

    The contract proven here is N+1 elimination: the root plus at most one
    statement per relationship level, never one per parent. Every level is
    instance-form and fans its own Structured Column out into its own members, so
    what a node CARRIES follows the layout while the join columns the levels are
    keyed on stay direct under either one.

    The independent ``referenceSql`` oracle grades the ROOT row set alone: a deep
    fetch's assembled graph is the thing under test, and a second naive statement
    for it would be a second assembly rather than an independent formulation.
    """
    dialect = reader.dialect
    query = case.object_query
    statements = case.golden_statements(dialect)
    steps = includes.fetch_steps(case.model, query)

    # Level 0: the root query. An abstract-target root resolves each row's own
    # concrete subtype into `familyVariant` exactly as a flat abstract read does —
    # both because the graph's root nodes carry it and because a path-root guard
    # selects the participating roots by it.
    root_rows = materialize.materialize_target_tph_document_layout(
        case,
        execute.query_rows(case, reader, statements[0], case.statement_binds(0, dialect)),
        include_value_objects=True,
    )
    root_rows = materialize.materialize_family_variant(case, root_rows)

    levels = [
        (statements[index], case.statement_binds(index, dialect))
        for index in range(1, len(statements))
    ]
    executed = includes.execute_fetch_levels(
        case, reader, "then.statements", query, steps, root_rows, levels
    )
    includes.refuse_unused_levels(case, "then.statements", dialect, executed, len(levels))

    assembled = graph.assemble_graph(case, query, steps, root_rows, executed.children_by_hop)
    expected = case.expected_graph or {}
    if not graph.graphs_equal(assembled, expected, case.model):
        raise CaseFailure(
            f"{case.path.name}: assembled graph != then.graph.\n"
            f"  assembled: {assembled!r}\n"
            f"  expected:  {expected!r}"
        )

    reference_sql = case.reference_sql_for(dialect)
    if reference_sql is not None:
        reference = materialize.materialize_family_variant(
            case, execute.reference_rows(reader, reference_sql)
        )
        root_projection = [execute.project_like(row, root_rows) for row in reference]
        if not rows_equal(root_projection, root_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: referenceSql root rows != then.statements root rows.\n"
                f"  reference: {reference!r}\n"
                f"  golden:    {root_rows!r}"
            )


def _graphs_root_entity(case: Case) -> Entity:
    """The entity a graph-publishing read is rooted at.

    The eager milestone-set terminal and the streamed one both publish roots of
    the read's own query ``target``: a milestone-set graph read (`then.graphs`) is
    a flat temporal read — history with Includes is out of scope for both v1
    slices — and a delivery's roots are the root level of its pages.
    """
    return case.model.entity(case.object_query["target"])


def _assert_graphs(case: Case, reader: ReadExecutor) -> None:
    """Assert a `history` / `asOfRange` read's per-milestone edge-pinned graphs.

    The single root statement returns the FULL milestone set in one query. Each
    ``then.graphs`` entry declares a milestone ``pin`` — its OWN edge coordinate
    (the milestone's from-instant per as-of axis), never a shared root pin — and
    the graph materialized at it, so ``history`` yields one independently
    edge-pinned graph per milestone and ``asOfRange`` one per overlapping
    milestone. ``referenceSql`` independently cross-checks the whole milestone set,
    and the partition rules themselves live in :func:`..graph.assert_milestone_partition`
    because a streamed delivery reaches the same interpretation.

    History with deep-fetch Includes is out of scope for both v1 slices, so a graph
    carries no child levels: a graph node authored with a nested relationship key
    would fail the value comparison, since the root-only assembly carries only the
    root projection.
    """
    dialect = reader.dialect
    statements = case.golden_statements(dialect)
    graph_specs = case.expected_graphs or []
    root_entity = _graphs_root_entity(case)

    # Level 0: the single history / asOfRange query — every milestone in one round trip.
    root_rows = execute.query_rows(case, reader, statements[0], case.statement_binds(0, dialect))

    reference_sql = case.reference_sql_for(dialect)
    if reference_sql is not None:
        reference = [
            execute.project_like(row, root_rows)
            for row in execute.reference_rows(reader, reference_sql)
        ]
        if not rows_equal(reference, root_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: referenceSql rows != then.statements milestone rows.\n"
                f"  reference: {reference!r}\n"
                f"  golden:    {root_rows!r}"
            )

    graph.assert_milestone_partition(
        case,
        root_entity,
        root_rows,
        [graph.graph_node(case.model, root_entity, row) for row in root_rows],
        graph_specs,
    )


def _assert_single_statement_graph(case: Case, reader: ReadExecutor) -> None:
    """Assert a top-level ``then.graph`` read with no Includes and no milestone set.

    Two independently-conditional kinds of case route here, and either, both, or
    neither may apply:

    * **A value-object graph read** (m-value-object): the single golden statement
      projects the owning entity including its structured-document column(s), and
      each row's occurrence column decodes into its declared nested to-one /
      to-many projection — the proof that nested values arrive WITH the owner
      rather than through a deep fetch. A no-op for an entity that declares no
      value objects.
    * **An abstract-target inheritance read** (m-inheritance): additionally
      materializes ``familyVariant`` through the same oracle the row-form path
      uses, and then narrows each node to its own concrete variant's declared
      columns — the instance-form per-variant node shape, distinct from row-form's
      unnarrowed superset. A no-op for a concrete-target read.

    A ``referenceSql`` oracle independently pins the matched row SET, identity
    columns only with the value-object columns stripped, so the filter that
    selected the rows is checked by a different formulation without routing the
    JSON document through row comparison.
    """
    dialect = reader.dialect
    (golden,) = case.golden_statements(dialect)
    entity = case.model.entity(case.object_query["target"])

    # `familyVariant` materialization happens on the RAW rows (also what the
    # referenceSql identity check below compares against — the matched ROW SET,
    # unrelated to per-variant field narrowing); the per-variant COLUMN narrowing
    # is a separate, graph-assembly-only step.
    rows = graph.instance_form_root_rows(
        case, reader, entity, golden, case.statement_binds(0, dialect)
    )
    narrowed = materialize.narrow_to_variant_columns(case, rows)
    assembled = {entity.name: [graph.graph_node(case.model, entity, row) for row in narrowed]}

    expected = case.expected_graph or {}
    if not graph.graphs_equal(assembled, expected, case.model):
        raise CaseFailure(
            f"{case.path.name}: materialized graph != then.graph.\n"
            f"  assembled: {assembled!r}\n"
            f"  expected:  {expected!r}"
        )

    reference_sql = case.reference_sql_for(dialect)
    if reference_sql is not None:
        identity_rows = [materialize.reference_identity_row(row) for row in rows]
        # An abstract-target inheritance read's naive reference SQL projects the
        # RAW tag column too (it is an independently-formulated but otherwise
        # equivalent selection); materialize familyVariant on it the same way,
        # so this identity check compares apples to apples (m-inheritance).
        reference = materialize.materialize_family_variant(
            case, execute.reference_rows(reader, reference_sql)
        )
        if not rows_equal(reference, identity_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: referenceSql rows != golden rows (identity).\n"
                f"  reference: {reference!r}\n"
                f"  expected:  {identity_rows!r}"
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
