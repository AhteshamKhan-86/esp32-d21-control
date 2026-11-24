from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import json

app = FastAPI()

# Dono boards ka current state track karne ke liye
device_states = {
    "master": 0,
    "slave_1": 0
}

esp32_client: WebSocket | None = None
browser_clients: list[WebSocket] = []

html_page = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Department Automation - 2 Node Control</title>
  <style>
    body {
      background: #0f172a;
      color: #f8fafc;
      font-family: system-ui, -apple-system, sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      padding: 20px;
    }
    .status-badge {
      padding: 6px 14px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 24px;
      background: #334155;
      color: #94a3b8;
    }
    .status-badge.online {
      background: #064e3b;
      color: #34d399;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 16px;
      width: 100%;
      max-width: 360px;
    }
    .card {
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 16px;
      padding: 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .info h3 { margin: 0 0 4px 0; font-size: 17px; }
    .info p { margin: 0; font-size: 12px; color: #94a3b8; }
    button {
      padding: 12px 22px;
      border: none;
      border-radius: 12px;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
      transition: 0.2s;
      min-width: 88px;
    }
    button.off { background: #334155; color: #e2e8f0; }
    button.on { background: #10b981; color: #022c22; box-shadow: 0 0 15px rgba(16,185,129,0.4); }
  </style>
</head>
<body>
  <div id="connStatus" class="status-badge">Master ESP32: Offline</div>

  <div class="grid">
    <div class="card">
      <div class="info">
        <h3>Switch 1 (Master)</h3>
        <p>Direct Wi-Fi • Pin D21</p>
      </div>
      <button id="btn-master" class="off" onclick="toggleDevice('master')">OFF</button>
    </div>

    <div class="card">
      <div class="info">
        <h3>Switch 2 (Slave 1)</h3>
        <p>ESP-NOW Radio • Pin D21</p>
      </div>
      <button id="btn-slave_1" class="off" onclick="toggleDevice('slave_1')">OFF</button>
    </div>
  </div>

  <script>
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/ws/ui`);
    let states = { master: 0, slave_1: 0 };

    function render() {
      for (const key of ['master', 'slave_1']) {
        const btn = document.getElementById('btn-' + key);
        const isOn = states[key] === 1;
        btn.textContent = isOn ? 'ON' : 'OFF';
        btn.className = isOn ? 'on' : 'off';
      }
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'sync') {
        states = data.states;
        render();
        const badge = document.getElementById('connStatus');
        badge.textContent = data.esp_online ? 'Master ESP32: Online' : 'Master ESP32: Offline';
        badge.className = 'status-badge' + (data.esp_online ? ' online' : '');
      }
    };

    function toggleDevice(target) {
      const nextState = states[target] === 1 ? 0 : 1;
      ws.send(JSON.stringify({ target: target, state: nextState }));
    }
  </script>
</body>
</html>
"""

async def broadcast_ui():
    payload = json.dumps({
        "type": "sync",
        "states": device_states,
        "esp_online": esp32_client is not None
    })
    for client in list(browser_clients):
        try:
            await client.send_text(payload)
        except Exception:
            browser_clients.remove(client)

@app.get("/")
async def get_ui():
    return HTMLResponse(html_page)

@app.websocket("/ws/ui")
async def ui_endpoint(websocket: WebSocket):
    await websocket.accept()
    browser_clients.append(websocket)
    await broadcast_ui()
    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            target = msg.get("target")
            state = int(msg.get("state", 0))
            if target in device_states:
                device_states[target] = state
                if esp32_client:
                    await esp32_client.send_text(json.dumps({"target": target, "state": state}))
                await broadcast_ui()
    except WebSocketDisconnect:
        if websocket in browser_clients:
            browser_clients.remove(websocket)

@app.websocket("/ws/esp32")
async def esp32_endpoint(websocket: WebSocket):
    global esp32_client
    await websocket.accept()
    esp32_client = websocket
    await broadcast_ui()
    # Reconnect hone par purana state wapas bhej dein
    for target, state in device_states.items():
        await websocket.send_text(json.dumps({"target": target, "state": state}))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if esp32_client == websocket:
            esp32_client = None
        await broadcast_ui()