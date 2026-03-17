# mangum-ws

WebSocket support for [Mangum](https://github.com/Kludex/mangum) — use FastAPI WebSockets on AWS Lambda behind API Gateway WebSocket API.

**Try it now** — a working chat demo in ~40 lines:

```bash
git clone https://github.com/okigan/mangum-ws.git && cd mangum-ws
uv sync --group dev
uv run python examples/demochat.py
# Open http://localhost:8000 in two browser tabs
```

## Problem

[Mangum](https://github.com/Kludex/mangum) lets you run ASGI apps (like FastAPI) on AWS Lambda behind API Gateway. It handles HTTP requests well, but **API Gateway WebSocket API** works differently: there's no persistent server — each WebSocket event (`$connect`, `$disconnect`, messages) triggers a separate Lambda invocation, and sending messages back requires calling the API Gateway Management API via HTTP.

Mangum doesn't natively support this. mangum-ws bridges the gap with a single `MangumWS` object:

- **Inbound** (Lambda): converts API Gateway WebSocket events into FastAPI route calls via a Mangum custom handler
- **Outbound** (Lambda): sends messages back to clients via `boto3` `post_to_connection`
- **Local dev**: mounts a real FastAPI WebSocket endpoint so the same code works without AWS

## Install

```bash
pip install mangum-ws
# With AWS support (boto3):
pip install mangum-ws[aws]
```

For local development with `ws.mount()`, uvicorn needs a WebSocket library:

```bash
pip install uvicorn[standard]
```

## Quick Start

```python
import os
from fastapi import FastAPI
from mangum import Mangum
from mangum_ws import MangumWS

app = FastAPI()

# One object, auto-selects AWS or local based on endpoint URL
ws = MangumWS(endpoint_url=os.getenv("APIGW_MANAGEMENT_URL"))

# Register WebSocket lifecycle handlers (write once, used everywhere)
@ws.on_connect
async def handle_connect(connection_id: str):
    print(f"Connected: {connection_id}")

@ws.on_disconnect
async def handle_disconnect(connection_id: str):
    print(f"Disconnected: {connection_id}")

@ws.on_message
async def handle_message(connection_id: str, data: dict):
    # Subscribe this connection to a topic, etc.
    pass

# Standard FastAPI: include the router (generates /internal/websocket/* routes)
app.include_router(ws.router)

# Local dev: mount a real WebSocket endpoint (no-op in production)
ws.mount(app)

# Sending messages back to clients
async def notify(connection_ids: set[str], payload: dict):
    gone = await ws.send(connection_ids=connection_ids, data=payload)
    # Remove gone connection IDs from your subscription store
    return gone

# Lambda handler
handler = Mangum(app, custom_handlers=[ws.handler])
```

## How It Works

In production, API Gateway WebSocket API manages connections and invokes Lambda for each event (`$connect`, `$disconnect`, `sendmessage`). The library converts these into FastAPI route calls via a Mangum custom handler, and sends messages back via `boto3`.

For local development, `ws.mount()` creates a real `@app.websocket()` endpoint that reuses the same handlers — so your code works identically in both environments.

## API

### `MangumWS(endpoint_url=None)`

Main entry point. Uses `AwsGateway` (boto3) if `endpoint_url` is provided, `LocalGateway` (in-memory) otherwise.

### `@ws.on_connect` / `@ws.on_disconnect` / `@ws.on_message`

Decorators to register WebSocket lifecycle handlers. Each handler is written once and used in both Lambda (`ws.router`) and local dev (`ws.mount`):

- **`@ws.on_connect`** — `async def(connection_id: str) -> None` — called on `$connect`
- **`@ws.on_disconnect`** — `async def(connection_id: str) -> None` — called on `$disconnect`
- **`@ws.on_message`** — `async def(connection_id: str, data: dict) -> None` — called on custom routes (e.g. `sendmessage`)

All are optional.

### `ws.router`

A `fastapi.APIRouter` containing `POST /internal/websocket/{connect,disconnect,sendmessage}/{connection_id}` routes that dispatch to your registered handlers. Add with `app.include_router(ws.router)`.

### `ws.mount(app, path="/")`

Mount a real `@app.websocket()` endpoint for local development, reusing the registered handlers. No-op in production (so you can call it unconditionally).

### `ws.handler`

The Mangum custom handler class. Pass to `Mangum(app, custom_handlers=[ws.handler])`.

### `ws.send(connection_ids, data) -> set[str]`

Send `data` (dict or string) to all `connection_ids`. Returns the set of gone (disconnected) connection IDs.

### `ws.send_to_connection(connection_id, data) -> bool`

Send to a single connection. Returns `False` if the connection is gone.

### `ws.is_local`

`True` when backed by `LocalGateway` (local dev), `False` when backed by `AwsGateway`.

## License

MIT
