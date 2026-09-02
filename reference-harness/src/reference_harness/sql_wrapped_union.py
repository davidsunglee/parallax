"""The oracle for the derived table an ordered or limited abstract read wraps its
``union all`` as (m-sql).

A ``union all`` carries no clause tail of its own, so the table-per-concrete-subtype
lowering of a read that authored Sort Keys or a cap wraps the whole union as the
derived table ``u`` and applies the result-shape tail against that alias. This module
holds what recognizing and grading that wrap takes: the model and query facts no
statement carries (:class:`WrapFacts`, :class:`WrapOrderKey`), the m-dialect decisions
the tail turns on, and the projection, ordering, and cap verifiers.

:func:`wrapped_union_source` is the entry point. Called with facts it grades the wrap
against the read it lowers; called without them — as ``sql_normalize`` does, holding no
model — it grades every shape a statement alone settles and admits the readings it does
not.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.expressions.core import Expr

from .sql_canonical import NonCanonicalError, sqlglot_dialect

# The alias m-sql gives the derived table an ordered or limited abstract read wraps
# its union as, and the clauses that wrap may carry outward.
_WRAP_ALIAS = "u"
_WRAP_TAIL = ("order", "limit")
_WRAP_FORBIDDEN = ("joins", "where", "group", "having", "distinct", "locks", "offset")


@dataclass(frozen=True, slots=True)
class WrapOrderKey:
    """One authored Sort Key as the wrap's ``order by`` must render it.

    ``alias`` is the union result alias the key reaches: its contributor's own where
    the layout gave the member a Column, and the Structured Column's where it did not.
    ``document_path`` is empty in the first case and the member's Document Path in the
    second, where the key lowers to that dialect's extraction under the ``neutral_type``
    cast the same member's predicate takes (``m-dialect`` *Typed cast form*).

    ``nullable`` is the key's DECLARED nullability: the positional rule
    (``m-object-query``) admits a Sort Key only over a member applicable to every
    concrete in the read's position, so the key never meets a branch's typed ``NULL``
    placeholder and no branch's effective nullability widens it.
    """

    alias: str
    descending: bool
    nulls_first: bool
    nullable: bool
    document_path: tuple[str, ...] = ()
    neutral_type: str | None = None


@dataclass(frozen=True, slots=True)
class WrapFacts:
    """The model and query facts the wrap's canonical shape depends on.

    A statement's TEXT carries none of them: which result alias holds a ``Document``,
    which Sort Keys the read authored, and the cap it declared are all facts of the
    model and the Object Query behind the statement, and the values its ``?`` holes
    stand for are authored beside the text rather than in it. A caller holding them
    supplies them so the wrap is graded against the read it lowers, rather than
    against the widest shape SQL alone admits.

    ``limit`` is the authored cap itself, not merely whether one exists, so the tail's
    cap bind is compared with the row count the query asked for. ``binds`` is the whole
    statement's bind list in order; the tail's own binds are its trailing entries,
    because a wrap's binds follow every branch's (m-sql). ``None`` where the caller has
    no bind list to grade against.
    """

    document_aliases: frozenset[str]
    order_keys: tuple[WrapOrderKey, ...]
    limit: int | None = None
    binds: tuple[object, ...] | None = None


def _wrap_column(node: Expr | None) -> str | None:
    """The union result alias *node* reads through the wrap alias, else ``None``.

    A wildcard is not one: ``u.*`` names none of the aliases the union allocated, so it
    is refused rather than read as an alias spelled ``*``.
    """
    if (
        isinstance(node, exp.Column)
        and isinstance(node.this, exp.Identifier)
        and node.table == _WRAP_ALIAS
        and not node.args.get("db")
    ):
        return node.name
    return None


def _wrap_presence_cell(node: Expr | None) -> str | None:
    """The alias a ``Document`` presence cell tests, else ``None``.

    The pair's first half is ``not u.<alias> is null`` — the only outer cell m-sql
    admits that is not itself a projected result alias.
    """
    if isinstance(node, exp.Not) and isinstance(node.this, exp.Is):
        return _wrap_column(node.this.this) if isinstance(node.this.expression, exp.Null) else None
    return None


def _assert_wrap_projection(
    select: exp.Select, union: exp.SetOperation, facts: WrapFacts | None
) -> None:
    """Every union result alias projected through the wrap, once, in the union's order.

    m-sql: the outer select projects the union's own result aliases through. The one
    exception is a ``Document`` slot — a presence cell carries no result alias and so
    cannot be addressed from outside the derived table, so each branch projects the
    slot as ONE aliased cell and the outer select expands the read pair
    ``not u.<alias> is null, u.<alias>`` over it. Walking the aliases and the outer
    cells together admits exactly those two spellings, which is what makes a
    duplicated, computed, missing, extra, or foreign-qualified outer cell a refusal
    rather than merely "not a wildcard".

    With *facts*, the pair is REQUIRED over every ``Document`` alias and refused over
    every other, because a projected ``Document`` value that is not preceded by its
    presence half is not readable as one. Without them, which alias holds a ``Document``
    is unsettled, so the pair is merely permitted anywhere — all a statement alone
    supports.
    """
    cells: list[Expr] = list(select.expressions)
    aliases = union.named_selects
    position = 0
    for alias in aliases:
        document = None if facts is None else alias in facts.document_aliases
        cell = cells[position] if position < len(cells) else None
        paired = _wrap_presence_cell(cell) == alias
        if paired and document is not False:
            position += 1
            cell = cells[position] if position < len(cells) else None
        if (document and not paired) or _wrap_column(cell) != alias:
            presence = f"`not {_WRAP_ALIAS}.{alias} is null`"
            requirement = (
                f" — optionally preceded by its {presence} Document presence cell"
                if document is None
                else f", preceded by its {presence} Document presence cell"
                if document
                else f", and {alias!r} holds no Document, so no presence cell precedes it"
            )
            raise NonCanonicalError(
                f"wrapped `union all`: outer cell {position} must project the union result "
                f"alias {alias!r} as `{_WRAP_ALIAS}.{alias}`{requirement} — got "
                f"{cell.sql() if cell is not None else None!r} (m-sql)"
            )
        position += 1
    if position != len(cells):
        raise NonCanonicalError(
            f"wrapped `union all`: the outer select projects {len(cells)} cell(s) over the "
            f"union's {len(aliases)} result alias(es) {aliases}; only a Document read pair "
            f"adds a cell, and every alias is projected through exactly once (m-sql)"
        )


@dataclass(frozen=True, slots=True)
class _DialectSeam:
    """The m-dialect decisions the wrap's tail turns on, for one dialect.

    ``null_is_largest`` fixes where the dialect's own ``order by`` puts ``NULL``s with
    no placement syntax at all, and ``placement_suffix`` how it compensates a differing
    request: Postgres with a ``nulls first`` / ``nulls last`` suffix, MariaDB — which
    has no such syntax — with a leading boolean rank term. ``extraction`` is its
    document extraction function and ``path_binds_per_segment`` whether that function
    takes one ``?`` per path segment or one for the whole JSON path. ``casts`` maps a
    declared neutral type to the target the extraction is compared under; a type absent
    from it compares as the extracted text with no cast on either dialect.
    """

    null_is_largest: bool
    placement_suffix: bool
    extraction: str
    path_binds_per_segment: bool
    casts: Mapping[str, str]


_DIALECT_SEAM = {
    "postgres": _DialectSeam(
        null_is_largest=True,
        placement_suffix=True,
        extraction="jsonb_extract_path_text",
        path_binds_per_segment=True,
        casts={
            "int32": "bigint",
            "int64": "bigint",
            "float32": "real",
            "float64": "double precision",
            "boolean": "boolean",
        },
    ),
    "mariadb": _DialectSeam(
        null_is_largest=False,
        placement_suffix=False,
        extraction="json_value",
        path_binds_per_segment=False,
        casts={
            "int32": "signed",
            "int64": "signed",
            "float32": "float",
            "float64": "double",
            "boolean": "signed",
        },
    ),
}


def _extracted_wrap_column(node: Expr | None, dialect: str) -> str | None:
    """The union result alias *dialect*'s document extraction reads, else ``None``.

    The extraction takes the Structured Column as its first argument and the path as
    ``?`` binds (one per segment on Postgres, one whole JSON path on MariaDB), so a
    call carrying anything else — a second column, a literal path, a folded
    expression — is not the extraction m-sql orders by. sqlglot parses MariaDB's
    ``json_value`` into a node of its own and leaves the Postgres spelling an anonymous
    call, so a key is matched by the shape its OWN dialect emits.
    """
    seam = _DIALECT_SEAM.get(dialect)
    if seam is None:
        return None
    extraction = seam.extraction
    if isinstance(node, exp.JSONValue):
        if extraction != "json_value":
            return None
        column, path = node.this, [node.args.get("path")]
    elif isinstance(node, exp.Anonymous) and node.name.lower() == extraction:
        column, *path = node.expressions or [None]
    else:
        return None
    if not path or not all(isinstance(segment, exp.Placeholder) for segment in path):
        return None
    return _wrap_column(column)


def _wrap_order_key(node: Expr | None, dialect: str) -> str | None:
    """The union result alias an ``order by`` key sorts on, else ``None``.

    m-sql admits two spellings and no others: the result alias itself, and — for a
    member the layout placed inside a Structured Column — the document extraction over
    that alias under the declared type's cast. Which of the two a member takes is a
    declaration fact the statement does not carry, so both are admitted for every
    alias, while a constant, a bind, an arbitrary function, and an expression over two
    aliases are keys the wrap never emits.
    """
    if (alias := _wrap_column(node)) is not None:
        return alias
    return _extracted_wrap_column(node.this if isinstance(node, exp.Cast) else node, dialect)


def _wrap_rank_term(node: Expr | None, dialect: str) -> tuple[Expr, str, bool] | None:
    """What a Null Placement rank term ranks, the alias it reaches, and its placement.

    MariaDB has no ``NULLS FIRST/LAST`` syntax and compensates with a leading boolean
    term instead (``m-dialect`` *NULL ordering*): ``<key> is null`` sorts ``NULL``s
    last and ``not <key> is null`` sorts them first. The ranked ``<key>`` is the WHOLE
    key term the rank precedes — a result alias, or the document extraction over one
    under its declared cast — so a rank over a ``Document``-resident key is recognized
    exactly as the key it ranks is. ``None`` for anything else.
    """
    nulls_first = isinstance(node, exp.Not)
    inner = node.this if nulls_first else node
    if not isinstance(inner, exp.Is) or not isinstance(inner.expression, exp.Null):
        return None
    ranked = inner.this
    alias = _wrap_order_key(ranked, dialect)
    return None if alias is None or ranked is None else (ranked, alias, nulls_first)


@dataclass(frozen=True, slots=True)
class _OrderTerm:
    """One comma-separated ``order by`` term the wrap must render.

    ``expression`` is what the term sorts on, compared as a parsed expression so a
    dialect's rendering conventions cannot make an equal term unequal; ``spelling`` is
    the whole term as it reads, and ``binds`` the values its ``?`` holes carry.
    ``direction`` is the direction KEYWORD the term must spell, and ``None`` for the
    rank term, which spells none: m-sql fixes ``<key> asc`` and ``<key> desc`` as the
    canonical key terms, so an omitted ``asc`` is a second spelling of the first and a
    direction on a rank term is a third. ``nulls_first`` is ``None`` where the parse
    settles nothing worth asserting — sqlglot resolves an omitted placement to the
    dialect's native one, so a redundant explicit suffix reads the same as none, and a
    rank term is a boolean that is never itself ``NULL``.
    """

    expression: str
    spelling: str
    direction: str | None
    nulls_first: bool | None
    binds: tuple[str, ...] = ()


def _extraction_cast(neutral_type: str | None, seam: _DialectSeam) -> str | None:
    """The target a document extraction of *neutral_type* is read under, else ``None``.

    ``decimal(p,s)`` casts to itself on both dialects; the rest of the numeric family
    and ``boolean`` take the dialect's own target; the text-compared types are read as
    the extracted text with no cast at all (``m-dialect`` *Typed cast form*).
    """
    if neutral_type is None:
        return None
    if neutral_type.startswith("decimal("):
        return neutral_type
    return seam.casts.get(neutral_type)


def _path_binds(path: tuple[str, ...], seam: _DialectSeam) -> tuple[str, ...]:
    """The values a document extraction of *path* binds, in bind order (``m-dialect``).

    Postgres carries the path segments as separate key binds; MariaDB carries the
    whole ``$.a.b`` JSON-path string as one. Spelled here rather than read off any
    emitter: the verifier is an independent oracle, so it derives the binds it expects.
    """
    if not path:
        return ()
    return path if seam.path_binds_per_segment else ("$." + ".".join(path),)


def _key_spelling(key: WrapOrderKey, seam: _DialectSeam) -> str:
    """How *key* names its value: the union result alias, or the extraction over it.

    A member the layout placed inside a Structured Column has no result alias of its
    own, so the key lowers to the same extraction and typed cast a predicate over that
    member takes, against the union alias (m-sql).
    """
    column = f"{_WRAP_ALIAS}.{key.alias}"
    if not key.document_path:
        return column
    holes = ", ".join(["?"] * len(_path_binds(key.document_path, seam)))
    extraction = f"{seam.extraction}({column}, {holes})"
    target = _extraction_cast(key.neutral_type, seam)
    return extraction if target is None else f"cast({extraction} as {target})"


def _expected_order_terms(key: WrapOrderKey, seam: _DialectSeam) -> list[_OrderTerm]:
    """The terms *key* lowers to under *seam* (``m-dialect`` *NULL ordering*).

    A non-nullable key holds no ``NULL`` under conforming storage, so it lowers to the
    plain directed term in both dialects under either placement, leaving the dialect's
    own convention to rank a ``NULL`` non-conforming storage left behind. A nullable
    one lowers to the plain term
    where the dialect's native placement already answers the request, and otherwise to
    the dialect's own compensation — a suffix on the term, or a boolean rank term
    before it.
    """
    spelling = _key_spelling(key, seam)
    binds = _path_binds(key.document_path, seam)
    native = key.descending == seam.null_is_largest
    requested = key.nulls_first if key.nullable else native
    compensates = requested != native
    terms: list[_OrderTerm] = []
    if compensates and not seam.placement_suffix:
        rank = f"{'not ' if requested else ''}{spelling} is null"
        terms.append(
            _OrderTerm(
                expression=rank, spelling=rank, direction=None, nulls_first=None, binds=binds
            )
        )
    suffix = f" nulls {'first' if requested else 'last'}" if compensates else ""
    direction = "desc" if key.descending else "asc"
    terms.append(
        _OrderTerm(
            expression=spelling,
            spelling=f"{spelling} {direction}{suffix}",
            direction=direction,
            nulls_first=requested if seam.placement_suffix else native,
            binds=binds,
        )
    )
    return terms


def _ordered_term(node: Expr | None) -> Expr | None:
    """What one ``order by`` term sorts on, unwrapped from its direction."""
    return node.this if isinstance(node, exp.Ordered) else node


# How the parse reports a term's direction keyword: absent, `asc`, `desc`. The rank
# term spells none, so `None` maps to `None` rather than to the ascending default.
_DIRECTION_IS_DESC: Mapping[str | None, bool | None] = {None: None, "asc": False, "desc": True}


def _assert_authored_wrap_order(
    terms: list[Expr], dialect: str, expected: list[_OrderTerm]
) -> None:
    """The wrap orders by exactly the authored Sort Keys, as *dialect* renders them.

    Each expected term is parsed under the same dialect as the statement and compared
    as an expression, so what is asserted is the term the read lowers to rather than a
    spelling of it. The direction keyword is compared as the tri-state the parse
    reports — absent, ``asc``, ``desc`` — so an omitted ``asc`` is refused for the
    second spelling of the canonical term it is.
    """
    engine = sqlglot_dialect(dialect)
    if len(terms) != len(expected):
        raise NonCanonicalError(
            f"wrapped `union all`: the outer `order by` has {len(terms)} term(s), but the "
            f"read's Sort Keys lower to {[term.spelling for term in expected]} in "
            f"{dialect} (m-sql / m-dialect)"
        )
    for position, term in enumerate(expected):
        found = terms[position]
        if (
            not isinstance(found, exp.Ordered)
            or found.this != sqlglot.parse_one(term.expression, read=engine)
            or found.args.get("desc") is not _DIRECTION_IS_DESC[term.direction]
            or (
                term.nulls_first is not None
                and bool(found.args.get("nulls_first")) != term.nulls_first
            )
        ):
            raise NonCanonicalError(
                f"wrapped `union all`: `order by` term {position} must be "
                f"{term.spelling!r} in {dialect} — got {found.sql()!r} (m-sql / m-dialect)"
            )


def _assert_wrap_tail_binds(facts: WrapFacts, expected: list[_OrderTerm], dialect: str) -> None:
    """The tail's binds are the ones the read it lowers puts there.

    The tail's holes are the Document paths its ``order by`` extracts under, in term
    order, then the cap — and a wrap's binds follow every branch's (m-sql), so they are
    the bind list's trailing entries. Comparing the VALUES is what refuses a tail whose
    shape is canonical but whose path addresses another member of the same arity, or
    whose cap is not the row count the query asked for.
    """
    if facts.binds is None:
        return
    values: list[object] = [bind for term in expected for bind in term.binds]
    if facts.limit is not None:
        values.append(facts.limit)
    if not values:
        return
    found = list(facts.binds)[len(facts.binds) - len(values) :]
    if len(facts.binds) < len(values) or found != values:
        raise NonCanonicalError(
            f"wrapped `union all`: the tail binds {values!r} in {dialect} — the Document "
            f"path(s) its `order by` extracts under, then the read's cap, after every "
            f"branch bind — got {found!r} (m-sql / m-dialect / m-object-query)"
        )


def _assert_directed_key(term: Expr | None) -> None:
    """One ``order by`` key term spells its direction.

    m-sql fixes the canonical key terms as ``<key> asc`` and ``<key> desc``; a term
    leaving the direction to the dialect's default is a second spelling of the first.
    """
    if not isinstance(term, exp.Ordered) or term.args.get("desc") is None:
        raise NonCanonicalError(
            f"wrapped `union all`: `order by` key "
            f"{term.sql() if term is not None else None!r} spells no direction, but the "
            f"canonical term is `<key> asc` / `<key> desc` (m-sql)"
        )


def _assert_wrap_order_shape(terms: list[Expr], union: exp.SetOperation, dialect: str) -> None:
    """Every ordering key names a union result alias, through the wrap alias.

    m-sql: an ``order by`` key names the result alias its contributor was allocated
    above, never a branch's physical spelling, and a key over a Structured Column
    member lowers to the same extraction taken against the union alias. A dialect that
    compensates a Null Placement with a rank term rather than a suffix prefixes that
    term to its key's own (``m-dialect``), so a rank term is admitted there — and only
    there — and only immediately before the key it ranks.

    Which placement a key REQUESTS is a query fact, but which one a rank term reaches
    is not: a rank term exists only where the dialect's native placement differs from
    the request, and MariaDB's native placement is fixed by the direction, so
    ``<key> is null`` compensates an ascending key and ``not <key> is null`` a
    descending one and neither compensates the other. That pairing, the identity of the
    ranked key with the key ranked, and the rank term's own lack of a direction are all
    gradeable from the statement alone.
    """
    seam = _DIALECT_SEAM.get(dialect)
    ranked = seam is not None and not seam.placement_suffix
    aliases = set(union.named_selects)
    position = 0
    while position < len(terms):
        rank = _wrap_rank_term(_ordered_term(terms[position]), dialect) if ranked else None
        if rank is not None and rank[1] in aliases:
            key, _, nulls_first = rank
            if isinstance(terms[position], exp.Ordered) and (
                terms[position].args.get("desc") is not None
            ):
                raise NonCanonicalError(
                    f"wrapped `union all`: the Null Placement rank term "
                    f"{terms[position].sql()!r} carries its own direction; the compensating "
                    f"form ranks ascending and the direction rides the key it precedes "
                    f"(m-dialect)"
                )
            following = terms[position + 1] if position + 1 < len(terms) else None
            direction = "desc" if nulls_first else "asc"
            if (
                not isinstance(following, exp.Ordered)
                or following.this != key
                or following.args.get("desc") is not nulls_first
            ):
                raise NonCanonicalError(
                    f"wrapped `union all`: the Null Placement rank term "
                    f"{terms[position].sql()!r} compensates only a {direction} key, so it must "
                    f"be followed by `{key.sql()} {direction}` — got "
                    f"{following.sql() if following is not None else None!r} (m-dialect)"
                )
            position += 2
            continue
        key_expression = _ordered_term(terms[position])
        if _wrap_order_key(key_expression, dialect) not in aliases:
            raise NonCanonicalError(
                f"wrapped `union all`: `order by` key "
                f"{key_expression.sql() if key_expression is not None else None!r} must name "
                f"one of the union's result aliases {sorted(aliases)} through "
                f"`{_WRAP_ALIAS}` — as `{_WRAP_ALIAS}.<alias>`, or as the {dialect} document "
                f"extraction over it under its declared cast (m-sql)"
            )
        _assert_directed_key(terms[position])
        position += 1


def _assert_wrap_cap_shape(select: exp.Select) -> None:
    """A cap is exactly ``limit ?`` (m-sql).

    The row count crosses as a bind, so a literal, an arithmetic fold, a function
    call, and a column are all caps the emitter never writes — and a column or a
    non-deterministic function makes the capped row set depend on the data it caps.
    """
    limit = select.args.get("limit")
    if limit is not None and not isinstance(limit.expression, exp.Placeholder):
        raise NonCanonicalError(
            f"wrapped `union all`: the cap is `limit ?` — the row count crosses as a bind, "
            f"never as a literal, an expression, or a column — got {limit.sql()!r} (m-sql)"
        )


def _assert_wrap_tail(
    select: exp.Select, union: exp.SetOperation, dialect: str, facts: WrapFacts | None
) -> None:
    """The result-shape tail the wrap exists to carry, as m-sql and m-dialect fix it.

    With *facts* the tail is graded against the read it lowers: the ordering terms are
    the ones the authored Sort Keys render to in *dialect*, and the cap is present
    exactly when the query authored one and binds the row count it asked for. Without
    them only the ordering keys' shape can be judged, since no statement carries the
    query behind it — but the cap's own shape is fixed by m-sql either way.
    """
    order = select.args.get("order")
    terms: list[Expr] = list(order.expressions) if order is not None else []
    _assert_wrap_cap_shape(select)
    if facts is None:
        _assert_wrap_order_shape(terms, union, dialect)
        return
    seam = _DIALECT_SEAM.get(dialect)
    if seam is None:
        raise NonCanonicalError(
            f"wrapped `union all`: m-dialect fixes no `order by` seam for {dialect!r}, so "
            f"the authored Sort Keys cannot be graded against it"
        )
    capped = facts.limit is not None
    if bool(select.args.get("limit")) is not capped:
        raise NonCanonicalError(
            f"wrapped `union all`: the read {'declares' if capped else 'declares no'} "
            f"`limit`, but the outer select carries {'none' if capped else 'one'} (m-sql)"
        )
    expected = [term for key in facts.order_keys for term in _expected_order_terms(key, seam)]
    _assert_authored_wrap_order(terms, dialect, expected)
    _assert_wrap_tail_binds(facts, expected, dialect)


def wrapped_union_source(
    select: exp.Select, dialect: str, facts: WrapFacts | None = None
) -> exp.SetOperation | None:
    """The set operation *select* wraps as m-sql's derived table ``u``, else ``None``.

    A ``union all`` has no clause tail of its own, so an ordered or limited
    table-per-concrete-subtype read wraps the whole union as the derived table ``u``
    and applies the result-shape tail against that alias (m-sql). Recognized so, the
    wrap is a SCOPE boundary rather than a source of its own: the outer select names
    no table, and each branch keeps restarting its own ``t0, t1, …`` sequence.

    ``None`` means *select* does not take a set operation as its sole ``from`` source
    at all — the locking table-per-hierarchy partitioned read JOINS its derived
    identity relation, so that union is a source among others and its branches share
    the outer scope's alias sequence. Anything that DOES take one is judged as the
    wrap and raises :class:`NonCanonicalError` unless it is the wrap in full: aliased
    ``u``, joined to nothing, carrying the tail that is the only reason to wrap and no
    clause the wrap does not move outward, projecting each of the union's result
    aliases through exactly once, and carrying a tail *dialect* renders that way.
    Refusing here is what keeps a malformed wrapper from falling through to be scored
    as an ordinary select whose branch aliases happen to run ``t0, t1, …`` globally.

    *facts* are the model and query facts no statement carries; supplying them turns
    the permissive readings a statement alone supports into the single shape the read
    behind it lowers to (:class:`WrapFacts`).
    """
    source = select.args.get("from_")
    inner = source.this if isinstance(source, exp.From) else None
    if not isinstance(inner, exp.Subquery) or not isinstance(inner.this, exp.SetOperation):
        return None
    union = inner.this
    if inner.alias != _WRAP_ALIAS:
        raise NonCanonicalError(
            f"a derived `union all` is the wrap m-sql names {_WRAP_ALIAS!r}, got "
            f"{inner.alias or None!r}"
        )
    forbidden = [clause for clause in _WRAP_FORBIDDEN if select.args.get(clause)]
    if forbidden:
        raise NonCanonicalError(
            f"wrapped `union all`: the wrap moves only the result-shape tail outward, but "
            f"the outer select carries {forbidden} (m-sql)"
        )
    if not any(select.args.get(clause) for clause in _WRAP_TAIL):
        raise NonCanonicalError(
            "wrapped `union all`: the result-shape tail is the only reason to wrap, so a "
            "wrap carrying no `order by` / `limit` is a second spelling of the bare union "
            "(m-sql)"
        )
    _assert_wrap_projection(select, union, facts)
    _assert_wrap_tail(select, union, dialect, facts)
    return union


def assert_union_tail_wrapped(union: exp.SetOperation) -> None:
    """A ``union all`` reached outside a wrap carries no result-shape tail.

    The set operation itself has no clause tail: an ordered or limited abstract read
    wraps the whole union as the derived table ``u`` and applies the tail against that
    alias (m-sql), so a tail hung on the union is a second spelling of the wrap.
    """
    tail = [clause for clause in _WRAP_TAIL if union.args.get(clause)]
    if tail:
        raise NonCanonicalError(
            f"a `union all` carrying {tail} must wrap the whole union as the derived "
            f"table `{_WRAP_ALIAS}` and apply the result-shape tail against that alias "
            f"(m-sql); the set operation itself carries no tail"
        )
