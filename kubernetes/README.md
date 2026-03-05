# Wednesday WhatsApp Assistant - Kubernetes/Rancher Deployment
# ============================================================
# This directory contains Kubernetes manifests for deploying
# the Wednesday MCP Server and WhatsApp Assistant to Rancher.

## Quick Deploy

```bash
# Create namespace
kubectl create namespace wednesday

# Apply secrets first
kubectl apply -f secrets.yaml -n wednesday

# Deploy all services
kubectl apply -f . -n wednesday
```

## Components

1. **mcp-server-deployment.yaml** - MCP Server for AI tool access
2. **assistant-deployment.yaml** - Main Flask assistant service
3. **whatsapp-deployment.yaml** - WhatsApp gateway (Baileys)
4. **configmap.yaml** - Non-sensitive configuration
5. **secrets.yaml** - API keys and credentials (template)
6. **ingress.yaml** - External access configuration
7. **pvc.yaml** - Persistent storage for session data
8. **hpa.yaml** - Horizontal Pod Autoscaler

## Rancher-Specific

For Rancher deployment:
1. Import this as a Git repository in Rancher
2. Use the Helm chart in `./helm-chart/` for easier management
3. Or deploy via Rancher Fleet using `fleet.yaml`

## Architecture

```
                    ┌─────────────────┐
                    │    Ingress      │
                    │  (nginx/traefik)│
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   MCP Server    │ │    Assistant    │ │ WhatsApp Service│
│  (mcp-server)   │ │    (Flask)      │ │   (Baileys)     │
│   Port: 8080    │ │   Port: 5000    │ │   Port: 3000    │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────┬───────┴───────────────────┘
                     │
                     ▼
            ┌─────────────────┐
            │   Persistent    │
            │    Storage      │
            │  (SQLite/PVC)   │
            └─────────────────┘
```
