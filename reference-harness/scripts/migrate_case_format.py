"""Pass-1 codemod: restructure the compatibility corpus to the grouped layout.

TEMPORARY tooling (COR-23) — committed for review, deleted in the final cleanup
commit. It rewrites every case under ``cases/**`` and every benchmark under
``benchmarks/**`` from the flat top-level layout (positionally-paired
``goldenSql`` / ``binds``) to the grouped ``given`` / ``when`` / ``then`` layout
with statement-first ``{sql, binds}`` entries and an explicit ``shape``
discriminator, per ``core/schemas/compatibility-case.schema.json``.

Two mechanical guarantees make the restructure safe to trust:

* **Per-file semantic self-check** — the old file and the emitted file are both
  parsed with ``yaml.safe_load`` (the executable definition the harness uses) and
  reduced to a *semantic projection* (statements per dialect, binds per statement
  read through both the old positional pairing and the new structural read,
  expected structures, shape, tags, and every non-SQL step field). The two
  projections MUST be equal, or the file is rejected and the script exits nonzero.
* **Schema validation** — every emitted document is validated against the new
  case schema; a document that does not validate rejects the whole run.

Usage::

    # Phase 1 — prove out-of-place, corpus untouched:
    uv run python scripts/migrate_case_format.py --out-dir /tmp/migrated ../core/compatibility

    # Phase 2 — rewrite in place:
    uv run python scripts/migrate_case_format.py ../core/compatibility

The codemod uses ``ruamel.yaml`` round-trip parsing so scalar representations
(``100.00``, quoted timestamps, the bare ``infinity`` sentinel) survive verbatim;
it reuses the original value nodes wherever a value is unchanged, so only the
grouping and the statement entries are freshly built. Every full-line and inline
comment in the source is hoisted verbatim into the emitted file's header block
(the Phase-6 editorial pass rewrites those headers).
"""

from __future__ import annotations

import copy
import json
import re
import sys
from io import StringIO
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

MAX_LINE = 120  # the fits-on-a-line row-style budget (~120 chars)

# --- canonical member order within each group ------------------------------

_GIVEN_ORDER = ["fixtures", "apply", "fault"]
_WHEN_ORDER = [
    "uow",
    "operation",
    "equivalentEncodings",
    "writeSequence",
    "scenario",
    "coherence",
    "concurrency",
    "boundary",
    "attempts",
    "write",
    "at",
    "observedInZ",
]
_THEN_ORDER = [
    "statements",
    "referenceSql",
    "rows",
    "graph",
    "affectedRows",
    "tableState",
    "errorClass",
    "nativeCode",
    "outcome",
    "roundTrips",
    "tolerance",
]

# Old top-level field -> new `when` / `then` member name. Fields not listed here
# stay top-level (model, tags, lane) or are handled specially (goldenSql/binds,
# loadFixtures/inject, precondition/preconditionBinds).
_WHEN_FIELDS = {
    "uow": "uow",
    "operation": "operation",
    "equivalentEncodings": "equivalentEncodings",
    "writeSequence": "writeSequence",
    "scenario": "scenario",
    "coherence": "coherence",
    "concurrency": "concurrency",
    "boundary": "boundary",
    "attempts": "attempts",
    "write": "write",
    "at": "at",
    "observedInZ": "observedInZ",
}
_THEN_FIELDS = {
    "referenceSql": "referenceSql",
    "expectedRows": "rows",
    "expectedGraph": "graph",
    "expectedAffectedRows": "affectedRows",
    "expectedTableState": "tableState",
    "errorClass": "errorClass",
    "expectedNativeCode": "nativeCode",
    "expect": "outcome",
    "roundTrips": "roundTrips",
    "tolerance": "tolerance",
}

# Step forms whose per-step SQL migrates goldenSql + binds -> statements. Their
# other internal fields ("note", "find", "expectRows", "observeRows", ...) are
# kept verbatim, so only the SQL representation changes.
_SQL_STEP_LISTS = ("scenario", "coherence", "attempts")


