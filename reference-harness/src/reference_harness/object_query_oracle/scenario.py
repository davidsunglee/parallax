"""Observing the reads of one Unit Work Scenario, one authored step at a time.

A Scenario states its reads as steps, and every fact a step's observation needs —
which operation it is, which earlier steps it names, which relationship it walks,
which identity it claims — is already written in the step. So the operation here
takes an index and a reader and nothing else: repeating that intent as interface
parameters would put a second authority on what a step means beside the case that
authored it.

Four workflows stay behaviorally distinct behind the one operation, because their
database behavior differs and a smaller interface must not collapse it. A query
runs its own golden statement and then its own Include levels. A relationship
`load` resolves a deferred fetch, one statement per coordinate group or level. A
named reuse returns the very rows an earlier step published, issuing nothing. And
an `access` navigates the view an earlier read materialized, issuing nothing —
unless it is the first access of a query-backed list, which resolves the list once
by following the step's own ``on`` index back to the constructor's Object Query.

What is NOT here is Scenario orchestration: step order, reader selection,
transaction lifecycle, writes, boundary actions, unresolved list construction, and
accounting across the whole Scenario all stay with the runner, which calls this
once per read-bearing step with the reader that step's lifecycle selected.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from typing import Any

from ..case import Case, Entity, frozen_view
from ..case_assertions import CaseFailure, rows_equal
from ..predicate_write_validate import requires_predicate_write_materialization
from ..serde import canonical
from . import execute, graph, includes, materialize, retained, stream
from .executor import ReadExecutor

# The m-case-format lifecycle verbs that READ: a `load` triggers a deferred fetch
# and an `access` reads an already-loaded set. Every other verb either commits
# buffered DML or acts in memory, and belongs to Scenario orchestration.
_ACTION_READ_VERBS = frozenset({"load", "access"})


class ScenarioReads:
    """Every accepted read of one Unit Work Scenario, and what those reads retain.

    Requires
        one instance per Compatibility Case; the runner calls every step this
        owns, in Scenario order, exactly once, with the reader Scenario lifecycle
        selected for that step. The steps the RUNNER owns are never passed: a
        write, an action whose verb is not ``load`` or ``access``, and the
        zero-round-trip construction of a query-backed list that has not resolved.
    Guarantees
        a step's observables are asserted atomically: what it published is retained
        under its own index only once every observable it states has passed, so a
        failed step leaves nothing behind for a later step to read. An ineligible
        index, a repeated assertion, or a reference to an observation no asserted
        step produced is refused locally. Every failure names the case path and the
        step index; a driver exception passes through unchanged.
    """

    def __init__(self, case: Case) -> None:
        self._case = case
        self._retained: dict[int, retained.Observation] = {}

    def assert_step(self, step_index: int, reader: ReadExecutor) -> None:
        """Assert the observables of the Scenario read step at *step_index*.

        Which of the four read workflows runs is read off the step: a ``stream``
        member makes it a delivery, listed ``statements`` make it a query or a
        resolving load, a read-verb ``action`` over an already-materialized view
        makes it an access, and a step that lists nothing and names an earlier one
        is a reuse.
        """
        with self._reported_against(step_index):
            step = self._eligible_step(step_index)
            pairs = _statement_pairs(step, reader.dialect)

            if "stream" in step:
                observation = self._deliver(step_index, step, reader)
            elif "action" in step:
                observation = self._act(step_index, step, pairs, reader)
            elif pairs:
                observation = self._query(step_index, step, pairs, reader)
            else:
                observation = retained.Observation(
                    rows=self._reused_rows(step_index, step),
                    entity=self._read_entity(step_index),
                    includes=None,
                )

            self._assert_row_observables(step_index, step, observation.rows)
            self._assert_graph_observable(step_index, step, observation)
            # Publication is the LAST thing a step does, so a step that failed an
            # observable published nothing: a later step naming it is refused for
            # naming an unobserved step rather than answered with rows nobody graded.
            self._retained[step_index] = observation

    # --- eligibility ---------------------------------------------------------

    @contextmanager
    def _reported_against(self, step_index: int) -> Iterator[None]:
        """Name the active step on every authored failure raised inside.

        A step's observation is graded by the same delivery, materialization,
        Include, and graph oracles an ordinary read's is, and those speak of the
        read they were handed rather than the Scenario position it occupies. So
        the position is added here, once, at the boundary that knows it — rather
        than threaded through every oracle beneath it as a second parameter.

        A driver exception is not an authored failure and passes through
        untouched, and a failure already naming both the case and this step — a
        delivery pointed at ``scenario[i].statements``, an Include level at
        ``when.scenario[i].statements`` — is re-raised as it was written.
        """
        try:
            yield
        except CaseFailure as failure:
            marker = f"scenario[{step_index}]"
            prefix = f"{self._case.path.name}: "
            message = str(failure)
            if message.startswith(prefix) and marker in message:
                raise
            detail = message[len(prefix) :] if message.startswith(prefix) else message
            raise CaseFailure(f"{prefix}{marker} {detail}") from failure

    def _eligible_step(self, step_index: int) -> dict[str, Any]:
        """The step at *step_index*, refused unless this instance owns it once.

        The runner routes what IT owns and sends everything else here, so these
        are defensive: a duplicate assertion would let a retained observation be
        silently overwritten, and a runner-owned step reaching here would grade
        DML or an unresolved construction as a read.
        """
        case = self._case
        scenario = case.scenario
        if not 0 <= step_index < len(scenario):
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}] is not a step of this case, "
                f"which declares {len(scenario)}."
            )
        if step_index in self._retained:
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}] is asserted twice. A Scenario "
                f"step is observed once, in Scenario order, so a second assertion would "
                f"replace the observation the steps naming it already read."
            )
        step = scenario[step_index]
        refusal = _runner_owned(step)
        if refusal is not None:
            raise CaseFailure(f"{case.path.name}: scenario[{step_index}] {refusal}")
        return step

    # --- the four read workflows ---------------------------------------------

    def _deliver(
        self, step_index: int, step: Mapping[str, Any], reader: ReadExecutor
    ) -> retained.Observation:
        """A streamed read step: its whole ``statements`` list is one delivery's pages.

        The step is handed to the placement-neutral delivery as the read it is,
        so the pages are graded exactly as an ordinary streamed read's are, and
        what it publishes is every root the delivery handed over across every
        page. Inside a `uow` group that runs on the group's own held session, so
        each page observes the writes the group buffered before it.

        A delivery hands back roots it has ALREADY materialized — fanned out of a
        Relational Document Layout and carrying ``familyVariant`` in place of the
        raw tag — so what is left here is the decode a delivery leaves to its
        caller: the owner's own value-object projection, taken at each root's own
        concrete variant, which an eager step's rows carry too and which the
        reference oracle below must not see.

        A streamed step states no ``expectGraph`` — what it publishes is roots,
        page after page — so it retains no view for a later access to navigate.
        """
        entity = self._read_entity(step_index)
        step_read = _step_as_read(self._case, step_index)
        delivered = stream.deliver_stream(
            step_read, reader, f"scenario[{step_index}].statements"
        ).root_rows
        reference = self._reference_rows(step, reader)
        if reference is not None:
            materialized = materialize.materialize_family_variant(step_read, reference)
            self._assert_reference_rows(
                step_index,
                [execute.project_like(row, delivered) for row in materialized],
                delivered,
            )
        rows = (
            delivered
            if entity is None
            else [
                materialize.materialize_variant_owner_node(self._case.model, entity, row)
                for row in delivered
            ]
        )
        return retained.Observation(rows=rows, entity=entity, includes=None)

    def _query(
        self,
        step_index: int,
        step: Mapping[str, Any],
        pairs: list[tuple[str, list[Any]]],
        reader: ReadExecutor,
    ) -> retained.Observation:
        """A find: one root statement, then the levels its own Include Paths declare.

        m-unit-work finds are single-statement at the root, so the first pair is
        the read and anything after it belongs to a child level. The independent
        ``referenceSql`` oracle runs on the SAME reader, before materialization,
        so a grouped find's mid-transaction state is what it observes too and the
        value-object columns never route through that identity comparison.
        """
        case = self._case
        entity = self._read_entity(step_index)
        if entity is None:
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}] find step resolved no read entity"
            )
        statement, binds = pairs[0]
        step_read = _step_as_read(case, step_index)
        rows = execute.query_rows(case, reader, statement, binds)
        reference = self._reference_rows(step, reader)
        if reference is not None:
            self._assert_reference_rows(step_index, reference, rows)
        # Under Relational Document Layout the fan-out comes FIRST, because it is
        # what puts each occurrence back under the very column name the projection
        # below reads it from — after which that projection is layout-blind. Both
        # decode against DECLARATIONS, which an abstract position does not carry for
        # its concretes' own members, so each stands at the row's own variant: the
        # fan-out resolves one itself, the projection reads the `familyVariant`
        # materialized between them.
        rows = materialize.materialize_target_tph_document_layout(
            step_read, rows, include_value_objects=True
        )
        rows = materialize.materialize_family_variant(step_read, rows)
        rows = [materialize.materialize_variant_owner_node(case.model, entity, row) for row in rows]
        return retained.Observation(
            rows=rows,
            entity=entity,
            includes=self._run_step_includes(step_index, step, rows, pairs, reader),
        )

    def _act(
        self,
        step_index: int,
        step: Mapping[str, Any],
        pairs: list[tuple[str, list[Any]]],
        reader: ReadExecutor,
    ) -> retained.Observation:
        """A ``load`` or an ``access``, which differ in whether they issue SQL.

        A `load` resolves a deferred fetch and lists one statement per lowered
        coordinate group or per level, whose rows are aggregated in listed order.
        So does the FIRST access of a query-backed list, which resolves the list
        the construction step built by following this step's own ``on`` index
        back to that step's authored Object Query — the read is resolved from the
        case, never handed across as an unresolved value. Every later access
        issues nothing: a snapshot is closed-world and a populated list is already
        populated, so it answers the rows its source already published.
        """
        case = self._case
        _assert_action_on(case, step_index, step, pairs)
        entity = self._read_entity(step_index)
        if not pairs:
            return retained.Observation(
                rows=self._reused_rows(step_index, step), entity=entity, includes=None
            )
        rows: list[dict[str, Any]] = []
        for statement, binds in pairs:
            rows.extend(execute.query_rows(case, reader, statement, binds))
        if entity is not None:
            # A freshly-resolved load / first access materializes the value-object
            # document of the entity it navigated TO, resolved per step so a
            # value-object-bearing child decodes with its OWN composite schema —
            # and, for a row naming a concrete variant, with that variant's rather
            # than the navigated position's. A polymorphic position names that
            # variant with a raw tag or a branch literal, neither of which is a
            # result field, so it is derived first: what the step publishes is
            # `familyVariant`, and it is also what the Relational Document Layout
            # fan-out and the owner-node decode below both stand at. A resolved
            # list is derived as the whole read it is — one call ordering the
            # fan-out ahead of the tag it already resolves itself — and a navigated
            # position as the position it stands at, per row, because a multi-hop
            # load aggregates levels whose Structured Columns differ.
            list_read = _resolved_list_read(case, step_index, step)
            if list_read is None:
                rows = materialize.materialize_navigated_family_variant(case, entity, rows)
                rows = [
                    materialize.materialize_document_layout(
                        case,
                        materialize.variant_entity(case.model, entity, row),
                        [row],
                        include_value_objects=True,
                    )[0]
                    for row in rows
                ]
            else:
                rows = materialize.materialize_target_tph_document_layout(
                    list_read, rows, include_value_objects=True
                )
                rows = materialize.materialize_family_variant(list_read, rows)
            rows = [
                materialize.materialize_variant_owner_node(case.model, entity, row) for row in rows
            ]
        return retained.Observation(rows=rows, entity=entity, includes=None)

    def _reused_rows(self, step_index: int, step: Mapping[str, Any]) -> list[dict[str, Any]]:
        """The rows a zero-round-trip step reuses from the earlier step it names.

        A cache hit, a re-access, or a repeated find returns the SAME rows an
        earlier step published, named by ``sameObjectAs`` or — on an action step —
        by its ``on``. The named source MUST be an earlier step this instance
        already observed: a forward, self, or unobserved index is an authoring
        error rather than an empty set, which would let the step's own identity
        and ``expectRows`` assertions pass against nothing.
        """
        case = self._case
        named = step.get("sameObjectAs", step.get("on"))
        source = (named[0] if named else -1) if isinstance(named, list) else named
        if not isinstance(source, int) or not 0 <= source < step_index:
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}] reuses prior rows from an "
                f"UNRESOLVED source {source!r} — a zero-round-trip cache hit / "
                f"re-access MUST name an EARLIER resolved step (0 <= source < "
                f"{step_index}). An empty reuse here would let its identity / "
                f"expectRows assertion pass vacuously."
            )
        return self._observation(step_index, source).rows

    # --- what a read retains --------------------------------------------------

    def _run_step_includes(
        self,
        step_index: int,
        step: Mapping[str, Any],
        root_rows: list[dict[str, Any]],
        pairs: list[tuple[str, list[Any]]],
        reader: ReadExecutor,
    ) -> retained.StepIncludes | None:
        """Execute a find's child levels, or refuse SQL for levels it declares none of.

        A read step's own ``objectQuery`` carries Include Paths exactly as a read
        case's does, so the step costs ``1 + L`` round trips and lists one golden
        statement per non-empty level. Without Includes there is nothing after the
        root, so a second listed statement is SQL nobody executes and the step's
        declared round trips would count a call it never made.
        """
        case = self._case
        query = step["objectQuery"]
        if not includes.query_has_includes(query):
            if len(pairs) > 1:
                raise CaseFailure(
                    f"{case.path.name}: scenario[{step_index}] lists {len(pairs)} golden "
                    f"statements but its objectQuery declares no `includes`, so only the "
                    f"root read has a level to run. A step that costs more than one round "
                    f"trip MUST declare the include levels the extra statements fetch."
                )
            return None
        steps = includes.fetch_steps(case.model, query)
        source = f"when.scenario[{step_index}].statements"
        executed = includes.execute_fetch_levels(
            case, reader, source, query, steps, root_rows, pairs[1:]
        )
        includes.refuse_unused_levels(case, source, reader.dialect, executed, len(pairs) - 1)
        return retained.StepIncludes(query, steps, root_rows, executed.children_by_hop)

    def _observation(self, step_index: int, source: int) -> retained.Observation:
        """The observation step *source* published, refused when it published none."""
        observation = self._retained.get(source)
        if observation is None:
            raise CaseFailure(
                f"{self._case.path.name}: scenario[{step_index}] names step {source}, "
                f"which published no observation. A step reaching back for rows, a view, "
                f"or an identity MUST name an earlier step that OBSERVED them — never a "
                f"write, a boundary action, or a list construction that has not resolved."
            )
        return observation

    def _read_entity(self, step_index: int) -> Entity | None:
        """The entity a step's observed rows belong to, for value-object decode.

        Resolving the PER-STEP read entity — rather than assuming the Scenario
        root — is what lets a step reading a different, value-object-bearing
        entity decode its document column with the RIGHT composite schema (m-sql
        *Read projection*, slot 4; m-case-format *Read result form*). A read step
        names its queried position inside its own ``objectQuery.target``. A
        ``load`` / ``access`` navigates from an earlier object (``on``, required
        for the read verbs): with a ``path`` its rows are the path's TERMINAL
        entity; a path-less query-backed-list ``access`` resolves the constructed
        list's own source entity, which is why this reads the source step out of
        the CASE rather than out of what was observed — the construction step it
        may name published nothing and is never observed at all.
        """
        case = self._case
        step = case.scenario[step_index]
        if "objectQuery" in step:
            return case.model.entity(step["objectQuery"]["target"])
        if step.get("action") in _ACTION_READ_VERBS:
            named = step["on"]
            source = named[0] if isinstance(named, list) else named
            if not isinstance(source, int) or not 0 <= source < step_index:
                raise CaseFailure(
                    f"{case.path.name}: scenario[{step_index}].on references step "
                    f"{source!r}, which is not a real EARLIER step "
                    f"(0 <= source < {step_index}); an action targets the result of a "
                    f"prior step."
                )
            start = self._read_entity(source)
            path = step.get("path")
            if path is None or start is None:
                return start
            return _relationship_path_target(case, start, path)
        return None

    # --- what a step observes -------------------------------------------------

    def _reference_rows(
        self, step: Mapping[str, Any], reader: ReadExecutor
    ) -> list[dict[str, Any]] | None:
        """Run a step's independent, bind-free naive SQL oracle, or ``None`` for none.

        On the SAME connection the golden read used — the provider's autocommit
        connection for an ungrouped find, the `uow` group's own held session for a
        grouped one — so a grouped find's mid-transaction, possibly uncommitted
        state is what the oracle observes too, never a different connection's
        committed-only view.
        """
        reference_sql = _reference_sql_for(step, reader.dialect)
        if reference_sql is None:
            return None
        return execute.query_rows(self._case, reader, reference_sql, [])

    def _assert_reference_rows(
        self,
        step_index: int,
        reference_rows: list[dict[str, Any]],
        golden_rows: list[dict[str, Any]],
    ) -> None:
        """Compare an independent formulation's rows to the ones the golden read reached.

        Both sides are handed in at the SAME stage of materialization: a find
        compares raw rows, before its value-object columns are decoded, while a
        delivery compares what its pages already materialized.
        """
        case = self._case
        if not rows_equal(reference_rows, golden_rows, case.tolerance):
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}] referenceSql rows != golden rows.\n"
                f"  reference: {reference_rows!r}\n"
                f"  golden:    {golden_rows!r}"
            )

    def _assert_row_observables(
        self, step_index: int, step: Mapping[str, Any], rows: list[dict[str, Any]]
    ) -> None:
        """Assert a step's ``expectRows`` and its ``sameObjectAs`` identity claim.

        ``expectRows`` compares the step's published rows to the fixture-derived
        expectation; ``sameObjectAs`` checks the one-object-per-PK rule against an
        earlier step. The reference-identity observables (``differentObjectFrom``,
        ``expectState``, ``expectError``) are adapter-delegated — validated by the
        schema and graded by each language's API Conformance Suite — so the wire
        harness skips them here.

        A STREAMED step compares positionally: its rows are the roots its delivery
        handed over in the Continuation Order, and nothing else in the case grades
        the order inside a page (m-case-format *Streamed read steps*).
        """
        case = self._case
        expect = step.get("expectRows")
        if expect is not None and not rows_equal(
            rows, expect, case.tolerance, ordered="stream" in step
        ):
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}] rows != expectRows.\n"
                f"  rows:     {rows!r}\n"
                f"  expected: {expect!r}"
            )
        if "sameObjectAs" not in step:
            return
        source = step["sameObjectAs"]
        if not isinstance(source, int) or not 0 <= source < step_index:
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}].sameObjectAs={source} "
                f"must reference an EARLIER step."
            )
        identity_column = step.get("identityAttr", _pk_column(case.model.root_entity))
        these = self._identity_keys(step_index, step_index, rows, identity_column)
        those = self._identity_keys(
            step_index, source, self._observation(step_index, source).rows, identity_column
        )
        if these != those:
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}] is declared to denote "
                f"the same object(s) as step {source}, but their primary-key "
                f"identities differ (one-object-per-PK violated).\n"
                f"  step {step_index}: {these!r}\n"
                f"  step {source}: {those!r}"
            )

    def _identity_keys(
        self, step_index: int, published_by: int, rows: list[dict[str, Any]], identity_column: str
    ) -> list[Any]:
        """The ordered set of primary-key identities carried by *rows*.

        An identity claim compares two steps' rows, so the refusal names the step
        that MADE the claim and, separately, the one whose rows cannot answer it.
        """
        case = self._case
        if any(identity_column not in row for row in rows):
            whose = "its own" if published_by == step_index else f"step {published_by}'s"
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}] compares identity against "
                f"{whose} result rows, which do not carry the identity column "
                f"{identity_column!r}; a scenario step's find MUST project the primary key "
                f"so identity can be checked."
            )
        return sorted(materialize.coerce_identity_key(row[identity_column]) for row in rows)

    def _assert_graph_observable(
        self, step_index: int, step: Mapping[str, Any], observation: retained.Observation
    ) -> None:
        """Assert whichever placement of ``expectGraph`` this step carries.

        One observable with two placements, making opposite claims. On a READ step
        it states the graph THAT read materialized, assembled from the step's own
        retained buckets — inside a `uow` group, the mid-transaction contents the
        group's session observes. On an ``access`` it states what an
        already-materialized view still holds, navigated with no SQL at all, so
        what it grades is survival rather than materialization.

        Either way the oracle is the model-aware graph comparison a read case's
        ``then.graph`` runs, so an entity collection compares as a multiset and a
        ``multiplicity: many`` Value Object positionally.
        """
        expected = step.get("expectGraph")
        if expected is None:
            return
        if "action" in step:
            observed, subject = self._accessed_contents(step_index, step), "relationship contents"
        else:
            observed, subject = (
                self._materialized_graph(step_index, observation),
                ("materialized graph"),
            )
        if not graph.graphs_equal(observed, expected, self._case.model):
            raise CaseFailure(
                f"{self._case.path.name}: scenario[{step_index}] {subject} != expectGraph.\n"
                f"  observed: {observed!r}\n"
                f"  expected: {expected!r}"
            )

    def _materialized_graph(
        self, step_index: int, observation: retained.Observation
    ) -> dict[str, list[dict[str, Any]]]:
        """The graph a read step's own Include Paths materialized."""
        case = self._case
        view = observation.includes
        if view is None or observation.entity is None:
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}] declares expectGraph on a read "
                f"that carries no `objectQuery.includes`. The contents a read step states "
                f"are the relationships its own Include Paths materialized."
            )
        return graph.assemble_graph(
            case, view.query, view.steps, view.root_rows, view.children_by_hop
        )

    def _accessed_contents(
        self, step_index: int, step: Mapping[str, Any]
    ) -> dict[str, list[dict[str, Any] | None]]:
        """The contents an access states, keyed by the entity its path terminates at.

        The step names ONE materializing read (m-case-format), so a multi-source
        ``on`` is refused rather than resolved to its first source: the contents an
        access states belong to a single view, and an array ``on`` spans sources at
        different lowered coordinates.
        """
        case = self._case
        source = step.get("on")
        if not isinstance(source, int):
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}] declares expectGraph on "
                f"`on: {source!r}`. An access stating relationship contents names ONE "
                f"read — the single step whose Include Paths materialized the view it "
                f"navigates — never a set of sources at different lowered coordinates."
            )
        path = step.get("path")
        terminal = self._read_entity(step_index)
        view = self._observation(step_index, source).includes
        if view is None or terminal is None or not isinstance(path, str):
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}] declares expectGraph, but it "
                f"names no navigated `path` on a source read carrying "
                f"`objectQuery.includes`. The contents an access states are the ones that "
                f"read materialized."
            )
        return {terminal.name: retained.path_nodes(case, step_index, path, view)}


