"""Griffe public-API snapshot diff.

Python tooling cannot prove an export unused, so the compensating control is a
committed snapshot of every public production module's declared surface (its
``__all__``). Any change to the public API is therefore a reviewed diff against
``public_api.json``.

An export list cannot observe a constructor added to an exported class, so the
snapshot also records, for a class named as ``<public module>:<Class>``, the
public classmethod constructors that class declares.
"""

from __future__ import annotations

import functools
import inspect
import json
from collections.abc import Callable, Iterable, Mapping
from importlib import import_module
from pathlib import Path
from types import MappingProxyType
from typing import Final, TypeAliasType, get_args, get_type_hints

import pytest
from griffe import Alias, Class, GriffeLoader, Module, Object

from parallax import snapshot
from parallax.core import ParallaxError
from parallax.core.internal import read_delivery, wire
from parallax.core.internal.base import JSON
from parallax.snapshot import (
    ReadOnlyTxnContext,
    ScopedDatabase,
    TxnContext,
    WireDatabaseView,
    WireTransactionView,
)
from tests._support.distributions import (
    DISTRIBUTION_ROOTS,
    PRODUCTION_PACKAGES,
    importable_submodules,
)

_SNAPSHOT = Path(__file__).parent / "public_api.json"

_PRODUCTION_ROOTS: Final = tuple(DISTRIBUTION_ROOTS[package] for package in PRODUCTION_PACKAGES)


@functools.cache
def _namespace() -> GriffeLoader:
    # Griffe loads a dotted path's whole top-level package and processes it the
    # same way whichever object was asked for, so one load of the namespace
    # serves every module these checks read.
    loader = GriffeLoader()
    loader.load("parallax")
    return loader


def _member(path: str) -> Object | Alias:
    return _namespace().modules_collection.get_member(path)


def _module(path: str) -> Module:
    module = _member(path)
    assert isinstance(module, Module), path
    return module


def _public_modules(roots: Iterable[Module]) -> list[Module]:
    """Each root and every module beneath it reached only through public names.

    A child whose name starts with ``_`` or is ``internal`` is private, and so
    is everything beneath it. Re-exported modules are aliases, not children.
    Griffe parses source rather than importing it, so a module whose optional
    dependencies are absent is still found.
    """
    discovered: list[Module] = []
    pending = list(roots)
    while pending:
        module = pending.pop()
        discovered.append(module)
        pending.extend(
            child
            for name, child in module.members.items()
            if isinstance(child, Module) and not name.startswith("_") and name != "internal"
        )
    return sorted(discovered, key=lambda module: module.path)


@functools.cache
def _production_modules() -> tuple[Module, ...]:
    return tuple(_public_modules(_module(root) for root in _PRODUCTION_ROOTS))


def _declared_exports(module: Module) -> list[str]:
    assert module.exports is not None, f"public module {module.path} must declare __all__"
    return sorted(str(name) for name in module.exports)


def _classmethod_constructors(declared: Object | Alias) -> list[str]:
    if isinstance(declared, Alias):
        declared = declared.final_target
    assert isinstance(declared, Class), declared.path
    return sorted(
        name
        for name, member in declared.members.items()
        if member.is_public and "classmethod" in member.labels
    )


def _snapshot_correction(actual: Mapping[str, list[str]], expected: Mapping[str, list[str]]) -> str:
    corrected = {key: names for key, names in sorted(actual.items()) if expected.get(key) != names}
    stale = sorted(expected.keys() - actual.keys())
    lines = [
        "public API drift detected; review the change and, if intended, update "
        f"{_SNAPSHOT.relative_to(_SNAPSHOT.parents[2])}"
    ]
    if corrected:
        lines += ["with these entries:", json.dumps(corrected, indent=2)]
    if stale:
        lines += ["and remove these keys:", json.dumps(stale, indent=2)]
    return "\n".join(lines)


def test_public_api_matches_committed_snapshot() -> None:
    expected: dict[str, list[str]] = json.loads(_SNAPSHOT.read_text())
    actual = {module.path: _declared_exports(module) for module in _production_modules()} | {
        recorded: _classmethod_constructors(_member(recorded.replace(":", ".")))
        for recorded in expected
        if ":" in recorded
    }
    assert actual == expected, _snapshot_correction(actual, expected)


def test_every_application_name_has_one_home() -> None:
    homes: dict[str, list[str]] = {}
    for module in _production_modules():
        for name in _declared_exports(module):
            homes.setdefault(name, []).append(module.path)
    assert {name: paths for name, paths in homes.items() if len(paths) > 1} == {}


def _load(root: Path, files: Mapping[str, str]) -> Module:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    package = GriffeLoader(search_paths=[root]).load("pkg")
    assert isinstance(package, Module)
    return package


