# Luna Tauri Prep + Build Guide

This guide covers two parts:

1. **What you need before Tauri UI work** (backend readiness checklist).
2. **How to build the Tauri app** (Rust + frontend integration flow).

---

## 1) Backend readiness checklist (do this first)

### 1.1 Start the sidecar API (persistent process)

You now have `backend/sidecar.py`, which runs an HTTP API and keeps PTY sessions alive in memory for terminal interactions.

Run it from repo root:

```bash
python -m backend.sidecar
```

Expected startup log:

```json
{"event":"sidecar_started","host":"127.0.0.1","port":8765}
```

You can change host/port with:

- `LUNA_SIDECAR_HOST`
- `LUNA_SIDECAR_PORT`

---

### 1.2 Verify API health

```bash
curl http://127.0.0.1:8765/health
```

Expected:

```json
{"ok":true}
```

---

### 1.3 Verify server listing

```bash
curl http://127.0.0.1:8765/servers
```

Returns:

```json
{"servers":[ ... ]}
```

---

### 1.4 Verify `run_server` terminal command flow (important)

Start a managed server process (replace fields with a real server):

```bash
curl -X POST http://127.0.0.1:8765/servers/start \
  -H 'Content-Type: application/json' \
  -d '{"edition":"java","platform":"paper","version":"1.21.1","name":"myserver"}'
```

You’ll get a `session_id`. Use it to send console commands:

```bash
curl -X POST http://127.0.0.1:8765/servers/command \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"<SESSION_ID>","command":"say hello from Luna"}'
```

Poll logs:

```bash
curl "http://127.0.0.1:8765/pty/poll?session_id=<SESSION_ID>"
```

Stop process:

```bash
curl -X POST http://127.0.0.1:8765/servers/stop \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"<SESSION_ID>"}'
```

> Yes: this gives you stdin-like command entry for `run_server` sessions from UI.

---

### 1.5 Optional: generic PTY endpoints

- `POST /pty/start` with `{ "cmd": ["python", "cli.py", "help"] }`
- `POST /pty/write`
- `GET /pty/poll?session_id=...`
- `POST /pty/resize`
- `GET /pty/status?session_id=...`
- `POST /pty/stop`

These are useful if you want tabs/tools beyond server consoles.

---

## 2) API contract for the Tauri app

Base URL: `http://127.0.0.1:8765`

### Read endpoints

- `GET /health`
- `GET /servers`
- `GET /pty/poll?session_id=...`
- `GET /pty/status?session_id=...`

### Server lifecycle endpoints

- `POST /servers/install`
- `POST /servers/delete`
- `POST /servers/start`
- `POST /servers/command`
- `POST /servers/stop`

### Generic PTY endpoints

- `POST /pty/start`
- `POST /pty/write`
- `POST /pty/resize`
- `POST /pty/stop`

---

## 3) Build the Tauri app

## 3.1 Create project

```bash
npm create tauri-app@latest luna-ui
cd luna-ui
npm install
npm run tauri dev
```

Choose:
- Frontend: React + TypeScript (recommended)
- Bundler: Vite

---

## 3.2 Add terminal UI deps

```bash
npm i xterm xterm-addon-fit
```

---

## 3.3 Add app routes/pages

Suggested pages:

- `/` Dashboard (server cards)
- `/server/:id` Server detail

Detail tabs:
- details
- console
- backups
- tunnels
- settings
- files

---

## 3.4 Implement sidecar client in frontend

Create `src/lib/api.ts`:

- `getServers()`
- `startServer(payload)`
- `sendServerCommand(sessionId, command)`
- `pollPty(sessionId)`
- `stopServer(sessionId)`

Use fetch with typed helpers and clear error messages.

---

## 3.5 Dashboard UI (first milestone)

Implement card list matching your mock:

- server icon
- name
- online/offline status pill
- quick start/stop action
- floating `+` button to install/create server

Data source:
- poll `/servers` every 2–5s

---

## 3.6 Server detail + console (second milestone)

When opening a server page:

1. call `/servers/start` (or attach to existing session if you track one)
2. initialize `xterm`
3. start poll loop (`/pty/poll`) every 100–250ms
4. write returned lines into xterm
5. on terminal input, call `/servers/command`
6. on resize, call `/pty/resize`

If you add an input box under console, send same command endpoint on Enter.

---

## 3.7 Suggested UI components

- `ServerCard`
- `ServerStatusPill`
- `ConsolePanel` (xterm + command box)
- `PlayersPanel`
- `ServerTabs`
- `AppTitlebar` (custom, if using undecorated window)

---

## 3.8 Tauri-side process management (production)

For local dev, you can run sidecar manually.
For production app, wire Rust startup to spawn sidecar automatically.

Rust responsibilities:
- start sidecar on app launch
- wait for `/health`
- stop sidecar on app exit

Tip: keep sidecar local-only (`127.0.0.1`) and avoid exposing externally.

---

## 4) Recommended development order

1. Sidecar running + health/servers checks.
2. Dashboard with real server list.
3. Start/stop button wiring.
4. Console tab with PTY poll + command send.
5. Style pass to match your mock.
6. Additional tabs (backups/tunnels/settings/files).

---

## 5) Troubleshooting

### Sidecar starts but `/servers/start` fails

- Confirm server entry exists in `servers/servers.json`.
- Confirm `edition/platform/version/name` exactly matches.

### Commands don’t appear in server console

- Ensure command endpoint appends newline (already done in sidecar).
- Check `/pty/poll` output for process exit lines.

### Console freezes

- Reduce poll interval to 100ms and cap rendered backlog.
- Keep only last ~5k lines in memory for UI performance.

---

## 6) Security and stability notes

- Keep sidecar bound to localhost.
- Validate all UI input before API calls.
- Don’t pass arbitrary user shell commands to `/pty/start` in production UI unless sandboxed.
- Prefer server-specific endpoints (`/servers/start`, `/servers/command`, `/servers/stop`) for normal use.

---

## 7) Minimal “ready to start Tauri” definition

You are ready when all are true:

- `python -m backend.sidecar` runs.
- `/health` and `/servers` return valid JSON.
- You can start a server with `/servers/start`.
- You can send commands with `/servers/command`.
- You can read logs with `/pty/poll`.

Once those pass, start frontend implementation.
