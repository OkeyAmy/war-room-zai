import urllib.request
import urllib.error
import json
import sys

print("Creating session...")
req = urllib.request.Request("http://localhost:8000/api/sessions", method="POST", headers={"Content-Type": "application/json"}, data=b'{"crisis_input": "Test crisis", "session_duration_minutes": 30, "chairman_name": "TEST"}')
try:
    with urllib.request.urlopen(req, timeout=5) as response:
        data = json.loads(response.read().decode())
        session_id = data["session_id"]
        token = data["chairman_token"]
except Exception as e:
    print("Failed to create session:", e)
    sys.exit(1)

print(f"Session {session_id} created.")

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

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

for url, method, payload in endpoints:
    full_url = f"http://localhost:8000{url}"
    data_bytes = json.dumps(payload).encode() if payload is not None else None
    
    req = urllib.request.Request(full_url, method=method, headers=headers, data=data_bytes)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            print(f"{method} {url}: {response.status}")
    except urllib.error.HTTPError as e:
        print(f"{method} {url}: {e.code} {e.reason}")
        error_msg = e.read().decode()
        print(f"  Error: {error_msg}")
    except Exception as e:
        print(f"{method} {url}: {e}")
