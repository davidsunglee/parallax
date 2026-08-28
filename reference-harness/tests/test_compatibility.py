"""Discover every compatibility case and run it through the layered assertions.

For each available database provider (selected by ``PARALLAX_DATABASES``,
default: all registered), one container is booted for the whole module and every
case whose outcome depends on the dialect is run against it. This is the
m-case-format runner exercising the suite end-to-end: schema conformance, triple
equivalence, normalization determinism, and serde round-trip — against real
Postgres.

Requires Docker (Testcontainers). If no provider can be started, the suite errors
rather than silently passing, because the walking skeleton's whole point is the
real-database run.

The module's second half is the same runner exercised from the other side: a
shipped case damaged in one specific way, asserted to be REFUSED. It lives here
because the harness designates exactly one entry point to a live database — the
``provider`` fixture below — and both directions of the runner need one.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import Case, dialect_executed_cases, discover_cases
from reference_harness.case_runner import (
    CaseFailure,
    _composed_seek,
    _continuation_order,
    _direct_term,
    _PageText,
    _refuse_a_drifting_page,
    _render_seek,
    run_case,
)
from reference_harness.inheritance import validate_family
from reference_harness.providers import available_dialects, provider_for
from reference_harness.storage_layout import validate_storage_layout

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"

# The excluded cases still round-trip through schema validation
# (test_schema_validate) and the profile gate (test_dep_graph); test_rejected.py
# is the sole runner for the `rejected` shape and pins the partition.
ALL_CASES = discover_cases(COMPATIBILITY_ROOT)
CASES = dialect_executed_cases(COMPATIBILITY_ROOT)
DIALECTS = available_dialects()


def _case_id(case) -> str:
    # Include the case's tags in the test id so module/feature selectors work,
    # e.g. ``pytest -k m-predicate`` runs every algebra case and ``pytest -k group`` runs
    # the group-precedence pair. Tags are sanitized to id-safe tokens.
    tags = "-".join(tag.replace(" ", "_") for tag in case.tags)
    return f"{case.path.stem}-{tags}" if tags else case.path.stem


@pytest.fixture(scope="session", params=DIALECTS)
def provider(request):
    dialect = request.param
    with provider_for(dialect) as db:
        yield db


def test_cases_discovered() -> None:
    assert CASES, "no compatibility cases discovered under core/compatibility/cases"


def test_api_conformance_lane_cases_are_not_executed() -> None:
    # DB-free pin: the api-conformance lane is filtered out of the executed set (the
    # m-case-format harness only schema-validates it), yet the cases DO exist in the corpus —
    # a regression that silently ran or dropped them fails here without Docker.
    executed = {c.path.name for c in CASES}
    skipped = {c.path.name for c in ALL_CASES if c.lane == "api-conformance"}
    assert skipped, "expected some api-conformance-lane cases in the corpus"
    assert executed.isdisjoint(skipped), "an api-conformance case leaked into the executed set"
    for case in ALL_CASES:
        if case.lane == "api-conformance":
            # run_case must early-return (schema-validate only) without a database —
            # None is a safe stand-in because no provisioning/execution is reached.
            run_case(case, None)  # type: ignore[arg-type]


def test_a_dialect_is_available() -> None:
    assert DIALECTS, (
        "no database providers available; set PARALLAX_DATABASES or ensure a provider is registered"
    )


@pytest.mark.parametrize("case", CASES, ids=[_case_id(c) for c in CASES])
def test_case(case, provider) -> None:
    run_case(case, provider)


# --------------------------------------------------------------------------
# The streamed-delivery oracle: a delivery that reached the right rows the
# wrong way is refused (m-case-format "Streamed reads")
#
# A streamed case's `then.statements` is the pages' own `1 + L` groups
# concatenated, so almost everything that makes a stream a stream lives in the
# page partition rather than in the graph: the size each page asks for, the
# coordinates each later page continues from, and the statement a full final page
# costs to prove exhaustion. A grader that only assembled the roots and compared
# them to `then.graph` would accept every delivery below, which is why each is
# authored as a refusal rather than left to the corpus's own green run. The
# undamaged form of each case passes as an ordinary member of the sweep above.
# --------------------------------------------------------------------------

_DEEP_FETCH = "m-snapshot-read-027-streamed-deep-fetch"
_TERMINAL_PAGE = "m-snapshot-read-028-stream-empty-terminal-page"
_MIXED_DIRECTIONS = "m-snapshot-read-031-stream-order-mixed-directions"
_NULLABLE_PLACEMENT = "m-snapshot-read-032-stream-order-nullable-placement"
_MULTI_TERM_SEEK = "m-snapshot-read-033-stream-order-multi-term-seek"
_DOCUMENT_RESIDENT = "m-snapshot-read-035-stream-order-document-resident"

# The Document Path spellings the resident case's pages carry, per dialect: one
# hole per segment on Postgres, one whole JSON path on MariaDB.
_RESIDENT_EXTRACTIONS = {
    "postgres": (
        "cast(jsonb_extract_path_text(t0.payload, ?) as bigint)",
        "jsonb_extract_path_text(t0.payload, ?)",
    ),
    "mariadb": (
        "cast(json_value(t0.payload, ?) as signed)",
        "json_value(t0.payload, ?)",
    ),
}


# The same extraction under a target m-dialect does NOT give `nights`, spelled so
# that it orders the fixture's values exactly as the declared target does.
_RETARGETED_RESIDENT_CAST = {
    "postgres": "cast(jsonb_extract_path_text(t0.payload, ?) as decimal(18, 2))",
    "mariadb": "cast(json_value(t0.payload, ?) as decimal(18, 2))",
}


def _respell_resident_pages(case: Case, was: str, now: str) -> None:
    """Rewrite every continuing page of the resident case, each dialect its own way."""
    for entry in _statements(case)[1:]:
        entry["sql"] = {
            dialect: sql.replace(
                was.format(*_RESIDENT_EXTRACTIONS[dialect]),
                now.format(*_RESIDENT_EXTRACTIONS[dialect]),
            )
            for dialect, sql in entry["sql"].items()
        }


def _damaged(stem: str) -> Case:
    """A writable copy of the shipped case named *stem*."""
    return copy.deepcopy(next(case for case in ALL_CASES if case.path.stem == stem))


def _statements(case: Case) -> list[dict[str, Any]]:
    return case.then["statements"]


def test_a_page_seeking_from_the_wrong_root_is_refused(provider) -> None:
    """The continuation is the previous page's LAST root, derived rather than trusted."""
    case = _damaged(_DEEP_FETCH)
    _statements(case)[3]["binds"][3] = 1

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        run_case(case, provider)


