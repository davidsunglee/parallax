/**
 * `@parallax/lists` — M5 lists & bulk/set operations.
 *
 * The lazy, operation-backed `ParallaxList` and the public error classes it
 * throws (`ParallaxError` / `ParallaxNotFoundError` / `ParallaxTooManyResultsError`).
 */
export {
  type IdentityKey,
  type ListResolver,
  ParallaxError,
  ParallaxList,
  type ParallaxListOptions,
  ParallaxNotFoundError,
  ParallaxTooManyResultsError,
} from "./parallax-list.js";
