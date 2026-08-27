"""Unit tests for the m-sql SQL normalizer (``sql_normalize``).

These are Docker-free: ``normalize`` is a pure function, so the canonical-form
rules can be checked without booting a database. They guard the canonical form
of the m-read-lock read-lock suffix, whose lock-clause keywords sqlglot tokenizes as
``VAR`` (not keyword tokens) — the case that previously escaped lowercasing.
"""

from __future__ import annotations

import pytest
import sqlglot

from reference_harness.sql_normalize import (
    NonCanonicalError,
    WrapFacts,
    WrapOrderKey,
    is_canonical,
    normalize,
    sqlglot_dialect,
    wrapped_union_source,
)


def test_read_lock_share_suffix_normalizes_to_lowercase() -> None:
    # sqlglot's generator emits the lock-clause keywords uppercase and tokenizes
    # `SHARE`/`OF` as VAR, so they used to survive the keyword-lowercasing pass.
    # m-sql rule 2 lowercases keywords, so the canonical form is fully lowercase.
    canonical = "select t0.id from account t0 where t0.id = ? for share of t0"
    assert normalize("select t0.id from account t0 where t0.id = ? for SHARE OF t0") == canonical
    assert is_canonical(canonical)


def test_read_lock_update_suffix_normalizes_to_lowercase() -> None:
    canonical = "select t0.id from account t0 where t0.id = ? for update of t0"
    assert normalize("select t0.id from account t0 where t0.id = ? for UPDATE OF t0") == canonical
    assert is_canonical(canonical)


def test_null_placement_suffix_normalizes_to_lowercase() -> None:
    # The m-dialect Null Placement suffix has the same hazard as the lock clause:
    # sqlglot tokenizes `NULLS` and `LAST` as VAR (while `FIRST` has its own token
    # type), so without lowercasing them the canonical form would read
    # `NULLS LAST` beside a lowercase `nulls first`.
    for term in ("t0.sku asc nulls first", "t0.sku desc nulls last"):
        canonical = f"select t0.id from orders t0 order by {term}"
        assert normalize(canonical.upper().replace("T0", "t0")) == canonical
        assert is_canonical(canonical)


def test_null_placement_leading_rank_term_normalizes_negation() -> None:
    # MariaDB's `nulls first` compensation on `desc` is a leading `is not null` rank
    # term, which m-sql normalization rewrites to a leading `not` like any other
    # negated null test — so the canonical golden carries `not t0.sku is null`.
    canonical = "select t0.id from orders t0 order by not t0.sku is null, t0.sku desc"
    assert (
        normalize("select t0.id from orders t0 order by t0.sku is not null, t0.sku desc", "mariadb")
        == canonical
    )
    assert is_canonical(canonical, "mariadb")


# --- quoted identifiers (reserved words) are preserved, not stripped ---------
# A reserved-word column must be quoted; the normalizer keeps the quotes (with
# the dialect's quote character) rather than stripping them (Postgres) or
# mangling the backticks (MariaDB), which is what broke before the fix.


def test_quoted_reserved_identifier_is_canonical_postgres() -> None:
    canonical = 'select t0.id, t0."order", t0.label from grade t0 where t0."order" > ?'
    assert is_canonical(canonical, "postgres")
    assert normalize(canonical, "postgres") == canonical


def test_quoted_reserved_identifier_is_canonical_mariadb() -> None:
    canonical = "select t0.id, t0.`order`, t0.label from grade t0 where t0.`order` > ?"
    assert is_canonical(canonical, "mariadb")
    assert normalize(canonical, "mariadb") == canonical


def test_quoted_identifier_in_insert_is_canonical() -> None:
    assert is_canonical('insert into grade(id, "order", label) values (?, ?, ?)', "postgres")
    assert is_canonical("insert into grade(id, `order`, label) values (?, ?, ?)", "mariadb")


# --- canonical-rule enforcement (m-sql rule 1: t0,t1 aliases + qualified columns;
#     rule 4: parameters as ? binds) ----------------------------------------
# Lowercasing + re-spacing alone is not enough: a lowercase-but-non-canonical
# read must be REJECTED so sql_lint cannot accept it as a fixture.


def test_rejects_non_canonical_table_alias() -> None:
    # alias `o` is not the canonical t0 (rule 1)
    assert not is_canonical("select o.id from orders o")


def test_rejects_out_of_sequence_alias() -> None:
    # a single table must be t0, not t1
    assert not is_canonical("select t1.id from orders t1")


def test_rejects_unqualified_column_in_read() -> None:
    # bare `id` is not alias-qualified (rule 1)
    assert not is_canonical("select id from orders t0")


def test_rejects_inline_predicate_literal() -> None:
    # `42` is a parameter and must be a ? bind (rule 4)
    assert not is_canonical("select t0.id from orders t0 where t0.id = 42")


