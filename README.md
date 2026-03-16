# mangum-ws

WebSocket support for [Mangum](https://github.com/jordanerber/mangum) — run FastAPI behind AWS API Gateway WebSocket API on Lambda.

## Problem

Mangum doesn't natively support API Gateway WebSocket API events (`$connect`, `$disconnect`, custom routes). This library bridges that gap with:

1. **`WebSocketHandler`** — a Mangum custom handler that converts WebSocket events into HTTP POST requests to your FastAPI routes
2. **`Gateway`** — a unified interface for sending messages back to connected clients (via boto3 in production, or in-memory for local dev)

## Install

```bash
pip install mangum-ws
# With AWS support (boto3):
pip install mangum-ws[aws]
```

## Quick Start

```python
import json
import os
from fastapi import FastAPI, Request
from mangum import Mangum
from mangum_ws import WebSocketHandler, Gateway

app = FastAPI()

# Gateway: auto-selects AWS or local based on endpoint URL
gw = Gateway.auto(endpoint_url=os.getenv("APIGW_MANAGEMENT_URL"))

# Mount local dev WebSocket endpoint (no-op in production)
async def on_ws_message(connection_id: str, data: dict):
    # Your subscribe logic here
    pass
gw.mount(app, path="/", on_message=on_ws_message)

# --- Internal routes (hit by WebSocketHandler via Mangum) ---

@app.post("/internal/websocket/connect/{connection_id}")
async def ws_connect(connection_id: str):
    pass  # Connection opened

@app.post("/internal/websocket/disconnect/{connection_id}")
async def ws_disconnect(connection_id: str):
    pass  # Connection closed — clean up subscriptions

@app.post("/internal/websocket/sendmessage/{connection_id}")
async def ws_message(connection_id: str, request: Request):
    body = json.loads(await request.body())
    # Subscribe this connection to a topic, etc.

# --- Sending messages back to clients ---

async def notify(connection_ids: set[str], payload: dict):
    gone = await gw.send(connection_ids=connection_ids, data=payload)
    # Remove gone connection IDs from your subscription store
    return gone

# Lambda handler
handler = Mangum(app, custom_handlers=[WebSocketHandler])
```

## How It Works

### Route Mapping

API Gateway WebSocket routes are mapped to internal HTTP POST routes:

| API Gateway Route | FastAPI Route |
|---|---|
| `$connect` | `POST /internal/websocket/connect/{connectionId}` |
| `$disconnect` | `POST /internal/websocket/disconnect/{connectionId}` |
| `sendmessage` | `POST /internal/websocket/sendmessage/{connectionId}` |

### Gateway

`Gateway.auto()` picks the right implementation:

- **`AwsGateway`** — wraps `boto3.client("apigatewaymanagementapi")` to push messages via `post_to_connection`
- **`LocalGateway`** — holds in-memory WebSocket references; mounts a real `@app.websocket()` endpoint for local testing

Both return gone connection IDs from `send()` so you can clean up your subscription store.

## API

### `WebSocketHandler`

Drop-in Mangum custom handler. Pass it to `Mangum(app, custom_handlers=[WebSocketHandler])`.

### `Gateway.auto(endpoint_url=None) → Gateway`

Factory that returns `AwsGateway` if `endpoint_url` is provided, `LocalGateway` otherwise.

### `gateway.send(connection_ids, data) → set[str]`

Send `data` (dict or string) to all `connection_ids`. Returns the set of gone (disconnected) connection IDs.

### `gateway.send_to_connection(connection_id, data) → bool`

Send to a single connection. Returns `False` if the connection is gone.

### `gateway.mount(app, path="/", *, on_message=None)`

Mount a WebSocket endpoint on the FastAPI app for local development. No-op on non-local gateways (e.g. `AwsGateway`), so it can be called unconditionally. `on_message` is an optional `async` callback `(connection_id, json_data) → None`.

### `local_gateway.register(connection_id, ws) → str`

Register a WebSocket under a connection ID (generates one if empty).

### `local_gateway.unregister_ws(ws)`

Remove a WebSocket from all connection mappings.

## License

MIT
