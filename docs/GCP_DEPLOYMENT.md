# 🚀 Google Cloud Platform Deployment Guide

This guide will help you deploy the **JARVIS-powered Wednesday WhatsApp Assistant** to Google Cloud Platform using Cloud Run.

## 📋 Prerequisites

1. **Google Cloud Account** with billing enabled
2. **Google Cloud SDK** installed ([Download](https://cloud.google.com/sdk/docs/install))
3. **GitHub Repository** with the Wednesday Assistant code
4. **GEMINI_API_KEY** (required for MCP Agent reasoning)

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Google Cloud Platform                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐      │
│  │   Artifact   │      │    Cloud     │      │   Secret     │      │
│  │   Registry   │─────▶│     Run      │◀────▶│   Manager    │      │
│  │   (Images)   │      │  (Services)  │      │   (Keys)     │      │
│  └──────────────┘      └──────────────┘      └──────────────┘      │
│                              │                                       │
│         ┌────────────────────┼────────────────────┐                 │
│         │                    │                    │                 │
│         ▼                    ▼                    ▼                 │
│  ┌──────────────┐     ┌──────────────┐    ┌──────────────┐         │
│  │  JARVIS      │     │   WhatsApp   │    │  MCP Server  │         │
│  │  Assistant   │◀───▶│   Service    │    │  (52 tools)  │         │
│  │  (MCP Agent) │     │  (Baileys)   │    │  Port 8080   │         │
│  └──────────────┘     └──────────────┘    └──────────────┘         │
│         │                                         │                 │
│         │    ┌───────────────────────────────────┐│                 │
│         └───▶│ MCP Agent (Gemini + 52 MCP Tools) │◀┘                 │
│              │ • Workflows    • Smart Home       │                  │
│              │ • Voice        • Memory           │                  │
│              │ • Security     • Fitness          │                  │
│              │ • Calendar     • Spotify          │                  │
│              └───────────────────────────────────┘                  │
│                              │                                       │
│                              ▼                                       │
│                    ┌──────────────────┐                             │
│                    │ External Services │                            │
│                    │ • Vertex AI/Gemini│                            │
│                    │ • ElevenLabs      │                            │
│                    │ • Smart Home      │                            │
│                    │ • Spotify/Google  │                            │
│                    └──────────────────┘                             │
└─────────────────────────────────────────────────────────────────────┘
```

## 🤖 MCP Agent Architecture

The JARVIS assistant now uses an **MCP Agent** that:
1. Receives WhatsApp messages via webhook
2. Uses **Gemini AI for reasoning** (deciding which tools to call)
3. Executes **52 MCP tools** for actions (calendar, email, smart home, etc.)
4. Returns responses through WhatsApp

## 🛠️ Quick Setup (Automated)

### Option 1: PowerShell (Windows)
```powershell
# Login to Google Cloud
gcloud auth login

# Run the setup script
.\scripts\setup-gcp.ps1 -ProjectId "your-project-id" -Region "us-central1"
```

### Option 2: Bash (Linux/macOS)
```bash
# Login to Google Cloud
gcloud auth login

# Make script executable
chmod +x scripts/setup-gcp.sh

# Run the setup script
./scripts/setup-gcp.sh your-project-id us-central1
```

## 📝 Manual Setup

### Step 1: Create a GCP Project

```bash
# Create project
gcloud projects create wednesday-assistant --name="Wednesday Assistant"

# Set as default project
gcloud config set project wednesday-assistant

# Enable billing (required for Cloud Run)
# Visit: https://console.cloud.google.com/billing
```

### Step 2: Enable Required APIs

```bash
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    cloudbuild.googleapis.com \
    iam.googleapis.com \
    storage.googleapis.com \
    aiplatform.googleapis.com
```

### Step 3: Create Artifact Registry

```bash
gcloud artifacts repositories create wednesday-registry \
    --repository-format=docker \
    --location=us-central1 \
    --description="Wednesday Assistant Docker images"
```

### Step 4: Create Service Account

```bash
# Create service account
gcloud iam service-accounts create wednesday-assistant-sa \
    --display-name="Wednesday Assistant CI/CD"

# Get the email
SA_EMAIL="wednesday-assistant-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com"

# Grant required roles
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/run.admin"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/iam.serviceAccountUser"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/secretmanager.admin"

# Needed to create the GCS session bucket and set its IAM policy from CI/CD
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/storage.admin"

# Needed so the Cloud Run *runtime* service account can call Vertex AI Gemini
# (The Compute Engine default SA is what Cloud Run instances run as)
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)')
CR_RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:${CR_RUNTIME_SA}" \
    --role="roles/aiplatform.user"
```

### Step 5: Create Service Account Key

```bash
gcloud iam service-accounts keys create gcp-sa-key.json \
    --iam-account=wednesday-assistant-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### Step 6: Create Secrets in Secret Manager

```bash
# Create secrets with your actual values
echo -n "your-bytez-api-key" | gcloud secrets create BYTEZ_API_KEY --data-file=-
echo -n "your-spotify-client-id" | gcloud secrets create SPOTIFY_CLIENT_ID --data-file=-
echo -n "your-spotify-secret" | gcloud secrets create SPOTIFY_SECRET --data-file=-
# ... repeat for other secrets
```

## 🔑 GitHub Secrets Configuration

Add these secrets to your GitHub repository (Settings → Secrets → Actions):

### Required Secrets
| Secret Name | Description | Example |
|-------------|-------------|---------|
| `GCP_PROJECT_ID` | Your GCP project ID | `wednesday-assistant` |
| `GCP_REGION` | Deployment region | `us-central1` |
| `GCP_SA_KEY` | Base64 encoded service account key | `eyJhbGci...` |
| `GEMINI_API_KEY` | **Required** - Gemini API key for MCP Agent | `AIzaSy...` |

### Optional - Core Features
| Secret Name | Description | Example |
|-------------|-------------|---------|
| `SPOTIFY_CLIENT_ID` | Spotify app client ID | `abc123...` |
| `SPOTIFY_SECRET` | Spotify app secret | `xyz789...` |
| `SPOTIFY_REFRESH_TOKEN` | Spotify refresh token (after OAuth) | `AQD...` |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | `123456...apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | Google OAuth secret | `GOCSPX-...` |
| `GOOGLE_REFRESH_TOKEN` | Google refresh token (after OAuth) | `1//0g...` |
| `NEWS_API_KEY` | NewsAPI.org key | `abc...` |
| `WEATHERAPI_KEY` | WeatherAPI.com key | `def...` |

### Optional - JARVIS Advanced Features
| Secret Name | Description | Example |
|-------------|-------------|---------|
| `ELEVENLABS_API_KEY` | ElevenLabs premium voice synthesis | `sk_...` |
| `IFTTT_WEBHOOK_KEY` | IFTTT webhook key for smart home | `abc123...` |
| `HOME_ASSISTANT_URL` | Home Assistant URL | `http://homeassistant.local:8123` |
| `HOME_ASSISTANT_TOKEN` | Home Assistant long-lived access token | `eyJ...` |

### Base64 Encode the Service Account Key

**PowerShell:**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("gcp-sa-key.json"))
```

**Bash:**
```bash
cat gcp-sa-key.json | base64 -w 0
```

## 🚀 Deployment

### Automatic Deployment (Recommended)

Push to `main` or `master` branch:
```bash
git add .
git commit -m "Deploy to GCP"
git push origin main
```

The GitHub Actions workflow will automatically:
1. ✅ Build and test the application
2. 🐳 Build Docker image
3. 📦 Push to Artifact Registry
4. 🚀 Deploy to Cloud Run
5. ✅ Run health checks

### Manual Deployment

```bash
# Build the image
docker build -t us-central1-docker.pkg.dev/YOUR_PROJECT/wednesday-registry/assistant:latest -f Dockerfile.cloudrun .

