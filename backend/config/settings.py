"""
WAR ROOM — Application Settings
Loads environment variables and provides typed configuration.
"""

import os

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # GCP
    gcp_project_id: str = "war-room-dev"
    google_application_credentials: str = ""
    google_api_key: str = ""

    # Firestore
    firestore_emulator_host: str = ""

    # FastAPI
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # Pub/Sub
    pubsub_emulator_host: str = ""
    pubsub_topic: str = "war-room-events"

    # Gemini Models
    # LLM reasoning model for agent content generation.
    text_model: str = "gemini-3-flash-preview"
    # Legacy realtime model (used only if voice_backend="gemini_live").
    live_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"

    # Voice backend:
    # - "livekit_elevenlabs": ElevenLabs STT/TTS via LiveKit plugins + Gemini LLM
    # - "gemini_live": legacy direct Gemini native audio websocket
    voice_backend: str = "livekit_elevenlabs"
    # Temporary stabilization mode: only one agent is allowed to speak.
    # Set to False to re-enable multi-agent autonomous voice.
    # MULTI-AGENT: changed default from True to False for 4-agent mode
    single_agent_voice_mode: bool = False
    # Optional explicit agent role_key or agent_id for the single speaking agent.
    # If empty, the first generated roster agent is used.
    single_agent_voice_target: str = ""

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_stt_model: str = "scribe_v2_realtime" # "scribe_v1"
    elevenlabs_tts_model: str = "eleven_turbo_v2_5"

    # LiveKit (server API)
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # Session config
    # MULTI-AGENT: changed default from 1 to 4 for 4-agent mode
    max_agents_per_session: int = 4
    session_timeout_minutes: int = 45
    escalation_score_penalty: int = -8

    # Environment: "development" or "production"
    environment: str = "development"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    s = Settings()
    # Export critical env vars so Google SDKs (ADK, genai) can find them.
    # pydantic-settings reads .env into Python attrs but does NOT set os.environ,
    # which the google.genai.Client constructor requires.
    if s.google_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", s.google_api_key)
    if s.google_application_credentials:
        os.environ.setdefault(
            "GOOGLE_APPLICATION_CREDENTIALS", s.google_application_credentials
        )
    return s
