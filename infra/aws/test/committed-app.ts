import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { App } from "aws-cdk-lib";

export const PACKAGE_ROOT = dirname(dirname(fileURLToPath(import.meta.url)));

/** The context the CDK CLI hands the app: the committed `cdk.json` context. */
export function committedContext(): Record<string, unknown> {
  const settings = JSON.parse(readFileSync(join(PACKAGE_ROOT, "cdk.json"), "utf8")) as {
    context: Record<string, unknown>;
  };
  return settings.context;
}

/** An app synthesized from the committed context, with *overrides* applied over it. */
export function committedApp(overrides: Readonly<Record<string, unknown>> = {}): App {
  return new App({ context: { ...committedContext(), ...overrides } });
}

/** A CloudFormation value with every `Fn::Join` flattened and each other intrinsic replaced by a marker. */
export interface Flattened {
  readonly text: string;
  readonly intrinsics: ReadonlyMap<string, unknown>;
}

/**
 * Flatten *value* so a template string built from deploy-time references can
 * be parsed: each non-string part becomes `«n»`, and `intrinsics` says which
 * reference each marker stands for.
 */
export function flatten(value: unknown): Flattened {
  const intrinsics = new Map<string, unknown>();
  const visit = (part: unknown): string => {
    if (typeof part === "string") return part;
    const join = (part as { "Fn::Join"?: [string, unknown[]] })["Fn::Join"];
    if (join !== undefined) return join[1].map(visit).join(join[0]);
    const marker = `«${String(intrinsics.size)}»`;
    intrinsics.set(marker, part);
    return marker;
  };
  return { text: visit(value), intrinsics };
}
