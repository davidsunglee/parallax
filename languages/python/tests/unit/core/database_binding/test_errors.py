"""m-database-binding: the aggregated binding refusal."""

from __future__ import annotations

import pickle

import pytest

from parallax.core.internal.base import UsageError
from parallax.core.internal.database_binding import REQUIRED, BindingError, BindingIssue


def test_issues_are_canonically_ordered_and_free_of_repeats() -> None:
    later = BindingIssue("binding-field-unknown", ("namespaces", "a", "x"))
    earlier = BindingIssue("binding-value-invalid", ("default",))
    same_path = BindingIssue("binding-field-missing", ("namespaces", "a", "x"))
    error = BindingError(
        "binding-definition-rejected",
        [later, earlier, same_path, BindingIssue(later.code, later.path, message="again")],
    )
    assert error.issues == (earlier, same_path, later)
    assert isinstance(error, UsageError)
    assert str(error).startswith("binding-definition-rejected: 3 issue(s)")


def test_issue_identity_excludes_the_message() -> None:
    assert BindingIssue("c", ("p",), message="a") == BindingIssue("c", ("p",), message="b")


def test_a_refusal_names_at_least_one_issue() -> None:
    with pytest.raises(ValueError, match="at least one issue"):
        BindingError("binding-definition-rejected", [])


def test_a_refusal_survives_pickling_with_its_issues() -> None:
    error = BindingError("binding-definition-rejected", [BindingIssue("c", ("p",))])
    restored = pickle.loads(pickle.dumps(error))
    assert restored.issues == error.issues
    assert restored.code == error.code


def test_the_omission_marker_reads_as_a_required_binding_in_a_signature() -> None:
    assert repr(REQUIRED) == "<binding required>"