def test_rejects_inline_in_list_literal() -> None:
    assert not is_canonical("select t0.id from orders t0 where t0.id in (1, 2)")


def test_rejects_inline_between_literal() -> None:
    assert not is_canonical("select t0.id from orders t0 where t0.amt between 1 and 9")


def test_rejects_inline_limit_literal() -> None:
    assert not is_canonical("select t0.id from orders t0 limit 10")


def test_rejects_insert_values_literal() -> None:
    assert not is_canonical("insert into account(id) values (1)")


def test_rejects_insert_values_literal_in_multi_row_insert() -> None:
    assert not is_canonical("insert into account(id) values (?), (2)")


def test_accepts_insert_values_placeholders_in_multi_row_insert() -> None:
    assert is_canonical("insert into account(id, owner) values (?, ?), (?, ?)")


# Structural literals are NOT parameters — they are part of the canonical form
# and must stay accepted.


def test_accepts_none_identity_structural_literal() -> None:
    assert is_canonical("select t0.id, t0.name from orders t0 where 1 = 0")


def test_accepts_exists_probe_and_correlated_alias() -> None:
    assert is_canonical(
        "select t0.id from orders t0 where exists "
        "(select 1 from order_item t1 where t1.order_id = t0.id)"
    )


# DML has its own canonical shape: the target table is unaliased and columns
# are bare. The read-only rules (1) MUST NOT be applied to it.


def test_accepts_dml_with_bare_columns() -> None:
    assert is_canonical("update balance set out_z = ? where bal_id = ? and out_z = ?")
    assert is_canonical("insert into balance(bal_id, val) values (?, ?)")


# --- union all (table-per-concrete-subtype abstract-read lowering) -----------
# `union all` over the effective concrete tables is a NEW canonical SQL surface
# (m-sql). It must be a normalization fixed point: each branch's alias scheme and
# column qualification (rule 1) apply PER BRANCH, branch order is preserved, and the
# NULL-placeholder casts + `familyVariant` string literals it introduces survive.

_TPCS_ROOT_UNION = (
    "select t0.id, t0.title, t0.currency, t0.amount_due, "
    "cast(null as decimal(18, 2)) paid_amount, cast(null as varchar(64)) body, "
    "'Invoice' family_variant from invoice t0 "
    "union all "
    "select t0.id, t0.title, t0.currency, cast(null as decimal(18, 2)) amount_due, "
    "t0.paid_amount, cast(null as varchar(64)) body, 'Receipt' family_variant "
    "from receipt t0 "
    "union all "
    "select t0.id, t0.title, cast(null as varchar(3)) currency, "
    "cast(null as decimal(18, 2)) amount_due, cast(null as decimal(18, 2)) paid_amount, "
    "t0.body, 'Memo' family_variant from memo t0"
)


def test_union_all_read_is_a_normalization_fixed_point() -> None:
    # The full three-branch abstract-root golden is already canonical, and
    # normalizing it is idempotent (the fixed-point property sql_lint enforces).
    assert is_canonical(_TPCS_ROOT_UNION, "postgres")
    assert normalize(_TPCS_ROOT_UNION, "postgres") == _TPCS_ROOT_UNION


def test_union_all_alias_scheme_restarts_per_branch() -> None:
    # Each branch independently uses t0; the alias scheme is NOT globalized across
    # branches (which would demand t0, t1, t2 for three branches).
    two_branch = "select t0.id from invoice t0 union all select t0.id from receipt t0"
    assert is_canonical(two_branch, "postgres")


def test_union_all_preserves_all_and_branch_order() -> None:
    # `union all` (not `union`) is preserved — de-duplication would drop rows — and
    # the left-to-right branch order is stable (a normalizer must not reorder arms).
    assert normalize(_TPCS_ROOT_UNION, "postgres").count(" union all ") == 2
    order = [
        _TPCS_ROOT_UNION.index("from invoice"),
        _TPCS_ROOT_UNION.index("from receipt"),
        _TPCS_ROOT_UNION.index("from memo"),
    ]
    assert order == sorted(order)


# --- the wrapped `union all` (an ordered or limited abstract read) -----------
# An abstract read declaring `orderBy` or `limit` wraps the whole union as the derived
# table `u` and applies the tail against that alias (m-sql). That wrap is the ONE shape
# whose outer select is a table-less scope, so each branch keeps restarting its own
# `t0, t1, …` sequence; every other way of reaching a union puts tables in the outer
# scope, and a normalizer that exempted those would be granting an exemption rather
# than applying a rule.

_WRAPPED_UNION = (
    "select u.id, u.title from "
    "(select t0.id, t0.title from invoice t0 "
    "union all "
    "select t0.id, t0.title from memo t0) u order by u.title desc limit ?"
)


