"""Render the application API reference from the API snapshot and docstrings."""

from __future__ import annotations

import inspect
import json
from importlib import import_module
from pathlib import Path

from griffe import Alias, GriffeLoader

PY_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = PY_ROOT / "tests" / "api" / "public_api.json"
REFERENCE = PY_ROOT / "docs" / "api-reference.md"
SUMMARY_LIMIT = 100

_HEADER = """\
# API reference

Every name an application imports from Parallax, by module, with the first line of
its docstring. Anything not listed here is private or internal.
[What each error asks of you](guide/08-errors.md#what-each-error-asks-of-you) says
when to handle each error.

This page is generated from the [API snapshot](../tests/api/public_api.json) and the
docstrings. After changing an exported name or its docstring, run
`uv run python tools/api_reference.py`.
"""

_GROUPS = ("Functions", "Classes", "Errors", "Constants and types")


def _group(value: object) -> str:
    if inspect.isroutine(value):
        return "Functions"
    if isinstance(value, type):
        return "Errors" if issubclass(value, BaseException) else "Classes"
    return "Constants and types"


def _summary(docstring: str, path: str) -> str:
    summary = " ".join(docstring.split("\n\n", 1)[0].split())
    if not summary:
        raise ValueError(f"{path} needs a docstring")
    if len(summary) > SUMMARY_LIMIT:
        raise ValueError(f"{path}'s first paragraph is longer than {SUMMARY_LIMIT} characters")
    return summary


def render() -> str:
    """The reference page for every application module the snapshot records."""
    loader = GriffeLoader()
    loader.load("parallax")
    names: dict[str, list[str]] = json.loads(SNAPSHOT.read_text())
    sections = [_HEADER]
    for path in sorted(key for key in names if ":" not in key):
        module = loader.modules_collection.get_member(path)
        runtime = import_module(path)
        intro = _summary(module.docstring.value if module.docstring else "", path)
        groups: dict[str, list[str]] = {group: [] for group in _GROUPS}
        for name in names[path]:
            member = module.members[name]
            target = member.final_target if isinstance(member, Alias) else member
            docstring = target.docstring.value if target.docstring else ""
            summary = _summary(docstring, f"{path}.{name}")
            groups[_group(getattr(runtime, name))].append(f"- `{name}`: {summary}")
        sections.append(f"## `{path}`\n\n{intro}\n")
        sections.extend(
            f"### {group}\n\n" + "\n".join(items) + "\n" for group, items in groups.items() if items
        )
    return "\n".join(sections)


if __name__ == "__main__":
    REFERENCE.write_text(render())
    print(f"wrote {REFERENCE.relative_to(PY_ROOT)}")
