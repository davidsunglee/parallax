"""Parse the normative module-dependency graph and assert it is a legal DAG.

Three modes:

* **DAG check** (default) — validate the graph in ``modules.md``::

      uv run python -m reference_harness.dep_graph_check core/spec/modules.md

* **Coverage gate** (``--coverage``) — the DAG check **plus** assert every
  ``active`` module whose coverage source is ``cases`` has at least one
  compatibility fixture tagged to it, **plus** assert no active module depends on
  a deferred one::

      uv run python -m reference_harness.dep_graph_check --coverage core/spec core/compatibility

* **Profile gate** (``--profile``) — assert the ``slice-mvp-1`` Conformance
  Slice's tagged cases are consistent with its canonical ``describe`` claim
  embedded in ``slices.md``::

      uv run python -m reference_harness.dep_graph_check --profile core/spec core/compatibility

The machine-readable source of truth for the graph is the fenced
```` ```dependency-graph ```` block in ``modules.md``. Each line is an edge
``A --> B`` meaning "A depends on B". Module identifiers are canonical
``m-<slug>`` tokens (grammar ``^m-[a-z0-9]+(-[a-z0-9]+)*$``); the same token form
appears in fixture ``tags``. The DAG check asserts:

* every edge names two well-formed module slugs;
* the graph is a **directed acyclic graph** (no cycles);
* edge direction is **legal** — an edge must not point "upward" against the
  layering (surfaced as the acyclicity property).

The **coverage gate** reads the module catalog table from ``modules.md`` and
asserts each ``active`` / ``cases`` module has fixture coverage, measured against
the ``tags`` of every fixture under ``core/compatibility/`` (cases *and*
benchmarks). ``deferred`` modules and the one ``contract``-covered module
(``m-db-port``) are excluded from the gate by construction.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

_FENCE_RE = re.compile(r"```dependency-graph\n(.*?)```", re.DOTALL)
_SLUG = r"m-[a-z0-9]+(?:-[a-z0-9]+)*"
_EDGE_RE = re.compile(rf"^\s*({_SLUG})\s*-->\s*({_SLUG})\s*$")
_MODULE_RE = re.compile(rf"^{_SLUG}$")  # doubles as the fixture-tag pattern

# The heading under which the module catalog table lives in modules.md, normalized
# to lower case. The coverage gate parses that table (module | summary | status |
# coverage) instead of a separate config file.
_CATALOG_HEADING = "the module catalog"

# The only legal values of the catalog's status/coverage columns. Parsing rejects
# anything else so a typo (`activ`, `case`) or a column-shifting stray pipe can't
# silently drop a module out of the gated set.
_CATALOG_STATUSES = frozenset({"active", "deferred"})
_CATALOG_COVERAGES = frozenset({"cases", "contract"})

# The named conformance slice the profile gate enforces. The slice is selected by
# this single tag on each included case; the canonical describe claim that declares
# its boundaries lives in slices.md.
_SLICE_TAG = "slice-mvp-1"

# The heading under which the canonical slice claim is embedded in slices.md,
# normalized to lower case (the json fence right after it is the source of truth).
_SLICE_HEADING = "first-implementation conformance slice"


class DepGraphFailure(Exception):
    pass


def parse_edges(markdown: str) -> list[tuple[str, str]]:
    """Extract the (depends-on) edges from the dependency-graph fenced block."""
    match = _FENCE_RE.search(markdown)
    if not match:
        raise DepGraphFailure("no ```dependency-graph fenced block found in the spec file")
    edges: list[tuple[str, str]] = []
    for lineno, line in enumerate(match.group(1).splitlines(), start=1):
        if not line.strip():
            continue
        edge = _EDGE_RE.match(line)
        if not edge:
            raise DepGraphFailure(
                f"dependency-graph line {lineno} is not a valid 'A --> B' edge: {line!r}"
            )
        edges.append((edge.group(1), edge.group(2)))
    if not edges:
        raise DepGraphFailure("dependency-graph block declares no edges")
    return edges


def _find_cycle(edges: list[tuple[str, str]]) -> list[str] | None:
    """Return a cycle path if the directed graph has one, else None."""
    adjacency: dict[str, list[str]] = {}
    for src, dst in edges:
        adjacency.setdefault(src, []).append(dst)
        adjacency.setdefault(dst, [])

    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(adjacency, WHITE)
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = GRAY
        stack.append(node)
        for neighbor in adjacency[node]:
            if color[neighbor] == GRAY:
                idx = stack.index(neighbor)
                return [*stack[idx:], neighbor]
            if color[neighbor] == WHITE:
                cycle = visit(neighbor)
                if cycle:
                    return cycle
        color[node] = BLACK
        stack.pop()
        return None

    for node in sorted(adjacency):
        if color[node] == WHITE:
            cycle = visit(node)
            if cycle:
                return cycle
    return None


def check(markdown: str) -> list[str]:
    """Validate the graph; return a list of error strings (empty == OK)."""
    errors: list[str] = []
    try:
        edges = parse_edges(markdown)
    except DepGraphFailure as exc:
        return [str(exc)]

    for src, dst in edges:
        if not _MODULE_RE.match(src):
            errors.append(f"unrecognized module on left of edge: {src!r}")
        if not _MODULE_RE.match(dst):
            errors.append(f"unrecognized module on right of edge: {dst!r}")
        if src == dst:
            errors.append(f"self-dependency is illegal: {src} --> {dst}")

    cycle = _find_cycle(edges)
    if cycle:
        errors.append("dependency graph is not a DAG; cycle: " + " --> ".join(cycle))

    return errors


# --- catalog + coverage gate ------------------------------------------------


def parse_catalog(modules_markdown: str) -> dict[str, dict[str, str]]:
    """Return ``{module: {"status", "coverage"}}`` from the catalog table.

    The catalog is a markdown table (``module | summary | status | coverage``)
    under the ``## The module catalog`` heading of ``modules.md``. ``status`` is
    ``active`` or ``deferred``; ``coverage`` is ``cases`` or ``contract``.
    """
    header: list[str] | None = None
    in_section = False
    catalog: dict[str, dict[str, str]] = {}
    for line in modules_markdown.splitlines():
        heading = re.match(r"^##\s+(.*?)\s*$", line)
        if heading:
            if header is not None:
                break  # the table's own section has ended
            in_section = heading.group(1).strip().lower() == _CATALOG_HEADING
            continue
        if not in_section:
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            if header is not None:
                break  # a non-table line after the table ends it
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if header is None:
            header = [cell.lower() for cell in cells]
            continue
        if all(set(cell) <= set("-: ") for cell in cells):
            continue  # separator row
        row = dict(zip(header, cells, strict=False))
        module = row.get("module", "").strip("` ")
        if not _MODULE_RE.match(module):
            continue
        status = row.get("status", "").strip("` ").lower()
        coverage = row.get("coverage", "").strip("` ").lower()
        if status not in _CATALOG_STATUSES:
            raise DepGraphFailure(
                f"module {module} has unknown status {status!r} in the catalog table "
                f"(expected one of {sorted(_CATALOG_STATUSES)})"
            )
        if coverage not in _CATALOG_COVERAGES:
            raise DepGraphFailure(
                f"module {module} has unknown coverage {coverage!r} in the catalog table "
                f"(expected one of {sorted(_CATALOG_COVERAGES)})"
            )
        catalog[module] = {"status": status, "coverage": coverage}
    if not catalog:
        raise DepGraphFailure(
            f"no module catalog table found under the '## {_CATALOG_HEADING}' heading of modules.md"
        )
    return catalog


def gated_modules(catalog: dict[str, dict[str, str]]) -> list[str]:
    """The modules the coverage gate enforces: ``active`` with ``cases`` coverage."""
    return sorted(
        module
        for module, meta in catalog.items()
        if meta["status"] == "active" and meta["coverage"] == "cases"
    )


def _fixture_tags(compatibility_root: Path) -> set[str]:
    """Collect the lower-cased ``tags`` of every fixture under compatibility/.

    Scans both ``cases/`` and ``benchmarks/``. A fixture that does not parse to a
    mapping, or that carries no ``tags``, contributes nothing.
    """
    tags: set[str] = set()
    for subdir in ("cases", "benchmarks"):
        root = compatibility_root / subdir
        if not root.is_dir():
            continue
        for path in sorted(root.glob("**/*.yaml")) + sorted(root.glob("**/*.yml")):
            try:
                doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            except yaml.YAMLError:
                continue
            if not isinstance(doc, dict):
                continue
            for tag in doc.get("tags", []):
                if isinstance(tag, str):
                    tags.add(tag.strip().lower())
    return tags


def coverage_errors(modules_markdown: str, compatibility_root: Path) -> list[str]:
    """Assert every ``active`` / ``cases`` module has >=1 fixture tagged to it."""
    try:
        catalog = parse_catalog(modules_markdown)
    except DepGraphFailure as exc:
        return [str(exc)]

    fixture_tags = _fixture_tags(compatibility_root)
    if not fixture_tags:
        return [f"no fixture tags discovered under {compatibility_root}"]

    uncovered = [m for m in gated_modules(catalog) if m.lower() not in fixture_tags]
    return [
        f"active module {module} (coverage: cases) has no fixture tagged to it "
        f"(expected at least one fixture with tag {module!r})"
        for module in uncovered
    ]


def active_deferred_edge_errors(modules_markdown: str) -> list[str]:
    """Assert no ``active`` module depends on a ``deferred`` one (a design rule)."""
    try:
        catalog = parse_catalog(modules_markdown)
        edges = parse_edges(modules_markdown)
    except DepGraphFailure as exc:
        return [str(exc)]

    status = {module: meta["status"] for module, meta in catalog.items()}
    return [
        f"active module {src} depends on deferred module {dst} ({src} --> {dst})"
        for src, dst in edges
        if status.get(src) == "active" and status.get(dst) == "deferred"
    ]


def catalog_graph_consistency_errors(modules_markdown: str) -> list[str]:
    """Assert the catalog table and the DAG name the same set of modules.

    The coverage and active->deferred gates both key off the catalog, so a
    module that is edged but not catalogued would slip past them silently (its
    status resolves to ``None``); a module that is catalogued but never edged is
    an orphan the DAG check cannot see. Requiring the two node sets to match
    closes both holes.
    """
    try:
        catalog = set(parse_catalog(modules_markdown))
        edges = parse_edges(modules_markdown)
    except DepGraphFailure as exc:
        return [str(exc)]

    nodes = {node for edge in edges for node in edge}
    return [
        f"module {module} appears in the DAG but not the catalog table"
        for module in sorted(nodes - catalog)
    ] + [
        f"module {module} is catalogued but never appears in the DAG"
        for module in sorted(catalog - nodes)
    ]


# --- profile (conformance-slice) consistency gate --------------------------


def parse_profile_claim(claim_markdown: str) -> dict:
    """Return the ``capabilities`` of the canonical slice ``describe`` claim.

    The claim is the single source of truth for the ``slice-mvp-1`` Conformance
    Slice: a fenced ```` ```json ```` block under the ``## First-implementation
    Conformance Slice`` heading of ``slices.md``. This parses the first such
    block, ``json.loads`` it, and returns its ``capabilities`` object.
    """
    lines = claim_markdown.splitlines()
    in_section = False
    fence_lines: list[str] | None = None
    block: str | None = None
    for line in lines:
        heading = re.match(r"^##\s+(.*?)\s*$", line)
        if heading:
            # Any "## " heading ends the slice section (the json fence sits
            # directly under the slice heading, not under a deeper heading).
            in_section = heading.group(1).strip().lower() == _SLICE_HEADING
            continue
        if not in_section:
            continue
        if fence_lines is None:
            if line.strip() == "```json":
                fence_lines = []
            continue
        if line.strip() == "```":
            block = "\n".join(fence_lines)
            break
        fence_lines.append(line)

    if block is None:
        raise DepGraphFailure(
            "no ```json slice claim found under the "
            "'## First-implementation Conformance Slice' heading of slices.md"
        )
    try:
        claim = json.loads(block)
    except json.JSONDecodeError as exc:
        raise DepGraphFailure(f"slice claim is not valid JSON: {exc}") from exc
    capabilities = claim.get("capabilities")
    if not isinstance(capabilities, dict):
        raise DepGraphFailure("slice claim has no 'capabilities' object")
    return capabilities