def test_wrapped_union_read_is_a_normalization_fixed_point() -> None:
    # The canonical wrap: sole derived source aliased `u`, named projection, tail.
    assert is_canonical(_WRAPPED_UNION, "postgres")
    assert normalize(_WRAPPED_UNION, "postgres") == _WRAPPED_UNION


def test_a_wrapped_unions_branches_are_the_unwrapped_reads_byte_for_byte() -> None:
    # What recognizing the wrap buys: branch scoping survives it, so ordering a read
    # does not renumber the branches the same read unordered already spells.
    bare = "select t0.id, t0.title from invoice t0 union all select t0.id, t0.title from memo t0"
    assert is_canonical(bare, "postgres")
    assert bare in _WRAPPED_UNION


def test_a_wrapped_union_under_another_alias_is_not_canonical() -> None:
    # m-sql names the derived table `u`; another alias is a different statement the
    # goldens must not spell.
    assert not is_canonical(_WRAPPED_UNION.replace(" u ", " x ").replace("u.", "x."), "postgres")


def test_a_wrapped_union_projecting_a_wildcard_is_not_canonical() -> None:
    # The outer select projects the union's own result aliases through; a wildcard
    # names none of them, and qualifying it with the wrap alias does not make `*` one
    # — not even where the union's own branches project a wildcard, so the aliases it
    # answers are spelled `*` too.
    for outer in ("select * from", "select u.* from"):
        assert not is_canonical(_WRAPPED_UNION.replace("select u.id, u.title from", outer, 1))
    starred = "select u.* from (select * from invoice t0 union all select * from memo t0) u limit ?"
    assert not is_canonical(starred, "postgres")


def test_a_wrapped_union_without_a_result_tail_is_not_canonical() -> None:
    # The tail is the only reason to wrap. Without one the canonical form is the bare
    # union, so the wrap is a second spelling of one read.
    tailless = _WRAPPED_UNION.split(" order by ")[0]
    assert not is_canonical(tailless, "postgres")


def test_a_wrapped_union_joined_to_another_table_is_not_canonical() -> None:
    # The outer scope is table-less ONLY in the canonical wrap. A read that takes the
    # union as its sole source and then joins to a table of its own is neither the
    # wrap nor the locking table-per-hierarchy partitioned read (whose sole source is
    # a table and whose derived union is the JOINED relation).
    joined = (
        "select u.id, t0.name from "
        "(select t0.id, t0.title from invoice t0 "
        "union all "
        "select t0.id, t0.title from memo t0) u "
        "join folder t0 on t0.id = u.id order by u.title desc"
    )
    assert not is_canonical(joined, "postgres")


def test_a_wrapped_union_carrying_an_outer_predicate_is_not_canonical() -> None:
    # Only the result-shape tail moves outward; the caller's predicate keeps lowering
    # inside each branch, where that branch's own Table Layout resolves it.
    filtered = _WRAPPED_UNION.replace(" order by ", " where u.id = ? order by ", 1)
    assert not is_canonical(filtered, "postgres")


def test_a_wrapped_plain_union_is_not_canonical() -> None:
    # The wrap does not launder the set operation inside it.
    assert not is_canonical(_WRAPPED_UNION.replace("union all", "union"), "postgres")


# The outer shape m-sql fixes is the whole of what the wrap buys, so the verifier
# grades it rather than accepting any named projection. Every spelling below reaches
# its union under an outer select that a projection-blind recognizer reads as
# canonical, so grading the outer shape is the only thing that refuses it.


@pytest.mark.parametrize(
    "outer",
    [
        pytest.param("select u.id, u.id from", id="duplicated"),
        pytest.param("select u.id from", id="missing"),
        pytest.param("select u.title, u.id from", id="reordered"),
        pytest.param("select 1, u.title from", id="computed"),
        pytest.param("select u.id id, u.title from", id="aliased"),
        pytest.param("select x.id, u.title from", id="foreign-qualifier"),
        pytest.param("select u.id, u.title, u.id from", id="extra"),
    ],
)
def test_a_wrapped_union_projecting_anything_but_the_result_aliases_is_not_canonical(
    outer: str,
) -> None:
    # m-sql: the outer select projects the union's OWN result aliases through, each
    # once and in the union's order. Everything else names cells the union does not
    # answer, or answers a different result shape under a canonical spelling.
    assert not is_canonical(_WRAPPED_UNION.replace("select u.id, u.title from", outer, 1))


def test_a_wrapped_union_expands_a_document_read_pair_over_its_alias() -> None:
    # The one exception: a presence cell carries no result alias, so the branch
    # projects the slot as a single aliased cell and the outer select expands the
    # pair over it. Both halves must name the same alias, in that order.
    paired = (
        "select u.id, not u.payload is null, u.payload from "
        "(select t0.id, t0.payload from publication_book t0 "
        "union all "
        "select t0.id, t0.payload from publication_film t0) u order by u.id limit ?"
    )
    assert is_canonical(paired, "postgres")
    assert not is_canonical(paired.replace("not u.payload is null", "not u.id is null", 1))
    assert not is_canonical(
        paired.replace("not u.payload is null, u.payload", "u.payload, not u.payload is null", 1)
    )


