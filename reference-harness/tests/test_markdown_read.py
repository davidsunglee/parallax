"""The body a heading owns, as the prose-vocabulary checks read it."""

from __future__ import annotations

from reference_harness.markdown_read import heading_section

_DOCUMENT = """\
# Title

Preamble.

## Rejected cases

- `rule-one` — first.

### Model rules

Nested body.

## Rejected cases, again

Later body.
"""


def test_heading_section_is_the_first_matching_heading_up_to_the_next_heading() -> None:
    assert heading_section(_DOCUMENT, "Rejected cases") == "\n\n- `rule-one` — first.\n\n"


def test_heading_section_runs_to_the_end_of_the_document_after_the_last_heading() -> None:
    assert heading_section(_DOCUMENT, "again") == "\n\nLater body.\n"


def test_heading_section_is_absent_when_no_heading_contains_the_marker() -> None:
    assert heading_section(_DOCUMENT, "Preamble") is None
