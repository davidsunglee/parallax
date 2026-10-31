"""The include tree's opaque, plan-lifetime memo of consumer answers."""

from __future__ import annotations

from parallax.core.deep_fetch._include_tree import build_include_tree
from parallax.core.metamodel import EntityIdentity

_ROOT = EntityIdentity("parallax.compatibility", "Order")


def test_a_prepared_answer_is_built_once_and_answered_by_reference() -> None:
    tree = build_include_tree(queried=_ROOT, root=(_ROOT,), positions=())
    built: list[object] = []

    def build() -> object:
        answer = object()
        built.append(answer)
        return answer

    first = tree.prepared(("consumer", 0), build)

    assert tree.prepared(("consumer", 0), build) is first
    assert built == [first]


def test_prepared_answers_are_kept_apart_by_key_and_by_tree() -> None:
    tree = build_include_tree(queried=_ROOT, root=(_ROOT,), positions=())
    other = build_include_tree(queried=_ROOT, root=(_ROOT,), positions=())

    first = tree.prepared("one", object)

    assert tree.prepared("two", object) is not first
    assert other.prepared("one", object) is not first
