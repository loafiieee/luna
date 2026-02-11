export type ServerInfo = {
  server_id: string;
  name: string;
  edition: "java" | "bedrock" | "both"; // "java" | "bedrock" (and potentially other)
  platform: string;
  version: string;
  folder: string;
  port: number;
  voice_port?: number | null;
  ram: number;
  eula: boolean;
  tunneling: boolean;
  sticky_address: boolean;

  server_dir?: string | null;
  icon_path?: string | null;
  running?: boolean;
  pid?: number | null;

  // runtime is whatever your runtime_state.json contains
  runtime?: any;
};

export type CliEnvelope<T> = {
  event: "result" | "event" | "error";
  command: string;
  timestamp: string;
  data: T;
};

export type LogItem = {
  t: number;
  level: "info" | "ok" | "warn" | "err";
  msg: string;
};

export type DetailTab =
  | "details"
  | "console"
  | "content"
  | "backups"
  | "tunnels"
  | "settings"
  | "server_folder";
