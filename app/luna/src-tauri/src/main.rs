#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use base64::Engine;
use once_cell::sync::Lazy;
use portable_pty::{native_pty_system, Child, CommandBuilder, MasterPty, PtySize};
use serde::Serialize;
use serde_json::Value;
use tauri::Emitter;
use std::{
    collections::HashMap,
    fs::{self, File, OpenOptions},
    io::{BufRead, BufReader, Read, Seek, SeekFrom, Write},
    path::PathBuf,
    process::{Child as ProcessChild, ChildStdin, ChildStdout, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread,
};
#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

fn configure_hidden_child_command(cmd: &mut Command) {
    #[cfg(target_os = "windows")]
    {
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
}

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

#[derive(Serialize, Clone)]
struct CliStreamEvent {
    stream_id: String,
    payload: Value,
}

#[derive(Serialize)]
struct ServerBansResult {
    banned_players: Vec<String>,
    banned_ips: Vec<String>,
}

#[derive(Serialize)]
struct ServerIconWriteResult {
    path: String,
}

#[derive(Serialize)]
struct ServerIconDataUrlResult {
    data_url: String,
    path: String,
}

struct PtySession {
    child: Box<dyn Child + Send>,
    master: Box<dyn MasterPty + Send>,
    writer: Box<dyn Write + Send>,
    chunks: Arc<Mutex<Vec<String>>>,
}

struct CliDaemon {
    child: ProcessChild,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_request_id: u64,
}

static PTY_SESSIONS: Lazy<Mutex<HashMap<String, PtySession>>> =
    Lazy::new(|| Mutex::new(HashMap::new()));
static CLI_DAEMON: Lazy<Mutex<Option<CliDaemon>>> = Lazy::new(|| Mutex::new(None));
static CLI_DAEMON_DISABLED: AtomicBool = AtomicBool::new(false);

fn load_server_from_state(server_id: &str) -> Result<(String, String, String, String), String> {
    let servers_path = app_data_dir()?.join("servers").join("servers.json");
    let raw = std::fs::read_to_string(&servers_path).map_err(|e| e.to_string())?;
    let parsed: Value = serde_json::from_str(&raw).map_err(|e| e.to_string())?;
    let list = parsed
        .as_array()
        .ok_or_else(|| "servers.json is not a JSON array".to_string())?;

    for item in list {
        if item.get("server_id").and_then(|v| v.as_str()) == Some(server_id) {
            let edition = item
                .get("edition")
                .and_then(|v| v.as_str())
                .unwrap_or("java")
                .to_string();
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
        return Err(format!(
            "Failed to parse JSON from CLI output. Raw: {stdout}"
        ));
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

fn emit_cli_stream_event(app: &tauri::AppHandle, stream_id: &str, payload: Value) {
    let event = CliStreamEvent {
        stream_id: stream_id.to_string(),
        payload,
    };
    let _ = app.emit("cli_stream_event", event);
}

fn spawn_cli_daemon(cli: &PathBuf, data_dir: &PathBuf) -> Result<CliDaemon, String> {
    let mut cmd = Command::new(cli);
    configure_hidden_child_command(&mut cmd);
    let mut child = cmd
        .arg("--json")
        .arg("--data-dir")
        .arg(data_dir)
        .arg("rpc_daemon")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| e.to_string())?;

    let stdin = child
        .stdin
        .take()
        .ok_or_else(|| "Failed to capture CLI daemon stdin".to_string())?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "Failed to capture CLI daemon stdout".to_string())?;

    Ok(CliDaemon {
        child,
        stdin,
        stdout: BufReader::new(stdout),
        next_request_id: 0,
    })
}

fn ensure_cli_daemon<'a>(
    slot: &'a mut Option<CliDaemon>,
    cli: &PathBuf,
    data_dir: &PathBuf,
) -> Result<&'a mut CliDaemon, String> {
    let should_restart = match slot.as_mut() {
        Some(existing) => existing
            .child
            .try_wait()
            .map_err(|e| e.to_string())?
            .is_some(),
        None => true,
    };

    if should_restart {
        *slot = Some(spawn_cli_daemon(cli, data_dir)?);
    }

    slot.as_mut()
        .ok_or_else(|| "CLI daemon was not available".to_string())
}

fn transact_cli_daemon_with_events<F>(
    daemon: &mut CliDaemon,
    args: Vec<String>,
    mut on_event: F,
) -> Result<Value, String>
where
    F: FnMut(Value),
{
    daemon.next_request_id = daemon.next_request_id.saturating_add(1);
    let request_id = daemon.next_request_id.to_string();
    let payload = serde_json::json!({
        "id": request_id,
        "args": args,
    });

    writeln!(daemon.stdin, "{}", payload).map_err(|e| e.to_string())?;
    daemon.stdin.flush().map_err(|e| e.to_string())?;

    loop {
        let mut line = String::new();
        let n = daemon.stdout.read_line(&mut line).map_err(|e| e.to_string())?;
        if n == 0 {
            return Err("CLI daemon terminated unexpectedly".to_string());
        }

        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        let parsed = match serde_json::from_str::<Value>(trimmed) {
            Ok(v) => v,
            Err(_) => continue,
        };

        if let Some(rid) = parsed.get("request_id").and_then(|v| v.as_str()) {
            if rid != request_id {
                continue;
            }
        }

        on_event(parsed.clone());

        let event = parsed.get("event").and_then(|v| v.as_str());
        if event == Some("result") {
            return Ok(parsed);
        }
        if event == Some("error") {
            let message = parsed
                .get("message")
                .and_then(|m| m.as_str())
                .filter(|m| !m.trim().is_empty())
                .unwrap_or(trimmed);
            return Err(format!("cli failed: {message}"));
        }
    }
}

fn run_cli_json_via_daemon(args: Vec<String>) -> Result<Value, String> {
    if CLI_DAEMON_DISABLED.load(Ordering::Relaxed) {
        return Err("cli daemon disabled".to_string());
    }

    let cli = find_cli_exe()?;
    let data_dir = app_data_dir()?;
    std::fs::create_dir_all(&data_dir).map_err(|e| e.to_string())?;

    let mut slot = CLI_DAEMON
        .lock()
        .map_err(|_| "cli daemon lock poisoned".to_string())?;

    let mut last_error: Option<String> = None;
    for _ in 0..2 {
        let daemon = ensure_cli_daemon(&mut *slot, &cli, &data_dir)?;
        match transact_cli_daemon_with_events(daemon, args.clone(), |_| {}) {
            Ok(v) => return Ok(v),
            Err(e) => {
                last_error = Some(e);
                *slot = None;
            }
        }
    }

    CLI_DAEMON_DISABLED.store(true, Ordering::Relaxed);
    Err(last_error.unwrap_or_else(|| "cli daemon request failed".to_string()))
}

fn run_cli_json_via_daemon_stream(
    app: tauri::AppHandle,
    args: Vec<String>,
    stream_id: String,
) -> Result<Value, String> {
    if CLI_DAEMON_DISABLED.load(Ordering::Relaxed) {
        return Err("cli daemon disabled".to_string());
    }

    let cli = find_cli_exe()?;
    let data_dir = app_data_dir()?;
    std::fs::create_dir_all(&data_dir).map_err(|e| e.to_string())?;

    let mut slot = CLI_DAEMON
        .lock()
        .map_err(|_| "cli daemon lock poisoned".to_string())?;

    let mut last_error: Option<String> = None;
    for _ in 0..2 {
        let daemon = ensure_cli_daemon(&mut *slot, &cli, &data_dir)?;
        let app_for_events = app.clone();
        let stream_for_events = stream_id.clone();
        match transact_cli_daemon_with_events(daemon, args.clone(), move |evt| {
            emit_cli_stream_event(&app_for_events, &stream_for_events, evt);
        }) {
            Ok(v) => return Ok(v),
            Err(e) => {
                last_error = Some(e);
                *slot = None;
            }
        }
    }

    CLI_DAEMON_DISABLED.store(true, Ordering::Relaxed);
    Err(last_error.unwrap_or_else(|| "cli daemon request failed".to_string()))
}

fn run_cli_json_one_shot(args: Vec<String>) -> Result<Value, String> {
    let cli = find_cli_exe()?;
    let data_dir = app_data_dir()?;

    std::fs::create_dir_all(&data_dir).map_err(|e| e.to_string())?;

    let mut cmd = Command::new(cli);
    configure_hidden_child_command(&mut cmd);
    let output = cmd
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
}

fn run_cli_json_one_shot_stream(
    app: tauri::AppHandle,
    args: Vec<String>,
    stream_id: String,
) -> Result<Value, String> {
    let cli = find_cli_exe()?;
    let data_dir = app_data_dir()?;

    std::fs::create_dir_all(&data_dir).map_err(|e| e.to_string())?;

    let mut cmd = Command::new(cli);
    configure_hidden_child_command(&mut cmd);
    let output = cmd
        .arg("--json")
        .arg("--data-dir")
        .arg(data_dir)
        .args(args)
        .output()
        .map_err(|e| e.to_string())?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    for line in stdout.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if let Ok(parsed) = serde_json::from_str::<Value>(trimmed) {
            emit_cli_stream_event(&app, &stream_id, parsed);
        }
    }

    if output.status.success() {
        return parse_cli_json_output(&stdout);
    }

    if let Ok(parsed) = parse_cli_json_output(&stdout) {
        if parsed.get("event").and_then(|e| e.as_str()) == Some("result") {
            return Ok(parsed);
        }
    }

    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    let message = extract_cli_error_message(&stdout, &stderr);
    let err_payload = serde_json::json!({
        "event": "error",
        "message": message,
    });
    emit_cli_stream_event(&app, &stream_id, err_payload);
    Err(format!("cli failed: {message}"))
}