def _facts(
    *,
    document_aliases: frozenset[str] = frozenset(),
    order_keys: tuple[WrapOrderKey, ...] = (),
    limited: bool = False,
) -> WrapFacts:
    return WrapFacts(document_aliases=document_aliases, order_keys=order_keys, limited=limited)


_DOCUMENT_WRAP = (
    "select {outer} from "
    "(select t0.id, t0.payload from publication_book t0 "
    "union all "
    "select t0.id, t0.payload from publication_film t0) u order by u.id limit ?"
)

_ID_KEY = (WrapOrderKey(alias="id", descending=False, nulls_first=False, nullable=False),)


def test_a_presence_pair_is_admitted_only_over_a_named_document_alias() -> None:
    # Which alias holds the Document is a model fact no statement carries. A caller
    # that knows names it, and a pair over a scalar — a shape indistinguishable from
    # the read pair in SQL alone — is refused; a caller that does not know gets the
    # widest reading the statement supports.
    scalar_pair = _DOCUMENT_WRAP.format(outer="not u.id is null, u.id, u.payload")
    tree = sqlglot.parse_one(scalar_pair, read="postgres")
    assert wrapped_union_source(tree, "postgres") is not None
    with pytest.raises(NonCanonicalError):
        wrapped_union_source(
            tree,
            "postgres",
            _facts(document_aliases=frozenset({"payload"}), order_keys=_ID_KEY, limited=True),
        )


def test_a_named_document_alias_must_carry_its_presence_half() -> None:
    # A projected Document value the outer select does not precede with
    # `not u.<alias> is null` is not readable as a Document at all: m-dialect's paired
    # parser needs both raw cells, so permitting the pair is not enough where the
    # caller knows which alias holds one.
    tree = sqlglot.parse_one(_DOCUMENT_WRAP.format(outer="u.id, u.payload"), read="postgres")
    assert wrapped_union_source(tree, "postgres") is not None
    with pytest.raises(NonCanonicalError):
        wrapped_union_source(
            tree,
            "postgres",
            _facts(document_aliases=frozenset({"payload"}), order_keys=_ID_KEY, limited=True),
        )
    paired = sqlglot.parse_one(
        _DOCUMENT_WRAP.format(outer="u.id, not u.payload is null, u.payload"), read="postgres"
    )
    assert (
        wrapped_union_source(
            paired,
            "postgres",
            _facts(document_aliases=frozenset({"payload"}), order_keys=_ID_KEY, limited=True),
        )
        is not None
    )


_EXTRACTION_WRAP = (
    "select u.id, not u.payload is null, u.payload from "
    "(select t0.id, t0.payload from publication_book t0 "
    "union all "
    "select t0.id, t0.payload from publication_film t0) u order by {key} limit ?"
)


def test_a_document_extraction_must_be_the_dialects_own_spelling() -> None:
    # m-dialect fixes ONE extraction function per dialect. The other dialect's
    # spelling is a call this statement's own dialect never emits, so a key written
    # with it names no result alias and the wrap is refused.
    assert is_canonical(
        _EXTRACTION_WRAP.format(key="jsonb_extract_path_text(u.payload, ?)"), "postgres"
    )
    assert not is_canonical(_EXTRACTION_WRAP.format(key="json_value(u.payload, ?)"), "postgres")
    assert is_canonical(_EXTRACTION_WRAP.format(key="json_value(u.payload, ?)"), "mariadb")
    assert not is_canonical(
        _EXTRACTION_WRAP.format(key="jsonb_extract_path_text(u.payload, ?)"), "mariadb"
    )


_RANK_WRAP = (
    "select u.id, u.title from "
    "(select t0.id, t0.title from invoice t0 "
    "union all "
    "select t0.id, t0.title from memo t0) u order by {tail}"
)


def test_a_null_placement_rank_term_is_canonical_only_where_the_dialect_needs_one() -> None:
    # MariaDB has no `NULLS FIRST/LAST` syntax and compensates with a leading boolean
    # rank term (m-dialect); Postgres spells the same request as a suffix and never
    # emits a rank term, so one there sorts on a value no Sort Key asks for.
    for tail in ("u.title is null, u.title asc", "not u.title is null, u.title desc"):
        assert is_canonical(_RANK_WRAP.format(tail=tail), "mariadb")
        assert not is_canonical(_RANK_WRAP.format(tail=tail), "postgres")
    # The rank term ranks the key it precedes and nothing else.
    assert not is_canonical(_RANK_WRAP.format(tail="u.title is null, u.id asc"), "mariadb")
    assert not is_canonical(_RANK_WRAP.format(tail="u.title is null"), "mariadb")


