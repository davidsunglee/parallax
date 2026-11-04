# Retry timing is a public policy, and the fixed window grows to its maximum

The retry bound and the delay before each replay become one immutable **Retry
Policy**, replacing the integer `max_retries` option. A root, scope, writable
invocation, or read-only invocation names it as `retry`; omission inherits, and an
explicit policy replaces the inherited one whole. A join compares complete
policies by value. There is no compatibility spelling: `max_retries=` is an unknown
keyword, as `retries=` already was.

Two timing inputs are public, `baseDelay` and `maxDelay`. The doubling, the
duration multiplier, and full jitter stay fixed. The built-in policy keeps ten
re-executions, an 8 ms base, a 1 s maximum, and the duration adaptation, and drops
the 25 ms plateau: the fixed window now doubles until the maximum.

## Why

ADR 0073 kept timing internal because a delay chosen from contention evidence
needed no public setting. Deployments disagree about the latency a conflict is
worth: retry budgets, slow commits, and remote databases all trade tail latency
against contention differently, and the budget alone cannot express that. A field
is public only where it decides something no other field can. `baseDelay` sets the
whole early schedule, the only way to lengthen the first waits when a replay fails
quickly but its cause clears slowly, and `maxDelay` bounds a single wait. Growth is
already fixed by those two, and the duration multiplier and jitter shape have one
measured configuration and no deployment question behind them.

The plateau came from one contention grid on one machine. It left a fast-failing
replay, such as a Serializable pivot cancellation that takes under a millisecond,
waiting at most 224 ms across ten retries, while a winning commit can take hundreds
of milliseconds to become visible. Doubling to the maximum waits at most about 4 s
over those retries. It is the shape FoundationDB and Google's client libraries
ship, and the shape the AWS jitter study recommends. Waits lengthen from the third
retry, deliberately, in exchange for fewer wasted attempts under sustained
contention. The duration term remains the refinement no surveyed system has: while
both terms double, it widens the window only for attempts slower than four base
delays.

Reladomo is prior art here, not an adopted rule: its wait is an internal flat
randomized 1-2 s with the same default budget of ten, and no option reaches it.

## Consequences

Timing stops being internal policy, so every portable and binding surface moves
together: the case format's `retry` placements, the outer lifecycle observation,
the log fields, and the exhaustion note. The lifecycle reports the whole resolved
policy, so an observer sees the backoff in effect as well as the bound.

A small budget stays a documented limit rather than a special case. The delay
never reads which failure occurred, so a minimum wait for serialization failures
would put classification into the timing calculation without bounding the problem,
since nothing limits how long a commit takes to become visible.

The current contention drivers configure these policies through the public keyword
and no longer patch retry internals, so they cannot compare the historical
immediate-replay, fixed-only, or plateaued algorithms. Those comparisons stand as
historical evidence.

Alternatives considered: keeping `max_retries=` as an alias, which forces a bare
bound to either merge into the inherited backoff or quietly reset it; a minimum wait
per failure kind; exposing growth, jitter, or duration scaling, which no deployment
decision calls for; and keeping the plateau, which leaves small budgets exposed to
slow commit visibility.

The contract lives in [`m-auto-retry`](../../core/spec/m-auto-retry.md), and the
Python spelling in [`execution.md`](../../languages/python/spec/execution.md).
