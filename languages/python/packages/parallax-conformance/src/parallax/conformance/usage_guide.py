from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

from parallax.conformance import api_suite, case_format

__all__ = ["GuideError", "expand", "generate", "main", "managed_paths", "snippet_sources"]

_SOURCE_ID = r"[a-z0-9][a-z0-9-]*"
_OPEN = re.compile(rf"<!-- example: (?P<source_id>{_SOURCE_ID}) -->")
_CLOSE = "<!-- /example -->"
_MARKER_LIKE = re.compile(r"\s*<!--\s*/?\s*example\b")


class GuideError(ValueError):
    """A managed file's example markers or the snippet sources they name are invalid."""


def snippet_sources(
    examples: Iterable[api_suite.Example] = api_suite.EXAMPLES,
    recipes: Iterable[api_suite.Recipe] = api_suite.RECIPES,
) -> dict[str, str]:
    """Every markable snippet by source ID: examples by corpus-case ID, recipes by recipe ID."""
    sources: dict[str, str] = {}
    keyed = [
        *((example.case_id, example.snippet) for example in examples),
        *((recipe.recipe_id, recipe.snippet) for recipe in recipes),
    ]
    for source_id, snippet in keyed:
        if not re.fullmatch(_SOURCE_ID, source_id):
            raise GuideError(f"snippet source ID cannot be named by a marker: {source_id!r}")
        if source_id in sources:
            raise GuideError(f"duplicate snippet source ID: {source_id}")
        sources[source_id] = snippet.rstrip("\n")
    return sources


def expand(text: str, sources: Mapping[str, str], *, origin: str) -> str:
    """Replace the body of every ``<!-- example: ID -->`` … ``<!-- /example -->`` block
    with the named snippet, preserving all text outside the blocks."""
    expanded: list[str] = []
    open_id: str | None = None
    open_line = 0
    newline = "\n"
    for number, line in enumerate(text.splitlines(keepends=True), start=1):
        content = line.rstrip("\r\n")
        if not _MARKER_LIKE.match(content):
            if open_id is None:
                expanded.append(line)
            continue
        if (opening := _OPEN.fullmatch(content)) is not None:
            if open_id is not None:
                raise GuideError(
                    f"{origin}:{number}: example marker nested in the block opened at line "
                    f"{open_line}"
                )
            open_id, open_line = opening["source_id"], number
            newline = line[len(content) :]
            if open_id not in sources:
                raise GuideError(f"{origin}:{number}: unknown snippet source ID: {open_id}")
            expanded.append(line)
        elif content == _CLOSE:
            if open_id is None:
                raise GuideError(f"{origin}:{number}: closing example marker without an opening")
            body = sources[open_id].replace("\n", newline)
            expanded.append(f"```python{newline}{body}{newline}```{newline}")
            expanded.append(line)
            open_id = None
        else:
            raise GuideError(f"{origin}:{number}: malformed example marker: {content}")
    if open_id is not None:
        raise GuideError(f"{origin}:{open_line}: example block is never closed")
    return "".join(expanded)


def managed_paths(root: Path) -> list[Path]:
    """The files whose example blocks the generator owns."""
    guide = root / "languages" / "python" / "docs" / "guide"
    return [root / "README.md", *sorted(guide.rglob("*.md"))]


def generate(root: Path) -> dict[Path, str]:
    """Each managed file's expanded text, keyed by path."""
    sources = snippet_sources()
    return {
        path: expand(
            path.read_text(encoding="utf-8", newline=""),
            sources,
            origin=str(path.relative_to(root)),
        )
        for path in managed_paths(root)
    }


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    """Console-script entry point for ``gen-usage-guide``."""
    parser = argparse.ArgumentParser(prog="gen-usage-guide")
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail on drift instead of rewriting example blocks",
    )
    args = parser.parse_args(argv)
    repo = root if root is not None else case_format.find_repo_root()

    try:
        rendered = generate(repo)
    except GuideError as error:
        print(f"gen-usage-guide: {error}", file=sys.stderr)
        return 1
    stale = [
        path
        for path, text in rendered.items()
        if path.read_text(encoding="utf-8", newline="") != text
    ]

    if args.check:
        for path in stale:
            print(
                f"gen-usage-guide: {path.relative_to(repo)} is out of date; "
                "run `uv run gen-usage-guide`.",
                file=sys.stderr,
            )
        if stale:
            return 1
        print(f"gen-usage-guide: {len(rendered)} files are up to date")
        return 0

    for path in stale:
        path.write_text(rendered[path], encoding="utf-8", newline="")
        print(f"gen-usage-guide: wrote {path.relative_to(repo)}")
    return 0