# The tail is a rendering of the read's own Sort Keys and cap, and the case runner
# knows both. Grading it against them is what makes an ordering that no authored key
# asks for a refusal rather than merely a well-formed key.

_TITLE_WRAP = (
    "select u.id, u.title from "
    "(select t0.id, t0.title from invoice t0 "
    "union all "
    "select t0.id, t0.title from memo t0) u order by {tail}"
)


def _title_key(*, descending: bool, nulls_first: bool, nullable: bool = True) -> WrapOrderKey:
    return WrapOrderKey(
        alias="title", descending=descending, nulls_first=nulls_first, nullable=nullable
    )


@pytest.mark.parametrize(
    ("descending", "nulls_first", "postgres", "mariadb"),
    [
        pytest.param(False, False, "u.title asc", "u.title is null, u.title asc", id="asc-last"),
        pytest.param(True, False, "u.title desc nulls last", "u.title desc", id="desc-last"),
        pytest.param(False, True, "u.title asc nulls first", "u.title asc", id="asc-first"),
        pytest.param(
            True, True, "u.title desc", "not u.title is null, u.title desc", id="desc-first"
        ),
    ],
)
def test_the_wrap_orders_by_what_the_authored_sort_key_renders_to(
    descending: bool, nulls_first: bool, postgres: str, mariadb: str
) -> None:
    # The m-dialect Null Placement table, applied against the union alias: exactly one
    # dialect compensates per row, and each compensates in its own syntax.
    facts = _facts(order_keys=(_title_key(descending=descending, nulls_first=nulls_first),))
    for dialect, expected in (("postgres", postgres), ("mariadb", mariadb)):
        tree = sqlglot.parse_one(_TITLE_WRAP.format(tail=expected), read=sqlglot_dialect(dialect))
        assert wrapped_union_source(tree, dialect, facts) is not None
    crossed = sqlglot.parse_one(_TITLE_WRAP.format(tail=mariadb), read="postgres")
    if mariadb != postgres:
        with pytest.raises(NonCanonicalError):
            wrapped_union_source(crossed, "postgres", facts)


def test_a_non_nullable_sort_key_takes_the_plain_term_under_either_placement() -> None:
    # Placement is observable only on a nullable key, so both dialects render the
    # plain directed term and neither compensates (m-dialect).
    for nulls_first in (False, True):
        facts = _facts(
            order_keys=(_title_key(descending=False, nulls_first=nulls_first, nullable=False),)
        )
        for dialect in ("postgres", "mariadb"):
            tree = sqlglot.parse_one(
                _TITLE_WRAP.format(tail="u.title asc"), read=sqlglot_dialect(dialect)
            )
            assert wrapped_union_source(tree, dialect, facts) is not None


@pytest.mark.parametrize(
    "tail",
    [
        pytest.param("u.title desc", id="wrong-direction"),
        pytest.param("u.id asc", id="wrong-alias"),
        pytest.param("u.title asc, u.id asc", id="extra-key"),
        pytest.param("jsonb_extract_path_text(u.title, ?)", id="extraction"),
    ],
)
def test_an_ordering_the_read_did_not_author_is_refused(tail: str) -> None:
    # A term that is a legal ordering key in the abstract still sorts on something
    # this read never asked for; the caller holding the query is the only one that can
    # tell the two apart.
    facts = _facts(order_keys=(_title_key(descending=False, nulls_first=False, nullable=False),))
    tree = sqlglot.parse_one(_TITLE_WRAP.format(tail=tail), read="postgres")
    with pytest.raises(NonCanonicalError):
        wrapped_union_source(tree, "postgres", facts)


def test_the_wraps_cap_is_the_one_the_read_authored() -> None:
    # A cap applies to the union's rows and is the other half of the tail the wrap
    # carries, so a golden capping a read that declared no `limit` returns a different
    # result set under a canonical spelling.
    key = (_title_key(descending=False, nulls_first=False, nullable=False),)
    ordered = sqlglot.parse_one(_TITLE_WRAP.format(tail="u.title asc"), read="postgres")
    capped = sqlglot.parse_one(_TITLE_WRAP.format(tail="u.title asc limit ?"), read="postgres")
    assert wrapped_union_source(ordered, "postgres", _facts(order_keys=key)) is not None
    assert (
        wrapped_union_source(capped, "postgres", _facts(order_keys=key, limited=True)) is not None
    )
    with pytest.raises(NonCanonicalError):
        wrapped_union_source(ordered, "postgres", _facts(order_keys=key, limited=True))
    with pytest.raises(NonCanonicalError):
        wrapped_union_source(capped, "postgres", _facts(order_keys=key))


