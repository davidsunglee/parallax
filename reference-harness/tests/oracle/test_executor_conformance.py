"""Who can be handed to the oracle as a reader.

The refactor creates no parallel provider hierarchy: both database providers and
both held transaction sessions already expose ``dialect`` and ``query``, so they
satisfy ``ReadExecutor`` structurally with no declared inheritance and no code
change. Instances are built with ``__new__`` because the check is structural and
constructing one for real boots a container.

That works only while ``dialect`` is a CLASS attribute. A ``runtime_checkable``
protocol's ``isinstance`` is a ``hasattr`` sweep, so a provider that assigned
``dialect`` in ``__init__`` would make every check below silently vacuous — which
is why the attribute's placement is pinned here too.
"""

from __future__ import annotations

import pytest

from reference_harness.object_query_oracle import ReadExecutor
from reference_harness.providers.mariadb import MariaDbProvider, _MariaTxSession
from reference_harness.providers.postgres import PostgresProvider, _PgTxSession

from .conftest import ScriptedReads

_READERS = [PostgresProvider, MariaDbProvider, _PgTxSession, _MariaTxSession]


@pytest.mark.parametrize("reader_type", _READERS, ids=lambda cls: cls.__name__)
def test_a_production_reader_satisfies_the_read_seam(reader_type: type) -> None:
    assert isinstance(reader_type.__new__(reader_type), ReadExecutor)


@pytest.mark.parametrize("reader_type", _READERS, ids=lambda cls: cls.__name__)
def test_the_dialect_a_reader_reports_is_a_class_attribute(reader_type: type) -> None:
    assert isinstance(vars(reader_type).get("dialect"), str)


def test_the_scripted_adapter_satisfies_the_same_seam() -> None:
    assert isinstance(ScriptedReads(), ReadExecutor)


def test_the_seam_admits_nothing_that_cannot_run_a_read() -> None:
    class _DialectOnly:
        dialect = "postgres"

    assert not isinstance(_DialectOnly(), ReadExecutor)
