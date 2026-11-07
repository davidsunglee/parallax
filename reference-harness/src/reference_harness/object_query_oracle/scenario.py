"""Compile and observe explicit scenario steps over snapshot values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from ..case import Case, Entity, entry_pairs, frozen_view
from ..case_assertions import CaseFailure, coerce_identity_key, reported_against, rows_equal
from . import execute, graph, includes, materialize, retained, row, stream
from .executor import ReadExecutor


class ScenarioRowObservations:
    """The accepted row observations of one Unit Work Scenario."""

    def __init__(self, case: Case) -> None:
        self._case = case
        self._retained: dict[int, retained.Observation] = {}

    def assert_step(self, step_index: int, reader: ReadExecutor) -> None:
        """Resolve a scenario observation from its authored source and result position."""
        with reported_against(self._case, step_index):
            step = self._case.scenario[step_index]
            pairs = entry_pairs(step.get("statements"), reader.dialect)

            if "stream" in step:
                observation = self._deliver(step_index, step, reader)
            elif "action" in step:
                observation = self._act(step_index, step, pairs)
            elif pairs:
                observation = self._query(step_index, step, pairs, reader)
            else:
                raise CaseFailure(
                    f"{self._case.path.name}: scenario[{step_index}] read step requires "
                    "golden statements; independent reads cannot reuse earlier rows"
                )

            self._assert_row_observables(step_index, step, observation)
            self._assert_graph_observable(step_index, step, observation)
            # Publication is the LAST thing a step does, so a step that failed an
            # observable published nothing: a later step naming it is refused for
            # naming an unobserved step rather than answered with rows nobody graded.
            self._retained[step_index] = observation

    # --- row-publication workflows -------------------------------------------

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
            materialized = materialize.materialize_read(step_read, reference)
            self._assert_reference_rows(
                step_index,
                [execute.project_like(row, delivered) for row in materialized],
                delivered,
                entity,
            )
        if entity is None:
            return retained.Observation(
                rows=delivered, nodes=[*delivered], entity=None, includes=None
            )
        return self._read_observation(entity, delivered, None)

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
            self._assert_reference_rows(step_index, reference, rows, entity)
        published = materialize.materialize_read(step_read, rows)
        return self._read_observation(
            entity,
            published,
            self._run_step_includes(step_index, step, published, pairs, reader),
        )

    def _read_observation(
        self,
        entity: Entity,
        published: list[materialize.PublishedRow],
        step_includes: retained.StepIncludes | None,
    ) -> retained.Observation:
        """What a read retains of the rows it published at *entity*'s position."""
        case = self._case
        return retained.Observation(
            rows=[
                materialize.materialize_variant_owner_node(case, entity, row) for row in published
            ],
            nodes=[graph.graph_node(case, entity, row) for row in published],
            entity=entity,
            includes=step_includes,
        )

    def _act(
        self,
        step_index: int,
        step: Mapping[str, Any],
        pairs: list[tuple[str, list[Any]]],
    ) -> retained.Observation:
        if pairs:
            raise CaseFailure(
                f"{self._case.path.name}: scenario[{step_index}] snapshot actions issue no SQL"
            )
        if step.get("action") == "mutate":
            return self._mutate(step_index, step)
        return replace(self._accessed_source(step_index, step), includes=None)

    def _mutate(self, step_index: int, step: Mapping[str, Any]) -> retained.Observation:
        """Publish the one Wire row a ``mutate`` derives from its source."""
        source = step.get("on")
        if not isinstance(source, int):
            raise CaseFailure(
                f"{self._case.path.name}: scenario[{step_index}] mutate names "
                f"{source!r}; a row-observing mutate requires one source step"
            )
        observed = self._observation(step_index, source)
        if len(observed.rows) != 1:
            raise CaseFailure(
                f"{self._case.path.name}: scenario[{step_index}] mutate names a step "
                f"that published {len(observed.rows)} rows; an edit requires exactly one"
            )
        assignments = step.get("set", {})
        if not isinstance(assignments, Mapping):
            raise CaseFailure(
                f"{self._case.path.name}: scenario[{step_index}] mutate set is not a mapping"
            )
        node = observed.nodes[0]
        if node is None:
            raise CaseFailure(
                f"{self._case.path.name}: scenario[{step_index}] mutate names a position "
                f"that published no value to edit"
            )
        return retained.Observation(
            rows=observed.rows,
            nodes=[materialize.edited(node, assignments)],
            entity=observed.entity,
            includes=observed.includes,
            derived=True,
        )

    def _accessed_source(self, step_index: int, step: Mapping[str, Any]) -> retained.Observation:
        """The observation whose already-materialized relationship an access navigates."""
        source = step.get("on")
        if not isinstance(source, int):
            raise CaseFailure(
                f"{self._case.path.name}: scenario[{step_index}] issues no statement of its "
                f"own and names no earlier source step — a zero-Database-Call "
                f"snapshot access answers with the rows an earlier step published."
            )
        return self._observation(step_index, source)

    # --- what an observation retains -----------------------------------------

    def _run_step_includes(
        self,
        step_index: int,
        step: Mapping[str, Any],
        root_rows: list[materialize.PublishedRow],
        pairs: list[tuple[str, list[Any]]],
        reader: ReadExecutor,
    ) -> retained.StepIncludes | None:
        """Execute a find's child levels, or refuse SQL for levels it declares none of.

        A read step's own ``objectQuery`` carries Include Paths exactly as a read
        case's does, so the step costs ``1 + L`` Database Calls and lists one golden
        statement per non-empty level. Without Includes there is nothing after the
        root, so a second listed statement is SQL nobody executes and the step's
        declared Database Calls would count a call it never made.
        """
        case = self._case
        query = step["objectQuery"]
        if not includes.query_has_includes(query):
            if len(pairs) > 1:
                raise CaseFailure(
                    f"{case.path.name}: scenario[{step_index}] lists {len(pairs)} golden "
                    f"statements but its objectQuery declares no `includes`, so only the "
                    f"root read has a level to run. A step that costs more than one Database "
                    f"Call MUST declare the include levels the extra statements fetch."
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
                f"write or a boundary action."
            )
        return observation

    def _read_entity(self, step_index: int) -> Entity | None:
        """The entity a step observes, following an edited value or loaded relationship."""
        case = self._case
        step = case.scenario[step_index]
        if "objectQuery" in step:
            return case.model.entity(step["objectQuery"]["target"])
        if "action" in step:
            named = step["on"]
            source = named
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
        golden_rows: Sequence[dict[str, Any]],
        entity: Entity | None,
    ) -> None:
        """Compare an independent formulation's rows to the ones the golden read reached.

        Both sides are handed in at the SAME stage of materialization: a find
        compares raw rows, before its value-object columns are decoded, while a
        delivery compares what its pages already materialized.
        """
        case = self._case
        equal = (
            rows_equal(reference_rows, golden_rows, case.tolerance)
            if entity is None
            else row.rows_equal(reference_rows, golden_rows, case.model, entity, case.tolerance)
        )
        if not equal:
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}] referenceSql rows != golden rows.\n"
                f"  reference: {reference_rows!r}\n"
                f"  golden:    {golden_rows!r}"
            )

    def _assert_row_observables(
        self, step_index: int, step: Mapping[str, Any], observation: retained.Observation
    ) -> None:
        """Assert the expected rows and preserved identity of a snapshot observation."""
        case = self._case
        expect = step.get("expectRows")
        entity = observation.entity
        stated = observation.stated_rows(case.model)
        if expect is not None and not (
            rows_equal(stated, expect, case.tolerance, ordered="stream" in step)
            if entity is None
            else row.rows_equal(
                stated, expect, case.model, entity, case.tolerance, ordered="stream" in step
            )
        ):
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}] rows != expectRows.\n"
                f"  rows:     {stated!r}\n"
                f"  expected: {expect!r}"
            )
        if "sameObjectAs" not in step:
            return
        source = step["sameObjectAs"]
        identity_column = step.get("identityAttr", case.model.root_entity.identity_column)
        these = self._identity_keys(step_index, step_index, observation.rows, identity_column)
        those = self._identity_keys(
            step_index, source, self._observation(step_index, source).rows, identity_column
        )
        if these != those:
            raise CaseFailure(
                f"{case.path.name}: scenario[{step_index}] is declared to denote "
                f"the same object(s) as step {source}, but their primary-key "
                f"identities differ (retained snapshot view changed).\n"
                f"  step {step_index}: {these!r}\n"
                f"  step {source}: {those!r}"
            )

    def _identity_keys(
        self,
        step_index: int,
        published_by: int,
        rows: Sequence[dict[str, Any]],
        identity_column: str,
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
        return sorted(coerce_identity_key(row[identity_column]) for row in rows)

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
    ) -> dict[str, list[dict[str, Any] | None]]:
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


