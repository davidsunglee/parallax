"""What a Scenario step's own document must say, asked of every case.

Three rules a step states about itself rather than about a run: which find a
write settles against (`m-case-format` *Settling against a grouped find*), which
earlier step an identity observable is anchored to, and whether the dialect-keyed
maps it carries cover the dialects its own golden declares. None needs an
executor, a dialect, or a database, so ``validate_tree`` asks them of every case
in the corpus — the api-conformance lane's Scenario cases, which no wire executor
ever runs, included.

The SHAPE of a reference belongs to the case schema and is pinned in
`test_case_schema.py` (an ungrouped write, an array `on`, a legacy-string or
predicate-selected `write`, and a step declaring both identity observables at
once are each REJECTED there). What is left, and what these probes pin, is the
part one step cannot state about another: the step a write names must be an
earlier one and a find of that write's own group, and the step an identity
observable anchors to must be an earlier one.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from reference_harness.schema_validate import (
    _scenario_statement_binds_keys,
    _validate_identity_anchor,
    _validate_scenario_reference_sql,
    _validate_settled_write,
    validate_tree,
)
from reference_harness.schemas import load_schemas

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORE = _REPO_ROOT / "core"
_CASE_SCHEMA = load_schemas(_CORE)["compatibility-case.schema.json"]

_QUERY = {"target": "Position", "predicate": {"all": {}}}
_FIND = {"uow": "g", "objectQuery": _QUERY}
_OTHER_FIND = {"uow": "h", "objectQuery": _QUERY}
_WRITE = {"uow": "g", "write": [{"mutation": "update", "entity": "Position", "rows": [{"id": 1}]}]}


def _settled(step: dict[str, Any], before: list[dict[str, Any]]) -> list[str]:
    """The problems reported for *step*, authored after the steps *before* it."""
    steps = [*before, step]
    errors: list[str] = []
    _validate_settled_write(steps, len(steps) - 1, "probe", errors)
    return errors


def _reference_sql(step: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    _validate_scenario_reference_sql(step, _CASE_SCHEMA, "probe", errors)
    return errors


def _anchored(step: dict[str, Any], index: int) -> list[str]:
    """The problems reported for *step*, authored at position *index*."""
    errors: list[str] = []
    _validate_identity_anchor(step, index, "probe", errors)
    return errors


# --- which find a write may settle against ----------------------------------


def test_a_settling_write_names_an_earlier_step() -> None:
    assert not _settled({**_WRITE, "on": 0}, [_FIND])
    assert _settled({**_WRITE, "on": 1}, [_FIND]) == [
        "probe: settles against step 1, which is not a real EARLIER step (0 <= source < 1)"
    ]
    assert _settled({**_WRITE, "on": -1}, [_FIND])


def test_a_settling_write_names_a_find_of_its_own_group() -> None:
    # Evidence a write consumes is transaction-scoped and published by a read, so a
    # find of another group and a step that observed nothing both name evidence
    # that never reaches this write.
    refusal = "probe: settles against step 0, which is not a find step of its own `uow` group 'g'"
    assert not _settled({**_WRITE, "on": 1}, [_OTHER_FIND, _FIND])
    assert _settled({**_WRITE, "on": 0}, [_OTHER_FIND, _FIND]) == [refusal]
    assert _settled({**_WRITE, "on": 0}, [_WRITE, _FIND]) == [refusal]


def test_a_reference_the_case_schema_types_is_left_to_the_case_schema() -> None:
    # A reference whose shape the schema already refuses is reported there, in the
    # schema's own vocabulary, rather than a second time here in a different one.
    ungrouped = {key: value for key, value in _WRITE.items() if key != "uow"}
    assert not _settled({**_WRITE, "on": "0"}, [_FIND])
    assert not _settled({**ungrouped, "on": 0}, [_FIND])


# --- which step an identity observable anchors to ---------------------------


def test_both_identity_observables_anchor_to_an_earlier_step() -> None:
    # `sameObjectAs` and `differentObjectFrom` are graded in different places — one
    # by the wire harness as primary-key identity, the other adapter-delegated to
    # each language's API Conformance Suite — but an anchor that is not an earlier
    # step names no result either grader could compare against.
    assert not _anchored({"sameObjectAs": 0}, 1)
    assert not _anchored({"differentObjectFrom": 0}, 1)
    assert _anchored({"sameObjectAs": 1}, 1) == [
        "probe: sameObjectAs names step 1, which is not a real EARLIER step (0 <= source < 1)"
    ]
    assert _anchored({"differentObjectFrom": 999}, 1) == [
        "probe: differentObjectFrom names step 999, which is not a real EARLIER step "
        "(0 <= source < 1)"
    ]


def test_an_anchor_the_case_schema_types_is_left_to_the_case_schema() -> None:
    # An anchor whose shape the schema already refuses is reported there, in the
    # schema's own vocabulary, rather than a second time here in a different one.
    assert not _anchored({"sameObjectAs": "0"}, 1)
    assert not _anchored({"differentObjectFrom": True}, 1)


# --- the dialect maps a step carries ----------------------------------------


def test_a_reference_sql_map_covers_exactly_the_dialects_its_golden_executes_on() -> None:
    both = [{"sql": {"postgres": "select 1", "mariadb": "select 1"}}]
    postgres_only = [{"sql": {"postgres": "select 1"}}]
    keyed = {"postgres": "p", "mariadb": "m"}
    assert not _reference_sql({"referenceSql": keyed, "statements": both})
    assert _reference_sql({"referenceSql": {"postgres": "p"}, "statements": both}) == [
        "probe: referenceSql map keys ['postgres'] != scenario golden sql map keys "
        "['mariadb', 'postgres']"
    ]
    assert _reference_sql({"referenceSql": keyed, "statements": postgres_only}) == [
        "probe: referenceSql map keys ['mariadb', 'postgres'] != scenario golden sql map keys "
        "['postgres']"
    ]


def test_a_streamed_deliverys_oracle_covers_every_dialect_a_page_declares() -> None:
    # A Scenario executes on a dialect as soon as ONE step lowers for it, and a
    # streamed step's pages are one delivery that runs whenever the Scenario does.
    # So the set the oracle owes is the UNION over the pages, not the intersection
    # `Case.golden_dialects` reads at `then`: a map covering only what every page
    # shares is asked for the odd page's dialect at execution and has no answer.
    pages = [{"sql": {"postgres": "p1", "mariadb": "m1"}}, {"sql": {"postgres": "p2"}}]
    step = {"stream": {"batchSize": 2}, "statements": pages}
    assert not _reference_sql({**step, "referenceSql": {"postgres": "p", "mariadb": "m"}})
    assert _reference_sql({**step, "referenceSql": {"postgres": "p"}}) == [
        "probe: referenceSql map keys ['postgres'] != scenario golden sql map keys "
        "['mariadb', 'postgres']"
    ]


def test_a_reference_sql_needs_the_golden_read_it_spells_naively() -> None:
    # One naive spelling answers ONE golden read: an ordinary find's single
    # statement, or a streamed step's whole page list for one delivery.
    two_statements = [{"sql": {"postgres": "p1"}}, {"sql": {"postgres": "p2"}}]
    assert _reference_sql({"referenceSql": "select 1", "statements": []})
    assert _reference_sql({"referenceSql": "select 1", "statements": two_statements})
    assert not _reference_sql(
        {"referenceSql": "select 1", "stream": {"batchSize": 2}, "statements": two_statements}
    )


def test_a_dialect_keyed_binds_map_covers_its_own_statements_sql_map() -> None:
    sql = {"postgres": "p", "mariadb": "m"}
    statements = [
        {"sql": sql, "binds": {"postgres": [1], "mariadb": [2]}},
        {"sql": sql, "binds": {"postgres": [1]}},
    ]
    errors: list[str] = []
    _scenario_statement_binds_keys({"statements": statements}, "probe", errors)
    assert errors == [
        "probe statements[1]: binds map keys ['postgres'] != sql map keys ['mariadb', 'postgres']"
    ]


# --- every rule reaches the lane no executor runs ----------------------------

_API_CONFORMANCE_CASE = "m-snapshot-read-019-write-keeps-unloaded-absent.yaml"


def test_whole_tree_validation_asks_every_rule_of_an_api_conformance_case(tmp_path: Path) -> None:
    """The lane whose Scenario cases the wire harness never executes is validated
    like every other, so a defect either rule owns is refused there too.

    This is what asking them of the document rather than of a run buys: an
    api-conformance Scenario case reaches no Scenario pipeline at all, so a rule
    that ran only where a case executed would leave the whole lane unchecked.
    """
    core = tmp_path / "core"
    shutil.copytree(_CORE, core)
    case_path = core / "compatibility" / "cases" / _API_CONFORMANCE_CASE
    case = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    steps = case["when"]["scenario"]
    # A write settling against a find that belongs to no group of its own.
    steps[1]["uow"] = "g"
    steps[1]["on"] = 0
    # An independent oracle authored for the one dialect this read has no golden for.
    steps[0]["referenceSql"] = {"mariadb": "select id from orders where id = 3"}
    # An identity observable anchored to a step the Scenario never authored.
    steps[2]["differentObjectFrom"] = 999
    case_path.write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")

    errors = validate_tree(core / "compatibility")
    assert [error for error in errors if "not a find step of its own `uow` group" in error]
    assert [error for error in errors if "referenceSql map keys" in error]
    assert [error for error in errors if "differentObjectFrom names step 999" in error]
