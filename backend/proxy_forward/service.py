"""Service layer for TCP proxy forward control and LAN IP detection."""
from __future__ import annotations

import ipaddress
import platform
import socket
import subprocess
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import settings_manager


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_local_timestamp() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    ordered = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _is_valid_lan_ipv4(ip: str) -> bool:
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return parsed.version == 4 and not parsed.is_loopback


def detect_lan_ips() -> List[str]:
    """Return best-effort LAN IPv4 list, primary first."""
    candidates: List[str] = []

    # macOS-first path: common Wi-Fi / ethernet interfaces.
    if platform.system() == 'Darwin':
        for iface in ('en0', 'en1', 'en2'):
            try:
                proc = subprocess.run(
                    ['ipconfig', 'getifaddr', iface],
                    capture_output=True,
                    text=True,
                    timeout=1.2,
                    check=False,
                )
                ip = (proc.stdout or '').strip()
                if _is_valid_lan_ipv4(ip):
                    candidates.append(ip)
            except Exception:
                continue

    # Hostname-based fallback.
    try:
        hostname = socket.gethostname()
        infos = socket.getaddrinfo(hostname, None, family=socket.AF_INET)
        for info in infos:
            ip = info[4][0]
            if _is_valid_lan_ipv4(ip):
                candidates.append(ip)
    except OSError:
        pass

    return _dedupe_keep_order(candidates)


