import { spawnSync } from "node:child_process";
import { devNull } from "node:os";

/** One child process a tool runs, and where. */
export interface Command {
  readonly program: string;
  readonly args: readonly string[];
  readonly cwd: string;
}

/** Runs *command* to completion, returning its exit status. */
export type Runner = (command: Command, env: Readonly<Record<string, string>>) => number;

/**
 * The whole environment a verification child process receives: the executable
 * search path, a home of its own, and settings that leave every AWS credential
 * source and the instance metadata service unreachable. Nothing else is
 * inherited, so no credential, profile, or user-level CDK setting can reach it.
 */
export function isolatedEnvironment(
  inherited: Readonly<Record<string, string | undefined>>,
  home: string,
): Record<string, string> {
  return {
    PATH: inherited["PATH"] ?? "",
    HOME: home,
    AWS_CONFIG_FILE: devNull,
    AWS_SHARED_CREDENTIALS_FILE: devNull,
    AWS_EC2_METADATA_DISABLED: "true",
    CDK_DISABLE_CLI_TELEMETRY: "true",
    CI: "true",
  };
}

/** Runs a child process with its output on this process's own streams. */
export const runInherited: Runner = (command, env) =>
  spawnSync(command.program, command.args, { cwd: command.cwd, env, stdio: "inherit" }).status ?? 1;
