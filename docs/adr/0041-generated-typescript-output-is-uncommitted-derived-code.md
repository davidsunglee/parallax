# Generated TypeScript output is uncommitted derived code

The generated TypeScript API is not committed to source control by default. Projects should gitignore the configured generated output directory and regenerate it during install, build, and CI. Users are not expected to edit generated files, and framework versions may change the emitted implementation details without requiring application source changes.

The committed source of truth is the Parallax descriptor set plus generator configuration. This keeps generated implementation churn out of reviews, makes upgrades a generator concern, and avoids treating the generated API as application-owned source. The cost is that generation must be deterministic, fast enough for normal development, and available before TypeScript typechecking or editor workflows that depend on generated imports.

The TypeScript package provides both a normal generation command and a CI-oriented check mode. `parallax generate` materializes the gitignored output directory so TypeScript can typecheck and build against it. `parallax generate --check` validates the descriptors, generator configuration, and code generation pipeline, then fails if generation would fail. Because generated output is not committed, `--check` is not a drift check against source control; it is a reproducibility and validity check for the generated API.

The default generated output path is `./.parallax/generated`. Generated files are derived implementation detail rather than application-owned source, so the default keeps them outside `src/`. Application code should import through the configured alias, normally `#parallax`, instead of depending on the physical output path.
