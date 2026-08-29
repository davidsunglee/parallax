"""A second `m-dialect` `Dialect`, for a test that must tell two ports' spellings apart.

Exported without a leading underscore: importing an underscored name across
modules is a `reportPrivateUsage` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

import dataclasses

from parallax.core.dialect import POSTGRES, Dialect

__all__ = ["BACKTICKED"]

BACKTICKED: Dialect = dataclasses.replace(
    POSTGRES,
    name="backticked",
    quote_char="`",
    reserved=frozenset({"id", "owner", "balance", "version"}),
)
"""A dialect differing from ``POSTGRES`` only in how it spells an identifier.

Every SQL string compiled through it is therefore distinguishable, character by
character, from the same SQL compiled through ``POSTGRES`` — which is what lets
a test read which port's dialect spelled a statement off the statement itself,
without depending on any real pair of dialects disagreeing about that construct.
"""