#[tauri::command]
async fn run_cli_json(args: Vec<String>) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let daemon_attempt = run_cli_json_via_daemon(args.clone());
        match daemon_attempt {
            Ok(v) => Ok(v),
            Err(daemon_err) => match run_cli_json_one_shot(args) {
                Ok(v) => Ok(v),
                Err(fallback_err) => Err(format!(
                    "cli daemon failed: {daemon_err}; fallback failed: {fallback_err}"
                )),
            },
        }
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn run_cli_json_stream(
    app: tauri::AppHandle,
    args: Vec<String>,
    stream_id: String,
) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let daemon_attempt = run_cli_json_via_daemon_stream(app.clone(), args.clone(), stream_id.clone());
        match daemon_attempt {
            Ok(v) => Ok(v),
            Err(daemon_err) => match run_cli_json_one_shot_stream(app, args, stream_id) {
                Ok(v) => Ok(v),
                Err(fallback_err) => Err(format!(
                    "cli daemon failed: {daemon_err}; fallback failed: {fallback_err}"
                )),
            },
        }
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn pty_start(
    server_id: String,
    cols: Option<u16>,
    rows: Option<u16>,
) -> Result<PtyStartResult, String> {
    let pty_id = server_id.clone();
    let (edition, platform, version, name) = load_server_from_state(&server_id)?;
    let cli = find_cli_exe()?;
    let data_dir = app_data_dir()?;

    let mut sessions = PTY_SESSIONS
        .lock()
        .map_err(|_| "pty lock poisoned".to_string())?;
    if let Some(existing) = sessions.get_mut(&pty_id) {
        let child_running = existing
            .child
            .try_wait()
            .map_err(|e| e.to_string())?
            .is_none();
        if child_running {
            return Ok(PtyStartResult { pty_id });
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
    let mut sessions = PTY_SESSIONS
        .lock()
        .map_err(|_| "pty lock poisoned".to_string())?;
    let session = sessions
        .get_mut(&pty_id)
        .ok_or_else(|| format!("No PTY session for {}", pty_id))?;
    session
        .writer
        .write_all(data.as_bytes())
        .map_err(|e| e.to_string())?;
    session.writer.flush().map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn pty_poll(pty_id: String) -> Result<PtyPollResult, String> {
    let mut sessions = PTY_SESSIONS
        .lock()
        .map_err(|_| "pty lock poisoned".to_string())?;
    let session = sessions
        .get_mut(&pty_id)
        .ok_or_else(|| format!("No PTY session for {}", pty_id))?;

    let exited = session
        .child
        .try_wait()
        .map_err(|e| e.to_string())?
        .is_some();
    let mut out = Vec::new();
    if let Ok(mut c) = session.chunks.lock() {
        out = std::mem::take(&mut *c);
    }

    Ok(PtyPollResult {
        chunks: out,
        exited,
    })
}

#[tauri::command]
fn pty_resize(pty_id: String, cols: u16, rows: u16) -> Result<(), String> {
    let mut sessions = PTY_SESSIONS
        .lock()
        .map_err(|_| "pty lock poisoned".to_string())?;
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
    let mut sessions = PTY_SESSIONS
        .lock()
        .map_err(|_| "pty lock poisoned".to_string())?;
    let session = match sessions.get_mut(&pty_id) {
        Some(s) => s,
        None => return Ok(PtyStatusResult { running: false }),
    };
    let running = session
        .child
        .try_wait()
        .map_err(|e| e.to_string())?
        .is_none();
    Ok(PtyStatusResult { running })
}

#[tauri::command]
fn pty_stop(pty_id: String) -> Result<(), String> {
    let mut sessions = PTY_SESSIONS
        .lock()
        .map_err(|_| "pty lock poisoned".to_string())?;
    let mut session = sessions
        .remove(&pty_id)
        .ok_or_else(|| format!("No PTY session for {}", pty_id))?;
    if let Err(e) = session.child.kill() {
        let child_running = session
            .child
            .try_wait()
            .map_err(|err| err.to_string())?
            .is_none();
        if child_running {
            return Err(e.to_string());
        }
    }
    Ok(())
}

#[tauri::command]
fn read_server_console(
    server_id: String,
    offset: Option<u64>,
    max_lines: Option<usize>,
) -> Result<ConsoleReadResult, String> {
    let path = server_runtime_dir(&server_id)?.join("console.ndjson");
    if !path.exists() {
        return Ok(ConsoleReadResult {
            lines: Vec::new(),
            offset: 0,
        });
    }

    let mut file = File::open(&path).map_err(|e| e.to_string())?;
    let file_len = file.metadata().map_err(|e| e.to_string())?.len();

    // Fast-path: callers sometimes just want the current end offset without reading/parsing
    // the entire console file (which can be very large). max_lines=0 is that sentinel.
    if matches!(max_lines, Some(0)) {
        return Ok(ConsoleReadResult {
            lines: Vec::new(),
            offset: file_len,
        });
    }

    // If the caller's offset is beyond EOF (file truncated/rotated or app restarted),
    // do **not** restart from 0 (that could force parsing a huge file and crash the app).
    // Instead, tail from near the end.
    const TAIL_BYTES_ON_RESET: u64 = 512 * 1024; // 512 KiB
    let mut start_offset = offset.unwrap_or(0);
    if start_offset > file_len {
        start_offset = file_len.saturating_sub(TAIL_BYTES_ON_RESET);
    }
    file.seek(SeekFrom::Start(start_offset))
        .map_err(|e| e.to_string())?;

    let mut lines: Vec<String> = Vec::new();
    let mut reader = BufReader::new(file);
    let limit = max_lines.unwrap_or(400);
    // Additional safety: never parse unbounded content in one request.
    // If we hit this, we'll return the most recent lines within `limit`.
    const MAX_LINES_SCANNED: usize = 10_000;
    for (i, line) in reader.by_ref().lines().enumerate() {
        if i >= MAX_LINES_SCANNED {
            break;
        }
        let raw = line.map_err(|e| e.to_string())?;
        let parsed = serde_json::from_str::<Value>(&raw).unwrap_or(Value::Null);
        if let Some(text) = parsed.get("line").and_then(|v| v.as_str()) {
            lines.push(text.to_string());
        }
    }

    let consumed_to = reader.stream_position().map_err(|e| e.to_string())?;
    if lines.len() > limit {
        let drain_count = lines.len() - limit;
        lines.drain(0..drain_count);
    }

    Ok(ConsoleReadResult {
        lines,
        offset: consumed_to,
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

#[tauri::command]
fn read_server_bans(server_dir: String) -> Result<ServerBansResult, String> {
    fn read_entries(path: PathBuf, field: &str) -> Vec<String> {
        let raw = match std::fs::read_to_string(path) {
            Ok(s) => s,
            Err(_) => return Vec::new(),
        };
        let parsed = match serde_json::from_str::<Value>(&raw) {
            Ok(v) => v,
            Err(_) => return Vec::new(),
        };

        let mut entries: Vec<String> = parsed
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|item| item.get(field).and_then(|v| v.as_str()))
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect();

        entries.sort_by_key(|s| s.to_lowercase());
        entries.dedup_by(|a, b| a.eq_ignore_ascii_case(b));
        entries
    }

    let dir = PathBuf::from(server_dir);
    let banned_players = read_entries(dir.join("banned-players.json"), "name");
    let banned_ips = read_entries(dir.join("banned-ips.json"), "ip");

    Ok(ServerBansResult {
        banned_players,
        banned_ips,
    })
}

#[tauri::command]
fn host_os() -> String {
    std::env::consts::OS.to_string()
}

#[tauri::command]
fn write_server_icon_png(server_dir: String, png_bytes: Vec<u8>) -> Result<ServerIconWriteResult, String> {
    if server_dir.trim().is_empty() {
        return Err("server_dir is required".to_string());
    }
    if png_bytes.is_empty() {
        return Err("No image data received".to_string());
    }
    if png_bytes.len() > 8 * 1024 * 1024 {
        return Err("Icon image is too large".to_string());
    }

    const PNG_SIG: [u8; 8] = [137, 80, 78, 71, 13, 10, 26, 10];
    if png_bytes.len() < PNG_SIG.len() || png_bytes[..PNG_SIG.len()] != PNG_SIG {
        return Err("Expected PNG image data".to_string());
    }

    let dir = PathBuf::from(server_dir);
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;

    let out_path = dir.join("server-icon.png");
    fs::write(&out_path, png_bytes).map_err(|e| e.to_string())?;

    Ok(ServerIconWriteResult {
        path: out_path.to_string_lossy().to_string(),
    })
}

#[tauri::command]
fn read_server_icon_data_url(server_dir: String) -> Result<ServerIconDataUrlResult, String> {
    if server_dir.trim().is_empty() {
        return Err("server_dir is required".to_string());
    }

    let path = PathBuf::from(server_dir).join("server-icon.png");
    if !path.exists() {
        return Err("server-icon.png not found".to_string());
    }

    let bytes = fs::read(&path).map_err(|e| e.to_string())?;
    if bytes.is_empty() {
        return Err("server-icon.png is empty".to_string());
    }
    if bytes.len() > 8 * 1024 * 1024 {
        return Err("server-icon.png is too large".to_string());
    }

    const PNG_SIG: [u8; 8] = [137, 80, 78, 71, 13, 10, 26, 10];
    if bytes.len() < PNG_SIG.len() || bytes[..PNG_SIG.len()] != PNG_SIG {
        return Err("server-icon.png is not a PNG file".to_string());
    }

    let b64 = base64::engine::general_purpose::STANDARD.encode(bytes);
    Ok(ServerIconDataUrlResult {
        data_url: format!("data:image/png;base64,{}", b64),
        path: path.to_string_lossy().to_string(),
    })
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            run_cli_json,
            run_cli_json_stream,
            pty_start,
            pty_write,
            pty_poll,
            pty_resize,
            pty_status,
            pty_stop,
            read_server_console,
            send_server_console_command,
            read_server_bans,
            host_os,
            write_server_icon_png,
            read_server_icon_data_url
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
