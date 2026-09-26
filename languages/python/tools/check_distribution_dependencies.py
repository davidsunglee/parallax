"""Fail when a workspace distribution's sibling declarations differ from the
sibling packages its source imports.

The distributions share the PEP 420 ``parallax`` namespace, so an import of
``parallax.postgres`` names no distribution a generic analyzer can see. Each
member owns ``src/parallax/<scope>`` (``python_workspace``), which is what maps
an imported ``parallax.<scope>`` module to the sibling that must be installed
for it. Third-party requirements are not this check's concern.

The contract, per member:

* **Every static import counts.** An import under ``TYPE_CHECKING`` or inside a
  function body needs its sibling as much as a module-level one: every
  distribution ships ``py.typed``, so a consumer's type checker resolves the
  published annotations, and runtime introspection of them does too. Dynamic
  imports by string are not seen.
* **An extra gates the slice it names.** An extra ``<name>`` covers exactly the
  ``parallax.<scope>.<name>`` module or package. An import made only inside
  that slice is satisfied by the extra's requirements, and any import outside
  every slice by ``[project].dependencies`` alone. An extra whose name matches
  no such slice is a finding, because nothing could tell what it gates.
* **Declarations are exact.** A sibling imported outside every slice belongs in
  the base dependencies; one imported only inside a slice belongs in that
  slice's extra; anything else declared is unused, including a member
  declaring itself or a sibling the base declares again in an extra. A
  ``parallax-*`` requirement naming no member is a finding, as is an import of
  a ``parallax.<scope>`` no member owns.

Every structural finding from :func:`python_workspace.load_workspace` fails the
check too, so a member the model cannot place is never silently skipped.

Usage: ``uv run python tools/check_distribution_dependencies.py`` (from
``languages/python``); exits non-zero on any finding.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

from python_workspace import (
    NAMESPACE,
    Member,
    Workspace,
    imported_modules,
    load_workspace,
    module_name,
    normalize,
    python_files,
    requirement_name,
)

PY_ROOT = Path(__file__).resolve().parents[1]

_BASE = "[project].dependencies"
_SIBLING_PREFIX = f"{NAMESPACE}-"


def _extra_group(extra: str) -> str:
    return f"[project.optional-dependencies].{extra}"


def check(workspace: Workspace) -> list[str]:
    """Every finding for ``workspace``: its structural findings, then each
    member's declaration findings."""
    findings = list(workspace.findings)
    for member in workspace.members:
        findings += _member_findings(workspace, member)
    return findings


def _member_findings(workspace: Workspace, member: Member) -> list[str]:
    findings: list[str] = []
    slices = _slices(member, findings)
    imports = _sibling_imports(workspace, member, slices, findings)
    declared = _declared(workspace, member, findings)
    base_required = imports.get(None, {})
    findings += _compare(member, _BASE, base_required, declared.get(None, set()))
    for extra in slices:
        required = {
            sibling: site
            for sibling, site in imports.get(extra, {}).items()
            if sibling not in base_required
        }
        findings += _compare(member, _extra_group(extra), required, declared.get(extra, set()))
    return findings


def _slices(member: Member, findings: list[str]) -> dict[str, str]:
    """Each extra mapped to the child module name of the slice it gates."""
    children = {
        normalize(path.stem if path.is_file() else path.name): path.stem
        for path in member.source.iterdir()
        if (path.is_file() and path.suffix == ".py" and path.stem != "__init__")
        or (path / "__init__.py").is_file()
    }
    slices: dict[str, str] = {}
    for extra in member.optional_dependencies:
        child = children.get(normalize(extra))
        if child is None:
            findings.append(
                f"{member.name}: extra {extra!r} gates no {member.package}.{extra} slice, "
                "so the check cannot tell which imports it satisfies"
            )
        else:
            slices[extra] = child
    return slices


def _sibling_imports(
    workspace: Workspace, member: Member, slices: Mapping[str, str], findings: list[str]
) -> dict[str | None, dict[str, str]]:
    """Each sibling the member imports with its first import site, keyed by the
    extra whose slice imports it, or ``None`` outside every slice."""
    source_root = member.source.parents[1]
    extra_of = {child: extra for extra, child in slices.items()}
    imports: dict[str | None, dict[str, str]] = {}
    for path in python_files(member.source):
        module = module_name(path, source_root)
        parts = module.split(".")
        extra = extra_of.get(parts[2]) if len(parts) > 2 else None
        for imported, line in imported_modules(path, module).items():
            site = f"{path.relative_to(member.directory).as_posix()}:{line}"
            sibling = _sibling(workspace, member, imported, site, findings)
            if sibling is not None:
                imports.setdefault(extra, {}).setdefault(sibling, site)
    return imports


def _sibling(
    workspace: Workspace, member: Member, imported: str, site: str, findings: list[str]
) -> str | None:
    parts = imported.split(".")
    if len(parts) < 2 or parts[0] != NAMESPACE or parts[1] == member.scope:
        return None
    owner = workspace.owner(imported)
    if owner is None:
        finding = (
            f"{member.name}: {site} imports {NAMESPACE}.{parts[1]}, which no workspace member owns"
        )
        if finding not in findings:
            findings.append(finding)
        return None
    return owner.name


def _declared(
    workspace: Workspace, member: Member, findings: list[str]
) -> dict[str | None, set[str]]:
    names = {sibling.name for sibling in workspace.members}
    groups: dict[str | None, Iterable[str]] = {None: member.dependencies}
    groups.update(member.optional_dependencies)
    declared: dict[str | None, set[str]] = {}
    for group, requirements in groups.items():
        where = _BASE if group is None else _extra_group(group)
        for requirement in requirements:
            name = requirement_name(requirement)
            if name in names:
                declared.setdefault(group, set()).add(name)
            elif name.startswith(_SIBLING_PREFIX):
                findings.append(
                    f"{member.name}: {where} declares {name}, which is no workspace member"
                )
    return declared


def _compare(
    member: Member, where: str, required: Mapping[str, str], declared: set[str]
) -> list[str]:
    findings = [
        f"{member.name}: imports {sibling} ({site}) but {where} does not declare it"
        for sibling, site in sorted(required.items())
        if sibling not in declared
    ]
    findings += [
        f"{member.name}: {where} declares {sibling}, which "
        + ("is the member itself" if sibling == member.name else "nothing it gates imports")
        for sibling in sorted(declared - required.keys())
    ]
    return findings


def main(argv: list[str] | None = None) -> int:
    del argv
    findings = check(load_workspace(PY_ROOT))
    if not findings:
        print("check_distribution_dependencies: every sibling declaration matches its imports")
        return 0
    for finding in findings:
        print(finding, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
