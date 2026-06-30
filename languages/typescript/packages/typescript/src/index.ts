/**
 * `@parallax/typescript` — the composition root.
 *
 * Owns the `parallax` and `parallax-conformance` CLIs, the generator config
 * API, the public runtime facade, and generated-barrel support. It may import
 * any numbered or support package; no package may import it.
 *
 * The public runtime facade (`parallax(...)`, the typed surface) lands in
 * Phase 9. This phase ships the CLI entry points only.
 */
export {};
