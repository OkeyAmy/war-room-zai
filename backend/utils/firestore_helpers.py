"""
WAR ROOM — Firestore Helper Utilities
Score updates, posture updates, threat level checks, and broadcast helpers.

STORAGE STRATEGY:
  ENVIRONMENT=development  →  LocalDevDB  (data/ directory tree, JSON files)
  ENVIRONMENT=production   →  google.cloud.firestore.AsyncClient

Both expose the same .collection().document().get/set/update() interface
so no other code needs to know which backend is active.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from config.constants import (
    COLLECTION_CRISIS_SESSIONS,
    THREAT_LEVEL_THRESHOLDS,
    THREAT_CONTAINED,
    THREAT_ELEVATED,
    THREAT_CRITICAL,
    THREAT_MELTDOWN,
    EVENT_POSTURE_UPDATE,
    EVENT_SCORE_UPDATE,
    EVENT_THREAT_LEVEL_CHANGE,
)

logger = logging.getLogger(__name__)

# ── CLIENT FACTORY ───────────────────────────────────────────────────────

_db = None


def _get_db():
    """
    Lazy-init the correct storage backend based on ENVIRONMENT setting.

    development → LocalDevDB  (data/ directory, JSON files)
    production  → google.cloud.firestore.AsyncClient
    """
    global _db
    if _db is None:
        from config.settings import get_settings
        settings = get_settings()

        if settings.environment == "production":
            try:
                from google.cloud import firestore
                _db = firestore.AsyncClient()
                logger.info("Storage: Firestore (production)")
            except ImportError:
                logger.warning(
                    "google-cloud-firestore not installed — falling back to dev store"
                )
                _db = _make_dev_db()
            except Exception as e:
                logger.error(f"Firestore init failed: {e} — falling back to dev store")
                _db = _make_dev_db()
        else:
            _db = _make_dev_db()

    return _db


def _make_dev_db():
    """Create and log the LocalDevDB instance."""
    from utils.local_storage import LocalDevDB
    db = LocalDevDB()
    logger.info("Storage: LocalDevDB (development) — data/ directory tree")
    return db


def reset_db():
    """Reset the singleton (useful in tests)."""
    global _db
    _db = None


# ── POSTURE UPDATE ───────────────────────────────────────────────────────


async def update_posture(session_id: str, posture_impact: dict) -> dict:
    """
    Apply posture deltas and push a posture_update event.
    Returns the new posture values.
    """
    from utils.events import push_event

    db = _get_db()
    doc = await db.collection(COLLECTION_CRISIS_SESSIONS) \
                  .document(session_id).get()

    if not doc.exists:
        logger.warning(f"Session {session_id} not found for posture update")
        return {}

    crisis = doc.to_dict()
    posture = crisis.get("posture", {})

    new_posture: dict = {
        "public_exposure": max(0, min(100,
            posture.get("public_exposure", 60)
            + posture_impact.get("public_exposure_delta", 0)
        )),
        "legal_exposure": max(0, min(100,
            posture.get("legal_exposure", 45)
            + posture_impact.get("legal_exposure_delta", 0)
        )),
        "internal_stability": max(0, min(100,
            posture.get("internal_stability", 50)
            + posture_impact.get("internal_stability_delta", 0)
        )),
    }

    # Compute trends
    for key, delta_key, trend_key in [
        ("public_exposure",    "public_exposure_delta",    "public_trend"),
        ("legal_exposure",     "legal_exposure_delta",     "legal_trend"),
        ("internal_stability", "internal_stability_delta", "internal_trend"),
    ]:
        delta = posture_impact.get(delta_key, 0)
        if delta > 0:
            new_posture[trend_key] = "rising"
        elif delta < 0:
            new_posture[trend_key] = "falling"
        else:
            new_posture[trend_key] = posture.get(trend_key, "stable")

    await db.collection(COLLECTION_CRISIS_SESSIONS) \
            .document(session_id) \
            .update({"posture": new_posture})

    await push_event(session_id, EVENT_POSTURE_UPDATE, new_posture)
    return new_posture


# ── RESOLUTION SCORE ─────────────────────────────────────────────────────


async def update_resolution_score(
    session_id: str,
    delta: int,
    driver: str,
) -> int:
    """
    Apply a delta to the resolution score and push a score_update event.
    Returns the new score.
    """
    from utils.events import push_event

    db = _get_db()
    doc = await db.collection(COLLECTION_CRISIS_SESSIONS) \
                  .document(session_id).get()

    if not doc.exists:
        logger.warning(f"Session {session_id} not found for score update")
        return 0

    crisis = doc.to_dict()
    current_score = crisis.get("resolution_score", 50)
    score_history = crisis.get("score_history", [50])

    new_score = max(0, min(100, current_score + delta))
    score_history.append(new_score)
    score_history = score_history[-20:]  # keep last 20 for sparkline

    threat_level = _calculate_threat_level(new_score)

    await db.collection(COLLECTION_CRISIS_SESSIONS) \
            .document(session_id) \
            .update({
                "resolution_score": new_score,
                "score_history": score_history,
                "threat_level": threat_level,
            })

    await push_event(session_id, EVENT_SCORE_UPDATE, {
        "score": new_score,
        "delta": delta,
        "score_history": score_history,
        "threat_level": threat_level,
        "driver": driver,
    })

    return new_score


def _calculate_threat_level(score: int) -> str:
    if score < THREAT_LEVEL_THRESHOLDS[THREAT_MELTDOWN]:
        return THREAT_MELTDOWN
    elif score < THREAT_LEVEL_THRESHOLDS[THREAT_CRITICAL]:
        return THREAT_CRITICAL
    elif score < THREAT_LEVEL_THRESHOLDS[THREAT_ELEVATED]:
        return THREAT_ELEVATED
    return THREAT_CONTAINED


# ── THREAT LEVEL CHECK ───────────────────────────────────────────────────


async def check_threat_level(session_id: str) -> Optional[str]:
    """
    Check if threat level changed after a score update.
    If changed, push a threat_level_change event.
    Returns new threat level if changed, else None.
    """
    from utils.events import push_event

    db = _get_db()
    doc = await db.collection(COLLECTION_CRISIS_SESSIONS) \
                  .document(session_id).get()

    if not doc.exists:
        return None

    crisis = doc.to_dict()
    current_threat = crisis.get("threat_level", THREAT_ELEVATED)
    score = crisis.get("resolution_score", 50)
    new_threat = _calculate_threat_level(score)

    if new_threat != current_threat:
        await db.collection(COLLECTION_CRISIS_SESSIONS) \
                .document(session_id) \
                .update({"threat_level": new_threat})

        await push_event(session_id, EVENT_THREAT_LEVEL_CHANGE, {
            "previous": current_threat,
            "current": new_threat,
        })

        logger.info(
            f"Threat level changed: {current_threat} → {new_threat} "
            f"(score={score}) for session {session_id}"
        )
        return new_threat

    return None


# ── ESCALATION HELPERS ───────────────────────────────────────────────────


def compute_next_escalation(
    escalation_schedule: list[dict],
    session_start: Optional[datetime] = None,
) -> Optional[str]:
    """
    Compute the timestamp of the next escalation event.
    Returns ISO timestamp string or None.
    """
    if not escalation_schedule:
        return None

    from datetime import timedelta
    start = session_start or datetime.now(timezone.utc)
    soonest = None
    for event in escalation_schedule:
        event_time = start + timedelta(minutes=event["delay_minutes"])
        if soonest is None or event_time < soonest:
            soonest = event_time

    return soonest.isoformat() if soonest else None


# ── BROADCAST TO AGENTS ─────────────────────────────────────────────────


async def broadcast_to_agents(session_id: str, message: dict) -> None:
    """
    Broadcast a message to all agents in a session.
    Pub/Sub in production; logged locally in dev.
    """
    logger.info(
        f"Broadcasting to agents in session {session_id}: "
        f"{message.get('type', 'unknown')}"
    )
    # Production: publish to Pub/Sub topic
    # publisher = pubsub_v1.PublisherClient()
    # topic_path = publisher.topic_path(project_id, topic_name)
    # publisher.publish(topic_path, json.dumps(message).encode())
