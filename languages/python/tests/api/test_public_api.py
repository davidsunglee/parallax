"""Griffe public-API snapshot diff (`api_surface` marker).

Python tooling cannot prove an export unused, so the compensating control is a
committed snapshot of every production distribution's declared public surface
(its ``__all__``). Any change to the public API is therefore a reviewed diff
against ``public_api.json``.

An export list cannot observe a constructor added to an exported class, so the
snapshot also records, for a class named as ``<public module>:<Class>``, the
public classmethod constructors that class declares.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import TypeAliasType, get_args

import pytest
from griffe import Alias, Class, GriffeLoader, Module

_SNAPSHOT = Path(__file__).parent / "public_api.json"


def _public_api(package: str) -> list[str]:
    module = GriffeLoader().load(package)
    assert isinstance(module, Module), package
    exports = module.exports
    if exports is None:
        # No ``__all__``: public surface is every non-underscore public member.
        return sorted(
            name
            for name, member in module.members.items()
            if member.is_public and not name.startswith("_")
        )
    return sorted(str(name) for name in exports)


def _public_constructors(public_class: str) -> list[str]:
    package, _, class_name = public_class.partition(":")
    module = GriffeLoader().load(package)
    assert isinstance(module, Module), package
    declared = module.members[class_name]
    if isinstance(declared, Alias):
        declared = declared.final_target
    assert isinstance(declared, Class), public_class
    return sorted(
        name
        for name, member in declared.members.items()
        if member.is_public and "classmethod" in member.labels
    )


def _public_surface(recorded: str) -> list[str]:
    return _public_constructors(recorded) if ":" in recorded else _public_api(recorded)


def test_public_api_matches_committed_snapshot() -> None:
    expected: dict[str, list[str]] = json.loads(_SNAPSHOT.read_text())
    actual = {recorded: _public_surface(recorded) for recorded in expected}
    assert actual == expected, (
        "public API drift detected; review the change and update "
        f"{_SNAPSHOT.relative_to(_SNAPSHOT.parents[2])} if intended"
    )


@pytest.mark.parametrize(
    ("public_module", "defining_module", "name", "variants"),
    [
        (
            "parallax.core.storage_layout",
            "parallax.core.storage_layout._facet",
            "ColumnContributor",
            (
                "AttributeIdentity",
                "ValueObjectIdentity",
                "InheritanceDiscriminator",
                "RelationalDocument",
            ),
        ),
        (
            "parallax.core.storage_layout",
            "parallax.core.storage_layout._facet",
            "MemberPlacement",
            ("DirectColumn", "DocumentPath"),
        ),
        (
            "parallax.core.inheritance",
            "parallax.core.inheritance._table_groups",
            "TableGroupContributor",
            (
                "AttributeTableContributor",
                "TopLevelValueObjectTableContributor",
                "TablePerHierarchyTagContributor",
            ),
        ),
    ],
)
def test_exported_closed_contributor_algebras_have_expected_variants(
    public_module: str,
    defining_module: str,
    name: str,
    variants: tuple[str, ...],
) -> None:
    loader = GriffeLoader()
    public = loader.load(public_module)
    defining = loader.load(defining_module)
    assert isinstance(public, Module)
    assert isinstance(defining, Module)
    assert public.exports is not None and name in {str(export) for export in public.exports}
    alias = getattr(import_module(defining_module), name)
    assert isinstance(alias, TypeAliasType)
    assert {variant.__name__ for variant in get_args(alias.__value__)} == set(variants)
