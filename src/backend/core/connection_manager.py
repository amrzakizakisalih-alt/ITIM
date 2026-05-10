import asyncio
from typing import List
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast(self, message: str, exclude: WebSocket = None):
        """Broadcast to all connected clients, optionally excluding one.
        Silently handles dead connections."""
        async with self._lock:
            connections = list(self.active_connections)
        dead = []
        for connection in connections:
            if connection is not exclude:
                try:
                    await connection.send_text(message)
                except Exception as exc:
                    logger.debug("Broadcast failed to a client: %s", exc)
                    dead.append(connection)
        for d in dead:
            await self.disconnect(d)