class MigrationError(Exception):
    """A file could not be migrated safely (self-check or schema failure)."""


# --- ruamel setup ----------------------------------------------------------


def _make_yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    return y


_MEASURE = _make_yaml()
_MEASURE.width = 100_000


# --- shape derivation (mirrors dep_graph_check._case_shape priority order) --


def derive_shape(doc: dict[str, Any]) -> str:
    """Derive the shape of an OLD-layout doc via the exact discriminator order."""
    if "errorClass" in doc:
        return "error"
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
    raise MigrationError("document matches no known shape")


# --- positional bind pairing (mirrors the harness helpers) -----------------


def binds_for_statement(binds: Any, index: int) -> list[Any]:
    """Pair binds to statement *index* the way ``_binds_for_statement`` does."""
    if not binds:
        return []
    if isinstance(binds[0], list):  # list-of-lists -> one bind list per statement
        return list(binds[index]) if index < len(binds) else []
    return list(binds) if index == 0 else []  # flat list -> belongs to statement 0


def _statements_per_dialect(golden: dict[str, Any]) -> dict[str, list[str]]:
    """Normalize a goldenSql map to ``{dialect: [statement, ...]}``."""
    per: dict[str, list[str]] = {}
    for dialect, value in golden.items():
        per[dialect] = [value] if isinstance(value, str) else list(value)
    return per


# --- statement-entry construction (reuses original scalar nodes) -----------


def _golden_entries(golden: Any, binds: Any, where: str) -> CommentedSeq:
    """Zip a goldenSql map + positional binds into ``[{sql, binds}]`` entries."""
    if not isinstance(golden, dict):
        raise MigrationError(f"{where}: goldenSql is not a dialect map")
    per = _statements_per_dialect(golden)
    counts = {dialect: len(stmts) for dialect, stmts in per.items()}
    if len(set(counts.values())) != 1:
        raise MigrationError(
            f"{where}: cross-dialect statement-count mismatch {counts} — refusing to zip binds"
        )
    n = next(iter(counts.values()))
    dialects = list(golden.keys())  # preserve authored dialect order (postgres first)
    entries = CommentedSeq()
    for index in range(n):
        entry = CommentedMap()
        sql_map = CommentedMap()
        for dialect in dialects:
            sql_map[dialect] = per[dialect][index]  # reuse the original scalar node
        entry["sql"] = sql_map
        stmt_binds = binds_for_statement(binds, index)
        if stmt_binds:
            # Reuse the authored bind node (preserves flow style / scalar formats).
            entry["binds"] = binds[index] if isinstance(binds[0], list) else binds
        entries.append(entry)
    return entries


def _naive_entries(precondition: Any, precond_binds: Any) -> CommentedSeq:
    """Zip a dialect-agnostic precondition + binds into naive ``{sql, binds}`` entries."""
    statements = [precondition] if isinstance(precondition, str) else list(precondition)
    entries = CommentedSeq()
    for index, statement in enumerate(statements):
        entry = CommentedMap()
        entry["sql"] = statement  # plain-string sql (reuse scalar node)
        stmt_binds = binds_for_statement(precond_binds, index)
        if stmt_binds:
            entry["binds"] = (
                precond_binds[index] if isinstance(precond_binds[0], list) else precond_binds
            )
        entries.append(entry)
    return entries


def _rebuild_sql_step(step: CommentedMap, where: str) -> CommentedMap:
    """Swap a step's ``goldenSql`` + ``binds`` for a ``statements`` list, in place order.

    Every other field is copied verbatim at its authored position, so only the
    SQL representation changes ("otherwise keep the existing internal structure").
    """
    golden = step.get("goldenSql")
    binds = step.get("binds")
    new = CommentedMap()
    for key, value in step.items():
        if key == "goldenSql":
            new["statements"] = _golden_entries(golden, binds, where)
        elif key == "binds":
            continue  # folded into statements
        else:
            new[key] = value
    return new


