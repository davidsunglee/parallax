/**
 * Negative-test fixture: a deliberately illegal cross-package import.
 *
 * `@parallax/core` is the foundational leaf (M0); it MUST NOT depend on any
 * sibling. Importing `@parallax/operation` (M2) here is a wrong-direction edge
 * that `depcruise --validate` must flag as `not-in-allowed`.
 *
 * This file lives under `test/fixtures/` and is excluded from both the `tsc -b`
 * build (`include: ["src/**\/*.ts"]`) and the real workspace dependency-cruiser
 * validation (which is scoped to `packages/*\/src`). It is referenced only by
 * `dep-boundary.test.ts`, which points dependency-cruiser at it on purpose and
 * asserts a non-zero exit.
 *
 * A relative import (rather than the `@parallax/operation` specifier) keeps the
 * edge resolvable regardless of whether sibling packages have been built.
 */
// @ts-nocheck — fixture is never compiled; the import is intentionally illegal.
import "../../../operation/src/index.js";
