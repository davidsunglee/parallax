"""Nullable encoded SQL NULL through the shipped Snapshot read surfaces.

The scalar write corpus proves that SQL NULL can be stored in every nullable
direct Column. This database-backed compatibility proof covers the two read
consumers for which an encoded Column is distinct: public row delivery validates
the projection alias, while Typed Snapshot delivery retains the decoded physical
row as predecessor evidence for a later keyed write.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from parallax.core.entity._model import model_of
from parallax.core.object_query import deserialize
from parallax.snapshot import connect
from parallax.snapshot.handle import Transaction
from tests._support import mirrored_models as mm

_TARGET = "parallax.compatibility.WritableScalar"
_ROW_QUERY = deserialize(
    {
        "target": _TARGET,
        "predicate": {"eq": {"attr": f"{_TARGET}.id", "value": 1}},
    }
)


# A nullable bytes Column is projected through PostgreSQL's encoded-text alias,
# but SQL NULL is member absence rather than a Wire literal: row delivery must
# publish None without decoding it, Typed Snapshot delivery must hydrate None,
# and a transaction must retain None under the physical Column as predecessor
# evidence so editing another member commits without decoding the NULL later.
def test_nullable_encoded_sql_null_survives_delivery_and_predecessor_observation(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(mm.WRITABLE_SCALARS_MODEL), {})
    db = connect(profile_run.port, mm.WRITABLE_SCALARS_MODEL)
    db.transact(
        lambda tx: tx.insert(
            mm.WritableScalar(
                id=1,
                f32=None,
                f64=None,
                payload=None,
                local_time=None,
                external_id=None,
                amount=None,
                label="before",
            )
        )
    )

    row = db.read_rows(_ROW_QUERY).rows[0]
    assert isinstance(row, Mapping)
    assert row["payload_hex"] is None

    delivered = db.find(mm.WritableScalar.where(mm.WritableScalar.id == 1)).result()
    assert delivered.payload is None

    def update(tx: Transaction) -> None:
        observed = tx.find(mm.WritableScalar.where(mm.WritableScalar.id == 1)).result()
        assert observed.payload is None
        tx.update(observed.edit(label="after"))

    db.transact(update)
    committed = db.find(mm.WritableScalar.where(mm.WritableScalar.id == 1)).result()
    assert committed.payload is None
    assert committed.label == "after"