def test_a_page_asking_for_the_wrong_size_is_refused(provider) -> None:
    """The requested size is `batchSize`, not whatever the golden happens to bind."""
    case = _damaged(_DEEP_FETCH)
    _statements(case)[0]["binds"][-1] = 3

    with pytest.raises(CaseFailure, match="the size it is asking for"):
        run_case(case, provider)


def test_a_delivery_ending_on_a_full_page_is_refused(provider) -> None:
    """A full final page proves nothing, so dropping the terminal statement fails."""
    case = _damaged(_TERMINAL_PAGE)
    del _statements(case)[4]
    case.then["roundTrips"] = 4

    with pytest.raises(CaseFailure, match="the delivery is not exhausted"):
        run_case(case, provider)


def test_a_statement_after_the_delivery_ended_is_refused(provider) -> None:
    """A stream stops at its first short page, so nothing may follow it."""
    case = _damaged(_DEEP_FETCH)
    entries = _statements(case)
    entries.append(copy.deepcopy(entries[3]))
    case.then["roundTrips"] = 7

    with pytest.raises(CaseFailure, match="after the delivery ended"):
        run_case(case, provider)


def test_a_continuing_page_that_does_not_seek_is_refused(provider) -> None:
    """A continuing page carries a conjunct the first page has no coordinate for.

    The bind oracle alone would accept this: the binds are unchanged and still
    name the right coordinate. What refuses it is that the two root SQL texts are
    equal, which no keyset-paged delivery can produce.
    """
    case = _damaged(_DEEP_FETCH)
    entries = _statements(case)
    entries[3]["sql"] = copy.deepcopy(entries[0]["sql"])

    with pytest.raises(CaseFailure, match="repeats the FIRST page's root SQL"):
        run_case(case, provider)


