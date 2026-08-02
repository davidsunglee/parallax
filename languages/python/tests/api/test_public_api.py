"""Griffe public-API snapshot diff (§10 `api_surface` marker).

Python tooling cannot prove an export unused, so the compensating control is a
committed snapshot of every production distribution's declared public surface
(its ``__all__``). Any change to the public API is therefore a reviewed diff
against ``public_api.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from griffe import GriffeLoader, Module

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


def test_public_api_matches_committed_snapshot() -> None:
    expected: dict[str, list[str]] = json.loads(_SNAPSHOT.read_text())
    actual = {package: _public_api(package) for package in expected}
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
def test_exported_closed_contributor_algebras_document_their_variants(
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
    docstring = defining.members[name].docstring
    assert docstring is not None
    assert all(variant in docstring.value for variant in variants)
