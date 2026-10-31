from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class VRBridge:
    def __init__(self, host: str = "0.0.0.0", port: int = 8901) -> None:
        self.host = host
        self.port = port
        self._clients: set[Any] = set()
        self._server = None

    async def _handler(self, websocket: Any) -> None:
        self._clients.add(websocket)
        try:
            await websocket.send(json.dumps({
                "type": "welcome",
                "message": "REAPER VR Bridge connected",
                "version": "4.0.0",
            }))
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(websocket, data)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            self._clients.discard(websocket)

    async def _handle_message(self, ws: Any, data: dict[str, Any]) -> None:
        msg_type = data.get("type", "")
        if msg_type == "ping":
            await ws.send(json.dumps({"type": "pong"}))
        elif msg_type == "subscribe":
            await ws.send(json.dumps({"type": "subscribed", "channel": data.get("channel")}))

    async def broadcast(self, event: dict[str, Any]) -> None:
        if not self._clients:
            return
        message = json.dumps(event)
        dead = set()
        for client in self._clients.copy():
            try:
                await client.send(message)
            except Exception:
                dead.add(client)
        self._clients -= dead

    async def broadcast_scan_event(self, event_type: str, data: Any) -> None:
        await self.broadcast({
            "type": "scan_event",
            "event": event_type,
            "data": data,
        })

    async def start(self) -> None:
        try:
            import websockets
            self._server = await websockets.serve(self._handler, self.host, self.port)
            logger.info(f"VR WebSocket bridge listening on ws://{self.host}:{self.port}")
        except ImportError:
            logger.warning("websockets not installed — VR bridge disabled")
        except Exception as e:
            logger.error(f"VR bridge failed to start: {e}")

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()


vr_bridge = VRBridge()
