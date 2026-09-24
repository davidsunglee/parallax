from __future__ import annotations

import argparse
import sys
from pathlib import Path

from parallax.conformance import api_suite, case_format

__all__ = ["generate", "guide_path", "main"]

_GUIDE_CASE_IDS = (
    "m-predicate-002",
    "m-predicate-020",
    "m-object-query-003",
    "m-navigate-004",
    "m-inheritance-012",
    "m-temporal-read-003",
    "m-value-object-019",
    "m-unit-work-001",
    "m-unit-work-005",
    "m-unit-work-006",
    "m-bitemp-write-001",
    "m-unit-work-041",
)


def guide_path() -> Path:
    """The committed Usage Guide path, discovered relative to the repo root."""
    return case_format.find_repo_root() / "languages" / "python" / "docs" / "usage-guide.md"


def generate() -> str:
    by_case = {example.case_id: example for example in api_suite.EXAMPLES}
    examples = [by_case[case_id] for case_id in _GUIDE_CASE_IDS]
    return api_suite.render_usage_guide(examples, api_suite.RECIPES)


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point for ``gen-usage-guide``."""
    parser = argparse.ArgumentParser(prog="gen-usage-guide")
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail on drift instead of writing the Usage Guide",
    )
    args = parser.parse_args(argv)

    rendered = generate()
    path = guide_path()

    if args.check:
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current != rendered:
            print(
                f"gen-usage-guide: {path} is out of date; run `uv run gen-usage-guide`.",
                file=sys.stderr,
            )
            return 1
        print(f"gen-usage-guide: {path} is up to date")
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    print(f"gen-usage-guide: wrote {path}")
    return 0
