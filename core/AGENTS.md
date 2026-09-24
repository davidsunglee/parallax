# Core Contract Instructions

- Only `core/spec/slices.md` may declare slice-to-module relationships. Files matching `core/spec/m-*.md` must not name slices or claim status; describe consumers as surfaces or sibling modules.
- Follow the repository-root `README.md#adding-or-changing-behavior`. Update the owning specification when intended behavior changes, plus only the schemas, models, fixtures, cases, or benchmarks whose contracts change. Private implementation changes need no core edit.
