"""The write-grading module's own interface.

The lanes that grade a write end to end — write sequence, conflict, bitemporal,
pk generation, Unit Work Scenario — cover the operations through their own
cases. What this file covers is what only the interface can state: the column
lists an operation reads a rendered statement down to, the object an existing-row
statement addresses, and the pin that the scanner underneath all of them stays
invisible.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from reference_harness import write_plan
from reference_harness.case import Case, discover_cases
from reference_harness.write_plan import (
    parse_insert_columns,
    parse_set_columns,
    statement_object,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"

_DIALECTS = ("postgres", "mariadb")


def _a_case() -> Case:
    """Any real case, for the operations that name one in their refusal."""
    return next(
        c
        for c in discover_cases(COMPATIBILITY_ROOT)
        if c.path.stem.startswith("m-storage-layout-022")
    )


# --- the interface itself ----------------------------------------------------


def _module_level_names(path: Path) -> set[str]:
    """Every name a module DECLARES at the top level, imports excluded.

    Read off the source rather than off ``dir()`` so a name the module merely
    imported to implement itself is not counted as something it offers.
    """
    names: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def test_write_grading_offers_operations_and_no_lexical_primitive() -> None:
    # Every offered name answers a question a caller of write grading has. The
    # character scanner beneath the statement readers, the write-derivation types,
    # and the sqlglot grammar are how those questions are answered, so a caller
    # that learned them would be learning the implementation instead of the
    # interface — which is what makes them refactorable.
    offered = {
        name for name in _module_level_names(Path(write_plan.__file__)) if not name.startswith("_")
    }
    assert offered == {
        "MILESTONE_COORDINATE_KEYS",
        "OPENING_MUTATIONS",
        "ObjectAddress",
        "assert_inheritance_write_routing",
        "assert_write_values",
        "classify_write_row",
        "close_address_binds",
        "has_temporal_gate",
        "has_version_gate",
        "is_existing_row_statement",
        "parse_insert_columns",
        "parse_set_columns",
        "statement_object",
        "tag",
        "unit_resolving_reads",
        "version_column",
    }


# --- the columns an update assigns -------------------------------------------


def test_the_assigned_columns_are_the_set_clause_in_rendered_order() -> None:
    # Assignment order IS bind order, so the sequence is the answer rather than a
    # set: a caller reading the value bound to one column finds it at that
    # column's own position.
    assert parse_set_columns("update t set a = ?, b = ? where id = ?") == ["a", "b"]


def test_a_statement_assigning_nothing_answers_nothing() -> None:
    # A DELETE and an INSERT assign no columns, and neither is a defect on its own
    # — a settled versioned write reaches a golden DELETE whenever a destructive
    # intent superseded the assignments buffered before it. The absence is
    # therefore the operation's own answer, so no caller needs a second name for
    # "does this statement have a `set` clause at all".
    assert parse_set_columns("delete from t where id = ?") is None
    assert parse_set_columns("insert into t(id, note) values (?, ?)") is None


def test_a_set_clause_splits_on_the_commas_that_separate_its_assignments() -> None:
    # A document mutation expression takes commas of its own — nested `jsonb_set`
    # calls on Postgres, one N-pair `json_set` on MariaDB — so only a comma at
    # bracket depth zero ends an assignment. Splitting naively would read the
    # expression's own arguments as further SET columns.
    nested = (
        "update t set payload = jsonb_set(jsonb_set(payload, ?, cast(? as jsonb)), "
        "?, cast(? as jsonb)) where id = ?"
    )
    assert parse_set_columns(nested) == ["payload"]
    pairs = "update t set payload = json_set(payload, ?, json_extract(?, '$')) where id = ?"
    assert parse_set_columns(pairs) == ["payload"]
    plain = "update t set a = ?, b = ? where id = ?"
    assert parse_set_columns(plain) == ["a", "b"]


def test_a_set_clause_reads_no_syntax_inside_a_quoted_identifier() -> None:
    # A column name is any nonempty string and a dialect quotes one that is reserved
    # or otherwise non-simple, so a comma, a bracket, an `=`, and the word `where`
    # can each sit INSIDE an identifier. A parse that read one as syntax would split
    # a legal one-assignment clause into two, or end the clause early.
    assert parse_set_columns('update t set "payload,archive" = ? where id = ?') == [
        '"payload,archive"'
    ]
    assert parse_set_columns("update t set `a(b` = ?, `c=d` = ? where id = ?") == [
        "`a(b`",
        "`c=d`",
    ]
    assert parse_set_columns('update t set "where" = ?, note = ? where id = ?') == [
        '"where"',
        "note",
    ]
    assert parse_set_columns("update t set note = 'a, b' where id = ?") == ["note"]


def test_an_insert_column_list_reads_no_syntax_inside_a_quoted_identifier() -> None:
    # The same rule one clause family over: a quoted identifier may carry a comma or
    # a bracket, so a raw split would report a one-column INSERT as two columns and a
    # quoted `)` would end the list early.
    case = _a_case()
    assert parse_insert_columns(case, 'insert into t(id, "payload,archive") values (?, ?)') == [
        "id",
        '"payload,archive"',
    ]
    assert parse_insert_columns(case, "insert into t(`a)b`, c) values (?, ?)") == ["`a)b`", "c"]
    # The pk-gen `max` form folds a call into its value list; the column list is
    # still the one that follows the table.
    max_form = 'insert into t(id, note) select coalesce(max(t0."id"), ?) + ?, ? from t t0'
    assert parse_insert_columns(case, max_form) == ["id", "note"]


# --- which object an existing-row statement addresses ------------------------


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_an_address_is_the_table_the_key_column_and_the_bound_key(dialect: str) -> None:
    address = statement_object(
        "update account set balance = ? where id = ? and version = ?", [50, 7, 3], dialect
    )
    assert address is not None
    assert address.names_table("account")
    assert address.names_key_column("id")
    # The key's bind is the predicate's FIRST placeholder: every placeholder before
    # it belongs to the `set` clause, and the tag guard, the temporal bounds, and
    # the optimistic gate all follow it.
    assert address.key == 7


@pytest.mark.parametrize(
    ("dialect", "statement"),
    [
        ("postgres", 'update "order" set note = ? where "select" = ? and version = ?'),
        ("mariadb", "update `order` set note = ? where `select` = ? and version = ?"),
    ],
)
def test_an_address_is_read_under_each_dialects_own_quoting(dialect: str, statement: str) -> None:
    # A reserved physical table or column is rendered QUOTED, in the executing
    # dialect's own quote character, so an address matched by text would miss the
    # statement that names exactly the model's own table.
    address = statement_object(statement, ["hi", 4, 1], dialect)
    assert address is not None
    assert address.names_table("order")
    assert address.names_key_column("select")
    assert address.key == 4


def test_a_quoted_identifier_names_only_what_it_spells() -> None:
    # Quoting is what a non-simple name is rendered with and the normalizer keeps
    # it, so a quoted `"Order"` and a bare `order` are two names one model may
    # declare separately rather than one identifier read two ways. An UNQUOTED
    # spelling is folded by the database instead, so it names the declared column
    # whenever the two differ only in case.
    quoted = statement_object('update "Order" set note = ? where id = ?', ["hi", 4], "postgres")
    assert quoted is not None
    assert quoted.names_table("Order")
    assert not quoted.names_table("order")
    bare = statement_object("update t set note = ? where ID = ?", ["hi", 4], "postgres")
    assert bare is not None
    assert bare.names_key_column("id")


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_a_delete_addresses_the_key_that_opens_its_predicate(dialect: str) -> None:
    # A DELETE assigns nothing, so no placeholder precedes its predicate and the key
    # is the statement's first bind rather than one counted in from the `set` clause.
    address = statement_object("delete from account where id = ?", [7], dialect)
    assert address is not None
    assert address.names_table("account")
    assert address.names_key_column("id")
    assert address.key == 7


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_a_placeholder_a_string_literal_spells_binds_no_value(dialect: str) -> None:
    # A `?` inside a string literal binds nothing, so counting the text's question
    # marks would read the key one position past the bind that actually carries it
    # and the statement would address the wrong object.
    address = statement_object("update t set note = 'a ? b', x = ? where id = ?", [4, 7], dialect)
    assert address is not None
    assert address.key == 7


def test_a_where_a_quoted_identifier_spells_opens_no_predicate() -> None:
    # `where` is a legal column name, quoted because it is reserved, so a statement
    # read as text would open the predicate inside the `set` clause and take an
    # assigned value for the key.
    address = statement_object('update t set "where" = ? where id = ?', [4, 7], "postgres")
    assert address is not None
    assert address.key == 7


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_a_statement_that_addresses_no_object_answers_nothing(dialect: str) -> None:
    # An INSERT addresses no existing object, a predicate-less write addresses
    # every row rather than one, and a leading non-equality does not name a key —
    # each is "no address" rather than a refusal, because whether reaching one is a
    # defect belongs to the lane that knows what it expected.
    assert statement_object("insert into t(id) values (?)", [1], dialect) is None
    assert statement_object("delete from t", [], dialect) is None
    assert statement_object("delete from t where id > ?", [1], dialect) is None


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_an_address_needs_a_bind_at_the_position_it_reads(dialect: str) -> None:
    # The golden's binds and its placeholders are authored separately, so a key
    # position past the end of the bind row names no value at all.
    assert statement_object("update t set a = ? where id = ?", [1], dialect) is None


@pytest.mark.parametrize("dialect", _DIALECTS)
def test_a_subquerys_own_predicate_is_not_this_statements_address(dialect: str) -> None:
    # A nested SELECT's `where` is a conjunct of the inner query; reading it as the
    # outer address would report a statement gating on nothing as keyed.
    assert (
        statement_object(
            "update t set a = ? where id in (select id from u where flag = ?)", [1, 2], dialect
        )
        is None
    )
