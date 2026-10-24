"""Fail when an architecture page names an implementation symbol that is not
where the page says it is.

An architecture page refers to each implementation symbol it shows through a
deliberate reference: an inline code span holding
``parallax.<module>:<QualifiedName>``, such as
``parallax.core.read_delivery._read_plan:ReadPlanCache``. Only a code span that
begins ``parallax.`` and holds a ``:`` is a reference; every other code span is
prose, and fenced blocks are never read, so a diagram uses short names and lists
their references beneath it.

A reference resolves by parsing the named module's source, never by importing
it. The module path resolves through the workspace members' source roots. The
first name must be bound at the module's top level — a class, a function, an
assignment or type alias, annotated or under ``if TYPE_CHECKING:`` alike, or an
import alias — and each further name must be a member declared in the body of
the class before it: a method, a property, or a class attribute. Nothing is
inherited and no import is followed, so a same-named definition in another
module never satisfies a reference. Name resolution proves only that a symbol
exists where the page says; review owns whether a diagram's arrows, ownership
and stage guarantees are right.

Usage
-----
* ``python tools/check_architecture_references.py``                check every page
* ``python tools/check_architecture_references.py --check``        check (explicit)
* ``python tools/check_architecture_references.py PAGE [PAGE ...]`` check these pages

Same ``--check``/exit-1 contract as ``tools/check_native_sources.py``.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from python_workspace import NAMESPACE, Workspace, load_workspace

_TOOL = "tools/check_architecture_references.py"
_HERE = Path(__file__).resolve()
PY_ROOT = _HERE.parents[1]
REPO_ROOT = PY_ROOT.parents[1]

PAGES = PY_ROOT / "docs" / "architecture"
"""The directory whose Markdown pages, at any depth, the check reads by default."""

_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
_REFERENCE = re.compile(rf"{NAMESPACE}(?:\.{_IDENTIFIER})+:{_IDENTIFIER}(?:\.{_IDENTIFIER})*")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")

type _Binding = ast.stmt | ast.alias


@dataclass(frozen=True, slots=True)
class Reference:
    """One deliberate reference token and where it was written."""

    page: Path
    line: int
    token: str


@dataclass(frozen=True, slots=True)
class Finding:
    page: Path
    line: int
    message: str

    def render(self, root: Path) -> str:
        where = self.page.relative_to(root) if self.page.is_relative_to(root) else self.page
        return f"{where.as_posix()}:{self.line}: {self.message}"


def references(page: Path) -> Iterator[Reference]:
    """Every deliberate reference ``page`` writes outside its fenced blocks."""
    fence: str | None = None
    for number, line in enumerate(page.read_text(encoding="utf-8").splitlines(), start=1):
        opening = _FENCE.match(line)
        if fence is None:
            if opening is not None:
                fence = opening.group(1)
                continue
        else:
            if opening is not None and _closes(opening.group(1), fence, line):
                fence = None
            continue
        for span in _CODE_SPAN.finditer(line):
            content = span.group(2).strip()
            if content.startswith(f"{NAMESPACE}.") and ":" in content:
                yield Reference(page, number, content)


def _closes(marker: str, fence: str, line: str) -> bool:
    return (
        marker[0] == fence[0]
        and len(marker) >= len(fence)
        and not line.strip().removeprefix(marker).strip()
    )


@dataclass(slots=True)
class Resolver:
    """Resolves references against one workspace, parsing each module once."""

    workspace: Workspace
    _trees: dict[str, ast.Module | None] = field(default_factory=dict[str, ast.Module | None])

    def problem(self, token: str) -> str | None:
        """Why ``token`` does not resolve, or ``None`` where it does."""
        if _REFERENCE.fullmatch(token) is None:
            return f"malformed reference `{token}`: expected `{NAMESPACE}.<module>:<QualifiedName>`"
        module, _, qualified = token.partition(":")
        tree = self._tree(module)
        if tree is None:
            return f"`{token}`: no workspace module {module}"
        return _member_problem(token, module, tree.body, qualified.split("."))

    def _tree(self, module: str) -> ast.Module | None:
        if module not in self._trees:
            source = module_source(self.workspace, module)
            self._trees[module] = (
                None
                if source is None
                else ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            )
        return self._trees[module]


def module_source(workspace: Workspace, module: str) -> Path | None:
    """The source file defining ``module`` under its member's ``src`` root."""
    member = workspace.owner(module)
    if member is None:
        return None
    base = member.directory / "src" / Path(*module.split("."))
    for candidate in (base.parent / f"{base.name}.py", base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _member_problem(
    token: str, module: str, body: Sequence[ast.stmt], parts: Sequence[str]
) -> str | None:
    bindings = _bindings(body)
    for depth, part in enumerate(parts):
        binding = bindings.get(part)
        if binding is None:
            if depth == 0:
                return f"`{token}`: {module} binds no top-level {part}"
            owner = ".".join(parts[:depth])
            return f"`{token}`: class {owner} in {module} declares no member {part}"
        if depth + 1 < len(parts):
            members = _members(token, module, ".".join(parts[: depth + 1]), binding)
            if isinstance(members, str):
                return members
            bindings = members
    return None


def _members(token: str, module: str, named: str, binding: _Binding) -> dict[str, _Binding] | str:
    """The members ``binding`` declares, or why a qualified name cannot reach any."""
    if isinstance(binding, ast.alias):
        return (
            f"`{token}`: {named} is an import alias in {module}; "
            "name its members at the module that defines it"
        )
    if not isinstance(binding, ast.ClassDef):
        return f"`{token}`: {named} in {module} is not a class, so it declares no members"
    return _bindings(binding.body)


def _bindings(body: Sequence[ast.stmt]) -> dict[str, _Binding]:
    """The names ``body`` binds, descending into conditional and ``try`` blocks.

    A definition outranks an import alias of the same name, so a name imported
    for type checking and also defined resolves as the definition.
    """
    found: dict[str, _Binding] = {}
    for statement in body:
        for name, binding in _statement_bindings(statement):
            current = found.get(name)
            if current is None or (
                isinstance(current, ast.alias) and not isinstance(binding, ast.alias)
            ):
                found[name] = binding
    return found


def _statement_bindings(statement: ast.stmt) -> Iterator[tuple[str, _Binding]]:
    match statement:
        case ast.ClassDef(name=name) | ast.FunctionDef(name=name) | ast.AsyncFunctionDef(name=name):
            yield name, statement
        case ast.TypeAlias(name=ast.Name(id=name)) | ast.AnnAssign(target=ast.Name(id=name)):
            yield name, statement
        case ast.Assign(targets=targets):
            for target in targets:
                for name in _target_names(target):
                    yield name, statement
        case ast.Import() | ast.ImportFrom():
            yield from _import_bindings(statement)
        case _:
            for block in _nested_blocks(statement):
                for nested in block:
                    yield from _statement_bindings(nested)


def _import_bindings(statement: ast.Import | ast.ImportFrom) -> Iterator[tuple[str, _Binding]]:
    for alias in statement.names:
        if isinstance(statement, ast.Import):
            yield alias.asname or alias.name.partition(".")[0], alias
        elif alias.name != "*":
            yield alias.asname or alias.name, alias


def _nested_blocks(statement: ast.stmt) -> Iterator[Sequence[ast.stmt]]:
    if isinstance(statement, ast.If):
        yield statement.body
        yield statement.orelse
    elif isinstance(statement, ast.Try | ast.TryStar):
        yield statement.body
        for handler in statement.handlers:
            yield handler.body
        yield statement.orelse
        yield statement.finalbody


def _target_names(target: ast.expr) -> Iterator[str]:
    match target:
        case ast.Name(id=name):
            yield name
        case ast.Tuple(elts=elements) | ast.List(elts=elements):
            for element in elements:
                yield from _target_names(element)
        case ast.Starred(value=value):
            yield from _target_names(value)
        case _:
            pass


def check(pages: Sequence[Path], workspace: Workspace) -> tuple[int, list[Finding]]:
    """How many references ``pages`` write, and every one that does not resolve."""
    resolver = Resolver(workspace)
    count = 0
    findings: list[Finding] = []
    for page in pages:
        for reference in references(page):
            count += 1
            problem = resolver.problem(reference.token)
            if problem is not None:
                findings.append(Finding(page, reference.line, problem))
    return count, findings


def default_pages() -> list[Path]:
    return sorted(PAGES.rglob("*.md"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify every reference resolves (default)",
    )
    parser.add_argument("pages", nargs="*", type=Path, help="pages to check instead of all")
    arguments = parser.parse_args(argv)

    pages: list[Path] = [page.resolve() for page in arguments.pages] or default_pages()
    if not pages:
        print(
            f"{_TOOL}: no architecture pages under {PAGES.relative_to(REPO_ROOT)}",
            file=sys.stderr,
        )
        return 1
    count, findings = check(pages, load_workspace(PY_ROOT))
    if not findings:
        print(f"{_TOOL}: {count} references in {len(pages)} pages resolve")
        return 0
    for finding in findings:
        print(f"{_TOOL}: {finding.render(REPO_ROOT)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
