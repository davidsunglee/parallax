"""The sole-connection scaffold's runtime lifetime.

Docker-free.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from parallax.conformance._mechanism.sole_connection import ConnectsAsItself
from parallax.core.db_port import ConnectionAcquisitionError, DocumentReadOrdinals, Row
from parallax.core.dialect import POSTGRES


class _NoRows(ConnectsAsItself):
    dialect = POSTGRES

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del sql, binds, document_reads
        return []


def test_a_closed_runtime_refuses_a_new_acquisition() -> None:
    runtime = _NoRows().open()
    execution = runtime.login_execution()
    runtime.close()

    with pytest.raises(ConnectionAcquisitionError) as refused:
        execution.new_context()

    assert refused.value.reason == "closed"
