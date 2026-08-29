"""What a Scenario read step published, and what a later step reads back from it.

A retained observation is the whole of what one step handed over: the rows it
published, the entity those rows decode against, and — where its Object Query
declared Include Paths — the per-hop child buckets its own levels fetched. It
carries no reader and no session, so a step naming it later is answered from the
observation alone however the connection that produced it has since ended.

Both readers of a retained view assemble through the same graph assembly a read
case's ``then.graph`` runs, over the buckets the observation holds rather than a
re-fetched set: the step's own graph is that whole assembly, and a later `access`
walks a path through it. A snapshot issues no SQL after materialization
(`m-snapshot-read`), so an access over an already-loaded relationship executes
nothing at all.

Nothing here reaches the package's public seam: a retained observation is built,
held, and read entirely inside one ``ScenarioReads``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..case import Case, Entity
from ..case_assertions import CaseFailure
from . import graph, includes, materialize


@dataclass(frozen=True, slots=True)
class StepIncludes:
    """What one Scenario read step's Include Paths materialized.

    Held per HOP, exactly as a deep-fetch read case holds them, because two
    branches may reach one entity through different guards or different parents.
    """

    query: dict[str, Any]
    steps: list[includes.FetchStep]
    root_rows: list[materialize.PublishedRow]
    children_by_hop: dict[includes.HopKey, dict[Any, list[materialize.PublishedRow]]]


@dataclass(frozen=True, slots=True)
class Observation:
    """Everything one asserted step published, keyed later by that step's index.

    ``entity`` is what the rows decode against — a read step's own query target,
    an `access`'s navigated terminal — and is ``None`` only where a step observed
    no rows. ``includes`` is ``None`` where the step's query declared no Include
    Paths, so there is no materialized view for a later access to navigate.

    ``rows`` are what the step PUBLISHED, so they come from the materialization
    seam and nowhere else. That is checked at construction rather than trusted:
    an observation outlives its reader and is read back by later steps, so a raw
    physical row admitted here would surface as a wrong ``expectRows``, a wrong
    identity, or a wrong graph several steps away from the path that let it in.
    """

    rows: list[materialize.PublishedRow]
    entity: Entity | None
    includes: StepIncludes | None

    def __post_init__(self) -> None:
        if not all(isinstance(row, materialize.PublishedRow) for row in self.rows):
            raise TypeError(
                "a retained observation holds the rows its step published; these did not "
                "come through the materialization seam (materialize_read / "
                "materialize_navigated), so they may still carry storage the read never "
                "asked for."
            )


def relationship_path_fans_out(case: Case, start: Entity, path: str) -> bool:
    """Whether any hop of *path* walked from *start* is a to-many relationship.

    A fanning-out path reaches a SET of terminal nodes, so a branch that reached
    no row contributes nothing to it; an all-to-one path reaches one terminal per
    starting object instead, which is the node or the null the last hop holds.
    """
    entity = start
    for rel_name in path.split("."):
        relationship = entity.relationship_metadata_by_name(rel_name)
        if relationship["cardinality"] == "one-to-many":
            return True
        entity = case.model.entity(relationship["join"]["target"]["entity"])
    return False


def path_nodes(
    case: Case, index: int, path: str, view: StepIncludes
) -> list[dict[str, Any] | None]:
    """The nodes a step's ``path`` reaches in the view its source read materialized.

    The whole graph is assembled from the source read's own retained buckets, then
    each hop of the dotted path is followed through the already-attached view keys —
    a to-many hop contributing its list and a to-one hop its single node (or the
    ``None`` a loaded-null view carries). Reaching a key the assembly never attached
    means the source read did not include that relationship, which is an access with
    no materialized contents to state rather than an empty answer.

    A loaded-null branch is not that: its own deeper levels saw an EMPTY parent set
    (m-deep-fetch), so it contributes no terminal value to a path that fans out
    through any to-many hop, and the walk of such a path answers non-null nodes
    alone. An all-to-one path fans out nowhere and answers one terminal per root
    instead — the ``None`` of a branch that reached no row included. That is the
    contents the observable itself is defined to carry (m-case-format
    *Relationship contents at a step*), which is why every executor and adapter
    walks a multi-hop path this way rather than each answering its own shape.
    """
    assembled = graph.assemble_graph(
        case, view.query, view.steps, view.root_rows, view.children_by_hop
    )
    nodes: list[Any] = [node for group in assembled.values() for node in group]
    fans_out = relationship_path_fans_out(case, case.model.entity(view.query["target"]), path)
    for hop, rel_name in enumerate(path.split(".")):
        reached: list[Any] = []
        for node in nodes:
            if node is None:
                reached.append(None)
                continue
            if not isinstance(node, dict) or rel_name not in node:
                raise CaseFailure(
                    f"{case.path.name}: scenario[{index}] accesses {path!r}, but the "
                    f"source read did not include {rel_name!r} (hop {hop}). An access "
                    f"asserting relationship contents MUST name a read whose "
                    f"`objectQuery.includes` materialized them."
                )
            value = node[rel_name]
            if isinstance(value, list):
                reached.extend(value)
            elif value is not None or not fans_out:
                reached.append(value)
        nodes = reached
    return nodes
