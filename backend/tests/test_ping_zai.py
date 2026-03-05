"""
WAR ROOM — Test Ping: Z.AI API
Verifies that your ZAI_API_KEY is valid and can reach Z.AI's GLM API.
Tests text generation using the OpenAI-compatible endpoint.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


def test_zai_api_key_exists():
    """Check that ZAI_API_KEY is set in environment."""
    api_key = os.environ.get("ZAI_API_KEY", "")
    assert api_key, "ZAI_API_KEY is not set in .env"
    assert api_key != "your-zai-api-key-here", "ZAI_API_KEY is still the placeholder value"
    print(f"  ✅ ZAI_API_KEY is set ({api_key[:10]}...)")


def test_zai_base_url_configured():
    """Check that ZAI_BASE_URL is set."""
    base_url = os.environ.get("ZAI_BASE_URL", "")
    assert base_url, "ZAI_BASE_URL is not set in .env"
    assert "z.ai" in base_url or "bigmodel" in base_url, (
        f"ZAI_BASE_URL does not look like a Z.AI endpoint: {base_url}"
    )
    print(f"  ✅ ZAI_BASE_URL = {base_url}")


def test_zai_text_generation():
    """Ping Z.AI API with a simple text generation request using OpenAI SDK."""
    from openai import OpenAI

    api_key = os.environ.get("ZAI_API_KEY")
    base_url = os.environ.get("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4/")
    model = os.environ.get("ZAI_AGENT_MODEL", "glm-4.7")

    client = OpenAI(api_key=api_key, base_url=base_url)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Respond with exactly: PING_OK"}],
        max_tokens=20,
    )

    text = response.choices[0].message.content or ""
    assert text.strip(), "Z.AI returned no text"
    print(f"  ✅ Z.AI text generation works (model={model}). Response: {text.strip()[:50]}")


def test_zai_scenario_model():
    """Test the scenario model (glm-5) with a JSON response."""
    from openai import OpenAI

    api_key = os.environ.get("ZAI_API_KEY")
    base_url = os.environ.get("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4/")
    model = os.environ.get("ZAI_SCENARIO_MODEL", "glm-5")

    client = OpenAI(api_key=api_key, base_url=base_url)

    response = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": 'Return a JSON object: {"status": "ok", "model": "' + model + '"}',
        }],
        max_tokens=50,
        response_format={"type": "json_object"},
    )

    import json
    text = response.choices[0].message.content or ""
    assert text.strip(), f"Z.AI {model} returned no text"
    data = json.loads(text)
    assert data.get("status") == "ok", f"Unexpected response: {data}"
    print(f"  ✅ Z.AI scenario model ({model}) works. Response: {text.strip()[:60]}")


if __name__ == "__main__":
    print("\n🔑 WAR ROOM — Z.AI API Ping Test\n" + "=" * 45)

    tests = [
        ("API Key Present", test_zai_api_key_exists),
        ("Base URL Configured", test_zai_base_url_configured),
        ("Text Generation (Agent Model)", test_zai_text_generation),
        ("JSON Generation (Scenario Model)", test_zai_scenario_model),
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
        print("🎉 All Z.AI API tests passed!")
    else:
        print("⚠️  Some tests failed — check your ZAI_API_KEY and ZAI_BASE_URL")
