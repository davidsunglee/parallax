# Slice tags follow the slice-naming convention

A Conformance Slice's name *is* its `caseTags.include` tag, and slice tags follow a fixed convention: lowercase, matching `^slice-[a-z0-9][a-z0-9-]*$` — a `slice-` prefix followed by a short, language-neutral purpose name and an ordinal. Under this convention the canonical first slice was renamed `first-implementation-mvp` → `slice-mvp-1`; the ordinal leaves room for successors and siblings without any name going stale. The convention itself is normative in `core/spec/slices.md`; the original slice-definition ADRs folded into the Considered Options below.

**Considered options.**

- Per-language slice tags (e.g. `slice-typescript-1`) were rejected: slices are core-defined and language-neutral, so per-language tags would force re-tagging the same shared corpus files for every adopter, and *which* language claims a slice already lives in the `adapter` identity of that language's `describe` response — not in the tag.
- The long-form `slice-first-implementation-mvp` was rejected: "first-implementation" goes stale the moment a second language adopts the slice, while the ordinal already carries the sequencing the name needs.
- From the folded first-slice ADR: whole-module scope, full module parity, absence-based membership, a dedicated profile manifest, and a `profile` wire key were rejected in favor of the include-driven slice membership now specified in `core/spec/slices.md`.
- From the folded first-adopter ADR: a broader implementation-specific first slice and a documented benchmark superset were rejected in favor of exact adoption of the canonical slice.
