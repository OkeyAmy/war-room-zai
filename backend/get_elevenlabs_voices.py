import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

if not ELEVENLABS_API_KEY:
    print("Error: ELEVENLABS_API_KEY not found in environment variables.")
    # You can also set it manually here for testing if needed
    # ELEVENLABS_API_KEY = "your_key_here"
    exit(1)

url = "https://api.elevenlabs.io/v1/voices"
headers = {
    "Accept": "application/json",
    "xi-api-key": ELEVENLABS_API_KEY
}

try:
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to fetch voices. Status code: {response.status_code}")
        print(f"Response: {response.text}")
        exit(1)
        
    data = response.json()
    voices = data.get("voices", [])
    
    if not voices:
        print("No voices found in your ElevenLabs account.")
        exit(0)
    
    print(f"Successfully fetched {len(voices)} voices. Showing up to 50 voices:\n")
    print(f"{'No.':<4} | {'Voice ID':<25} | {'Name':<25} | {'Category'}")
    print("-" * 80)
    
    for i, voice in enumerate(voices[:50]):
        voice_id = voice.get("voice_id", "N/A")
        name = voice.get("name", "N/A")
        category = voice.get("category", "N/A")
        print(f"{i+1:<4} | {voice_id:<25} | {name:<25} | {category}")
        
except Exception as e:
    print(f"An error occurred: {e}")