def _runner_owned(step: Mapping[str, Any]) -> str | None:
    """Why Scenario orchestration owns *step*, or ``None`` when this oracle does.

    The complement of "is this a read step?": the runner routes the closed set of
    kinds it owns and sends everything else here, and this is the oracle's own
    reading of that same classification. The two MUST agree — so a step the runner
    owns is named here rather than mis-graded as a read, and a kind this refuses
    that the runner nevertheless routes here is a disagreement about the seam
    rather than an authoring error in the case.
    """
    if "write" in step:
        return "is a write step, whose DML and lifecycle belong to Scenario orchestration."
    action = step.get("action")
    if action is not None and action not in _ACTION_READ_VERBS:
        return (
            f"is a {action!r} action step. Only the read verbs "
            f"{sorted(_ACTION_READ_VERBS)} observe rows; every other verb commits "
            f"buffered DML or acts in memory."
        )
    if (
        "action" not in step
        and not step.get("statements")
        and "stream" not in step
        and step.get("sameObjectAs") is None
        and step.get("on") is None
    ):
        return (
            "constructs a query-backed list that has not resolved. It carries no rows "
            "until a later step accesses it, which is the step that resolves its Object "
            "Query."
        )
    return None


def _statement_pairs(step: Mapping[str, Any], dialect: str) -> list[tuple[str, list[Any]]]:
    """The ``(sql, binds)`` pairs a step's ``statements`` list declares for *dialect*.

    Each statement's binds ride inline on its own entry (default ``[]``), so the
    two are read together rather than paired positionally. An entry whose ``sql``
    map does not declare *dialect* contributes nothing: a step lists golden SQL
    per dialect, and a dialect it was never lowered for has no statement to run.
    """
    entries = step.get("statements")
    if not isinstance(entries, list):
        return []
    pairs: list[tuple[str, list[Any]]] = []
    for entry in entries:
        sql = entry.get("sql") if isinstance(entry, dict) else None
        if not isinstance(sql, dict) or dialect not in sql:
            continue
        binds = entry.get("binds", [])
        pairs.append(
            (sql[dialect], list(binds[dialect]) if isinstance(binds, dict) else list(binds))
        )
    return pairs


