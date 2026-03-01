"""
WAR ROOM — LiveKit AgentSession config builder.

Builds a normalized runtime payload used by:
1) backend orchestration (single active voice agent routing)
2) frontend/ops visibility (exact LiveKit pipeline parameters)
3) scenario + skill generation (instruction guide for voice behavior)
"""

from __future__ import annotations

from datetime import datetime, timezone


def build_scenario_instruction_guide(
    *,
    crisis_input: str,
    crisis_title: str,
    crisis_brief: str,
) -> str:
    """
    Returns the instruction guide used by the scenario pipeline before voice boot.

    This guide is stored on the session document so the full sequence is inspectable:
      user typed crisis -> scenario analyst -> single active voice agent -> livekit params.
    """
    created_at = datetime.now(timezone.utc).isoformat()
    return (
        "SCENARIO AGENT GUIDE (LIVEKIT MULTIMODAL)\n"
        f"Generated: {created_at}\n\n"
        "1) Accept user-typed crisis input verbatim.\n"
        "2) Produce ScenarioSpec JSON (title, brief, threats, intel, conflicts).\n"
        "3) Create four active speaking agents, each in an independent LiveKit pod.\n"
        "4) Generate SKILL instructions for each agent.\n"
        "5) Build LiveKit AgentSession parameters with STT-LLM-TTS pipeline:\n"
        "   - STT provider: ElevenLabs (scribe_v1)\n"
        "   - LLM provider: Gemini text model\n"
        "   - TTS provider: ElevenLabs\n"
        "6) Enable multimodality (audio + text + transcriptions).\n"
        "7) Enable turn detection and chairman interruption routing.\n"
        "8) Set allow_interruptions=true for natural barge-in behavior.\n"
        "9) Ensure observer/world agents remain listen-only and update board state.\n\n"
        f"CRISIS INPUT:\n{crisis_input}\n\n"
        f"CRISIS TITLE:\n{crisis_title}\n\n"
        f"CRISIS BRIEF:\n{crisis_brief}\n"
    )


def build_livekit_agent_session_config(
    *,
    session_id: str,
    agent_id: str,
    character_name: str,
    role_title: str,
    assigned_voice: str,
    skill_md: str,
    text_model: str,
    stt_model: str,
    tts_model: str,
    crisis_brief: str,
    allow_interruptions: bool = True,
) -> dict:
    """
    Build a backend-owned config payload mirroring LiveKit AgentSession options.
    """
    return {
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_identity": {
            "character_name": character_name,
            "role_title": role_title,
            "voice_id": assigned_voice,
        },
        "runtime": "livekit_agents",
        "pipeline": {
            "mode": "stt-llm-tts",
            "stt": f"elevenlabs/{stt_model}",
            "llm": f"google/{text_model}",
            "tts": f"elevenlabs/{tts_model}:{assigned_voice}",
        },
        "multimodality": {
            "audio_input": True,
            "audio_output": True,
            "text_input": True,
            "text_output": True,
            "transcriptions": True,
            "chat_topic": "lk.chat",
            "transcription_topic": "lk.transcription",
        },
        "voice_options": {
            "allow_interruptions": allow_interruptions,
            "preemptive_generation": True,
            "use_tts_aligned_transcript": True,
            "sync_transcription": True,
        },
        "turn_detection": {
            "enabled": True,
            "mode": "vad+turn_detector",
            "chairman_interrupt_priority": True,
            "manual_interrupt_topic": "chairman_taking_floor",
        },
        "input_options": {
            "audio_enabled": True,
            "text_enabled": True,
        },
        "output_options": {
            "audio_enabled": True,
            "transcription_enabled": True,
            "sync_transcription": True,
        },
        "startup": {
            "introduce_on_join": True,
            "intro_delay_seconds": 1.2,
            "intro_message": (
                f"I am {character_name}, {role_title}. "
                "I am online and ready. Share the immediate crisis objective."
            ),
        },
        "instruction_sources": {
            "skill_md_chars": len(skill_md),
            "skill_md_bound_to_runtime": True,
            "crisis_brief": crisis_brief,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
