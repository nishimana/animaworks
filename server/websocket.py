from __future__ import annotations
# AnimaWorks - Digital Person Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.


import json
import logging

from fastapi import WebSocket

logger = logging.getLogger("animaworks.websocket")


class WebSocketManager:
    """Manages WebSocket connections and broadcasts."""

    _MAX_QUEUE_SIZE = 50  # prevent unbounded growth

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._notification_queue: list[dict] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket connected. Total: %d", len(self.active_connections))
        # Flush any queued notifications to the new client
        await self.flush_notification_queue(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            "WebSocket disconnected. Total: %d", len(self.active_connections)
        )

    async def broadcast_notification(self, data: dict) -> None:
        """Broadcast a notification event. Queue if no clients connected."""
        event = {"type": "person.notification", "data": data}
        if self.active_connections:
            await self.broadcast(event)
        else:
            self._notification_queue.append(event)
            if len(self._notification_queue) > self._MAX_QUEUE_SIZE:
                self._notification_queue.pop(0)  # drop oldest

    async def flush_notification_queue(self, websocket: WebSocket) -> None:
        """Send queued notifications to a newly connected client."""
        while self._notification_queue:
            event = self._notification_queue.pop(0)
            try:
                await websocket.send_text(
                    json.dumps(event, ensure_ascii=False, default=str)
                )
            except Exception:
                break

    async def broadcast(self, data: dict) -> None:
        if not self.active_connections:
            return
        message = json.dumps(data, ensure_ascii=False, default=str)
        disconnected: list[WebSocket] = []
        for conn in self.active_connections:
            try:
                await conn.send_text(message)
            except Exception:
                disconnected.append(conn)
        for conn in disconnected:
            self.disconnect(conn)