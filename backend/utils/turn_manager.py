"""
WAR ROOM — Turn Manager
Session-level coordinator that ensures agents speak one at a time.

KEY BEHAVIOR:
  - When an agent's audio arrives and the floor is taken, we IMMEDIATELY
    drop the response (return False instantly) instead of waiting.
    This eliminates delays and prevents voice overlap.
  - try_acquire_turn: properly awaits the lock — no optimistic returns.
  - Emits turn_started / turn_ended events so frontend can gate audio.
  - Inter-turn cooldown prevents rapid re-acquisition.
  - Chairman interrupt: forces immediate floor release within 2s max.
  - Session end: terminates all speech immediately.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class TurnManager:
    """One instance per session.  Shared by all CrisisAgent objects."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._lock = asyncio.Lock()
        self._current_speaker: Optional[str] = None
        self._chairman_interrupt = asyncio.Event()
        self._session_ended = asyncio.Event()
        self._turn_start_time: float = 0
        # Inter-turn cooldown — prevents rapid re-acquisition
        self._cooldown_until: float = 0
        # Max seconds one agent may speak (safety valve — Gemini usually ends turns)
        # Allow fuller arguments before automatic yield; Chairman interrupt
        # still preempts immediately.
        self.max_turn_seconds: float = 75.0

    # ── Properties ───────────────────────────────────────────────────

    @property
    def current_speaker(self) -> Optional[str]:
        return self._current_speaker

    def is_floor_free(self) -> bool:
        return not self._lock.locked()

    def is_speaking(self, agent_id: str) -> bool:
        return self._current_speaker == agent_id

    def is_session_ended(self) -> bool:
        return self._session_ended.is_set()

    # ── Acquire (blocking with generous timeout for chairman-addressed agents) ──

    async def acquire_turn(self, agent_id: str, timeout: float = 20.0) -> bool:
        """
        Block until this agent can speak (or *timeout* seconds elapse).
        For AUTONOMOUS turns, use try_acquire_turn instead.
        Returns True if acquired, False on timeout / session-ended.
        """
        if self._session_ended.is_set():
            return False

        # Respect inter-turn cooldown
        cooldown_remaining = self._cooldown_until - time.monotonic()
        if cooldown_remaining > 0:
            await asyncio.sleep(cooldown_remaining)

        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.debug(
                f"[TURN] {agent_id} timed out waiting for floor "
                f"(held by {self._current_speaker})"
            )
            return False

        self._current_speaker = agent_id
        self._turn_start_time = time.monotonic()
        self._chairman_interrupt.clear()
        logger.info(f"[TURN] {agent_id} acquired the floor")

        # Emit turn_started event for frontend gating
        await self._emit_turn_started(agent_id)
        return True

    async def try_acquire_turn(self, agent_id: str) -> bool:
        """
        Non-blocking: acquire only if floor is free right now.
        Used by _receive_from_gemini for autonomous (non-prompted) audio.
        Returns True if acquired, False immediately if busy.

        IMPORTANT: This is now a proper coroutine — callers must await it.
        The old implementation returned True optimistically before the lock
        was actually acquired, allowing multiple agents through concurrently.
        """
        if self._session_ended.is_set():
            return False

        # Check cooldown — prevents rapid re-acquisition after a turn ends
        if time.monotonic() < self._cooldown_until:
            logger.debug(
                f"[TURN] {agent_id} skipped — cooldown active"
            )
            return False

        if self._lock.locked():
            # Floor busy — drop this turn immediately (no waiting)
            logger.debug(
                f"[TURN] {agent_id} dropping autonomous audio "
                f"(floor held by {self._current_speaker})"
            )
            return False

        # Floor appears free — acquire with a very short timeout.
        # In single-threaded asyncio this should succeed immediately,
        # but the timeout guards against edge cases.
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=0.2)
        except asyncio.TimeoutError:
            logger.debug(
                f"[TURN] {agent_id} lost race for floor"
            )
            return False

        self._current_speaker = agent_id
        self._turn_start_time = time.monotonic()
        self._chairman_interrupt.clear()
        logger.info(f"[TURN] {agent_id} acquired the floor (try-acquire)")

        # Emit turn_started event for frontend gating
        await self._emit_turn_started(agent_id)
        return True

    def release_turn(self, agent_id: str) -> None:
        """Release the floor. Safe to call even if not holding it."""
        if self._current_speaker != agent_id:
            return  # not holding the lock
        self._current_speaker = None
        # Set cooldown to prevent immediate re-acquisition
        self._cooldown_until = time.monotonic() + 0.3
        try:
            self._lock.release()
        except RuntimeError:
            pass  # already released
        logger.info(f"[TURN] {agent_id} released the floor")

        # Emit turn_ended event for frontend — fire-and-forget
        asyncio.ensure_future(self._emit_turn_ended(agent_id))

    # ── Chairman priority ────────────────────────────────────────────

    async def chairman_interrupt(self) -> None:
        """
        Signal the current speaker to yield immediately and wait up to 2s.
        The chairman's addressed agent acquires normally after.
        """
        if not self._lock.locked():
            return  # floor already free, nothing to do

        speaker = self._current_speaker
        logger.info(f"[TURN] Chairman interrupt — forcing {speaker} to yield")
        self._chairman_interrupt.set()

        # Wait up to 2s for the holder to release
        for _ in range(10):
            if not self._lock.locked():
                break
            await asyncio.sleep(0.2)

        # Force-release if still held
        if self._lock.locked():
            logger.warning("[TURN] Force-releasing lock after chairman interrupt")
            self._current_speaker = None
            try:
                self._lock.release()
            except RuntimeError:
                pass

    def should_yield(self, agent_id: str) -> bool:
        """
        True when the agent should stop speaking immediately.
        Checked every audio chunk.
        """
        if self._session_ended.is_set():
            return True
        # If floor ownership moved to another agent, current agent must stop
        # streaming immediately to prevent overlapping voices.
        if self._current_speaker and self._current_speaker != agent_id:
            return True
        if self._chairman_interrupt.is_set():
            return True
        if (
            self._current_speaker == agent_id
            and time.monotonic() - self._turn_start_time > self.max_turn_seconds
        ):
            logger.info(
                f"[TURN] {agent_id} exceeded max turn duration "
                f"({self.max_turn_seconds}s) — yielding"
            )
            return True
        return False

    # ── Session end ──────────────────────────────────────────────────

    async def end_session(self) -> None:
        """
        Called when the session is closed or timer expires.
        Forces all agents to stop speaking immediately.
        """
        logger.info(f"[TURN] Session {self.session_id} ended — releasing all turns")
        self._session_ended.set()
        self._chairman_interrupt.set()  # trigger any current speaker to yield
        # Force-release the lock if held
        if self._lock.locked():
            self._current_speaker = None
            try:
                self._lock.release()
            except RuntimeError:
                pass

    # ── Event emission helpers ─────────────────────────────────────────

    async def _emit_turn_started(self, agent_id: str) -> None:
        """Push turn_started event so frontend sets activeSpeaker gate."""
        try:
            from utils.events import push_event_direct
            await push_event_direct(
                self.session_id,
                "turn_started",
                {
                    "agent_id": agent_id,
                    "turn_start_time": time.monotonic(),
                },
                source_agent_id=agent_id,
            )
        except Exception as e:
            logger.warning(f"[TURN] Failed to emit turn_started: {e}")

    async def _emit_turn_ended(self, agent_id: str) -> None:
        """Push turn_ended event so frontend clears activeSpeaker gate."""
        try:
            from utils.events import push_event_direct
            await push_event_direct(
                self.session_id,
                "turn_ended",
                {
                    "agent_id": agent_id,
                },
                source_agent_id=agent_id,
            )
        except Exception as e:
            logger.warning(f"[TURN] Failed to emit turn_ended: {e}")


# ── Registry (one TurnManager per session) ───────────────────────────

_managers: dict[str, TurnManager] = {}


def get_turn_manager(session_id: str) -> TurnManager:
    """Get (or create) the TurnManager for a session."""
    if session_id not in _managers:
        _managers[session_id] = TurnManager(session_id)
    return _managers[session_id]


def remove_turn_manager(session_id: str) -> None:
    """Clean up when session closes."""
    _managers.pop(session_id, None)
