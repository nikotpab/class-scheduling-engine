from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages active WebSocket connections keyed by job_id.
    On a single-instance deployment this in-memory store is sufficient.
    For horizontal scaling, replace with a Redis pub/sub backend.
    """

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, job_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(job_id, []).append(websocket)
        logger.info("WebSocket connected: job_id=%s", job_id)

    def disconnect(self, job_id: str, websocket: WebSocket) -> None:
        conns = self._connections.get(job_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self._connections.pop(job_id, None)
        logger.info("WebSocket disconnected: job_id=%s", job_id)

    async def broadcast(self, job_id: str, message: dict[str, Any]) -> None:
        """Send message to all WebSocket clients listening to a job_id."""
        dead: list[WebSocket] = []
        for websocket in self._connections.get(job_id, []):
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)
        for ws in dead:
            self.disconnect(job_id, ws)

    async def send_personal(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        await websocket.send_json(message)


# Application-wide singleton
manager = ConnectionManager()
