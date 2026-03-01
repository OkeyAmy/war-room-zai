"""
WAR ROOM — Observer Agent
Silent agent — no voice, no speaking. Watches all transcripts and
Firestore state. Outputs insights (contradictions, alliances, blind spots)
and trust score adjustments.
"""

from __future__ import annotations

import json
import uuid
import logging
from typing import Optional

from config.settings import get_settings
from config.constants import (
    COLLECTION_AGENT_MEMORY,
    COLLECTION_CRISIS_SESSIONS,
    EVENT_TRUST_SCORE_UPDATE,
    EVENT_OBSERVER_INSIGHT,
)

logger = logging.getLogger(__name__)

# ── SYSTEM INSTRUCTION ───────────────────────────────────────────────────

OBSERVER_INSTRUCTION = """
You are the Observer Agent in WAR ROOM. You have no voice.
You watch everything. You output structured analysis only.

You receive:
- A recent agent statement (transcript)
- The agent's previous public positions (from their Firestore record)
- The current crisis board state
- The current resolution score

You output a JSON object with this structure:
{
  "trust_delta": number,              // -20 to +10 per statement
  "trust_reason": string,             // one-line explanation
  "insight_type": "contradiction" | "alliance" | "blind_spot" | "mood_shift" | null,
  "insight_title": string | null,
  "insight_body": string | null,
  "agents_referenced": [string],
  "posture_impact": {
    "public_exposure_delta": number,  // -10 to +10
    "legal_exposure_delta": number,
    "internal_stability_delta": number
  },
  "resolution_score_delta": number,   // -5 to +5
  "new_decisions": [
    {
      "text": "Decision text",
      "agents_agreed": ["agent1", "agent2"]
    }
  ],
  "new_conflicts": [
    {
      "description": "Conflict description",
      "agents_involved": ["agent1", "agent2"],
      "severity": "low" | "medium" | "high" | "critical"
    }
  ],
  "new_intel": [
    {
      "text": "Intel text",
      "source": "WORLD|MEDIA|LEGAL|INTERNAL|SOCIAL",
      "is_escalation": boolean
    }
  ]
}

Rules:
- CONTRADICTION: trust_delta should be -10 to -20.
  Triggered when the agent says something inconsistent with previous positions.
- ALLIANCE: trust_delta +3 to +5 for both agents.
  Triggered when two agents align on a position.
- BLIND_SPOT: no trust impact, but posture impact.
  Something nobody is addressing that could escalate.
- MOOD_SHIFT: subtle — the room's tone has changed.
  May affect internal_stability.
- WORLD MODEL UPDATES: Extract any newly formed Agreed Decisions, Open Conflicts, or Critical Intel from the transcript. Only include these if they are NEWLY established in this specific transcript chunk. Do not repeat existing ones.
- If no insight is warranted, set insight_type to null.
- Be precise. One insight per analysis, or none.
- Output ONLY the JSON object. No explanatory text.
"""


