from __future__ import annotations

import ast
import hashlib
from collections.abc import Sequence
from typing import Final

WRITE_SOURCES: Final = (
    "tests/unit/_write_lowering_support.py",
    "tests/unit/_structural_geometry_support.py",
    "tests/unit/_leaf_type_support.py",
    "tests/unit/_workload_spelling_support.py",
)


class _WithoutProse(ast.NodeTransformer):
    def visit_Expr(self, node: ast.Expr) -> ast.AST | None:
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return None
        return self.generic_visit(node)


def canonical_source(source: str, *, omit_digest: bool = False) -> bytes:
    """Executable syntax without prose or source positions.

    The write workload's digest declaration describes its identity rather than
    running inside a measured window, so only that top-level declaration may
    be omitted while proving a change to the digest definition itself.
    """
    tree = ast.parse(source)
    if omit_digest:
        tree.body = [
            node
            for node in tree.body
            if not (isinstance(node, ast.FunctionDef) and node.name == "write_lowering_digest")
        ]
    return ast.dump(_WithoutProse().visit(tree), include_attributes=False).encode("utf-8")


def write_digest(sources: Sequence[str], manifests: Sequence[str], *, legacy: bool = False) -> str:
    digest = hashlib.sha256()
    for index, source in enumerate(sources[:3] if legacy else sources):
        digest.update(
            source.encode("utf-8") if legacy else canonical_source(source, omit_digest=index == 0)
        )
        digest.update(b"\0")
    for manifest in manifests:
        digest.update(manifest.encode("utf-8"))
    return digest.hexdigest()