def _case_shape(doc: dict) -> str | None:
    """Detect the case shape from the present discriminating keys.

    Mirrors the ``oneOf`` discrimination in ``compatibility-case.schema.json`` and
    the ``is_*`` properties of ``Case``; there is no literal ``shape`` field. Order
    matters — the more specific shapes are checked before ``read``. Returns one of
    ``read`` / ``writeSequence`` / ``scenario`` / ``conflict`` / ``coherence`` /
    ``error`` / ``concurrencySuccess`` / ``boundary``, or ``None`` if the document
    matches no known shape.
    """
    if "errorClass" in doc:
        return "error"
    # A concurrency choreography with NO `errorClass` is the concurrency-success shape
    # (behavioral read-lock: m-read-lock-007/m-read-lock-008). Checked AFTER `errorClass` so an
    # error/concurrency case (m-read-lock-006) still resolves to `error`.
    if "concurrency" in doc:
        return "concurrencySuccess"
    if "coherence" in doc:
        return "coherence"
    if "scenario" in doc:
        return "scenario"
    if "writeSequence" in doc:
        return "writeSequence"
    if "expectedAffectedRows" in doc or "attempts" in doc:
        return "conflict"
    if "boundary" in doc:
        return "boundary"
    if "operation" in doc:
        return "read"
    return None


