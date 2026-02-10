from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Session:
    session_id: str
    proc: subprocess.Popen
    queue: queue.Queue[str] = field(default_factory=queue.Queue)
    pty_master_fd: Optional[int] = None


class ServerProcessManager:
    """Best-effort PTY-backed process manager for interactive server sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def start(self, cmd: list[str], *, cwd: Optional[str] = None) -> str:
        session_id = str(uuid.uuid4())

        if os.name != "nt":
            import pty

            master_fd, slave_fd = pty.openpty()
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                text=False,
                close_fds=True,
            )
            os.close(slave_fd)
            sess = Session(session_id=session_id, proc=proc, pty_master_fd=master_fd)
            self._start_pty_reader(sess)
        else:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            sess = Session(session_id=session_id, proc=proc)
            self._start_pipe_reader(sess)

        with self._lock:
            self._sessions[session_id] = sess

        return session_id

    def write(self, session_id: str, data: str) -> None:
        sess = self._get(session_id)
        if sess.pty_master_fd is not None:
            os.write(sess.pty_master_fd, data.encode("utf-8", errors="ignore"))
            return
        if sess.proc.stdin:
            sess.proc.stdin.write(data)
            sess.proc.stdin.flush()

    def resize(self, session_id: str, cols: int, rows: int) -> None:
        sess = self._get(session_id)
        if sess.pty_master_fd is None or os.name == "nt":
            return
        import fcntl
        import termios
        import struct

        fcntl.ioctl(sess.pty_master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def poll_output(self, session_id: str, max_lines: int = 200) -> list[str]:
        sess = self._get(session_id)
        out: list[str] = []
        for _ in range(max_lines):
            try:
                out.append(sess.queue.get_nowait())
            except queue.Empty:
                break
        return out

    def status(self, session_id: str) -> dict:
        sess = self._get(session_id)
        code = sess.proc.poll()
        return {"running": code is None, "exit_code": code}

    def stop(self, session_id: str) -> None:
        sess = self._get(session_id)
        if sess.proc.poll() is None:
            if os.name == "nt":
                sess.proc.terminate()
            else:
                sess.proc.send_signal(signal.SIGTERM)
            try:
                sess.proc.wait(timeout=8)
            except Exception:
                sess.proc.kill()
        if sess.pty_master_fd is not None:
            try:
                os.close(sess.pty_master_fd)
            except OSError:
                pass
        with self._lock:
            self._sessions.pop(session_id, None)

    def _start_pty_reader(self, sess: Session) -> None:
        def _reader() -> None:
            assert sess.pty_master_fd is not None
            while True:
                try:
                    data = os.read(sess.pty_master_fd, 4096)
                except OSError:
                    break
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                for line in text.splitlines():
                    sess.queue.put(line)
            code = sess.proc.poll()
            if code is not None:
                sess.queue.put(f"[session-exit] code={code}")

        threading.Thread(target=_reader, daemon=True).start()

    def _start_pipe_reader(self, sess: Session) -> None:
        def _reader() -> None:
            if not sess.proc.stdout:
                return
            for line in sess.proc.stdout:
                sess.queue.put(line.rstrip("\n"))
            code = sess.proc.poll()
            if code is not None:
                sess.queue.put(f"[session-exit] code={code}")

        threading.Thread(target=_reader, daemon=True).start()

    def _get(self, session_id: str) -> Session:
        with self._lock:
            sess = self._sessions.get(session_id)
        if not sess:
            raise ValueError(f"Unknown session_id: {session_id}")
        return sess


MANAGER = ServerProcessManager()
