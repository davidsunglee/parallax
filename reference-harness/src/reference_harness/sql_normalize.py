"""sqlglot-based implementation of the m-sql canonical SQL normalization rules.

The normative rules (m-sql, ``core/spec/m-sql.md``):

1. Table-alias scheme ``t0, t1, …``; columns always alias-qualified.
2. Lowercase keywords and unquoted identifiers.
3. Whitespace collapsed to single spaces; trimmed.
4. Literal parameters rendered as ``?`` bind placeholders.
5. Deterministic clause order
   (``select … from … where … group by … having … order by … limit …``).

The golden SQL stored in a case **must already be a fixed point**:
``normalize(sql) == sql`` for each statement's dialect text. The m-case-format
harness asserts this (layer 3), so a contributor who hand-writes non-canonical
golden SQL fails before any database is touched.

Approach. sqlglot parses the statement and re-renders it, which gives us
deterministic clause order (rule 5), single-space whitespace (rule 3), explicit
column-qualified projection, and ``?`` placeholders preserved (rule 4). We then
walk the token stream to lowercase keyword tokens and drop the alias ``AS``
keyword (rules 1–2 produce the spec's lowercase, ``AS``-free canonical form,
e.g. ``from orders t0`` rather than ``FROM orders AS t0``). Unquoted identifiers
are lowercased on the AST before rendering; quoted identifiers are left intact.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.dialects.dialect import Dialect
from sqlglot.expressions.core import Expr
from sqlglot.parser import Parser
from sqlglot.tokenizer_core import Token, TokenType

# Map a parallax dialect identifier to the sqlglot dialect that parses/renders
# it. ``mariadb`` (Phase 10, the second dialect behind the m-dialect seam) has no
# dedicated sqlglot dialect; MariaDB is MySQL-protocol-compatible and sqlglot's
# ``mysql`` dialect parses + renders the SQL we need, so the MariaDB normalization
# pass runs through ``mysql``. Any dialect not listed here is passed to sqlglot
# verbatim (``postgres`` is its own sqlglot dialect).
_SQLGLOT_DIALECT = {"mariadb": "mysql"}


def sqlglot_dialect(dialect: str) -> str:
    """The sqlglot dialect that parses/renders the parallax *dialect*.

    ``mariadb`` maps to sqlglot's ``mysql`` (MariaDB is MySQL-protocol-compatible
    and sqlglot has no dedicated MariaDB dialect); every other dialect is its own
    sqlglot dialect and passes through. Used by both the normalizer and the static
    SQL lint so a statement entry's ``sql.mariadb`` text is parsed under the right dialect.
    """
    return _SQLGLOT_DIALECT.get(dialect, dialect)


# Token types that carry a value / identifier and MUST keep their original case
# (identifiers are lowercased separately on the AST when unquoted).
_VALUE_TOKENS = frozenset(
    {
        TokenType.VAR,
        TokenType.IDENTIFIER,
        TokenType.STRING,
        TokenType.NATIONAL_STRING,
        TokenType.RAW_STRING,
        TokenType.NUMBER,
        TokenType.PLACEHOLDER,
        TokenType.PARAMETER,
        TokenType.COLON,
    }
)

# The alias keyword (``AS``) is dropped entirely: the canonical form writes
# ``orders t0`` and ``t0.id`` projections, never ``orders AS t0``. The one
# exception is the ``AS`` inside a ``cast(expr AS type)`` — there it is required
# syntax, not an alias — which :func:`_render_tokens` preserves (see below).
_DROP_TOKENS = frozenset({TokenType.ALIAS})

# Function names whose parenthesised body uses ``AS`` as required syntax rather
# than as an alias introducer. A ``valueObject`` numeric nested predicate lowers
# to a typed cast of the document extraction (``cast(extract as double precision)``
# on Postgres, ``cast(extract as double)`` on MariaDB — the m-dialect *typed cast
# form*), so the cast's ``AS`` MUST survive normalization even though a table /
# column alias ``AS`` is dropped. sqlglot renders both a ``::`` cast and a
# ``convert(expr, type)`` as ``CAST(expr AS type)``, so matching ``CAST`` covers
# every surface; ``CONVERT`` is matched too for defensiveness.
_CAST_FUNCTIONS = frozenset({"CAST", "CONVERT"})

# A private spacing sentinel used by the renderer to mark a VAR token that is a
# function name (``lower(…)``). It is never a real sqlglot token type; it only
# drives the "no space before the following ``(``" spacing rule.
_FUNCTION_NAME = "function-name"

# SQL keywords that sqlglot tokenizes as ``VAR`` rather than a dedicated keyword
# token. The row-locking suffix ``for SHARE OF t0`` is the case in point: sqlglot
# tokenizes ``SHARE`` and ``OF`` as ``VAR`` and its generator emits them
# uppercase, so they would otherwise slip past the keyword-lowercasing pass. m-sql
# rule 2 lowercases keywords, so these are lowercased even though they arrive as
# value tokens. (Unquoted identifiers are already lowercased on the AST and
# quoted ones tokenize as ``IDENTIFIER``, so lowercasing these VARs is safe.)
_KEYWORD_VARS = frozenset({"SHARE", "OF"})

# String-literal tokens keep their (case-sensitive) text but tokenize with the
# surrounding quotes STRIPPED; the renderer re-wraps them in single quotes so a
# canonical string literal survives normalization unchanged. A string literal
# appears in canonical m-sql only as the table-per-concrete-subtype ``familyVariant``
# branch literal (``'Dog'``, ``'Cat'``, …) — every caller-supplied value is a ``?``
# bind (rule 4), so this path is exercised solely by the inheritance ``union all``
# lowering.
_STRING_TOKENS = frozenset({TokenType.STRING, TokenType.NATIONAL_STRING, TokenType.RAW_STRING})

# SQL type-name tokens whose length/precision list binds TIGHT to the type name
# (``decimal(18, 2)``, ``varchar(64)``, ``char(3)``), exactly like a function call's
# paren. They appear in canonical m-sql inside a ``cast(null as <type>)`` NULL
# placeholder in a table-per-concrete-subtype ``union all`` branch; without the
# tight-binding the renderer would insert a space (``decimal (18, 2)``) because a
# type name is neither a value token nor a VAR function name. This is sqlglot's OWN
# full type-token classification (``Parser.TYPE_TOKENS``) rather than a hand-curated
# allowlist, so ANY parametrized type a future cast introduces (Phase 8 temporal
# TPCS: ``timestamp(6)``, ``datetime(6)``, ``numeric``, ...) renders correctly with
# no edit here. It is only consulted when the token is immediately followed by ``(``
# (a parametrized type); ``TYPE_TOKENS`` excludes clause keywords such as ``in`` /
# ``values``, so ``in (?, …)`` still renders with its space.
_SQL_TYPE_TOKENS = Parser.TYPE_TOKENS

# The identifier-quoting character per dialect (m-sql rule 2 leaves quoted
# identifiers intact). A quoted identifier — a reserved word or otherwise
# non-simple column/table name — tokenizes as a single ``IDENTIFIER`` token whose
# text has the quotes stripped; the renderer re-wraps it in the dialect's quote
# character so the canonical form keeps the quotes (``t0."order"`` on Postgres,
# ``t0.`order``` on MariaDB).
_QUOTE_CHAR = {"postgres": '"', "mariadb": "`"}

_RenderTokenType = TokenType | str


def _lowercase_unquoted_identifiers(tree: Expr) -> None:
    for node in tree.walk():
        if isinstance(node, exp.Identifier) and not node.args.get("quoted"):
            node.set("this", node.this.lower())


def _render_tokens(tokens: list[Token], dialect: str) -> str:
    """Reassemble a token stream into canonical single-space-separated SQL."""
    quote_char = _QUOTE_CHAR.get(dialect, '"')
    parts: list[tuple[_RenderTokenType, str]] = []
    # Whether each currently-open paren was opened by a cast function. The `AS`
    # directly inside a `cast(… as type)` is required syntax and preserved; every
    # other alias `AS` (table / column) is dropped.
    cast_paren_stack: list[bool] = []
    for index, token in enumerate(tokens):
        if token.token_type is TokenType.L_PAREN:
            previous = tokens[index - 1] if index > 0 else None
            cast_paren_stack.append(
                previous is not None
                and previous.token_type is TokenType.VAR
                and previous.text.upper() in _CAST_FUNCTIONS
            )
        elif token.token_type is TokenType.R_PAREN and cast_paren_stack:
            cast_paren_stack.pop()
        if token.token_type in _DROP_TOKENS:
            # Keep the `AS` when the innermost open paren is a cast's; drop it
            # (an alias introducer) everywhere else.
            if not (cast_paren_stack and cast_paren_stack[-1]):
                continue
        text = token.text
        # A quoted identifier (reserved word / non-simple name) tokenizes to an
        # IDENTIFIER whose text has the quotes stripped; re-wrap it in the
        # dialect's quote character so the canonical form preserves the quoting.
        # IDENTIFIER is a value token, so its case is left intact below.
        if token.token_type is TokenType.IDENTIFIER:
            text = f"{quote_char}{text}{quote_char}"
        # A string literal tokenizes with its surrounding quotes stripped; re-wrap
        # it in single quotes (doubling any embedded quote) so the canonical form
        # keeps the literal. STRING is a value token, so its case is left intact.
        elif token.token_type in _STRING_TOKENS:
            text = "'" + text.replace("'", "''") + "'"
        following_is_paren = (
            index + 1 < len(tokens) and tokens[index + 1].token_type is TokenType.L_PAREN
        )
        # A VAR immediately followed by ``(`` is a function name (``lower(…)``),
        # not a table/column identifier. sqlglot renders function names in
        # uppercase (``LOWER``); m-sql rule 2 lowercases unquoted identifiers, so we
        # lowercase the function name and render it tight against its paren.
        is_function_name = token.token_type is TokenType.VAR and following_is_paren
        # A parametrized type name (``decimal(18, 2)``) inside a NULL-placeholder
        # cast binds its length list tight to the type, exactly like a function
        # name; it is not a value token, so it is already lowercased below.
        is_paren_type = token.token_type in _SQL_TYPE_TOKENS and following_is_paren
        # A lock-clause keyword sqlglot tokenized as VAR (``SHARE``/``OF``) must
        # be lowercased like any other keyword (m-sql rule 2), not preserved.
        is_keyword_var = token.token_type is TokenType.VAR and text.upper() in _KEYWORD_VARS
        if token.token_type not in _VALUE_TOKENS or is_function_name or is_keyword_var:
            text = text.lower()
        token_type = _FUNCTION_NAME if (is_function_name or is_paren_type) else token.token_type
        parts.append((token_type, text))

    # Join with spaces, but keep punctuation tight (no space before ``,`` ``.``
    # ``)`` and no space after ``(`` ``.`` and a function name).
    out: list[str] = []
    no_space_before = {TokenType.COMMA, TokenType.DOT, TokenType.R_PAREN}
    no_space_after: set[_RenderTokenType] = {TokenType.L_PAREN, TokenType.DOT, _FUNCTION_NAME}
    prev_type: _RenderTokenType | None = None
    for token_type, text in parts:
        if out and token_type not in no_space_before and prev_type not in no_space_after:
            out.append(" ")
        out.append(text)
        prev_type = token_type
    return "".join(out).strip()


class NonCanonicalError(ValueError):
    """*sql* violates an m-sql canonical rule the normalizer enforces structurally
    rather than by re-rendering: the read alias scheme + column qualification
    (rule 1) and ``?`` bind placeholders for parameters (rule 4).

    Lowercasing and re-spacing alone do not catch these, so without this check
    ``normalize`` would return a lowercase-but-non-canonical statement unchanged
    and ``is_canonical`` / ``sql_lint`` would wrongly accept it as a fixture.
    """


def _inline_parameter_literal(tree: Expr) -> Expr | None:
    """The first literal used as a *parameter* (which must therefore be a ``?``
    bind), or ``None``. A literal compared against a column, listed in an
    ``in`` / ``between`` against a column, used as a row ``limit``, or placed in
    an ``INSERT ... VALUES`` tuple is a parameter. Structural constants — the
    ``1 = 0`` none-identity and the ``select 1`` EXISTS probe — are not
    parameters and are left alone."""

    def col_vs_lit(a: Expr, b: Expr) -> bool:
        return isinstance(a, exp.Column) and isinstance(b, exp.Literal)

    for node in tree.find_all(exp.Binary):
        if col_vs_lit(node.left, node.right) or col_vs_lit(node.right, node.left):
            return node
    for node in tree.find_all(exp.In):
        if isinstance(node.this, exp.Column) and any(
            isinstance(value, exp.Literal) for value in node.expressions
        ):
            return node
    for node in tree.find_all(exp.Between):
        if isinstance(node.this, exp.Column) and any(
            isinstance(node.args.get(bound), exp.Literal) for bound in ("low", "high")
        ):
            return node
    for node in tree.find_all(exp.Limit):
        if isinstance(node.expression, exp.Literal):
            return node
    if isinstance(tree, exp.Insert):
        values = tree.args.get("expression")
        if isinstance(values, exp.Values):
            return next(values.find_all(exp.Literal), None)
    return None


def is_union_all(node: exp.SetOperation) -> bool:
    """True iff *node* is a canonical ``union all`` set operation (m-sql).

    In sqlglot ``union all`` parses to ``exp.Union(distinct=False)``; a plain
    ``union`` is ``exp.Union(distinct=True)`` — which silently **de-duplicates** rows
    and so changes the read's semantics — and ``intersect`` / ``except`` are their own
    ``SetOperation`` subclasses (``exp.Intersect`` / ``exp.Except``, both
    ``distinct=True``). The ONLY canonical m-sql set operation is ``union all`` (the
    table-per-concrete-subtype abstract-read lowering); every other set operation is
    non-canonical. Used by the normalizer (below) and re-exported for the TPCS read
    oracle's branch walk so both surfaces enforce the same rule.
    """
    return isinstance(node, exp.Union) and not node.args.get("distinct")


def _canonical_select_scopes(tree: Expr) -> list[exp.Select]:
    """The independent SELECT scopes rule 1 applies to, in first-appearance order.

    A plain read is one scope (itself). A ``union all`` is lowered by the
    table-per-concrete-subtype inheritance strategy as N independent branches, so
    rule 1's alias scheme (``t0, t1, …``) restarts PER BRANCH — each branch is scored
    on its own tables/columns, and branch order is preserved by the left-to-right leaf
    walk. A set operation that is NOT ``union all`` (a plain de-duplicating ``union``,
    or ``intersect`` / ``except``) is non-canonical and rejected — it never appears in
    canonical m-sql. DML (Insert / Update / Delete) is not a SELECT and keeps its own
    canonical shape, so it contributes no scope.
    """
    if isinstance(tree, exp.Select):
        return [tree]
    if isinstance(tree, exp.SetOperation):
        if not is_union_all(tree):
            raise NonCanonicalError(
                f"set operation {tree.key!r} is not `union all`; the only canonical "
                f"m-sql set operation is `union all` (the table-per-concrete-subtype "
                f"abstract-read lowering) — a plain `union` de-duplicates rows and "
                f"`intersect` / `except` are not emitted"
            )
        scopes: list[exp.Select] = []
        for side in (tree.this, tree.expression):
            scopes.extend(_canonical_select_scopes(side))
        return scopes
    return []


def _assert_select_canonical(select: exp.Select) -> None:
    """Enforce m-sql rule 1 over one SELECT scope (a read or one union branch)."""
    # A row-lock suffix (`for share of t0`) references an existing alias and
    # sqlglot models that reference as its own Table node; it is not a FROM
    # source, so exclude it from the alias sequence.
    aliases = [
        table.alias for table in select.find_all(exp.Table) if table.find_ancestor(exp.Lock) is None
    ]
    expected = [f"t{index}" for index in range(len(aliases))]
    if aliases != expected:
        raise NonCanonicalError(
            f"read table aliases must be {expected} in first-appearance order "
            f"(m-sql rule 1), got {aliases}"
        )
    for column in select.find_all(exp.Column):
        if not column.table:
            raise NonCanonicalError(f"column {column.name!r} is not alias-qualified (m-sql rule 1)")


def _assert_canonical(tree: Expr) -> None:
    """Enforce the m-sql canonical rules that re-rendering cannot. Parameters must
    be ``?`` binds (rule 4) in every statement; and for *read* (``SELECT``)
    statements — including each branch of a ``union all`` — the alias scheme is
    ``t0, t1, …`` in first-appearance order with every column alias-qualified
    (rule 1). DML keeps its own canonical shape (an unaliased target table and bare
    columns), so rule 1 is not applied to it."""
    literal = _inline_parameter_literal(tree)
    if literal is not None:
        raise NonCanonicalError(
            f"inline literal where a ? bind is required (m-sql rule 4): {literal.sql()!r}"
        )
    for select in _canonical_select_scopes(tree):
        _assert_select_canonical(select)


# MariaDB's shared-row-lock suffix (m-dialect). sqlglot's ``mysql`` dialect parses both
# ``lock in share mode`` and ``for share`` into the same ``exp.Lock(update=False)``
# node and *renders* it as ``for share`` — losing MariaDB's spelling (MariaDB has
# no ``for share``; MDEV-17514). So for MariaDB we strip sqlglot's lock from the
# AST and append the canonical MariaDB suffix ourselves. The form is unaliased
# (``lock in share mode``, never ``of t0``), unlike Postgres' ``for share of t0``
# — exactly the read-lock divergence Phase 10 exercises through the seam.
_MARIADB_READ_LOCK = "lock in share mode"


def _detach_read_lock(tree: Expr, dialect: str) -> str:
    """Pop a non-update ``exp.Lock`` for MariaDB, returning the canonical suffix.

    Returns ``""`` (and leaves the tree untouched) for any other dialect or when
    there is no shared lock. For MariaDB a shared lock is removed from the AST so
    sqlglot does not re-render it as ``for share``; the caller appends the
    returned ``lock in share mode`` suffix after normalizing the rest.
    """
    if dialect != "mariadb":
        return ""
    locks = tree.args.get("locks")
    if not locks:
        return ""
    if any(lock.args.get("update") for lock in locks):
        # An exclusive lock (``for update``) is a different decision point not
        # exercised here; leave it for sqlglot to render rather than guess.
        return ""
    tree.set("locks", None)
    return f" {_MARIADB_READ_LOCK}"


def normalize(sql: str, dialect: str = "postgres") -> str:
    """Normalize *sql* into the m-sql canonical form for *dialect*.

    Raises :class:`NonCanonicalError` for the structural rules re-rendering
    cannot express (rule 1 read aliases / column qualification; rule 4 bind
    placeholders); the textual rules (2, 3, 5) are produced by re-rendering.

    A *dialect* the m-dialect seam knows but sqlglot does not (``mariadb`` → sqlglot
    ``mysql``) is mapped through :func:`sqlglot_dialect`; the MariaDB shared-row
    lock suffix is rendered by the seam rather than sqlglot (see
    :func:`_detach_read_lock`).
    """
    engine = sqlglot_dialect(dialect)
    tree = sqlglot.parse_one(sql, read=engine)
    _assert_canonical(tree)
    lock_suffix = _detach_read_lock(tree, dialect)
    _lowercase_unquoted_identifiers(tree)
    rendered = tree.sql(dialect=engine, normalize=True, pretty=False)
    # Tokenize through the dialect (not the base Tokenizer) so a quoted identifier
    # — double-quoted on Postgres, backtick-quoted on MariaDB/MySQL — tokenizes as
    # a single IDENTIFIER token the renderer can re-quote, rather than being
    # stripped (Postgres) or split around the backticks (MySQL).
    tokens = Dialect.get_or_raise(engine).tokenize(rendered)
    return _render_tokens(tokens, dialect) + lock_suffix


def is_canonical(sql: str, dialect: str = "postgres") -> bool:
    """True iff *sql* is already a fixed point of normalization for *dialect*."""
    try:
        return normalize(sql, dialect) == sql
    except NonCanonicalError:
        return False
