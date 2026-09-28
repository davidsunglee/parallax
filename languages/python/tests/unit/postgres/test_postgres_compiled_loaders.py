"""Which compiled loaders the adapter runs, and what it refuses to run."""

from __future__ import annotations

import sys
from types import ModuleType

import psycopg
import pytest
from psycopg import _cmodule

from parallax.postgres._compiled_loaders import compiled_loaders

_ACTIVE = psycopg.pq.__impl__
_DRIVER_LOADER: type = _cmodule._psycopg.CLoader  # pyright: ignore[reportPrivateUsage] - the base psycopg's Transformer dispatches through


def _variant_module(implementation: str) -> str:
    return f"parallax.postgres._cloaders_{implementation}"


def test_the_active_implementation_gets_loaders_psycopg_calls_directly() -> None:
    loaders = compiled_loaders(_ACTIVE)

    assert loaders.float4.__module__ == _variant_module(_ACTIVE)
    assert issubclass(loaders.float4, _DRIVER_LOADER)
    assert issubclass(loaders.timestamptz, _DRIVER_LOADER)


@pytest.mark.parametrize("implementation", ["python", "unknown"])
def test_an_implementation_without_compiled_loaders_is_refused(implementation: str) -> None:
    with pytest.raises(ImportError) as refused:
        compiled_loaders(implementation)

    message = str(refused.value)
    assert f"running its {implementation!r} implementation" in message
    assert "install psycopg[binary] or psycopg[c]" in message
    assert "PSYCOPG_IMPL" in message


@pytest.mark.parametrize("implementation", ["binary", "c"])
def test_a_variant_that_cannot_be_loaded_is_refused_with_its_cause(
    monkeypatch: pytest.MonkeyPatch, implementation: str
) -> None:
    # A `None` entry is how the import system spells a module that cannot load.
    monkeypatch.setitem(sys.modules, _variant_module(implementation), None)
    monkeypatch.delattr(
        sys.modules["parallax.postgres"], f"_cloaders_{implementation}", raising=False
    )

    with pytest.raises(ImportError) as refused:
        compiled_loaders(implementation)

    assert f"compiled loaders for psycopg's {implementation!r} implementation" in str(refused.value)
    assert "reinstall parallax-postgres" in str(refused.value)
    assert isinstance(refused.value.__cause__, ImportError)


class _PythonLoader:
    pass


# A subclass of the driver's base whose instances carry one more field, as a
# variant compiled over a base declared smaller than it now is would.
_WiderLoader = type("_WiderLoader", (_DRIVER_LOADER,), {"__slots__": ("field",)})


@pytest.mark.parametrize(
    ("float4", "timestamptz"),
    [(_PythonLoader, _PythonLoader), (_WiderLoader, _WiderLoader)],
    ids=["outside-the-driver-base", "over-a-differently-sized-base"],
)
def test_a_variant_that_does_not_match_the_driver_loader_layout_is_refused(
    monkeypatch: pytest.MonkeyPatch, float4: type, timestamptz: type
) -> None:
    variant = ModuleType(_variant_module(_ACTIVE))
    variant.ExactFloat4Loader = float4  # pyright: ignore[reportAttributeAccessIssue] - a stand-in for the compiled module
    variant.InfinityTimestamptzLoader = timestamptz  # pyright: ignore[reportAttributeAccessIssue] - a stand-in for the compiled module
    monkeypatch.setitem(sys.modules, variant.__name__, variant)
    monkeypatch.setattr(
        sys.modules["parallax.postgres"], f"_cloaders_{_ACTIVE}", variant, raising=False
    )

    with pytest.raises(ImportError, match="do not match the C loader layout"):
        compiled_loaders(_ACTIVE)