def _reference_sql_for(step: Mapping[str, Any], dialect: str) -> str | None:
    """Resolve one Scenario read's naive SQL oracle for *dialect*."""
    raw = step.get("referenceSql")
    if raw is None:
        return None
    if isinstance(raw, dict):
        if dialect not in raw:
            raise KeyError(
                f"scenario referenceSql map has no key {dialect!r} (keys: {sorted(raw)})"
            )
        return raw[dialect]
    return raw


def _assert_action_on(
    case: Case, step_index: int, step: Mapping[str, Any], pairs: list[tuple[str, list[Any]]]
) -> None:
    """Validate a read-verb action step's ``on`` source indices.

    Every index in ``on`` — a single int, or an array of coordinate-group
    sources — MUST name a REAL earlier step, and, for the array form, name it once.
    A coordinate-grouped ``load`` emits one child statement per lowered-coordinate
    group, so it MUST NOT execute MORE statement groups than it references sources:
    every executed group is accounted for by a referenced source (m-deep-fetch
    batching contract).
    """
    if "on" not in step:
        return
    on = step["on"]
    indices = list(on) if isinstance(on, list) else [on]
    if isinstance(on, list) and len(set(indices)) != len(indices):
        raise CaseFailure(
            f"{case.path.name}: scenario[{step_index}].on {on!r} names a DUPLICATE source; "
            f"a coordinate-grouped action references each source at most once."
        )
    for source in indices:
        if not 0 <= source < step_index:
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}].on references step {source!r}, "
                f"which is not a real EARLIER step (0 <= source < {step_index}); an action "
                f"targets the result of a prior step."
            )
    if isinstance(on, list) and len(pairs) > len(indices):
        raise CaseFailure(
            f"{case.path.name}: scenario[{step_index}] executes {len(pairs)} statement "
            f"group(s) but references only {len(indices)} coordinate source(s); a "
            f"coordinate-grouped load emits at most one statement per referenced source, "
            f"so every executed group MUST be accounted for by a referenced source."
        )