def test_discovery_descends_through_public_children_only(tmp_path: Path) -> None:
    package = _load(
        tmp_path,
        {
            "pkg/__init__.py": "from pkg import leaf as republished\n",
            "pkg/leaf.py": "",
            "pkg/added.py": "",
            "pkg/nested/__init__.py": "",
            "pkg/nested/deeper.py": "",
            "pkg/nested/_private.py": "",
            "pkg/_private/__init__.py": "",
            "pkg/_private/public_name.py": "",
            "pkg/internal/__init__.py": "",
            "pkg/internal/public_name.py": "",
        },
    )

    assert [module.path for module in _public_modules([package])] == [
        "pkg",
        "pkg.added",
        "pkg.leaf",
        "pkg.nested",
        "pkg.nested.deeper",
    ]


def test_production_discovery_covers_every_distribution_root_but_conformance() -> None:
    discovered = {module.path for module in _production_modules()}

    assert {root for root in DISTRIBUTION_ROOTS.values() if root not in discovered} == {
        "parallax.conformance"
    }
    assert not {path for path in discovered if path.startswith("parallax.conformance")}


def test_a_public_module_without_all_names_itself(tmp_path: Path) -> None:
    package = _load(tmp_path, {"pkg/__init__.py": "", "pkg/silent.py": "VALUE = 1\n"})

    with pytest.raises(AssertionError, match=r"public module pkg\.silent must declare __all__"):
        _declared_exports(package.modules["silent"])


def test_exports_and_constructors_are_recorded_sorted(tmp_path: Path) -> None:
    package = _load(
        tmp_path,
        {
            "pkg/__init__.py": (
                "from pkg._made import Made\n__all__ = ['zeta', 'Made', 'alpha']\n"
            ),
            "pkg/_made.py": (
                "class Made:\n"
                "    @classmethod\n"
                "    def zeta(cls): ...\n"
                "    @classmethod\n"
                "    def alpha(cls): ...\n"
                "    @classmethod\n"
                "    def _hidden(cls): ...\n"
                "    @staticmethod\n"
                "    def helper(): ...\n"
                "    def method(self): ...\n"
            ),
        },
    )

    assert _declared_exports(package) == ["Made", "alpha", "zeta"]
    assert _classmethod_constructors(package.members["Made"]) == ["alpha", "zeta"]


def test_drift_prints_the_entries_that_correct_the_snapshot() -> None:
    correction = _snapshot_correction(
        {"kept": ["a"], "changed": ["a", "b"], "added": ["c"]},
        {"kept": ["a"], "changed": ["a"], "removed": ["d"]},
    )

    corrected, _, stale = correction.partition("and remove these keys:")
    assert json.loads(corrected.partition("with these entries:")[2]) == {
        "added": ["c"],
        "changed": ["a", "b"],
    }
    assert json.loads(stale) == ["removed"]


