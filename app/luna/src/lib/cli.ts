import { invoke } from "@tauri-apps/api/core";
import type { CliEnvelope } from "./types";

export async function cli<T>(...args: string[]): Promise<CliEnvelope<T>> {
  return await invoke<CliEnvelope<T>>("run_cli_json", { args });
}
