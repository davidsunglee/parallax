"""The compiled loader modules. Everything else about the build is declared in pyproject.toml."""

from setuptools import Extension, setup

_PACKAGE = "src/parallax/postgres"
_LAYOUT = f"{_PACKAGE}/_psycopg_layout"


def _loaders(build: str) -> Extension:
    """The one loader body, compiled against one psycopg build's C adaptation module."""
    return Extension(
        f"parallax.postgres._cloaders_{build}",
        sources=[f"{_PACKAGE}/_cloaders_{build}.pyx"],
        include_dirs=[_LAYOUT],
        depends=[
            f"{_PACKAGE}/_cloaders.pxi",
            f"{_LAYOUT}/cloader.pxi",
            f"{_LAYOUT}/psycopg_{build}/__init__.pxd",
            f"{_LAYOUT}/psycopg_{build}/_psycopg.pxd",
        ],
    )


setup(ext_modules=[_loaders("binary"), _loaders("c")])
