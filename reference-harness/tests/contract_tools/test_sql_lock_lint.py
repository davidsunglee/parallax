from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import sqlglot
import yaml

from reference_harness.case import Model
from reference_harness.inheritance import Family
from reference_harness.schema_validate import validation_error
from reference_harness.schemas import registry_for
from reference_harness.sql_lint import lint_tree

_REPO = Path(__file__).resolve().parents[3]
_SCHEMAS, _REGISTRY = registry_for(_REPO / "core" / "compatibility")
_ACCOUNT = "select t0.id, t0.version from account t0"
_WALLET = "select t0.id, t0.account_id from wallet t0"
_SHARED = {"postgres": "for share of t0", "mariadb": "lock in share mode"}
_MODEL = {
    "entities": [
        {
            "name": "Account",
            "table": "account",
            "attributes": [
                {"name": "id", "type": "int64", "primaryKey": True},
                {"name": "version", "type": "int32", "optimisticLocking": True},
            ],
            "relationships": [
                {
                    "name": "wallets",
                    "cardinality": "one-to-many",
                    "join": {
                        "source": "id",
                        "target": {"entity": "Wallet", "attribute": "accountId"},
                    },
                }
            ],
        },
        {
            "name": "Wallet",
            "table": "wallet",
            "attributes": [
                {"name": "id", "type": "int64", "primaryKey": True},
                {"name": "accountId", "type": "int64"},
            ],
            "relationships": [{"name": "account", "reverseOf": "Account.wallets"}],
        },
    ]
}


def _entry(sql: str, dialect: str = "postgres") -> dict[str, Any]:
    return {"sql": {dialect: sql}, "binds": [1] * sql.count("?")}


def _step(
    sql: str = _ACCOUNT, *, target: str = "Account", grouped: bool = True, dialect: str = "postgres"
) -> dict[str, Any]:
    step: dict[str, Any] = {
        "objectQuery": {"target": target, "predicate": {"true": {}}},
        "databaseCalls": 1,
        "statements": [_entry(sql, dialect)],
        "expectRows": [],
    }
    if grouped:
        step["uow"] = "writer"
    return step


def _corpus(
    tmp_path: Path,
    steps: list[dict[str, Any]],
    *,
    concurrency: str | None = None,
    default: str | None = None,
    coherence: bool = False,
    model: dict[str, Any] | None = None,
) -> Path:
    (tmp_path / "models").mkdir()
    (tmp_path / "cases").mkdir()
    descriptor = model or _MODEL
    assert validation_error(descriptor, _SCHEMAS["metamodel.schema.json"], _REGISTRY) is None
    (tmp_path / "models" / "model.yaml").write_text(yaml.safe_dump(descriptor))
    sequence = "coherence" if coherence else "scenario"
    case: dict[str, Any] = {
        "model": "models/model.yaml",
        "shape": sequence,
        "tags": ["m-read-lock"],
        "when": {sequence: steps},
        "then": {"databaseCalls": sum(step.get("databaseCalls", 0) for step in steps)},
    }
    if concurrency is not None:
        case["when"]["uow"] = {"concurrency": concurrency}
    if default is not None:
        case["given"] = {"databaseOptions": {"concurrency": default}}
    if coherence:
        case.pop("then")
    assert validation_error(case, _SCHEMAS["compatibility-case.schema.json"], _REGISTRY) is None
    (tmp_path / "cases" / "lock.yaml").write_text(yaml.safe_dump(case, sort_keys=False))
    return tmp_path


def _lock_errors(root: Path) -> list[str]:
    return [error for error in lint_tree(root) if "lock consistency:" in error]


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_missing_required_lock_is_rejected_with_location(tmp_path: Path, dialect: str) -> None:
    root = _corpus(tmp_path, [_step(dialect=dialect)], concurrency="locking")
    assert _lock_errors(root) == [
        f"case lock.yaml: when.scenario[0].statements[0].{dialect} "
        f"lock consistency: missing required {_SHARED[dialect]!r}"
    ]


