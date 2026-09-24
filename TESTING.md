# Testing Parallax

## Workflow

1. While iterating, select the tests or execution command covering the change.
   Python placement and fixtures are in
   [its testing map](languages/python/TESTING.md).
2. Before running an aggregate, inspect its execution owners with
   `just show-gates <command>`.
3. After the last relevant change, run `just check` directly. It is the local
   merge gate. Report its result and any skipped database checks.
4. After a failure, fix and rerun the focused owner. Repeat the aggregate only
   after relevant changes.

The local merge gate omits the `cost` class. CI owns that class and the complete
aggregate, `just check-all`; do not run the complete or cost aggregates locally.
While changing memory instruments or a suite that reads a whole interpreter,
`just python-check-cost` is the focused iteration command for that work.

## Finding a command

`just --list` is the command catalog. `just show-gates` renders the command
graph; add a command name to inspect its closure. The [justfile](justfile) owns
commands, execution ownership, and scheduling metadata. This document does not
maintain a second inventory.

Useful focused selectors include `just python-test-<surface>` for a Python
semantic surface and `just harness-test-contract-tools` for language-contract
diagnostics. Select a specific test module through that scope's test runner when
the change is narrower. A focused pass is not a merge-gate result.

[The testing contract](core/spec/language-testing.md) defines the command
grammar and scheduling rules. `just check-gates` checks the graph, test layout,
runner configuration, cited command names, and actual CI execution coverage.

## Databases

Database-backed commands need a reachable Docker daemon. See
[Docker setup](README.md#running-and-inspecting-the-project) for alternative
runtimes. The Python fixture's `PARALLAX_REQUIRE_DB=1` mode turns a skipped
database into a failure; always report unavailable providers.

## CI and cost evidence

[ci.yml](.github/workflows/ci.yml) owns job names, matrices, and shard counts.
Its job union covers the complete required graph, including the cost class.
Event checks such as secret scanning and commit-message validation remain
native workflow steps.

Committed cost evidence is also checked for freshness by CI. A change to a
digested workload input can require a new capture even when the local merge
gate passes. [cost-report.yml](.github/workflows/cost-report.yml) owns automated
captures: the `cost-report` pull-request label, manual dispatch, and scheduled
runs. The Python [cost report tool](languages/python/tools/cost_report.py)
owns measurement and comparison; the
[event adapter](languages/python/tools/cost_report_adapter.py) owns request
pinning and artifact selection.

For a local capture use `just python-report-cost`. For a diagnostic subset,
run `uv run python tools/cost_report.py --help` from `languages/python`.
Diagnostic output is not a retained evidence envelope. Cost gates and
measurement budgets remain in their executable configuration.

## Local permissions

Tracked command permissions live in `.claude/settings.json`. Untracked local
overrides may contain obsolete names; prune those locally when necessary.
