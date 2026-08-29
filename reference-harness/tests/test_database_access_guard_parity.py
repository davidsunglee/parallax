"""Pin the repository's two database-access guards to one analyzer.

`core/spec/language-testing.md` §5 requires the resource that defines a
scheduling class to be reachable only through designated entry points, and makes
that restriction a blocking check. Every scope declaring a `db` class owns one:
`reference_harness.check_database_access` for the harness test tree, and
`languages/python/tools/check_database_access.py` for the Python one. Two trees,
two gates, one rule — so both carry the same analyzer over Python source.

They carry it as copies rather than as an import. `languages/AGENTS.md` binds
every path under `languages/`, and it forbids a language implementation
inspecting reference-harness internals or taking them as design input; a shared
module would make the Python gate do exactly that. What copies leave exposed is
divergence: a resolution bug fixed in one and not the other lets one gate accept
access the other rejects, and both gates stay green while it does.

This module closes that without merging them. It is the only direction available
— gate tooling here already reads the language scopes' own files, and nothing
under `languages/` reads anything here. Comparison is over each definition's
abstract syntax with docstrings removed, because what a scope's own tree makes
true of the rule is its to explain, while what the rule computes is not its to
choose.

The two guards' test suites are deliberately *not* compared. Each proves its own
scope's seams and entry points, and anything either proves about the analyzer
holds of both copies of it once the definitions below are pinned identical.
"""

from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

_GUARDS = {
    "harness": _REPO_ROOT / "reference-harness/src/reference_harness/check_database_access.py",
    "python": _REPO_ROOT / "languages/python/tools/check_database_access.py",
}

_SHARED_ANALYSER = (
    "Finding",
    "_acquisition_named",
    "_bound_names",
    "_declared_database_fixtures",
    "_entry_point_span",
    "_imported_names",
    "_local_aliases",
    "_pattern_names",
    "_resolved_target",
    "_resolves_to_callable",
    "_value_bindings",
    "seam_calls",
    "unresolved_seams",
)
"""Every definition deciding what the rule computes: the finding it reports, the
import bindings, binding forms, local aliases, and call targets it resolves a
violation from, the fixture declarations it reads out of a classifier, and the seam
resolution that keeps it from matching nothing."""

_SCOPE_OWNED = {
    "audit": (
        "the harness declares its entry-point fixture and its classifier in two "
        "modules and the Python tree declares both in one, so the two audits walk "
        "a different number of files"
    ),
    "main": (
        "each scope follows its own established argument and output conventions, "
        "which its siblings rather than its twin fix"
    ),
}
"""Definitions the two guards share by name and, for the reason recorded against
each, not by body."""

_Definition = ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef


def _definitions(path: Path) -> dict[str, _Definition]:
    return {
        node.name: node
        for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef)
    }


_DEFINED = {scope: _definitions(path) for scope, path in _GUARDS.items()}


def _computation(definition: _Definition) -> str:
    """*definition* rendered from its syntax alone, docstrings dropped at every
    level, so formatting and prose are outside the comparison."""
    stripped = copy.deepcopy(definition)
    for node in ast.walk(stripped):
        if not isinstance(node, ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef):
            continue
        opening = node.body[0]
        if isinstance(opening, ast.Expr) and isinstance(opening.value, ast.Constant):
            if isinstance(opening.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(stripped)


@pytest.mark.parametrize("name", _SHARED_ANALYSER)
def test_both_guards_decide_a_violation_the_same_way(name: str) -> None:
    absent = sorted(scope for scope, defined in _DEFINED.items() if name not in defined)
    assert not absent, (
        f"`{name}` is not defined in the {' and '.join(absent)} guard; the two guards "
        f"answer one rule and cannot answer it with different pieces"
    )

    rendered = {scope: _computation(_DEFINED[scope][name]) for scope in _GUARDS}

    assert rendered["harness"] == rendered["python"], (
        f"`{name}` differs between the two database-access guards. A rule corrected in one "
        f"tree and not the other lets one gate accept live access the other rejects, with "
        f"both reporting success."
    )


def test_every_definition_the_guards_share_is_accounted_for() -> None:
    shared = set(_DEFINED["harness"]) & set(_DEFINED["python"])
    accounted = set(_SHARED_ANALYSER) | set(_SCOPE_OWNED)

    assert shared == accounted, (
        "the two guards share a definition this module neither pins nor exempts, or they "
        "have stopped sharing one it names. A definition present in both is either the same "
        "analyzer — pin it — or a difference a scope chose, which belongs in _SCOPE_OWNED "
        "with the reason it chose it."
    )
