"""Validate language binding selection and independently declared dependency topology."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reference_harness.dep_graph_check import (
    MODULE_SLUG,
    DepGraphFailure,
    parse_edges,
    parse_profile_envelopes,
    transitive_prerequisites,
)
from reference_harness.diagnostics import Diagnostic, report_failures
from reference_harness.schema_validate import validation_error

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

# A §7 table cell declares only what it spells in backticks, so a bare module
# token in a cell is prose and counts for no row.
_BACKTICKED_MODULE_RE = re.compile(rf"`({MODULE_SLUG})`")
_UNRESOLVED_RE = re.compile(
    r"\(decide and record\b|\b(?:TBD|TODO|FIXME|UNRESOLVED)\b|\?\?\?",
    re.IGNORECASE,
)

_SECTION_SOURCE_TOPOLOGY = "7. Source-enforcement topology"
_SECTION_ARTIFACT_TOPOLOGY = "8. Deployable artifact topology"


@dataclass(frozen=True)
class _Table:
    header: list[str]
    rows: list[tuple[int, list[str]]]


@dataclass(frozen=True)
class _LifecycleProfile:
    artifact_keyword: str


# Keyed by the value _lifecycle() returns.
_LIFECYCLE_PROFILES: dict[str, _LifecycleProfile] = {
    "snapshot": _LifecycleProfile(
        artifact_keyword="snapshot",
    ),
    "managed-object": _LifecycleProfile(
        artifact_keyword="managed",
    ),
}


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip("`*")).casefold()


def _line_number(markdown: str, offset: int) -> int:
    return markdown.count("\n", 0, offset) + 1


def _headings(markdown: str) -> list[tuple[int, str, int, int]]:
    return [
        (len(match.group(1)), match.group(2).strip(), match.start(), match.end())
        for match in _HEADING_RE.finditer(markdown)
    ]


def _section(markdown: str, title: str, level: int = 2) -> str | None:
    headings = _headings(markdown)
    normalized = _normalize(title)
    for index, (heading_level, heading, _start, end) in enumerate(headings):
        if heading_level != level or _normalize(heading) != normalized:
            continue
        section_end = len(markdown)
        for next_level, _next_heading, next_start, _next_end in headings[index + 1 :]:
            if next_level <= heading_level:
                section_end = next_start
                break
        return markdown[end:section_end]
    return None


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    content = stripped[1:-1] if stripped.endswith("|") else stripped[1:]
    return [cell.replace(r"\|", "|").strip() for cell in re.split(r"(?<!\\)\|", content)]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def _table_in_section(markdown: str, title: str) -> _Table | None:
    section = _section(markdown, title)
    if section is None:
        return None
    lines = section.splitlines()
    for index, line in enumerate(lines):
        header = _split_table_row(line)
        if not header or index + 1 >= len(lines):
            continue
        separator = _split_table_row(lines[index + 1])
        if len(separator) != len(header) or not _is_separator(separator):
            continue
        rows: list[tuple[int, list[str]]] = []
        for row_index, row_line in enumerate(lines[index + 2 :], start=index + 2):
            cells = _split_table_row(row_line)
            if not cells:
                break
            rows.append((row_index + 1, cells))
        return _Table(header=header, rows=rows)
    return None


def _lifecycle(capabilities: dict[str, Any]) -> str | None:
    modules = {module for module in capabilities.get("modules", []) if isinstance(module, str)}
    snapshot = "m-snapshot-read" in modules
    managed = "m-identity-map" in modules
    if snapshot == managed:
        return None
    return "snapshot" if snapshot else "managed-object"


def _check_table_shape(
    markdown: str,
    template: str,
    title: str,
    issues: list[Diagnostic],
) -> _Table | None:
    table = _table_in_section(markdown, title)
    if table is None:
        issues.append(Diagnostic("missing-section", f"missing '## {title}' or its table"))
        return None
    template_table = _table_in_section(template, title)
    if template_table is None:
        raise DepGraphFailure(f"template has no table under {title!r}")
    if [_normalize(cell) for cell in table.header] != [
        _normalize(cell) for cell in template_table.header
    ]:
        issues.append(
            Diagnostic(
                "topology-header",
                f"table under '## {title}' does not retain the canonical columns",
            )
        )
    if not table.rows:
        issues.append(Diagnostic("empty-topology", f"table under '## {title}' has no rows"))
    for _line, row in table.rows:
        if len(row) != len(table.header) or any(not cell.strip() for cell in row):
            issues.append(
                Diagnostic(
                    "incomplete-topology-row",
                    f"table under '## {title}' has a row with blank or missing cells",
                )
            )
    return table


def _check_topologies(
    markdown: str,
    template: str,
    capabilities: dict[str, Any],
    lifecycle: str | None,
    edges: list[tuple[str, str]],
    issues: list[Diagnostic],
) -> None:
    source = _check_table_shape(markdown, template, _SECTION_SOURCE_TOPOLOGY, issues)
    claimed = {module for module in capabilities.get("modules", []) if isinstance(module, str)}
    required_modules = claimed | set(transitive_prerequisites(claimed, edges))
    if source is not None:
        row_modules = [
            set(_BACKTICKED_MODULE_RE.findall(row[0])) for _line, row in source.rows if row
        ]
        for modules in row_modules:
            if len(modules) > 1:
                issues.append(
                    Diagnostic(
                        "combined-source-module-row",
                        "source-enforcement topology combines "
                        f"{', '.join(sorted(modules))} in one row",
                    )
                )
        for module in sorted(required_modules):
            occurrences = sum(module in modules for modules in row_modules)
            if occurrences == 0:
                issues.append(
                    Diagnostic(
                        "missing-source-module",
                        f"source-enforcement topology has no row for {module}",
                    )
                )
            elif occurrences > 1:
                issues.append(
                    Diagnostic(
                        "duplicate-source-module",
                        f"source-enforcement topology repeats {module}",
                    )
                )

    artifacts = _check_table_shape(markdown, template, _SECTION_ARTIFACT_TOPOLOGY, issues)
    if artifacts is None:
        return
    row_text = [" ".join(row).casefold() for _line, row in artifacts.rows]
    if not any("common runtime" in row for row in row_text):
        issues.append(
            Diagnostic("missing-artifact-role", "artifact topology has no common runtime row")
        )
    if lifecycle is not None:
        selected_keyword = _LIFECYCLE_PROFILES[lifecycle].artifact_keyword
        if not any(selected_keyword in row and "lifecycle" in row for row in row_text):
            issues.append(
                Diagnostic(
                    "missing-artifact-role",
                    f"artifact topology has no {selected_keyword} lifecycle extension row",
                )
            )
        # The completed spec retains only the selected lifecycle extension, so a
        # row describing the unselected sibling lifecycle must be rejected.
        for key, sibling in _LIFECYCLE_PROFILES.items():
            if key == lifecycle:
                continue
            if any(sibling.artifact_keyword in row and "lifecycle" in row for row in row_text):
                issues.append(
                    Diagnostic(
                        "unexpected-artifact-role",
                        f"artifact topology lists a stray {sibling.artifact_keyword} "
                        "lifecycle extension row",
                    )
                )
    for dialect in capabilities.get("dialects", []):
        if isinstance(dialect, str) and not any(
            dialect.casefold() in row and "adapter" in row for row in row_text
        ):
            issues.append(
                Diagnostic(
                    "missing-artifact-role",
                    f"artifact topology has no separate {dialect} adapter row",
                )
            )
    if not any(
        len(row) > 1 and "development-only" in row[1].casefold() for _line, row in artifacts.rows
    ):
        issues.append(
            Diagnostic(
                "missing-artifact-role", "artifact topology has no development-only tooling row"
            )
        )


def _unique_binding_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate binding key {key!r}")
        result[key] = value
    return result


def validate_language_spec(
    markdown: str,
    slices_markdown: str,
    modules_markdown: str,
    template: str,
    adapter_schema: dict[str, Any],
) -> tuple[list[Diagnostic], str | None, str | None]:
    issues = [
        Diagnostic(
            "unresolved-marker",
            f"line {_line_number(markdown, match.start())} contains unresolved marker "
            f"{match.group()!r}",
        )
        for match in _UNRESOLVED_RE.finditer(markdown)
    ]
    fences = re.findall(r"^```language-binding[ \t]*\n(.*?)^```[ \t]*$", markdown, re.M | re.S)
    starts = re.findall(r"^```language-binding[ \t]*$", markdown, re.M)
    if len(fences) != 1 or len(starts) != 1:
        issues.append(
            Diagnostic("binding-manifest", "expected exactly one closed language-binding fence")
        )
        return issues, None, None
    try:
        manifest = json.loads(fences[0], object_pairs_hook=_unique_binding_object)
    except ValueError as exc:
        issues.append(Diagnostic("binding-manifest", f"invalid binding JSON: {exc}"))
        return issues, None, None
    if not isinstance(manifest, dict) or set(manifest) != {"slice"}:
        issues.append(Diagnostic("binding-manifest", "binding must contain only the 'slice' key"))
        return issues, None, None
    selected = manifest["slice"]
    if not isinstance(selected, str) or not selected:
        issues.append(Diagnostic("slice-selection", "slice must be a nonempty string"))
        return issues, None, None

    canonical = parse_profile_envelopes(slices_markdown)
    envelope = canonical.get(selected)
    if envelope is None:
        issues.append(
            Diagnostic("unknown-slice", f"selected slice {selected!r} is not declared in slices.md")
        )
        return issues, selected, None
    schema_problem = validation_error(envelope, adapter_schema)
    if schema_problem is not None:
        issues.append(
            Diagnostic(
                "invalid-describe-envelope",
                "canonical claim does not satisfy conformance-adapter.schema.json: "
                + schema_problem,
            )
        )
        return issues, selected, None
    capabilities = envelope["capabilities"]
    lifecycle = _lifecycle(capabilities)
    if lifecycle is None:
        issues.append(
            Diagnostic(
                "lifecycle-incomplete-slice",
                f"selected slice {selected!r} is not a lifecycle-complete authoring choice",
            )
        )
    _check_topologies(
        markdown, template, capabilities, lifecycle, parse_edges(modules_markdown), issues
    )
    return issues, selected, lifecycle


def _usage() -> str:
    return (
        "usage: python -m reference_harness.language_spec_validate <repository-root>\n"
        "       python -m reference_harness.language_spec_validate "
        "<language-spec.md> <core-spec-dir>"
    )


def _validate_one(language_spec: Path, spec_dir: Path) -> int:
    if not language_spec.is_file():
        print(f"not a file: {language_spec}", file=sys.stderr)
        return 2
    if not spec_dir.is_dir():
        print(f"not a directory: {spec_dir}", file=sys.stderr)
        return 2
    sources = {
        "slices": spec_dir / "slices.md",
        "modules": spec_dir / "modules.md",
        "template": spec_dir / "language-spec-template.md",
        "adapter_schema": spec_dir.parent / "schemas" / "conformance-adapter.schema.json",
    }
    for required in sources.values():
        if not required.is_file():
            print(f"not a file: {required}", file=sys.stderr)
            return 2

    try:
        issues, selected, lifecycle = validate_language_spec(
            language_spec.read_text(encoding="utf-8"),
            sources["slices"].read_text(encoding="utf-8"),
            sources["modules"].read_text(encoding="utf-8"),
            sources["template"].read_text(encoding="utf-8"),
            json.loads(sources["adapter_schema"].read_text(encoding="utf-8")),
        )
    except (DepGraphFailure, OSError, ValueError) as exc:
        print(f"language spec validation FAILED: {exc}", file=sys.stderr)
        return 1

    if issues:
        report_failures("language spec validation", str(language_spec), issues)
        return 1

    print(f"language spec OK: {language_spec} ({selected}, {lifecycle} lifecycle)")
    return 0


def _validate_every_spec(root: Path) -> int:
    spec_dir = root / "core" / "spec"
    languages = root / "languages"
    if not languages.is_dir():
        print(f"not a directory: {languages}", file=sys.stderr)
        return 2
    targets = sorted(entry for entry in languages.iterdir() if entry.is_dir())
    worst = 0
    discovered = 0
    for target in targets:
        spec = target / "spec" / f"{target.name}.md"
        if not spec.is_file():
            print(f"missing language binding: {spec}", file=sys.stderr)
            worst = max(worst, 1)
            continue
        discovered += 1
        worst = max(worst, _validate_one(spec, spec_dir))
    if worst:
        return worst
    print(f"language specs OK: {discovered} completed spec(s) under {languages}")
    return 0


def main(argv: list[str]) -> int:
    """Validate one completed language spec, or every one the repository holds.

    Exit codes: 0 — binding selection and topology are valid; 1 — validation or
    input reading failed; 2 — usage error, including a path that does not exist.
    """
    if len(argv) == 2:
        return _validate_one(Path(argv[0]), Path(argv[1]))
    if len(argv) != 1:
        print(_usage(), file=sys.stderr)
        return 2
    root = Path(argv[0])
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    return _validate_every_spec(root)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
