# TypeScript tooling uses pnpm

Repository-level TypeScript and Node tooling uses pnpm. The root package declares pnpm in `packageManager`, commits `pnpm-lock.yaml`, and avoids npm or yarn commands in CI and contributor instructions.

Using one package manager keeps lockfile behavior, script execution, workspace installation, and generated-code setup predictable. Contributors should install dependencies with `pnpm install --frozen-lockfile`, run scripts with `pnpm run ...`, and invoke local binaries with `pnpm exec ...`.
