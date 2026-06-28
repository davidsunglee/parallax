# Parallax init writes project setup conservatively

The TypeScript CLI provides `parallax init` as a setup assistant that can create or update the project files needed for generation and imports. It should configure the Parallax generator rather than merely print instructions.

`parallax init` may create or update:

- `parallax.config.ts`
- the gitignore entry for generated output
- package scripts for generation and checks
- resolver configuration for the generated import alias

The command must be conservative about overwrites. It supports `--dry-run` to preview planned changes and `--force` to overwrite conflicting existing content. Without `--force`, conflicting files or settings produce a `ParallaxConfigurationError` or `ParallaxValidationError` with accumulated issues explaining what must be resolved.

By default, `init` adds explicit package scripts only:

```json
{
  "scripts": {
    "parallax:generate": "parallax generate",
    "parallax:check": "parallax generate --check"
  }
}
```

It does not automatically add lifecycle hooks such as `prebuild` or `pretest`, because lifecycle scripts can surprise projects. An opt-in flag such as `--wire-lifecycle` may add those hooks for teams that want generation wired into build and test commands.