@pytest.mark.parametrize(
    ("public_module", "defining_module", "name", "variants"),
    [
        (
            "parallax.core.internal.storage_layout",
            "parallax.core.internal.storage_layout._facet",
            "ColumnContributor",
            (
                "AttributeIdentity",
                "ValueObjectIdentity",
                "InheritanceDiscriminator",
                "RelationalDocument",
            ),
        ),
        (
            "parallax.core.internal.storage_layout._facet",
            "parallax.core.internal.storage_layout._facet",
            "MemberPlacement",
            ("DirectColumn", "DocumentPath"),
        ),
        (
            "parallax.core.internal.inheritance",
            "parallax.core.internal.inheritance._table_groups",
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
    assert not {"RowsResult", "PublishedRow"} & set(
        _declared_exports(_module("parallax.core.internal.read_delivery"))
    )
    assert not hasattr(read_delivery, "RowsResult")
    assert not hasattr(read_delivery, "PublishedRow")
    assert "InvalidData" in _declared_exports(_module("parallax.core.internal.read_delivery"))
    assert {"WireValue", "edge_of", "pin_of"} <= set(
        _declared_exports(_module("parallax.snapshot"))
    )


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
        _declared_exports(_module("parallax.core.internal.unit_work"))
    )


_LIFECYCLE_VOCABULARY: Final = "parallax.core.execution_lifecycle"
_LIFECYCLE_SEAMS: Final = frozenset(
    {
        "ExecutionLifecycleHandler",
        "ExecutionLifecycleHandlerError",
        "ExecutionLifecycleProvider",
        "FanoutLifecycleProvider",
        "LIFECYCLE_PROVIDER_FAILED",
        "LIFECYCLE_REENTERED",
        "LoggingLifecycleProvider",
        "PoolAvailable",
        "PoolDetached",
        "PoolMetricsObserver",
        "PoolMetricsSource",
        "PoolObservation",
        "PoolSample",
        "PoolUnavailable",
        "RootExecution",
    }
)


def test_the_lifecycle_seams_are_published_by_the_core_root_not_the_vocabulary() -> None:
    assert set(_declared_exports(_module("parallax.core"))) >= _LIFECYCLE_SEAMS
    assert not _LIFECYCLE_SEAMS & set(_declared_exports(_module(_LIFECYCLE_VOCABULARY)))


def _family(alias: object, owners: frozenset[str]) -> dict[str, type]:
    """Every class ``owners`` define that ``alias`` reaches through unions,
    aliases, and the fields of the classes it reaches."""
    reached: dict[str, type] = {}
    pending: list[object] = [alias]
    while pending:
        current = pending.pop()
        if isinstance(current, TypeAliasType):
            pending.append(current.__value__)
        elif isinstance(current, type) and current.__module__ in owners:
            if current.__name__ not in reached:
                reached[current.__name__] = current
                pending.extend(get_type_hints(current).values())
        else:
            pending.extend(get_args(current))
    return reached


def test_the_lifecycle_vocabulary_publishes_the_whole_portable_event_family() -> None:
    vocabulary = import_module(_LIFECYCLE_VOCABULARY)
    family = _family(
        vocabulary.ExecutionEvent,
        frozenset({f"{_LIFECYCLE_VOCABULARY}._events", f"{_LIFECYCLE_VOCABULARY}._diagnostics"}),
    )
    assert sum(name.endswith(("Started", "Finished")) for name in family) == 18
    assert {name: getattr(vocabulary, name, None) for name in family} == family
    published = set(_declared_exports(_module(_LIFECYCLE_VOCABULARY)))
    assert set(family) | {"ExecutionEvent"} == published


@pytest.mark.parametrize(
    "home",
    [
        "parallax.core",
        _LIFECYCLE_VOCABULARY,
        "parallax.core.introspection",
        "parallax.evolution",
        "parallax.evolution.operations",
    ],
)
def test_an_application_home_publishes_the_objects_their_owners_define(home: str) -> None:
    module = import_module(home)
    for name in _declared_exports(_module(home)):
        value = getattr(module, name)
        if isinstance(value, type) or inspect.isfunction(value):
            assert value.__module__ != home, name
            assert getattr(import_module(value.__module__), value.__qualname__) is value, name


def test_the_root_publishes_the_stored_data_issue_vocabulary_its_owner_defines() -> None:
    root = import_module("parallax.core")
    owner = import_module("parallax.core._stored_data")
    assert root.StoredDataIssue is owner.StoredDataIssue
    assert root.MISSING_STORED_VALUE is owner.MISSING_STORED_VALUE


_ERROR_SURFACE: Final[dict[str, frozenset[str]]] = {
    "parallax.core": frozenset(
        {
            "ParallaxError",
            "UsageError",
            "InvalidValueError",
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
    "parallax.evolution": frozenset({"UnsupportedSchemaEvolutionError"}),
}
"""Every exception class an application may catch, by the module that defines
its import home."""

_MODULE_PRIVATE_CARRIERS: Final = frozenset(
    {
        "parallax.core.internal.auto_retry._RetryCandidate",
        "parallax.core.internal.base._neutral.JsonCarrierFailure",
        "parallax.core.internal.document_codec._leaf.LeafEncodingError",
        "parallax.core.internal.document_codec._plan.AuthoringRefusal",
        "parallax.core.internal.document_codec._plan._Refused",
        "parallax.core.internal.entity._row_fill._InvalidOccurrence",
        "parallax.core.internal.wire._codec._JsonFailure",
        "parallax.core.internal.wire._json._HostSpellingChangesMeaning",
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
    exported: dict[str, type[BaseException]] = {}
    for module in _production_modules():
        for name in _declared_exports(module):
            value = getattr(import_module(module.path), name)
            if isinstance(value, type) and issubclass(value, BaseException):
                exported[f"{module.path}.{name}"] = value
    return exported


def _shipped_exceptions() -> list[type[BaseException]]:
    for root in _PRODUCTION_ROOTS:
        for module in importable_submodules(root):
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
    assert len(_error_surface()) == 21
    root = import_module("parallax.core")
    assert {
        name
        for name in _declared_exports(_module("parallax.core"))
        if isinstance(value := getattr(root, name), type) and issubclass(value, BaseException)
    } == _ERROR_SURFACE["parallax.core"]


def test_no_public_module_exports_an_exception_outside_the_error_surface() -> None:
    surface = _error_surface()
    assert {
        exported: kind for exported, kind in _exported_exceptions().items() if kind not in surface
    } == {}


def test_every_shipped_exception_is_a_parallax_error_or_a_module_private_carrier() -> None:
    assert {
        _qualified(kind) for kind in _shipped_exceptions() if not issubclass(kind, ParallaxError)
    } == _MODULE_PRIVATE_CARRIERS
