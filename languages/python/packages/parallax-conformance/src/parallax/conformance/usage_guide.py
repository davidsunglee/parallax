"""``parallax.conformance.usage_guide`` — the ``gen-usage-guide`` generator.

Renders the Usage Guide from the API Conformance Suite's registered examples
into ``languages/python/docs/usage-guide.md``. ``--check`` compares the current
file to freshly generated output and fails on drift (the CI drift gate); the
default mode writes the file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from parallax.conformance import api_suite, case_format

__all__ = ["generate", "guide_path", "main"]


def guide_path() -> Path:
    """The committed Usage Guide path, discovered relative to the repo root."""
    return case_format.find_repo_root() / "languages" / "python" / "docs" / "usage-guide.md"


def generate() -> str:
    """The Usage Guide markdown for the currently registered examples."""
    return api_suite.render_usage_guide(api_suite.EXAMPLES)


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
