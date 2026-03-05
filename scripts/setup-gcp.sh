#!/bin/bash
# ============================================
# Google Cloud Platform Setup Script
# ============================================
# Run this script to set up your GCP project for Wednesday Assistant
#
# Prerequisites:
# 1. Google Cloud SDK installed (gcloud)
# 2. Logged in with: gcloud auth login
# 3. A GCP project created
#
# Usage: ./scripts/setup-gcp.sh <project-id> [region]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "\n${BLUE}============================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}============================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Find gcloud command
find_gcloud() {
    # Check if gcloud is in PATH
    if command -v gcloud &> /dev/null; then
        echo "gcloud"
        return 0
    fi
    
    # Check Windows AppData location (for Git Bash/MINGW)
    local win_gcloud="$LOCALAPPDATA/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd"
    if [ -f "$win_gcloud" ]; then
        echo "$win_gcloud"
        return 0
    fi
    
    # Check converted path for MINGW/Git Bash
    local mingw_gcloud="/c/Users/$USER/AppData/Local/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd"
    if [ -f "$mingw_gcloud" ]; then
        echo "$mingw_gcloud"
        return 0
    fi
    
    # Try common Windows username pattern
    for user_dir in /c/Users/*/AppData/Local/Google/Cloud\ SDK/google-cloud-sdk/bin/gcloud.cmd; do
        if [ -f "$user_dir" ]; then
            echo "$user_dir"
            return 0
        fi
    done
    
    return 1
}

# Check arguments
if [ -z "$1" ] || [[ "$1" == -* ]]; then
    print_error "Usage: $0 <project-id> [region]"
    echo ""
    echo "Example: $0 wednesday-459810 us-central1"
    echo ""
    echo "Note: Use positional arguments, not PowerShell flags like -ProjectId"
    exit 1
fi

PROJECT_ID=$1
REGION=${2:-us-central1}
SERVICE_ACCOUNT_NAME="wednesday-assistant-sa"
ARTIFACT_REGISTRY="wednesday-registry"

# Find gcloud
GCLOUD=$(find_gcloud)
if [ -z "$GCLOUD" ]; then
    print_error "gcloud command not found!"
    echo ""
    echo "Please install Google Cloud SDK:"
    echo "  - Windows: https://cloud.google.com/sdk/docs/install"
    echo "  - Or run in PowerShell: .\scripts\setup-gcp.ps1 -ProjectId $PROJECT_ID"
    exit 1
fi

print_info "Using gcloud at: $GCLOUD"

print_header "Wednesday Assistant - GCP Setup"
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Set the project
print_info "Setting project to $PROJECT_ID..."
"$GCLOUD" config set project $PROJECT_ID

# Enable required APIs
print_header "Enabling Required APIs"
apis=(
    "run.googleapis.com"
    "artifactregistry.googleapis.com"
    "secretmanager.googleapis.com"
    "cloudbuild.googleapis.com"
    "containerregistry.googleapis.com"
    "iam.googleapis.com"
)

for api in "${apis[@]}"; do
    print_info "Enabling $api..."
    "$GCLOUD" services enable $api --quiet
    print_success "$api enabled"
done

# Create Artifact Registry
print_header "Creating Artifact Registry"
if "$GCLOUD" artifacts repositories describe $ARTIFACT_REGISTRY --location=$REGION >/dev/null 2>&1; then
    print_warning "Artifact Registry '$ARTIFACT_REGISTRY' already exists"
else
    "$GCLOUD" artifacts repositories create $ARTIFACT_REGISTRY \
        --repository-format=docker \
        --location=$REGION \
        --description="Wednesday Assistant Docker images"
    print_success "Artifact Registry created"
fi

# Create Service Account
print_header "Creating Service Account"
SA_EMAIL="$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"

if "$GCLOUD" iam service-accounts describe $SA_EMAIL >/dev/null 2>&1; then
    print_warning "Service account '$SERVICE_ACCOUNT_NAME' already exists"
else
    "$GCLOUD" iam service-accounts create $SERVICE_ACCOUNT_NAME \
        --display-name="Wednesday Assistant CI/CD"
    print_success "Service account created"
fi

# Grant roles to service account
print_header "Granting IAM Roles"
roles=(
    "roles/run.admin"
    "roles/artifactregistry.writer"
    "roles/iam.serviceAccountUser"
    "roles/secretmanager.secretAccessor"
    "roles/secretmanager.admin"
    "roles/storage.admin"
)

for role in "${roles[@]}"; do
    print_info "Granting $role..."
    "$GCLOUD" projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SA_EMAIL" \
        --role="$role" \
        --quiet >/dev/null
    print_success "$role granted"
done

# Create service account key
print_header "Creating Service Account Key"
KEY_FILE="./gcp-sa-key.json"
if [ -f "$KEY_FILE" ]; then
    print_warning "Key file already exists. Delete it first if you need a new key."
else
    "$GCLOUD" iam service-accounts keys create $KEY_FILE \
        --iam-account=$SA_EMAIL
    print_success "Service account key saved to $KEY_FILE"
    print_warning "Keep this file secure! Add it to .gitignore"
fi

# Create initial secrets (empty placeholders)
print_header "Creating Secret Manager Secrets"
secrets=(
    "BYTEZ_API_KEY"
    "GEMINI_API_KEY"
    "SPOTIFY_CLIENT_ID"
    "SPOTIFY_SECRET"
    "SPOTIFY_REFRESH_TOKEN"
    "GOOGLE_CLIENT_ID"
    "GOOGLE_CLIENT_SECRET"
    "GOOGLE_REFRESH_TOKEN"
    "NEWS_API_KEY"
    "WEATHERAPI_KEY"
    "FLASK_SECRET_KEY"
)

for secret in "${secrets[@]}"; do
    if "$GCLOUD" secrets describe $secret >/dev/null 2>&1; then
        print_warning "Secret '$secret' already exists"
    else
        print_info "Creating secret: $secret"
        echo -n "placeholder" | "$GCLOUD" secrets create $secret --data-file=- --quiet
        print_success "Secret '$secret' created (update with actual value)"
    fi
done

# Output summary
print_header "Setup Complete!"
echo ""
echo "📋 Next Steps:"
echo ""
echo "1. Add GitHub Secrets to your repository:"
echo "   - GCP_PROJECT_ID: $PROJECT_ID"
echo "   - GCP_REGION: $REGION"
echo "   - GCP_SA_KEY: (base64 encode $KEY_FILE)"
echo ""
echo "   To base64 encode the key:"
echo "   cat $KEY_FILE | base64 -w 0"
echo ""
echo "2. Update Secret Manager secrets with actual values:"
for secret in "${secrets[@]}"; do
    echo "   $GCLOUD secrets versions add $secret --data-file=- <<< 'your-value'"
done
echo ""
echo "3. Push to main/master branch to trigger deployment"
echo ""
echo "4. After deployment, get your service URLs with:"
echo "   $GCLOUD run services list --region=$REGION"
echo ""
print_success "GCP setup complete!"
