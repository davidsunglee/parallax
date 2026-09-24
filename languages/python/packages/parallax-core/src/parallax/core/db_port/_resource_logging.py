from __future__ import annotations

import logging
from typing import Final, Literal

from parallax.core.db_port._resources import CleanupCode, CleanupIssue, CleanupResult
from parallax.core.diagnostics import guarded

__all__ = [
    "RESOURCE_LOGGER_NAME",
    "ResourceCondition",
    "report_resource_issues",
    "report_unregistration_failure",
]

type ResourceCondition = Literal["startup", "operation", "shutdown", "unregistration"]
"""The occasions on which this logger speaks at all.

Three of them are outside any execution: startup unwinds before observation
exists, and shutdown and the unregistration after it run once it is gone, which
is why none of them could be reported as an event even in principle.
``operation`` is the one that can be observed, and it reports here whenever
nothing else received it.
"""

RESOURCE_LOGGER_NAME: Final = "parallax.resources"
"""The one logger name a resource problem is reported under.

Fixed rather than derived, so an operator silences or routes resource reporting
by naming one logger, and so nothing about a connection ever becomes part of a
logger name.
"""

_LOGGER: Final = logging.getLogger(RESOURCE_LOGGER_NAME)

_EXPLANATIONS: Final[dict[CleanupCode, str]] = {
    "state-unreadable": (
        "the connection's state could not be read, so its reuse could not be established"
    ),
    "not-idle": "the connection was not idle when released, so it was not offered for reuse",
    "suspect": "the execution declared the connection untrustworthy, so it was not reused",
    "close-failed": "closing the connection failed, so its disposal is not established",
    "handoff-failed": "returning the connection failed, so its accounting is not established",
    "authorization-restore-failed": (
        "restoring the connection's authorization failed, so it was not offered for reuse"
    ),
}
"""One fixed sentence per cleanup code, and the whole of what may be said.

Fixed text rather than a formatted one: the condition is already classified, and
a message assembled from a failure is how native text reaches a log nobody
audited.
"""

_CONDITIONS: Final[dict[ResourceCondition, str]] = {
    "startup": "a database runtime that failed to start could not release everything it took",
    "operation": "a database operation could not release the connection it held",
    "shutdown": "a database runtime being closed could not release everything it held",
    "unregistration": "a pool observation registered at composition could not be closed",
}
"""The fixed sentence each occasion is reported under."""


def _issue_line(issue: CleanupIssue) -> str:
    return f"{issue.phase}/{issue.code}: {_EXPLANATIONS[issue.code]}"


def report_resource_issues(condition: ResourceCondition, result: CleanupResult | None) -> None:
    """Report ``result``'s issues under ``condition``, and never raise.

    Silent when there is nothing to say — an absent result, or one whose steps
    all completed — so this stays failure-only reporting rather than
    instrumentation of a working path.

    Guarded end to end: a logging configuration that raises must not prevent the
    cleanup this is describing, nor replace the primary error that cleanup ran
    beside.
    """
    if result is None or not result.issues:
        return
    guarded(lambda: _emit(condition, result), None)


def report_unregistration_failure() -> None:
    """Report that a pool observation would not close, and never raise.

    Deliberately parameterless. There is no cleanup phase or code here — nothing
    was released — and what raised is the application's own observer holding
    the application's own state, so a message assembled from it would be exactly
    the unaudited disclosure this logger exists to prevent. The one fact worth
    stating is that an interest registered at composition outlived the handle
    that registered it.
    """
    guarded(lambda: _LOGGER.warning("%s", _CONDITIONS["unregistration"]), None)


def _emit(condition: ResourceCondition, result: CleanupResult) -> None:
    headline = _CONDITIONS[condition]
    for issue in result.issues:
        _LOGGER.warning("%s [%s]", headline, _issue_line(issue))