# Push to Artifact Registry
docker push us-central1-docker.pkg.dev/YOUR_PROJECT/wednesday-registry/assistant:latest

# Deploy to Cloud Run
gcloud run deploy wednesday-assistant \
    --image=us-central1-docker.pkg.dev/YOUR_PROJECT/wednesday-registry/assistant:latest \
    --region=us-central1 \
    --platform=managed \
    --allow-unauthenticated \
    --memory=512Mi \
    --port=5000
```

## 📍 Post-Deployment

### Get Service URLs

```bash
gcloud run services list --region=us-central1
```

### Update WhatsApp Webhook

After deployment, update your WhatsApp service to point to the new URL:
```bash
# Get the assistant URL
ASSISTANT_URL=$(gcloud run services describe wednesday-assistant --region=us-central1 --format='value(status.url)')

# Update environment variable
gcloud run services update wednesday-whatsapp \
    --region=us-central1 \
    --update-env-vars="WHATSAPP_HOOK_URL=$ASSISTANT_URL/webhook"
```

### Monitor Logs

```bash
# View logs
gcloud run services logs read wednesday-assistant --region=us-central1

# Stream logs
gcloud run services logs tail wednesday-assistant --region=us-central1
```

## 💰 Cost Optimization

Cloud Run charges only for actual usage:

| Resource | Free Tier | Beyond Free Tier |
|----------|-----------|------------------|
| CPU | 180,000 vCPU-seconds/month | $0.00002400/vCPU-second |
| Memory | 360,000 GiB-seconds/month | $0.00000250/GiB-second |
| Requests | 2 million/month | $0.40/million |

### Tips to Minimize Costs:
1. Set `min-instances=0` (scale to zero when idle)
2. Use appropriate memory (512Mi is usually enough)
3. Enable request-based billing (default)

## 🔧 Troubleshooting

### Common Issues

**1. Deployment fails with "Permission denied"**
```bash
# Ensure service account has required roles
gcloud projects get-iam-policy YOUR_PROJECT_ID
```

**2. Service not starting**
```bash
# Check logs
gcloud run services logs read wednesday-assistant --region=us-central1 --limit=50
```

**3. Health check failing**
```bash
# Test health endpoint directly
curl https://your-service-url.run.app/health
```

**4. Secrets not loading**
```bash
# Verify secrets exist
gcloud secrets list

# Check secret versions
gcloud secrets versions list BYTEZ_API_KEY
```

## 📚 Additional Resources

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Artifact Registry Documentation](https://cloud.google.com/artifact-registry/docs)
- [Secret Manager Documentation](https://cloud.google.com/secret-manager/docs)
- [GitHub Actions for GCP](https://github.com/google-github-actions)

## 🆘 Support

If you encounter issues:
1. Check the GitHub Actions workflow logs
2. Review Cloud Run service logs
3. Verify all secrets are configured correctly
4. Ensure APIs are enabled in your GCP project
