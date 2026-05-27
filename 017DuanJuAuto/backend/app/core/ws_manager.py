from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket


class WSManager:
    def __init__(self):
        self.conns: list[WebSocket] = []
        self.main_loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.conns.append(ws)
        if self.main_loop is None:
            self.main_loop = asyncio.get_running_loop()

    def disconnect(self, ws: WebSocket):
        if ws in self.conns:
            self.conns.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in list(self.conns):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for d in dead:
            self.disconnect(d)

    def broadcast_sync(self, data: dict):
        if self.main_loop is None:
            return
        future = asyncio.run_coroutine_threadsafe(self.broadcast(data), self.main_loop)
        try:
            future.result(timeout=5)
        except Exception:
            logging.warning("broadcast_sync failed to deliver message", exc_info=True)


manager = WSManager()