@pytest.mark.parametrize(
    ("dialect", "suffix"),
    [
        ("postgres", "for update of t0"),
        ("postgres", "for key share of t0"),
        ("postgres", "for share"),
        ("postgres", "for share of t1"),
        ("postgres", "for share of t0 nowait"),
        ("postgres", "lock in share mode"),
        ("mariadb", "for share"),
        ("mariadb", "for update"),
        ("mariadb", "for share of t0"),
    ],
)
def test_incorrect_lock_is_rejected(tmp_path: Path, dialect: str, suffix: str) -> None:
    root = _corpus(
        tmp_path, [_step(f"{_ACCOUNT} {suffix}", dialect=dialect)], concurrency="locking"
    )
    errors = _lock_errors(root)
    assert len(errors) == 1
    assert "flavor, target, placement, spelling" in errors[0]


def test_lock_before_other_clauses_is_rejected(tmp_path: Path) -> None:
    root = _corpus(tmp_path, [_step(f"{_ACCOUNT} for share of t0 limit ?")], concurrency="locking")
    assert "expected only outer suffix" in _lock_errors(root)[0]


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
@pytest.mark.parametrize(
    ("concurrency", "default", "required"),
    [
        (None, None, False),
        (None, "locking", True),
        ("optimistic", "locking", False),
        ("locking", "optimistic", True),
    ],
)
def test_preference_precedence(
    tmp_path: Path, dialect: str, concurrency: str | None, default: str | None, required: bool
) -> None:
    suffix = f" {_SHARED[dialect]}" if required else ""
    root = _corpus(
        tmp_path,
        [_step(_ACCOUNT + suffix, dialect=dialect)],
        concurrency=concurrency,
        default=default,
    )
    assert lint_tree(root) == []


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_optimistic_preference_locks_unversioned_entity(tmp_path: Path, dialect: str) -> None:
    root = _corpus(
        tmp_path, [_step(_WALLET + " " + _SHARED[dialect], target="Wallet", dialect=dialect)]
    )
    assert lint_tree(root) == []


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_optimistic_read_forbids_shared_lock(tmp_path: Path, dialect: str) -> None:
    root = _corpus(tmp_path, [_step(_ACCOUNT + " " + _SHARED[dialect], dialect=dialect)])
    assert "forbidden lock" in _lock_errors(root)[0]


@pytest.mark.parametrize("coherence", [False, True])
@pytest.mark.parametrize("target", ["Account", "Wallet"])
def test_standalone_and_peer_reads_forbid_lock_even_with_locking_root(
    tmp_path: Path, coherence: bool, target: str
) -> None:
    sql = _ACCOUNT if target == "Account" else _WALLET
    step = _step(sql + " for share of t0", target=target, grouped=False)
    if coherence:
        step["node"] = "B"
        step["kind"] = "read"
        step["observeRows"] = step.pop("expectRows")
        step.pop("databaseCalls")
        seed = copy.deepcopy(step)
        seed["statements"] = [_entry(sql)]
        steps = [seed, step]
    else:
        steps = [step]
    root = _corpus(tmp_path, steps, default="locking", coherence=coherence)
    assert "forbidden lock" in _lock_errors(root)[0]


def test_unlabeled_read_does_not_inherit_boundary_participation(tmp_path: Path) -> None:
    root = _corpus(tmp_path, [_step(grouped=False)], concurrency="locking")
    assert lint_tree(root) == []


def test_temporal_entity_uses_optimistic_gate_without_version_attribute(tmp_path: Path) -> None:
    model = copy.deepcopy(_MODEL)
    model["entities"][1]["temporality"] = "transaction-time"
    assert lint_tree(_corpus(tmp_path, [_step(_WALLET, target="Wallet")], model=model)) == []


@pytest.mark.parametrize("missing_child_lock", [False, True])
def test_included_entities_resolve_strategy_independently(
    tmp_path: Path, missing_child_lock: bool
) -> None:
    step = _step()
    step["objectQuery"]["includes"] = [{"segments": [{"rel": "Account.wallets"}]}]
    step["statements"].append(_entry(_WALLET + ("" if missing_child_lock else " for share of t0")))
    step["databaseCalls"] = 2
    root = _corpus(tmp_path, [step])
    if missing_child_lock:
        assert "statements[1].postgres lock consistency: missing required" in _lock_errors(root)[0]
    else:
        assert lint_tree(root) == []


