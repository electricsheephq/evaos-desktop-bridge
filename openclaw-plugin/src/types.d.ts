declare module "openclaw/plugin-sdk/plugin-entry" {
  export function definePluginEntry(entry: unknown): unknown;
}

declare module "node:child_process" {
  export function execFile(...args: unknown[]): unknown;
}

declare module "node:util" {
  export function promisify(fn: unknown): (...args: unknown[]) => Promise<unknown>;
}

declare module "node:fs/promises" {
  export function mkdir(path: string, options?: { recursive?: boolean }): Promise<void>;
  export function writeFile(path: string, data: unknown): Promise<void>;
}

declare module "node:path" {
  const path: {
    join(...parts: string[]): string;
  };
  export default path;
}

declare const process: {
  env: Record<string, string | undefined>;
};

declare const Buffer: {
  from(value: string, encoding: string): unknown;
  from(value: ArrayBuffer): unknown;
};
