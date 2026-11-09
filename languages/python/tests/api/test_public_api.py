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

import functools
import json
from collections.abc import Callable, Mapping
from importlib import import_module
from pathlib import Path
from types import MappingProxyType
from typing import Final, TypeAliasType, get_args

import pytest
from griffe import Alias, Class, GriffeLoader, Module

from parallax import snapshot
from parallax.core import ParallaxError, read_delivery, wire
from parallax.core.base import JSON
from parallax.snapshot import (
    ReadOnlyTxnContext,
    ScopedDatabase,
    TxnContext,
    WireDatabaseView,
    WireTransactionView,
)
from tests._support.distributions import TOP_PACKAGE_NAMES, importable_submodules

_SNAPSHOT = Path(__file__).parent / "public_api.json"


@functools.cache
def _namespace() -> GriffeLoader:
    # Griffe loads a dotted path's whole top-level package and processes it the
    # same way whichever object was asked for, so one load of the namespace
    # serves every module these checks read.
    loader = GriffeLoader()
    loader.load("parallax")
    return loader


def _module(path: str) -> Module:
    module = _namespace().modules_collection.get_member(path)
    assert isinstance(module, Module), path
    return module


def _public_api(package: str) -> list[str]:
    module = _module(package)
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
    declared = _module(package).members[class_name]
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
            "parallax.core.storage_layout._facet",
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
    public = _module(public_module)
    _module(defining_module)
    assert public.exports is not None and name in {str(export) for export in public.exports}
    alias = getattr(import_module(defining_module), name)
    assert isinstance(alias, TypeAliasType)
    assert {variant.__name__ for variant in get_args(alias.__value__)} == set(variants)


@pytest.mark.parametrize(
    "handle",
    [ScopedDatabase, TxnContext, ReadOnlyTxnContext, WireDatabaseView, WireTransactionView],
    ids=lambda handle: handle.__name__,
)
def test_no_read_handle_offers_row_delivery(handle: type) -> None:
    assert not [name for name in dir(handle) if "row" in name and not name.startswith("_")]


def test_row_envelopes_left_the_surface_and_what_graph_reads_publish_stayed() -> None:
    assert not {"RowsResult", "PublishedRow"} & set(_public_api("parallax.core.read_delivery"))
    assert not hasattr(read_delivery, "RowsResult")
    assert not hasattr(read_delivery, "PublishedRow")
    assert "InvalidData" in _public_api("parallax.core.read_delivery")
    assert {"WireValue", "edge_of", "pin_of"} <= set(_public_api("parallax.snapshot"))


def test_snapshot_exports_the_one_wire_value_alias() -> None:
    assert snapshot.WireValue is wire.WireValue


def _as_wire_value(value: snapshot.WireValue) -> snapshot.WireValue:
    return value


def test_an_immutable_mapping_is_a_wire_value() -> None:
    nested: Mapping[str, snapshot.WireValue] = MappingProxyType({"city": "Oslo"})
    frozen: Mapping[str, snapshot.WireValue] = MappingProxyType({"address": nested, "tags": ["a"]})

    assert _as_wire_value(frozen) is frozen
    assert wire.decode_wire(JSON, frozen) == {"address": {"city": "Oslo"}, "tags": ["a"]}


def test_a_published_wire_node_is_a_wire_value() -> None:
    published: Callable[[snapshot.WireEntity], snapshot.WireValue] = _as_wire_value

    assert published is _as_wire_value


def test_unit_work_exports_the_codes_a_refused_write_instruction_carries() -> None:
    assert {"WRITE_INSTRUCTION_INVALID", "WriteRejectionCode"} <= set(
        _public_api("parallax.core.unit_work")
    )


