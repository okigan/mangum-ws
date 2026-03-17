"""mangum-ws: WebSocket support for Mangum (AWS API Gateway WebSocket API → FastAPI)."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

import fastapi

from mangum_ws.handler import WebSocketHandler, INTERNAL_WS_PATH_PREFIX
from mangum_ws.gateway import Gateway, AwsGateway, LocalGateway

# Callback type aliases
ConnectCallback = Callable[[str], Awaitable[None]]
DisconnectCallback = Callable[[str], Awaitable[None]]
MessageCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class MangumWS:
    """Single entry-point for mangum-ws.

    Register handlers with decorators, then include the router and mount::

        from mangum_ws import MangumWS

        ws = MangumWS(endpoint_url=os.getenv("APIGW_MANAGEMENT_URL"))

        @ws.on_connect
        async def handle_connect(connection_id: str):
            print(f"Connected: {connection_id}")

        @ws.on_message
        async def handle_message(connection_id: str, data: dict):
            # subscribe to topic, etc.
            pass

        app.include_router(ws.router)   # /internal/websocket/* routes
        ws.mount(app)                   # local dev WS endpoint (no-op in prod)
        handler = Mangum(app, custom_handlers=[ws.handler])
    """

    def __init__(self, endpoint_url: str | None = None) -> None:
        self._gateway = Gateway.auto(endpoint_url=endpoint_url)
        self._on_connect_fn: ConnectCallback | None = None
        self._on_disconnect_fn: DisconnectCallback | None = None
        self._on_message_fn: MessageCallback | None = None

    # ── decorators ──────────────────────────────────────────────

    def on_connect(self, fn: ConnectCallback) -> ConnectCallback:
        """Register a ``$connect`` handler: ``async def(connection_id) -> None``."""
        self._on_connect_fn = fn
        return fn

    def on_disconnect(self, fn: DisconnectCallback) -> DisconnectCallback:
        """Register a ``$disconnect`` handler: ``async def(connection_id) -> None``."""
        self._on_disconnect_fn = fn
        return fn

    def on_message(self, fn: MessageCallback) -> MessageCallback:
        """Register a message handler: ``async def(connection_id, data) -> None``."""
        self._on_message_fn = fn
        return fn

    # ── router ──────────────────────────────────────────────────

    @property
    def router(self) -> fastapi.APIRouter:
        """A ``fastapi.APIRouter`` containing the ``/internal/websocket/*``
        POST routes that ``WebSocketHandler`` dispatches to in Lambda.

        Add to your app with ``app.include_router(ws.router)``.
        """
        r = fastapi.APIRouter()
        on_connect = self._on_connect_fn
        on_disconnect = self._on_disconnect_fn
        on_message = self._on_message_fn

        @r.post(f"{INTERNAL_WS_PATH_PREFIX}/connect/{{connection_id}}")
        async def _ws_connect(connection_id: str) -> dict[str, str]:
            if on_connect is not None:
                await on_connect(connection_id)
            return {"status": "connected"}

        @r.post(f"{INTERNAL_WS_PATH_PREFIX}/disconnect/{{connection_id}}")
        async def _ws_disconnect(connection_id: str) -> dict[str, str]:
            if on_disconnect is not None:
                await on_disconnect(connection_id)
            return {"status": "disconnected"}

        @r.post(f"{INTERNAL_WS_PATH_PREFIX}/sendmessage/{{connection_id}}")
        async def _ws_sendmessage(
            connection_id: str, request: fastapi.Request
        ) -> dict[str, Any]:
            body = await request.body()
            data = json.loads(body.decode())
            if on_message is not None:
                await on_message(connection_id, data)
            return {"status": "received"}

        return r

    # ── handler / gateway ───────────────────────────────────────

    @property
    def handler(self) -> type:
        """The Mangum custom handler class.  Pass to
        ``Mangum(app, custom_handlers=[ws.handler])``."""
        return WebSocketHandler

    @property
    def is_local(self) -> bool:
        return self._gateway.is_local

    async def send_to_connection(self, connection_id: str, data: str) -> bool:
        return await self._gateway.send_to_connection(connection_id, data)

    async def send(
        self,
        connection_ids: set[str] | frozenset[str],
        data: dict[str, Any] | str,
    ) -> set[str]:
        return await self._gateway.send(connection_ids, data)

    def mount(self, app: fastapi.FastAPI, path: str = "/") -> None:
        """Mount a local-dev WebSocket endpoint that reuses the registered
        handlers.  No-op in production (``AwsGateway``)."""
        self._gateway.mount(
            app, path=path,
            on_connect=self._on_connect_fn,
            on_disconnect=self._on_disconnect_fn,
            on_message=self._on_message_fn,
        )


__all__ = [
    "MangumWS",
    # Lower-level pieces still accessible if needed
    "WebSocketHandler",
    "Gateway",
    "AwsGateway",
    "LocalGateway",
]
