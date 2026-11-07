"""Every family node in the corpus states `_type`, and no other node does."""

from __future__ import annotations

import copy
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import Case, Entity, discover_cases, load_case
from reference_harness.inheritance import TYPE_KEY, Family, inheritance_of

_COMPATIBILITY = Path(__file__).resolve().parents[2] / "core" / "compatibility"


def _nodes(value: object) -> Iterator[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            yield from _nodes(item)


def _stated_types(value: object) -> int:
    """How many mappings anywhere under *value* carry the key."""
    if isinstance(value, Mapping):
        return (TYPE_KEY in value) + sum(_stated_types(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return sum(_stated_types(item) for item in value)
    return 0


class _Walk:
    """One case's stated nodes, each graded against the Entity it stands at."""

    def __init__(self, case: Case) -> None:
        self.case = case
        self.family = Family(case.model.entity_defs)
        self.problems: list[str] = []
        self.visited = 0
        self.seen = 0

    def rows(self, target: str, rows: object, where: str) -> None:
        for index, node in enumerate(_nodes(rows)):
            self.node(self.case.model.entity(target), node, f"{where}[{index}]")

    def graph(self, graph: object, where: str) -> None:
        for roots in _nodes(graph):
            for name, nodes in roots.items():
                self.rows(name, nodes, f"{where}.{name}")

    def node(self, position: Entity, node: Mapping[str, Any], where: str) -> None:
        self.visited += 1
        self.seen += TYPE_KEY in node
        stated = node.get(TYPE_KEY)
        participates = inheritance_of(self.family.defs[position.canonical_name]) is not None
        concrete = position
        if not participates:
            if TYPE_KEY in node:
                self.problems.append(f"{where}: {position.name} is outside a family")
        elif not isinstance(stated, str):
            self.problems.append(f"{where}: a {position.name} node states no {TYPE_KEY}")
        elif stated not in self._effective(position):
            self.problems.append(f"{where}: {stated!r} is no concrete of {position.name}")
        else:
            concrete = self.case.model.entity(stated)
        relationships = {
            item["name"]: item
            for name in self.family.ancestry(concrete.canonical_name) or [concrete.canonical_name]
            for item in self.case.model.entity(name).relationship_metadata
        }
        for key, value in node.items():
            relationship = relationships.get(key.split("[", 1)[0])
            if relationship is None:
                continue
            target = self.case.model.entity(relationship["join"]["target"]["entity"])
            for index, child in enumerate(_nodes(value)):
                self.node(target, child, f"{where}.{key}[{index}]")

    def _effective(self, position: Entity) -> set[str]:
        return {
            self.family.defs.canonical_key(name)
            for name in self.family.effective_concrete_set(position.canonical_name)
        }


def _walked(case: Case) -> _Walk:
    walk = _Walk(case)
    then = case.then
    if case.shape == "read" and "rows" in then:
        walk.rows(case.object_query["target"], then["rows"], "then.rows")
    if "graph" in then:
        walk.graph(then["graph"], "then.graph")
    for index, milestone in enumerate(then.get("graphs", ())):
        walk.graph(milestone["graph"], f"then.graphs[{index}]")
    for index, step in enumerate(case.when.get("scenario", ())):
        query = step.get("objectQuery")
        if "expectRows" in step and query is not None:
            walk.rows(query["target"], step["expectRows"], f"scenario[{index}].expectRows")
        if "expectGraph" in step:
            walk.graph(step["expectGraph"], f"scenario[{index}].expectGraph")
    return walk


_CASES = discover_cases(_COMPATIBILITY)
_FAMILY_ROWS = "m-inheritance-001-tph-concrete-target-read.yaml"
_STANDALONE_ROWS = "m-object-query-001-order-by-limit.yaml"
_FAMILY_CHILD_OF_STANDALONE = "m-inheritance-065-tph-deepfetch-narrowed-pets-dog.yaml"


def _case(name: str) -> Case:
    return copy.deepcopy(load_case(_COMPATIBILITY, _COMPATIBILITY / "cases" / name))


def test_every_family_node_states_its_concrete_and_no_other_node_states_one() -> None:
    problems = [
        f"{case.path.name}: {problem}" for case in _CASES for problem in _walked(case).problems
    ]
    assert problems == []


def test_the_walk_reaches_every_type_the_corpus_states() -> None:
    # A position the walk does not read would hold a `_type` no rule above graded.
    unread = []
    for case in _CASES:
        if case.shape == "rejected":
            continue
        stated = _stated_types(case.then) + _stated_types(case.when.get("scenario", ()))
        if _walked(case).seen != stated:
            unread.append(case.path.name)
    assert unread == []


def test_the_walk_refuses_a_family_node_losing_its_type() -> None:
    case = _case(_FAMILY_ROWS)
    del case.then["rows"][0][TYPE_KEY]
    assert "states no _type" in _walked(case).problems[0]


@pytest.mark.parametrize("stated", ["CardPayment", "parallax.compatibility.CashPayment"])
def test_the_walk_refuses_a_family_node_naming_the_wrong_type(stated: str) -> None:
    case = _case(_FAMILY_ROWS)
    case.then["rows"][0][TYPE_KEY] = stated
    assert "is no concrete of" in _walked(case).problems[0]


def test_the_walk_refuses_a_type_on_a_row_outside_a_family() -> None:
    case = _case(_STANDALONE_ROWS)
    case.then["rows"][0][TYPE_KEY] = "parallax.compatibility.Order"
    assert "is outside a family" in _walked(case).problems[0]


def test_the_walk_refuses_a_type_on_a_standalone_parent_of_family_nodes() -> None:
    case = _case(_FAMILY_CHILD_OF_STANDALONE)
    case.then["graph"]["Person"][0][TYPE_KEY] = "parallax.compatibility.Person"
    assert "is outside a family" in _walked(case).problems[0]
