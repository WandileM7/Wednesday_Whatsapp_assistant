# ============================================
# Google Cloud Platform Setup Script (PowerShell)
# ============================================
# Run this script to set up your GCP project for Wednesday Assistant
#
# Prerequisites:
# 1. Google Cloud SDK installed (gcloud)
# 2. Logged in with: gcloud auth login
# 3. A GCP project created
#
# Usage: .\scripts\setup-gcp.ps1 -ProjectId <project-id> [-Region <region>]

param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectId,
    
    [Parameter(Mandatory=$false)]
    [string]$Region = "us-central1"
)

$ErrorActionPreference = "Stop"

# Configuration
$ServiceAccountName = "wednesday-assistant-sa"
$ArtifactRegistry = "wednesday-registry"
$SaEmail = "$ServiceAccountName@$ProjectId.iam.gserviceaccount.com"

function Write-Header {
    param([string]$Text)
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Blue
    Write-Host "  $Text" -ForegroundColor Blue
    Write-Host "============================================" -ForegroundColor Blue
    Write-Host ""
}

function Write-Success {
    param([string]$Text)
    Write-Host "✅ $Text" -ForegroundColor Green
}

function Write-WarningMsg {
    param([string]$Text)
    Write-Host "⚠️  $Text" -ForegroundColor Yellow
}

function Write-ErrorMsg {
    param([string]$Text)
    Write-Host "❌ $Text" -ForegroundColor Red
}

function Write-Info {
    param([string]$Text)
    Write-Host "ℹ️  $Text" -ForegroundColor Cyan
}

# Main script
Write-Header "Wednesday Assistant - GCP Setup"
Write-Host "Project ID: $ProjectId"
Write-Host "Region: $Region"

# Set the project
Write-Info "Setting project to $ProjectId..."
gcloud config set project $ProjectId

# Enable required APIs
Write-Header "Enabling Required APIs"
$apis = @(
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "containerregistry.googleapis.com",
    "iam.googleapis.com"
)

foreach ($api in $apis) {
    Write-Info "Enabling $api..."
    gcloud services enable $api --quiet
    Write-Success "$api enabled"
}

# Create Artifact Registry
Write-Header "Creating Artifact Registry"
$registryExists = gcloud artifacts repositories describe $ArtifactRegistry --location=$Region 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-WarningMsg "Artifact Registry '$ArtifactRegistry' already exists"
} else {
    gcloud artifacts repositories create $ArtifactRegistry `
        --repository-format=docker `
        --location=$Region `
        --description="Wednesday Assistant Docker images"
    Write-Success "Artifact Registry created"
}

# Create Service Account
Write-Header "Creating Service Account"
$saExists = gcloud iam service-accounts describe $SaEmail 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-WarningMsg "Service account '$ServiceAccountName' already exists"
} else {
    gcloud iam service-accounts create $ServiceAccountName `
        --display-name="Wednesday Assistant CI/CD"
    Write-Success "Service account created"
}

# Grant roles to service account
Write-Header "Granting IAM Roles"
$roles = @(
    "roles/run.admin",
    "roles/artifactregistry.writer",
    "roles/iam.serviceAccountUser",
    "roles/secretmanager.secretAccessor",
    "roles/secretmanager.admin",
    "roles/storage.admin"
)

foreach ($role in $roles) {
    Write-Info "Granting $role..."
    gcloud projects add-iam-policy-binding $ProjectId `
        --member="serviceAccount:$SaEmail" `
        --role="$role" `
        --quiet | Out-Null
    Write-Success "$role granted"
}

# Create service account key
Write-Header "Creating Service Account Key"
$keyFile = ".\gcp-sa-key.json"
if (Test-Path $keyFile) {
    Write-WarningMsg "Key file already exists. Delete it first if you need a new key."
} else {
    gcloud iam service-accounts keys create $keyFile `
        --iam-account=$SaEmail
    Write-Success "Service account key saved to $keyFile"
    Write-WarningMsg "Keep this file secure! Add it to .gitignore"
}

# Create initial secrets
Write-Header "Creating Secret Manager Secrets"
$secrets = @(
    # Core AI
    "GEMINI_API_KEY",
    "BYTEZ_API_KEY",
    # Spotify
    "SPOTIFY_CLIENT_ID",
    "SPOTIFY_SECRET",
    "SPOTIFY_REFRESH_TOKEN",
    # Google OAuth
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REFRESH_TOKEN",
    # External APIs
    "NEWS_API_KEY",
    "WEATHERAPI_KEY",
    "FLASK_SECRET_KEY",
    # JARVIS Advanced Features
    "ELEVENLABS_API_KEY",
    "IFTTT_WEBHOOK_KEY",
    "HOME_ASSISTANT_URL",
    "HOME_ASSISTANT_TOKEN"
)

foreach ($secret in $secrets) {
    $secretExists = gcloud secrets describe $secret 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-WarningMsg "Secret '$secret' already exists"
    } else {
        Write-Info "Creating secret: $secret"
        "placeholder" | gcloud secrets create $secret --data-file=- --quiet
        Write-Success "Secret '$secret' created (update with actual value)"
    }
}

# Output summary
Write-Header "Setup Complete!"
Write-Host ""
Write-Host "📋 Next Steps:" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Add GitHub Secrets to your repository:"
Write-Host "   - GCP_PROJECT_ID: $ProjectId"
Write-Host "   - GCP_REGION: $Region"
Write-Host "   - GCP_SA_KEY: (base64 encode $keyFile)"
Write-Host ""
Write-Host "   To base64 encode the key (PowerShell):"
Write-Host "   [Convert]::ToBase64String([IO.File]::ReadAllBytes('$keyFile'))"
Write-Host ""
Write-Host "2. Update Secret Manager secrets with actual values:"
foreach ($secret in $secrets) {
    Write-Host "   'your-value' | gcloud secrets versions add $secret --data-file=-"
}
Write-Host ""
Write-Host "3. Push to main/master branch to trigger deployment"
Write-Host ""
Write-Host "4. After deployment, get your service URLs with:"
Write-Host "   gcloud run services list --region=$Region"
Write-Host ""
Write-Success "GCP setup complete!"
