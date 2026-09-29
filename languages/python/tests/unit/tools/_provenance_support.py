"""Provenance captures that do not depend on the live working tree."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from parallax.conformance.cost_envelope import Provenance


def pin_dirty_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    """Record every provenance capture as taken from a dirty tree.

    A capture reads ``dirty`` from ``git status``, so anything creating a file in
    the working tree between two report runs would make otherwise identical
    envelopes differ.
    """
    live = Provenance.capture

    def capture(*arguments: Any, **options: Any) -> Provenance:
        return replace(live(*arguments, **options), dirty=True)

    monkeypatch.setattr(Provenance, "capture", staticmethod(capture))
