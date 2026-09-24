# Python Target Instructions

- `spec/python.md` is the binding entrypoint. Read the linked binding page and core module relevant to the change; private refactors need no binding edit unless they change an enforced source boundary.
- Preserve the spec's source and artifact topology declarations, `tools/check_dag_sync.py`'s independent mappings, and `tools/check_scope_ownership.py`'s checks. Changes to their enforcement mechanism require explicit design review.
- `pyproject.toml` and package metadata own Python versions, dependencies, tool settings, and quality thresholds. Do not repeat those settings in prose.
- Before changing tests, read `TESTING.md` for placement and fixtures. Root `justfile` recipes and `just show-gates <recipe>` describe verification ownership.
- Keep useful public contracts and critical local rationale in source. Do not require docstrings to list variants, signatures, or behavior already expressed by types, tests, or a contract owner.
- `docs/deferred-ledger.md` tracks open unowned work. Consult relevant entries when touching their subject, record a new deferral only when no issue or task owns it, and remove resolved entries at claim closure. It is not required reading for unrelated changes.
- ADRs record consequential Python-specific decisions and alternatives; ordinary internal refactors need no ADR. `CONTEXT.md` is a terminology index, not another binding specification.