def _relationship_path_target(case: Case, start: Entity, path: str) -> Entity:
    """The terminal entity of a dotted relationship *path* walked from *start*.

    A ``load`` / ``access`` navigates one hop (``items``) or a dotted multi-hop
    path (``items.statuses``) from the source object, so its rows are of the entity
    the LAST hop targets — the entity whose value-object schema decodes them.
    """
    entity = start
    for rel_name in path.split("."):
        relationship = entity.relationship_metadata_by_name(rel_name)
        entity = case.model.entity(relationship["join"]["target"]["entity"])
    return entity


def _pk_column(entity: Entity) -> str:
    """The column a step's identity claim compares on by default.

    Scenario cases query a single entity (cache / identity over one type), so the
    identity column defaults to the model root's primary key.
    """
    for attribute in entity.attributes:
        if attribute.get("primaryKey"):
            return attribute["column"]
    return entity.attributes[0]["column"]


def _resolves_a_materializing_write(case: Case, step_index: int) -> bool:
    """Whether the find at *step_index* is a materializing predicate write's own resolve.

    That write is authored immediately after the find that resolves it, over that
    find's own target and canonical predicate, and its target MATERIALIZES — a
    versioned or temporal one does, while an unversioned, non-temporal `update` /
    `delete` is readless and resolves nothing, so an ordinary find before one is an
    ordinary find (`m-case-format` *Materializing cases*).

    "That find's own target" is decided by MODEL IDENTITY, because a case may spell
    an Entity either way: a find naming ``Subscriber`` and a write naming
    ``parallax.compatibility.Subscriber`` are one materializing operation.
    """
    scenario = case.scenario
    step = scenario[step_index]
    query = step.get("objectQuery")
    following = scenario[step_index + 1] if step_index + 1 < len(scenario) else None
    write = following.get("write") if isinstance(following, Mapping) else None
    if not isinstance(query, Mapping) or not isinstance(write, Mapping):
        return False
    target = write.get("target")
    if not isinstance(target, Mapping) or not isinstance(target.get("predicate"), Mapping):
        return False
    if canonical(target["predicate"]) != canonical(query.get("predicate")):
        return False
    try:
        written = case.model.entity(target["entity"])
        read = case.model.entity(query["target"])
    except (KeyError, TypeError):
        return False
    if written.canonical_name != read.canonical_name:
        return False
    return requires_predicate_write_materialization(written)