def _has_postgres_golden(doc: dict, shape: str) -> bool:
    """Whether a case carries Postgres golden SQL, shape-aware.

    read / writeSequence / conflict carry golden SQL at the top level — except the
    ``attempts`` conflict form, whose golden SQL lives per attempt. scenario carries
    golden SQL per step. A case satisfies the gate when *some* Postgres golden is
    present where its shape puts it.
    """
    if isinstance(doc.get("goldenSql"), dict) and "postgres" in doc["goldenSql"]:
        return True
    if isinstance(doc.get("concurrency"), dict):
        for rnd in doc["concurrency"].get("rounds", []):
            if not isinstance(rnd, dict):
                continue
            for node in ("A", "B"):
                step = rnd.get(node)
                golden = step.get("goldenSql") if isinstance(step, dict) else None
                if isinstance(golden, dict) and "postgres" in golden:
                    return True
    if shape == "scenario":
        steps = doc.get("scenario", [])
    elif shape == "conflict":
        steps = doc.get("attempts", [])
    else:
        steps = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        golden = step.get("goldenSql")
        if isinstance(golden, dict) and "postgres" in golden:
            return True
    return False


def _slice_cases(compatibility_root: Path) -> list[tuple[Path, dict]]:
    """Load (path, doc) for every ``cases/`` fixture carrying the slice tag.

    Benchmarks are intentionally ignored — the slice is a subset of ``cases/``.
    """
    cases_dir = compatibility_root / "cases"
    tagged: list[tuple[Path, dict]] = []
    if not cases_dir.is_dir():
        return tagged
    paths = sorted(cases_dir.glob("**/*.yaml")) + sorted(cases_dir.glob("**/*.yml"))
    for path in sorted(set(paths)):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict):
            continue
        tags = [t for t in doc.get("tags", []) if isinstance(t, str)]
        if _SLICE_TAG in tags:
            tagged.append((path, doc))
    return tagged


