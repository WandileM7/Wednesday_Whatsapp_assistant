import os

# n8n handles all AI/tools — these are only needed by n8n itself
N8N_WEBHOOK_URL       = os.getenv("N8N_WEBHOOK_URL", "http://n8n:5678")
N8N_WEBHOOK_PATH      = os.getenv("N8N_WEBHOOK_PATH", "/webhook/whatsapp-webhook")
N8N_TIMEOUT           = int(os.getenv("N8N_TIMEOUT", "120"))

WAHA_URL              = os.getenv("WAHA_URL", "http://whatsapp-service:3000/api/sendText")