def test_a_page_hoisting_the_wrong_leading_coordinate_is_refused(provider) -> None:
    """The hoisted range is DERIVED from the leading term's own coordinate.

    Its bind repeats a value the remainder binds again, so a golden that got it
    wrong still selects a plausible row set — and here selects the right one, the
    remainder being unchanged. What refuses it is that the derivation says which
    coordinate the range compares against.
    """
    case = _damaged(_MIXED_DIRECTIONS)
    _statements(case)[1]["binds"][0] = False

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        run_case(case, provider)


def test_a_page_binding_the_wrong_tie_coordinate_is_refused(provider) -> None:
    """Every term of the order supplies its own coordinate, at every tie depth.

    The damaged bind is the second branch's `qty` coordinate — neither the
    leading term nor the primary key — so an oracle that continued from the last
    root's KEY alone, as a single-term order allows, would accept it.
    """
    case = _damaged(_MIXED_DIRECTIONS)
    _statements(case)[1]["binds"][3] = 5

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        run_case(case, provider)


def test_a_page_dropping_its_hoisted_range_is_refused(provider) -> None:
    """The range is redundant by rows and required by contract.

    Removing it leaves a statement that selects exactly the same roots, so every
    result-level oracle passes; the delivery has simply given up the leading
    index range a non-nullable leading term is entitled to.
    """
    case = _damaged(_MIXED_DIRECTIONS)
    entry = _statements(case)[1]
    entry["sql"] = {
        dialect: sql.replace("where t0.active <= ? and (", "where (")
        for dialect, sql in entry["sql"].items()
    }
    del entry["binds"][0]

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        run_case(case, provider)


def test_a_continuing_page_respelling_its_seek_is_refused(provider) -> None:
    """Two pages seeking coordinates of the same NULLNESS seek the same way.

    The damaged page reorders one disjunction, which no bind comparison sees: the
    binds are unchanged, in the same positions, and the statement selects exactly
    the same rows. Only the text is different, and a delivery whose page
    statements drift apart is one whose seek is not a function of its order.
    """
    case = _damaged(_NULLABLE_PLACEMENT)
    entry = _statements(case)[2]
    entry["sql"] = {
        dialect: sql.replace(
            "where (t0.sku > ? or t0.sku is null or", "where (t0.sku is null or t0.sku > ? or"
        )
        for dialect, sql in entry["sql"].items()
    }

    with pytest.raises(CaseFailure, match="seeking the same shape of coordinates"):
        run_case(case, provider)


def test_a_page_seeking_the_wrong_WAY_past_the_right_coordinates_is_refused(provider) -> None:
    """A page's binds carry its coordinates and never the direction it compares them in.

    The damaged page is the terminal one, whose coordinates are null where no
    other page's are, so no sibling page constrains its text; its binds are
    untouched and correct; and it still returns nothing, the one root it could
    have reached having been delivered already. Every other oracle here passes.
    What refuses it is that the Continuation Order composes the comparator, and
    an ascending term is never sought backwards.
    """
    case = _damaged(_NULLABLE_PLACEMENT)
    entry = _statements(case)[3]
    entry["sql"] = {
        dialect: sql.replace("t0.id > ?", "t0.id < ?") for dialect, sql in entry["sql"].items()
    }

    with pytest.raises(CaseFailure, match="seeks .*, not "):
        run_case(case, provider)


def test_continuing_pages_drifting_outside_their_seek_are_refused(provider) -> None:
    """A continuing page is the first page's statement plus the seek, and nothing else.

    Every continuing page here reverses the same ordering term, so they still
    agree with each other and the same-shape rule sees nothing; the seek they
    spell is untouched and so are their binds. What refuses it is that the pages
    no longer read the same rows the same way: a delivery whose later pages
    reorder themselves is not one read paged.
    """
    case = _damaged(_MULTI_TERM_SEEK)
    for index in (2, 4, 6):
        entry = _statements(case)[index]
        entry["sql"] = {
            dialect: sql.replace(
                "order by t0.active asc, t0.id desc", "order by t0.active asc, t0.id asc"
            )
            for dialect, sql in entry["sql"].items()
        }

    with pytest.raises(CaseFailure, match="ONE conjunct spliced into it"):
        run_case(case, provider)


