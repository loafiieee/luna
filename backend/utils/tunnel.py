from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Optional, Callable, Dict, Tuple, Any, List

import msgpack
import websockets


# Cross-platform data dir (luna identity storage)
try:
    from utils.platform import ensure_data_dir  # type: ignore
except Exception:  # pragma: no cover
    try:
        from backend.utils.platform import ensure_data_dir  # type: ignore
    except Exception:  # pragma: no cover
        ensure_data_dir = None  # type: ignore


def _pack(obj) -> bytes:
    return msgpack.packb(obj, use_bin_type=True)


def _unpack(b: bytes):
    return msgpack.unpackb(b, raw=False)


def _default_identity_path(app_name: str = "luna") -> str:
    """Return path to the local identity file.

    Uses an OS-appropriate per-user data directory when possible.
    """
    if ensure_data_dir is not None:
        d = ensure_data_dir(app_name)
        return str(Path(d) / "identity.json")

    # Fallback: keep previous behavior
    appdata = os.environ.get("APPDATA") or "."
    d = os.path.join(appdata, app_name)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "identity.json")


def load_or_create_identity(path: Optional[str] = None, app_name: str = "luna") -> Dict[str, str]:
    """Returns {"device_id": ..., "secret": ...}.

    Stored locally so the same machine gets the same allocation.
    """
    p = path or _default_identity_path(app_name)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    ident = {"device_id": secrets.token_hex(16), "secret": secrets.token_hex(32)}
    with open(p, "w", encoding="utf-8") as f:
        json.dump(ident, f)
    return ident


@dataclass
class TunnelInfo:
    subdomain: str
    domain_suffix: str
    public_tcp: Optional[int] = None
    public_udp: Optional[int] = None

    @property
    def public_tcp_address(self) -> Optional[str]:
        if self.public_tcp is None:
            return None
        return f"{self.subdomain}.{self.domain_suffix}:{self.public_tcp}"

    @property
    def public_udp_address(self) -> Optional[str]:
        if self.public_udp is None:
            return None
        return f"{self.subdomain}.{self.domain_suffix}:{self.public_udp}"


class _UdpPerPeerProtocol(asyncio.DatagramProtocol):
    """One local UDP socket per remote peer.

    This lets replies from the local Bedrock server be mapped back to the
    correct internet peer.
    """

    def __init__(self, peer: Tuple[str, int], send_to_edge: Callable[[Tuple[str, int], bytes], Any]):
        self.peer = peer
        self.send_to_edge = send_to_edge
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr) -> None:
        # addr will be ('127.0.0.1', local_server_port) because we connect() to it
        self.send_to_edge(self.peer, data)

    def error_received(self, exc: Exception) -> None:
        # Ignore noisy UDP errors
        pass


