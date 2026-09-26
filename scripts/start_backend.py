import subprocess
import sys
import os
import time
import urllib.request

root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
common_path = os.path.join(root, "services", "common")

env = os.environ.copy()
pythonpath = f"{root};{common_path};" + env.get("PYTHONPATH", "")
env["PYTHONPATH"] = pythonpath
env["ATLAS_DATABASE_URL"] = f"sqlite:///{root.replace('\\', '/')}/atlas.db"
env["ATLAS_REQUIRE_AUTH"] = "0"

services = [
    {"name": "risk-model", "dir": "services/risk-model", "app": "app.main:app", "port": 8000},
    {"name": "finance-service", "dir": "services/finance-service", "app": "app.main:app", "port": 8001},
    {"name": "scheduling-service", "dir": "services/scheduling-service", "app": "app.main:app", "port": 8002},
    {"name": "mcp-server", "dir": "mcp-server", "app": "atlas_mcp_server.server:app", "port": 8003},
]

processes = []
for s in services:
    cwd = os.path.join(root, s["dir"])
    cmd = [sys.executable, "-m", "uvicorn", s["app"], "--port", str(s["port"]), "--host", "127.0.0.1"]
    print(f"Starting {s['name']} on :{s['port']}...")
    p = subprocess.Popen(cmd, cwd=cwd, env=env)
    processes.append((s, p))

time.sleep(6)

for s in services:
    url = f"http://127.0.0.1:{s['port']}/health"
    try:
        req = urllib.request.urlopen(url, timeout=3)
        print(f"[OK] {s['name']} is live on port {s['port']}: {req.read().decode().strip()}")
    except Exception as e:
        print(f"[WARN] {s['name']} health check failed: {e}")

try:
    while True:
        time.sleep(10)
except KeyboardInterrupt:
    for s, p in processes:
        p.terminate()
