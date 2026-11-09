"""The composition root is the only source of a Write Planner, and its wiring.

``build_write_planner`` is the planner's only constructor, so every planner
plans under production's one set of strategies. The planner's type says so, and
the static probes below keep it saying so. Its batching and payload wiring are
graded by every write a compatibility case lowers; the audit port is the one
strategy whose production value is a decision rather than an implementation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Never, cast

import pytest

from parallax.conformance import models
from parallax.core._execution._planning import build_write_planner
from parallax.core.unit_work import NO_AUDIT, SubjectActor, WritePlanner
from tests._support.clock_probes import inert_instant

if TYPE_CHECKING:
    from parallax.core.metamodel import Metamodel

_ACCOUNT = models.load_models()["account"]


def test_a_write_planner_is_obtained_only_from_the_composition_root() -> None:
    with pytest.raises(TypeError):
        WritePlanner(cast("Never", _ACCOUNT))


def test_the_composition_root_wires_the_audit_port_to_the_neutral_strategy() -> None:
    # Audit decoration is a wired port with nothing behind it, and this is the
    # wiring half: every planner holds the neutral strategy, so no step reaching
    # audit meets one that could decorate. The other half, that the neutral
    # strategy hands back what it was given, lives in `test_strategy.py`.
    decoration = build_write_planner(_ACCOUNT).audit_decoration(
        actor_identity=SubjectActor("alice"), transaction_instant=inert_instant()
    )

    assert decoration.audit is NO_AUDIT


if TYPE_CHECKING:

    def _static_construction_probes(  # pyright: ignore[reportUnusedFunction] - static contract probe
        model: Metamodel,
    ) -> None:
        """Typechecked, never called: no call but the composition root's builds a
        planner."""
        WritePlanner(model)  # pyright: ignore[reportArgumentType]
        WritePlanner()  # pyright: ignore[reportCallIssue]
        _ = WritePlanner._wired  # pyright: ignore[reportPrivateUsage]

    class SecondPlanner(WritePlanner):  # pyright: ignore[reportGeneralTypeIssues]
        """Typechecked, never defined: no second planner class descends from it."""