class ObserverAgent:
    """
    Silent observer — watches all transcripts, detects contradictions,
    alliances, blind spots, and mood shifts. Updates trust scores and
    crisis posture.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id

        # Firestore client
        self._db = None

        # ADK components (optional — works without ADK for local dev)
        self.session_service = None
        self.llm = None
        self.runner = None

        self._initialized = False

    @property
    def db(self):
        if self._db is None:
            from utils.firestore_helpers import _get_db
            self._db = _get_db()
        return self._db

    def _ensure_initialized(self):
        """Lazy-init ADK components."""
        if self._initialized:
            return

        try:
            from google.adk.agents import LlmAgent
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService

            settings = get_settings()
            self.session_service = InMemorySessionService()

            self.llm = LlmAgent(
                name="ObserverAgent",
                model=settings.text_model,
                instruction=OBSERVER_INSTRUCTION,
            )

            self.runner = Runner(
                agent=self.llm,
                app_name=f"observer_{self.session_id}",
                session_service=self.session_service,
            )

        except ImportError:
            logger.warning("ADK not available — Observer in local-dev mode")

        self._initialized = True

    async def start_watching(self):
        """Start the Observer's Firestore listener (called at session boot)."""
        self._ensure_initialized()
        logger.info(f"Observer Agent watching session {self.session_id}")

    async def analyze_statement(
        self,
        session_id: str,
        agent_id: str,
        transcript: str,
    ) -> Optional[dict]:
        """
        Runs after every agent turn.
        Produces trust score updates + room intelligence insights.

        Args:
            session_id: The crisis session ID.
            agent_id: The agent who just spoke.
            transcript: What the agent said.

        Returns:
            The Observer's analysis dict, or None if ADK unavailable.
        """
        from utils.events import push_event
        from utils.firestore_helpers import update_posture, update_resolution_score

        self._ensure_initialized()

        # Gather context (READ ONLY)
        memory_doc = await self.db.collection(COLLECTION_AGENT_MEMORY) \
                                  .document(f"{agent_id}_{session_id}").get()
        crisis_doc = await self.db.collection(COLLECTION_CRISIS_SESSIONS) \
                                  .document(session_id).get()

        memory = memory_doc.to_dict() if memory_doc.exists else {}
        crisis = crisis_doc.to_dict() if crisis_doc.exists else {}

        # Run Observer LLM analysis
        output = None
        if self.runner:
            try:
                from google.genai import types

                # runner.run_async() returns an AsyncGenerator — iterate events
                # Create session first — ADK requires it to exist
                observer_session_id = f"observer_{session_id}_{agent_id}"
                try:
                    await self.session_service.create_session(
                        app_name=f"observer_{self.session_id}",
                        user_id="system",
                        session_id=observer_session_id,
                    )
                except Exception as e:
                    # Reuse existing ADK observer session if it already exists.
                    if "already exists" not in str(e).lower():
                        raise

                final_response_text = ""
                async for event in self.runner.run_async(
                    user_id="system",
                    session_id=observer_session_id,
                    new_message=types.Content(
                        role="user",
                        parts=[types.Part(text=json.dumps({
                            "agent_id": agent_id,
                            "new_statement": transcript,
                            "previous_positions": memory.get("public_positions", {}),
                            "crisis_board": {
                                "agreed": crisis.get("agreed_decisions", []),
                                "conflicts": crisis.get("open_conflicts", []),
                            },
                            "current_resolution_score": crisis.get("resolution_score", 50),
                        }))]
                    ),
                ):
                    if event.is_final_response() and event.content and event.content.parts:
                        final_response_text = event.content.parts[0].text

                if final_response_text:
                    output = json.loads(final_response_text)
                else:
                    output = self._generate_default_analysis(transcript, agent_id)

            except Exception as e:
                logger.warning(f"Observer LLM analysis failed: {e}")
                output = self._generate_default_analysis(transcript, agent_id)
        else:
            output = self._generate_default_analysis(transcript, agent_id)

        if not output:
            return None

        # Push trust score update
        trust_delta = output.get("trust_delta", 0)
        if trust_delta != 0:
            roster = crisis.get("agent_roster", [])
            updated = False
            for agent in roster:
                if agent.get("agent_id") == agent_id:
                    current_score = agent.get("trust_score", 70)
                    new_score = max(0, min(100, current_score + trust_delta))
                    agent["trust_score"] = new_score
                    agent["trust_delta"] = trust_delta
                    agent["trust_reason"] = output.get("trust_reason", "")
                    updated = True

                    await push_event(session_id, EVENT_TRUST_SCORE_UPDATE, {
                        "agent_id": agent_id,
                        "score": new_score,
                        "delta": trust_delta,
                        "reason": output.get("trust_reason", ""),
                    })
                    break
            
            if updated:
                await self.db.collection(COLLECTION_CRISIS_SESSIONS) \
                             .document(session_id) \
                             .update({"agent_roster": roster})

        # Push insight if generated
        if output.get("insight_type"):
            insight_id = str(uuid.uuid4())
            insight_obj = {
                "insight_id": insight_id,
                "type": output["insight_type"],
                "title": output.get("insight_title", ""),
                "body": output.get("insight_body", ""),
                "agents_referenced": output.get("agents_referenced", []),
            }
            
            try:
                from google.cloud import firestore as fs
                await self.db.collection(COLLECTION_CRISIS_SESSIONS) \
                             .document(session_id) \
                             .update({"observer_insights": fs.ArrayUnion([insight_obj])})
            except ImportError:
                # Local dev mock fallback
                insights = crisis.get("observer_insights", [])
                insights.append(insight_obj)
                await self.db.collection(COLLECTION_CRISIS_SESSIONS) \
                             .document(session_id) \
                             .update({"observer_insights": insights})

            await push_event(session_id, EVENT_OBSERVER_INSIGHT, insight_obj)

        # Update posture
        posture_impact = output.get("posture_impact", {})
        if any(v != 0 for v in posture_impact.values()):
            await update_posture(session_id, posture_impact)

        # Update resolution score
        score_delta = output.get("resolution_score_delta", 0)
        if score_delta != 0:
            await update_resolution_score(
                session_id, score_delta, "Agent statement impact"
            )

        # Process new decisions, conflicts, intel
        if output.get("new_decisions") or output.get("new_conflicts") or output.get("new_intel"):
            try:
                from tools.crisis_board_tools import (
                    write_agreed_decision, write_open_conflict, write_critical_intel
                )
                
                for decision in output.get("new_decisions", []):
                    await write_agreed_decision(
                        session_id=session_id,
                        agent_id="observer",
                        text=decision.get("text", ""),
                        agents_agreed=decision.get("agents_agreed", [])
                    )
                
                for conflict in output.get("new_conflicts", []):
                    await write_open_conflict(
                        session_id=session_id,
                        agent_id="observer",
                        description=conflict.get("description", ""),
                        agents_involved=conflict.get("agents_involved", []),
                        severity=conflict.get("severity", "medium")
                    )
                
                for intel in output.get("new_intel", []):
                    await write_critical_intel(
                        session_id=session_id,
                        agent_id="observer",
                        text=intel.get("text", ""),
                        source=intel.get("source", "INTERNAL"),
                        is_escalation=intel.get("is_escalation", False)
                    )
            except Exception as e:
                logger.error(f"Failed to process world model updates from observer: {e}")

        return output

    def _generate_default_analysis(
        self, transcript: str, agent_id: str
    ) -> dict:
        """Default analysis when LLM is not available."""
        return {
            "trust_delta": 0,
            "trust_reason": "Analysis unavailable (local dev mode)",
            "insight_type": None,
            "insight_title": None,
            "insight_body": None,
            "agents_referenced": [agent_id],
            "posture_impact": {
                "public_exposure_delta": 0,
                "legal_exposure_delta": 0,
                "internal_stability_delta": 0,
            },
            "resolution_score_delta": 0,
            "new_decisions": [],
            "new_conflicts": [],
            "new_intel": [],
        }