class ProxyForwardService:
    """Lifecycle and runtime state of a TCP forward server."""

    def __init__(self) -> None:
        config = settings_manager.load_settings()

        self._lock = threading.RLock()
        self._stop_event = threading.Event()

        self._running = False
        self._listen_host = config['listen_host']
        self._listen_port = config['listen_port']
        self._target_host = config['target_host']
        self._target_port = config['target_port']
        self._started_at: Optional[str] = None
        self._last_error: Optional[str] = None

        self._server_socket: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None

        self._active_connections = 0
        self._total_connections = 0
        self._history: List[Dict[str, Any]] = []
        self._history_seq = 0

    @staticmethod
    def _format_endpoint(host: str, port: int) -> str:
        return f'{host}:{port}'

    def _append_history(self, level: str, event: str, message: str) -> None:
        with self._lock:
            self._history_seq += 1
            self._history.append(
                {
                    'id': self._history_seq,
                    'timestamp': _now_local_timestamp(),
                    'level': level,
                    'event': event,
                    'message': message,
                }
            )
            if len(self._history) > 2000:
                self._history = self._history[-2000:]

    @staticmethod
    def _validate_port(port: int, field: str) -> int:
        try:
            v = int(port)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'{field} must be an integer') from exc
        if v < 1 or v > 65535:
            raise ValueError(f'{field} must be between 1 and 65535')
        return v

    @staticmethod
    def _validate_host(host: str, field: str) -> str:
        value = (host or '').strip()
        if not value:
            raise ValueError(f'{field} is required')
        return value

    def _set_last_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message
        self._append_history('error', 'error', message)

    def _resolve_runtime_config(
        self,
        listen_host: Optional[str],
        listen_port: Optional[int],
        target_host: Optional[str],
        target_port: Optional[int],
    ) -> Dict[str, Any]:
        configured = settings_manager.load_settings()
        resolved = {
            'listen_host': listen_host if listen_host is not None else configured.get('listen_host'),
            'listen_port': listen_port if listen_port is not None else configured.get('listen_port'),
            'target_host': target_host if target_host is not None else configured.get('target_host'),
            'target_port': target_port if target_port is not None else configured.get('target_port'),
        }
        return settings_manager.validate_and_normalize(resolved)

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            running = self._running
            listen_host = self._listen_host
            listen_port = self._listen_port
            target_host = self._target_host
            target_port = self._target_port
            started_at = self._started_at
            active_connections = self._active_connections
            total_connections = self._total_connections
            last_error = self._last_error
            history_count = len(self._history)

        lan_ips = detect_lan_ips()
        return {
            'running': running,
            'listen_host': listen_host,
            'listen_port': listen_port,
            'target_host': target_host,
            'target_port': target_port,
            'started_at': started_at,
            'active_connections': active_connections,
            'total_connections': total_connections,
            'lan_ip': lan_ips[0] if lan_ips else None,
            'lan_ips': lan_ips,
            'last_error': last_error,
            'history_count': history_count,
        }

    def get_history(self, limit: int = 200) -> List[Dict[str, Any]]:
        if limit < 1:
            limit = 1
        if limit > 2000:
            limit = 2000
        with self._lock:
            return list(self._history[-limit:])

    def clear_history(self) -> int:
        with self._lock:
            cleared = len(self._history)
            self._history = []
        return cleared

    def start(
        self,
        listen_host: Optional[str] = None,
        listen_port: Optional[int] = None,
        target_host: Optional[str] = None,
        target_port: Optional[int] = None,
    ) -> Dict[str, Any]:
        runtime = self._resolve_runtime_config(
            listen_host=listen_host,
            listen_port=listen_port,
            target_host=target_host,
            target_port=target_port,
        )

        resolved_listen_host = self._validate_host(runtime['listen_host'], 'listen_host')
        resolved_target_host = self._validate_host(runtime['target_host'], 'target_host')
        resolved_listen_port = self._validate_port(runtime['listen_port'], 'listen_port')
        resolved_target_port = self._validate_port(runtime['target_port'], 'target_port')

        with self._lock:
            if self._running:
                raise RuntimeError('Proxy is already running')

            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.bind((resolved_listen_host, resolved_listen_port))
                server.listen(20)
                server.settimeout(1.0)
            except OSError as exc:
                server.close()
                raise RuntimeError(
                    f'Failed to bind/listen on {resolved_listen_host}:{resolved_listen_port}: {exc}'
                ) from exc

            self._listen_host = resolved_listen_host
            self._listen_port = resolved_listen_port
            self._target_host = resolved_target_host
            self._target_port = resolved_target_port
            self._started_at = _utc_now_iso()
            self._last_error = None
            self._active_connections = 0
            self._total_connections = 0

            self._stop_event.clear()
            self._server_socket = server
            self._running = True

            self._accept_thread = threading.Thread(target=self._accept_loop, name='proxy-forward-accept', daemon=True)
            self._accept_thread.start()

        self._append_history(
            'info',
            'start',
            'Forwarding started: '
            f'{self._format_endpoint(resolved_listen_host, resolved_listen_port)} -> '
            f'{self._format_endpoint(resolved_target_host, resolved_target_port)}',
        )

        settings_manager.save_settings(
            {
                'listen_host': resolved_listen_host,
                'listen_port': resolved_listen_port,
                'target_host': resolved_target_host,
                'target_port': resolved_target_port,
            }
        )

        return self.get_status()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            was_running = self._running

        with self._lock:
            self._stop_event.set()
            server = self._server_socket
            accept_thread = self._accept_thread
            self._server_socket = None
            self._accept_thread = None
            self._running = False

        if server is not None:
            try:
                server.close()
            except OSError:
                pass

        if accept_thread is not None and accept_thread.is_alive():
            accept_thread.join(timeout=2.0)

        if was_running:
            self._append_history('info', 'stop', 'Forwarding stopped')

        return self.get_status()

    def _accept_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                server = self._server_socket
                target: Tuple[str, int] = (self._target_host, self._target_port)
            if server is None:
                break

            try:
                client_socket, client_addr = server.accept()
            except socket.timeout:
                continue
            except OSError as exc:
                if self._stop_event.is_set():
                    break
                self._set_last_error(f'Accept failed: {exc}')
                break

            with self._lock:
                self._active_connections += 1
                self._total_connections += 1

            self._append_history(
                'info',
                'connect',
                f'Client connected: {client_addr[0]}:{client_addr[1]} -> '
                f'{self._format_endpoint(target[0], target[1])}',
            )

            threading.Thread(
                target=self._handle_client,
                args=(client_socket, client_addr, target),
                name='proxy-forward-client',
                daemon=True,
            ).start()

        with self._lock:
            if not self._stop_event.is_set():
                self._running = False
            if self._server_socket is not None:
                try:
                    self._server_socket.close()
                except OSError:
                    pass
                self._server_socket = None

    def _handle_client(
        self,
        client_socket: socket.socket,
        client_addr: Tuple[str, int],
        target: Tuple[str, int],
    ) -> None:
        target_socket: Optional[socket.socket] = None
        connected = False
        try:
            target_socket = socket.create_connection(target, timeout=10)
            target_socket.settimeout(None)
            client_socket.settimeout(None)
            connected = True

            t1 = threading.Thread(
                target=self._forward_data,
                args=(client_socket, target_socket),
                daemon=True,
            )
            t2 = threading.Thread(
                target=self._forward_data,
                args=(target_socket, client_socket),
                daemon=True,
            )
            t1.start()
            t2.start()
            t1.join()
            t2.join()
        except OSError as exc:
            self._set_last_error(
                f'Connection {client_addr[0]}:{client_addr[1]} -> {target[0]}:{target[1]} failed: {exc}'
            )
        finally:
            try:
                client_socket.close()
            except OSError:
                pass
            if target_socket is not None:
                try:
                    target_socket.close()
                except OSError:
                    pass
            with self._lock:
                self._active_connections = max(0, self._active_connections - 1)

            if connected:
                self._append_history(
                    'info',
                    'disconnect',
                    f'Client disconnected: {client_addr[0]}:{client_addr[1]}',
                )

    @staticmethod
    def _forward_data(source: socket.socket, destination: socket.socket) -> None:
        try:
            while True:
                data = source.recv(4096)
                if not data:
                    break
                destination.sendall(data)
        except OSError:
            pass
        finally:
            try:
                destination.shutdown(socket.SHUT_WR)
            except OSError:
                pass


_service: Optional[ProxyForwardService] = None


def get_service() -> ProxyForwardService:
    global _service
    if _service is None:
        _service = ProxyForwardService()
    return _service
