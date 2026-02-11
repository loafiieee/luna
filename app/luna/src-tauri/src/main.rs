#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::Value;
use std::{path::PathBuf, process::Command};

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
  serde_json::from_str(&stdout).map_err(|e| format!("Failed to parse JSON: {e}\nRaw: {stdout}"))
}

fn main() {
  tauri::Builder::default()
    .invoke_handler(tauri::generate_handler![run_cli_json])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
