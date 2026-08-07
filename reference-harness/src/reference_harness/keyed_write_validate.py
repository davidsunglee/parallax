"""Model-aware KEYED-INSTRUCTION validation (m-unit-work).

The two other write validators judge a *payload*: `write_validate` walks a
neutral write row's value-object documents, `predicate_write_validate` judges a
predicate-selected instruction's target and assignments. This one judges the
**shape of a keyed instruction itself** — the members `mutation` / `entity` /
`rows` carry *together* — against what its target's temporal profile admits:

* ``temporal-keyed-write-multi-row`` — a keyed instruction on a **temporal**
  target carries more than one row. Each row of a milestone chain closes its own
  current milestone, consumes its own Temporal Observation, and opens its own
  successors, and a temporal target never collapses into a set-based statement
  (`m-batch-write`), so several rows under one instruction denote several
  independent chains rather than one wider write. Settling the first row and
  discarding the rest is what the rule forbids, which is why refusing is the only
  conforming answer even when the discarded rows would each have lowered to
  well-formed SQL of their own.

The bound is model-dependent — it exists only for a temporal target — so the
shared case schema states the general one-or-more `rows` bound and leaves this to
a validator that can see the model. Two callers reach it: a `scenario` step's own
buffered write (:mod:`reference_harness.schema_validate`), and the `rejected`
lane's keyed `when.write` (:mod:`reference_harness.case_runner`), where the
instruction is itself the input under test. One rule, one wording, so those two
lanes cannot be read as saying different things. A `when.writeSequence` entry is
NOT among them — this harness grades a write sequence by executing its golden
DML rather than by translating its entries, so it inspects no instruction there.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .case import Entity
from .value_object_resolve import RejectionError

TEMPORAL_KEYED_WRITE_MULTI_ROW = "temporal-keyed-write-multi-row"

KEYED_WRITE_REJECTED_RULES: frozenset[str] = frozenset({TEMPORAL_KEYED_WRITE_MULTI_ROW})


def validate_keyed_write(entity: Entity, instruction: Mapping[str, Any]) -> None:
    """Reject *instruction* pre-SQL if its shape is inadmissible for *entity*.

    *entity* is the effective definition of the instruction's own ``entity``
    handle, so a concrete subtype inherits the root's temporality unchanged
    (`m-inheritance`). Raises :class:`RejectionError` naming the violated rule.
    """
    rows = instruction.get("rows")
    if not isinstance(rows, list) or len(rows) <= 1:
        return
    if not entity.is_temporal:
        return
    mutation = instruction.get("mutation")
    raise RejectionError(
        TEMPORAL_KEYED_WRITE_MULTI_ROW,
        f"a keyed {mutation!r} on the temporal entity {entity.name!r} carries {len(rows)} rows "
        f"— a temporal keyed instruction carries exactly one (m-unit-work), since each row "
        f"closes its own milestone, consumes its own observation, and chains its own "
        f"successors; author one instruction per row",
    )
