"""Root classification: one verdict per result root, downstream of the merge.

Detection is local and layout-neutral; attribution is not. Whether a root is
invalid depends on the whole include tree reachable from it, which only the
merged graph knows — so classification runs here, once, after merging and before
construction, and neither materializer re-judges anything it answers.

The rule is root-granular by contract: an issue anywhere in a root's requested
include tree makes that root invalid, one invalid included node repeats its
diagnosis in every root that reaches it, and no node is pruned or given a union
of its own. A root whose issues all left values producible still constructs — its
collapse produced legal member values — so hydration and classification stay one
pass rather than a construct-and-catch that would re-judge by exception.

The construction scope narrows honestly with it: nodes reachable only from
non-hydrating roots are left out, so atomic publication means *everything
constructible publishes together* rather than everything the query matched. The
scope is closed under reachability by construction — a root that reaches a
non-hydrating node is itself non-hydrating — so no constructed node ever points
at one left out.

A conforming graph pays nothing: :func:`classify_roots` answers from
:attr:`~parallax.snapshot.materialize.GraphMerge.has_issues` alone, walking
nothing and wrapping nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    PrimaryKey,
)
from parallax.core.temporal_read import Edge, TemporalReadError, milestone_edge_of
from parallax.core.unit_work import ObjectKey
from parallax.snapshot.materialize._input import InvalidRootInput, StoredDataIssueCode
from parallax.snapshot.materialize._invalid import InvalidData, StoredDataIssue
from parallax.snapshot.materialize._merge import GraphMerge, MergedNode

__all__ = [
    "ClassifiedRoot",
    "ConformingRoot",
    "GraphClassification",
    "RootClassification",
    "classify_roots",
]

NON_HYDRATING_CODES: Final[frozenset[StoredDataIssueCode]] = frozenset(
    {
        "stored-data-leaf-undecodable",
        "stored-data-attribute-null",
        "stored-data-family-tag-unknown",
        "stored-data-primary-key-null",
        "stored-data-primary-key-undecodable",
    }
)
"""The codes for which no conforming value exists to hydrate (`m-snapshot-read`).

Their complement — a required member absent or stored null, and a wrong-kind
occurrence — is exactly the set the normative absence collapse already answers,
so a root carrying only those hydrates completely.
"""

_UNIDENTIFIED_CODES: Final[frozenset[StoredDataIssueCode]] = frozenset(
    {
        "stored-data-primary-key-null",
        "stored-data-primary-key-undecodable",
        "stored-data-family-tag-unknown",
    }
)
"""The codes that leave a node with no trustworthy Object Key of its own: its
identity did not decode, or the Entity that identity would name is unresolved."""


@dataclass(frozen=True, slots=True)
class ConformingRoot:
    """A root whose whole requested include tree conforms; it publishes as itself."""

    node: int


@dataclass(frozen=True, slots=True)
class ClassifiedRoot:
    """A root some stored state contradicted; it publishes as :class:`InvalidData`.

    ``node`` is the allocation index hydration constructs ``data`` from, and is
    absent exactly where no value could be produced without inventing one.
    """

    ordinal: int
    issues: frozenset[StoredDataIssue]
    object_key: ObjectKey | None
    version: int | None
    edge: Edge | None
    node: int | None

    def published(self, data: object | None) -> InvalidData[object]:
        """This root's public record, carrying ``data`` when hydration produced one."""
        return InvalidData(
            issues=self.issues,
            data=data,
            object_key=self.object_key,
            version=self.version,
            edge=self.edge,
            ordinal=self.ordinal,
        )


type RootClassification = ConformingRoot | ClassifiedRoot
"""One result root's verdict, in the position the result orders it at."""


@dataclass(frozen=True, slots=True)
class GraphClassification:
    """One merged graph's verdicts and the construction scope they imply.

    ``excluded`` names the allocation indices construction leaves out. ``roots``
    is one verdict per result position, in result order, including the
    non-hydrating roots no allocation index stands behind.
    """

    roots: tuple[RootClassification, ...]
    excluded: frozenset[int] = frozenset()
    conforming: bool = False


