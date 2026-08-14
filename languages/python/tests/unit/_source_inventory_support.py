"""Source inventories over Python files, for guards stated over source shape.

Extraction and nothing more: globbing a distribution's sources, matching a
regular expression against their lines, parsing them with ``ast``, and reading
the import statements out of the parse. A caller gets paths, ``path:line`` sites,
parse trees, and `Import` records, and decides for itself what any of it means.
`synthetic_sources` hands it source to read in place of this tree's, which is how
a guard is shown to fail for the shape it forbids and to pass source that merely
resembles it. Two readers ask Python instead of the text — importing every module
and walking the subclass registry — because ancestry is a runtime fact that no
spelling settles.

Nothing here resolves a name to what it denotes. A relative import's source
module is completed from the importing file's own position, which the file system
settles outright; what a name MEANS is a claim behavior grades directly, and
approximating an interpreter to grade it here would be both weaker than that and
a second implementation to maintain.

Exported names carry no leading underscore: importing an underscored name across
modules is a `reportPrivateUsage` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

import ast
import importlib
import re
from collections.abc import Iterable, Iterator, Mapping
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
    "first_party_descendants",
    "hits",
    "import_every_module",
    "parsed",
    "production_sources",
    "site_of",
    "snapshot_imports",
    "sources",
    "synthetic_site",
    "synthetic_sources",
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


_SYNTHETIC_SRC = PACKAGES / "parallax-synthetic" / "src"


def _synthetic_path(module: str) -> Path:
    return _SYNTHETIC_SRC.joinpath(*module.split(".")).with_suffix(".py")


def synthetic_sources(modules: Mapping[str, str]) -> Iterator[tuple[Path, str]]:
    """Each module's text, at the path a distribution holding it would use.

    Nothing is written and nothing needs to exist: every reader here takes a path
    and its text, so naming the module is enough.
    """
    for module, text in modules.items():
        yield _synthetic_path(module), text


def synthetic_site(module: str, line: int) -> str:
    """One line of a `synthetic_sources` module, as a failure would name it."""
    return site_of(_synthetic_path(module), line)


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


def _descendants(root: type) -> Iterator[type]:
    yield root
    for child in root.__subclasses__():
        yield from _descendants(child)


def first_party_descendants(root: type) -> list[type]:
    """Every shipped class that is, or descends from, ``root``.

    Python's own subclass registry answers this once every module is imported, so
    no alias, qualified base spelling, or class name evades it — and a class
    merely named like ``root`` is not in it. A class a test defines is not shipped
    and is left out.
    """
    return sorted(
        (kind for kind in _descendants(root) if kind.__module__.startswith("parallax.")),
        key=lambda kind: (kind.__module__, kind.__qualname__),
    )


@dataclass(frozen=True, slots=True)
class Import:
    """One name one module imports, at the site the import statement stands.

    Both the module an import READS FROM and the name it BINDS are carried, since
    a guard stated over bound names alone admits `from pydantic import Field`.
    """

    site: str
    importer: str
    """The dotted module doing the importing."""
    source: str
    """The dotted module imported FROM, absolute however it was spelled; empty for
    a plain ``import x``."""
    name: str
    """The imported attribute, or the dotted module for a plain ``import x``."""
    local: str
    """The name the import binds in ``importer``."""

    @property
    def distribution(self) -> str:
        """The top-level package the import reads from, however it is spelled."""
        return (self.source or self.name).partition(".")[0]


def _absolute(importer: str, path: Path, level: int, module: str) -> str:
    """The module a ``from`` import reads from, with a relative spelling completed.

    ``level`` counts directories up from the importing file's own package, which
    is the file's parent module unless the file IS the package's ``__init__``.
    """
    if not level:
        return module
    package = importer if path.name == "__init__.py" else importer.rpartition(".")[0]
    parts = package.split(".")
    base = ".".join(parts[: len(parts) - (level - 1)])
    return f"{base}.{module}" if module else base


def _module_imports(path: Path, tree: ast.Module) -> Iterator[Import]:
    importer = _dotted(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            source = _absolute(importer, path, node.level, node.module or "")
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
