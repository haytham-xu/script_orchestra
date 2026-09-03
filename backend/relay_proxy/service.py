"""Relay proxy data-plane service.

This module provides a LAN-facing HTTP/CONNECT and SOCKS5 relay.
It forwards traffic without inspecting or modifying tunneled payload bytes.
"""
from __future__ import annotations

import ipaddress
import platform
import socket
import subprocess
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from . import settings_manager


def _local_timestamp() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def detect_lan_ips() -> List[str]:
    """Return best-effort LAN IPv4 addresses."""
    candidates: List[str] = []

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
                value = (proc.stdout or '').strip()
                if value:
                    parsed = ipaddress.ip_address(value)
                    if parsed.version == 4 and not parsed.is_loopback:
                        candidates.append(value)
            except Exception:
                continue

    try:
        hostname = socket.gethostname()
        infos = socket.getaddrinfo(hostname, None, family=socket.AF_INET)
        for info in infos:
            value = info[4][0]
            try:
                parsed = ipaddress.ip_address(value)
            except ValueError:
                continue
            if parsed.version == 4 and not parsed.is_loopback:
                candidates.append(value)
    except OSError:
        pass

    return _dedupe_keep_order(candidates)


class RelayProxyService:
    """Runtime service for relay proxy listeners and connection tunneling."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._running = False
        self._stop_event = threading.Event()

        self._listener_sockets: Dict[str, socket.socket] = {}
        self._listener_threads: Dict[str, threading.Thread] = {}

        self._active_connections = 0
        self._total_connections = 0
        self._last_error: Optional[str] = None
        self._started_at: Optional[str] = None

        self._history: List[Dict[str, Any]] = []
        self._history_seq = 0
        self._history_limit = 2000

        self._settings = settings_manager.load_settings()

    def _append_history(self, level: str, event: str, message: str) -> None:
        with self._lock:
            self._history_seq += 1
            self._history.append(
                {
                    'id': self._history_seq,
                    'timestamp': _local_timestamp(),
                    'level': level,
                    'event': event,
                    'message': message,
                }
            )
            if len(self._history) > self._history_limit:
                self._history = self._history[-self._history_limit:]

    def _set_last_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message
        self._append_history('error', 'error', message)

    def _format_endpoint(self, host: str, port: int) -> str:
        return f'{host}:{port}'

    def _load_runtime_settings(self) -> Dict[str, Any]:
        settings = settings_manager.load_settings()
        with self._lock:
            self._settings = settings
            self._history_limit = settings['limits']['history_limit']
        return settings

    def get_settings(self) -> Dict[str, Any]:
        return self._load_runtime_settings()

    def update_settings(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        current = settings_manager.load_settings()
        updated = settings_manager.validate_and_normalize(patch, current)
        saved = settings_manager.save_settings(updated)
        with self._lock:
            self._settings = saved
            self._history_limit = saved['limits']['history_limit']
        self._append_history('info', 'settings', 'Settings updated')
        return saved

    def get_history(self, limit: int = 200) -> List[Dict[str, Any]]:
        limit_value = max(1, min(2000, int(limit)))
        with self._lock:
            return list(self._history[-limit_value:])

    def clear_history(self) -> int:
        with self._lock:
            cleared = len(self._history)
            self._history = []
        return cleared

    def _build_probe_check(
        self,
        name: str,
        ok: bool,
        detail: str,
        skipped: bool = False,
    ) -> Dict[str, Any]:
        return {
            'name': name,
            'ok': bool(ok),
            'skipped': bool(skipped),
            'detail': detail,
        }

    def _probe_bind(
        self,
        listener_name: str,
        host: str,
        port: int,
        runtime_listeners: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        runtime_listener = runtime_listeners.get(listener_name)
        if runtime_listener is not None:
            runtime_host = runtime_listener.get('bind_host')
            runtime_port = runtime_listener.get('bind_port')
            if runtime_host == host and runtime_port == port:
                return self._build_probe_check(
                    f'listener.{listener_name}.bind',
                    True,
                    f'Listener is already running on {host}:{port}',
                )

        probe_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe_socket.bind((host, port))
        except OSError as exc:
            return self._build_probe_check(
                f'listener.{listener_name}.bind',
                False,
                f'Bind failed on {host}:{port}: {exc}',
            )
        finally:
            try:
                probe_socket.close()
            except OSError:
                pass

        return self._build_probe_check(
            f'listener.{listener_name}.bind',
            True,
            f'Bind check passed on {host}:{port}',
        )

    def _probe_upstream(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        if settings['mode'] != 'upstream_proxy':
            return self._build_probe_check(
                'upstream.connect',
                True,
                'Skipped because mode is direct',
                skipped=True,
            )

        upstream = settings['upstream']
        host = upstream.get('host')
        port = upstream.get('port')
        protocol = upstream.get('protocol')

        if not host or port is None:
            return self._build_probe_check(
                'upstream.connect',
                False,
                'upstream.host and upstream.port are required in upstream_proxy mode',
            )

        timeout = float(settings['limits']['connect_timeout_seconds'])
        upstream_socket: Optional[socket.socket] = None
        try:
            upstream_socket = socket.create_connection((host, port), timeout=timeout)
            upstream_socket.settimeout(timeout)

            if protocol == 'socks5':
                upstream_socket.sendall(b'\x05\x01\x00')
                response = self._recv_exact(upstream_socket, 2)
                if response[0] != 5:
                    raise RuntimeError('Invalid SOCKS5 version in upstream greeting reply')
                if response[1] == 0xFF:
                    raise RuntimeError('Upstream SOCKS5 rejected no-auth method')

            return self._build_probe_check(
                'upstream.connect',
                True,
                f'Upstream reachable via {protocol}: {host}:{port}',
            )
        except Exception as exc:  # noqa: BLE001
            return self._build_probe_check(
                'upstream.connect',
                False,
                f'Upstream probe failed for {host}:{port}: {exc}',
            )
        finally:
            if upstream_socket is not None:
                try:
                    upstream_socket.close()
                except OSError:
                    pass

    def run_diagnostics_probe(self, patch: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        base_settings = settings_manager.load_settings()
        effective = settings_manager.validate_and_normalize(patch or {}, base_settings)

        checks: List[Dict[str, Any]] = []

        listeners = effective['listeners']
        enabled_listener_names = [
            name for name in ('http', 'socks5') if listeners[name]['enabled']
        ]

        if not enabled_listener_names:
            checks.append(
                self._build_probe_check(
                    'listeners.enabled',
                    False,
                    'At least one listener must be enabled',
                )
            )
        else:
            checks.append(
                self._build_probe_check(
                    'listeners.enabled',
                    True,
                    f'Enabled listeners: {", ".join(enabled_listener_names)}',
                )
            )

        runtime_listeners = self.get_status().get('listeners_runtime', {})

        for listener_name in ('http', 'socks5'):
            listener = listeners[listener_name]
            if not listener['enabled']:
                checks.append(
                    self._build_probe_check(
                        f'listener.{listener_name}.bind',
                        True,
                        'Skipped because listener is disabled',
                        skipped=True,
                    )
                )
                continue

            bind_host = listener['bind_host']
            bind_port = listener['bind_port']
            if bind_port is None:
                checks.append(
                    self._build_probe_check(
                        f'listener.{listener_name}.bind',
                        False,
                        'bind_port is required when listener is enabled',
                    )
                )
                continue

            checks.append(
                self._probe_bind(
                    listener_name=listener_name,
                    host=bind_host,
                    port=bind_port,
                    runtime_listeners=runtime_listeners,
                )
            )

        checks.append(self._probe_upstream(effective))

        ok = all(check['ok'] for check in checks)
        result = {
            'ok': ok,
            'timestamp': _local_timestamp(),
            'mode': effective['mode'],
            'checks': checks,
        }

        self._append_history(
            'info' if ok else 'warning',
            'probe',
            f'Diagnostics probe completed (ok={ok})',
        )
        return result

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            listeners_runtime = {
                key: {
                    'enabled': True,
                    'bind_host': value.getsockname()[0],
                    'bind_port': value.getsockname()[1],
                }
                for key, value in self._listener_sockets.items()
            }
            status = {
                'running': self._running,
                'mode': self._settings.get('mode'),
                'listeners_runtime': listeners_runtime,
                'active_connections': self._active_connections,
                'total_connections': self._total_connections,
                'started_at': self._started_at,
                'last_error': self._last_error,
                'history_count': len(self._history),
            }

        lan_ips = detect_lan_ips()
        status['lan_ip'] = lan_ips[0] if lan_ips else None
        status['lan_ips'] = lan_ips
        return status

    def _validate_startable(self, settings: Dict[str, Any]) -> None:
        listeners = settings['listeners']
        if not listeners['http']['enabled'] and not listeners['socks5']['enabled']:
            raise RuntimeError('At least one listener must be enabled')

        if settings['mode'] == 'upstream_proxy':
            upstream = settings['upstream']
            if not upstream.get('host') or upstream.get('port') is None:
                raise RuntimeError('upstream.host and upstream.port are required in upstream_proxy mode')

    def start(self) -> Dict[str, Any]:
        settings = self._load_runtime_settings()
        self._validate_startable(settings)

        with self._lock:
            if self._running:
                raise RuntimeError('Relay proxy is already running')

            self._stop_event.clear()

        prepared: Dict[str, socket.socket] = {}
        try:
            for listener_name in ('http', 'socks5'):
                listener_settings = settings['listeners'][listener_name]
                if not listener_settings['enabled']:
                    continue
                bind_host = listener_settings['bind_host']
                bind_port = listener_settings['bind_port']
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((bind_host, bind_port))
                sock.listen(settings['limits']['max_connections'])
                sock.settimeout(1.0)
                prepared[listener_name] = sock
        except OSError as exc:
            for sock in prepared.values():
                try:
                    sock.close()
                except OSError:
                    pass
            raise RuntimeError(f'Failed to bind listener: {exc}') from exc

        with self._lock:
            self._listener_sockets = prepared
            self._listener_threads = {}
            self._active_connections = 0
            self._total_connections = 0
            self._last_error = None
            self._started_at = _local_timestamp()
            self._running = True

            for listener_name, sock in self._listener_sockets.items():
                thread = threading.Thread(
                    target=self._accept_loop,
                    args=(listener_name, sock),
                    name=f'relay-proxy-{listener_name}-accept',
                    daemon=True,
                )
                self._listener_threads[listener_name] = thread
                thread.start()

        self._append_history('info', 'start', 'Relay proxy started')
        return self.get_status()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            was_running = self._running
            self._running = False
            self._stop_event.set()
            sockets = list(self._listener_sockets.values())
            threads = list(self._listener_threads.values())
            self._listener_sockets = {}
            self._listener_threads = {}

        for sock in sockets:
            try:
                sock.close()
            except OSError:
                pass

        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=2.0)

        if was_running:
            self._append_history('info', 'stop', 'Relay proxy stopped')

        return self.get_status()

    def _client_allowed(self, client_ip: str) -> bool:
        cidrs = self._settings.get('access', {}).get('allowed_client_cidrs', [])
        if not cidrs:
            return True

        try:
            client_address = ipaddress.ip_address(client_ip)
        except ValueError:
            return False

        for cidr in cidrs:
            try:
                network = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                continue
            if client_address in network:
                return True
        return False

    def _accept_loop(self, listener_name: str, listener_socket: socket.socket) -> None:
        while not self._stop_event.is_set():
            try:
                client_socket, client_addr = listener_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            client_ip = str(client_addr[0])
            if not self._client_allowed(client_ip):
                self._append_history('warning', 'deny', f'Client denied by CIDR policy: {client_ip}')
                try:
                    client_socket.close()
                except OSError:
                    pass
                continue

            with self._lock:
                if self._active_connections >= self._settings['limits']['max_connections']:
                    self._append_history('warning', 'limit', 'Connection rejected: max_connections reached')
                    try:
                        client_socket.close()
                    except OSError:
                        pass
                    continue

                self._active_connections += 1
                self._total_connections += 1

            thread = threading.Thread(
                target=self._handle_client,
                args=(listener_name, client_socket, client_addr),
                name=f'relay-proxy-{listener_name}-client',
                daemon=True,
            )
            thread.start()

    def _handle_client(
        self,
        listener_name: str,
        client_socket: socket.socket,
        client_addr: Tuple[str, int],
    ) -> None:
        connection_started = time.time()
        bytes_up = 0
        bytes_down = 0

        self._append_history(
            'info',
            'connect',
            f'Client connected ({listener_name}): {client_addr[0]}:{client_addr[1]}',
        )

        try:
            client_socket.settimeout(float(self._settings['limits']['idle_timeout_seconds']))
            if listener_name == 'http':
                up, down = self._handle_http_listener(client_socket)
            elif listener_name == 'socks5':
                up, down = self._handle_socks5_listener(client_socket)
            else:
                raise RuntimeError(f'Unsupported listener: {listener_name}')
            bytes_up += up
            bytes_down += down
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
        finally:
            try:
                client_socket.close()
            except OSError:
                pass

            duration_ms = int((time.time() - connection_started) * 1000)
            self._append_history(
                'info',
                'disconnect',
                f'Client disconnected ({listener_name}): {client_addr[0]}:{client_addr[1]}, '
                f'duration_ms={duration_ms}, bytes_up={bytes_up}, bytes_down={bytes_down}',
            )

            with self._lock:
                self._active_connections = max(0, self._active_connections - 1)

    def _recv_exact(self, sock: socket.socket, length: int) -> bytes:
        chunks = []
        remaining = length
        while remaining > 0:
            data = sock.recv(remaining)
            if not data:
                raise RuntimeError('Socket closed while reading expected bytes')
            chunks.append(data)
            remaining -= len(data)
        return b''.join(chunks)

    def _recv_until(self, sock: socket.socket, marker: bytes, max_bytes: int) -> bytes:
        buffer = bytearray()
        while marker not in buffer:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buffer.extend(chunk)
            if len(buffer) > max_bytes:
                raise RuntimeError('Request header too large')
        return bytes(buffer)

    def _parse_http_request_line(self, initial: bytes) -> Tuple[str, str, str]:
        first_line = initial.split(b'\r\n', 1)[0].decode('latin1', errors='replace').strip()
        parts = first_line.split(' ', 2)
        if len(parts) != 3:
            raise RuntimeError('Invalid HTTP request line')
        return parts[0].upper(), parts[1], parts[2]

    def _parse_connect_target(self, authority: str) -> Tuple[str, int]:
        target = authority.strip()
        if not target or ':' not in target:
            raise RuntimeError('CONNECT target must include host:port')

        host, port_text = target.rsplit(':', 1)
        host = host.strip().strip('[]')
        if not host:
            raise RuntimeError('CONNECT target host is empty')
        try:
            port = int(port_text)
        except ValueError as exc:
            raise RuntimeError('CONNECT target port is invalid') from exc
        if port < 1 or port > 65535:
            raise RuntimeError('CONNECT target port out of range')
        return host, port

    def _parse_http_status(self, response_headers: bytes) -> int:
        line = response_headers.split(b'\r\n', 1)[0].decode('latin1', errors='replace')
        parts = line.split(' ', 2)
        if len(parts) < 2:
            raise RuntimeError('Invalid upstream HTTP response')
        try:
            return int(parts[1])
        except ValueError as exc:
            raise RuntimeError('Invalid upstream HTTP status code') from exc

    def _open_tcp(self, host: str, port: int) -> socket.socket:
        timeout = float(self._settings['limits']['connect_timeout_seconds'])
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
        except OSError as exc:
            raise RuntimeError(f'Failed to connect {self._format_endpoint(host, port)}: {exc}') from exc
        sock.settimeout(float(self._settings['limits']['idle_timeout_seconds']))
        return sock

    def _connect_via_upstream_http(self, target_host: str, target_port: int) -> socket.socket:
        upstream = self._settings['upstream']
        upstream_sock = self._open_tcp(upstream['host'], upstream['port'])
        request = (
            f'CONNECT {target_host}:{target_port} HTTP/1.1\r\n'
            f'Host: {target_host}:{target_port}\r\n'
            '\r\n'
        ).encode('ascii', errors='ignore')
        upstream_sock.sendall(request)
        response = self._recv_until(
            upstream_sock,
            b'\r\n\r\n',
            int(self._settings['limits']['max_header_bytes']),
        )
        status_code = self._parse_http_status(response)
        if status_code // 100 != 2:
            upstream_sock.close()
            raise RuntimeError(f'Upstream HTTP CONNECT rejected: {status_code}')
        return upstream_sock

    def _socks5_negotiate_upstream(
        self,
        upstream_sock: socket.socket,
        target_host: str,
        target_port: int,
    ) -> None:
        upstream_sock.sendall(b'\x05\x01\x00')
        greet = self._recv_exact(upstream_sock, 2)
        if greet[0] != 5 or greet[1] != 0:
            raise RuntimeError('Upstream SOCKS5 authentication method is unsupported')

        host_bytes = target_host.encode('idna')
        if len(host_bytes) > 255:
            raise RuntimeError('Target host is too long for SOCKS5 domain format')

        request = bytearray(b'\x05\x01\x00\x03')
        request.append(len(host_bytes))
        request.extend(host_bytes)
        request.extend(target_port.to_bytes(2, 'big'))
        upstream_sock.sendall(bytes(request))

        reply_head = self._recv_exact(upstream_sock, 4)
        if reply_head[0] != 5:
            raise RuntimeError('Invalid SOCKS5 reply version from upstream')
        if reply_head[1] != 0:
            raise RuntimeError(f'Upstream SOCKS5 connect failed with code {reply_head[1]}')

        atyp = reply_head[3]
        if atyp == 1:
            self._recv_exact(upstream_sock, 4)
        elif atyp == 3:
            name_len = self._recv_exact(upstream_sock, 1)[0]
            self._recv_exact(upstream_sock, name_len)
        elif atyp == 4:
            self._recv_exact(upstream_sock, 16)
        else:
            raise RuntimeError('Invalid SOCKS5 ATYP from upstream')
        self._recv_exact(upstream_sock, 2)

    def _open_upstream_for_target(self, target_host: str, target_port: int) -> socket.socket:
        mode = self._settings['mode']
        if mode == 'direct':
            return self._open_tcp(target_host, target_port)

        upstream = self._settings['upstream']
        upstream_protocol = upstream['protocol']
        if upstream_protocol == 'http':
            return self._connect_via_upstream_http(target_host, target_port)
        if upstream_protocol == 'socks5':
            upstream_sock = self._open_tcp(upstream['host'], upstream['port'])
            self._socks5_negotiate_upstream(upstream_sock, target_host, target_port)
            return upstream_sock
        raise RuntimeError(f'Unsupported upstream protocol: {upstream_protocol}')

    def _tunnel(self, client_socket: socket.socket, upstream_socket: socket.socket) -> Tuple[int, int]:
        lock = threading.Lock()
        bytes_up = 0
        bytes_down = 0

        def pipe(source: socket.socket, target: socket.socket, direction: str) -> None:
            nonlocal bytes_up, bytes_down
            try:
                while True:
                    data = source.recv(65536)
                    if not data:
                        break
                    target.sendall(data)
                    with lock:
                        if direction == 'up':
                            bytes_up += len(data)
                        else:
                            bytes_down += len(data)
            except OSError:
                pass
            finally:
                try:
                    target.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        t1 = threading.Thread(target=pipe, args=(client_socket, upstream_socket, 'up'), daemon=True)
        t2 = threading.Thread(target=pipe, args=(upstream_socket, client_socket, 'down'), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        try:
            upstream_socket.close()
        except OSError:
            pass

        return bytes_up, bytes_down

    def _handle_http_listener(self, client_socket: socket.socket) -> Tuple[int, int]:
        max_header_bytes = int(self._settings['limits']['max_header_bytes'])
        initial = self._recv_until(client_socket, b'\r\n\r\n', max_header_bytes)
        if not initial:
            return 0, 0

        method, target, _version = self._parse_http_request_line(initial)

        if method == 'CONNECT':
            target_host, target_port = self._parse_connect_target(target)

            if self._settings['mode'] == 'upstream_proxy' and self._settings['upstream']['protocol'] == 'http':
                upstream = self._open_tcp(self._settings['upstream']['host'], self._settings['upstream']['port'])
                upstream.sendall(initial)
                response = self._recv_until(upstream, b'\r\n\r\n', max_header_bytes)
                client_socket.sendall(response)
                status_code = self._parse_http_status(response)
                if status_code // 100 != 2:
                    upstream.close()
                    return 0, 0
                return self._tunnel(client_socket, upstream)

            upstream = self._open_upstream_for_target(target_host, target_port)
            client_socket.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            return self._tunnel(client_socket, upstream)

        if self._settings['mode'] == 'upstream_proxy' and self._settings['upstream']['protocol'] == 'http':
            upstream = self._open_tcp(self._settings['upstream']['host'], self._settings['upstream']['port'])
            upstream.sendall(initial)
            return self._tunnel(client_socket, upstream)

        body = b'Plain HTTP relay requires upstream HTTP proxy mode for transparent forwarding.\n'
        response = (
            b'HTTP/1.1 501 Not Implemented\r\n'
            b'Connection: close\r\n'
            + f'Content-Length: {len(body)}\r\n'.encode('ascii')
            + b'\r\n'
            + body
        )
        client_socket.sendall(response)
        return 0, 0

    def _socks5_send_reply(self, client_socket: socket.socket, code: int) -> None:
        response = b'\x05' + bytes([code]) + b'\x00\x01\x00\x00\x00\x00\x00\x00'
        client_socket.sendall(response)

    def _socks5_parse_target(self, client_socket: socket.socket, atyp: int) -> Tuple[str, int]:
        if atyp == 1:
            raw = self._recv_exact(client_socket, 4)
            host = str(ipaddress.IPv4Address(raw))
        elif atyp == 3:
            domain_len = self._recv_exact(client_socket, 1)[0]
            if domain_len == 0:
                raise RuntimeError('SOCKS5 domain length cannot be zero')
            host = self._recv_exact(client_socket, domain_len).decode('idna', errors='ignore')
        elif atyp == 4:
            raw = self._recv_exact(client_socket, 16)
            host = str(ipaddress.IPv6Address(raw))
        else:
            raise RuntimeError('Unsupported SOCKS5 address type')

        port = int.from_bytes(self._recv_exact(client_socket, 2), 'big')
        if port < 1 or port > 65535:
            raise RuntimeError('SOCKS5 target port out of range')
        return host, port

    def _handle_socks5_listener(self, client_socket: socket.socket) -> Tuple[int, int]:
        head = self._recv_exact(client_socket, 2)
        version = head[0]
        n_methods = head[1]
        if version != 5:
            raise RuntimeError('Unsupported SOCKS version')

        methods = self._recv_exact(client_socket, n_methods)
        if 0 not in methods:
            client_socket.sendall(b'\x05\xff')
            raise RuntimeError('SOCKS5 no-auth method not offered')

        client_socket.sendall(b'\x05\x00')

        request_head = self._recv_exact(client_socket, 4)
        if request_head[0] != 5:
            raise RuntimeError('Invalid SOCKS5 request version')
        command = request_head[1]
        atyp = request_head[3]

        if command != 1:
            self._socks5_send_reply(client_socket, 7)
            raise RuntimeError('SOCKS5 command is not CONNECT')

        target_host, target_port = self._socks5_parse_target(client_socket, atyp)

        try:
            upstream = self._open_upstream_for_target(target_host, target_port)
        except Exception as exc:  # noqa: BLE001
            self._socks5_send_reply(client_socket, 5)
            raise RuntimeError(str(exc)) from exc

        self._socks5_send_reply(client_socket, 0)
        return self._tunnel(client_socket, upstream)


_service: Optional[RelayProxyService] = None


def get_service() -> RelayProxyService:
    global _service
    if _service is None:
        _service = RelayProxyService()
    return _service
