"""
Wednesday WhatsApp Assistant — Thin relay to n8n

Receives WhatsApp webhooks from the Baileys/WAHA service,
forwards them to the self-hosted n8n workflow, and proxies
WhatsApp management endpoints (QR, status, send).
"""

import os
import time
import json
import logging
import requests
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("wednesday")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
N8N_WEBHOOK_URL = os.getenv(
    "N8N_WEBHOOK_URL", "http://n8n:5678"
).rstrip("/")
N8N_WEBHOOK_PATH = os.getenv(
    "N8N_WEBHOOK_PATH", "/webhook/whatsapp-webhook"
)
N8N_TIMEOUT = int(os.getenv("N8N_TIMEOUT", "120"))

WAHA_URL = os.getenv("WAHA_URL", "http://whatsapp-service:3000")
WAHA_HEALTH_URL = os.getenv(
    "WAHA_HEALTH_URL", WAHA_URL.rsplit("/api", 1)[0] + "/health"
)

MAX_REQUESTS_PER_MINUTE = int(os.getenv("RATE_LIMIT", "30"))

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.urandom(24)

# ---------------------------------------------------------------------------
# In-memory helpers
# ---------------------------------------------------------------------------
_rate: dict[str, list[float]] = {}
_seen: dict[str, float] = {}


def _rate_ok(phone: str) -> bool:
    """Return True if *phone* is under the per-minute rate limit."""
    now = time.time()
    cutoff = now - 60
    ts = [t for t in _rate.get(phone, []) if t > cutoff]
    if len(ts) >= MAX_REQUESTS_PER_MINUTE:
        return False
    ts.append(now)
    _rate[phone] = ts
    return True


def _dedup(msg_id: str | None) -> bool:
    """Return True if *msg_id* was already processed (within 5 min)."""
    if not msg_id:
        return False
    now = time.time()
    # Prune old entries every 50 calls
    if len(_seen) > 500:
        _seen.clear()
    if msg_id in _seen and now - _seen[msg_id] < 300:
        return True
    _seen[msg_id] = now
    return False


# ---------------------------------------------------------------------------
# WhatsApp helpers
# ---------------------------------------------------------------------------
def waha_send_text(chat_id: str, text: str) -> bool:
    """Send a text message through the WAHA/Baileys service."""
    try:
        r = requests.post(
            WAHA_URL if "/api/" in WAHA_URL else f"{WAHA_URL}/api/sendText",
            json={"chatId": chat_id, "text": text, "session": "default"},
            timeout=15,
        )
        return r.ok
    except Exception as e:
        logger.error(f"WAHA send failed: {e}")
        return False


def waha_healthy() -> bool:
    try:
        return requests.get(WAHA_HEALTH_URL, timeout=5).ok
    except Exception:
        return False


def n8n_healthy() -> bool:
    try:
        return requests.get(f"{N8N_WEBHOOK_URL}/healthz", timeout=5).ok
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return jsonify({
        "service": "Wednesday WhatsApp Assistant",
        "mode": "n8n-relay",
        "n8n_url": N8N_WEBHOOK_URL,
        "endpoints": [
            "GET  /health",
            "POST /webhook",
            "POST /send",
            "GET  /whatsapp-status",
            "GET  /whatsapp-qr",
        ],
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "mode": "n8n-relay",
        "n8n": "connected" if n8n_healthy() else "unreachable",
        "whatsapp": "connected" if waha_healthy() else "unreachable",
        "timestamp": datetime.now().isoformat(),
    })


