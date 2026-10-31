"""Whether a measurement process runs this checkout's own production sources.

A cost reading is evidence about the checkout that took it only if every
production module the measuring process loaded came from that checkout: a stale
compiled extension beside a source, an installed distribution ahead of the
workspace, or another checkout on the path would each measure something else
under this checkout's name.

The rule is stated over the modules a process has loaded, never over what it
might load. Every loaded ``parallax`` module belongs to this checkout's
``packages/*/src``: a package's search path and a module's origin both lie
under one of them. Outside ``parallax.postgres``, whose row loaders are
compiled extensions, every module is a ``.py`` source its source loader read;
inside it, a module is that or an extension built for this interpreter's ABI.

:func:`require_source_origins` reads only ``sys.modules``, so a measurement
process asserts it before its first window and after its last without loading
anything its reading would not. :func:`resolved_origins` resolves the
read-construction inventory, importing those modules' parent packages, and is
therefore for the unmeasured identity probe alone; :func:`loaded_origins`
answers the same record without importing anything.

Never imported by production code.
"""

from __future__ import annotations

import importlib.machinery
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Final

WORKSPACE: Final = Path(__file__).resolve().parents[1]
ROOT_PACKAGE: Final = "parallax"
COMPILED_PACKAGE: Final = "parallax.postgres"
COMPILED_DISTRIBUTION: Final = "parallax-postgres"
NOT_LOADED: Final = "not-loaded"

MEASURED_MODULES: Final = (
    "parallax.core.read_delivery._row_recording",
    "parallax.core.read_delivery._page._rows",
    "parallax.core.read_delivery._convert",
    "parallax.core.document_codec._document",
    "parallax.core.entity._row_fill",
    "parallax.snapshot._publication._root",
    "parallax.snapshot._publication._wire_render",
)
"""The read-construction modules whose origins a runtime's identity records,
each relative to the checkout, or :data:`NOT_LOADED` where a process that
imports nothing on their account never loaded them."""


def source_roots(workspace: Path = WORKSPACE) -> tuple[Path, ...]:
    """Every distribution's source root in ``workspace``, resolved."""
    return tuple(sorted(path.resolve() for path in (workspace / "packages").glob("*/src")))


def _within(location: str, roots: Iterable[Path]) -> bool:
    resolved = Path(location).resolve()
    return any(resolved.is_relative_to(root) for root in roots)


def _origin_finding(
    name: str, origin: str | None, loader: object, roots: tuple[Path, ...]
) -> str | None:
    """Why the module ``name`` loaded from ``origin`` by ``loader`` is not this
    checkout's production code, or nothing when it is."""
    if origin is None:
        return f"{name} has no origin"
    if not _within(origin, roots):
        return f"{name} was loaded from {origin}, outside the checkout's package sources"
    if isinstance(loader, importlib.machinery.SourceFileLoader) and origin.endswith(".py"):
        return None
    compiled = name == COMPILED_PACKAGE or name.startswith(f"{COMPILED_PACKAGE}.")
    if (
        compiled
        and isinstance(loader, importlib.machinery.ExtensionFileLoader)
        and origin.endswith(importlib.machinery.EXTENSION_SUFFIXES[0])
    ):
        return None
    if compiled:
        return f"{name} was loaded from {origin}, neither a source nor this interpreter's extension"
    return f"{name} was loaded from {origin}, which is not a .py source"


def origin_findings(
    modules: Mapping[str, object] | None = None, workspace: Path = WORKSPACE
) -> list[str]:
    """Every way the loaded ``parallax`` modules among ``modules``, this
    process's own unless named, break the rule this module states."""
    loaded = dict(sys.modules if modules is None else modules)
    roots = source_roots(workspace)
    findings: list[str] = []
    for name, module in sorted(loaded.items()):
        if name != ROOT_PACKAGE and not name.startswith(f"{ROOT_PACKAGE}."):
            continue
        findings += [
            f"{name} searches {entry}, outside the checkout's package sources"
            for entry in getattr(module, "__path__", None) or ()
            if not _within(str(entry), roots)
        ]
        spec = getattr(module, "__spec__", None)
        origin = getattr(spec, "origin", None)
        if origin is None and hasattr(module, "__path__"):
            continue  # a namespace package: its search path, checked above, is all it has
        finding = _origin_finding(name, origin, getattr(spec, "loader", None), roots)
        if finding is not None:
            findings.append(finding)
    return findings


def require_source_origins() -> None:
    """Refuse a process any of whose loaded ``parallax`` modules is not this
    checkout's production code, naming every one."""
    findings = origin_findings()
    if findings:
        raise RuntimeError(
            "this process did not load the checkout's production sources:\n- "
            + "\n- ".join(findings)
        )


def _relative(origin: str, workspace: Path) -> str:
    return Path(origin).resolve().relative_to(workspace.resolve()).as_posix()


def loaded_origins(
    modules: Mapping[str, object] | None = None, workspace: Path = WORKSPACE
) -> dict[str, str]:
    """Each of :data:`MEASURED_MODULES` this process, or ``modules``, has
    loaded, by its checkout-relative origin, and every other as
    :data:`NOT_LOADED`; refused as :func:`require_source_origins` refuses."""
    loaded = dict(sys.modules if modules is None else modules)
    findings = origin_findings(loaded, workspace)
    if findings:
        raise RuntimeError("; ".join(findings))
    record: dict[str, str] = {}
    for name in MEASURED_MODULES:
        origin = getattr(getattr(loaded.get(name), "__spec__", None), "origin", None)
        record[name] = NOT_LOADED if origin is None else _relative(str(origin), workspace)
    return record


def resolved_origins(workspace: Path = WORKSPACE) -> dict[str, str]:
    """Each of :data:`MEASURED_MODULES` by the checkout-relative origin this
    interpreter resolves it to, importing its parent packages but not itself,
    once every module that leaves loaded is this checkout's; ``RuntimeError``
    names every module that is not."""
    import importlib.util

    roots = source_roots(workspace)
    record: dict[str, str] = {}
    findings: list[str] = []
    for name in MEASURED_MODULES:
        spec = importlib.util.find_spec(name)
        if spec is None:
            findings.append(f"{name} does not resolve")
            continue
        finding = _origin_finding(name, spec.origin, spec.loader, roots)
        if finding is not None:
            findings.append(finding)
            continue
        record[name] = _relative(str(spec.origin), workspace)
    findings += origin_findings(workspace=workspace)
    if findings:
        raise RuntimeError("; ".join(findings))
    return record


def stale_extensions(workspace: Path = WORKSPACE) -> tuple[Path, ...]:
    """Every compiled extension under a source root that ships none, relative
    to ``workspace``: one would be imported ahead of the source beside it."""
    suffixes = tuple(importlib.machinery.EXTENSION_SUFFIXES)
    return tuple(
        path.relative_to(workspace)
        for root in sorted((workspace / "packages").glob("*/src"))
        if root.parent.name != COMPILED_DISTRIBUTION
        for path in sorted(root.rglob("*"))
        if path.name.endswith(suffixes)
    )
