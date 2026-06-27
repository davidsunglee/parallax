"""sqlglot-based implementation of the M3 canonical SQL normalization rules.

The normative rules (M3, ``core/spec/m3-sql-contract.md``):

1. Table-alias scheme ``t0, t1, …``; columns always alias-qualified.
2. Lowercase keywords and unquoted identifiers.
3. Whitespace collapsed to single spaces; trimmed.
4. Literal parameters rendered as ``?`` bind placeholders.
5. Deterministic clause order
   (``select … from … where … group by … having … order by … limit …``).

The golden SQL stored in a case **must already be a fixed point**:
``normalize(goldenSql) == goldenSql``. The M12 harness asserts this (layer 3),
so a contributor who hand-writes non-canonical golden SQL fails before any
database is touched.

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
from sqlglot.tokens import Token, Tokenizer, TokenType

# Map a parallax dialect identifier to the sqlglot dialect that parses/renders
# it. ``mariadb`` (Phase 10, the second dialect behind the M11 seam) has no
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
    SQL lint so a ``goldenSql.mariadb`` statement is parsed under the right dialect.
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
# ``orders t0`` and ``t0.id`` projections, never ``orders AS t0``.
_DROP_TOKENS = frozenset({TokenType.ALIAS})

# A private spacing sentinel used by the renderer to mark a VAR token that is a
# function name (``lower(…)``). It is never a real sqlglot token type; it only
# drives the "no space before the following ``(``" spacing rule.
_FUNCTION_NAME = "function-name"

# SQL keywords that sqlglot tokenizes as ``VAR`` rather than a dedicated keyword
# token. The row-locking suffix ``for SHARE OF t0`` is the case in point: sqlglot
# tokenizes ``SHARE`` and ``OF`` as ``VAR`` and its generator emits them
# uppercase, so they would otherwise slip past the keyword-lowercasing pass. M3
# rule 2 lowercases keywords, so these are lowercased even though they arrive as
# value tokens. (Unquoted identifiers are already lowercased on the AST and
# quoted ones tokenize as ``IDENTIFIER``, so lowercasing these VARs is safe.)
_KEYWORD_VARS = frozenset({"SHARE", "OF"})


def _lowercase_unquoted_identifiers(tree: exp.Expression) -> None:
    for node in tree.walk():
        if isinstance(node, exp.Identifier) and not node.args.get("quoted"):
            node.set("this", node.this.lower())


def _render_tokens(tokens: list[Token]) -> str:
    """Reassemble a token stream into canonical single-space-separated SQL."""
    parts: list[tuple[TokenType, str]] = []
    for index, token in enumerate(tokens):
        if token.token_type in _DROP_TOKENS:
            continue
        text = token.text
        # A VAR immediately followed by ``(`` is a function name (``lower(…)``),
        # not a table/column identifier. sqlglot renders function names in
        # uppercase (``LOWER``); M3 rule 2 lowercases unquoted identifiers, so we
        # lowercase the function name and render it tight against its paren.
        is_function_name = (
            token.token_type is TokenType.VAR
            and index + 1 < len(tokens)
            and tokens[index + 1].token_type is TokenType.L_PAREN
        )
        # A lock-clause keyword sqlglot tokenized as VAR (``SHARE``/``OF``) must
        # be lowercased like any other keyword (M3 rule 2), not preserved.
        is_keyword_var = (
            token.token_type is TokenType.VAR and text.upper() in _KEYWORD_VARS
        )
        if token.token_type not in _VALUE_TOKENS or is_function_name or is_keyword_var:
            text = text.lower()
        token_type = _FUNCTION_NAME if is_function_name else token.token_type
        parts.append((token_type, text))

    # Join with spaces, but keep punctuation tight (no space before ``,`` ``.``
    # ``)`` and no space after ``(`` ``.`` and a function name).
    out: list[str] = []
    no_space_before = {TokenType.COMMA, TokenType.DOT, TokenType.R_PAREN}
    no_space_after = {TokenType.L_PAREN, TokenType.DOT, _FUNCTION_NAME}
    prev_type: TokenType | None = None
    for token_type, text in parts:
        if out and token_type not in no_space_before and prev_type not in no_space_after:
            out.append(" ")
        out.append(text)
        prev_type = token_type
    return "".join(out).strip()


class NonCanonicalError(ValueError):
    """*sql* violates an M3 canonical rule the normalizer enforces structurally
    rather than by re-rendering: the read alias scheme + column qualification
    (rule 1) and ``?`` bind placeholders for parameters (rule 4).

    Lowercasing and re-spacing alone do not catch these, so without this check
    ``normalize`` would return a lowercase-but-non-canonical statement unchanged
    and ``is_canonical`` / ``sql_lint`` would wrongly accept it as a fixture.
    """


def _inline_parameter_literal(tree: exp.Expression) -> exp.Expression | None:
    """The first literal used as a *parameter* (which must therefore be a ``?``
    bind), or ``None``. A literal compared against a column, listed in an
    ``in`` / ``between`` against a column, used as a row ``limit``, or placed in
    an ``INSERT ... VALUES`` tuple is a parameter. Structural constants — the
    ``1 = 0`` none-identity and the ``select 1`` EXISTS probe — are not
    parameters and are left alone."""

    def col_vs_lit(a: exp.Expression, b: exp.Expression) -> bool:
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


def _assert_canonical(tree: exp.Expression) -> None:
    """Enforce the M3 canonical rules that re-rendering cannot. Parameters must
    be ``?`` binds (rule 4) in every statement; and for *read* (``SELECT``)
    statements the alias scheme is ``t0, t1, …`` in first-appearance order with
    every column alias-qualified (rule 1). DML keeps its own canonical shape (an
    unaliased target table and bare columns), so rule 1 is not applied to it."""
    literal = _inline_parameter_literal(tree)
    if literal is not None:
        raise NonCanonicalError(
            f"inline literal where a ? bind is required (M3 rule 4): {literal.sql()!r}"
        )
    if isinstance(tree, exp.Select):
        # A row-lock suffix (`for share of t0`) references an existing alias and
        # sqlglot models that reference as its own Table node; it is not a FROM
        # source, so exclude it from the alias sequence.
        aliases = [
            table.alias
            for table in tree.find_all(exp.Table)
            if table.find_ancestor(exp.Lock) is None
        ]
        expected = [f"t{index}" for index in range(len(aliases))]
        if aliases != expected:
            raise NonCanonicalError(
                f"read table aliases must be {expected} in first-appearance order "
                f"(M3 rule 1), got {aliases}"
            )
        for column in tree.find_all(exp.Column):
            if not column.table:
                raise NonCanonicalError(
                    f"column {column.name!r} is not alias-qualified (M3 rule 1)"
                )


# MariaDB's shared-row-lock suffix (M11). sqlglot's ``mysql`` dialect parses both
# ``lock in share mode`` and ``for share`` into the same ``exp.Lock(update=False)``
# node and *renders* it as ``for share`` — losing MariaDB's spelling (MariaDB has
# no ``for share``; MDEV-17514). So for MariaDB we strip sqlglot's lock from the
# AST and append the canonical MariaDB suffix ourselves. The form is unaliased
# (``lock in share mode``, never ``of t0``), unlike Postgres' ``for share of t0``
# — exactly the read-lock divergence Phase 10 exercises through the seam.
_MARIADB_READ_LOCK = "lock in share mode"


def _detach_read_lock(tree: exp.Expression, dialect: str) -> str:
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
    """Normalize *sql* into the M3 canonical form for *dialect*.

    Raises :class:`NonCanonicalError` for the structural rules re-rendering
    cannot express (rule 1 read aliases / column qualification; rule 4 bind
    placeholders); the textual rules (2, 3, 5) are produced by re-rendering.

    A *dialect* the M11 seam knows but sqlglot does not (``mariadb`` → sqlglot
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
    tokens = Tokenizer(dialect=engine).tokenize(rendered)
    return _render_tokens(tokens) + lock_suffix


def is_canonical(sql: str, dialect: str = "postgres") -> bool:
    """True iff *sql* is already a fixed point of normalization for *dialect*."""
    try:
        return normalize(sql, dialect) == sql
    except NonCanonicalError:
        return False