def test_a_wrapped_union_ordered_by_a_foreign_qualifier_is_not_canonical() -> None:
    # An ordering key names the result alias its contributor was allocated above,
    # taken against the union alias — never a branch's own spelling.
    assert not is_canonical(_WRAPPED_UNION.replace("order by u.title", "order by t0.title", 1))
    assert not is_canonical(_WRAPPED_UNION.replace("order by u.title", "order by u.missing", 1))


@pytest.mark.parametrize(
    "tail",
    [
        pytest.param("order by 1", id="ordinal"),
        pytest.param("order by ?", id="bind"),
        pytest.param("order by 'title'", id="constant"),
        pytest.param("order by random()", id="foreign-function"),
        pytest.param("order by upper(u.title)", id="folded-alias"),
        pytest.param("order by u.id + u.title", id="two-aliases"),
        pytest.param("order by cast(u.title as varchar(64))", id="cast-without-extraction"),
    ],
)
def test_a_wrapped_union_ordered_by_anything_but_an_alias_key_is_not_canonical(tail: str) -> None:
    # m-sql fixes the whole key, not just its qualifier: an ordering key is the result
    # alias, or the document extraction over it under its declared cast. A key naming
    # no alias sorts on something the union does not answer, and one folding an alias
    # sorts on a value no member has.
    assert not is_canonical(_WRAPPED_UNION.replace("order by u.title desc", tail, 1), "postgres")


def test_a_wrapped_union_ordered_by_an_extraction_over_the_alias_is_canonical() -> None:
    # The positive twin: a key over a Structured Column member lowers to the same
    # extraction a predicate over it does — under the same declared cast, in each
    # dialect's own spelling — taken against the union alias.
    extracted = (
        "select u.id, u.payload from "
        "(select t0.id, t0.payload from publication_book t0 "
        "union all "
        "select t0.id, t0.payload from publication_film t0) u "
        "order by {key} desc"
    )
    assert is_canonical(extracted.format(key="jsonb_extract_path_text(u.payload, ?)"), "postgres")
    assert is_canonical(
        extracted.format(key="cast(jsonb_extract_path_text(u.payload, ?) as decimal(18, 2))"),
        "postgres",
    )
    assert is_canonical(extracted.format(key="json_value(u.payload, ?)"), "mariadb")


def test_a_malformed_wrapper_is_refused_rather_than_scored_as_one_select() -> None:
    # Declining a malformed wrapper is not the same as refusing it: a declined wrapper
    # keeps its branches in the outer scope, where a globally numbered `t0, t1, …`
    # sequence satisfies rule 1 and the statement is accepted outright.
    globally_numbered = (
        "select x.id, x.title from "
        "(select t0.id, t0.title from invoice t0 "
        "union all "
        "select t1.id, t1.title from memo t1) x order by x.title desc limit ?"
    )
    assert not is_canonical(globally_numbered, "postgres")


def test_an_unwrapped_union_carrying_a_result_tail_is_not_canonical() -> None:
    # The wrap exists BECAUSE a `union all` has no clause tail of its own, so a tail
    # hung directly on the set operation is the shape the wrap replaces.
    bare = "select t0.id from invoice t0 union all select t0.id from memo t0"
    assert is_canonical(bare, "postgres")
    assert not is_canonical(f"{bare} order by id", "postgres")
    assert not is_canonical(f"{bare} limit ?", "postgres")


# --- only `union all` is a canonical set operation ----------------------------
# `union all` is the ONLY canonical m-sql set operation (the TPCS abstract-read
# lowering). A plain `union` silently DE-DUPLICATES rows — changing the read's
# semantics — and `intersect` / `except` are never emitted; all three are non-canonical
# and MUST be rejected, or a golden that used the wrong set op would slip past the lint.
# Reproduce-then-green: before the fix `_canonical_select_scopes` walked any
# `SetOperation`, so these were wrongly accepted as canonical.


def test_plain_union_is_not_canonical() -> None:
    # Same branches as the canonical golden but a de-duplicating `union` (not `union all`).
    plain = "select t0.id from invoice t0 union select t0.id from receipt t0"
    assert not is_canonical(plain, "postgres")


def test_intersect_and_except_are_not_canonical() -> None:
    assert not is_canonical("select t0.id from invoice t0 intersect select t0.id from receipt t0")
    assert not is_canonical("select t0.id from invoice t0 except select t0.id from receipt t0")


def test_union_all_remains_canonical() -> None:
    # The positive twin: `union all` stays a canonical fixed point.
    assert is_canonical("select t0.id from invoice t0 union all select t0.id from receipt t0")


def test_nested_plain_union_inside_union_all_is_not_canonical() -> None:
    # A single non-`union all` arm anywhere in the tree taints the whole statement.
    mixed = (
        "select t0.id from invoice t0 union all "
        "select t0.id from receipt t0 union "
        "select t0.id from memo t0"
    )
    assert not is_canonical(mixed, "postgres")