# --- building the grouped document -----------------------------------------


def _ordered(members: dict[str, Any], order: list[str]) -> CommentedMap:
    out = CommentedMap()
    for name in order:
        if name in members:
            out[name] = members[name]
    for name, value in members.items():  # any straggler (should not happen) stays last
        if name not in out:
            out[name] = value
    return out


def migrate_case(raw: CommentedMap, name: str) -> CommentedMap:
    """Restructure one OLD-layout case into the grouped layout."""
    shape = derive_shape(raw)
    new = CommentedMap()
    new["model"] = raw["model"]
    new["tags"] = raw["tags"]
    if "lane" in raw:
        new["lane"] = raw["lane"]
    new["shape"] = shape

    given: dict[str, Any] = {}
    when: dict[str, Any] = {}
    then: dict[str, Any] = {}

    # given -----------------------------------------------------------------
    if "loadFixtures" in raw:
        given["fixtures"] = raw["loadFixtures"]
    if "inject" in raw:
        given["fault"] = raw["inject"]
    if "precondition" in raw:
        given["apply"] = _naive_entries(raw["precondition"], raw.get("preconditionBinds"))

    # when ------------------------------------------------------------------
    for old_key, new_key in _WHEN_FIELDS.items():
        if old_key not in raw:
            continue
        if old_key in _SQL_STEP_LISTS:
            steps = CommentedSeq()
            for index, step in enumerate(raw[old_key]):
                steps.append(_rebuild_sql_step(step, f"{name}: {old_key}[{index}]"))
            when[new_key] = steps
        elif old_key == "concurrency":
            when[new_key] = _rebuild_concurrency(raw[old_key], name)
        else:
            when[new_key] = raw[old_key]

    # then ------------------------------------------------------------------
    if "goldenSql" in raw:
        then["statements"] = _golden_entries(
            raw["goldenSql"], raw.get("binds"), f"{name}: goldenSql"
        )
    for old_key, new_key in _THEN_FIELDS.items():
        if old_key in raw:
            then[new_key] = raw[old_key]

    if given:
        new["given"] = _ordered(given, _GIVEN_ORDER)
    if when:
        new["when"] = _ordered(when, _WHEN_ORDER)
    if then:
        new["then"] = _ordered(then, _THEN_ORDER)

    _strip_comments(new)
    _style_document(new)
    return new


def _rebuild_concurrency(concurrency: CommentedMap, name: str) -> CommentedMap:
    """Rebuild a concurrency choreography, migrating each node step's SQL."""
    new = CommentedMap()
    rounds = CommentedSeq()
    for r_index, rnd in enumerate(concurrency.get("rounds", [])):
        new_round = CommentedMap()
        for node in ("A", "B"):
            if node in rnd:
                new_round[node] = _rebuild_sql_step(
                    rnd[node], f"{name}: concurrency.rounds[{r_index}].{node}"
                )
                new_round[node].fa.set_block_style()
        rounds.append(new_round)
    new["rounds"] = rounds
    for key, value in concurrency.items():
        if key != "rounds":
            new[key] = value
    return new


def migrate_benchmark(raw: CommentedMap, name: str) -> CommentedMap:
    """Migrate a benchmark fixture's ``workloads[]`` goldenSql/binds to statements."""
    new = CommentedMap()
    for key, value in raw.items():
        if key == "workloads":
            workloads = CommentedSeq()
            for index, workload in enumerate(value):
                if isinstance(workload, dict) and "goldenSql" in workload:
                    workloads.append(_rebuild_sql_step(workload, f"{name}: workloads[{index}]"))
                else:
                    workloads.append(workload)  # cache-hit workload lists no SQL
            new[key] = workloads
        else:
            new[key] = value
    _strip_comments(new)
    _style_document(new)
    return new


# --- comment handling ------------------------------------------------------


