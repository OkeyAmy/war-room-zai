"""
WAR ROOM — Test Ping: Gemini API
Verifies that your GOOGLE_API_KEY is valid and can reach Google AI Studio.
Tests both text generation (Gemini 2.0 Flash) and lists available models.
"""

import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


def test_gemini_api_key_exists():
    """Check that GOOGLE_API_KEY is set in environment."""
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    assert api_key, "GOOGLE_API_KEY is not set in .env"
    assert api_key != "your-gemini-api-key", "GOOGLE_API_KEY is still the placeholder value"
    print(f"  ✅ GOOGLE_API_KEY is set ({api_key[:10]}...)")


def test_gemini_text_generation():
    """Ping Gemini API with a simple text generation request."""
    from google import genai

    api_key = os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="Respond with exactly: PING_OK",
    )

    assert response.text is not None, "Gemini returned no text"
    print(f"  ✅ Gemini text generation works. Response: {response.text.strip()[:50]}")


def test_gemini_list_models():
    """List available Gemini models to verify API access."""
    from google import genai

    api_key = os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)

    models = list(client.models.list())
    assert len(models) > 0, "No models returned from Gemini API"

    model_names = [m.name for m in models[:5]]
    print(f"  ✅ Gemini API access confirmed. Found {len(models)} models.")
    print(f"     First 5: {', '.join(model_names)}")


def test_gemini_live_model_available():
    """Check that the Gemini Live model exists in available models."""
    from google import genai

    api_key = os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)

    models = list(client.models.list())
    model_names = [m.name for m in models]

    # Check for live-capable models
    live_models = [n for n in model_names if "live" in n.lower() or "2.0-flash" in n.lower()]
    print(f"  ✅ Found {len(live_models)} potential Live API models.")
    if live_models:
        print(f"     Live models: {', '.join(live_models[:5])}")


if __name__ == "__main__":
    print("\n🔑 WAR ROOM — Gemini API Ping Test\n" + "=" * 45)

    tests = [
        ("API Key Present", test_gemini_api_key_exists),
        ("Text Generation", test_gemini_text_generation),
        ("List Models", test_gemini_list_models),
        ("Live Model Available", test_gemini_live_model_available),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            print(f"\n🧪 {name}...")
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1

    print(f"\n{'=' * 45}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("🎉 All Gemini API tests passed!")
    else:
        print("⚠️  Some tests failed — check your GOOGLE_API_KEY")
