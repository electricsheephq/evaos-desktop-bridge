declare module "openclaw/plugin-sdk/plugin-entry" {
  export function definePluginEntry(entry: unknown): unknown;
}

declare module "node:child_process" {
  export function execFile(...args: unknown[]): unknown;
}

declare module "node:util" {
  export function promisify(fn: unknown): (...args: unknown[]) => Promise<unknown>;
}

declare const process: {
  env: Record<string, string | undefined>;
};