def _strip_comments(node: Any) -> None:
    """Recursively drop every comment attached to a ruamel node.

    Comments are hoisted to the header from the raw source text instead, so the
    emitted body carries no inline / mid-document comment metadata.
    """
    if isinstance(node, (CommentedMap, CommentedSeq)):
        try:
            node.ca.comment = None
            node.ca.items.clear()
            node.ca.end = []
        except AttributeError:
            pass
    if isinstance(node, CommentedMap):
        for value in node.values():
            _strip_comments(value)
    elif isinstance(node, CommentedSeq):
        for value in node:
            _strip_comments(value)


def _comment_start(line: str) -> int:
    """Index of the first quote-safe ``#`` in *line*, or -1 if none."""
    in_single = in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if index == 0 or line[index - 1].isspace():
                return index
    return -1


def extract_header(source: str) -> str:
    """Collect every full-line and inline comment from *source*, in file order.

    Full-line comments are left-stripped to column 0; inline comments keep their
    ``#...`` text. The result is the emitted file's header block (Phase 6 rewrites
    these headers to the house style).
    """
    comments: list[str] = []
    for line in source.splitlines():
        start = _comment_start(line)
        if start < 0:
            continue
        comments.append(line[start:].rstrip())
    return "\n".join(comments)


# --- row-style rule (fits-on-a-line -> flow, else block) -------------------


def _set_flow_deep(node: Any) -> None:
    if isinstance(node, CommentedMap):
        node.fa.set_flow_style()
        for value in node.values():
            _set_flow_deep(value)
    elif isinstance(node, CommentedSeq):
        node.fa.set_flow_style()
        for value in node:
            _set_flow_deep(value)


def _flow_width(node: Any) -> int:
    """The single-line width of *node* rendered entirely in flow style.

    Measured against the padded rendering (`{ a: 1 }`) so the fits-on-a-line rule
    is applied to the width the file will actually carry.
    """
    trial = copy.deepcopy(node)
    _set_flow_deep(trial)
    buffer = StringIO()
    _MEASURE.dump(trial, buffer)
    return len(_pad_flow_braces(buffer.getvalue().splitlines()[0]))


def _is_scalar(value: Any) -> bool:
    return not isinstance(value, (CommentedMap, CommentedSeq, dict, list))


def _style_row(node: Any, content_col: int) -> None:
    """Apply the fits-on-a-line rule to a row and recurse into nested row lists."""
    if isinstance(node, CommentedMap):
        if all(_is_scalar(value) for value in node.values()):
            if content_col + _flow_width(node) <= MAX_LINE:
                _set_flow_deep(node)
            else:
                node.fa.set_block_style()
        else:
            node.fa.set_block_style()
            for key, value in node.items():
                # a relationship key at content_col owns a block child at +2 / seq +4
                if isinstance(value, CommentedSeq):
                    _style_row_list(value, content_col + len(str(key)) + 6)
                elif isinstance(value, CommentedMap):
                    _style_row(value, content_col + len(str(key)) + 2)
    elif isinstance(node, CommentedSeq):
        _style_row_list(node, content_col)


def _style_row_list(seq: CommentedSeq, content_col: int) -> None:
    for item in seq:
        _style_row(item, content_col)


def _style_document(doc: CommentedMap) -> None:
    """Style statement entries and apply the row-style rule to every row list."""
    then = doc.get("then")
    if isinstance(then, CommentedMap):
        if isinstance(then.get("rows"), CommentedSeq):
            _style_row_list(then["rows"], 6)
        if isinstance(then.get("tableState"), CommentedMap):
            for rows in then["tableState"].values():
                if isinstance(rows, CommentedSeq):
                    _style_row_list(rows, 8)
        if isinstance(then.get("graph"), CommentedMap):
            for rows in then["graph"].values():
                if isinstance(rows, CommentedSeq):
                    _style_row_list(rows, 8)

    when = doc.get("when")
    if isinstance(when, CommentedMap):
        _style_step_rows(when.get("scenario"), "expectRows", 10)
        _style_step_rows(when.get("coherence"), "observeRows", 10)
        _style_concurrency_rows(when.get("concurrency"))


