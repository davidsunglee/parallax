from __future__ import annotations

from typing import Final, Literal

from parallax.core.base import UsageError
from parallax.core.write_plan.keys import ObjectKey

__all__ = [
    "VERSION_UNOBSERVED",
    "WRITE_EVIDENCE_ALREADY_CLAIMED",
    "WRITE_EVIDENCE_CONSUMED",
    "WRITE_EVIDENCE_INSERTED",
    "WRITE_EVIDENCE_UNAVAILABLE",
    "WRITE_VALUE_ALREADY_STORED",
    "WRITE_VALUE_FOREIGN_LIFECYCLE",
    "WRITE_VALUE_NOT_STORED",
    "KeyedWriteValueCode",
    "WriteEvidenceCode",
    "write_evidence_refusal",
]

VERSION_UNOBSERVED: Final = "version-unobserved"
"""A keyed update or delete of an explicitly versioned row reached settlement
carrying no observed version, refused before any DML runs under either
Effective Concurrency Strategy.

The new version is computed from the observed one, and the framework never
issues an implicit resolving read on behalf of a keyed write, so this is a
read-before-write programming error.
"""

type WriteEvidenceCode = Literal[
    "write-evidence-unavailable",
    "write-evidence-consumed",
    "write-evidence-already-claimed",
    "write-evidence-inserted",
]
"""The write-evidence refusals a keyed verb raises.

The first three partition what can be wrong with a source's evidence at the
verb: there is none the target Entity's Effective Concurrency Strategy can use,
the evidence there is reaches no state this attempt still protects — published
from rows a completed write changed, of an object a completed deletion removed,
or of a temporal state a completed write left nothing of at the source's pin —
or a write already buffered in this unit
of work claimed the scope this one settles against, for an intent this one
cannot join. The fourth refuses a caller's own condition on an
object this attempt inserted, which only that insertion's source or a read
addresses.

Each is raised synchronously at the verb, before any buffering and before any
database access, and its message names the object the write addressed. A
conflict the database discovers later is a different thing entirely and keeps
its own flush-time classification.
"""

WRITE_EVIDENCE_UNAVAILABLE: Final = "write-evidence-unavailable"
WRITE_EVIDENCE_CONSUMED: Final = "write-evidence-consumed"
WRITE_EVIDENCE_ALREADY_CLAIMED: Final = "write-evidence-already-claimed"
WRITE_EVIDENCE_INSERTED: Final = "write-evidence-inserted"


def write_evidence_refusal(
    code: WriteEvidenceCode, object_key: ObjectKey, reason: str
) -> UsageError:
    """The write-evidence refusal of a write addressing ``object_key``, which
    the message names so a caller can say WHICH write was refused."""
    return UsageError(
        code,
        f"{object_key.entity.canonical} {dict(object_key.primary_key)!r}: {reason}",
    )


type KeyedWriteValueCode = Literal[
    "write-value-not-stored",
    "write-value-already-stored",
    "write-value-foreign-lifecycle",
]
"""The keyed-write value refusals (`m-unit-work` "Write value provenance").

The three answer to the three
:data:`~parallax.core._execution._keyed_writes.Provenance` answers — no managed
source published this value, this verb's own source did, another managed
source did — so a refused value carries exactly one of them. The value itself
is never retained: what the refusal is about is which source published it, and
the message names the Entity the write addressed and the verb that does accept
the value.
"""

WRITE_VALUE_NOT_STORED: Final = "write-value-not-stored"
WRITE_VALUE_ALREADY_STORED: Final = "write-value-already-stored"
WRITE_VALUE_FOREIGN_LIFECYCLE: Final = "write-value-foreign-lifecycle"
