"""Source inventories over the tree's own Python files.

Extraction and nothing more: globbing a distribution's sources, matching a
regular expression against their lines, parsing them with ``ast``, and reading
the import statements out of the parse. A caller gets paths, ``path:line``
sites, parse trees, and `Import` records, and decides for itself what any of it
means. Shared by `test_frontend_contraction_guards.py` and
`test_source_enforcement_topology.py`, which assert about source shape for
different reasons and on different timescales but read the source the same way.

Name resolution is deliberately absent and is not coming back here. The scope
trees, reaching definitions, and denotation this module's predecessor carried
were deleted with the guards that read them: a claim about what a name MEANS,
rather than about how the source spells it, is a claim behavior can grade
directly, and grading it by approximating an interpreter is both weaker and a
second implementation to maintain.

Exported names carry no leading underscore: importing an underscored name across
modules is a `reportPrivateUsage` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

import ast
import importlib
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from _support.distributions import ALL_PACKAGES, PRODUCTION_PACKAGES, TOP_PACKAGE_DIR
from _support.repo import PY_ROOT

__all__ = [
    "CONFORMANCE_SRC",
    "CORE_SRC",
    "ENTITY_PACKAGE",
    "ENTITY_SRC",
    "PACKAGES",
    "SNAPSHOT_SRC",
    "Import",
    "all_sources",
    "declared_imports",
    "hits",
    "import_every_module",
    "parsed",
    "production_sources",
    "site_of",
    "snapshot_imports",
    "sources",
    "word",
]

PACKAGES = PY_ROOT / "packages"
CORE_SRC = PACKAGES / "parallax-core" / "src" / "parallax" / "core"
SNAPSHOT_SRC = PACKAGES / "parallax-snapshot" / "src" / "parallax" / "snapshot"
ENTITY_SRC = CORE_SRC / "entity"
CONFORMANCE_SRC = PACKAGES / "parallax-conformance" / "src" / "parallax" / "conformance"

ENTITY_PACKAGE = "parallax.core.entity"


def sources(*roots: Path) -> Iterator[tuple[Path, str]]:
    """Each source file under ``roots`` and its text; a file root is itself."""
    for root in roots:
        paths = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in paths:
            yield path, path.read_text(encoding="utf-8")


def _package_sources(names: Iterable[str]) -> Iterator[tuple[Path, str]]:
    yield from sources(*(PACKAGES / name / "src" / TOP_PACKAGE_DIR[name] for name in names))


def production_sources() -> Iterator[tuple[Path, str]]:
    """Every shipped distribution's sources; the conformance tooling is not one."""
    yield from _package_sources(PRODUCTION_PACKAGES)


def all_sources() -> Iterator[tuple[Path, str]]:
    """Every distribution's sources, the dev-only conformance tooling included."""
    yield from _package_sources(ALL_PACKAGES)


def site_of(path: Path, line: int) -> str:
    """One repository-relative ``path:line``, as a failure names it."""
    return f"{path.relative_to(PY_ROOT)}:{line}"


def _dotted(path: Path) -> str:
    """A source file's importable module name."""
    src = next(parent for parent in path.parents if parent.name == "src")
    return ".".join(path.relative_to(src).with_suffix("").parts).removesuffix(".__init__")


def hits(pattern: str, over: Iterator[tuple[Path, str]], *, flags: int = 0) -> list[str]:
    """Every ``path:line`` the regular expression ``pattern`` matches."""
    expression = re.compile(pattern, flags)
    return [
        site_of(path, number)
        for path, text in over
        for number, line in enumerate(text.splitlines(), 1)
        if expression.search(line)
    ]


def word(name: str) -> str:
    """``name`` as a whole-word pattern, so a longer identifier containing it misses."""
    return rf"\b{re.escape(name)}\b"


def parsed(over: Iterator[tuple[Path, str]]) -> Iterator[tuple[Path, ast.Module]]:
    """Each source file and its parse tree."""
    for path, text in over:
        yield path, ast.parse(text)


def import_every_module(over: Iterator[tuple[Path, str]]) -> None:
    """Import each source file, so a caller can ask Python rather than the text.

    Importing is what turns a spelling into an object, which is the only way to
    ask what descends from a class. A module that cannot be imported fails here
    as an error rather than a quiet absence.
    """
    for path, _text in over:
        importlib.import_module(_dotted(path))


# --------------------------------------------------------------------------- #
# Imports, modelled so that a caller can name the module an import READS from   #
# and not only the local name it binds. `from pydantic import Field` binds no  #
# name any inventory of forbidden spellings would list, and a guard stated     #
# over bound names alone therefore admits it.                                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Import:
    """One name one module imports, at the site the import statement stands."""

    site: str
    importer: str
    """The dotted module doing the importing."""
    source: str
    """The dotted module imported FROM; empty for a plain ``import x``."""
    name: str
    """The imported attribute, or the dotted module for a plain ``import x``."""
    local: str
    """The name the import binds in ``importer``."""

    @property
    def distribution(self) -> str:
        """The top-level package the import reads from, however it is spelled."""
        return (self.source or self.name).partition(".")[0]


def _module_imports(path: Path, tree: ast.Module) -> Iterator[Import]:
    importer = _dotted(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            source = "." * node.level + (node.module or "")
            for alias in node.names:
                yield Import(
                    site_of(path, node.lineno),
                    importer,
                    source,
                    alias.name,
                    alias.asname or alias.name,
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield Import(
                    site_of(path, node.lineno),
                    importer,
                    "",
                    alias.name,
                    alias.asname or alias.name.partition(".")[0],
                )


def declared_imports(over: Iterator[tuple[Path, str]]) -> Iterator[Import]:
    """Every import statement's names, across the given sources."""
    for path, tree in parsed(over):
        yield from _module_imports(path, tree)


def snapshot_imports() -> list[Import]:
    """Every import the Snapshot distribution declares."""
    return list(declared_imports(sources(SNAPSHOT_SRC)))
