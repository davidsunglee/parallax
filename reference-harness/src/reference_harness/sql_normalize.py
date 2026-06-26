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


def _lowercase_unquoted_identifiers(tree: exp.Expression) -> None:
    for node in tree.walk():
        if isinstance(node, exp.Identifier) and not node.args.get("quoted"):
            node.set("this", node.this.lower())


def _render_tokens(tokens: list[Token]) -> str:
    """Reassemble a token stream into canonical single-space-separated SQL."""
    parts: list[str] = []
    for token in tokens:
        if token.token_type in _DROP_TOKENS:
            continue
        text = token.text
        if token.token_type not in _VALUE_TOKENS:
            text = text.lower()
        parts.append((token.token_type, text))

    # Join with spaces, but keep punctuation tight (no space before ``,`` ``.``
    # ``)`` and no space after ``(`` ``.``).
    out: list[str] = []
    no_space_before = {TokenType.COMMA, TokenType.DOT, TokenType.R_PAREN}
    no_space_after = {TokenType.L_PAREN, TokenType.DOT}
    prev_type: TokenType | None = None
    for token_type, text in parts:
        if out and token_type not in no_space_before and prev_type not in no_space_after:
            out.append(" ")
        out.append(text)
        prev_type = token_type
    return "".join(out).strip()


def normalize(sql: str, dialect: str = "postgres") -> str:
    """Normalize *sql* into the M3 canonical form for *dialect*."""
    tree = sqlglot.parse_one(sql, read=dialect)
    _lowercase_unquoted_identifiers(tree)
    rendered = tree.sql(dialect=dialect, normalize=True, pretty=False)
    tokens = Tokenizer(dialect=dialect).tokenize(rendered)
    return _render_tokens(tokens)


def is_canonical(sql: str, dialect: str = "postgres") -> bool:
    """True iff *sql* is already a fixed point of normalization for *dialect*."""
    return normalize(sql, dialect) == sql