def _style_step_rows(steps: Any, field: str, content_col: int) -> None:
    if not isinstance(steps, CommentedSeq):
        return
    for step in steps:
        if isinstance(step, CommentedMap) and isinstance(step.get(field), CommentedSeq):
            _style_row_list(step[field], content_col)


def _style_concurrency_rows(concurrency: Any) -> None:
    if not isinstance(concurrency, CommentedMap):
        return
    for rnd in concurrency.get("rounds", []):
        if not isinstance(rnd, CommentedMap):
            continue
        for node in ("A", "B"):
            step = rnd.get(node)
            if isinstance(step, CommentedMap) and isinstance(step.get("expectRows"), CommentedSeq):
                _style_row_list(step["expectRows"], 14)


# --- semantic self-check ---------------------------------------------------


def _sql_projection_old(golden: Any, binds: Any) -> dict[str, Any]:
    if not isinstance(golden, dict):
        return {"per": {}, "binds": []}
    per = _statements_per_dialect(golden)
    n = len(next(iter(per.values())))
    return {"per": per, "binds": [binds_for_statement(binds, i) for i in range(n)]}


def _sql_projection_new(statements: Any) -> dict[str, Any]:
    if not isinstance(statements, list):
        return {"per": {}, "binds": []}
    dialects: list[str] = []
    for entry in statements:
        for dialect in entry.get("sql", {}):
            if dialect not in dialects:
                dialects.append(dialect)
    per = {d: [e["sql"][d] for e in statements if d in e.get("sql", {})] for d in dialects}
    return {"per": per, "binds": [list(e.get("binds", [])) for e in statements]}


def _step_meta(step: dict[str, Any], sql_keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: v for k, v in step.items() if k not in sql_keys}


def _project_step_list_old(steps: Any) -> list[dict[str, Any]]:
    result = []
    for step in steps or []:
        result.append(
            {
                "sql": _sql_projection_old(step.get("goldenSql"), step.get("binds")),
                "meta": _step_meta(step, ("goldenSql", "binds")),
            }
        )
    return result


def _project_step_list_new(steps: Any) -> list[dict[str, Any]]:
    result = []
    for step in steps or []:
        result.append(
            {
                "sql": _sql_projection_new(step.get("statements")),
                "meta": _step_meta(step, ("statements",)),
            }
        )
    return result


def _project_concurrency_old(concurrency: Any) -> list[dict[str, Any]]:
    result = []
    for rnd in (concurrency or {}).get("rounds", []):
        entry = {}
        for node in ("A", "B"):
            if node in rnd:
                step = rnd[node]
                entry[node] = {
                    "sql": _sql_projection_old(step.get("goldenSql"), step.get("binds")),
                    "meta": _step_meta(step, ("goldenSql", "binds")),
                }
        result.append(entry)
    return result


def _project_concurrency_new(concurrency: Any) -> list[dict[str, Any]]:
    result = []
    for rnd in (concurrency or {}).get("rounds", []):
        entry = {}
        for node in ("A", "B"):
            if node in rnd:
                step = rnd[node]
                entry[node] = {
                    "sql": _sql_projection_new(step.get("statements")),
                    "meta": _step_meta(step, ("statements",)),
                }
        result.append(entry)
    return result


