"""Fail when a Cython source escapes its package or its declared coverage exemption.

Two gates cannot read a Cython source, and each is sound only while every such
source sits where this check puts it.

* **Imports.** import-linter parses Python, so an import a ``.pyx`` makes is
  graded by no contract. The compiled loaders are the adapter's own, inside the
  ``parallax.postgres`` scope; confining every Cython source to that package
  keeps the imports no contract sees inside the one scope whose manifest already
  grants what they reach.
* **Changed-line coverage.** coverage.py cannot trace a compiled module, so
  ``diff-cover`` scores no line of a Cython source and skips the file without a
  word. Differential tests grade those sources instead, and the skip is made a
  decision rather than an accident: ``[tool.diff_cover] exclude`` in
  ``pyproject.toml`` names each one, and this check requires the list to name
  exactly the Cython sources that exist.

Every Cython source in the repository counts, tracked or not — an untracked one
is still compiled, still imported, and still skipped. Ignored files do not: the
installed Cython distribution ships declaration files of its own.

Usage
-----
* ``python tools/check_native_sources.py``          check (default)
* ``python tools/check_native_sources.py --check``  check (explicit)

Same ``--check``/exit-1 contract as ``tools/check_untracked_sources.py``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

_TOOL = "tools/check_native_sources.py"
_HERE = Path(__file__).resolve()
PY_ROOT = _HERE.parents[1]

CONFINEMENT = "languages/python/packages/parallax-postgres/src/parallax/postgres"
"""The one directory, relative to the repository root, Cython sources may live in."""

SUFFIXES: tuple[str, ...] = (".pyx", ".pxd", ".pxi")


def cython_sources(root: Path) -> list[str]:
    """Every Cython source under the git checkout holding ``root``, repository-relative.

    Raises rather than returning empty when git is unavailable — a gate that
    cannot see the checkout must not report success.
    """
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "--full-name",
            "-z",
            "--",
            *(f":(top,glob)**/*{suffix}" for suffix in SUFFIXES),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"`git ls-files` failed in {root}: {result.stderr.strip()}")
    return sorted({line for line in result.stdout.split("\0") if line})


def outside_confinement(sources: Sequence[str]) -> list[str]:
    return [
        source
        for source in sources
        if not PurePosixPath(source).is_relative_to(PurePosixPath(CONFINEMENT))
    ]


def declared_exemptions(pyproject: Path) -> list[str]:
    """The ``[tool.diff_cover] exclude`` patterns, each read back as the path it names."""
    with pyproject.open("rb") as handle:
        configuration = tomllib.load(handle)
    patterns: list[str] = configuration.get("tool", {}).get("diff_cover", {}).get("exclude", [])
    return [pattern.removeprefix("*/") for pattern in patterns]


def exemption_differences(
    sources: Sequence[str], exemptions: Sequence[str]
) -> tuple[list[str], list[str]]:
    """Cython sources no exemption names, and exemptions naming no Cython source.

    Sources are repository-relative and exemptions are relative to the Python
    root, so each exemption is compared as the source path it would match.
    """
    named = {f"languages/python/{exemption}" for exemption in exemptions}
    return sorted(set(sources) - named), sorted(named - set(sources))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify every Cython source is confined and exempted by name (default)",
    )
    parser.parse_args(argv)

    sources = cython_sources(PY_ROOT)
    escaped = outside_confinement(sources)
    unexempted, stale = exemption_differences(
        sources, declared_exemptions(PY_ROOT / "pyproject.toml")
    )
    if not (escaped or unexempted or stale):
        print(f"{_TOOL}: {len(sources)} Cython sources, all confined and exempted by name")
        return 0

    for heading, paths in (
        (f"Cython sources outside {CONFINEMENT}:", escaped),
        ("Cython sources [tool.diff_cover] exclude does not name:", unexempted),
        ("[tool.diff_cover] exclude entries naming no Cython source:", stale),
    ):
        if paths:
            print(f"{_TOOL}: {heading}", file=sys.stderr)
            for path in paths:
                print(f"    {path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