class TunnelClient:
    """Embedded tunnel client.

    Supports TCP (Java) and UDP (Bedrock) through a single WS connection.

    Works best when run inside an asyncio loop.
    For synchronous apps, use TunnelRunner below.
    """

    def __init__(
        self,
        edge_url: str,
        domain_suffix: str,
        identity_path: Optional[str] = None,
        app_name: str = "luna",
        on_status: Optional[Callable[[str], None]] = None,
        # UDP peer cleanup
        udp_peer_ttl_s: float = 120.0,
        udp_peer_reap_interval_s: float = 30.0,
        # Keepalive / reconnect tuning (important when running behind proxies)
        ws_ping_interval_s: float = 15.0,
        ws_ping_timeout_s: float = 15.0,
        app_keepalive_interval_s: float = 25.0,
        app_keepalive_timeout_s: float = 10.0,
        reconnect: bool = True,
        reconnect_initial_delay_s: float = 1.0,
        reconnect_max_delay_s: float = 20.0,
    ):
        self.edge_url = edge_url
        self.domain_suffix = domain_suffix
        self.identity_path = identity_path or _default_identity_path(app_name)
        self.app_name = app_name
        self.on_status = on_status

        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.stop_event = asyncio.Event()
        self.main_task: Optional[asyncio.Task] = None

        self.local_tcp_port: Optional[int] = None
        self.local_udp_port: Optional[int] = None

        self.server_id: Optional[str] = None
        self.sticky_address: bool = True
        self.info: Optional[TunnelInfo] = None
        self._open_future: Optional[asyncio.Future[TunnelInfo]] = None

        # TCP: conn_id -> (reader, writer)
        self._tcp_local: Dict[int, Tuple[asyncio.StreamReader, asyncio.StreamWriter]] = {}

        # UDP: peer -> (protocol/transport, last_seen_monotonic)
        self._udp_peers: Dict[Tuple[str, int], Tuple[_UdpPerPeerProtocol, asyncio.DatagramTransport, float]] = {}
        self._udp_peer_ttl_s = float(udp_peer_ttl_s)
        self._udp_peer_reap_interval_s = float(udp_peer_reap_interval_s)

        # WebSocket ping keepalive (low-level)
        self._ws_ping_interval_s = float(ws_ping_interval_s)
        self._ws_ping_timeout_s = float(ws_ping_timeout_s)

        # Active keepalive (forces reconnect on half-open sockets)
        self._app_keepalive_interval_s = float(app_keepalive_interval_s)
        self._app_keepalive_timeout_s = float(app_keepalive_timeout_s)
        self._keepalive_task: Optional[asyncio.Task] = None

        # Reconnect behavior
        self._reconnect_enabled = bool(reconnect)
        self._reconnect_initial_delay_s = float(reconnect_initial_delay_s)
        self._reconnect_max_delay_s = float(reconnect_max_delay_s)

        # Rx tracking (for detecting half-open connections)
        self._last_rx_monotonic: float = time.monotonic()

        # UDP reaper
        self._udp_reaper_task: Optional[asyncio.Task] = None

        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # WS send queue (prevents "task per packet")
        self._ws_send_q: Optional[asyncio.Queue[bytes]] = None
        self._ws_sender_task: Optional[asyncio.Task] = None

    def _status(self, msg: str) -> None:
        if self.on_status:
            self.on_status(msg)

    async def open(
        self,
        *,
        server_id: str,
        sticky_address: bool,
        tcp_local: Optional[int] = None,
        udp_local: Optional[int] = None,
    ) -> TunnelInfo:
        """Start tunnel for TCP and/or UDP.

        Returns when allocation arrives.
        Keeps running until close().
        """
        if self.main_task and not self.main_task.done():
            # already running; allow idempotent same config
            if (
                self.local_tcp_port == tcp_local
                and self.local_udp_port == udp_local
                and self.server_id == server_id
                and self.sticky_address == bool(sticky_address)
                and self.info
            ):
                return self.info
            raise RuntimeError("TunnelClient already running with different config; call close() first.")

        self.local_tcp_port = tcp_local
        self.local_udp_port = udp_local
        self.server_id = server_id
        self.sticky_address = bool(sticky_address)
        self.stop_event.clear()

        loop = asyncio.get_running_loop()
        self._loop = loop
        self._open_future = loop.create_future()
        self.main_task = asyncio.create_task(self._run())

        return await self._open_future

    async def close(self) -> None:
        self.stop_event.set()

        # Close WS (sender task will exit)
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass

        # Close TCP locals
        for cid in list(self._tcp_local.keys()):
            await self._tcp_close_local(cid)

        # Close UDP peer sockets
        for peer, (_proto, transport, _ts) in list(self._udp_peers.items()):
            try:
                transport.close()
            except Exception:
                pass
            self._udp_peers.pop(peer, None)

        # Stop keepalive
        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None

        # Stop reaper
        if self._udp_reaper_task:
            self._udp_reaper_task.cancel()
            self._udp_reaper_task = None

        # Stop ws sender
        if self._ws_sender_task:
            self._ws_sender_task.cancel()
            self._ws_sender_task = None
        self._ws_send_q = None

        if self.main_task:
            try:
                await asyncio.wait_for(self.main_task, timeout=5)
            except Exception:
                self.main_task.cancel()

        self.ws = None
        self.main_task = None

    # ---------------- TCP helpers ----------------

    async def _tcp_open_local(self, cid: int) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        assert self.local_tcp_port is not None
        r, w = await asyncio.open_connection("127.0.0.1", self.local_tcp_port)
        self._tcp_local[cid] = (r, w)
        return r, w

    async def _tcp_close_local(self, cid: int) -> None:
        pair = self._tcp_local.pop(cid, None)
        if not pair:
            return
        _, w = pair
        try:
            w.close()
            await w.wait_closed()
        except Exception:
            pass

    async def _tcp_pump_local_to_edge(self, cid: int, reader: asyncio.StreamReader) -> None:
        # ws can change on reconnect; capture the current one when starting the pump
        ws = self.ws
        if ws is None:
            return
        try:
            while not self.stop_event.is_set():
                data = await reader.read(65536)
                if not data:
                    break
                await ws.send(_pack({"t": "tcp_data", "id": cid, "d": data}))
        finally:
            try:
                await ws.send(_pack({"t": "tcp_close", "id": cid}))
            except Exception:
                pass

    # ---------------- WS send queue helpers ----------------

    async def _ws_sender(self) -> None:
        ws = self.ws
        q = self._ws_send_q
        if ws is None or q is None:
            return
        try:
            while not self.stop_event.is_set():
                raw = await q.get()
                try:
                    await ws.send(raw)
                except Exception:
                    break
        except asyncio.CancelledError:
            pass

    def _ws_send_nowait(self, obj: dict) -> None:
        if self.stop_event.is_set():
            return
        q = self._ws_send_q
        if not q:
            return
        try:
            q.put_nowait(_pack(obj))
        except Exception:
            pass

    # ---------------- Keepalive / liveness ----------------

    async def _keepalive(self) -> None:
        """Actively ping to keep the WS alive and detect half-open connections.

        websockets has built-in pings, but a dedicated task lets us:
          - fail fast on broken paths
          - trigger reconnects quickly without waiting for application traffic
        """
        try:
            while not self.stop_event.is_set():
                await asyncio.sleep(self._app_keepalive_interval_s)

                ws = self.ws
                if ws is None:
                    break

                try:
                    pong_waiter = ws.ping()
                    await asyncio.wait_for(pong_waiter, timeout=self._app_keepalive_timeout_s)
                except Exception:
                    # Closing the ws will unwind _run() and trigger reconnect logic.
                    try:
                        await ws.close()
                    except Exception:
                        pass
                    break
        except asyncio.CancelledError:
            pass

    # ---------------- UDP helpers ----------------

    async def _udp_reaper(self) -> None:
        try:
            while not self.stop_event.is_set():
                await asyncio.sleep(self._udp_peer_reap_interval_s)
                now = time.monotonic()
                for peer, (_proto, transport, last_seen) in list(self._udp_peers.items()):
                    if (now - last_seen) > self._udp_peer_ttl_s:
                        try:
                            transport.close()
                        except Exception:
                            pass
                        self._udp_peers.pop(peer, None)
        except asyncio.CancelledError:
            pass

    async def _udp_get_peer_socket(self, peer: Tuple[str, int]) -> Tuple[_UdpPerPeerProtocol, asyncio.DatagramTransport]:
        """Create (or reuse) a per-peer local UDP socket connected to 127.0.0.1:<local_udp_port>."""
        assert self._loop is not None
        assert self.local_udp_port is not None

        existing = self._udp_peers.get(peer)
        if existing:
            proto, transport, _ts = existing
            self._udp_peers[peer] = (proto, transport, time.monotonic())
            return proto, transport

        def send_to_edge(peer2: Tuple[str, int], data: bytes):
            # Called from protocol callbacks (same loop thread)
            self._ws_send_nowait({"t": "udp_data", "peer": [peer2[0], peer2[1]], "d": data})

        proto = _UdpPerPeerProtocol(peer=peer, send_to_edge=send_to_edge)

        transport, _ = await self._loop.create_datagram_endpoint(
            lambda: proto,
            local_addr=("127.0.0.1", 0),  # ephemeral local port
            remote_addr=("127.0.0.1", self.local_udp_port),  # connect to local Bedrock server
        )
        transport = transport  # type: ignore[assignment]
        self._udp_peers[peer] = (proto, transport, time.monotonic())
        return proto, transport  # type: ignore[return-value]

    async def _udp_forward_to_local(self, peer: Tuple[str, int], data: bytes) -> None:
        """Send incoming internet datagram to local Bedrock server via the per-peer socket."""
        _proto, transport = await self._udp_get_peer_socket(peer)
        transport.sendto(data)

    # ---------------- main loop ----------------

    async def _run(self) -> None:
        ident = load_or_create_identity(self.identity_path, self.app_name)
        device_id = ident["device_id"]
        secret = ident["secret"]

        assert self.server_id is not None

        want: List[dict] = []
        if self.local_tcp_port is not None:
            want.append({"proto": "tcp", "local": int(self.local_tcp_port)})
        if self.local_udp_port is not None:
            want.append({"proto": "udp", "local": int(self.local_udp_port)})

        # Exponential backoff for reconnects
        backoff = self._reconnect_initial_delay_s

        while not self.stop_event.is_set():
            self._status("connecting")
            try:
                async with websockets.connect(
                    self.edge_url,
                    max_size=None,
                    ping_interval=self._ws_ping_interval_s,
                    ping_timeout=self._ws_ping_timeout_s,
                    close_timeout=5,
                ) as ws:
                    self.ws = ws
                    self._last_rx_monotonic = time.monotonic()
                    self._status("connected")

                    # Start sender queue
                    self._ws_send_q = asyncio.Queue()
                    self._ws_sender_task = asyncio.create_task(self._ws_sender())

                    # Start UDP reaper if needed
                    if self.local_udp_port is not None:
                        self._udp_reaper_task = asyncio.create_task(self._udp_reaper())

                    # Start keepalive (detect half-open connections + force timely reconnects)
                    self._keepalive_task = asyncio.create_task(self._keepalive())

                    # (Re)open
                    await ws.send(
                        _pack(
                            {
                                "t": "hello",
                                "op": "open",
                                "device_id": device_id,
                                "secret": secret,
                                "server_id": self.server_id,
                                "sticky_address": bool(self.sticky_address),
                                "want": want,
                            }
                        )
                    )

                    first = _unpack(await ws.recv())
                    self._last_rx_monotonic = time.monotonic()

                    if first.get("t") == "err":
                        raise RuntimeError(str(first.get("msg") or "edge error"))

                    if first.get("t") != "open_result":
                        raise RuntimeError(f"Unexpected response: {first}")

                    sub = first["sub"]
                    ports = first.get("ports", {})
                    info = TunnelInfo(
                        subdomain=sub,
                        domain_suffix=self.domain_suffix,
                        public_tcp=int(ports["tcp"]) if "tcp" in ports else None,
                        public_udp=int(ports["udp"]) if "udp" in ports else None,
                    )
                    self.info = info

                    if self._open_future and not self._open_future.done():
                        self._open_future.set_result(info)

                    # Successful connection => reset backoff
                    backoff = self._reconnect_initial_delay_s

                    # Process messages
                    async for raw in ws:
                        if self.stop_event.is_set():
                            break

                        self._last_rx_monotonic = time.monotonic()
                        msg = _unpack(raw)
                        t = msg.get("t")

                        # ---- TCP ----
                        if t == "tcp_accept":
                            cid = int(msg["id"])
                            r, _w = await self._tcp_open_local(cid)
                            asyncio.create_task(self._tcp_pump_local_to_edge(cid, r))

                        elif t == "tcp_data":
                            cid = int(msg["id"])
                            data = msg["d"]
                            pair = self._tcp_local.get(cid)
                            if pair:
                                _r, w = pair
                                w.write(data)
                                await w.drain()

                        elif t == "tcp_close":
                            cid = int(msg["id"])
                            await self._tcp_close_local(cid)

                        # ---- UDP ----
                        elif t == "udp_data":
                            peer_list = msg["peer"]
                            peer = (str(peer_list[0]), int(peer_list[1]))
                            data = msg["d"]
                            await self._udp_forward_to_local(peer, data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Only surface open() failures once; after that we just reconnect.
                self._status(f"error: {e}")
                if self._open_future and not self._open_future.done():
                    self._open_future.set_exception(e)
            finally:
                # Stop keepalive
                if self._keepalive_task:
                    self._keepalive_task.cancel()
                    self._keepalive_task = None

                # Stop sender
                if self._ws_sender_task:
                    self._ws_sender_task.cancel()
                    self._ws_sender_task = None
                self._ws_send_q = None

                # Stop reaper
                if self._udp_reaper_task:
                    self._udp_reaper_task.cancel()
                    self._udp_reaper_task = None

                # Close WS reference
                self.ws = None

                # Tear down local state (TCP/UDP) so reconnect starts cleanly
                for cid in list(self._tcp_local.keys()):
                    try:
                        await self._tcp_close_local(cid)
                    except Exception:
                        pass

                for peer, (_proto, transport, _ts) in list(self._udp_peers.items()):
                    try:
                        transport.close()
                    except Exception:
                        pass
                    self._udp_peers.pop(peer, None)

            if self.stop_event.is_set():
                break

            if not self._reconnect_enabled:
                break

            # Reconnect after a short backoff
            self._status("reconnecting")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2.0, self._reconnect_max_delay_s)

        self._status("stopped")


