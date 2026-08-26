"""The two claims about the instance-state Module that only its source settles.

Neither is a behavior a value can be asked about, so both are stated over the
source of ``parallax.core.entity`` and graded there.

**Presence is asked one member at a time.** A published value keeps no
``set[str]``; the set a caller sees is synthesized from its bitmap on request.
So an internal read that asks for the whole set builds one per value it looks at,
and nothing about the answer would say it had. What forbids that is not a rule to
remember but the shape of the Interface — internal code has
:func:`~parallax.core.entity._instance_state.is_present`, a membership test over
one bit — and the inventory below is what keeps the second operation out of
reach.

**The Module earns its keep by how much would come back without it.** Deleting it
puts the compact-versus-ordinary branch back at every site that imports it, so
the inventory of those sites IS the Locality it buys. It is an exact set rather
than a floor: a site leaving it is the Module growing shallower, and a site
joining it is a decision worth making deliberately.

Every inventory here is a function of the source handed to it and is shown on
both sides: run over synthetic source carrying the shape it grades, each names
that source's sites rather than this tree's. Each is exact over the reaches
source SPELLS — an attribute, a bare name, a string constant, an import — which
is the whole of what reading source settles; a name a module assembles at run
time denotes something only an interpreter knows, and the equivalence a value's
answers are graded by is where such a reach shows up instead.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from _source_inventory_support import (
    ENTITY_PACKAGE,
    ENTITY_SRC,
    declared_imports,
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

# Inside the Module, what reaches that state and why each one may.
#
# `_PopulatedMembers` is the descriptor, and the one site that SYNTHESIZES a set:
# it builds one out of the bitmap when a caller asks the value for its populated
# members, fresh each time and memoized nowhere. `is_present` reaches the state
# without building anything — for a published value it tests one bit, and for an
# ordinary one it tests membership of the set the value already holds.
# `carry_presence` is the one caller that needs the whole set, because what it
# builds is ordinary backing, which has nowhere but a `set[str]` to keep presence
# in. Module scope carries the imports, the descriptor's own binding, and the
# slot classification beside it, so what this pins is which DEFINITIONS reach the
# state — a function reaching it through an already-imported name is named here
# all the same.
INSTANCE_STATE_SITES_REACHING_PRESENCE: dict[str, frozenset[str]] = {
    "<module>": frozenset(
        {
            "MODEL_PRESENCE",
            "_PopulatedState",
            "__pydantic_fields_set__",
            "instance_presence",
            "replace_instance_presence",
        }
    ),
    "_PopulatedMembers": frozenset({"MODEL_PRESENCE", "replace_instance_presence"}),
    "carry_presence": frozenset({"_PopulatedState", "replace_instance_presence"}),
    "is_present": frozenset({"instance_presence"}),
}

# What would have to learn the backing again if `_instance_state` were deleted.
#
# Six sites, each taking exactly what it takes. `_declaration` builds every
# class's plan and hands each descriptor its ordinal; `_members` addresses the
# row from those ordinals; both frontends extend the root that answers Pydantic
# for a value's state, and derive edited copies through it; `_edit` partitions a
# value's named state; `_row_codec` selects by presence and reads the provenance
# slot. Delete the Module and the tuple, the bitmap, and the ordinal arithmetic
# reappear at all six.
#
# The publication writer is deliberately absent, and is the one site that would
# otherwise belong: it writes ordinary Pydantic state one member at a time, so it
# takes nothing from the Module and learns nothing about the backing.
INSTANCE_STATE_CONSUMERS: dict[str, frozenset[str]] = {
    "parallax.core.entity._declaration": frozenset({"PublicationPlan", "install"}),
    "parallax.core.entity._edit": frozenset({"named_state"}),
    "parallax.core.entity._entity": frozenset(
        {"BackedModel", "carry_slots_beside_state", "named_state", "restated"}
    ),
    "parallax.core.entity._members": frozenset({"COMPACT_STATE_SLOT", "is_published", "plan_of"}),
    "parallax.core.entity._row_codec": frozenset({"is_present", "named_state", "plan_of"}),
    "parallax.core.entity._value_object": frozenset(
        {
            "BackedModel",
            "carry_presence",
            "carry_slots_beside_state",
            "is_present",
            "plan_of",
            "restated",
        }
    ),
}

_INSTANCE_STATE = f"{ENTITY_PACKAGE}._instance_state"


def _spellings(tree: ast.AST, wanted: Iterable[str]) -> set[str]:
    """Every name in ``wanted`` that ``tree`` spells: as an attribute, a bare
    name, a string literal, or an import alias.

    Four, because a guard reading one of them admits the other three. A name a
    module assembles at run time — concatenated, interpolated, or read out of a
    variable — is spelled nowhere and lies outside what source shape settles at
    all; that boundary is the inventories' own, not an omission in them.
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