# ---------------------------------------------------------------------------
# Core webhook — receive from WAHA, forward to n8n
# ---------------------------------------------------------------------------
@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    if request.method == "GET":
        return jsonify({"status": "online", "mode": "n8n-relay"})

    start = time.time()
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"status": "ignored", "reason": "no_data"}), 200

    payload = data.get("payload", data)

    # --- basic guards ---------------------------------------------------
    msg_id = payload.get("id") or payload.get("messageId")
    if _dedup(msg_id):
        return jsonify({"status": "ignored", "reason": "duplicate"}), 200

    if payload.get("fromMe"):
        return jsonify({"status": "ignored", "reason": "from_me"}), 200

    phone = payload.get("chatId") or payload.get("from", "")
    body = (
        payload.get("body")
        or payload.get("text")
        or payload.get("message", "")
    )

    if not phone or not body:
        return jsonify({"status": "ignored", "reason": "missing_data"}), 200

    if not _rate_ok(phone):
        logger.warning(f"Rate-limited: {phone}")
        return jsonify({"status": "rate_limited"}), 200

    # --- forward to n8n --------------------------------------------------
    n8n_url = f"{N8N_WEBHOOK_URL}{N8N_WEBHOOK_PATH}"
    logger.info(f"→ n8n | {phone}: {body[:80]}")

    try:
        resp = requests.post(
            n8n_url,
            json=data,  # forward the raw WAHA payload
            headers={"Content-Type": "application/json"},
            timeout=N8N_TIMEOUT,
        )

        if resp.ok:
            # n8n workflow sends the reply to WhatsApp itself,
            # but if it returns a reply body we can send it as fallback.
            try:
                result = resp.json()
                reply = (
                    result.get("reply")
                    or result.get("response")
                    or result.get("output")
                )
                if reply:
                    waha_send_text(phone, reply)
            except ValueError:
                pass  # n8n returned non-JSON (e.g. 200 empty) — that's fine

            elapsed = int((time.time() - start) * 1000)
            return jsonify({"status": "ok", "ms": elapsed}), 200
        else:
            logger.error(f"n8n returned {resp.status_code}: {resp.text[:200]}")
            waha_send_text(
                phone,
                "⚠️ I'm having trouble processing your message. Please try again in a moment.",
            )
            return jsonify({"status": "n8n_error", "code": resp.status_code}), 200

    except requests.Timeout:
        logger.error(f"n8n timed out ({N8N_TIMEOUT}s)")
        waha_send_text(phone, "⏳ That took too long — please try again.")
        return jsonify({"status": "timeout"}), 200

    except Exception as e:
        logger.error(f"n8n forward error: {e}")
        waha_send_text(
            phone,
            "⚠️ Something went wrong on my end. Please try again later.",
        )
        return jsonify({"status": "error", "error": str(e)}), 200


# ---------------------------------------------------------------------------
# Manual send (useful for testing / external calls)
# ---------------------------------------------------------------------------
@app.route("/send", methods=["POST"])
def send():
    data = request.get_json(silent=True) or {}
    chat_id = data.get("chatId") or data.get("phone")
    text = data.get("text") or data.get("message")
    if not chat_id or not text:
        return jsonify({"error": "chatId and text required"}), 400
    ok = waha_send_text(chat_id, text)
    return jsonify({"success": ok})


# ---------------------------------------------------------------------------
# WhatsApp management (proxy to WAHA service)
# ---------------------------------------------------------------------------
@app.route("/whatsapp-status")
def whatsapp_status():
    base = WAHA_URL.rsplit("/api", 1)[0] if "/api/" in WAHA_URL else WAHA_URL
    try:
        r = requests.get(f"{base}/api/sessions/default", timeout=5)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"status": "unreachable", "error": str(e)})


@app.route("/whatsapp-qr")
def whatsapp_qr():
    base = WAHA_URL.rsplit("/api", 1)[0] if "/api/" in WAHA_URL else WAHA_URL
    try:
        r = requests.get(f"{base}/api/qr", timeout=10)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/n8n-status")
def n8n_status():
    return jsonify({
        "url": N8N_WEBHOOK_URL,
        "webhook": f"{N8N_WEBHOOK_URL}{N8N_WEBHOOK_PATH}",
        "healthy": n8n_healthy(),
    })


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info(
        f"🚀 Wednesday relay starting — "
        f"n8n={N8N_WEBHOOK_URL}, waha={WAHA_URL}"
    )
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug, threaded=True)
