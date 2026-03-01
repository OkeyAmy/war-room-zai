# How to Get API Keys for WAR ROOM

This guide explains how to get the necessary API keys and credentials to run the **WAR ROOM** backend, both for local development and production deployment.

---

## Quick Start: Running Locally for FREE

You can run the entire backend locally **without spending any money**. Here's how:

### Option A: Fully Offline (No API keys needed)

The backend has built-in mock fallbacks for everything:

- **No Gemini key?** → Agents use mock scenario data (pre-built crisis simulation)
- **No GCP credentials?** → Firestore operations use an in-memory mock database
- **No emulator?** → Everything still works with the mock layer

Just run:

```bash
cd backend
python -m uvicorn main:app --reload
```

### Option B: Free Gemini API + Local Emulator (Recommended for Development)

This gives you **real** AI responses without costing money:

1. Get a **free Gemini API key** (see Section 1 below)
2. Use the **Firestore Emulator** (see Section 3 below) — runs locally, no billing
3. Comment out `FIRESTORE_EMULATOR_HOST` only when you're ready for production

Your `.env` for free local development:

```env
# Gemini API (free tier)
GOOGLE_API_KEY=your-gemini-api-key

# Firestore Emulator (free, runs locally)
FIRESTORE_EMULATOR_HOST=localhost:8080

# FastAPI
HOST=0.0.0.0
PORT=8000
DEBUG=true

# GCP — NOT NEEDED for local dev
# GCP_PROJECT_ID=
# GOOGLE_APPLICATION_CREDENTIALS=
```

> **💡 When does it cost money?**
> Only when you deploy to **Google Cloud Run** and use **live Firestore** (not the emulator). The Gemini API free tier is very generous for development.

---

## 1. Gemini API Key (`GOOGLE_API_KEY`) — FREE

The Gemini API has a **free tier** that is more than enough for development and testing.

### How to get it

1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Sign in with your Google account
3. Click **Get API key** in the left sidebar
4. Click **Create API key**
5. Select a Google Cloud project (or let it create a new one)
6. Copy the generated key

### Free tier limits

- **Gemini 2.0 Flash**: 15 requests per minute, 1 million tokens per minute (free)
- **Gemini 2.0 Flash Live**: Available in the free tier

Add to your `.env`:

```env
GOOGLE_API_KEY="AIzaSy..."
```

### Test it

```bash
cd backend
source .venv/bin/activate
python tests/test_ping_gemini.py
```

---

## 2. GCP Credentials (`GOOGLE_APPLICATION_CREDENTIALS` & `GCP_PROJECT_ID`)

**⚠️ Only needed for production or testing with live Firestore.**  
For local dev, use the Firestore Emulator (Section 3) instead.

### How to get it

1. **Create a GCP Project:**
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Click the project dropdown → **New Project**
   - Name it `war-room-production`
   - Copy the **Project ID**

2. **Enable Firestore API:**
   - Search "Firestore API" in the console → **Enable**
   - Go to Firestore → **Create Database** → choose "Native mode"
   - Select a region (e.g., `us-central1`)

3. **Create a Service Account:**
   - Go to **IAM & Admin > Service Accounts**
   - Click **Create Service Account**
   - Name: `war-room-backend-sa`
   - Grant role: `Cloud Datastore User`
   - Click **Done**

4. **Download the JSON Key:**
   - Click the three dots → **Manage keys**
   - **Add Key > Create new key > JSON**
   - Save the file as `gcp-service-account.json` in the `backend/` directory

Add to your `.env`:

```env
GCP_PROJECT_ID="war-room-production"
GOOGLE_APPLICATION_CREDENTIALS="./gcp-service-account.json"
```

> 🔒 **SECURITY**: Never commit `gcp-service-account.json` or `.env` to GitHub.
> The `.gitignore` already excludes these files.

### Test it

```bash
cd backend
source .venv/bin/activate
python tests/test_ping_gcp.py
```

---

## 3. Firestore Emulator (FREE Local Database)

The Firestore Emulator runs a local database that is **100% free** and does not hit Google Cloud.

### Install

```bash
# Install Google Cloud CLI if not already
curl -sSL https://sdk.cloud.google.com | bash

# Install the emulator component
gcloud components install cloud-firestore-emulator
```

### Run locally

```bash
gcloud emulators firestore start --host-port=localhost:8080
```

### Configure in `.env`

```env
FIRESTORE_EMULATOR_HOST=localhost:8080
```

> **To switch to real Firestore:** just remove or comment out `FIRESTORE_EMULATOR_HOST` in `.env`.
> That's when billing may start (live Firestore has a generous free tier too: 50K reads/day, 20K writes/day).

---

## 4. Running All Tests

Run all connectivity tests in one command:

```bash
cd backend
source .venv/bin/activate
python tests/test_ping_all.py
```

This will test:

- ✅ Gemini API key validity
- ✅ Gemini text generation
- ✅ Available Gemini models
- ✅ Live API model availability
- ✅ GCP project ID
- ✅ Credentials file
- ✅ Firestore emulator connectivity
- ✅ Firestore write/read/delete

---

## 5. Production Deployment (Google Cloud Run)

When you're ready to deploy, your costs come from:

- **Cloud Run**: Pay per request (very generous free tier: 2M requests/month)
- **Firestore**: Pay per read/write (free tier: 50K reads, 20K writes per day)
- **Gemini API**: Pay per token (or stick to free tier limits)

### Steps

1. Remove `FIRESTORE_EMULATOR_HOST` from your production config
2. In Cloud Run settings → **Variables & Secrets**, add:
   - `GOOGLE_API_KEY` = your Gemini API key
   - `GCP_PROJECT_ID` = your project ID
3. Cloud Run uses IAM natively — ensure the default service account has `Cloud Datastore User` role
4. Deploy:

   ```bash
   gcloud builds submit --config cloudbuild.yaml
   ```

### Cost Summary

| Service | Free Tier | After Free Tier |
|---------|-----------|----------------|
| Gemini 2.0 Flash | 15 RPM, 1M tokens/min | $0.075/1M input tokens |
| Cloud Run | 2M requests/month | $0.40/1M requests |
| Firestore | 50K reads, 20K writes/day | $0.06/100K reads |
