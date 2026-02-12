#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use once_cell::sync::Lazy;
use portable_pty::{native_pty_system, Child, CommandBuilder, MasterPty, PtySize};
use serde::Serialize;
use serde_json::Value;
use std::{
  collections::HashMap,
  fs::{File, OpenOptions},
  io::{BufRead, BufReader, Read, Seek, SeekFrom, Write},
  path::PathBuf,
  process::Command,
  sync::{Arc, Mutex},
  thread,
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


fn runtime_state_value(server_id: &str) -> Option<Value> {
  let path = server_runtime_dir(server_id).ok()?.join("state.json");
  let raw = std::fs::read_to_string(path).ok()?;
  serde_json::from_str::<Value>(&raw).ok()
}

fn runtime_indicates_running(server_id: &str) -> bool {
  let state = runtime_state_value(server_id);
  let Some(v) = state else { return false; };
  let text = v
    .get("state")
    .and_then(|x| x.as_str())
    .unwrap_or("")
    .to_ascii_lowercase();
  matches!(text.as_str(), "running" | "starting" | "online" | "up")
}

#[derive(Serialize)]
struct ConsoleReadResult {
  lines: Vec<String>,
  offset: u64,
}

#[derive(Serialize)]
struct PtyStartResult {
  pty_id: String,
}

#[derive(Serialize)]
struct PtyPollResult {
  chunks: Vec<String>,
  exited: bool,
}

#[derive(Serialize)]
struct PtyStatusResult {
  running: bool,
}

struct PtySession {
  child: Box<dyn Child + Send>,
  master: Box<dyn MasterPty + Send>,
  writer: Box<dyn Write + Send>,
  chunks: Arc<Mutex<Vec<String>>>,
}

static PTY_SESSIONS: Lazy<Mutex<HashMap<String, PtySession>>> = Lazy::new(|| Mutex::new(HashMap::new()));

fn load_server_from_state(server_id: &str) -> Result<(String, String, String, String), String> {
  let servers_path = app_data_dir()?.join("servers").join("servers.json");
  let raw = std::fs::read_to_string(&servers_path).map_err(|e| e.to_string())?;
  let parsed: Value = serde_json::from_str(&raw).map_err(|e| e.to_string())?;
  let list = parsed
    .as_array()
    .ok_or_else(|| "servers.json is not a JSON array".to_string())?;

  for item in list {
    if item.get("server_id").and_then(|v| v.as_str()) == Some(server_id) {
      let edition = item.get("edition").and_then(|v| v.as_str()).unwrap_or("java").to_string();
      let platform = item
        .get("platform")
        .and_then(|v| v.as_str())
        .ok_or_else(|| "server missing platform".to_string())?
        .to_string();
      let version = item
        .get("version")
        .and_then(|v| v.as_str())
        .ok_or_else(|| "server missing version".to_string())?
        .to_string();
      let name = item
        .get("name")
        .and_then(|v| v.as_str())
        .ok_or_else(|| "server missing name".to_string())?
        .to_string();
      return Ok((edition, platform, version, name));
    }
  }

  Err(format!("Server {} not found", server_id))
}

fn parse_cli_json_output(stdout: &str) -> Result<Value, String> {
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

fn extract_cli_error_message(stdout: &str, stderr: &str) -> String {
  for line in stdout.lines().rev() {
    let trimmed = line.trim();
    if trimmed.is_empty() {
      continue;
    }

    if let Ok(v) = serde_json::from_str::<Value>(trimmed) {
      if let Some(msg) = v.get("message").and_then(|m| m.as_str()) {
        if !msg.trim().is_empty() {
          return msg.to_string();
        }
      }
    }
  }

  let err = stderr.trim();
  if !err.is_empty() {
    return err.to_string();
  }

  let out = stdout.trim();
  if !out.is_empty() {
    return out.to_string();
  }

  "CLI command failed without output".to_string()
}

#[tauri::command]
async fn run_cli_json(args: Vec<String>) -> Result<Value, String> {
  tauri::async_runtime::spawn_blocking(move || {
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

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    if output.status.success() {
      return parse_cli_json_output(&stdout);
    }

    // Some CLI paths can emit a structured JSON result payload even when the
    // process exits non-zero. Preserve that structured response for the UI
    // instead of converting everything into a hard transport error.
    if let Ok(parsed) = parse_cli_json_output(&stdout) {
      if parsed.get("event").and_then(|e| e.as_str()) == Some("result") {
        return Ok(parsed);
      }
    }

    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    let message = extract_cli_error_message(&stdout, &stderr);
    Err(format!("cli failed: {message}"))
  })
  .await
  .map_err(|e| e.to_string())?
}

#[tauri::command]
fn pty_start(server_id: String, cols: Option<u16>, rows: Option<u16>) -> Result<PtyStartResult, String> {
  let pty_id = server_id.clone();
  let (edition, platform, version, name) = load_server_from_state(&server_id)?;
  let cli = find_cli_exe()?;
  let data_dir = app_data_dir()?;

  let mut sessions = PTY_SESSIONS.lock().map_err(|_| "pty lock poisoned".to_string())?;
  if let Some(existing) = sessions.get_mut(&pty_id) {
    let child_running = existing.child.try_wait().map_err(|e| e.to_string())?.is_none();
    if child_running && runtime_indicates_running(&server_id) {
      return Ok(PtyStartResult { pty_id });
    }

    if child_running {
      let _ = existing.writer.write_all(b"stop\n");
      let _ = existing.writer.flush();
      let _ = existing.child.kill();
    }
  }
  sessions.remove(&pty_id);

  let pty_system = native_pty_system();
  let pair = pty_system
    .openpty(PtySize {
      rows: rows.unwrap_or(24),
      cols: cols.unwrap_or(100),
      pixel_width: 0,
      pixel_height: 0,
    })
    .map_err(|e| e.to_string())?;

  let mut cmd = CommandBuilder::new(cli);
  cmd.arg("--json");
  cmd.arg("--data-dir");
  cmd.arg(data_dir.to_string_lossy().to_string());
  cmd.arg("run_server");
  cmd.arg(edition);
  cmd.arg(platform);
  cmd.arg(version);
  cmd.arg(name);

  let child = pair.slave.spawn_command(cmd).map_err(|e| e.to_string())?;
  let mut reader = pair.master.try_clone_reader().map_err(|e| e.to_string())?;
  let writer = pair.master.take_writer().map_err(|e| e.to_string())?;
  let chunks: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
  let chunks_for_thread = chunks.clone();

  thread::spawn(move || {
    let mut buf = [0u8; 8192];
    loop {
      match reader.read(&mut buf) {
        Ok(0) => break,
        Ok(n) => {
          let txt = String::from_utf8_lossy(&buf[..n]).to_string();
          if let Ok(mut c) = chunks_for_thread.lock() {
            c.push(txt);
            if c.len() > 800 {
              let drop_n = c.len() - 800;
              c.drain(0..drop_n);
            }
          }
        }
        Err(_) => break,
      }
    }
  });

  sessions.insert(
    pty_id.clone(),
    PtySession {
      child,
      master: pair.master,
      writer,
      chunks,
    },
  );

  Ok(PtyStartResult { pty_id })
}

#[tauri::command]
fn pty_write(pty_id: String, data: String) -> Result<(), String> {
  let mut sessions = PTY_SESSIONS.lock().map_err(|_| "pty lock poisoned".to_string())?;
  let session = sessions
    .get_mut(&pty_id)
    .ok_or_else(|| format!("No PTY session for {}", pty_id))?;
  session.writer.write_all(data.as_bytes()).map_err(|e| e.to_string())?;
  session.writer.flush().map_err(|e| e.to_string())?;
  Ok(())
}

#[tauri::command]
fn pty_poll(pty_id: String) -> Result<PtyPollResult, String> {
  let mut sessions = PTY_SESSIONS.lock().map_err(|_| "pty lock poisoned".to_string())?;
  let session = sessions
    .get_mut(&pty_id)
    .ok_or_else(|| format!("No PTY session for {}", pty_id))?;

  let exited = session.child.try_wait().map_err(|e| e.to_string())?.is_some();
  let mut out = Vec::new();
  if let Ok(mut c) = session.chunks.lock() {
    out = std::mem::take(&mut *c);
  }

  Ok(PtyPollResult { chunks: out, exited })
}

#[tauri::command]
fn pty_resize(pty_id: String, cols: u16, rows: u16) -> Result<(), String> {
  let mut sessions = PTY_SESSIONS.lock().map_err(|_| "pty lock poisoned".to_string())?;
  let session = sessions
    .get_mut(&pty_id)
    .ok_or_else(|| format!("No PTY session for {}", pty_id))?;
  session
    .master
    .resize(PtySize {
      rows,
      cols,
      pixel_width: 0,
      pixel_height: 0,
    })
    .map_err(|e| e.to_string())?;
  Ok(())
}

#[tauri::command]
fn pty_status(pty_id: String) -> Result<PtyStatusResult, String> {
  let mut sessions = PTY_SESSIONS.lock().map_err(|_| "pty lock poisoned".to_string())?;
  let session = match sessions.get_mut(&pty_id) {
    Some(s) => s,
    None => return Ok(PtyStatusResult { running: false }),
  };
  let running = session.child.try_wait().map_err(|e| e.to_string())?.is_none();
  Ok(PtyStatusResult { running })
}

#[tauri::command]
fn pty_stop(pty_id: String) -> Result<(), String> {
  let mut sessions = PTY_SESSIONS.lock().map_err(|_| "pty lock poisoned".to_string())?;
  let mut session = sessions
    .remove(&pty_id)
    .ok_or_else(|| format!("No PTY session for {}", pty_id))?;
  let _ = session.writer.write_all(b"stop\n");
  let _ = session.writer.flush();
  session.child.kill().map_err(|e| e.to_string())?;
  Ok(())
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
    "t": "stdin",
    "line": trimmed,
  });

  writeln!(file, "{}", payload).map_err(|e| e.to_string())?;
  file.flush().map_err(|e| e.to_string())?;
  Ok(())
}

fn main() {
  tauri::Builder::default()
    .invoke_handler(tauri::generate_handler![
      run_cli_json,
      pty_start,
      pty_write,
      pty_poll,
      pty_resize,
      pty_status,
      pty_stop,
      read_server_console,
      send_server_console_command
    ])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
