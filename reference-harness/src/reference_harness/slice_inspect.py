"""Derive a Conformance Slice report from the canonical core artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from reference_harness.dep_graph_check import (
    DepGraphFailure,
    check,
    load_cases,
    parse_edges,
    parse_profile_envelopes,
    profile_errors,
    transitive_prerequisites,
)
from reference_harness.paths import find_core_root
from reference_harness.schema_validate import validation_error


def _module_tags(doc: dict[str, Any]) -> set[str]:
    return {tag for tag in doc.get("tags", []) if isinstance(tag, str) and tag.startswith("m-")}


def build_reports(spec_dir: Path, compatibility_root: Path) -> dict[str, dict[str, Any]]:
    """Build one derived report per canonical claim.

    The claims, graph, and case documents remain authoritative. The returned
    mappings contain only values derived from those inputs.
    """
    slices_path = spec_dir / "slices.md"
    modules_path = spec_dir / "modules.md"
    slices_markdown = slices_path.read_text(encoding="utf-8")
    modules_markdown = modules_path.read_text(encoding="utf-8")

    graph_errors = check(modules_markdown)
    claim_errors = profile_errors(slices_markdown, compatibility_root)
    errors = [*graph_errors, *claim_errors]
    if errors:
        raise DepGraphFailure("; ".join(errors))

    envelopes = parse_profile_envelopes(slices_markdown)
    adapter_schema_path = find_core_root(spec_dir) / "schemas" / "conformance-adapter.schema.json"
    adapter_schema = json.loads(adapter_schema_path.read_text(encoding="utf-8"))
    for slice_tag, envelope in envelopes.items():
        problem = validation_error(envelope, adapter_schema)
        if problem is not None:
            raise DepGraphFailure(
                f"canonical claim {slice_tag!r} does not satisfy "
                f"conformance-adapter.schema.json: {problem}"
            )
    cases = load_cases(compatibility_root)
    edges = parse_edges(modules_markdown)
    repo_root = find_core_root(compatibility_root).parent
    reports: dict[str, dict[str, Any]] = {}

    for slice_tag, envelope in envelopes.items():
        capabilities = envelope["capabilities"]
        tagged = [
            (path, doc)
            for path, doc in cases
            if slice_tag in [tag for tag in doc.get("tags", []) if isinstance(tag, str)]
        ]
        module_union = sorted({module for _path, doc in tagged for module in _module_tags(doc)})
        claimed_modules = {
            module for module in capabilities.get("modules", []) if isinstance(module, str)
        }
        reports[slice_tag] = {
            "slice": slice_tag,
            "canonicalClaim": envelope,
            "cases": [path.resolve().relative_to(repo_root).as_posix() for path, _doc in tagged],
            "moduleTagUnion": module_union,
            "supported": {
                "caseShapes": capabilities.get("caseShapes", []),
                "commands": capabilities.get("commands", []),
                "dialects": capabilities.get("dialects", []),
            },
            "transitivePrerequisitesOutsideClaim": transitive_prerequisites(claimed_modules, edges),
        }
    return reports


def _print_report(report: dict[str, Any]) -> None:
    print(f"Slice: {report['slice']}")
    print("Canonical claim:")
    print(json.dumps(report["canonicalClaim"], indent=2, sort_keys=True))
    cases = report["cases"]
    print(f"Case membership ({len(cases)}):")
    for case in cases:
        print(f"  - {case}")
    modules = report["moduleTagUnion"]
    print(f"Module-tag union ({len(modules)}):")
    for module in modules:
        print(f"  - {module}")
    supported = report["supported"]
    print("Supported case shapes: " + ", ".join(supported["caseShapes"]))
    print("Supported dialects: " + ", ".join(supported["dialects"]))
    print("Supported commands: " + ", ".join(supported["commands"]))
    prerequisites = report["transitivePrerequisitesOutsideClaim"]
    print(f"Transitive prerequisites outside claim coverage ({len(prerequisites)}):")
    for module in prerequisites:
        print(f"  - {module}")


def _usage() -> str:
    return (
        "usage: python -m reference_harness.slice_inspect [--json] "
        "<spec-dir> <compatibility-dir> <slice-tag>\n"
        "   or: python -m reference_harness.slice_inspect --check-all "
        "<spec-dir> <compatibility-dir>"
    )


def main(argv: list[str]) -> int:
    json_output = bool(argv and argv[0] == "--json")
    check_all = bool(argv and argv[0] == "--check-all")
    rest = argv[1:] if json_output or check_all else argv
    expected = 2 if check_all else 3
    if len(rest) != expected:
        print(_usage(), file=sys.stderr)
        return 2

    spec_dir = Path(rest[0])
    compatibility_root = Path(rest[1])
    if not spec_dir.is_dir():
        print(f"not a directory: {spec_dir}", file=sys.stderr)
        return 2
    if not compatibility_root.is_dir():
        print(f"not a directory: {compatibility_root}", file=sys.stderr)
        return 2
    for required in (spec_dir / "slices.md", spec_dir / "modules.md"):
        if not required.is_file():
            print(f"not a file: {required}", file=sys.stderr)
            return 2

    try:
        reports = build_reports(spec_dir, compatibility_root)
    except (DepGraphFailure, OSError, ValueError) as exc:
        print(f"slice inspection FAILED: {exc}", file=sys.stderr)
        return 1

    if check_all:
        print(f"slice inspection OK: {len(reports)} canonical claim(s)")
        return 0

    slice_tag = rest[2]
    report = reports.get(slice_tag)
    if report is None:
        available = ", ".join(sorted(reports))
        print(
            f"unknown slice {slice_tag!r}; available canonical claims: {available}",
            file=sys.stderr,
        )
        return 2
    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
