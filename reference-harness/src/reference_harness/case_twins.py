"""The corpus's twin-proof vocabulary, shared by every kind of twin.

A twin proof authors one logical behavior once per physical arm and asserts,
statically, that the arms differ only where the arm itself makes them differ.
Two kinds exist — the cross-layout descriptor/fixture/case triples and the
streamed batch-size case pairs — and each owns its own naming grammar, its own
subject, and its own notion of what an arm legitimately changes. What they share
is this module: how a case document is reduced to the behavior an arm may not
change, and how the corpus's catalog module prefix is read off a filename.

Keeping the reduction here is what makes a new physical observation a one-line
change: a `then` key that becomes an arm-specific golden is added once and every
twin gate stops comparing it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from reference_harness.corpus_yaml import read_corpus_yaml
from reference_harness.dep_graph_check import DepGraphFailure, parse_catalog

__all__ = [
    "TOP_LEVEL_PHYSICAL_KEYS",
    "PhysicalMember",
    "is_physical_case_member",
    "logical_case",
    "mapping_document",
    "module_and_body",
    "module_ids",
    "primary_module",
    "yaml_paths",
]

type PhysicalMember = Callable[[tuple[str, ...], str], bool]
"""Whether the member at ``(path, key)`` is a physical observation an arm owns."""

TOP_LEVEL_PHYSICAL_KEYS = frozenset({"statements", "referenceSql", "tableState", "execution"})
_STEP_STATEMENT_PATHS = frozenset(
    {
        ("when", "scenario", "[]"),
        ("when", "coherence", "[]"),
        ("when", "attempts", "[]"),
        ("when", "concurrency", "rounds", "[]", "A"),
        ("when", "concurrency", "rounds", "[]", "B"),
    }
)


def yaml_paths(directory: Path) -> list[Path]:
    return sorted({*directory.glob("*.yaml"), *directory.glob("*.yml")})


def mapping_document(path: Path, kind: str, errors: list[str]) -> dict[str, Any] | None:
    """Read one corpus document, recording rather than raising a parse failure."""
    try:
        document = read_corpus_yaml(path)
    except Exception as exc:
        errors.append(f"{path.name}: cannot parse {kind}: {exc}")
        return None
    if not isinstance(document, dict):
        errors.append(f"{path.name}: {kind} is not a mapping")
        return None
    return document


def module_ids(compatibility_root: Path, errors: list[str]) -> frozenset[str]:
    """The canonical module catalog, or an empty set with the reason recorded."""
    modules_path = compatibility_root.parent / "spec" / "modules.md"
    try:
        markdown = modules_path.read_text(encoding="utf-8")
        return frozenset(parse_catalog(markdown))
    except (OSError, DepGraphFailure) as exc:
        errors.append(f"cannot read the canonical module catalog {modules_path}: {exc}")
        return frozenset()


def module_and_body(prefix: str, modules: frozenset[str]) -> tuple[str, str] | None:
    """Split a case-name *prefix* into its catalog module and everything after it.

    The module is resolved against the catalog longest-first, before the
    three-digit sequence is separated, so a proof slug containing numeric
    segments cannot be mistaken for the sequence.
    """
    for module in sorted(modules, key=len, reverse=True):
        module_prefix = f"{module}-"
        if not prefix.startswith(module_prefix):
            continue
        body = prefix.removeprefix(module_prefix)
        if len(body) > 4 and body[:3].isdigit() and body[3] == "-":
            return module, body[4:]
    return None


def primary_module(document: Mapping[str, Any], is_module_tag: Callable[[str], bool]) -> str | None:
    """The first module tag — the module the case chiefly proves."""
    tags = document.get("tags")
    if not isinstance(tags, list):
        return None
    return next((tag for tag in tags if isinstance(tag, str) and is_module_tag(tag)), None)


def is_physical_case_member(path: tuple[str, ...], key: str) -> bool:
    """Whether the member at ``(path, key)`` is a physical observation or routing.

    Physical observations are every authored SQL group, the naive oracle, the
    resulting table state, and the execution provenance — each graded
    independently in its own arm's file. ``tags`` is excluded for a different
    reason: it routes rather than describes behavior, and two arms legitimately
    carry different routing tags.
    """
    if not path:
        return key == "tags"
    if path == ("given",):
        return key == "apply"
    if path == ("then",):
        return key in TOP_LEVEL_PHYSICAL_KEYS
    if path == ("when", "scenario", "[]"):
        return key in {"statements", "referenceSql"}
    return key == "statements" and path in _STEP_STATEMENT_PATHS


def logical_case(
    value: Any,
    *,
    physical: PhysicalMember = is_physical_case_member,
    rewrite: Callable[[Any], Any] | None = None,
    path: tuple[str, ...] = (),
) -> Any:
    """One case document reduced to the behavior every arm of its twin shares.

    *physical* decides which members an arm owns and this drops; *rewrite*
    normalizes the top-level ``model`` reference where the arms name different
    descriptor files, and is absent where they name the same one.
    """
    if isinstance(value, list):
        return [
            logical_case(item, physical=physical, rewrite=rewrite, path=(*path, "[]"))
            for item in value  # pyright: ignore[reportUnknownVariableType]
        ]
    if not isinstance(value, Mapping):
        return value
    normalized: dict[str, Any] = {}
    for key, item in value.items():  # pyright: ignore[reportUnknownVariableType]
        if physical(path, key):
            continue
        normalized[key] = (
            rewrite(item)
            if rewrite is not None and not path and key == "model"
            else logical_case(item, physical=physical, rewrite=rewrite, path=(*path, key))
        )
    return normalized
