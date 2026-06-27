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
