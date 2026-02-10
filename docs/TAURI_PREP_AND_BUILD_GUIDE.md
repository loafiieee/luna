# Luna Tauri Prep + Build Guide (Direct `cli.py`, no sidecar)

This guide assumes you want Tauri to directly launch and control `python cli.py ...` processes and pipe stdin/stdout to `xterm`.

---

## 1) What to finish before frontend work

### 1.1 Decide process model (recommended)

Use **one long-lived child process per running server console tab**:

- Start command: `python cli.py run_server <edition> <platform> <version> <name> --json`
- Keep process handle in Rust state
- Stream stdout/stderr to frontend
- Write user terminal input to child stdin
- Stop by sending `stop\n` to stdin first, then force-kill if needed

Why this works:
- `run_server` is lifecycle/blocking by design and continues until exit.
- Tauri can treat it as a persistent console process.

---

### 1.2 Keep using `servers.json` state helpers

Your backend already has atomic+locked state management (`STATE`) and migrated server metadata flows.
Keep using that path for all install/delete/read operations.

---

### 1.3 Use JSON output mode for machine-readable logs

Always pass `--json` when launching `cli.py` from Tauri so UI can parse structured events.

Example:

```bash
python cli.py run_server java paper 1.21.1 myserver --json
```

---

### 1.4 Do **not** use CLI PTY subcommands from separate short-lived processes

`pty_start`/`pty_write`/etc. keep session state in-process, so they are not useful if each call starts a new Python process.
For direct Tauri control, just manage the `run_server` child process in Rust.

---

## 2) Tauri architecture (direct CLI)

## 2.1 Rust responsibilities

- Maintain a global process map:
  - key: `server_key` (`edition:platform:version:name`)
  - value: process handle + stdin writer + output task channel
- Expose commands to frontend:
  - `list_servers`
  - `start_server`
  - `send_server_command`
  - `stop_server`
  - `server_status`
- Emit console output events to frontend with `app_handle.emit_all(...)`

---

## 2.2 Frontend responsibilities (React)

- Dashboard page:
  - list servers
  - start/stop buttons
- Server detail page:
  - xterm console
  - command input box
  - players panel (later)
- Subscribe to Tauri event stream for console lines
- Send user keystrokes/commands to Rust command

---

## 3) Build steps

## 3.1 Create app

```bash
npm create tauri-app@latest luna-ui
cd luna-ui
npm install
npm run tauri dev
```

Choose React + TypeScript + Vite.

---

## 3.2 Install console deps

```bash
npm i xterm xterm-addon-fit
```

---

## 3.3 Add Rust state for server processes

In `src-tauri/src/main.rs` (or module files), create an app state like:

- `HashMap<String, ManagedServerProc>`
- each entry stores:
  - `Child`
  - `stdin` handle
  - running flag / exit code

Guard with `Arc<Mutex<...>>`.

---

## 3.4 Implement Rust commands

### `list_servers`
- Run `python cli.py list_servers --json`
- Parse output and return typed list

### `start_server(edition, platform, version, name)`
- Spawn child:
  - `python cli.py run_server <...> --json`
- Capture stdout/stderr
- Start async reader that emits lines to frontend:
  - event name: `server-log:<server_key>`

### `send_server_command(server_key, command)`
- Lookup child stdin
- write `command + "\n"`
- flush

### `stop_server(server_key)`
- send `stop\n`
- wait grace period (e.g., 8–15s)
- force kill if still running

### `server_status(server_key)`
- return running/exit code

---

## 3.5 Frontend: dashboard page

Match your mock:

- top app bar (Luna)
- server cards with icon, name, status
- quick play/stop controls
- floating `+` button

Refresh list every 2–5 seconds.

---

## 3.6 Frontend: server detail + console page

Layout:

- left nav tabs: details/console/backups/tunnels/settings/files
- center: console panel (`xterm`)
- bottom input: command entry + send button
- right panel: players/search list

Data flow:

1. on page open, call `start_server(...)` if not running
2. subscribe to `server-log:<server_key>`
3. append output lines to `xterm`
4. on Enter in input box, call `send_server_command(...)`
5. on stop button, call `stop_server(...)`

---

## 4) Parsing `--json` CLI logs/events

Your CLI emits structured logs/events in JSON mode. For frontend:

- parse line-by-line JSON
- route by `event` + `level`
- display `log` and `error` lines in console
- optional: show toast notifications for install/delete/run lifecycle events

If a line is not valid JSON, render raw text fallback.

---

## 5) Suggested minimal API surface inside Tauri

Expose these commands to frontend first:

- `list_servers()`
- `start_server(edition, platform, version, name)`
- `send_server_command(server_key, command)`
- `stop_server(server_key)`
- `server_status(server_key)`

Add later:

- `install_server(...)`
- `delete_server(...)`
- `modrinth_search(...)`
- `modrinth_download(...)`

---

## 6) Stability checklist

Before full UI polish, verify:

1. Start server from dashboard
2. Console log stream appears in detail page
3. Sending `say hello` works
4. Sending `stop` cleanly shuts down
5. Reopening detail page reattaches to existing process
6. App close cleans up running child processes safely

---

## 7) Troubleshooting

### No output in console
- Ensure `--json` is passed
- Ensure Rust reader task is attached to child stdout
- Ensure event subscription name matches emitted name

### Commands not executing
- Ensure stdin writes append newline
- Ensure stdin is flushed
- Ensure process still running

### Process exits immediately
- Check server key arguments (`edition/platform/version/name`)
- Check server exists in `servers/servers.json`
- Display stderr lines in xterm for diagnosis

---

## 8) Security notes

- Don’t expose arbitrary command execution from renderer
- Validate all command inputs in Rust
- Restrict spawn arguments to known CLI commands
- Keep principle: renderer requests, Rust validates/executes

---

## 9) “Ready to build UI” definition

You are ready when:

- Tauri can spawn `python cli.py run_server ... --json`
- stdout/stderr stream reaches xterm
- stdin command send works (`say`, `stop`)
- process map survives navigation changes

At that point, build out the full SquidServers-like UI.
