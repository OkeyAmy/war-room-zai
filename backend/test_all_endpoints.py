import sys
import os
sys.path.append(os.getcwd())
import logging

from fastapi.testclient import TestClient
from main import app

# Silence uvicorn/fastapi logs to focus on errors
logging.getLogger("uvicorn").setLevel(logging.CRITICAL)

client = TestClient(app)

print("Creating session...")
resp = client.post("/api/sessions", json={"crisis_input": "Test crisis", "session_duration_minutes": 30, "chairman_name": "TEST"})
print(f"POST /api/sessions: {resp.status_code}")
if resp.status_code != 201:
    print(resp.text)
    sys.exit(1)

data = resp.json()
session_id = data["session_id"]
token = data["chairman_token"]
headers = {"Authorization": f"Bearer {token}"}

endpoints = [
    (f"/api/sessions/{session_id}", "GET", None),
    (f"/api/sessions/{session_id}/agents", "GET", None),
    (f"/api/sessions/{session_id}/board", "GET", None),
    (f"/api/sessions/{session_id}/feed", "GET", None),
    (f"/api/sessions/{session_id}/intel", "GET", None),
    (f"/api/sessions/{session_id}/intel/trust", "GET", None),
    (f"/api/sessions/{session_id}/posture", "GET", None),
    (f"/api/sessions/{session_id}/score", "GET", None),
    (f"/api/sessions/{session_id}/chairman/command", "POST", {"text": "hello"}),
    (f"/api/sessions/{session_id}/voice/token", "POST", {}),
    (f"/api/sessions/{session_id}/voice/status", "GET", None),
]

print("Testing endpoints...")
for url, method, payload in endpoints:
    if method == "GET":
        r = client.get(url, headers=headers)
    else:
        r = client.post(url, headers=headers, json=payload)
    
    print(f"{method} {url}: {r.status_code}")
    if r.status_code >= 400:
        print(f"  Error: {r.text}")