def test_a_continuing_page_negating_its_seek_is_refused(provider) -> None:
    """A seek is the expression an order COMPOSES, not the comparisons it mentions.

    The damaged page mentions exactly the comparisons and null checks its own
    coordinates compose, in exactly their order, and binds exactly what a correct
    page binds. It is the terminal one, whose null coordinate no sibling page's
    text constrains, and it still returns nothing. Only the Boolean shape is
    different, and a Continuation Order composes no negation at any depth.
    """
    case = _damaged(_NULLABLE_PLACEMENT)
    entry = _statements(case)[3]
    entry["sql"] = {
        dialect: sql.replace("t0.id > ?", "not not t0.id > ?")
        for dialect, sql in entry["sql"].items()
    }

    with pytest.raises(CaseFailure, match="seeks .*, not "):
        run_case(case, provider)


def test_a_resident_branch_that_dropped_its_grouping_is_not_authorable(provider) -> None:
    """A tie's own two-way branch has to be grouped, and no golden may spell it flat.

    Ungrouped, `and` binds tighter than `or`, so the second branch becomes
    "destination at its coordinate and nights strictly after its own" OR "nights
    is null" — which admits every null-`nights` trip in the table whatever its
    destination, re-delivering roots the stream already published. The fixtures
    have no such trip, so the damaged pages return exactly the rows the correct
    ones return and bind exactly what they bind. What refuses them is the
    canonical-SQL rule rather than the seek oracle behind it: a disjunction
    grouped directly inside a disjunction is not a spelling m-sql admits, so the
    flat branch has no authorable form and the seek it would compose is never
    reached.
    """
    case = _damaged(_DOCUMENT_RESIDENT)
    _respell_resident_pages(case, "and ({0} < ? or {1} is null))", "and {0} < ? or {1} is null)")

    with pytest.raises(CaseFailure, match="is not canonical"):
        run_case(case, provider)


def test_a_resident_null_check_spelled_against_the_cast_is_refused(provider) -> None:
    """Presence is asked of the extraction, and the cast is not part of the question.

    Casting before a null test selects the same rows — a cast of NULL is NULL — so
    the damaged pages deliver the same graph and bind the same paths in the same
    places. What differs is that the statement claims the declared type stands
    between the document and a presence question that never asks it.
    """
    case = _damaged(_DOCUMENT_RESIDENT)
    _respell_resident_pages(case, "or {1} is null))", "or {0} is null))")

    with pytest.raises(CaseFailure, match="seeks .*, not "):
        run_case(case, provider)


def test_a_resident_comparison_that_dropped_its_cast_is_refused(provider) -> None:
    """A member whose document form does not order as text compares under its cast.

    `nights` is an `int32`, so the damaged page compares `"7"` against `"1"` as
    text. Both fixture values are single digits, so the rows and the ordering are
    unchanged and every bind still lands where it did — the statement simply stops
    claiming the cast m-dialect's table gives the numeric family.
    """
    case = _damaged(_DOCUMENT_RESIDENT)
    _respell_resident_pages(case, "{0} < ?", "{1} < ?")

    with pytest.raises(CaseFailure, match="seeks .*, not "):
        run_case(case, provider)


def test_a_resident_comparison_under_ANOTHER_cast_target_is_refused(provider) -> None:
    """A cast is graded down to the target m-dialect's table names for the type.

    The damaged pages still cast, and to a target that orders the fixture's
    `nights` exactly as the declared one does — so they select the same rows, hand
    the next page the same cursor, and bind what a correct page binds. Nothing
    downstream of the statement can tell them apart: only the target itself says
    which type the comparison claims to be in.
    """
    case = _damaged(_DOCUMENT_RESIDENT)
    for entry in _statements(case)[1:]:
        entry["sql"] = {
            dialect: sql.replace(
                f"{_RESIDENT_EXTRACTIONS[dialect][0]} <", f"{_RETARGETED_RESIDENT_CAST[dialect]} <"
            ).replace(
                f"{_RESIDENT_EXTRACTIONS[dialect][0]} =", f"{_RETARGETED_RESIDENT_CAST[dialect]} ="
            )
            for dialect, sql in entry["sql"].items()
        }

    with pytest.raises(CaseFailure, match="seeks .*, not "):
        run_case(case, provider)