def profile_errors(claim_markdown: str, compatibility_root: Path) -> list[str]:
    """Assert the tagged slice cases are consistent with the canonical claim.

    Parse the declared claim, scan ``cases/``, diff, and return one error per
    inconsistency (empty == consistent). First, the claim must select exactly
    ``caseTags.include: ["slice-mvp-1"]``; then the gate checks both directions:

    * **forward (completeness)** — every module the claim lists has at least one
      tagged case carrying that module tag;
    * **reverse (no drift), per tagged case** — its shape is in the claim's
      ``caseShapes``; every module slug tag on it is in the claim's ``modules``; it
      carries a Postgres golden (shape-aware); and if the claim lists
      ``caseTags.exclude``, the case carries none of those tags.
    """
    try:
        capabilities = parse_profile_claim(claim_markdown)
    except DepGraphFailure as exc:
        return [str(exc)]

    errors: list[str] = []
    claim_modules = {m for m in capabilities.get("modules", []) if isinstance(m, str)}
    claim_shapes = {s for s in capabilities.get("caseShapes", []) if isinstance(s, str)}
    case_tags = capabilities.get("caseTags")
    if not isinstance(case_tags, dict):
        errors.append(f"slice claim must declare caseTags.include exactly [{_SLICE_TAG!r}]")
        case_tags = {}
    raw_include = case_tags.get("include")
    if raw_include != [_SLICE_TAG]:
        errors.append(
            f"slice claim caseTags.include must be exactly [{_SLICE_TAG!r}], got {raw_include!r}"
        )
    claim_exclude = {t for t in case_tags.get("exclude", []) if isinstance(t, str)}

    tagged = _slice_cases(compatibility_root)

    # forward: every claimed module is carried by at least one tagged case.
    covered_modules: set[str] = set()
    for _path, doc in tagged:
        for tag in doc.get("tags", []):
            if isinstance(tag, str) and _MODULE_RE.match(tag):
                covered_modules.add(tag)
    for module in sorted(claim_modules):
        if module not in covered_modules:
            errors.append(f"slice claims module {module!r} but no tagged case carries it")

    # reverse: every tagged case stays inside the claim.
    for path, doc in tagged:
        name = path.name
        shape = _case_shape(doc)
        if shape is None:
            errors.append(f"{name}: tagged case has no recognizable shape")
        elif shape not in claim_shapes:
            errors.append(
                f"{name}: shape {shape!r} is outside the slice claim "
                f"(allowed: {sorted(claim_shapes)})"
            )

        case_tags_list = [t for t in doc.get("tags", []) if isinstance(t, str)]
        for tag in case_tags_list:
            if _MODULE_RE.match(tag) and tag not in claim_modules:
                errors.append(f"{name}: carries module tag {tag!r} not in the slice claim")

        # An api-conformance-lane case (every boundary case, plus the read-lock
        # matrix reads) is NOT executed by the harness, so it need not carry a
        # Postgres golden — its observable is proven by the language's API
        # Conformance Suite. Harness-lane cases still must carry one.
        if (
            shape is not None
            and doc.get("lane") != "api-conformance"
            and not _has_postgres_golden(doc, shape)
        ):
            errors.append(f"{name}: tagged case has no Postgres golden SQL")

        if claim_exclude:
            offending = sorted(set(case_tags_list) & claim_exclude)
            if offending:
                errors.append(f"{name}: carries excluded slice tag(s) {offending}")

    return errors


