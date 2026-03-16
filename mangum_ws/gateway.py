"""Unified gateway for sending messages to API Gateway WebSocket connections.

Two implementations:
- ``AwsGateway``  – uses boto3 ``apigatewaymanagementapi``
- ``LocalGateway`` – in-memory delivery via FastAPI WebSocket objects (for local dev)
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Optional

import fastapi

logger = logging.getLogger(__name__)


class Gateway:
    """Abstract base for pushing messages to WebSocket connections."""

    is_local: bool = False

    @staticmethod
    def auto(endpoint_url: str | None = None) -> Gateway:
        """Create the right gateway: ``AwsGateway`` if *endpoint_url* is
        provided, ``LocalGateway`` otherwise."""
        if endpoint_url:
            return AwsGateway(endpoint_url)
        return LocalGateway()

    async def send_to_connection(self, connection_id: str, data: str) -> bool:
        """Send *data* to one connection.  Return ``False`` if the connection
        is gone."""
        raise NotImplementedError

    async def send(
        self,
        connection_ids: set[str] | frozenset[str],
        data: dict[str, Any] | str,
    ) -> set[str]:
        """Send to many connections.  Returns the set of gone connection IDs."""
        payload = json.dumps(data) if isinstance(data, dict) else data
        gone: set[str] = set()
        for cid in connection_ids:
            if not await self.send_to_connection(cid, payload):
                gone.add(cid)
        return gone

    def mount(
        self,
        app: fastapi.FastAPI,
        path: str = "/",
        *,
        on_message: Optional[Callable[[str, dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        """Mount a local-dev WebSocket endpoint.  Only available on
        ``LocalGateway``."""
        raise NotImplementedError("mount() is only available on LocalGateway")


class AwsGateway(Gateway):
    """Send messages via boto3 ``apigatewaymanagementapi``."""

    def __init__(self, endpoint_url: str) -> None:
        import boto3

        self._client: Any = boto3.client(
            "apigatewaymanagementapi", endpoint_url=endpoint_url
        )

    async def send_to_connection(self, connection_id: str, data: str) -> bool:
        try:
            self._client.post_to_connection(ConnectionId=connection_id, Data=data)
            return True
        except self._client.exceptions.GoneException:
            logger.debug("Connection %s is gone", connection_id)
            return False
        except Exception:
            logger.exception("Failed to send to connection %s", connection_id)
            return False


@dataclass
class LocalGateway(Gateway):
    """In-memory gateway that delivers messages through FastAPI WebSocket
    objects.  Intended for local development and testing."""

    is_local: bool = field(default=True, init=False)
    _connections: dict[str, list[fastapi.WebSocket]] = field(default_factory=dict)

    # ── send ────────────────────────────────────────────────────

    async def send_to_connection(self, connection_id: str, data: str) -> bool:
        sockets = self._connections.get(connection_id, [])
        if not sockets:
            return False
        stale: list[fastapi.WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_text(data)
            except Exception:
                stale.append(ws)
        for ws in stale:
            sockets.remove(ws)
        if not sockets:
            del self._connections[connection_id]
            return False
        return True

    # ── connection management ───────────────────────────────────

    def register(self, connection_id: str, ws: fastapi.WebSocket) -> str:
        """Register a WebSocket under *connection_id*.  Returns the
        connection_id (generates one if empty)."""
        if not connection_id:
            connection_id = f"local_{uuid.uuid4()}"
        self._connections.setdefault(connection_id, []).append(ws)
        return connection_id

    def unregister_ws(self, ws: fastapi.WebSocket) -> None:
        """Remove *ws* from all connection mappings."""
        for cid in list(self._connections):
            self._connections[cid] = [s for s in self._connections[cid] if s is not ws]
            if not self._connections[cid]:
                del self._connections[cid]

    # ── local dev endpoint ──────────────────────────────────────

    def mount(
        self,
        app: fastapi.FastAPI,
        path: str = "/",
        *,
        on_message: Optional[Callable[[str, dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        """Mount a real WebSocket endpoint on *app* that bridges browser
        WebSocket connections to the internal HTTP route convention used
        by ``WebSocketHandler``.

        *on_message* is an optional async callback invoked with
        ``(connection_id, parsed_json)`` for each incoming message.  If not
        provided, messages are forwarded to FastAPI's internal routes via
        ``TestClient``-style dispatch (you usually don't need this — just
        register your ``/internal/websocket/…`` routes on the app).
        """
        gw = self  # capture for closure

        @app.websocket(path)
        async def _local_ws_endpoint(websocket: fastapi.WebSocket) -> None:
            await websocket.accept()
            local_cids: list[str] = []
            try:
                while True:
                    data = await websocket.receive_text()
                    logger.debug("Local WS received: %s", data)
                    await websocket.send_text(
                        json.dumps({"type": "info", "message": "Message received", "data": data})
                    )
                    try:
                        json_data = json.loads(data)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    cid = gw.register("", websocket)
                    local_cids.append(cid)

                    if on_message is not None:
                        await on_message(cid, json_data)
            except fastapi.WebSocketDisconnect:
                logger.debug("Local WS disconnected")
            except Exception as exc:
                logger.error("Local WS error: %s", exc)
            finally:
                gw.unregister_ws(websocket)
                try:
                    await websocket.close()
                except Exception:
                    pass