def _top_level_sites(text: str, wanted: Iterable[str]) -> dict[str, frozenset[str]]:
    """Each top-level definition of one module to the names of ``wanted`` it spells.

    Module scope answers under ``<module>``, which is where a module-level
    binding or constant reaching one of them lands.
    """
    tree = ast.parse(text)
    sites: dict[str, frozenset[str]] = {}
    at_module = ast.Module(
        body=[
            node
            for node in tree.body
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        ],
        type_ignores=[],
    )
    for node in [at_module, *tree.body]:
        if isinstance(node, ast.Module):
            name = "<module>"
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            name = node.name
        else:
            continue
        spelled = _spellings(node, wanted)
        if spelled:
            sites[name] = frozenset(spelled)
    return sites


def _instance_state_source() -> str:
    return (ENTITY_SRC / "_instance_state.py").read_text(encoding="utf-8")


def _naming_the_module_as_text(over: Iterator[tuple[Path, str]]) -> list[str]:
    """Each module spelling the instance-state Module's own dotted name as a string.

    An import statement is not the only spelling of a reach: a module named to
    ``importlib.import_module`` or ``__import__`` is a string constant, which the
    consumer inventory — stated over import statements — does not read. Nothing
    shipped spells one, so the two together decide every reach the source
    actually spells.
    """
    return [
        path.stem
        for path, text in over
        if any(
            isinstance(node, ast.Constant) and node.value == _INSTANCE_STATE
            for node in ast.walk(ast.parse(text))
        )
    ]


def _consumers(over: Iterator[tuple[Path, str]]) -> dict[str, frozenset[str]]:
    """Each module importing the instance-state Module, and what it imports."""
    taken: dict[str, set[str]] = {}
    for one in declared_imports(over):
        if one.source == _INSTANCE_STATE:
            taken.setdefault(one.importer, set()).add(one.name)
        elif not one.source and one.name == _INSTANCE_STATE:
            taken.setdefault(one.importer, set()).add("<the module itself>")
    return {importer: frozenset(names) for importer, names in taken.items()}


# --------------------------------------------------------------------------- #
# Presence is asked one member at a time
# --------------------------------------------------------------------------- #


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
                    "from parallax.core.entity._pydantic_storage import instance_presence\n"
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


def test_only_the_descriptor_synthesizes_a_populated_member_set() -> None:
    assert (
        _top_level_sites(_instance_state_source(), POPULATED_MEMBER_STATE)
        == INSTANCE_STATE_SITES_REACHING_PRESENCE
    )


def test_that_inventory_names_a_second_function_reaching_the_same_state() -> None:
    assert _top_level_sites(
        "PRESENCE = '__pydantic_fields_set__'\n"
        "\n"
        "def is_present(value, bit):\n"
        "    return bit in instance_presence(value)\n"
        "\n"
        "def declared(value):\n"
        "    return {name: value.model_fields_set for name in ()}\n",
        POPULATED_MEMBER_STATE,
    ) == {
        "<module>": frozenset({"__pydantic_fields_set__"}),
        "is_present": frozenset({"instance_presence"}),
        "declared": frozenset({"model_fields_set"}),
    }


# --------------------------------------------------------------------------- #
# The deletion test, as an assertion
# --------------------------------------------------------------------------- #


def test_the_sites_backing_logic_would_return_to_are_exactly_these_six() -> None:
    # Read over every shipped distribution rather than over the package alone,
    # which is what makes this the Module's whole consumer set rather than the
    # part of it that happens to live nearby.
    consumers = _consumers(production_sources())
    assert consumers == {importer: names for importer, names in INSTANCE_STATE_CONSUMERS.items()}
    assert len(consumers) == 6
    assert _naming_the_module_as_text(production_sources()) == []


def test_that_inventory_names_a_new_consumer_and_passes_a_resembling_import() -> None:
    assert _consumers(
        synthetic_sources(
            {
                f"{ENTITY_PACKAGE}._new_writer": (
                    "from parallax.core.entity._instance_state import allocate, publish\n"
                    "from parallax.core.entity._pydantic_storage import instance_state\n"
                ),
                f"{ENTITY_PACKAGE}._new_bystander": (
                    "import parallax.core.entity._instance_state\n"
                    "from parallax.core.entity import Entity\n"
                    "from parallax.core.entity_records._instance_state import publish\n"
                ),
            }
        )
    ) == {
        f"{ENTITY_PACKAGE}._new_writer": frozenset({"allocate", "publish"}),
        f"{ENTITY_PACKAGE}._new_bystander": frozenset({"<the module itself>"}),
    }


def test_that_inventory_names_a_consumer_that_spelled_the_module_rather_than_imported_it() -> None:
    assert _naming_the_module_as_text(
        synthetic_sources(
            {
                f"{ENTITY_PACKAGE}._new_loader": (
                    "import importlib\n"
                    "\n"
                    "def door():\n"
                    '    return importlib.import_module("parallax.core.entity._instance_state")\n'
                ),
                f"{ENTITY_PACKAGE}._new_neighbour": (
                    'MODULE = "parallax.core.entity._instance_state_records"\n'
                ),
            }
        )
    ) == ["_new_loader"]
