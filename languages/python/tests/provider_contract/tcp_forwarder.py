from __future__ import annotations

import socket
import threading
from contextlib import contextmanager, suppress
from select import select
from socketserver import BaseRequestHandler, ThreadingTCPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

__all__ = ["TcpForwarder"]


class TcpForwarder:
    """A loopback endpoint that starts down and keeps its port through outages.

    Down means new streams close before any protocol exchange. Severing also
    shuts down both ends of every stream already being forwarded.
    """

    def __init__(self, upstream: tuple[str, int]) -> None:
        relay = self._relay

        class _Relay(BaseRequestHandler):
            def handle(self) -> None:
                relay(self.request)

        self._upstream = upstream
        self._forwarding = False
        self._lock = threading.Lock()
        self._streams: set[tuple[socket.socket, socket.socket]] = set()
        self._server = ThreadingTCPServer(("127.0.0.1", 0), _Relay)
        self.port: int = self._server.server_address[1]

    @classmethod
    @contextmanager
    def open(cls, upstream: tuple[str, int]) -> Generator[TcpForwarder]:
        forwarder = cls(upstream)
        with forwarder._server as server:
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
            thread.start()
            try:
                yield forwarder
            finally:
                server.shutdown()
                forwarder.sever()
                thread.join()

    def restore(self) -> None:
        with self._lock:
            self._forwarding = True

    def sever(self) -> None:
        with self._lock:
            self._forwarding = False
            for stream in self._streams:
                for end in stream:
                    with suppress(OSError):
                        end.shutdown(socket.SHUT_RDWR)

    def _relay(self, client: socket.socket) -> None:
        with suppress(OSError):
            with self._lock:
                if not self._forwarding:
                    return
                upstream = socket.create_connection(self._upstream, timeout=1.0)
                stream = (client, upstream)
                self._streams.add(stream)
            try:
                upstream.settimeout(None)
                while True:
                    readable, _, _ = select(stream, (), ())
                    for source in readable:
                        data = source.recv(65536)
                        if not data:
                            return
                        sink = upstream if source is client else client
                        sink.sendall(data)
            finally:
                with self._lock:
                    self._streams.remove(stream)
                upstream.close()