def project_old(doc: dict[str, Any]) -> dict[str, Any]:
    """The semantic projection read from an OLD-layout document."""
    precondition = doc.get("precondition")
    apply_statements = (
        ([precondition] if isinstance(precondition, str) else list(precondition))
        if precondition is not None
        else []
    )
    apply_binds = [
        binds_for_statement(doc.get("preconditionBinds"), i) for i in range(len(apply_statements))
    ]
    return {
        "shape": derive_shape(doc),
        "model": doc.get("model"),
        "tags": doc.get("tags"),
        "lane": doc.get("lane", "harness"),
        "top_sql": _sql_projection_old(doc.get("goldenSql"), doc.get("binds")),
        "referenceSql": doc.get("referenceSql"),
        "rows": doc.get("expectedRows"),
        "graph": doc.get("expectedGraph"),
        "tableState": doc.get("expectedTableState"),
        "affectedRows": doc.get("expectedAffectedRows"),
        "errorClass": doc.get("errorClass"),
        "nativeCode": doc.get("expectedNativeCode"),
        "outcome": doc.get("expect"),
        "roundTrips": doc.get("roundTrips"),
        "tolerance": doc.get("tolerance"),
        "operation": doc.get("operation"),
        "writeSequence": doc.get("writeSequence"),
        "equivalentEncodings": doc.get("equivalentEncodings"),
        "boundary": doc.get("boundary"),
        "uow": doc.get("uow"),
        "at": doc.get("at"),
        "observedInZ": doc.get("observedInZ"),
        "fixtures": doc.get("loadFixtures", False),
        "fault": doc.get("inject"),
        "apply": {"statements": apply_statements, "binds": apply_binds},
        "scenario": _project_step_list_old(doc.get("scenario")),
        "coherence": _project_step_list_old(doc.get("coherence")),
        "attempts": _project_step_list_old(doc.get("attempts")),
        "concurrency": _project_concurrency_old(doc.get("concurrency")),
    }


def project_new(doc: dict[str, Any]) -> dict[str, Any]:
    """The semantic projection read STRUCTURALLY from a NEW-layout document."""
    given = doc.get("given") or {}
    when = doc.get("when") or {}
    then = doc.get("then") or {}
    apply_entries = given.get("apply") or []
    return {
        "shape": doc.get("shape"),
        "model": doc.get("model"),
        "tags": doc.get("tags"),
        "lane": doc.get("lane", "harness"),
        "top_sql": _sql_projection_new(then.get("statements")),
        "referenceSql": then.get("referenceSql"),
        "rows": then.get("rows"),
        "graph": then.get("graph"),
        "tableState": then.get("tableState"),
        "affectedRows": then.get("affectedRows"),
        "errorClass": then.get("errorClass"),
        "nativeCode": then.get("nativeCode"),
        "outcome": then.get("outcome"),
        "roundTrips": then.get("roundTrips"),
        "tolerance": then.get("tolerance"),
        "operation": when.get("operation"),
        "writeSequence": when.get("writeSequence"),
        "equivalentEncodings": when.get("equivalentEncodings"),
        "boundary": when.get("boundary"),
        "uow": when.get("uow"),
        "at": when.get("at"),
        "observedInZ": when.get("observedInZ"),
        "fixtures": given.get("fixtures", False),
        "fault": given.get("fault"),
        "apply": {
            "statements": [e.get("sql") for e in apply_entries],
            "binds": [list(e.get("binds", [])) for e in apply_entries],
        },
        "scenario": _project_step_list_new(when.get("scenario")),
        "coherence": _project_step_list_new(when.get("coherence")),
        "attempts": _project_step_list_new(when.get("attempts")),
        "concurrency": _project_concurrency_new(when.get("concurrency")),
    }


def project_benchmark_old(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "top": {k: v for k, v in doc.items() if k != "workloads"},
        "workloads": [
            {
                "sql": _sql_projection_old(w.get("goldenSql"), w.get("binds")),
                "meta": _step_meta(w, ("goldenSql", "binds")),
            }
            for w in doc.get("workloads", [])
        ],
    }


def project_benchmark_new(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "top": {k: v for k, v in doc.items() if k != "workloads"},
        "workloads": [
            {
                "sql": _sql_projection_new(w.get("statements")),
                "meta": _step_meta(w, ("statements",)),
            }
            for w in doc.get("workloads", [])
        ],
    }


