from __future__ import annotations

from typing import Any

import pytest

from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.core import LATEST
from parallax.snapshot import Database
from tests._support import live_read_workloads as workloads
from tests._support.bindings import TEST_BINDING


@pytest.mark.parametrize("workload", workloads.WORKLOAD_IDS)
def test_frozen_live_reads_match_their_exact_oracle_in_every_delivery(
    profile_run: Any, workload: str
) -> None:
    workloads.provision(workload, profile_run)
    observation = LifecycleObservation()
    with Database.connect(
        profile_run.port,
        workloads.domain_model(workload),
        lifecycle_provider=observation.provider,
        binding=TEST_BINDING,
    ) as root:
        database = root.using_database_login()
        counts = workloads.verify(database, workload, observation)
        assert set(counts) == {"typed.eager", "typed.page32", "wire.eager", "wire.page32"}
        for lane in ("typed", "wire"):
            for form in ("eager", "page32"):
                assert workloads.read(database, workload, lane, form) == workloads.ROOTS


@pytest.mark.parametrize(
    "workload,entity",
    [
        ("historical-txtime", workloads.HistoricalLedger),
        ("historical-bitemporal", workloads.HistoricalPosition),
    ],
)
def test_history_fixture_discriminates_current_and_out_of_window_rows(
    profile_run: Any, workload: str, entity: type[Any]
) -> None:
    workloads.provision(workload, profile_run)
    with Database.connect(
        profile_run.port, workloads.domain_model(workload), binding=TEST_BINDING
    ) as root:
        database = root.using_database_login()
        query = entity.where(entity.all)
        if workload == "historical-bitemporal":
            query = query.as_of(valid_time=workloads.VALID_INSTANT)
        current = database.find(query.as_of(tx_time=LATEST)).results()
        assert len(current) == 200
        assert all(":version-2:" in row.payload for row in current)
        before = workloads.TX_BOUNDARIES[0].replace(year=2023)
        assert database.find(query.as_of(tx_time=before)).results() == []
        if workload == "historical-bitemporal":
            outside = workloads.VALID_BOUNDARIES[-1]
            assert (
                database.find(
                    entity.where(entity.all).as_of(tx_time=workloads.TX_INSTANT, valid_time=outside)
                ).results()
                == []
            )
