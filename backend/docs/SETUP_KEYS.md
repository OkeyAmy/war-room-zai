# How to Get API Keys for WAR ROOM

This guide explains how to get the necessary API keys and credentials to run the **WAR ROOM** backend, both for local development and production deployment.

---

## 1. Z.AI API Key (`ZAI_API_KEY`)

The WAR ROOM backend uses Z.AI's GLM models for its core reasoning, scenario generation, and agent interactions.

### How to get it

1. Go to the Z.AI website: [z.ai](https://z.ai/manage-apikey/apikey-list)
2. Sign in or create an account.
3. Navigate to the API or Developer dashboard to generate a new API key.
4. Copy the generated key.

Add to your `.env`:

```env
ZAI_API_KEY="your-zai-api-key-here"
ZAI_BASE_URL="https://api.z.ai/api/paas/v4/"

# Recommended default models
ZAI_SCENARIO_MODEL=glm-5
ZAI_AGENT_MODEL=glm-4.7
ZAI_FAST_MODEL=glm-5
ZAI_VISION_MODEL=glm-4.6v
ZAI_OCR_MODEL=glm-ocr
```

---

## 2. LiveKit Credentials (`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`)

LiveKit manages the real-time WebRTC audio distribution for the simulation, enabling seamless streaming of agent voices and your own microphone input.

### How to get it

1. Go to [LiveKit Cloud](https://cloud.livekit.io/)
2. Create an account and a new project.
3. In your project settings, locate the **URL**, **API Key**, and **API Secret**.

Add to your `.env`:

```env
LIVEKIT_URL="wss://your-project.livekit.cloud"
LIVEKIT_API_KEY="your-livekit-api-key"
LIVEKIT_API_SECRET="your-livekit-api-secret"
```

---

## 3. ElevenLabs API Key (`ELEVENLABS_API_KEY`)

ElevenLabs provides the ultra-realistic Text-to-Speech (TTS) voices for our AI agents, and fast Speech-to-Text (STT) transcription for your input.

### How to get it

1. Go to [ElevenLabs](https://elevenlabs.io/)
2. Sign in to your account.
3. Go to your Profile -> Settings -> API Keys and generate a new key.

Add to your `.env`:

```env
ELEVENLABS_API_KEY="your-elevenlabs-api-key"
ELEVENLABS_STT_MODEL=scribe_v2_realtime
ELEVENLABS_TTS_MODEL=eleven_turbo_v2_5
```

---

## 4. GCP Credentials & Firestore Emulator

The backend uses Google Cloud Firestore for state management.

### Local Development (Free Database)

For local development, you **do not** need real GCP credentials. You can use the local Firestore Emulator instead.

1. Install the Google Cloud CLI.
2. Run the emulator component:

   ```bash
   gcloud components install cloud-firestore-emulator
   gcloud emulators firestore start --host-port=localhost:8080
   ```

3. Set the emulator host in your `.env`:

   ```env
   FIRESTORE_EMULATOR_HOST=localhost:8080
   ```

### Production Deployment

For production, you will need a real GCP project:

1. Create a GCP Project and enable the **Firestore API**.
2. Create a Service Account with the `Cloud Datastore User` role.
3. Download the JSON key file.

Add to your production `.env` (and ensure `FIRESTORE_EMULATOR_HOST` is either commented out or removed):

```env
GCP_PROJECT_ID="your-gcp-project-id"
GOOGLE_APPLICATION_CREDENTIALS="path/to/service-account.json"
```

---

## Running the Application Locally

Once you have configured all your keys in the `.env` file and started your Firestore emulator, you can run the backend:

```bash
cd backend
python -m uvicorn main:app --reload
```