# --- MariaDB `union all` + `char` NULL-placeholder casts ----------------------
# The TPCS abstract-read goldens run on BOTH dialects. MariaDB's CAST target grammar
# does not accept `varchar`, so a bounded-string placeholder casts to `char(n)`
# (m-dialect); `decimal(p, s)` is identical on both. The MariaDB golden must be a
# normalization fixed point under the `mariadb` dialect.
_TPCS_ROOT_UNION_MARIADB = (
    "select t0.id, t0.title, t0.currency, t0.amount_due, "
    "cast(null as decimal(18, 2)) paid_amount, cast(null as char(64)) body, "
    "'Invoice' family_variant from invoice t0 "
    "union all "
    "select t0.id, t0.title, t0.currency, cast(null as decimal(18, 2)) amount_due, "
    "t0.paid_amount, cast(null as char(64)) body, 'Receipt' family_variant "
    "from receipt t0 "
    "union all "
    "select t0.id, t0.title, cast(null as char(3)) currency, "
    "cast(null as decimal(18, 2)) amount_due, cast(null as decimal(18, 2)) paid_amount, "
    "t0.body, 'Memo' family_variant from memo t0"
)


def test_mariadb_union_all_char_cast_is_a_fixed_point() -> None:
    assert is_canonical(_TPCS_ROOT_UNION_MARIADB, "mariadb")
    assert normalize(_TPCS_ROOT_UNION_MARIADB, "mariadb") == _TPCS_ROOT_UNION_MARIADB


def test_mariadb_varchar_cast_normalizes_to_char() -> None:
    # A MariaDB golden authored with `varchar` is NOT a fixed point: sqlglot's mysql
    # dialect renders the CAST target as `char`, so lint would reject the `varchar`
    # spelling — the mechanism that keeps the MariaDB goldens honest.
    authored = "select cast(null as varchar(3)) currency, t0.id from memo t0"
    expected = "select cast(null as char(3)) currency, t0.id from memo t0"
    assert normalize(authored, "mariadb") == expected
    assert not is_canonical(authored, "mariadb")


def test_union_all_rejects_non_canonical_branch_alias() -> None:
    # A bad alias in ONE branch fails the whole statement (rule 1, per branch).
    bad = "select o.id from invoice o union all select t0.id from receipt t0"
    assert not is_canonical(bad, "postgres")


def test_union_all_rejects_unqualified_column_in_a_branch() -> None:
    bad = "select id from invoice t0 union all select t0.id from receipt t0"
    assert not is_canonical(bad, "postgres")


def test_union_all_rejects_inline_literal_in_a_branch() -> None:
    # A parameter literal in any branch must be a ? bind (rule 4).
    bad = "select t0.id from invoice t0 where t0.id = 5 union all select t0.id from receipt t0"
    assert not is_canonical(bad, "postgres")


# --- string literals + NULL-placeholder casts (the union-all projection) -----
# String literals (the `familyVariant` branch literal) and cast(null as <type>)
# NULL placeholders appear in canonical m-sql only via the TPCS lowering. The
# literal keeps its single quotes and case; a parametrized type binds its length
# list tight (`decimal(18, 2)`, not `decimal (18, 2)`).


def test_string_literal_is_requoted_and_case_preserved() -> None:
    canonical = "select 'Invoice' family_variant from invoice t0"
    assert is_canonical(canonical, "postgres")
    # sqlglot strips the surrounding quotes on re-tokenize; the normalizer re-wraps
    # them, and the literal's case is not lowered.
    assert normalize("select 'Invoice' AS family_variant from invoice t0", "postgres") == canonical


def test_null_placeholder_cast_binds_type_params_tight() -> None:
    canonical = "select cast(null as decimal(18, 2)) amount_due, t0.id from invoice t0"
    assert is_canonical(canonical, "postgres")
    # `numeric` canonicalizes to `decimal`, and the length list renders tight to the
    # type name rather than with an interposed space.
    assert (
        normalize(
            "select cast(null as numeric(18,2)) amount_due, t0.id from invoice t0", "postgres"
        )
        == canonical
    )


# --- flat grouped `OR` of per-branch correlated EXISTS (m-sql rule 1) ---------
# A table-per-concrete-subtype polymorphic semi-join lowers to a grouped `OR` of one
# correlated `EXISTS` per concrete branch (m-navigate / m-sql; the corpus witness is
# m-inheritance-070). The canonical form is the FLAT left-deep spine `a or b or c`
# with the branch tables numbered `t1, t2, t3` in a single source-order sequence
# (continuing the outer `t0`). A right-nested fold `a or (b or c)` is NOT a second
# canonical form — it normalizes to the flat spine.