def test_a_resident_page_binding_the_wrong_path_first_is_refused(provider) -> None:
    """Which member an extraction reads is a BIND, so the paths are graded as binds.

    Two resident terms over one Structured Column spell one expression and are
    told apart only by the Document Paths their holes carry, in the order the seek
    composes them. Swapping the leading branch's path for the second term's leaves
    the statement text untouched.
    """
    case = _damaged(_DOCUMENT_RESIDENT)
    for entry in _statements(case)[1:]:
        for dialect, binds in entry["binds"].items():
            entry["binds"][dialect] = [*binds]
            entry["binds"][dialect][0] = binds[5]

    with pytest.raises(CaseFailure, match="root binds"):
        run_case(case, provider)


# --------------------------------------------------------------------------
# The milestone edge: a streamed milestone set's own third order component
# (m-snapshot-read "Streamed delivery")
#
# A milestone-set read puts every milestone of one key in the result at once, so
# the primary key stops separating roots and the edge is what does. The two
# refusals below are the two ways a delivery can get that wrong while still
# reaching plausible rows: seeking past the key alone, which crosses a boundary
# inside one object's own history, and continuing from a coordinate that is a
# milestone of the right object but not the one the page ended on.
# --------------------------------------------------------------------------

_HISTORY_BOUNDARY = "m-snapshot-read-036-stream-history-page-boundary"
_MILESTONE_EDGE_PINS = "m-snapshot-read-037-stream-milestone-edge-pins"


def test_a_milestone_page_seeking_past_the_key_alone_is_refused(provider) -> None:
    """A page that dropped the edge from its seek still reaches real rows.

    Damaged this way, page 2 asks for everything after line 1000 rather than
    after line 1000's FIRST milestone, which is exactly the skip the edge exists
    to prevent — and the rows it returns are a legal suffix of the result, so
    nothing about the page itself looks wrong. What refuses it is that the seek
    is derived from the Continuation Order, whose last term is the edge.
    """
    case = _damaged(_HISTORY_BOUNDARY)
    for entry in _statements(case)[1:]:
        entry["sql"] = {
            dialect: sql.replace(
                "and t0.id >= ? and (t0.id > ? or (t0.id = ? and t0.in_z > ?))", "and t0.id > ?"
            )
            for dialect, sql in entry["sql"].items()
        }
        entry["binds"] = [entry["binds"][0], entry["binds"][1], entry["binds"][-1]]

    with pytest.raises(CaseFailure, match="root binds"):
        run_case(case, provider)


def test_a_milestone_page_continuing_from_another_milestone_is_refused(provider) -> None:
    """The coordinate is the edge of the root the previous page ENDED on.

    Every bind here names a real milestone of the object the page is continuing
    through, and the damaged page still returns rows in the right order — it
    simply resumes from the wrong rectangle. Only the derivation says which.
    """
    case = _damaged(_MILESTONE_EDGE_PINS)
    binds = _statements(case)[2]["binds"]
    binds[7] = _statements(case)[1]["binds"][7]

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        run_case(case, provider)


def test_a_streamed_milestone_graph_claiming_the_wrong_root_is_refused(provider) -> None:
    """`then.graphs` states which milestone each DELIVERED root stands at.

    Moving one root between two declared graphs leaves the delivery, its pages,
    and its seek coordinates untouched, and the two graphs still hold every root
    exactly once between them. What refuses it is the pin partition: a root is
    grouped by the edge it was published at, not by the entry that names it.
    """
    case = _damaged(_HISTORY_BOUNDARY)
    graphs = case.then["graphs"]
    graphs[1]["graph"]["InvoiceLine"].append(graphs[0]["graph"]["InvoiceLine"].pop())

    with pytest.raises(CaseFailure, match="assembled graph"):
        run_case(case, provider)