def _step_as_read(case: Case, step_index: int) -> Case:
    """The step at *step_index* presented as the READ case its materialization belongs to.

    A row materializer asks a case for the read it is materializing — the target
    its Object Query names, the projection shape its golden ``select`` states, and
    the result form that shape belongs to — because a `read` case has exactly one
    of each. A Scenario read step has its own, so it is handed over in the
    vocabulary those materializers already speak rather than each of them being
    taught a second place to look. Everything they read BESIDE those three stays
    the case's own: the model, the path a failure names, and the comparison
    tolerance.

    A step's own ``expectRows`` names no form, so the form follows the step's read
    semantics (`m-case-format` *Read result form*). An observation find, a resolving
    ``load``, and a first ``access`` are the object lane; the sole row-form step read
    is the materialized-predicate-write resolving find, which is an ordinary
    preceding ``objectQuery`` step this oracle grades like any other and is
    recognized as the resolve by the write it serves
    (:func:`_resolves_a_materializing_write`), so an abstract table-per-concrete-subtype
    step is graded on projecting the top-level Value Object `Document` slot its own
    lane selects.
    """
    step = case.scenario[step_index]
    return _as_read(
        case,
        {key: step[key] for key in ("objectQuery", "stream") if key in step},
        step.get("statements", []),
        row_form=_resolves_a_materializing_write(case, step_index),
    )


