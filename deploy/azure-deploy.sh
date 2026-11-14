#!/usr/bin/env bash
# Deploy the Silsila prototype to Azure Container Apps in UAE North.
#
# Prerequisites: Azure CLI (`brew install azure-cli`), then `az login`.
# Run from the repository root:   bash deploy/azure-deploy.sh
#
# Images are built in Azure Container Registry when the subscription allows ACR
# Tasks; otherwise (common on free/new subscriptions) they are built locally with
# Docker for linux/amd64 and pushed. Set LOCAL_BUILD=1 to force local builds. The API runs as ONE replica because demo mode
# uses SQLite and recreates the fictional families on every start.
# Demo passwords are read from backend/.env and stored as Container Apps secrets.
set -euo pipefail

RG="${RG:-silsila-rg}"
LOCATION="${LOCATION:-uaenorth}"
ENV_NAME="${ENV_NAME:-silsila-env}"
API_APP="${API_APP:-silsila-api}"
WEB_APP="${WEB_APP:-silsila-web}"
TAG="${TAG:-$(git rev-parse --short HEAD)}"

[ -f backend/.env ] || { echo "backend/.env not found (copy backend/.env.example)"; exit 1; }
set -a; . backend/.env; set +a
: "${SILSILA_DEMO_FAMILY_PASSWORD:?missing in backend/.env}"
: "${SILSILA_DEMO_COUNSELLOR_PASSWORD:?missing in backend/.env}"
JWT_SECRET="${SILSILA_SECRET:-$(openssl rand -hex 32)}"

echo "== Subscription: $(az account show --query name -o tsv)  Region: $LOCATION  Group: $RG"
az extension add --name containerapp --upgrade --only-show-errors >/dev/null 2>&1 || az extension show --name containerapp -o none
for ns in Microsoft.App Microsoft.OperationalInsights Microsoft.ContainerRegistry; do
  az provider register --namespace "$ns" --only-show-errors >/dev/null
done

az group create -n "$RG" -l "$LOCATION" --tags project=silsila purpose=future-health-challenge -o none

# Registry name must be globally unique and alphanumeric; derive it from the subscription id.
ACR="${ACR:-silsila$(az account show --query id -o tsv | tr -d '-' | cut -c1-10)}"
if ! az acr show -n "$ACR" -g "$RG" -o none 2>/dev/null; then
  az acr create -n "$ACR" -g "$RG" -l "$LOCATION" --sku Basic --admin-enabled true -o none
fi
REG="$(az acr show -n "$ACR" --query loginServer -o tsv)"
REG_USER="$(az acr credential show -n "$ACR" --query username -o tsv)"
REG_PASS="$(az acr credential show -n "$ACR" --query 'passwords[0].value' -o tsv)"

# build_image <name:tag> <dockerfile> <context> [build-arg...]
build_image() {
  local image="$1" dockerfile="$2" context="$3"; shift 3
  local args=(); for a in "$@"; do args+=(--build-arg "$a"); done
  if [ "${LOCAL_BUILD:-0}" != "1" ] && az acr build -r "$ACR" -t "$image" -f "$dockerfile" ${args[@]+"${args[@]}"} "$context" -o none 2>/dev/null; then
    return 0
  fi
  echo "   (cloud build not available; building locally for linux/amd64)"
  az acr login -n "$ACR" >/dev/null
  docker buildx build --platform linux/amd64 -t "$REG/$image" -f "$dockerfile" ${args[@]+"${args[@]}"} --push "$context"
}

echo "== Building API image in ACR"
build_image "silsila-api:$TAG" backend/Dockerfile .

if ! az containerapp env show -n "$ENV_NAME" -g "$RG" -o none 2>/dev/null; then
  az containerapp env create -n "$ENV_NAME" -g "$RG" -l "$LOCATION" -o none
fi

SECRETS=(fampw="$SILSILA_DEMO_FAMILY_PASSWORD" coupw="$SILSILA_DEMO_COUNSELLOR_PASSWORD" jwt="$JWT_SECRET")
API_ENV=(SILSILA_DEMO=1 SILSILA_DEMO_FAMILY_PASSWORD=secretref:fampw
         SILSILA_DEMO_COUNSELLOR_PASSWORD=secretref:coupw SILSILA_SECRET=secretref:jwt SILSILA_CORS='*')

if az containerapp show -n "$API_APP" -g "$RG" -o none 2>/dev/null; then
  az containerapp secret set -n "$API_APP" -g "$RG" --secrets "${SECRETS[@]}" -o none
  az containerapp update -n "$API_APP" -g "$RG" --image "$REG/silsila-api:$TAG" --set-env-vars "${API_ENV[@]}" -o none
else
  az containerapp create -n "$API_APP" -g "$RG" --environment "$ENV_NAME" \
    --image "$REG/silsila-api:$TAG" --registry-server "$REG" --registry-username "$REG_USER" --registry-password "$REG_PASS" \
    --target-port 8000 --ingress external --min-replicas 1 --max-replicas 1 --cpu 1.0 --memory 2.0Gi \
    --secrets "${SECRETS[@]}" --env-vars "${API_ENV[@]}" -o none
fi
API_URL="https://$(az containerapp show -n "$API_APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"

echo "== Building web image in ACR (API: $API_URL)"
build_image "silsila-web:$TAG" web/Dockerfile web NEXT_PUBLIC_API_URL="$API_URL"

if az containerapp show -n "$WEB_APP" -g "$RG" -o none 2>/dev/null; then
  az containerapp update -n "$WEB_APP" -g "$RG" --image "$REG/silsila-web:$TAG" -o none
else
  az containerapp create -n "$WEB_APP" -g "$RG" --environment "$ENV_NAME" \
    --image "$REG/silsila-web:$TAG" --registry-server "$REG" --registry-username "$REG_USER" --registry-password "$REG_PASS" \
    --target-port 3000 --ingress external --min-replicas 1 --max-replicas 2 --cpu 0.5 --memory 1.0Gi -o none
fi
WEB_URL="https://$(az containerapp show -n "$WEB_APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"

# Allow only the web app's origin to call the API.
az containerapp update -n "$API_APP" -g "$RG" --set-env-vars SILSILA_CORS="$WEB_URL" -o none

echo
echo "Web app : $WEB_URL"
echo "API     : $API_URL/api/health"
echo "Region  : $LOCATION (resource group $RG)"