def run_dag_check(spec_path: Path) -> int:
    markdown = spec_path.read_text(encoding="utf-8")
    errors = check(markdown)
    if errors:
        print(
            f"dependency-graph check FAILED ({len(errors)} problem(s)):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    edges = parse_edges(markdown)
    modules = sorted({m for edge in edges for m in edge})
    print(
        f"dependency-graph OK: DAG with legal directions "
        f"({len(modules)} modules, {len(edges)} edges)"
    )
    return 0


def run_coverage(spec_dir: Path, compatibility_root: Path) -> int:
    graph_path = spec_dir / "modules.md"
    if not graph_path.is_file():
        print(f"not a file: {graph_path}", file=sys.stderr)
        return 2
    if not compatibility_root.is_dir():
        print(f"not a directory: {compatibility_root}", file=sys.stderr)
        return 2

    # The coverage gate runs ON TOP OF the DAG check.
    dag_rc = run_dag_check(graph_path)

    modules_markdown = graph_path.read_text(encoding="utf-8")
    errors = catalog_graph_consistency_errors(modules_markdown)
    errors += coverage_errors(modules_markdown, compatibility_root)
    errors += active_deferred_edge_errors(modules_markdown)
    # A catalog parse failure surfaces from each gate; collapse the repeats.
    errors = list(dict.fromkeys(errors))
    if errors:
        print(
            f"coverage gate FAILED ({len(errors)} problem(s)):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1 if dag_rc == 0 else dag_rc

    catalog = parse_catalog(modules_markdown)
    gated = gated_modules(catalog)
    print(
        f"coverage gate OK: every active/cases module is covered "
        f"({len(gated)} of {len(catalog)} catalog module(s)); "
        f"no active module depends on a deferred one"
    )
    return dag_rc


def run_profile(spec_dir: Path, compatibility_root: Path) -> int:
    claim_path = spec_dir / "slices.md"
    if not claim_path.is_file():
        print(f"not a file: {claim_path}", file=sys.stderr)
        return 2
    if not compatibility_root.is_dir():
        print(f"not a directory: {compatibility_root}", file=sys.stderr)
        return 2

    claim_markdown = claim_path.read_text(encoding="utf-8")
    errors = profile_errors(claim_markdown, compatibility_root)
    if errors:
        print(
            f"profile gate FAILED ({len(errors)} inconsistency(ies) for {_SLICE_TAG!r}):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    tagged = _slice_cases(compatibility_root)
    print(
        f"profile gate OK: the {_SLICE_TAG!r} slice is consistent with its claim "
        f"({len(tagged)} tagged case(s))"
    )
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--coverage":
        rest = argv[1:]
        if len(rest) != 2:
            print(
                "usage: python -m reference_harness.dep_graph_check --coverage "
                "<spec-dir> <compatibility-dir>",
                file=sys.stderr,
            )
            return 2
        return run_coverage(Path(rest[0]), Path(rest[1]))

    if argv and argv[0] == "--profile":
        rest = argv[1:]
        if len(rest) != 2:
            print(
                "usage: python -m reference_harness.dep_graph_check --profile "
                "<spec-dir> <compatibility-dir>",
                file=sys.stderr,
            )
            return 2
        return run_profile(Path(rest[0]), Path(rest[1]))

    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.dep_graph_check "
            "<modules.md>\n"
            "   or: python -m reference_harness.dep_graph_check --coverage "
            "<spec-dir> <compatibility-dir>\n"
            "   or: python -m reference_harness.dep_graph_check --profile "
            "<spec-dir> <compatibility-dir>",
            file=sys.stderr,
        )
        return 2
    spec_path = Path(argv[0])
    if not spec_path.is_file():
        print(f"not a file: {spec_path}", file=sys.stderr)
        return 2
    return run_dag_check(spec_path)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