_FLAT_GROUPED_OR = (
    "select t0.id, t0.name from folder t0 where "
    "(exists (select 1 from invoice t1 where t1.folder_id = t0.id) "
    "or exists (select 1 from memo t2 where t2.folder_id = t0.id) "
    "or exists (select 1 from receipt t3 where t3.folder_id = t0.id))"
)

_FOLDED_GROUPED_OR = (
    "select t0.id, t0.name from folder t0 where "
    "(exists (select 1 from invoice t1 where t1.folder_id = t0.id) "
    "or (exists (select 1 from memo t2 where t2.folder_id = t0.id) "
    "or exists (select 1 from receipt t3 where t3.folder_id = t0.id)))"
)


def test_flat_grouped_or_exists_is_a_normalization_fixed_point() -> None:
    # The flat three-branch grouped `OR` is canonical: it is the golden form of
    # m-inheritance-070, and normalizing it is idempotent.
    assert is_canonical(_FLAT_GROUPED_OR, "postgres")
    assert normalize(_FLAT_GROUPED_OR, "postgres") == _FLAT_GROUPED_OR


def test_folded_grouped_or_normalizes_to_the_flat_form() -> None:
    # The right-nested fold `a or (b or c)` — the shape a contributor previously had
    # to hand-author so the branch tables numbered in source order — is now
    # non-canonical and normalizes to the single flat canonical form. This is the
    # reassociation (m-sql rule 1) that removes the need for the fold.
    assert not is_canonical(_FOLDED_GROUPED_OR, "postgres")
    assert normalize(_FOLDED_GROUPED_OR, "postgres") == _FLAT_GROUPED_OR


def test_grouped_or_uses_a_single_global_source_order_alias_sequence() -> None:
    # Scheme (A): the branch tables continue the outer `t0` in ONE global sequence
    # (`t1, t2, t3`), they do NOT restart per subquery. A per-subquery-restart
    # spelling (every branch `t1`) is rejected — the sibling tables are not in
    # source order `t1, t2, t3`.
    per_branch_restart = (
        "select t0.id, t0.name from folder t0 where "
        "(exists (select 1 from invoice t1 where t1.folder_id = t0.id) "
        "or exists (select 1 from memo t1 where t1.folder_id = t0.id) "
        "or exists (select 1 from receipt t1 where t1.folder_id = t0.id))"
    )
    assert not is_canonical(per_branch_restart, "postgres")


def test_flat_grouped_or_rejects_out_of_source_order_branch_aliases() -> None:
    # The branches must number in the order they are written; a scrambled sequence
    # (memo `t1` before invoice `t2`, though invoice is written first) is rejected.
    scrambled = (
        "select t0.id, t0.name from folder t0 where "
        "(exists (select 1 from invoice t2 where t2.folder_id = t0.id) "
        "or exists (select 1 from memo t1 where t1.folder_id = t0.id))"
    )
    assert not is_canonical(scrambled, "postgres")


def test_sibling_correlated_exists_number_globally_t1_t2() -> None:
    # Two independent (ANDed) correlated `EXISTS` in one predicate — the existing
    # value-object shape (m-value-object-018) — alias `t1` and `t2` in one global
    # sequence, not `t1`/`t1`. This is the convention scheme (A) preserves.
    canonical = (
        "select t0.id from customer t0 where "
        "exists (select 1 from phone t1 where t1.customer_id = t0.id and t1.kind = ?) "
        "and exists (select 1 from phone t2 where t2.customer_id = t0.id and t2.kind = ?)"
    )
    assert is_canonical(canonical, "postgres")
    per_branch_restart = (
        "select t0.id from customer t0 where "
        "exists (select 1 from phone t1 where t1.customer_id = t0.id and t1.kind = ?) "
        "and exists (select 1 from phone t1 where t1.customer_id = t0.id and t1.kind = ?)"
    )
    assert not is_canonical(per_branch_restart, "postgres")


def test_reassociation_preserves_precedence_significant_parentheses() -> None:
    # Reassociation only flattens SAME-connector chains. A parenthesis over a
    # DIFFERENT connector is precedence-significant and MUST survive, so a mixed
    # `and (… or …)` predicate is left untouched (a fixed point).
    mixed = "select t0.id from orders t0 where t0.a = ? and (t0.b = ? or t0.c = ?)"
    assert is_canonical(mixed, "postgres")
    assert normalize(mixed, "postgres") == mixed


def test_reassociation_flattens_a_nested_and_chain() -> None:
    # `and` is associative too: a right-nested `a and (b and c)` normalizes to the
    # flat left-deep spine, matching how a flat `a and b and c` is stored.
    folded = "select t0.id from orders t0 where t0.a = ? and (t0.b = ? and t0.c = ?)"
    flat = "select t0.id from orders t0 where t0.a = ? and t0.b = ? and t0.c = ?"
    assert not is_canonical(folded, "postgres")
    assert normalize(folded, "postgres") == flat
    assert is_canonical(flat, "postgres")
