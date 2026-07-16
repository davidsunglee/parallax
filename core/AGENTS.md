# Core Contract Instructions

- Only `core/spec/slices.md` may declare slice-to-module relationships. Files matching `core/spec/m-*.md` must not name slices or claim status; describe consumers as surfaces or sibling modules.
- Follow the repository-root `README.md#adding-or-changing-behavior`. When intended behavior changes, update the affected specification, schemas, models, fixtures, cases, and benchmarks together, then run the applicable root verification gates.
