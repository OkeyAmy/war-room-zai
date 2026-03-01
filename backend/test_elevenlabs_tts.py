import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

if not ELEVENLABS_API_KEY:
    print("Error: ELEVENLABS_API_KEY missing.")
    exit(1)

# Using a selection of the IDs
VOICES_TO_TEST = [
    "EXAVITQu4vr4xnSDxMaL",  # Sarah
    "nPczCjzI2devNBz1zQrb",  # Brian
    "cgSgspJ2msm6clMCkdW9",  # Jessica
    "cjVigY5qzO86Huf0OWal",  # Eric
    "SOYHLrjzK2X1ezoPC6cr",  # Harry
    "pNInz6obpgDQGcFmaJgB",  # Adam
    "CwhRBWXzGAHq8TQ4Fs17",  # Roger
    "onwK4e9ZLuTAKqWW03F9",  # Daniel
    "pFZP5JQG7iQjIQuC4Bku",  # Lily
    "Xb7hH8MSUJpSbSDYk0k2",  # Alice
    "tnSpp4vdxKPjI9w0GnoV"   # Manual user entry
]

def test_voice(voice_id):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    data = {
        "text": "This is a short test of the crisis management voice system.",
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }
    
    start_time = time.time()
    try:
        response = requests.post(url, json=data, headers=headers, timeout=15)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            print(f"✅ Voice {voice_id} SUCCESS (Took {elapsed:.2f}s, Audio Size: {len(response.content)} bytes)")
            return True
        else:
            print(f"❌ Voice {voice_id} FAILED - Status {response.status_code}: {response.text}")
            return False
            
    except requests.exceptions.ReadTimeout:
        print(f"❌ Voice {voice_id} TIMED OUT after 15s")
        return False
    except Exception as e:
        print(f"❌ Voice {voice_id} ERROR: {str(e)}")
        return False

print("Starting ElevenLabs TTS synthesis test...\n")
success_count = 0
for vid in VOICES_TO_TEST:
    if test_voice(vid):
        success_count += 1
    # Adding a short delay to avoid rate limiting
    time.sleep(1)

print(f"\nTest completed: {success_count}/{len(VOICES_TO_TEST)} voices succeeded.")