# --------------------------------------------------------------------------
# The same oracle at the member's SECOND placement: a streamed scenario READ
# step (m-case-format "Streamed read steps")
#
# A streamed step's own `statements` are a whole delivery's pages, so the step
# is graded page by page rather than as the one statement every other find step
# lists. What the placement adds beyond the delivery itself is the evidence the
# delivery hands over: the write that names it settles against the version THAT
# delivery observed, which is what the two refusals below and the one above them
# pin from three directions.
# --------------------------------------------------------------------------

_STREAMED_EVIDENCE = "m-unit-work-030-a-streamed-roots-evidence-licenses-a-later-write"


def _steps(case: Case) -> list[dict[str, Any]]:
    return case.when["scenario"]


def test_a_streamed_step_page_seeking_from_the_wrong_root_is_refused(provider) -> None:
    """A step's pages reach the delivery oracle, not a single-statement find path."""
    case = _damaged(_STREAMED_EVIDENCE)
    _steps(case)[0]["statements"][1]["binds"][0] = 1

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        run_case(case, provider)


def test_a_streamed_step_ending_on_a_full_page_is_refused(provider) -> None:
    """Dropping the short final page leaves a delivery that never proved exhaustion.

    A grader taking the step's FIRST statement and stopping would accept this: the
    remaining page still returns the two roots page 1 asked for.
    """
    case = _damaged(_STREAMED_EVIDENCE)
    del _steps(case)[0]["statements"][1]
    _steps(case)[0]["roundTrips"] = 1
    case.then["roundTrips"] = 5

    with pytest.raises(CaseFailure, match="the delivery is not exhausted"):
        run_case(case, provider)


def test_a_streamed_step_whose_roots_are_stated_out_of_delivery_order_is_refused(
    provider,
) -> None:
    """A delivery publishes in the Continuation Order, and only its rows grade that.

    The damage swaps the first and last root of the first delivery's `expectRows`
    and nothing else: the multiset is unchanged, both pages still ask for the same
    size, and the second page still seeks from the same coordinate — so every other
    oracle the step carries still passes, and only a positional row comparison
    refuses it.
    """
    case = _damaged(_STREAMED_EVIDENCE)
    rows = _steps(case)[0]["expectRows"]
    rows[0], rows[-1] = rows[-1], rows[0]

    with pytest.raises(CaseFailure, match="rows != expectRows"):
        run_case(case, provider)


def test_a_write_settling_against_the_OTHER_delivery_is_refused(provider) -> None:
    """Which delivery published the root decides the version the write gates on.

    The two deliveries observe account 1 at two generations, so a write naming the
    first one may not carry the second one's gate. The damage moves the step's `on`
    and nothing else: a grader reading the gate off the group's LATEST observation
    rather than off the delivery the step names accepts the case as authored, where
    each write already names the delivery that ran most recently before it.
    """
    case = _damaged(_STREAMED_EVIDENCE)
    _steps(case)[3]["on"] = 0

    with pytest.raises(CaseFailure, match="observed version 1, but its golden gate binds 2"):
        run_case(case, provider)


_NULLS_FIRST_TERMS = [
    _direct_term("sku", direction="asc", nulls="first", nullable=True),
    _direct_term("id", direction="asc", nulls="last", nullable=False),
]
_NULLS_FIRST_PAGE = (
    "select t0.id, t0.sku from orders t0 order by t0.sku asc nulls first, t0.id asc limit ?"
)


def _grade_a_page_past_a_null(case: Case, dialect: str, non_nulls: str, ties: str) -> None:
    """Grade the page continuing past a null `sku`, its two null tests spelled as given.

    Under Nulls First the null coordinate is followed by the non-nulls and by the
    ties it has not delivered yet, so the seek is one disjunction over exactly the
    two null tests this splices in.
    """
    continuing = (
        f"select t0.id, t0.sku from orders t0 where ({non_nulls} or "
        f"({ties} and t0.id > ?)) order by t0.sku asc nulls first, t0.id asc limit ?"
    )
    _refuse_a_drifting_page(
        _PageText(case, dialect, 1, _NULLS_FIRST_PAGE, continuing),
        _composed_seek(_NULLS_FIRST_TERMS, (None, 4)),
        (None, 4),
        {},
    )


