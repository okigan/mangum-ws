"""mangum-ws demo: a tiny chat room.

Run with:
    uv run python examples/demochat.py

Or:
    uv run uvicorn examples.demochat:app --reload

Open http://localhost:8000 in two browser tabs and chat between them.
"""

import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from mangum import Mangum
from mangum_ws import MangumWS

app = FastAPI()

ws = MangumWS(endpoint_url=os.getenv("APIGW_MANAGEMENT_URL"))

# In-memory set of connected clients
connected: set[str] = set()


@ws.on_connect
async def handle_connect(connection_id: str):
    connected.add(connection_id)
    # Notify everyone that someone joined
    await ws.send(connected, {"type": "system", "text": f"{connection_id[:8]}… joined"})


@ws.on_disconnect
async def handle_disconnect(connection_id: str):
    connected.discard(connection_id)
    await ws.send(connected, {"type": "system", "text": f"{connection_id[:8]}… left"})


@ws.on_message
async def handle_message(connection_id: str, data: dict):
    text = data.get("text", "")
    if text:
        await ws.send(connected, {
            "type": "chat",
            "from": connection_id[:8],
            "text": text,
        })


app.include_router(ws.router)
ws.mount(app, path="/ws")


@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html>
<head>
  <title>mangum-ws chat demo</title>
  <style>
    body { font-family: system-ui; max-width: 600px; margin: 2rem auto; }
    #log { border: 1px solid #ccc; padding: 1rem; height: 300px; overflow-y: auto;
           background: #fafafa; margin-bottom: 1rem; }
    .system { color: #888; font-style: italic; }
    form { display: flex; gap: 0.5rem; }
    input { flex: 1; padding: 0.5rem; }
    button { padding: 0.5rem 1rem; }
  </style>
</head>
<body>
  <h2>mangum-ws chat demo</h2>
  <div id="log"></div>
  <form onsubmit="send(event)">
    <input id="msg" placeholder="Type a message…" autocomplete="off" />
    <button>Send</button>
  </form>
  <script>
    const log = document.getElementById('log');
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    let ws;

    function addLog(text, cls) {
      const div = document.createElement('div');
      if (cls) div.className = cls;
      div.textContent = text;
      log.appendChild(div);
      log.scrollTop = log.scrollHeight;
    }

    function connect() {
      ws = new WebSocket(`${proto}//${location.host}/ws`);

      ws.onopen = () => addLog('Connected', 'system');

      ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.type === 'system') {
          addLog(data.text, 'system');
        } else {
          addLog(`${data.from}…: ${data.text}`);
        }
      };

      ws.onclose = () => {
        addLog('Disconnected — reconnecting…', 'system');
        setTimeout(connect, 1000);
      };
    }

    connect();

    function send(e) {
      e.preventDefault();
      const input = document.getElementById('msg');
      if (input.value && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ text: input.value }));
        input.value = '';
      }
    }
  </script>
</body>
</html>"""


handler = Mangum(app, custom_handlers=[ws.handler])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
