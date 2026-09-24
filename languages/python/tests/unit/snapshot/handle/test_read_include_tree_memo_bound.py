"""What the memoizing `IncludeTree` a result retains keeps reachable.

ADR 0012 and the *Projection capability and retained shape* rule bound what a
Typed result holds by the includes clause and the model. The tree answers the
Wire walk's per-node questions from a memo it fills as the walk asks them, which
is inside that bound only while its key domain is closed over the plan's
positions and the model's concretes. A walk of ten times the roots asks the same
questions of the same tree many more times; if any answer were keyed by anything
a root carries, the tree would be larger after the larger walk.

The proof is a closure rather than a survivor sample or a byte delta, because
the claim is about one structure's own total state. It reads that structure off
the result through the private field the retention proofs read, since only a
Typed result retains a tree at all, and fills the memo through `wire()`, which
runs the same walk over the same three methods as direct publication. Root count
comes from the port: the read-plan key carries a non-paged query's limit, so two
handles compile their own tree from one identical query and the two closures can
differ only by what their walks filled.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from parallax.conformance.budget import BudgetContract
from parallax.snapshot.handle import Database
from tests.unit import _delivery_control_support as control_support
from tests.unit._gc_reachability import closure

if TYPE_CHECKING:
    from tests.unit._gc_reachability import Closure


def _tree_after_projecting(roots: int) -> Closure:
    port = control_support.GuardedPort(roots)
    root = Database(port.open(), control_support.GUARDED_MODEL)
    try:
        result = root.using_database_login().find(
            control_support.guarded_query(control_support.GUARD_WIDTHS[-1])
        )
        result.wire()
        return closure(cast("Any", result)._includes, ())
    finally:
        root.close()


def test_the_include_tree_memo_is_flat_in_roots() -> None:
    arms = BudgetContract.load().memory_scaling_arms
    small = _tree_after_projecting(arms[0])
    large = _tree_after_projecting(arms[-1])

    assert small.tracked > 0
    assert small == large