_ERROR_SURFACE: Final[dict[str, frozenset[str]]] = {
    "parallax.core": frozenset(
        {
            "ParallaxError",
            "UsageError",
            "UnsupportedError",
            "EditError",
            "MetamodelValidationError",
            "UnloadedRelationshipError",
            "NoResultFound",
            "TooManyResultsFound",
            "InvalidDataError",
            "ConflictError",
            "WritePreconditionError",
            "PublicationConflictError",
            "DatabaseError",
            "ConnectionAcquisitionError",
            "DatabaseStartupError",
            "CredentialResolutionError",
            "TransactionRollbackError",
            "InternalError",
        }
    ),
    "parallax.descriptor": frozenset({"DescriptorError"}),
    "parallax.evolution.schema_delta": frozenset({"UnsupportedSchemaEvolutionError"}),
}
"""Every exception class an application may catch, by the module that defines
its import home."""

_EXECUTION_WRAPPER: Final = "parallax.core._execution._adoption.ExecutionFailure"
"""The execution-boundary wrapper, the one exported exception outside the root."""

_MODULE_PRIVATE_CARRIERS: Final = frozenset(
    {
        "parallax.core.auto_retry._RetryCandidate",
        "parallax.core.base._neutral.JsonCarrierFailure",
        "parallax.core.document_codec._leaf.LeafEncodingError",
        "parallax.core.document_codec._plan.AuthoringRefusal",
        "parallax.core.document_codec._plan._Refused",
        "parallax.core.entity._row_fill._InvalidOccurrence",
        "parallax.core.wire._codec._JsonFailure",
        "parallax.core.wire._json._HostSpellingChangesMeaning",
        "parallax.postgres._connection.IncompatibleSessionError",
        "parallax.postgres._context._Condition",
        "parallax.postgres._context._FellBack",
        "parallax.postgres._pool_metrics._MalformedStatistics",
        "parallax.postgres._route.ProbeMismatch",
        "parallax.postgres._startup._ReadinessFailure",
        "parallax.snapshot._publication._graph_view._RowsIncompatible",
    }
)
"""Exceptions raised and caught inside their own distribution, which no caller
ever receives."""


def _qualified(kind: type) -> str:
    return f"{kind.__module__}.{kind.__qualname__}"


def _error_surface() -> frozenset[type[BaseException]]:
    return frozenset(
        getattr(import_module(module), name)
        for module, names in _ERROR_SURFACE.items()
        for name in names
    )


def _exported_exceptions() -> dict[str, type[BaseException]]:
    expected: dict[str, list[str]] = json.loads(_SNAPSHOT.read_text())
    modules = {recorded for recorded in expected if ":" not in recorded}
    exported: dict[str, type[BaseException]] = {}
    for module in sorted({*modules, "parallax.core.unit_work"}):
        for name in _public_api(module):
            value = getattr(import_module(module), name)
            if isinstance(value, type) and issubclass(value, BaseException):
                exported[f"{module}.{name}"] = value
    return exported


def _shipped_exceptions() -> list[type[BaseException]]:
    for package in TOP_PACKAGE_NAMES:
        if package != "parallax.conformance":
            for module in importable_submodules(package):
                import_module(module)
    pending: list[type[BaseException]] = [BaseException]
    shipped: list[type[BaseException]] = []
    while pending:
        kind = pending.pop()
        pending.extend(kind.__subclasses__())
        if kind.__module__.startswith("parallax.") and not kind.__module__.startswith(
            "parallax.conformance"
        ):
            shipped.append(kind)
    return shipped


def test_every_application_error_is_rooted_in_parallax_error() -> None:
    assert all(issubclass(kind, ParallaxError) for kind in _error_surface())
    assert len(_error_surface()) == 20
    assert {
        name for name in _public_api("parallax.core") if name.endswith(("Error", "Found"))
    } == _ERROR_SURFACE["parallax.core"]


def test_no_public_module_exports_an_exception_outside_the_error_surface() -> None:
    surface = _error_surface()
    assert {
        exported: kind
        for exported, kind in _exported_exceptions().items()
        if kind not in surface and _qualified(kind) != _EXECUTION_WRAPPER
    } == {}


def test_every_shipped_exception_is_a_parallax_error_or_a_module_private_carrier() -> None:
    assert {
        _qualified(kind) for kind in _shipped_exceptions() if not issubclass(kind, ParallaxError)
    } == _MODULE_PRIVATE_CARRIERS | {_EXECUTION_WRAPPER}