def classify_roots(
    merge: GraphMerge, model: Metamodel, *, ordinal_offset: int = 0
) -> GraphClassification:
    """``merge``'s per-root verdicts, attributed over each root's reachable tree.

    ``ordinal_offset`` is where this graph's roots start in the ordered result a
    Snapshot publishes, which is nonzero only for a milestone-set read whose
    results span several graphs.
    """
    if not merge.has_issues:
        return GraphClassification(
            roots=tuple(ConformingRoot(index) for index in merge.roots if index is not None),
            conforming=True,
        )
    nodes = tuple(merge.node(index) for index in range(len(merge.order)))
    children = tuple(_children(node) for node in nodes)
    keys = tuple(_object_key(model, node) for node in nodes)
    diagnoses = tuple(
        frozenset(
            StoredDataIssue(issue.code, issue.entity, issue.member, key) for issue in node.issues
        )
        for node, key in zip(nodes, keys, strict=True)
    )
    blocking = tuple(
        any(issue.code in NON_HYDRATING_CODES for issue in node.issues) for node in nodes
    )

    roots: list[RootClassification] = []
    reached_by_published: set[int] = set()
    keyless_roots = iter(merge.invalid_roots)
    for position, index in enumerate(merge.roots):
        ordinal = ordinal_offset + position
        if index is None:
            roots.append(_keyless_root(next(keyless_roots), ordinal))
            continue
        reachable = _reachable(children, index)
        issues = frozenset(issue for node in reachable for issue in diagnoses[node])
        if not issues:
            roots.append(ConformingRoot(index))
            reached_by_published |= reachable
            continue
        hydrating = not any(blocking[node] for node in reachable)
        declaring = _declaring(model, nodes[index].concrete_entity)
        roots.append(
            ClassifiedRoot(
                ordinal=ordinal,
                issues=issues,
                object_key=keys[index],
                version=_version(declaring, nodes[index]),
                edge=_edge(declaring, nodes[index]),
                node=index if hydrating else None,
            )
        )
        if hydrating:
            reached_by_published |= reachable
    return GraphClassification(
        roots=tuple(roots),
        excluded=frozenset(range(len(nodes))) - reached_by_published,
    )


def _keyless_root(record: InvalidRootInput, ordinal: int) -> ClassifiedRoot:
    """One result root whose own identity never decoded.

    It has no converted node behind it, so it reaches nothing, hydrates nothing,
    and locates itself by result position alone — the ordinal is the only fact
    about it that survived.
    """
    return ClassifiedRoot(
        ordinal=ordinal,
        issues=frozenset(
            StoredDataIssue(issue.code, issue.entity, issue.member) for issue in record.issues
        ),
        object_key=None,
        version=None,
        edge=None,
        node=None,
    )


def _children(node: MergedNode) -> tuple[int, ...]:
    """The allocation indices ``node``'s loaded relationship views reach."""
    reached: dict[int, None] = {}
    for view in node.views:
        value = view.value
        if isinstance(value, tuple):
            reached.update(dict.fromkeys(value))
        elif value is not None:
            reached[value] = None
    return tuple(reached)


def _reachable(children: tuple[tuple[int, ...], ...], root: int) -> frozenset[int]:
    """Every allocation index reachable from ``root``, including itself.

    The merged graph is the requested include tree already realized: a view
    exists exactly where a level loaded one, so following views is following the
    includes. Cycles terminate on the visited set rather than on a depth bound.
    """
    seen = {root}
    pending = [root]
    while pending:
        for child in children[pending.pop()]:
            if child not in seen:
                seen.add(child)
                pending.append(child)
    return frozenset(seen)


def _object_key(model: Metamodel, node: MergedNode) -> ObjectKey | None:
    """``node``'s object identity, or absence where nothing trustworthy decoded.

    Derived exactly as a keyed write derives its own: the row's OWN resolved
    concrete Entity, never family-normalized, paired with the family-declared
    primary key's ``(name, value)`` pairs in declaration order (`m-unit-work`).
    """
    if any(issue.code in _UNIDENTIFIED_CODES for issue in node.issues):
        return None
    declaring = _declaring(model, node.concrete_entity)
    if declaring is None:  # pragma: no cover - a family root is always accepted
        return None
    values = _values(node)
    primary_key = tuple(
        attribute
        for attribute in declaring.declared_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    )
    if not primary_key:  # pragma: no cover - formation refuses a primary-key-less Entity
        return None
    return ObjectKey(
        node.concrete_entity,
        tuple(
            (attribute.identity.name, values.get(attribute.identity)) for attribute in primary_key
        ),
    )


def _version(declaring: EntityMetadata | None, node: MergedNode) -> int | None:
    """``node``'s observed explicit version, or absence for every other shape.

    A temporal family derives its concurrency coordinate from its own axis rather
    than from a version Attribute — and formation refuses a temporal root that
    declares one — so the two locators are mutually exclusive by construction.
    """
    if declaring is None or declaring.declared_as_of_axes:
        return None
    version = next(
        (attribute for attribute in declaring.declared_attributes if attribute.optimistic_locking),
        None,
    )
    if version is None:
        return None
    value = _values(node).get(version.identity)
    return value if isinstance(value, int) else None


def _edge(declaring: EntityMetadata | None, node: MergedNode) -> Edge | None:
    """``node``'s observed milestone, or absence where no temporal edge decoded."""
    if declaring is None or not declaring.declared_as_of_axes:
        return None
    try:
        return milestone_edge_of(declaring, _values(node))
    except TemporalReadError:
        return None


def _values(node: MergedNode) -> dict[AttributeIdentity, object]:
    return {entry.identity: entry.value for entry in node.attributes}


def _declaring(model: Metamodel, entity: EntityIdentity) -> EntityMetadata | None:
    """The position declaring ``entity``'s family-wide facts — its family root."""
    position = inheritance_view(model).entity(entity)
    return model.entity(entity if position is None else position.root)
