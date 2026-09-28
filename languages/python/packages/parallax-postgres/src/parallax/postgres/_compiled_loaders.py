from __future__ import annotations

from typing import NamedTuple

import psycopg
from psycopg import _cmodule
from psycopg.abc import Loader

__all__ = ["CompiledLoaders", "compiled_loaders"]


class CompiledLoaders(NamedTuple):
    """The text loaders the adapter registers on every connection."""

    float4: type[Loader]
    timestamptz: type[Loader]


def compiled_loaders(implementation: str) -> CompiledLoaders:
    """The compiled loaders built for psycopg's ``implementation``, or an ``ImportError``.

    psycopg's C Transformer calls a loader's decoding directly only when the
    loader extends the C loader base of the build it runs, and calls anything
    else through Python per cell. The loaders are compiled once against each
    build, so the variant is chosen by the implementation psycopg selected, and
    only that variant is imported: the other build need not be installed.

    Nothing slower stands in for a refusal. The pure-Python implementation, a
    variant that cannot be loaded, and a variant that does not extend the base
    it was compiled against as that base is actually laid out are all refused,
    since each would decode correctly at a cost nobody asked for, or not at all.
    """
    if implementation not in ("binary", "c"):
        raise ImportError(
            f"psycopg is running its {implementation!r} implementation, which decodes every "
            f"cell through Python; parallax-postgres decodes with compiled loaders that only "
            f"psycopg's 'binary' or 'c' implementation can run, so install psycopg[binary] or "
            f"psycopg[c] and leave PSYCOPG_IMPL unset or naming one of them"
        )
    try:
        loaders = _variant(implementation)
    except Exception as exc:
        raise ImportError(
            f"parallax-postgres could not load its compiled loaders for psycopg's "
            f"{implementation!r} implementation; reinstall parallax-postgres for this "
            f"interpreter and platform"
        ) from exc
    base: type = _cmodule._psycopg.CLoader  # pyright: ignore[reportPrivateUsage] - the base the Transformer checks loaders against
    # The Float32 loader adds no field of its own, so its size is the base's
    # size as it was declared when the variant was compiled.
    if not all(issubclass(loader, base) for loader in loaders) or (
        loaders.float4.__basicsize__ != base.__basicsize__
    ):
        raise ImportError(
            f"parallax-postgres's compiled loaders for psycopg's {implementation!r} "
            f"implementation do not match the C loader layout of the installed psycopg "
            f"{psycopg.__version__}; install the psycopg release parallax-postgres declares"
        )
    return loaders


def _variant(implementation: str) -> CompiledLoaders:
    if implementation == "binary":
        from parallax.postgres import _cloaders_binary as variant
    else:
        from parallax.postgres import _cloaders_c as variant
    return CompiledLoaders(variant.ExactFloat4Loader, variant.InfinityTimestamptzLoader)
