"""mangum-ws: WebSocket support for Mangum (AWS API Gateway WebSocket API → FastAPI)."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

import fastapi

from mangum_ws.handler import WebSocketHandler
from mangum_ws.gateway import Gateway, AwsGateway, LocalGateway


class MangumWS:
    """Single entry-point for mangum-ws.

    Bundles the Mangum ``WebSocketHandler`` and the ``Gateway`` so users
    only need one import and one object::

        from mangum_ws import MangumWS

        ws = MangumWS(endpoint_url=os.getenv("APIGW_MANAGEMENT_URL"))
        ws.mount(app, path="/", on_message=on_ws_message)
        mangum = Mangum(app, custom_handlers=[ws.handler])
        gone = await ws.send(connection_ids, data)
    """

    def __init__(self, endpoint_url: str | None = None) -> None:
        self._gateway = Gateway.auto(endpoint_url=endpoint_url)

    @property
    def handler(self) -> type:
        """The Mangum custom handler class.  Pass to
        ``Mangum(app, custom_handlers=[ws.handler])``."""
        return WebSocketHandler

    @property
    def is_local(self) -> bool:
        return self._gateway.is_local

    # ── delegate to gateway ─────────────────────────────────────

    async def send_to_connection(self, connection_id: str, data: str) -> bool:
        return await self._gateway.send_to_connection(connection_id, data)

    async def send(
        self,
        connection_ids: set[str] | frozenset[str],
        data: dict[str, Any] | str,
    ) -> set[str]:
        return await self._gateway.send(connection_ids, data)

    def mount(
        self,
        app: fastapi.FastAPI,
        path: str = "/",
        *,
        on_message: Optional[Callable[[str, dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        self._gateway.mount(app, path=path, on_message=on_message)


__all__ = [
    "MangumWS",
    # Lower-level pieces still accessible if needed
    "WebSocketHandler",
    "Gateway",
    "AwsGateway",
    "LocalGateway",
]
