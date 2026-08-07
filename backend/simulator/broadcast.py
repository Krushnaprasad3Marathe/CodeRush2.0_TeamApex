"""
Aegis MOS — WebSocket Broadcast Manager.

Handles fan-out of simulation state to all connected WebSocket clients.

Three guarantees:
  1. Byte-identical: serialize once, send the same bytes to every client
  2. Instant-state-on-connect: new clients get current state immediately
  3. Backpressure-safe: per-client queue with bounded size; slow clients drop oldest
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("aegis.broadcast")


class BroadcastManager:
    """
    Manages WebSocket connections and broadcasts simulation state.

    Each connected client gets a dedicated asyncio.Queue. The publish()
    method pushes the same serialized payload to every queue. A per-client
    sender task drains the queue and sends over the WebSocket.

    If a client's queue is full (slow consumer), the oldest tick is dropped
    to keep the stream live — for a real-time dashboard, the latest state
    is always more valuable than a stale one.
    """

    def __init__(self, max_queue_size: int = 50):
        self._clients: dict[str, tuple[WebSocket, asyncio.Queue[bytes]]] = {}
        self._sender_tasks: dict[str, asyncio.Task[Any]] = {}
        self._latest_payload: bytes | None = None
        self._max_queue = max_queue_size
        self._lock = asyncio.Lock()

    @property
    def client_count(self) -> int:
        """Number of currently connected clients."""
        return len(self._clients)

    async def connect(self, ws: WebSocket, client_id: str) -> None:
        """
        Register a new WebSocket client.

        Accepts the connection, sends instant-state-on-connect if available,
        and starts a per-client sender task.
        """
        await ws.accept()

        q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=self._max_queue)

        async with self._lock:
            self._clients[client_id] = (ws, q)

        # Instant-state-on-connect: send current state immediately
        if self._latest_payload is not None:
            try:
                await ws.send_bytes(self._latest_payload)
            except Exception:
                await self.disconnect(client_id)
                return

        # Start per-client sender task
        task = asyncio.create_task(
            self._client_sender(client_id, ws, q),
            name=f"ws-sender-{client_id[:8]}",
        )
        self._sender_tasks[client_id] = task
        logger.debug(f"Client {client_id[:8]} connected ({self.client_count} total)")

    async def disconnect(self, client_id: str) -> None:
        """Remove a client and cancel its sender task."""
        async with self._lock:
            self._clients.pop(client_id, None)

        task = self._sender_tasks.pop(client_id, None)
        if task and not task.done():
            task.cancel()

        logger.debug(f"Client {client_id[:8]} disconnected ({self.client_count} total)")

    async def publish(self, payload: bytes) -> None:
        """
        Broadcast a payload to all connected clients.

        The same bytes object is pushed to every client's queue.
        If a client's queue is full, the oldest entry is dropped.
        """
        self._latest_payload = payload

        dead_clients: list[str] = []

        async with self._lock:
            for cid, (ws, q) in self._clients.items():
                try:
                    if q.full():
                        try:
                            q.get_nowait()  # Drop oldest tick for slow consumers
                        except asyncio.QueueEmpty:
                            pass
                    q.put_nowait(payload)
                except Exception:
                    dead_clients.append(cid)

        # Clean up dead clients outside the lock
        for cid in dead_clients:
            await self.disconnect(cid)

    async def _client_sender(
        self, client_id: str, ws: WebSocket, q: asyncio.Queue[bytes]
    ) -> None:
        """
        Per-client sender coroutine.

        Drains the queue and sends payloads over the WebSocket.
        Exits cleanly on disconnect or cancellation.
        """
        try:
            while client_id in self._clients:
                payload = await asyncio.wait_for(q.get(), timeout=5.0)
                await ws.send_bytes(payload)
        except WebSocketDisconnect:
            pass
        except asyncio.TimeoutError:
            # No data for 5 seconds — check if still connected
            if client_id in self._clients:
                # Still connected, just no data — loop back
                asyncio.create_task(self._client_sender(client_id, ws, q))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Sender for {client_id[:8]} failed: {e}")
        finally:
            await self.disconnect(client_id)
