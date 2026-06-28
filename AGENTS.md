# AGENTS.md

## Language Implementation Work

- Before implementing a language target, read `README.md`, `IMPLEMENTING.md`, `design-discussion.md`, `core/spec/00-overview.md`, and the target language spec.
- Do not change `core/spec`, `core/schemas`, or `core/compatibility` only to make a language implementation pass. Treat those artifacts as the source of truth; any change to them must update the spec, schema, fixtures, and cases consistently.
- Implement capabilities in dependency-graph order from `core/spec/dependency-graph.md`, and preserve any language-module dependency-boundary enforcement.
- Use compatibility corpus cases as the primary behavioral verification. Add language unit tests for internal seams, diagnostics, and failure modes.
- Expose implementation conformance through `core/spec/conformance-adapter-contract.md`; do not invent a different language-specific conformance surface.
- For implementation changes, run the smallest relevant language conformance slice plus feasible root verification. Report any skipped database-backed checks.

## Commit Messages

- Every commit subject MUST use a Conventional Commits prefix such as `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, or `ci:`.
- Before running `git commit`, inspect recent history with `git log --oneline -5` and match the repository's subject style.
- Do not bypass Husky for normal commits. If hooks fail because local Node tools are missing, run `pnpm install --frozen-lockfile` and retry the commit.
- Keep commit messages concise and review-oriented.
- Use exactly one blank line between the subject and body.
- Use exactly one blank line between the body paragraph and bullet list.
- Do not include verification commands in the commit message body unless the user asks for them.
