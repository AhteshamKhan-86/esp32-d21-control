from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import json

app = FastAPI()

ALLOWED_MAC = "38:18:2B:8B:BD:40"

connected_devices = {}  # Key = MAC Address
web_clients = set()
current_state = "OFF"   # Pin D21 ka current state track karega

html_page = """
<!DOCTYPE html>
<html>
<head>
  <title>MAC-Based ESP32 D21 Control</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
    .box { background: #1e293b; padding: 32px; border-radius: 16px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.5); width: 320px; }
    .badge { display: inline-block; padding: 6px 14px; border-radius: 20px; font-size: 13px; margin-bottom: 24px; background: #ef4444; }
    .online { background: #22c55e; }
    
    /* Single Smart Toggle Button */
    #toggleBtn {
      width: 100%;
      padding: 18px;
      font-size: 18px;
      font-weight: bold;
      border: none;
      border-radius: 12px;
      cursor: pointer;
      transition: all 0.2s ease;
      color: white;
    }
    .state-off { background: #ef4444; box-shadow: 0 4px 14px rgba(239, 68, 68, 0.4); }
    .state-on  { background: #22c55e; box-shadow: 0 4px 14px rgba(34, 197, 94, 0.4); }
    #toggleBtn:active { transform: scale(0.97); }
    
    #log { margin-top: 18px; font-size: 13px; color: #94a3b8; }
  </style>
</head>
<body>
  <div class="box">
    <h2>ESP32 D21 Control</h2>
    <div id="statusBadge" class="badge">Target ESP32 Offline</div>
    
    <!-- Sirf Ek Hi Toggle Switch -->
    <button id="toggleBtn" class="state-off" onclick="toggleSwitch()">
      CURRENT: OFF (Tap to ON)
    </button>
    
    <p id="log">Waiting for command...</p>
  </div>

  <script>
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(protocol + '//' + location.host + '/ws');

    ws.onopen = () => ws.send(JSON.stringify({ type: 'WEB_CLIENT' }));

    function updateButtonUI(state) {
      const btn = document.getElementById('toggleBtn');
      if (state === 'ON') {
        btn.innerText = 'CURRENT: ON (Tap to OFF)';
        btn.className = 'state-on';
      } else {
        btn.innerText = 'CURRENT: OFF (Tap to ON)';
        btn.className = 'state-off';
      }
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const badge = document.getElementById('statusBadge');

      if (data.status === 'ESP_ONLINE') {
        badge.innerText = 'Online | MAC: ' + data.mac;
        badge.classList.add('online');
      } else if (data.status === 'ESP_OFFLINE') {
        badge.innerText = 'Target ESP32 Offline';
        badge.classList.remove('online');
      }

      if (data.state) {
        updateButtonUI(data.state);
      }
      if (data.msg) {
        document.getElementById('log').innerText = data.msg;
      }
    };

    function toggleSwitch() {
      ws.send(JSON.stringify({ type: 'TOGGLE', pin: 21 }));
    }
  </script>
</body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(html_page)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global current_state
    await websocket.accept()
    client_mac = None
    is_web = False

    try:
        while True:
            data = json.loads(await websocket.receive_text())

            if data.get("type") == "WEB_CLIENT":
                is_web = True
                web_clients.add(websocket)
                # Naye browser ko current online status aur current ON/OFF state bhejein
                status = "ESP_ONLINE" if ALLOWED_MAC in connected_devices else "ESP_OFFLINE"
                await websocket.send_text(json.dumps({
                    "status": status,
                    "mac": ALLOWED_MAC,
                    "state": current_state
                }))

            elif data.get("type") == "REGISTER":
                mac = data.get("mac", "").upper()
                if mac != ALLOWED_MAC.upper():
                    print(f"[BLOCKED] Unknown MAC tried to connect: {mac}")
                    await websocket.close()
                    return
                
                client_mac = mac
                connected_devices[client_mac] = websocket
                print(f"[VERIFIED] ESP32 Connected via MAC: {client_mac}")
                
                # Reconnect hone par ESP32 ko last state sync karein
                await websocket.send_text(json.dumps({"pin": 21, "state": current_state}))
                
                for client in web_clients:
                    await client.send_text(json.dumps({
                        "status": "ESP_ONLINE",
                        "mac": client_mac,
                        "state": current_state
                    }))

            # Single Toggle Command: ON ko OFF aur OFF ko ON karega
            elif data.get("type") == "TOGGLE":
                if ALLOWED_MAC in connected_devices:
                    current_state = "OFF" if current_state == "ON" else "ON"
                    
                    await connected_devices[ALLOWED_MAC].send_text(json.dumps({
                        "pin": 21,
                        "state": current_state
                    }))
                    
                    # Sabhi connected browsers ko live update bhejein
                    for client in web_clients:
                        await client.send_text(json.dumps({
                            "state": current_state,
                            "msg": f"Switched D21 -> {current_state}"
                        }))
                else:
                    await websocket.send_text(json.dumps({
                        "msg": f"Error: MAC {ALLOWED_MAC} offline hai!"
                    }))

    except WebSocketDisconnect:
        if is_web:
            web_clients.discard(websocket)
        if client_mac in connected_devices:
            del connected_devices[client_mac]
            print(f"[DISCONNECTED] MAC: {client_mac}")
            for client in web_clients:
                await client.send_text(json.dumps({"status": "ESP_OFFLINE"}))