"""The shared adapter the two `parallax.snapshot.handle._wrap` suites drive.

`wrap_graph` takes an accepted Metamodel and a class index separately, because
the composition root is the one place that pairs them; a test names the Domain
Model instead and lets this adapter take both off it. Shared by
`test_snapshot_wrap_identity.py` and `test_snapshot_wrap_values.py`, which split
one seam by observable behavior.

Exported names carry no leading underscore: importing an underscored name across
modules is a `reportPrivateUsage` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from parallax.core import DomainModel
from parallax.core.entity._model import class_index, model_of
from parallax.core.metamodel import Metamodel
from parallax.core.temporal_read import Pin
from parallax.snapshot.handle._wrap import wrap_graph
from parallax.snapshot.materialize import Node

__all__ = ["wrap"]

_NO_PIN = Pin()


def wrap(
    nodes: tuple[Node, ...],
    target: str,
    domain: DomainModel,
    pin: Pin = _NO_PIN,
    model: Metamodel | None = None,
) -> tuple[object, ...]:
    """Wrap ``nodes`` through ``domain``'s own accepted model and class index.

    ``model`` overrides the model wrapping reads without changing the class
    index, which is how the suites exercise a model and its classes disagreeing —
    a member the model calls a value object while the composed class maps it as a
    scalar. Only a test can reach that state: the composition root always takes
    both facts off one Domain Model.
    """
    classes = class_index(domain)
    assert classes is not None, "the wrap suites compose class-backed models"
    return wrap_graph(nodes, target, model if model is not None else model_of(domain), pin, classes)
