"""Validate the compatibility corpus's sharing-scope twin proofs.

A Sharing Scope governs which published nodes are reused across a result's roots,
and changes no statement and no Wire document. The corpus proves that by authoring
the same read once per scope, so the claim two such cases jointly make survives
only while they still describe one read. This checker keeps that true: a coherent
edit to one arm's query and graph together would otherwise leave two cases passing
and the invariance quietly gone.

The arms are named ``<module>-NNN-<proof>-sharing-scope-twin-<sharingScope>.yaml``
and paired by ``<module>-<proof>``. Each arm declares its own ``sharingScope``, and
on everything else they must be equal, their statements included. Only an arm may
declare a scope, so every case is read: a declaration under any other name would
otherwise escape the pairing that proves it.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from reference_harness.case_twins import (
    case_twin_arms,
    logical_case,
    mapping_document,
    module_ids,
    yaml_paths,
)

__all__ = ["main", "run", "sharing_scope_twin_errors"]

_CASE_TWIN_RE = re.compile(r"^(?P<prefix>.+)-sharing-scope-twin-(?P<arm>[^.]+)\.ya?ml$")
_SCOPES = frozenset({"root", "page"})


def _is_sharing_scope_member(path: tuple[str, ...], key: str) -> bool:
    """The one member an arm owns. A Sharing Scope moves no physical observation,
    so the members other twins set aside stay compared here."""
    return path == ("when",) and key == "sharingScope"


def _declared_scope(document: Mapping[str, Any]) -> object:
    when = document.get("when")
    return when.get("sharingScope") if isinstance(when, Mapping) else None


def _refuse_scopes_outside_twins(paths: Iterable[Path], errors: list[str]) -> None:
    for path in paths:
        if _CASE_TWIN_RE.match(path.name) is not None:
            continue
        document = mapping_document(path, "compatibility case", errors)
        if document is not None and _declared_scope(document) is not None:
            errors.append(
                f"{path.name}: only a sharing-scope twin may declare when.sharingScope; name "
                "the case <module>-NNN-<proof>-sharing-scope-twin-<sharingScope>.yaml"
            )


def sharing_scope_twin_errors(compatibility_root: Path) -> list[str]:
    """Return every sharing-scope twin inconsistency under *compatibility_root*."""
    errors: list[str] = []
    if not compatibility_root.is_dir():
        return [f"not a directory: {compatibility_root}"]

    modules = module_ids(compatibility_root, errors)
    paths = yaml_paths(compatibility_root / "cases")
    _refuse_scopes_outside_twins(paths, errors)
    candidates = case_twin_arms(paths, _CASE_TWIN_RE, modules, "sharing-scope", errors)
    for pair, arms in sorted(candidates.items()):
        if set(arms) != _SCOPES:
            errors.append(
                f"sharing-scope twin {pair!r} has arms {sorted(arms)}; the proof is that one "
                "read states the same thing at root and at page"
            )
            continue
        documents: dict[str, dict[str, Any]] = {}
        for arm, path in sorted(arms.items()):
            document = mapping_document(path, "compatibility case", errors)
            if document is None:
                continue
            declared = _declared_scope(document)
            if declared != arm:
                errors.append(
                    f"{path.name}: filename declares sharing scope {arm} but "
                    f"when.sharingScope is {declared!r}"
                )
            documents[arm] = document
        if len(documents) == len(arms) and logical_case(
            documents["root"], physical=_is_sharing_scope_member
        ) != logical_case(documents["page"], physical=_is_sharing_scope_member):
            errors.append(f"sharing-scope twin {pair!r} arms differ in more than when.sharingScope")
    return errors


def run(compatibility_root: Path) -> int:
    """Run the sharing-scope twin gate and print a concise verdict."""
    errors = sharing_scope_twin_errors(compatibility_root)
    if errors:
        print(f"sharing-scope twin gate FAILED ({len(errors)} problem(s)):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("sharing-scope twin gate OK: every twin states one read at both scopes")
    return 0


def main(argv: list[str]) -> int:
    """CLI entry point for ``python -m reference_harness.sharing_scope_twin_check``."""
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.sharing_scope_twin_check <compatibility-dir>",
            file=sys.stderr,
        )
        return 2
    return run(Path(argv[0]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
