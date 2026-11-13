"""The standby proofs' pair, reset to the shared routed-read fixtures."""

from __future__ import annotations

from typing import Any

from parallax.conformance._replication import ReplicationPair
from tests._support.bindings import TEST_BINDING
from tests._support.routed_reads import SEEDED_MODEL, seeded_fixtures


def replicated(profile_run: Any) -> ReplicationPair:
    """This run's pair, reset to the seeded rows on both servers."""
    pair: ReplicationPair = profile_run.replication()
    pair.reset(SEEDED_MODEL, seeded_fixtures(), TEST_BINDING)
    return pair
