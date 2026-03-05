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

    # Z.AI API (OpenAI-compatible)
    zai_api_key: str = ""
    zai_base_url: str = "https://api.z.ai/api/paas/v4/"

    # Z.AI Models — all configurable via .env for easy testing
    zai_scenario_model: str = "glm-5"       # Scenario generation, document finalization
    zai_agent_model: str = "glm-4.7"        # Per-agent reasoning
    zai_fast_model: str = "glm-5"           # Speaker selection, observer analysis
    zai_vision_model: str = "glm-4.6v"      # Visual document understanding
    zai_ocr_model: str = "glm-ocr"          # Structured text extraction

    # Firestore
    firestore_emulator_host: str = ""

    # FastAPI
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # Pub/Sub
    pubsub_emulator_host: str = ""
    pubsub_topic: str = "war-room-events"

    # Voice backend:
    # - "livekit_elevenlabs": ElevenLabs STT/TTS via LiveKit plugins + Z.AI text LLM
    voice_backend: str = "livekit_elevenlabs"
    # Temporary stabilization mode: only one agent is allowed to speak.
    # Set to False to re-enable multi-agent autonomous voice.
    single_agent_voice_mode: bool = False
    # Optional explicit agent role_key or agent_id for the single speaking agent.
    # If empty, the first generated roster agent is used.
    single_agent_voice_target: str = ""

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_stt_model: str = "scribe_v2_realtime"
    elevenlabs_tts_model: str = "eleven_turbo_v2_5"

    # LiveKit (server API)
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # Session config
    max_agents_per_session: int = 5
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
    if s.google_application_credentials:
        os.environ.setdefault(
            "GOOGLE_APPLICATION_CREDENTIALS", s.google_application_credentials
        )
    return s
