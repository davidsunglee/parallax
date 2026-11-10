"""The claim about the instance-state Module that only its source settles.

It is not a behavior a value can be asked about, so it is stated over the
source of ``parallax.core.internal.entity`` and graded there.

**Presence is asked one member at a time.** A published value keeps no
``set[str]``; the set a caller sees is synthesized from its bitmap on request.
So an internal read that asks for the whole set builds one per value it looks at,
and nothing about the answer would say it had. What forbids that is not a rule to
remember but the shape of the Interface — internal code has
:func:`~parallax.core.internal.entity._instance_state.is_present`, a membership test over
one bit — and the inventory below is what keeps the second operation out of
reach.

The inventory is a function of the source handed to it and is shown on both
sides: run over synthetic source carrying the shape it grades, it names that
source's sites rather than this tree's. It is exact over the reaches source
SPELLS — an attribute, a bare name, a string constant, an import — which is the
whole of what reading source settles; a name a module assembles at run time
denotes something only an interpreter knows, and the equivalence a value's
answers are graded by is where such a reach shows up instead.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from tests.unit._source_inventory_support import (
    ENTITY_PACKAGE,
    production_sources,
    synthetic_sources,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path

POPULATED_MEMBER_NAMES = frozenset({"model_fields_set", "__pydantic_fields_set__"})
"""Both spellings of the populated-member set: Pydantic's public property and the
slot beneath it, either of which materializes one for a published value."""

POPULATED_MEMBER_STATE = POPULATED_MEMBER_NAMES | {
    "MODEL_PRESENCE",
    "_PopulatedState",
    "instance_presence",
    "replace_instance_presence",
}
"""Every name that reaches a value's populated-member state, the descriptors over
it included, so a site cannot leave the inventory below by spelling the reach
differently."""

# Which shipped modules reach the populated-member set at all, under ANY of its
# names.
#
# Three, and none of them a reader. `_instance_state` binds the descriptor that
# answers for the name; `_pydantic_storage` holds Pydantic's own slot descriptor
# that descriptor is layered on; `_declaration` reserves the name from every
# class body, which is what makes the framework the only thing bound under it.
# Every OTHER module — the two frontends, edit, the descriptors, row derivation,
# graph construction — asks `is_present` instead, so no row, document, or
# relationship operation synthesizes a set for a value it merely reads.
#
# Stated over the whole of `POPULATED_MEMBER_STATE` rather than over the two
# spellings of the set itself, because a module reaching `instance_presence` or
# the raw slot descriptor synthesizes just as whole a set while naming neither.
MODULES_NAMING_THE_POPULATED_SET: dict[str, frozenset[str]] = {
    "_declaration": frozenset({"__pydantic_fields_set__"}),
    "_instance_state": frozenset(
        {
            "MODEL_PRESENCE",
            "_PopulatedState",
            "__pydantic_fields_set__",
            "instance_presence",
            "replace_instance_presence",
        }
    ),
    "_pydantic_storage": frozenset(
        {
            "MODEL_PRESENCE",
            "__pydantic_fields_set__",
            "instance_presence",
            "replace_instance_presence",
        }
    ),
}


def _spellings(tree: ast.AST, wanted: Iterable[str]) -> set[str]:
    """Every name in ``wanted`` that ``tree`` spells: as an attribute, a bare
    name, a string literal, or an import alias.

    Four, because a guard reading one of them admits the other three. A name a
    module assembles at run time — concatenated, interpolated, or read out of a
    variable — is spelled nowhere and lies outside what source shape settles at
    all; that boundary is the inventory's own, not an omission in it.
    """
    named = set(wanted)
    spelled: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            spelled.add(node.attr)
        elif isinstance(node, ast.Name):
            spelled.add(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            spelled.add(node.value)
        elif isinstance(node, ast.alias):
            spelled.update({node.name, node.asname or node.name})
    return spelled & named


def _modules_naming(
    over: Iterator[tuple[Path, str]], wanted: Iterable[str]
) -> dict[str, frozenset[str]]:
    """Each module's stem to the names of ``wanted`` its source spells."""
    named: dict[str, frozenset[str]] = {}
    for path, text in over:
        spelled = _spellings(ast.parse(text), wanted)
        if spelled:
            named[path.stem] = frozenset(spelled)
    return named


def test_the_populated_member_set_is_named_only_where_the_seam_owns_it() -> None:
    assert _modules_naming(production_sources(), POPULATED_MEMBER_STATE) == {
        stem: names for stem, names in MODULES_NAMING_THE_POPULATED_SET.items()
    }


def test_that_inventory_names_a_reader_that_asked_for_the_whole_set() -> None:
    # Both routes to a whole set, and the one operation that is neither: asking
    # the value for its populated members, and taking the descriptor the seam is
    # layered on straight out of the storage module.
    named = _modules_naming(
        synthetic_sources(
            {
                f"{ENTITY_PACKAGE}._new_codec": (
                    "def row(value):\n    return {name for name in value.model_fields_set}\n"
                ),
                f"{ENTITY_PACKAGE}._new_storage_reader": (
                    "from parallax.core.internal.entity._pydantic_storage "
                    "import instance_presence\n"
                    "\n"
                    "def row(value):\n    return {name for name in instance_presence(value)}\n"
                ),
                f"{ENTITY_PACKAGE}._new_reader": (
                    "def presence(value, bit):\n    return is_present(value, bit)\n"
                ),
            }
        ),
        POPULATED_MEMBER_STATE,
    )
    assert named == {
        "_new_codec": frozenset({"model_fields_set"}),
        "_new_storage_reader": frozenset({"instance_presence"}),
    }
