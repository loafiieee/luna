#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use serde_json::Value;
use std::{
  fs::{File, OpenOptions},
  io::{BufRead, BufReader, Seek, SeekFrom, Write},
  path::PathBuf,
  process::Command,
};

fn find_cli_exe() -> Result<PathBuf, String> {
  let mut dir = std::env::current_exe().map_err(|e| e.to_string())?;
  dir.pop();

  for _ in 0..10 {
    let candidate = dir.join("luna").join("cli.exe");
    if candidate.exists() {
      return Ok(candidate);
    }
    if !dir.pop() {
      break;
    }
  }

  Err("Could not locate luna/cli.exe (expected somewhere above the app exe)".into())
}

fn app_data_dir() -> Result<PathBuf, String> {
  let appdata = std::env::var("APPDATA").map_err(|e| e.to_string())?;
  Ok(PathBuf::from(appdata).join("luna"))
}

fn server_runtime_dir(server_id: &str) -> Result<PathBuf, String> {
  Ok(app_data_dir()?.join("runtime").join(server_id))
}

#[derive(Serialize)]
struct ConsoleReadResult {
  lines: Vec<String>,
  offset: u64,
}


fn parse_cli_json_output(stdout: &str) -> Result<Value, String> {
  // CLI may emit newline-delimited JSON events; prefer the final result event.
  let mut parsed: Vec<Value> = Vec::new();
  for line in stdout.lines() {
    let trimmed = line.trim();
    if trimmed.is_empty() {
      continue;
    }
    if let Ok(v) = serde_json::from_str::<Value>(trimmed) {
      parsed.push(v);
    }
  }

  if parsed.is_empty() {
    return Err(format!("Failed to parse JSON from CLI output. Raw: {stdout}"));
  }

  for v in parsed.iter().rev() {
    if v.get("event").and_then(|e| e.as_str()) == Some("result") {
      return Ok(v.clone());
    }
  }

  Ok(parsed.pop().expect("parsed is non-empty"))
}

#[tauri::command]
fn run_cli_json(args: Vec<String>) -> Result<Value, String> {
  let cli = find_cli_exe()?;
  let data_dir = app_data_dir()?;

  std::fs::create_dir_all(&data_dir).map_err(|e| e.to_string())?;

  let output = Command::new(cli)
    .arg("--json")
    .arg("--data-dir")
    .arg(data_dir)
    .args(args)
    .output()
    .map_err(|e| e.to_string())?;

  if !output.status.success() {
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    return Err(format!("cli failed: {}", stderr));
  }

  let stdout = String::from_utf8_lossy(&output.stdout).to_string();
  parse_cli_json_output(&stdout)
}

#[tauri::command]
fn read_server_console(server_id: String, offset: Option<u64>, max_lines: Option<usize>) -> Result<ConsoleReadResult, String> {
  let path = server_runtime_dir(&server_id)?.join("console.ndjson");
  if !path.exists() {
    return Ok(ConsoleReadResult {
      lines: Vec::new(),
      offset: 0,
    });
  }

  let mut file = File::open(&path).map_err(|e| e.to_string())?;
  let file_len = file.metadata().map_err(|e| e.to_string())?.len();
  let mut start_offset = offset.unwrap_or(0);
  if start_offset > file_len {
    start_offset = 0;
  }
  file.seek(SeekFrom::Start(start_offset)).map_err(|e| e.to_string())?;

  let mut lines: Vec<String> = Vec::new();
  let reader = BufReader::new(file);
  for line in reader.lines() {
    let raw = line.map_err(|e| e.to_string())?;
    let parsed = serde_json::from_str::<Value>(&raw).unwrap_or(Value::Null);
    if let Some(text) = parsed.get("line").and_then(|v| v.as_str()) {
      lines.push(text.to_string());
    }
  }

  let limit = max_lines.unwrap_or(400);
  if lines.len() > limit {
    let drain_count = lines.len() - limit;
    lines.drain(0..drain_count);
  }

  Ok(ConsoleReadResult {
    lines,
    offset: file_len,
  })
}

#[tauri::command]
fn send_server_console_command(server_id: String, command: String) -> Result<(), String> {
  let trimmed = command.trim();
  if trimmed.is_empty() {
    return Ok(());
  }

  let runtime_dir = server_runtime_dir(&server_id)?;
  std::fs::create_dir_all(&runtime_dir).map_err(|e| e.to_string())?;

  let control_path = runtime_dir.join("control.ndjson");
  let mut file = OpenOptions::new()
    .create(true)
    .append(true)
    .open(control_path)
    .map_err(|e| e.to_string())?;

  let payload = serde_json::json!({
    "type": "stdin",
    "data": format!("{}\n", trimmed),
  });

  writeln!(file, "{}", payload).map_err(|e| e.to_string())?;
  file.flush().map_err(|e| e.to_string())?;
  Ok(())
}

fn main() {
  tauri::Builder::default()
    .invoke_handler(tauri::generate_handler![run_cli_json, read_server_console, send_server_console_command])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