def _relationship_path_target(case: Case, start: Entity, path: str) -> Entity:
    """The terminal entity of a loaded relationship path."""
    entity = start
    for rel_name in path.split("."):
        relationship = entity.relationship_metadata_by_name(rel_name)
        entity = case.model.entity(relationship["join"]["target"]["entity"])
    return entity


def _step_as_read(case: Case, step_index: int) -> Case:
    """The step at *step_index* presented as the READ case its materialization belongs to.

    A row materializer asks a case for the read it is materializing — the target
    its Object Query names and the projection shape its golden ``select`` states —
    because a `read` case has exactly one of each. A Scenario read step has its own,
    so it is handed over in the vocabulary those materializers already speak rather
    than each of them being taught a second place to look. Everything they read
    BESIDE those two stays the case's own: the model, the path a failure names, and
    the comparison tolerance.
    """
    step = case.scenario[step_index]
    return _as_read(
        case,
        {key: step[key] for key in ("objectQuery", "stream") if key in step},
        step.get("statements", []),
        grouped=isinstance(step.get("uow"), str),
    )


def _as_read(
    case: Case,
    when: Mapping[str, Any],
    statements: Any,
    *,
    grouped: bool = False,
) -> Case:
    """*case* restated as the one-read `read` case *when* and *statements* describe.

    The result member's CONTENTS are never read: what a step observed is graded
    against the step's own ``expectRows`` / ``expectGraph``.
    Both placements a preference or level can be resolved from travel with the
    step — the scenario's own ``when.uow`` request and its root's
    ``given.databaseOptions`` — so the restated read resolves exactly what the
    scenario's transaction resolves. A read case is transactional exactly when it
    carries ``when.uow``, so a step that is ``grouped`` — inside a `uow` group's
    transaction — carries the block whether or not the scenario authored one:
    the group opened the transaction, and the preference it runs under is then
    resolved from the request over the root rather than read off the block's
    presence.
    """
    then: dict[str, Any] = {"statements": statements, "graph": {}}
    if "tolerance" in case.then:
        then["tolerance"] = case.then["tolerance"]
    transactional = grouped or "uow" in case.when
    read_when = {**({"uow": case.uow} if transactional else {}), **when}
    raw: dict[str, Any] = {
        "model": case.raw["model"],
        "shape": "read",
        "when": read_when,
        "then": then,
    }
    if case.database_options:
        raw["given"] = {"databaseOptions": case.database_options}
    return replace(case, raw=frozen_view(raw))