def test_reverse_include_uses_canonical_directional_metadata(tmp_path: Path) -> None:
    step = _step(_WALLET + " for share of t0", target="Wallet")
    step["objectQuery"]["includes"] = [{"segments": [{"rel": "Wallet.account"}]}]
    step["statements"].append(_entry(_ACCOUNT))
    step["databaseCalls"] = 2
    assert lint_tree(_corpus(tmp_path, [step])) == []


def test_elided_include_and_no_sql_reads_require_no_invented_statements(tmp_path: Path) -> None:
    step = _step()
    step["objectQuery"]["includes"] = [{"segments": [{"rel": "Account.wallets"}]}]
    cached = _step()
    cached.pop("statements")
    cached["databaseCalls"] = 0
    assert lint_tree(_corpus(tmp_path, [step, cached])) == []


def test_exists_predicate_table_is_not_a_materialized_entity(tmp_path: Path) -> None:
    sql = _ACCOUNT + " where exists (select t1.id from wallet t1 where t1.account_id = t0.id)"
    assert lint_tree(_corpus(tmp_path, [_step(sql)])) == []


@pytest.mark.parametrize("mutation", ["none", "missing-outer", "inner-lock", "wrong-join"])
def test_wrapped_stream_continuation_grades_only_outer_physical_lock(
    tmp_path: Path, mutation: str
) -> None:
    source = _REPO / "core" / "compatibility"
    raw = yaml.safe_load(
        (source / "cases" / "m-read-lock-016-locking-stream-two-arm-continuation.yaml").read_text()
    )
    (tmp_path / "models").mkdir()
    (tmp_path / "cases").mkdir()
    (tmp_path / "models" / "account.yaml").write_text(
        (source / "models" / "account.yaml").read_text()
    )
    sql = raw["when"]["scenario"][0]["statements"][1]["sql"]["postgres"]
    if mutation == "missing-outer":
        sql = sql.removesuffix(" for share of t0")
    elif mutation == "inner-lock":
        sql = sql.replace("limit ?) union all", "limit ? for share of t0) union all", 1)
    elif mutation == "wrong-join":
        sql = sql.replace("join account t0", "join wallet t0")
    raw["when"]["scenario"][0]["statements"][1]["sql"]["postgres"] = sql
    (tmp_path / "cases" / "stream.yaml").write_text(yaml.safe_dump(raw))
    errors = lint_tree(tmp_path)
    if mutation == "none":
        assert errors == []
    else:
        assert any(
            "when.scenario[0].statements[1].postgres lock consistency:" in error for error in errors
        )


@pytest.mark.parametrize(
    "sql", ["select t0.id from unknown t0", "select u.id from (select t0.id from account t0) u"]
)
def test_unmappable_emitted_reads_fail_with_precise_diagnostic(tmp_path: Path, sql: str) -> None:
    errors = _lock_errors(_corpus(tmp_path, [_step(sql)]))
    assert len(errors) == 1
    assert errors[0].startswith(
        "case lock.yaml: when.scenario[0].statements[0].postgres "
        "lock consistency: cannot map emitted read unambiguously:"
    )


def test_competing_materialized_strategies_fail_mapping(tmp_path: Path) -> None:
    step = _step(_ACCOUNT + " union all " + _WALLET)
    step["objectQuery"]["includes"] = [{"segments": [{"rel": "Account.wallets"}]}]
    assert "incompatible strategies" in _lock_errors(_corpus(tmp_path, [step]))[0]


def test_unrelated_union_positions_fail_even_with_the_same_strategy(tmp_path: Path) -> None:
    step = _step(_ACCOUNT + " union all " + _WALLET, grouped=False)
    step["objectQuery"]["includes"] = [{"segments": [{"rel": "Account.wallets"}]}]
    assert "read spans unrelated entity positions" in _lock_errors(_corpus(tmp_path, [step]))[0]


