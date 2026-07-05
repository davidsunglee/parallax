"""Parse the normative module-dependency graph and assert it is a legal DAG.

Three modes:

* **DAG check** (default) — validate the graph in ``dependency-graph.md``::

      uv run python -m reference_harness.dep_graph_check core/spec/dependency-graph.md

* **Coverage gate** (``--coverage``) — the DAG check **plus** assert every
  in-scope module (MVP / fast-follow / definitely-do) has at least one
  compatibility fixture tagged to it::

      uv run python -m reference_harness.dep_graph_check --coverage core/spec core/compatibility

* **Profile gate** (``--profile``) — assert the ``slice-mvp-1``
  Conformance Slice's tagged cases are consistent with its canonical ``describe``
  claim embedded in ``scope-and-tiers.md`` (every claimed module covered, no stray
  module tag, every shape in claim, every tagged case Postgres-golden)::

      uv run python -m reference_harness.dep_graph_check --profile core/spec core/compatibility

The machine-readable source of truth for the graph is the fenced
```` ```dependency-graph ```` block in ``dependency-graph.md``. Each line is an
edge ``A --> B`` meaning "A depends on B". The DAG check asserts:

* every edge names two recognized modules (``M0`` and up; ``M6`` is intentionally absent);
* the graph is a **directed acyclic graph** (no cycles);
* edge direction is **legal** — an edge must not point "upward" against the
  layering. We derive a topological level per module from the declared edges and
  require every edge to go from a higher level to a strictly lower one, which is
  exactly the acyclicity property surfaced as a direction error.

The **coverage gate** (Phase 12) reads the in-scope tiers from
``scope-and-tiers.md`` and asserts each in-scope module has fixture coverage,
measured against the ``tags`` of every fixture under ``core/compatibility/``
(cases *and* benchmarks). The might-do / won't-do tiers — including the RFC-2119
MAY temporal mutations — are excluded from the gate by construction (they are not
listed under the in-scope tier headings).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

_FENCE_RE = re.compile(r"```dependency-graph\n(.*?)```", re.DOTALL)
_EDGE_RE = re.compile(r"^\s*(M\d+)\s*-->\s*(M\d+)\s*$")
_MODULE_RE = re.compile(r"^M\d+$")
_MODULE_TOKEN_RE = re.compile(r"\bM\d+\b")
_MODULE_TAG_RE = re.compile(r"^m\d+$")

# The three in-scope tier headings in scope-and-tiers.md, normalized to lower case.
# Any module mentioned under one of these (until the next "### " heading) is
# treated as in-scope for the coverage gate.
_IN_SCOPE_TIERS = ("mvp", "fast-follow", "definitely-do")

# The named conformance slice the profile gate enforces. The slice is selected by
# this single tag on each included case (see scope-and-tiers.md); the canonical
# describe claim that declares its boundaries lives in the same file.
_SLICE_TAG = "slice-mvp-1"

# The heading under which the canonical slice claim is embedded in
# scope-and-tiers.md, normalized to lower case (the json fence right after it is the
# single source of truth for the claim).
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


# --- coverage gate ---------------------------------------------------------


def parse_in_scope_modules(scope_markdown: str) -> set[str]:
    """Return the set of in-scope module tokens (``M0`` and up), read from the
    three in-scope tier sections of ``scope-and-tiers.md``.

    A module is in scope iff it is mentioned under an ``MVP`` / ``Fast-follow`` /
    ``Definitely-do`` ``### `` heading (until the next ``### `` heading).
    Cross-process cache coherence is ``M14`` and is picked up by the normal
    ``M\\d+`` token scan.
    """
    in_scope: set[str] = set()
    current_in_scope = False
    for line in scope_markdown.splitlines():
        heading = re.match(r"^###\s+(.*?)\s*$", line)
        if heading:
            title = heading.group(1).strip().lower()
            current_in_scope = title in _IN_SCOPE_TIERS
            continue
        if not current_in_scope:
            continue
        for token in _MODULE_TOKEN_RE.findall(line):
            in_scope.add(token)
    if not in_scope:
        raise DepGraphFailure(
            "no in-scope modules found under the MVP / fast-follow / definitely-do "
            "headings of scope-and-tiers.md"
        )
    return in_scope


def _fixture_tags(compatibility_root: Path) -> set[str]:
    """Collect the lower-cased ``tags`` of every fixture under compatibility/.

    Scans both ``cases/`` and ``benchmarks/`` (M13 fixtures cover M13). A fixture
    that does not parse to a mapping, or that carries no ``tags``, contributes
    nothing.
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


