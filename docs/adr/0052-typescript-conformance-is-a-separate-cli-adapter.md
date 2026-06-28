# TypeScript conformance is a separate CLI adapter

The TypeScript implementation exposes core conformance through a separate CLI adapter, not through the generated `#parallax` domain API. The adapter follows the core conformance contract and accepts compatibility corpus files as inputs.

The command surface is:

```text
parallax-conformance describe
parallax-conformance compile --case <case.yaml> --dialect <dialect>
parallax-conformance run --case <case.yaml> --dialect <dialect>
parallax-conformance benchmark --benchmark <benchmark.yaml> --dialect <dialect>
```

Each command writes the JSON envelope required by `core/spec/conformance-adapter-contract.md` to stdout. Human-readable logs may go to stderr.

Keeping conformance as a CLI preserves the separation between application-facing domain APIs and implementation verification. The generated `#parallax` API remains focused on domain operations, while CI and compatibility runners use `parallax-conformance`.
