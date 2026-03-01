"""
WAR ROOM — Local Development Storage System
============================================

Mirrors the Firestore collection hierarchy as a directory tree under /data/.
Every write is immediately flushed to disk so you can inspect live data
in VS Code (JSON files with collapsible trees).

DIRECTORY STRUCTURE:
  data/
  ├── crisis_sessions/
  │   └── {session_id}/
  │       └── session.json             ← shared session state
  │
  ├── agent_memory/
  │   └── {agent_id}_{session_id}/
  │       └── memory.json              ← per-agent private memory (ISOLATED)
  │
  ├── agent_skills/
  │   └── {session_id}_{agent_id}/
  │       └── skill.json               ← generated skill context
  │
  ├── session_events/
  │   └── {session_id}/
  │       └── events/
  │           └── {event_id}.json      ← one file per event (append-only)
  │
  └── _dev_log/
      └── {session_id}.ndjson          ← newline-delimited JSON log
                                          (tail -f to see everything live)

PRODUCTION SWAP:
  When ENVIRONMENT=production, the application uses the real
  google.cloud.firestore.AsyncClient instead of this class.
  The interface is identical — no other code needs to change.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── DATA ROOT ────────────────────────────────────────────────────────────

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"

# Filename convention per collection
_COLLECTION_FILENAMES = {
    "crisis_sessions": "session.json",
    "agent_memory": "memory.json",
    "agent_skills": "skill.json",
    "session_events": "event.json",   # default; events sub-path overrides
}

_DEFAULT_FILENAME = "document.json"


def _doc_path(collection: str, doc_id: str) -> Path:
    """
    Resolve the JSON file path for a top-level document.
    e.g. crisis_sessions/A3F9B2C1/session.json
    """
    filename = _COLLECTION_FILENAMES.get(collection, _DEFAULT_FILENAME)
    return DATA_ROOT / collection / doc_id / filename


def _ensure(path: Path) -> None:
    """Create all parent directories if they don't exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> dict:
    """Read a JSON file; returns {} if missing or invalid."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(path: Path, data: Any) -> None:
    """Write data to disk as pretty-printed JSON, creating parents."""
    _ensure(path)
    path.write_text(
        json.dumps(data, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )


# ── DEV LOG ──────────────────────────────────────────────────────────────


def _append_dev_log(session_id: str, operation: str, path: str, data: dict) -> None:
    """Append a structured entry to _dev_log/{session_id}.ndjson."""
    log_dir = DATA_ROOT / "_dev_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{session_id}.ndjson"
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "op": operation,
        "path": path,
        "preview": _truncate_preview(data),
    }
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _truncate_preview(data: dict, max_keys: int = 5) -> dict:
    """Return a short preview of data for the dev log."""
    if not isinstance(data, dict):
        return {}
    keys = list(data.keys())[:max_keys]
    return {k: data[k] for k in keys}


# ── SNAPSHOT (mirrors Firestore DocumentSnapshot) ────────────────────────


class LocalSnapshot:
    """Mimics google.cloud.firestore.DocumentSnapshot."""

    def __init__(self, data: dict, path: str):
        self._data = data
        self._path = path
        self.exists = bool(data)

    def to_dict(self) -> dict:
        return dict(self._data)


# ── DOCUMENT REFERENCE ───────────────────────────────────────────────────


class LocalDocument:
    """
    Mimics google.cloud.firestore.AsyncDocumentReference.
    Supports: get(), set(), update(), collection().
    """

    def __init__(
        self,
        collection: str,
        doc_id: str,
        file_path: Path,
        session_id_for_log: Optional[str] = None,
    ):
        self._collection = collection
        self._doc_id = doc_id
        self._file_path = file_path
        self._session_id_for_log = session_id_for_log or doc_id

    # ── Read ─────────────────────────────────────────────────────────────

    async def get(self) -> LocalSnapshot:
        data = _read_json(self._file_path)
        return LocalSnapshot(data, str(self._file_path))

    # ── Write (full replace) ─────────────────────────────────────────────

    async def set(self, data: dict) -> None:
        _write_json(self._file_path, data)
        _append_dev_log(
            self._session_id_for_log, "SET",
            str(self._file_path.relative_to(DATA_ROOT)), data,
        )
        logger.debug(f"[DEV-STORE] SET {self._file_path.relative_to(DATA_ROOT)}")

    # ── Write (partial update) ────────────────────────────────────────────

    async def update(self, data: dict) -> None:
        existing = _read_json(self._file_path)
        merged = {**existing, **data}
        _write_json(self._file_path, merged)
        _append_dev_log(
            self._session_id_for_log, "UPDATE",
            str(self._file_path.relative_to(DATA_ROOT)), data,
        )
        logger.debug(f"[DEV-STORE] UPDATE {self._file_path.relative_to(DATA_ROOT)}")

    # ── Sub-collection ───────────────────────────────────────────────────

    def collection(self, sub_name: str) -> "LocalSubCollection":
        """Return a sub-collection handle (e.g. session_events/{id}/events)."""
        sub_dir = self._file_path.parent / sub_name
        return LocalSubCollection(
            parent_dir=sub_dir,
            collection_path=f"{self._collection}/{self._doc_id}/{sub_name}",
            session_id_for_log=self._session_id_for_log,
        )


# ── SUB-COLLECTION ───────────────────────────────────────────────────────


class LocalSubCollection:
    """
    Mimics a Firestore sub-collection (e.g. session_events/{id}/events).
    Documents in the sub-collection are stored as individual JSON files:
      data/session_events/{session_id}/events/{event_id}.json
    """

    def __init__(self, parent_dir: Path, collection_path: str, session_id_for_log: str):
        self._parent_dir = parent_dir
        self._collection_path = collection_path
        self._session_id_for_log = session_id_for_log

    def document(self, doc_id: str) -> "LocalSubDocument":
        file_path = self._parent_dir / f"{doc_id}.json"
        return LocalSubDocument(
            file_path=file_path,
            collection_path=self._collection_path,
            doc_id=doc_id,
            session_id_for_log=self._session_id_for_log,
        )

    def list_documents(self) -> list[Path]:
        """Return all document files in this sub-collection."""
        if not self._parent_dir.exists():
            return []
        return sorted(self._parent_dir.glob("*.json"))

    def get_all_events(self) -> list[dict]:
        """Read all events from disk (sorted by filename = event_id order)."""
        events = []
        for p in self.list_documents():
            data = _read_json(p)
            if data:
                events.append(data)
        return events


class LocalSubDocument:
    """A single document inside a LocalSubCollection."""

    def __init__(
        self,
        file_path: Path,
        collection_path: str,
        doc_id: str,
        session_id_for_log: str,
    ):
        self._file_path = file_path
        self._collection_path = collection_path
        self._doc_id = doc_id
        self._session_id_for_log = session_id_for_log

    async def get(self) -> LocalSnapshot:
        data = _read_json(self._file_path)
        return LocalSnapshot(data, str(self._file_path))

    async def set(self, data: dict) -> None:
        _ensure(self._file_path)
        _write_json(self._file_path, data)
        _append_dev_log(
            self._session_id_for_log, "SET",
            f"{self._collection_path}/{self._doc_id}.json", data,
        )
        logger.debug(
            f"[DEV-STORE] SET {self._collection_path}/{self._doc_id}.json"
        )

    async def update(self, data: dict) -> None:
        existing = _read_json(self._file_path)
        merged = {**existing, **data}
        _write_json(self._file_path, merged)
        _append_dev_log(
            self._session_id_for_log, "UPDATE",
            f"{self._collection_path}/{self._doc_id}.json", data,
        )


# ── TOP-LEVEL COLLECTION ─────────────────────────────────────────────────


class LocalCollection:
    """
    Mimics google.cloud.firestore.AsyncCollectionReference.
    """

    def __init__(self, name: str):
        self._name = name

    def document(self, doc_id: str) -> LocalDocument:
        file_path = _doc_path(self._name, doc_id)
        # Infer session_id from doc_id for logging purposes
        session_id = doc_id.split("_")[-1] if "_" in doc_id else doc_id
        return LocalDocument(
            collection=self._name,
            doc_id=doc_id,
            file_path=file_path,
            session_id_for_log=session_id,
        )

    def list_documents(self) -> list[str]:
        """Return all document IDs in this collection."""
        base = DATA_ROOT / self._name
        if not base.exists():
            return []
        return [d.name for d in base.iterdir() if d.is_dir()]


# ── ROOT CLIENT ──────────────────────────────────────────────────────────


class LocalDevDB:
    """
    Drop-in replacement for google.cloud.firestore.AsyncClient during development.
    Writes every document to data/{collection}/{doc_id}/ as a JSON file.

    Usage:
        db = LocalDevDB()
        await db.collection("crisis_sessions").document("A3F9B2C1").set({...})
        # → writes to data/crisis_sessions/A3F9B2C1/session.json
    """

    def collection(self, name: str) -> LocalCollection:
        return LocalCollection(name)

    def clear_session(self, session_id: str) -> None:
        """Remove all data directories for a given session (for test cleanup)."""
        targets = [
            DATA_ROOT / "crisis_sessions" / session_id,
            DATA_ROOT / "session_events" / session_id,
            DATA_ROOT / "_dev_log" / f"{session_id}.ndjson",
        ]
        # agent_memory and agent_skills use {agent}_{session_id} naming
        for collection in ["agent_memory", "agent_skills"]:
            base = DATA_ROOT / collection
            if base.exists():
                for d in base.iterdir():
                    if d.is_dir() and d.name.endswith(f"_{session_id}"):
                        targets.append(d)

        for target in targets:
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.is_file():
                target.unlink(missing_ok=True)