def test_either_production_spelling_of_a_negated_null_check_is_accepted() -> None:
    """A valid continuation is accepted however its null check is written.

    Under Nulls First what follows a null coordinate is the non-nulls, which a
    page may spell `sku is not null` or `not sku is null`; sqlglot reads the
    first into the second's tree under MariaDB and keeps them apart under
    Postgres. Both are one leaf of the expression the order composes, so a seek
    graded as an expression must accept either on either dialect.
    """
    case = _damaged(_NULLABLE_PLACEMENT)
    for spelling in ("t0.sku is not null", "not t0.sku is null"):
        for dialect in ("postgres", "mariadb"):
            _grade_a_page_past_a_null(case, dialect, spelling, "t0.sku is null")


def test_a_DOUBLY_negated_null_check_is_refused_on_either_dialect() -> None:
    """One negation is a spelling of the leaf; two are a shape the order never composes.

    The damaged page selects exactly the rows a correct one selects — `not sku is
    not null` is `sku is null` — and binds exactly what a correct page binds, so
    only the composed Boolean shape tells them apart, and a Continuation Order
    composes no negation at any depth. sqlglot hands the dialects different trees
    for it: Postgres a `not` over a negated null test, MariaDB a `not` over a
    `not`. Folding the pair away rather than one negation would accept the
    Postgres tree and refuse the MariaDB one, making the same text's verdict
    depend on which parser read it.
    """
    case = _damaged(_NULLABLE_PLACEMENT)
    for dialect in ("postgres", "mariadb"):
        with pytest.raises(CaseFailure, match="seeks .*, not "):
            _grade_a_page_past_a_null(case, dialect, "t0.sku is not null", "not t0.sku is not null")


def test_a_direct_sort_key_spelled_like_a_document_member_is_accepted() -> None:
    """Residence belongs to the member, not to the Column spelling it would take.

    A document-resident member claims no Column, so it can neither establish a
    claim nor collide with one: the primary key here holds the physical column
    `score`, the very spelling the resident Attribute `score` carries, and the
    layout is valid. Ordering by `Traveler.id` therefore orders by a real Column
    that no extraction reaches, and the derivation this oracle refuses to make
    is not needed.
    """
    case = _damaged("m-storage-layout-020-document-layout-path-predicate-ordering")
    traveler = next(
        definition for definition in case.model.entity_defs if definition["name"] == "Traveler"
    )
    key = next(attribute for attribute in traveler["attributes"] if attribute["name"] == "id")
    key["column"] = "score"
    validate_storage_layout(case.model.entity_defs)

    query = {**case.object_query, "orderBy": [{"attr": "parallax.compatibility.Traveler.id"}]}
    entity = case.model.entity(query["target"])

    order = _continuation_order(case, query, entity, "postgres")
    assert [(term.column, term.compared, term.path_binds) for term in order] == [
        ("score", "score", ())
    ]


def test_a_sort_key_a_TPH_SIBLING_keeps_in_a_Column_of_its_own_is_accepted() -> None:
    """Disjoint siblings may reuse a member name, and each keeps its own placement.

    `m-inheritance` lets disjoint branches declare the same member name, and the
    two Payment siblings here both declare `code` over the one shared Table:
    CardPayment's is document-resident, while CashPayment's is a Relationship Join
    endpoint and so keeps the Column `b_code`. Both placements live in that one
    Table keyed by their declaring owners, so a CashPayment read ordered by `code`
    orders by a real Column that no extraction reaches — which only the owner
    distinguishes, the name and the document path being CardPayment's too.
    """
    case = _damaged("m-inheritance-124-document-layout-tph-sibling-path-reuse")
    siblings = {definition["name"]: definition for definition in case.model.entity_defs}
    siblings["CardPayment"]["attributes"].append(
        {"name": "code", "type": "string", "maxLength": 32, "nullable": True}
    )
    siblings["CashPayment"]["attributes"].append(
        {"name": "code", "type": "int64", "column": "b_code", "nullable": True}
    )
    siblings["CashPayment"]["relationships"] = [
        {
            "name": "trip",
            "cardinality": "many-to-one",
            "join": {
                "source": "code",
                "target": {"entity": "parallax.compatibility.Trip", "attribute": "id"},
            },
        }
    ]
    validate_storage_layout(case.model.entity_defs)
    validate_family({"entities": case.model.entity_defs})

    query = {
        "target": "parallax.compatibility.CashPayment",
        "orderBy": [{"attr": "parallax.compatibility.CashPayment.code"}],
    }
    entity = case.model.entity(query["target"])

    order = _continuation_order(case, query, entity, "postgres")
    assert [(term.column, term.compared, term.path_binds) for term in order] == [
        ("b_code", "b_code", ()),
        ("id", "id", ()),
    ]