def _semantic_check(old_text: str, new_text: str, name: str, is_benchmark: bool) -> None:
    old_doc = yaml.safe_load(old_text)
    new_doc = yaml.safe_load(new_text)
    if is_benchmark:
        before = project_benchmark_old(old_doc)
        after = project_benchmark_new(new_doc)
    else:
        before = project_old(old_doc)
        after = project_new(new_doc)
    if before != after:
        diffs = [key for key in before if before[key] != after.get(key)]
        raise MigrationError(f"{name}: semantic self-check FAILED — differing keys: {diffs}")


# --- driver ----------------------------------------------------------------


def _schema_validator(compatibility_root: Path) -> Draft202012Validator:
    schema_path = compatibility_root.parent / "schemas" / "compatibility-case.schema.json"
    return Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))


def _pad_flow_braces(body: str) -> str:
    """Restore the corpus house style of inner-spaced flow maps (`{ a: 1 }`).

    ruamel emits flow mappings tight (`{a: 1}`) even on plain round-trip, but the
    corpus and the m-case-format docs author them spaced. Only flow-map braces are
    padded — flow sequences (`[1, 2]`) and the empty map (`{}`) are left untouched.
    The per-file semantic self-check re-parses the padded body, so any accidental
    edit of a scalar would fail loudly rather than slip through.
    """
    body = re.sub(r"\{(?!\})", "{ ", body)
    body = re.sub(r"(?<!\{)\}", " }", body)
    return body


def _render(doc: CommentedMap, header: str) -> str:
    yaml_rt = _make_yaml()
    buffer = StringIO()
    yaml_rt.dump(doc, buffer)
    body = _pad_flow_braces(buffer.getvalue())
    if header:
        return header + "\n" + body
    return body


def migrate_file(path: Path, is_benchmark: bool) -> tuple[str, CommentedMap]:
    source = path.read_text(encoding="utf-8")
    raw = _make_yaml().load(source)
    name = path.name
    new_doc = migrate_benchmark(raw, name) if is_benchmark else migrate_case(raw, name)
    header = extract_header(source)
    return _render(new_doc, header), new_doc


def run(compatibility_root: Path, out_dir: Path | None) -> int:
    validator = _schema_validator(compatibility_root)
    families = [("cases", False), ("benchmarks", True)]
    total = 0
    failures: list[str] = []
    for subdir, is_benchmark in families:
        root = compatibility_root / subdir
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")):
            total += 1
            try:
                new_text, new_doc = migrate_file(path, is_benchmark)
                if not is_benchmark:
                    errors = sorted(validator.iter_errors(new_doc), key=lambda e: list(e.path))
                    if errors:
                        loc = "/".join(str(p) for p in errors[0].absolute_path) or "<root>"
                        raise MigrationError(
                            f"{path.name}: emitted doc fails schema at {loc}: {errors[0].message}"
                        )
                _semantic_check(path.read_text(encoding="utf-8"), new_text, path.name, is_benchmark)
            except MigrationError as exc:
                failures.append(str(exc))
                continue

            if out_dir is not None:
                dest = out_dir / subdir / path.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(new_text, encoding="utf-8")
            else:
                path.write_text(new_text, encoding="utf-8")

    if failures:
        print(f"migration FAILED ({len(failures)} of {total} file(s)):", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    where = f" -> {out_dir}" if out_dir is not None else " (in place)"
    print(f"migration OK: {total} file(s) restructured, self-checked, and schema-valid{where}")
    return 0


def main(argv: list[str]) -> int:
    out_dir: Path | None = None
    positional: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--out-dir":
            index += 1
            if index >= len(argv):
                print("--out-dir requires a directory argument", file=sys.stderr)
                return 2
            out_dir = Path(argv[index])
        else:
            positional.append(arg)
        index += 1

    if len(positional) != 1:
        print(
            "usage: migrate_case_format.py [--out-dir DIR] <core/compatibility>",
            file=sys.stderr,
        )
        return 2
    compatibility_root = Path(positional[0])
    if not compatibility_root.is_dir():
        print(f"not a directory: {compatibility_root}", file=sys.stderr)
        return 2
    return run(compatibility_root, out_dir)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
