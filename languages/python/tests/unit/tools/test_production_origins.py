from __future__ import annotations

import importlib.machinery
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Final, cast

import pytest

import feature_boundary_reading
import instance_state_reading
import lifecycle_overhead
import production_origins as origins
import snapshot_delivery_reading
import time_interval_runtime
import write_lowering_reading
from parallax.conformance.budget import BudgetContract

WORKSPACE = origins.WORKSPACE
ABI = importlib.machinery.EXTENSION_SUFFIXES[0]


def _module(
    name: str,
    origin: str | None,
    *,
    loader: object | None = None,
    path: list[str] | None = None,
) -> ModuleType:
    module = ModuleType(name)
    if loader is None and origin is not None:
        loader = (
            importlib.machinery.SourceFileLoader(name, origin)
            if origin.endswith(".py")
            else importlib.machinery.ExtensionFileLoader(name, origin)
        )
    module.__spec__ = cast("Any", SimpleNamespace(origin=origin, loader=loader))
    if path is not None:
        module.__path__ = path
    return module


def _source(relative: str) -> str:
    return str(WORKSPACE / relative)


_CORE = "packages/parallax-core/src"
_POSTGRES = "packages/parallax-postgres/src"


def test_source_roots_treat_the_workspace_literally_and_include_hidden_packages(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace[one]"
    hidden = workspace / "packages/.hidden/src"
    visible = workspace / "packages/visible/src"
    for source in (hidden, visible, tmp_path / "workspaceo/packages/decoy/src"):
        source.mkdir(parents=True)
    assert origins.source_roots(workspace) == tuple(sorted((hidden.resolve(), visible.resolve())))


def test_the_checkouts_own_sources_and_an_abi_matched_loader_extension_break_no_rule() -> None:
    modules = {
        "parallax": _module("parallax", None, path=[_source(f"{_CORE}/parallax")]),
        "parallax.core": _module(
            "parallax.core",
            _source(f"{_CORE}/parallax/core/__init__.py"),
            path=[_source(f"{_CORE}/parallax/core")],
        ),
        "parallax.core.entity._row_fill": _module(
            "parallax.core.entity._row_fill", _source(f"{_CORE}/parallax/core/entity/_row_fill.py")
        ),
        "parallax.postgres._cloaders_binary": _module(
            "parallax.postgres._cloaders_binary",
            _source(f"{_POSTGRES}/parallax/postgres/_cloaders_binary{ABI}"),
        ),
        "json": json,
        "elsewhere": _module("elsewhere", "/nowhere/elsewhere.so"),
    }
    assert origins.origin_findings(modules) == []


@pytest.mark.parametrize(
    ("module", "finding"),
    [
        (
            _module("parallax.core.entity._row_fill", "/site-packages/parallax/core/_row_fill.py"),
            "outside the checkout's package sources",
        ),
        (
            _module(
                "parallax.core.entity._row_fill",
                _source(f"{_CORE}/parallax/core/entity/_row_fill{ABI}"),
            ),
            "which is not a .py source",
        ),
        (
            _module(
                "parallax.core.entity._row_fill",
                _source(f"{_CORE}/parallax/core/entity/__pycache__/_row_fill.pyc"),
                loader=importlib.machinery.SourcelessFileLoader("_row_fill", "x.pyc"),
            ),
            "which is not a .py source",
        ),
        (
            _module(
                "parallax.postgres._cloaders_binary",
                _source(f"{_POSTGRES}/parallax/postgres/_cloaders_binary.cpython-30-other.so"),
            ),
            "neither a source nor this interpreter's extension",
        ),
        (_module("parallax.core.generated", None), "has no origin"),
        (
            _module(
                "parallax", None, path=[_source(f"{_CORE}/parallax"), "/site-packages/parallax"]
            ),
            "searches /site-packages/parallax",
        ),
    ],
)
def test_every_module_outside_the_rule_is_named(module: ModuleType, finding: str) -> None:
    (found,) = origins.origin_findings({module.__name__: module})
    assert found.startswith(module.__name__)
    assert finding in found


def test_a_process_holding_a_foreign_production_module_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origins.require_source_origins()
    monkeypatch.setitem(
        sys.modules, "parallax.stale", _module("parallax.stale", "/elsewhere/parallax/stale.py")
    )
    with pytest.raises(RuntimeError, match=r"parallax\.stale was loaded from /elsewhere"):
        origins.require_source_origins()
    with pytest.raises(RuntimeError, match=r"parallax\.stale"):
        origins.loaded_origins()


def test_loaded_origins_record_only_what_was_loaded() -> None:
    loaded, *unloaded = origins.MEASURED_MODULES
    relative = "packages/parallax-core/src/parallax/core/read_delivery/_row_recording.py"
    record = origins.loaded_origins({loaded: _module(loaded, _source(relative))})
    assert record == {loaded: relative, **dict.fromkeys(unloaded, origins.NOT_LOADED)}


def test_a_reported_record_names_each_inventory_module_once() -> None:
    record = dict.fromkeys(origins.MEASURED_MODULES, origins.NOT_LOADED)
    assert origins.reported_origins(record) == record
    first, *rest = origins.MEASURED_MODULES
    malformed: tuple[object, ...] = (
        None,
        [],
        dict.fromkeys(rest, origins.NOT_LOADED),
        record | {"parallax.unlisted": origins.NOT_LOADED},
        record | {first: ""},
        record | {first: 1},
    )
    for value in malformed:
        with pytest.raises(ValueError, match=origins.ORIGINS_FIELD):
            origins.reported_origins(value)


def test_resolution_answers_every_inventory_module_as_a_checkout_source() -> None:
    record = origins.resolved_origins()
    assert list(record) == list(origins.MEASURED_MODULES)
    for name, origin in record.items():
        assert origin.startswith("packages/") and origin.endswith(".py"), name
        assert (WORKSPACE / origin).is_file()


def test_checking_a_process_imports_nothing_it_had_not_loaded() -> None:
    program = (
        "import sys, json; sys.path.insert(0, 'tools'); import production_origins as p; "
        "before = set(sys.modules); p.require_source_origins(); record = p.loaded_origins(); "
        "print(json.dumps([sorted(set(sys.modules) - before), record]))"
    )
    environment = {name: value for name, value in os.environ.items() if name != "PYTHONPATH"}
    completed = subprocess.run(
        [sys.executable, "-c", program],
        cwd=WORKSPACE,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    imported, record = json.loads(completed.stdout)
    assert imported == []
    assert set(record.values()) == {origins.NOT_LOADED}


def test_stale_extensions_are_found_outside_the_compiled_distribution(tmp_path: Path) -> None:
    stale = tmp_path / "packages/parallax-core/src/parallax/core/entity" / f"_row_fill{ABI}"
    shipped = tmp_path / "packages/parallax-postgres/src/parallax/postgres" / f"_loaders{ABI}"
    source = tmp_path / "packages/parallax-core/src/parallax/core/entity/_row_fill.py"
    for path in (stale, shipped, source):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    assert origins.stale_extensions(tmp_path) == (stale.relative_to(tmp_path),)


def _refuse_measuring(*_args: object, **_kwargs: object) -> object:
    pytest.fail("a measurement ran in a process holding a foreign production module")


def _snapshot_reading() -> int:
    contract = BudgetContract.load()
    return snapshot_delivery_reading.main(
        [
            "--workload",
            "read-depth-4",
            "--cell",
            "document.peakKiB",
            "--roots",
            "1",
            "--warmups",
            str(contract.timing_warmups),
            "--measured",
            str(contract.timing_measured),
        ]
    )


_CHILDREN: Final = [
    (snapshot_delivery_reading, "_geometry", _snapshot_reading),
    (
        write_lowering_reading,
        "measure",
        lambda: write_lowering_reading.main(
            [write_lowering_reading.CASE_NAMES[0], "--warmups", "0", "--measured", "1"]
        ),
    ),
    (
        feature_boundary_reading,
        "measure",
        lambda: feature_boundary_reading.main(
            [feature_boundary_reading.CASE_NAMES[0], "--warmups", "0", "--measured", "1"]
        ),
    ),
    (
        instance_state_reading,
        "measure",
        lambda: instance_state_reading.main([instance_state_reading.SCENARIOS[0].name]),
    ),
    (
        time_interval_runtime,
        "reading_document",
        lambda: time_interval_runtime.main(
            ["read", time_interval_runtime.support.CELLS[0].id, "--warmups", "0", "--measured", "1"]
        ),
    ),
]


@pytest.mark.parametrize(
    ("module", "measuring", "entry"),
    [*_CHILDREN, (lifecycle_overhead, "_shape", lambda: lifecycle_overhead.main([]))],
)
def test_a_measurement_child_refuses_foreign_production_code_before_measuring(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, measuring: str, entry: Callable[[], int]
) -> None:
    monkeypatch.setattr(module, measuring, _refuse_measuring)
    monkeypatch.setitem(
        sys.modules, "parallax.stale", _module("parallax.stale", "/elsewhere/parallax/stale.py")
    )
    with pytest.raises(RuntimeError, match="did not load the checkout's production sources"):
        entry()


_MEASURED: Final[dict[str, object]] = {
    "_geometry": (1.0, "KiB", [1.0]),
    "measure": {},
    "reading_document": {},
}


@pytest.mark.parametrize(("module", "measuring", "entry"), _CHILDREN)
def test_a_measurement_child_refuses_foreign_production_code_loaded_while_measuring(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, measuring: str, entry: Callable[[], int]
) -> None:
    def measuring_foreign(*_args: object, **_kwargs: object) -> object:
        monkeypatch.setitem(
            sys.modules, "parallax.stale", _module("parallax.stale", "/elsewhere/parallax/stale.py")
        )
        return _MEASURED[measuring]

    monkeypatch.setattr(module, measuring, measuring_foreign)
    with pytest.raises(RuntimeError, match="did not load the checkout's production sources"):
        entry()


@pytest.mark.parametrize(("module", "measuring", "entry"), [*_CHILDREN[:3], _CHILDREN[4]])
def test_a_measurement_child_reports_what_it_loaded_once_it_has_measured(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module: ModuleType,
    measuring: str,
    entry: Callable[[], int],
) -> None:
    def measured(*_args: object, **_kwargs: object) -> object:
        return _MEASURED[measuring]

    monkeypatch.setattr(module, measuring, measured)
    assert entry() == 0
    line = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert line[origins.ORIGINS_FIELD] == origins.loaded_origins()
