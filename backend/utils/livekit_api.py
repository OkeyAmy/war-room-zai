"""
WAR ROOM — LiveKit API Integration (backend-owned).

Uses LiveKit server APIs directly:
  - Access token generation (JWT with VideoGrant claims)
  - Room creation via RoomService/CreateRoom

Frontend should call WAR ROOM backend endpoints only; backend handles LiveKit.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from config.settings import get_settings

logger = logging.getLogger(__name__)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _sign_jwt(payload: dict[str, Any], api_key: str, api_secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_with_iss = {"iss": api_key, **payload}
    payload_b64 = _b64url(
        json.dumps(payload_with_iss, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(
        api_secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{header_b64}.{payload_b64}.{_b64url(signature)}"


def is_livekit_configured() -> bool:
    settings = get_settings()
    return bool(
        settings.livekit_url
        and settings.livekit_api_key
        and settings.livekit_api_secret
    )


def build_livekit_participant_token(
    room_name: str,
    identity: str,
    name: str,
    metadata: dict[str, Any] | None = None,
    ttl_seconds: int = 3600,
) -> str:
    """
    Build a LiveKit access token for room join.
    """
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": identity,
        "nbf": now - 5,
        "exp": now + ttl_seconds,
        "name": name,
        "metadata": json.dumps(metadata or {}),
        "video": {
            "room": room_name,
            "roomJoin": True,
            "canPublish": True,
            "canSubscribe": True,
            "canPublishData": True,
        },
    }
    return _sign_jwt(payload, settings.livekit_api_key, settings.livekit_api_secret)


def build_livekit_admin_token(ttl_seconds: int = 300) -> str:
    """
    Short-lived LiveKit admin token for RoomService calls.
    """
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": "war-room-backend",
        "nbf": now - 5,
        "exp": now + ttl_seconds,
        "video": {
            "roomCreate": True,
            "roomList": True,
            "roomAdmin": True,
        },
    }
    return _sign_jwt(payload, settings.livekit_api_key, settings.livekit_api_secret)


def _twirp_url(path: str) -> str:
    settings = get_settings()
    base = settings.livekit_url.rstrip("/")
    if base.startswith("wss://"):
        base = "https://" + base[len("wss://") :]
    elif base.startswith("ws://"):
        base = "http://" + base[len("ws://") :]
    return f"{base}/twirp/livekit.RoomService/{path}"


def ensure_livekit_room(
    room_name: str,
    metadata: dict[str, Any] | None = None,
    empty_timeout: int = 600,
) -> None:
    """
    Ensure room exists in LiveKit.
    """
    if not is_livekit_configured():
        return

    token = build_livekit_admin_token()
    body = {
        "name": room_name,
        "empty_timeout": empty_timeout,
        "metadata": json.dumps(metadata or {}),
    }
    req = urllib.request.Request(
        _twirp_url("CreateRoom"),
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            _ = resp.read()
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="ignore")
        except Exception:
            raw = ""
        # Room already exists is not fatal.
        if "already exists" in raw.lower():
            return
        logger.warning(f"LiveKit CreateRoom failed ({e.code}): {raw}")
        raise


def ping_livekit() -> tuple[bool, str]:
    """
    Connectivity check against LiveKit RoomService/ListRooms.
    Returns (ok, message).
    """
    if not is_livekit_configured():
        return False, "LiveKit env not configured"

    token = build_livekit_admin_token()
    body = {"names": []}
    req = urllib.request.Request(
        _twirp_url("ListRooms"),
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        return True, f"LiveKit reachable: {raw[:120]}"
    except Exception as e:
        return False, f"LiveKit ping failed: {e}"
