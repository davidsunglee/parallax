"""What a capture's comparability depends on, as one boundary two reports share.

A capture is comparable with another only when both were taken by the same
instruments over the same workloads, so each report folds the source of its
instruments into the digest it records beside its workload digest. The
instruments are the report, its reading child, and every module of this
workspace's own ``tools`` and ``tests`` trees they import, transitively: an edit
to any of them can move a reading while already-committed evidence still looks
fresh.

Two kinds of source are outside the boundary, and both exclusions are what makes
it exact rather than merely wide. Production ``parallax`` packages are what two
captures are taken ACROSS — digesting them would make every production change a
recapture — and the conformance inputs that do define a measurement, the Budget
Contract and the workload catalog, are digested beside this one. A report's
diagnostic, argument-parsing, and output declarations decide what is printed
rather than what is read, so a report names its own and an edit to one reuses the
evidence it cannot have changed.

An instrument module imports by absolute name, which is what lets this resolve
the closure from source alone.
"""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path


def _imported(module: Path) -> Iterator[str]:
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise ValueError(f"{module.name}: an instrument imports by absolute name only")
            base = node.module or ""
            for alias in node.names:
                yield f"{base}.{alias.name}"
            yield base


def local_module(name: str, workspace: Path) -> Path | None:
    """The file a dotted module name resolves to inside ``workspace``, or absence
    for a name this workspace does not own."""
    parts = name.split(".")
    for base in (workspace, workspace / "tools"):
        module = base.joinpath(*parts).with_suffix(".py")
        if module.is_file():
            return module
        package = base.joinpath(*parts) / "__init__.py"
        if package.is_file():
            return package
    return None


def measurement_sources(roots: Sequence[Path], workspace: Path) -> tuple[Path, ...]:
    """``roots`` and every workspace-local module they import, transitively."""
    reached: set[Path] = set()
    pending = [root.resolve() for root in roots]
    while pending:
        module = pending.pop()
        if module in reached:
            continue
        reached.add(module)
        pending += [
            found.resolve()
            for name in _imported(module)
            if (found := local_module(name, workspace)) is not None
        ]
    return tuple(sorted(reached))


def measurement_source(path: Path, excluded: Sequence[str] = ()) -> bytes:
    """``path``'s source with the named top-level functions and classes removed.

    Every name has to be declared, so renaming one of them widens the boundary
    loudly rather than silently.
    """
    text = path.read_text(encoding="utf-8")
    names = set(excluded)
    if not names:
        return text.encode("utf-8")
    spans: list[range] = []
    for node in ast.parse(text).body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        if node.name in names:
            names.discard(node.name)
            first = min([node.lineno, *(item.lineno for item in node.decorator_list)])
            spans.append(range(first, (node.end_lineno or node.lineno) + 1))
    if names:
        raise ValueError(f"{path.name} declares no {', '.join(sorted(names))}")
    kept = [
        line
        for number, line in enumerate(text.splitlines(keepends=True), start=1)
        if not any(number in span for span in spans)
    ]
    return "".join(kept).encode("utf-8")


def digest(workloads: str, sources: Sequence[Path], excluded: Mapping[Path, Sequence[str]]) -> str:
    """The digest of the workloads a capture measured and of every instrument
    source that measured them, each without the declarations named for it."""
    digested = hashlib.sha256(workloads.encode("utf-8"))
    for source in sources:
        digested.update(measurement_source(source, excluded.get(source, ())))
        digested.update(b"\0")
    return digested.hexdigest()
