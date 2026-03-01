"""
WAR ROOM — Authentication Helpers
Validates chairman_token from the Authorization: Bearer header.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

security = HTTPBearer()


async def get_chairman_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    FastAPI dependency: extracts the Bearer token from the Authorization header.
    Raises 403 if no token is provided.
    """
    if not credentials:
        raise HTTPException(status_code=403, detail="Missing Authorization header")

    return credentials.credentials


async def validate_chairman_token(session_id: str, token: str) -> dict:
    """
    Validate that the given token matches the chairman_token stored
    in the crisis_sessions Firestore document.

    Returns the session document dict if valid.
    Raises 403 if token mismatch, 404 if session not found.
    """
    from utils.firestore_helpers import _get_db
    from config.constants import COLLECTION_CRISIS_SESSIONS

    db = _get_db()
    doc = await db.collection(COLLECTION_CRISIS_SESSIONS).document(session_id).get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="session_not_found")

    session_data = doc.to_dict()
    stored_token = session_data.get("chairman_token", "")

    if stored_token != token:
        raise HTTPException(status_code=403, detail="invalid_chairman_token")

    return session_data