@pytest.mark.parametrize("gate", ["version", "transaction-time"])
def test_inherited_optimistic_gate_is_resolved_from_canonical_metadata(
    tmp_path: Path, gate: str
) -> None:
    root: dict[str, Any] = {
        "name": "Base",
        "table": "account",
        "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
        "inheritance": {
            "role": "root",
            "strategy": "table-per-hierarchy",
            "tag": {"column": "kind"},
        },
    }
    if gate == "version":
        root["attributes"].append({"name": "version", "type": "int32", "optimisticLocking": True})
        sql = "select t0.id, t0.version, t0.kind from account t0"
    else:
        root["temporality"] = "transaction-time"
        sql = "select t0.id, t0.in_z, t0.out_z, t0.kind from account t0"
    concrete = {
        "name": "Account",
        "inheritance": {"role": "concrete-subtype", "parent": "Base", "tagValue": "account"},
    }
    step = _step(sql, target="Base")
    step["objectQuery"]["narrowTo"] = ["Account"]
    if gate == "transaction-time":
        step["objectQuery"]["temporal"] = {"transaction-time": {"asOf": "latest"}}
    assert lint_tree(_corpus(tmp_path, [step], model={"entities": [root, concrete]})) == []


def test_include_elision_does_not_shift_later_materialized_entity_strategy(tmp_path: Path) -> None:
    step = _step()
    step["objectQuery"]["includes"] = [
        {
            "segments": [
                {"rel": "Account.wallets"},
                {"rel": "Wallet.account"},
                {"rel": "Account.wallets"},
            ]
        }
    ]
    step["statements"].append(_entry(_WALLET + " for share of t0"))
    step["databaseCalls"] = 2
    assert lint_tree(_corpus(tmp_path, [step])) == []


def test_diagnostic_order_is_stable_by_case_step_statement_and_dialect(tmp_path: Path) -> None:
    step = _step()
    step["statements"][0]["sql"]["mariadb"] = _ACCOUNT
    step["statements"].append(copy.deepcopy(step["statements"][0]))
    root = _corpus(tmp_path, [step, copy.deepcopy(step)], concurrency="locking")
    first = _lock_errors(root)
    assert first == _lock_errors(root)
    assert [error.split(" lock consistency:")[0] for error in first] == [
        f"case lock.yaml: when.scenario[{step_index}].statements[{statement_index}].{dialect}"
        for step_index in range(2)
        for statement_index in range(2)
        for dialect in ("postgres", "mariadb")
    ]


def test_rule_reuses_parses_metadata_include_resolution_and_corpus_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    step = _step()
    step["objectQuery"]["includes"] = [{"segments": [{"rel": "Account.wallets"}]}]
    step["statements"].append(_entry(_WALLET + " for share of t0"))
    root = _corpus(tmp_path, [step, copy.deepcopy(step)])
    (root / "fixtures").mkdir()
    (root / "fixtures" / "model.yaml").write_text("[invalid: fixture:")
    calls = {"parses": 0, "entities": 0, "positions": 0, "case_passes": 0}
    parse = sqlglot.parse_one
    entities = Model.entities.fget
    position = Family.effective_concrete_set
    glob = Path.glob

    def count_parse(*args: Any, **kwargs: Any) -> Any:
        calls["parses"] += 1
        return parse(*args, **kwargs)

    def count_entities(model: Model) -> Any:
        calls["entities"] += 1
        assert entities is not None
        return entities(model)

    def count_position(family: Family, name: str) -> list[str]:
        calls["positions"] += 1
        return position(family, name)

    def count_glob(path: Path, pattern: str, **kwargs: Any) -> Any:
        if path == root / "cases":
            calls["case_passes"] += 1
        return glob(path, pattern, **kwargs)

    monkeypatch.setattr(sqlglot, "parse_one", count_parse)
    monkeypatch.setattr(Model, "entities", property(count_entities))
    monkeypatch.setattr(Family, "effective_concrete_set", count_position)
    monkeypatch.setattr(Path, "glob", count_glob)
    assert lint_tree(root) == []
    assert calls == {"parses": 8, "entities": 1, "positions": 2, "case_passes": 1}


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_shared_lock_targets_only_root_rows(tmp_path: Path, dialect: str) -> None:
    sql = _ACCOUNT + " join wallet t1 on t1.account_id = t0.id " + _SHARED[dialect]
    root = _corpus(tmp_path, [_step(sql, dialect=dialect)], concurrency="locking")
    if dialect == "postgres":
        assert lint_tree(root) == []
    else:
        assert "MariaDB shared lock must cover only the physical root" in _lock_errors(root)[0]