def coverage_errors(scope_markdown: str, compatibility_root: Path) -> list[str]:
    """Assert every in-scope module has >=1 fixture tagged to it.

    Returns a list of error strings (empty == fully covered).
    """
    try:
        in_scope = parse_in_scope_modules(scope_markdown)
    except DepGraphFailure as exc:
        return [str(exc)]

    fixture_tags = _fixture_tags(compatibility_root)
    if not fixture_tags:
        return [f"no fixture tags discovered under {compatibility_root}"]

    uncovered = sorted(module for module in in_scope if module.lower() not in fixture_tags)
    return [
        f"in-scope module {module} has no fixture tagged to it "
        f"(expected at least one fixture with tag {module.lower()!r})"
        for module in uncovered
    ]


# --- profile (conformance-slice) consistency gate --------------------------


def parse_profile_claim(scope_markdown: str) -> dict:
    """Return the ``capabilities`` of the canonical slice ``describe`` claim.

    The claim is the single source of truth for the ``slice-mvp-1``
    Conformance Slice: a fenced ```` ```json ```` block embedded under the
    ``## First-implementation Conformance Slice`` heading of ``scope-and-tiers.md``
    (no new file, no schema change). This parses the first such fenced block,
    ``json.loads`` it, and returns its ``capabilities`` object
    (``modules`` / ``dialects`` / ``caseShapes`` / ``caseTags``).
    """
    lines = scope_markdown.splitlines()
    in_section = False
    fence_lines: list[str] | None = None
    block: str | None = None
    for line in lines:
        heading = re.match(r"^##\s+(.*?)\s*$", line)
        if heading:
            # Any "## " heading ends the slice section (the json fence sits
            # directly under the slice heading, not under a tier ### heading).
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
            "'## First-implementation Conformance Slice' heading of scope-and-tiers.md"
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
    # (M8 behavioral read-lock: 0729/0734). Checked AFTER `errorClass` so an
    # error/concurrency case (0728) still resolves to `error`.
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


def profile_errors(scope_markdown: str, compatibility_root: Path) -> list[str]:
    """Assert the tagged slice cases are consistent with the canonical claim.

    Mirrors ``coverage_errors``: parse a declared set, scan ``cases/``, diff, and
    return one error per inconsistency (empty == consistent). First, the canonical
    claim must select exactly ``caseTags.include: ["slice-mvp-1"]``;
    then the gate checks both directions:

    * **forward (completeness)** — every module the claim lists has at least one
      tagged case carrying that module tag;
    * **reverse (no drift), per tagged case** — its shape is in the claim's
      ``caseShapes``; every ``m\\d+`` tag on it is in the claim's ``modules``; it
      carries a Postgres golden (shape-aware); and if the claim lists
      ``caseTags.exclude``, the case carries none of those tags.
    """
    try:
        capabilities = parse_profile_claim(scope_markdown)
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
            if isinstance(tag, str) and _MODULE_TAG_RE.match(tag):
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
            if _MODULE_TAG_RE.match(tag) and tag not in claim_modules:
                errors.append(f"{name}: carries module tag {tag!r} not in the slice claim")

        # An api-conformance-lane case (every boundary case, plus the read-lock
        # matrix reads) is NOT executed by the M12 harness, so it need not carry a
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
    graph_path = spec_dir / "dependency-graph.md"
    scope_path = spec_dir / "scope-and-tiers.md"
    for required in (graph_path, scope_path):
        if not required.is_file():
            print(f"not a file: {required}", file=sys.stderr)
            return 2
    if not compatibility_root.is_dir():
        print(f"not a directory: {compatibility_root}", file=sys.stderr)
        return 2

    # The coverage gate runs ON TOP OF the DAG check.
    dag_rc = run_dag_check(graph_path)

    scope_markdown = scope_path.read_text(encoding="utf-8")
    errors = coverage_errors(scope_markdown, compatibility_root)
    if errors:
        print(
            f"coverage gate FAILED ({len(errors)} uncovered module(s)):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1 if dag_rc == 0 else dag_rc

    in_scope = parse_in_scope_modules(scope_markdown)
    print(
        f"coverage gate OK: every in-scope module is covered "
        f"({len(in_scope)} module(s) across MVP / fast-follow / definitely-do)"
    )
    return dag_rc


def run_profile(spec_dir: Path, compatibility_root: Path) -> int:
    scope_path = spec_dir / "scope-and-tiers.md"
    if not scope_path.is_file():
        print(f"not a file: {scope_path}", file=sys.stderr)
        return 2
    if not compatibility_root.is_dir():
        print(f"not a directory: {compatibility_root}", file=sys.stderr)
        return 2

    scope_markdown = scope_path.read_text(encoding="utf-8")
    errors = profile_errors(scope_markdown, compatibility_root)
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
            "<dependency-graph.md>\n"
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
