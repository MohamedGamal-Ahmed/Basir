#!/bin/bash
# ==============================================================================
# Basir Deployment Script
# Deploys the Web Co-Pilot to Google Cloud Run and handles Secret setup.
# ==============================================================================

set -e

PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
SERVICE_NAME="basir-agent"
SECRET_NAME="basir-gemini-key"

echo "🚀 Deploying Basir Web Co-Pilot to Google Cloud ($PROJECT_ID)"

# 1. Enable Required APIs
echo "✅ Enabling required GCP APIs..."
gcloud services enable run.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com \
    aiplatform.googleapis.com

# 2. Setup Secret Manager for Gemini API Key
if ! gcloud secrets describe $SECRET_NAME >/dev/null 2>&1; then
    echo "🔑 Secret '$SECRET_NAME' not found. Creating..."
    gcloud secrets create $SECRET_NAME --replication-policy="automatic"
    
    echo "Enter your Gemini API Key: "
    read -s API_KEY
    echo -n "$API_KEY" | gcloud secrets versions add $SECRET_NAME --data-file=-
    echo "✅ Secret created."
else
    echo "✅ Secret '$SECRET_NAME' already exists."
fi

# 3. Grant Cloud Run Service Agent access to the secret
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "🛡️  Granting Secret Access to $SERVICE_ACCOUNT..."
gcloud secrets add-iam-policy-binding $SECRET_NAME \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor"

# 4. Submit Build and Deploy via Cloud Build
echo "🏗️  Submitting to Cloud Build..."
# Go up to the root directory
cd ..
gcloud builds submit --config deploy/cloudbuild.yaml .

echo ""
echo "🎉 Deployment Complete!"
echo "📡 Check the Cloud Run dashboard for the service URL."
