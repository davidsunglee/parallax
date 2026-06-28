# TypeScript exposes public Parallax error classes

The TypeScript runtime exposes a small public error hierarchy rooted at `ParallaxError`. Public Parallax failures use package-owned classes with stable machine-readable `code` values so applications and compatibility tests can branch on type or code rather than parsing messages.

The initial public classes are:

- `ParallaxError`
- `ParallaxConfigurationError`
- `ParallaxValidationError`
- `ParallaxNotFoundError`
- `ParallaxTooManyResultsError`
- `ParallaxTransactionError`
- `ParallaxOptimisticLockError`

Messages remain human-readable diagnostics and may evolve. Stable behavior belongs in the class, `code`, and structured details where applicable.

`ParallaxValidationError` accumulates validation issues rather than failing fast. Descriptor validation, entity input validation, create payload validation, and configuration validation should report all reasonably discoverable issues in one error object. Each issue carries a stable issue code, an input path, and a human-readable message.

Validation issue paths are represented internally as path arrays, such as `["lineItems", 0, "quantity"]`, because they are lossless and convenient for programmatic handling. Public issue objects also expose a JSON Pointer string, such as `/lineItems/0/quantity`, for display, logs, and interchange.

Validation errors use two levels of machine-readable codes. The top-level `ParallaxValidationError` has a broad error code such as `PARALLAX_VALIDATION_FAILED`. Each validation issue has a more specific issue code such as `REQUIRED_ATTRIBUTE_MISSING` or `UNKNOWN_RELATIONSHIP`. This lets callers branch on the broad error class while still presenting precise field-level diagnostics.

The public validation issue shape is:

```ts
type ParallaxValidationIssue = {
  code: string;
  path: readonly (string | number)[];
  pointer: string;
  message: string;
  details?: Record<string, unknown>;
};
```
