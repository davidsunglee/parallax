# AGENTS.md

## Core Spec Authoring

- The slice ⇒ module reference is **one-way**: `core/spec/slices.md` names modules; a module spec (`core/spec/m-*.md`) never names a slice or its claim status. Express "who uses this" in terms of surfaces or sibling modules.

## Language Implementation Work

- Before implementing a language target, read `README.md`, `IMPLEMENTING.md`, `core/spec/00-overview.md`, `core/spec/modules.md`, `core/spec/slices.md`, `core/spec/m-conformance-adapter.md`, and the target language spec.
- Do not change `core/spec`, `core/schemas`, or `core/compatibility` only to make a language implementation pass. Treat those artifacts as the source of truth; any change to them must update the spec, schema, fixtures, and cases consistently.
- Implement capabilities in dependency-graph order from `core/spec/modules.md`, and preserve any language-module dependency-boundary enforcement.
- Use compatibility corpus cases as the primary behavioral verification. Add language unit tests for internal seams, diagnostics, and failure modes.
- Expose implementation conformance through `core/spec/m-conformance-adapter.md`; do not invent a different language-specific conformance surface.
- The reference harness's internals are non-normative and MUST NOT be used as design input for a language implementation; the binding inputs are the spec modules, `core/schemas/`, the compatibility corpus, and the conformance-adapter contract.
- For implementation changes, run the smallest relevant language conformance slice plus feasible root verification. Report any skipped database-backed checks.

## Prior Art: Reladomo

- Parallax is informed by Reladomo. The full Reladomo repository is checked out as a peer of this repo (`../reladomo`); research findings live in `docs/research/reladomo/` (start at `00-index.md`).
- When researching a design decision (locking, transactions, temporal semantics, caching), always include how Reladomo handles it as prior art. Parallax generally follows Reladomo's lead on runtime semantics unless a spec module says otherwise.
- Reladomo is prior art, not a template: match its semantics where the spec adopts them, not its Java idioms.

## Task Workflow

- Task artifacts live in `.humanlayer/tasks/<ticket>/` (research, design discussion, structure outline, review findings, handoff docs).
- Implementation of large features happens in per-ticket worktrees (`~/.humanlayer/workspaces/<ticket>/parallax`), never directly on `main` in the primary checkout.
- After each phase, state whether the accumulated unreviewed changes warrant an external code review; unreviewed phases roll forward into the next review's scope. Offer to generate a prompt for the code review, if a review is warranted.

## Commit Messages

- Every commit subject MUST use a Conventional Commits prefix such as `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, or `ci:`.
- Before running `git commit`, inspect recent history with `git log --oneline -5` and match the repository's subject style.
- Do not bypass Husky for normal commits. If hooks fail because local Node tools are missing, run `pnpm install --frozen-lockfile` and retry the commit.
- Keep commit messages concise and review-oriented.
- Use exactly one blank line between the subject and body.
- Use exactly one blank line between the body paragraph and bullet list.
- Do not include verification commands in the commit message body unless the user asks for them.
- Do not add `Co-authored-by`, `Generated with`, or similar trailers to commits.
