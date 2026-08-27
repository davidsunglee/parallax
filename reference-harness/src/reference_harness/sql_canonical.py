"""The vocabulary every m-sql canonicality check shares.

Which sqlglot dialect parses a parallax dialect, and the refusal a statement that
is not in m-sql canonical form raises. Held apart from the checks themselves so the
normalizer (``sql_normalize``) and the wrapped-union verifier (``sql_wrapped_union``)
speak the same refusal without either depending on the other.
"""

from __future__ import annotations

# Map a parallax dialect identifier to the sqlglot dialect that parses/renders it.
# ``mariadb`` has no dedicated sqlglot dialect; MariaDB is MySQL-protocol-compatible
# and sqlglot's ``mysql`` dialect parses + renders the SQL we need, so the MariaDB
# normalization pass runs through ``mysql``. Any dialect not listed here is passed to
# sqlglot verbatim (``postgres`` is its own sqlglot dialect).
_SQLGLOT_DIALECT = {"mariadb": "mysql"}


def sqlglot_dialect(dialect: str) -> str:
    """The sqlglot dialect that parses/renders the parallax *dialect*.

    ``mariadb`` maps to sqlglot's ``mysql`` (MariaDB is MySQL-protocol-compatible
    and sqlglot has no dedicated MariaDB dialect); every other dialect is its own
    sqlglot dialect and passes through. Used by both the normalizer and the static
    SQL lint so a statement entry's ``sql.mariadb`` text is parsed under the right dialect.
    """
    return _SQLGLOT_DIALECT.get(dialect, dialect)


class NonCanonicalError(ValueError):
    """*sql* violates an m-sql canonical rule enforced structurally rather than by
    re-rendering: the read alias scheme + column qualification (rule 1), ``?`` bind
    placeholders for parameters (rule 4), and the shape of the derived table an
    ordered or limited abstract read wraps its ``union all`` as.

    Lowercasing and re-spacing alone do not catch these, so without this check
    ``normalize`` would return a lowercase-but-non-canonical statement unchanged
    and ``is_canonical`` / ``sql_lint`` would wrongly accept it as a fixture.
    """