# ---------------- Synchronous wrapper (so run_server can call it) ----------------


@dataclass
class TunnelRunner:
    """Synchronous-friendly runner. Use start() from normal (non-async) code."""

    edge_url: str = "wss://tunnel.loafiieee.com"
    domain_suffix: str = "mc.loafiieee.com"
    app_name: str = "luna"
    on_status: Optional[Callable[[str], None]] = None

    _loop: Optional[asyncio.AbstractEventLoop] = None
    _thread: Optional[threading.Thread] = None
    _client: Optional[TunnelClient] = None
    info: Optional[TunnelInfo] = None

    def _ensure_loop(self) -> None:
        if self._loop and self._thread and self._thread.is_alive():
            return

        self._loop = asyncio.new_event_loop()

        def run():
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def start(
        self,
        *,
        server_id: str,
        sticky_address: bool,
        tcp_local: Optional[int] = None,
        udp_local: Optional[int] = None,
        timeout: float = 10.0,
    ) -> TunnelInfo:
        self.stop()  # stop any existing tunnel first
        self._ensure_loop()

        assert self._loop is not None
        self._client = TunnelClient(
            edge_url=self.edge_url,
            domain_suffix=self.domain_suffix,
            app_name=self.app_name,
            on_status=self.on_status,
        )

        fut = asyncio.run_coroutine_threadsafe(
            self._client.open(server_id=server_id, sticky_address=sticky_address, tcp_local=tcp_local, udp_local=udp_local),
            self._loop,
        )
        self.info = fut.result(timeout=timeout)
        return self.info

    def sync_desired(self, *, desired_server_ids: List[str], timeout: float = 8.0) -> None:
        """One-shot: tell the edge which sticky server_ids still exist locally."""
        self._ensure_loop()
        assert self._loop is not None
        fut = asyncio.run_coroutine_threadsafe(
            _sync_desired_async(edge_url=self.edge_url, app_name=self.app_name, desired_server_ids=desired_server_ids),
            self._loop,
        )
        fut.result(timeout=timeout)

    def stop(self) -> None:
        loop = self._loop
        client = self._client
        thread = self._thread

        if client and loop:
            try:
                asyncio.run_coroutine_threadsafe(client.close(), loop).result(timeout=5)
            except Exception:
                pass

        self._client = None
        self.info = None

        if loop:
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass

        if thread and thread.is_alive():
            thread.join(timeout=2)

        if loop:
            try:
                loop.close()
            except Exception:
                pass

        self._loop = None
        self._thread = None


async def _sync_desired_async(*, edge_url: str, app_name: str, desired_server_ids: List[str]) -> None:
    ident = load_or_create_identity(None, app_name)
    device_id = ident["device_id"]
    secret = ident["secret"]

    async with websockets.connect(
        edge_url,
        max_size=None,
        ping_interval=15,
        ping_timeout=15,
        close_timeout=5,
    ) as ws:
        await ws.send(
            _pack({"t": "hello", "op": "sync", "device_id": device_id, "secret": secret, "desired": desired_server_ids})
        )
        resp = _unpack(await ws.recv())
        if resp.get("t") == "err":
            raise RuntimeError(str(resp.get("msg") or "edge error"))
        if resp.get("t") != "sync_ok":
            raise RuntimeError(f"Unexpected sync response: {resp}")
