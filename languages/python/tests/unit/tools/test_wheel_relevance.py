from __future__ import annotations

import pytest

from wheel_relevance import changed, relevant


@pytest.mark.parametrize(
    "path",
    [
        "languages/python/uv.lock",
        "languages/python/pyproject.toml",
        "languages/python/packages/parallax-postgres/pyproject.toml",
        "languages/python/packages/parallax-core/pyproject.toml",
        "languages/python/packages/parallax-postgres/setup.py",
        "languages/python/packages/parallax-postgres/src/parallax/postgres/_cloaders.pxi",
        "languages/python/packages/parallax-postgres/src/parallax/postgres/_psycopg_layout/cloader.pxi",
        "languages/python/packages/parallax-postgres/src/parallax/postgres/_connection.py",
        "languages/python/packages/parallax-core/src/parallax/core/base/_neutral.py",
        "languages/python/tests/provider_contract/test_postgres_timestamp_delivery.py",
        "languages/python/tests/_support/binary32.py",
        "languages/python/tools/validate_wheel.py",
        ".github/workflows/wheels.yml",
    ],
)
def test_wheel_inputs_require_the_complete_matrix(path: str) -> None:
    assert relevant([path])


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "languages/python/docs/guide/03-reading.md",
        "infra/aws/lib/test-environment-stack.ts",
        "languages/python/packages/parallax-core/src/parallax/core/read_planning/_plan.py",
        "languages/python/packages/parallax-core/src/parallax/core/unit_work/_changes.py",
        "languages/python/packages/parallax-snapshot/src/parallax/snapshot/_publication/__init__.py",
        "languages/python/tests/unit/core/read_planning/test_plan.py",
    ],
)
def test_unrelated_python_documentation_and_infrastructure_changes_skip_wheels(path: str) -> None:
    assert not relevant([path])


def test_an_unknown_change_base_requires_validation() -> None:
    assert changed("0" * 40)