def test_a_document_resident_sort_key_seeks_through_its_own_extraction() -> None:
    """A resident Sort Key is derived from, not refused, and per dialect.

    A member inside a Structured Column has no Column to name, so every one of
    its occurrences is the dialect's extraction over that column and binds a
    Document Path ahead of its own coordinate — one hole per segment on Postgres,
    one whole JSON path on MariaDB, so the same order is a different bind list on
    the two. `score` is an `int64`, whose document form does not order as text, so
    the comparisons go through its declared cast while the null check beside them
    asks the bare extraction.
    """
    case = _damaged("m-storage-layout-020-document-layout-path-predicate-ordering")
    query = case.object_query
    entity = case.model.entity(query["target"])

    order = _continuation_order(case, query, entity, "postgres")
    assert [(term.column, term.compared, term.tested, term.path_binds) for term in order] == [
        ("score", "cast(payload extraction as bigint)", "payload extraction", ("score",)),
        ("id", "id", "id", ()),
    ]
    assert [term.path_binds for term in _continuation_order(case, query, entity, "mariadb")] == [
        ("$.score",),
        (),
    ]

    seek = _composed_seek(order, (7, 1))
    assert _render_seek(seek.node) == (
        "(cast(payload extraction as bigint) < ? or payload extraction is null "
        "or (cast(payload extraction as bigint) = ? and id > ?))"
    )
    assert seek.binds == ("score", 7, "score", "score", 7, 1)


def test_a_document_resident_sort_key_at_a_SHARED_TABLE_position_is_derived() -> None:
    """One Structured Column is what a resident Sort Key needs, not a concrete position.

    The read is at a table-per-hierarchy root narrowed to one subtype, which is
    the ordering m-object-query admits over a subtype's own member. Every branch
    of that family shares the root's Table, so the member is resident in exactly
    one Structured Column and the extraction that seeks it has one spelling —
    which abstractness alone would have refused.
    """
    case = _damaged("m-inheritance-123-document-layout-tph-broad-read")
    query = case.object_query
    query["narrowTo"] = ["parallax.compatibility.CardPayment"]
    query["orderBy"] = [{"attr": "parallax.compatibility.CardPayment.detail"}]
    entity = case.model.entity(query["target"])

    order = _continuation_order(case, query, entity, "postgres")
    assert [(term.column, term.compared, term.tested, term.path_binds) for term in order] == [
        ("detail", "payload extraction", "payload extraction", ("detail",)),
        ("id", "id", "id", ()),
    ]


def test_a_document_resident_sort_key_at_a_TABLELESS_position_is_refused() -> None:
    """Residence belongs to a Table, and an abstract position holds none of its own.

    The read is at a table-per-concrete-subtype root: every concrete branch keeps
    `title` inside its own document, while the root itself has no Table to be
    asked. Asking only the position the Sort Key is resolved at answers that the
    member has an ordinary Column, and the order derived from that grades a
    delivery against coordinates no page ever binds alone.
    """
    case = _damaged("m-inheritance-136-tpcs-union-vo-projection")
    query = case.object_query
    entity = case.model.entity(query["target"])

    assert entity.table == ""
    with pytest.raises(CaseFailure, match="document-resident member"):
        _continuation_order(case, query, entity, "postgres")
