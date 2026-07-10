"""Validate a completed language spec against the canonical authoring contract."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reference_harness.dep_graph_check import (
    JSON_FENCE_RE,
    MODULE_SLUG,
    DepGraphFailure,
    parse_edges,
    parse_profile_envelopes,
    transitive_prerequisites,
)
from reference_harness.schema_validate import validation_error

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
# The canonical module-slug body lives in dep_graph_check; wrap it in word
# boundaries here to extract module tokens embedded in prose and table cells.
_MODULE_RE = re.compile(rf"\b{MODULE_SLUG}\b")
_UNRESOLVED_RE = re.compile(
    r"\(decide and record\b|\b(?:TBD|TODO|FIXME|UNRESOLVED)\b|\?\?\?",
    re.IGNORECASE,
)

# Section titles that mirror the numbered headings in language-spec-template.md.
_SECTION_SOURCE_TOPOLOGY = "7. Source-enforcement topology"
_SECTION_ARTIFACT_TOPOLOGY = "8. Deployable artifact topology"
_SECTION_CONDITIONALS = "9. Conditional capability decisions"
_SECTION_QUALITY = "10. Mandatory quality toolchain"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


@dataclass(frozen=True)
class _Table:
    header: list[str]
    rows: list[tuple[int, list[str]]]


@dataclass(frozen=True)
class _LifecycleProfile:
    """One object-lifecycle authoring choice.

    Centralizes the template headings and the §8 artifact keyword that differ
    between the snapshot and managed-object lifecycles so the title/keyword
    selection lives in one place. Titles mirror language-spec-template.md.
    """

    lifecycle_heading: str
    results_heading: str
    artifact_keyword: str


# Keyed by the value _lifecycle() returns.
_LIFECYCLE_PROFILES: dict[str, _LifecycleProfile] = {
    "snapshot": _LifecycleProfile(
        lifecycle_heading="Snapshot lifecycle",
        results_heading="Snapshot results",
        artifact_keyword="snapshot",
    ),
    "managed-object": _LifecycleProfile(
        lifecycle_heading="Managed-object lifecycle",
        results_heading="Managed-object results",
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


def _heading_count(markdown: str, title: str, level: int = 3) -> int:
    normalized = _normalize(title)
    return sum(
        heading_level == level and _normalize(heading) == normalized
        for heading_level, heading, _start, _end in _headings(markdown)
    )


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


def _describe_envelopes(markdown: str) -> tuple[list[dict[str, Any]], list[ValidationIssue]]:
    envelopes: list[dict[str, Any]] = []
    issues: list[ValidationIssue] = []
    for index, block in enumerate(JSON_FENCE_RE.findall(markdown), start=1):
        try:
            value = json.loads(block)
        except json.JSONDecodeError as exc:
            issues.append(
                ValidationIssue("invalid-json", f"JSON fence {index} is invalid: {exc.msg}")
            )
            continue
        if (
            isinstance(value, dict)
            and value.get("command") == "describe"
            and isinstance(value.get("capabilities"), dict)
        ):
            envelopes.append(value)
    return envelopes, issues


def _selected_slice(envelope: dict[str, Any]) -> str | None:
    capabilities = envelope.get("capabilities")
    case_tags = capabilities.get("caseTags") if isinstance(capabilities, dict) else None
    include = case_tags.get("include") if isinstance(case_tags, dict) else None
    if isinstance(include, list) and len(include) == 1 and isinstance(include[0], str):
        return include[0]
    return None


def _lifecycle(capabilities: dict[str, Any]) -> str | None:
    modules = {module for module in capabilities.get("modules", []) if isinstance(module, str)}
    snapshot = "m-snapshot-read" in modules
    managed = {"m-identity-map", "m-detach"}.issubset(modules)
    if snapshot == managed:
        return None
    return "snapshot" if snapshot else "managed-object"


def _conditional_rules(template: str) -> dict[str, set[str]]:
    section = _section(template, _SECTION_CONDITIONALS)
    if section is None:
        return {}
    rules: dict[str, set[str]] = {}
    headings = _headings(section)
    for index, (level, title, _start, end) in enumerate(headings):
        if level != 3:
            continue
        body_end = len(section)
        for next_level, _next_title, next_start, _next_end in headings[index + 1 :]:
            if next_level <= level:
                body_end = next_start
                break
        marker_lines = "\n".join(
            line for line in section[end:body_end].splitlines() if "decide and record" in line
        )
        rules[title] = set(_MODULE_RE.findall(marker_lines))
    return rules


def _check_lifecycle(markdown: str, expected: str | None, issues: list[ValidationIssue]) -> None:
    # The §3 lifecycle headings and §4 result headings run the same retained-heading
    # logic; each kind's per-lifecycle titles come from _LIFECYCLE_PROFILES.
    heading_kinds = (
        (
            "lifecycle-profile",
            "lifecycle heading",
            {key: profile.lifecycle_heading for key, profile in _LIFECYCLE_PROFILES.items()},
        ),
        (
            "result-profile",
            "result heading",
            {key: profile.results_heading for key, profile in _LIFECYCLE_PROFILES.items()},
        ),
    )
    for code, noun, title_for in heading_kinds:
        retained = [title for title in title_for.values() if _heading_count(markdown, title) > 0]
        if len(retained) != 1:
            issues.append(
                ValidationIssue(
                    code,
                    f"retain exactly one {noun}; found: "
                    + (", ".join(retained) if retained else "none"),
                )
            )
        elif expected is not None:
            expected_title = title_for[expected]
            if retained[0] != expected_title:
                issues.append(
                    ValidationIssue(
                        code,
                        f"slice requires '{expected_title}', but '{retained[0]}' is retained",
                    )
                )


def _check_conditionals(
    markdown: str,
    template: str,
    capabilities: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    claimed = {module for module in capabilities.get("modules", []) if isinstance(module, str)}
    for title, required in _conditional_rules(template).items():
        expected = bool(required) and required.issubset(claimed)
        present = _heading_count(markdown, title) == 1
        if expected and not present:
            issues.append(
                ValidationIssue(
                    "missing-conditional-section",
                    f"retain '{title}'; {', '.join(sorted(required))} is claimed",
                )
            )
        elif not expected and present:
            issues.append(
                ValidationIssue(
                    "unexpected-conditional-section",
                    f"remove '{title}'; {', '.join(sorted(required))} is not claimed",
                )
            )
        elif present and not (_section(markdown, title, level=3) or "").strip():
            issues.append(
                ValidationIssue(
                    "incomplete-conditional-section", f"'{title}' has no completed decision"
                )
            )

    additional_dialects = len(capabilities.get("dialects", [])) > 1
    has_additional = _heading_count(markdown, "Additional dialects") == 1
    if additional_dialects and not has_additional:
        issues.append(
            ValidationIssue(
                "missing-conditional-section",
                "retain 'Additional dialects'; the claim contains more than one dialect",
            )
        )
    elif not additional_dialects and has_additional:
        issues.append(
            ValidationIssue(
                "unexpected-conditional-section",
                "remove 'Additional dialects'; the claim contains only its initial dialect",
            )
        )


def _check_table_shape(
    markdown: str,
    template: str,
    title: str,
    issues: list[ValidationIssue],
) -> _Table | None:
    table = _table_in_section(markdown, title)
    if table is None:
        issues.append(ValidationIssue("missing-section", f"missing '## {title}' or its table"))
        return None
    template_table = _table_in_section(template, title)
    if template_table is None:
        raise DepGraphFailure(f"template has no table under {title!r}")
    if [_normalize(cell) for cell in table.header] != [
        _normalize(cell) for cell in template_table.header
    ]:
        issues.append(
            ValidationIssue(
                "topology-header",
                f"table under '## {title}' does not retain the canonical columns",
            )
        )
    if not table.rows:
        issues.append(ValidationIssue("empty-topology", f"table under '## {title}' has no rows"))
    for _line, row in table.rows:
        if len(row) != len(table.header) or any(not cell.strip() for cell in row):
            issues.append(
                ValidationIssue(
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
    issues: list[ValidationIssue],
) -> None:
    source = _check_table_shape(markdown, template, _SECTION_SOURCE_TOPOLOGY, issues)
    claimed = {module for module in capabilities.get("modules", []) if isinstance(module, str)}
    required_modules = claimed | set(transitive_prerequisites(claimed, edges))
    if source is not None:
        row_modules = [set(_MODULE_RE.findall(row[0])) for _line, row in source.rows if row]
        for module in sorted(required_modules):
            occurrences = sum(module in modules for modules in row_modules)
            if occurrences == 0:
                issues.append(
                    ValidationIssue(
                        "missing-source-module",
                        f"source-enforcement topology has no row for {module}",
                    )
                )
            elif occurrences > 1:
                issues.append(
                    ValidationIssue(
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
            ValidationIssue("missing-artifact-role", "artifact topology has no common runtime row")
        )
    if lifecycle is not None:
        selected_keyword = _LIFECYCLE_PROFILES[lifecycle].artifact_keyword
        if not any(selected_keyword in row and "lifecycle" in row for row in row_text):
            issues.append(
                ValidationIssue(
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
                    ValidationIssue(
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
                ValidationIssue(
                    "missing-artifact-role",
                    f"artifact topology has no separate {dialect} adapter row",
                )
            )
    if not any(
        len(row) > 1 and "development-only" in row[1].casefold() for _line, row in artifacts.rows
    ):
        issues.append(
            ValidationIssue(
                "missing-artifact-role", "artifact topology has no development-only tooling row"
            )
        )


def _check_quality(markdown: str, template: str, issues: list[ValidationIssue]) -> None:
    title = _SECTION_QUALITY
    table = _table_in_section(markdown, title)
    canonical = _table_in_section(template, title)
    if table is None:
        issues.append(ValidationIssue("missing-section", f"missing '## {title}' or its table"))
        return
    if canonical is None:
        raise DepGraphFailure("template has no mandatory quality table")
    if [_normalize(cell) for cell in table.header] != [
        _normalize(cell) for cell in canonical.header
    ]:
        issues.append(
            ValidationIssue("quality-header", "quality table does not retain the canonical columns")
        )

    rows = {_normalize(row[0]): row for _line, row in table.rows if row}
    expected = [row[0] for _line, row in canonical.rows if row]
    for label in expected:
        normalized = _normalize(label)
        row = rows.get(normalized)
        if row is None:
            issues.append(
                ValidationIssue("missing-quality-row", f"quality table has no '{label}' row")
            )
            continue
        for index, header in enumerate(table.header):
            if index >= len(row) or not row[index].strip():
                issues.append(
                    ValidationIssue(
                        "incomplete-quality-row",
                        f"quality row '{label}' has a blank {header} cell",
                    )
                )

    coverage = rows.get(_normalize("Code coverage"), [])
    if coverage and not re.search(r"\b\d+(?:\.\d+)?\s*%", " ".join(coverage)):
        issues.append(
            ValidationIssue(
                "coverage-threshold", "Code coverage row has no explicit numeric percentage"
            )
        )
    typing = rows.get(_normalize("Strict static typing"), [])
    if typing and "strict" not in " ".join(typing).casefold():
        issues.append(
            ValidationIssue("strict-typing", "Strict static typing row does not enable strict mode")
        )
    database = rows.get(_normalize("Database-backed verification"), [])
    database_text = " ".join(database).casefold()
    if database and not ("skip" in database_text and "reason" in database_text):
        issues.append(
            ValidationIssue(
                "database-skip-policy",
                "Database-backed verification row must report every skipped check with a reason",
            )
        )

    section = _section(markdown, title) or ""
    if not re.search(r"\bstatic[- ]verification\b", section, re.IGNORECASE):
        issues.append(
            ValidationIssue(
                "missing-aggregate-command",
                "quality section has no aggregate static-verification command",
            )
        )
    if not re.search(r"\bfull verification\b", section, re.IGNORECASE):
        issues.append(
            ValidationIssue(
                "missing-aggregate-command",
                "quality section has no aggregate full verification command",
            )
        )


def validate_language_spec(
    markdown: str,
    slices_markdown: str,
    modules_markdown: str,
    template: str,
    adapter_schema: dict[str, Any],
) -> tuple[list[ValidationIssue], str | None, str | None]:
    """Return all completion issues plus the selected slice/lifecycle when known."""
    issues: list[ValidationIssue] = []
    for match in _UNRESOLVED_RE.finditer(markdown):
        issues.append(
            ValidationIssue(
                "unresolved-marker",
                f"line {_line_number(markdown, match.start())} contains unresolved marker "
                f"{match.group(0)!r}",
            )
        )

    authored, json_issues = _describe_envelopes(markdown)
    issues.extend(json_issues)
    if len(authored) != 1:
        issues.append(
            ValidationIssue(
                "describe-claim",
                f"expected exactly one describe claim JSON fence, found {len(authored)}",
            )
        )
        selected = None
        capabilities: dict[str, Any] = {}
    else:
        selected = _selected_slice(authored[0])
        capabilities = authored[0]["capabilities"]
        schema_problem = validation_error(authored[0], adapter_schema)
        if schema_problem is not None:
            issues.append(
                ValidationIssue(
                    "invalid-describe-envelope",
                    "describe claim does not satisfy conformance-adapter.schema.json: "
                    + schema_problem,
                )
            )
        if selected is None:
            issues.append(
                ValidationIssue(
                    "slice-selection",
                    "describe claim must select exactly one slice tag with caseTags.include",
                )
            )

    canonical = parse_profile_envelopes(slices_markdown)
    expected_capabilities: dict[str, Any] = {}
    if selected is not None:
        envelope = canonical.get(selected)
        if envelope is None:
            issues.append(
                ValidationIssue(
                    "unknown-slice", f"selected slice {selected!r} is not declared in slices.md"
                )
            )
        else:
            expected_capabilities = envelope["capabilities"]
            for key in sorted(set(capabilities) | set(expected_capabilities)):
                if capabilities.get(key) != expected_capabilities.get(key):
                    issues.append(
                        ValidationIssue(
                            "claim-mismatch",
                            f"capabilities.{key} differs from the canonical claim",
                        )
                    )

    lifecycle = _lifecycle(expected_capabilities) if expected_capabilities else None
    if selected is not None and selected in canonical and lifecycle is None:
        issues.append(
            ValidationIssue(
                "lifecycle-incomplete-slice",
                f"selected slice {selected!r} is not a lifecycle-complete authoring choice",
            )
        )

    _check_lifecycle(markdown, lifecycle, issues)
    if expected_capabilities:
        _check_conditionals(markdown, template, expected_capabilities, issues)
        edges = parse_edges(modules_markdown)
        _check_topologies(markdown, template, expected_capabilities, lifecycle, edges, issues)
    _check_quality(markdown, template, issues)
    return issues, selected, lifecycle


def _usage() -> str:
    return (
        "usage: python -m reference_harness.language_spec_validate "
        "<language-spec.md> <core-spec-dir>"
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(_usage(), file=sys.stderr)
        return 2
    language_spec = Path(argv[0])
    spec_dir = Path(argv[1])
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
        print(
            f"language spec validation FAILED ({len(issues)} problem(s)): {language_spec}",
            file=sys.stderr,
        )
        for issue in issues:
            print(f"  - [{issue.code}] {issue.message}", file=sys.stderr)
        return 1

    print(f"language spec OK: {language_spec} ({selected}, {lifecycle} lifecycle)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