def _resolved_list_read(case: Case, step_index: int, step: Mapping[str, Any]) -> Case | None:
    """A first ``access`` of a query-backed list, presented as the read it resolves.

    Such an access navigates no relationship: it resolves the list an earlier step
    constructed, so one read is spread over two steps — the position and its Subtype
    Selection are the CONSTRUCTION step's Object Query, the projection shape is THIS
    step's golden. A ``load`` / ``access`` that walked a ``path`` stands at a
    navigated position instead, which no Object Query describes, and answers ``None``
    (:func:`materialize.materialize_navigated_family_variant`).
    """
    if step.get("path") is not None:
        return None
    named = step.get("on")
    source = named[0] if isinstance(named, list) else named
    if not isinstance(source, int) or not 0 <= source < step_index:
        return None
    query = case.scenario[source].get("objectQuery")
    if not isinstance(query, Mapping):
        return None
    return _as_read(case, {"objectQuery": query}, step.get("statements", []), row_form=False)


def _as_read(case: Case, when: Mapping[str, Any], statements: Any, *, row_form: bool) -> Case:
    """*case* restated as the one-read `read` case *when* and *statements* describe.

    A read case states its lane by WHICH result member it carries, so that is how
    this presentation states it. The member's CONTENTS are never read: what a step
    observed is graded against the step's own ``expectRows`` / ``expectGraph``.
    """
    then: dict[str, Any] = {
        "statements": statements,
        **({"rows": []} if row_form else {"graph": {}}),
    }
    if "tolerance" in case.then:
        then["tolerance"] = case.then["tolerance"]
    return replace(
        case,
        raw=frozen_view(
            {
                "model": case.raw["model"],
                "shape": "read",
                "when": dict(when),
                "then": then,
            }
        ),
    )
