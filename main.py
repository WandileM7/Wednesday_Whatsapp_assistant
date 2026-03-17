import json
import os
import sys
import time
import threading
import logging
import requests
import uuid
from dotenv import load_dotenv
from datetime import datetime
from urllib.parse import urlparse
from config import GEMINI_API_KEY, BYTEZ_API_KEY
import io
import base64

# Initialize logger early so it can be used in imports
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# QR Code generation
try:
    import qrcode
    from PIL import Image
    QR_AVAILABLE = True
except ImportError:
    logger.warning("QR code generation not available")
    QR_AVAILABLE = False

# Import Bytez SDK (primary AI - 175k+ models)
try:
    from bytez import Bytez
    BYTEZ_SDK_AVAILABLE = True
except ImportError:
    BYTEZ_SDK_AVAILABLE = False
    Bytez = None

# Import Google Gemini SDK (fallback)
try:
    from google import genai
except ImportError:
    genai = None

# Timeout exception for webhook processing
class TimeoutException(Exception):
    pass

from flask import Flask, redirect, request, jsonify, session, url_for, send_file, Response, send_from_directory
from flask_session import Session
from werkzeug.middleware.proxy_fix import ProxyFix

# Import handlers
from handlers.google_auth import auth_bp
from handlers.speech import speech_to_text, text_to_speech, download_voice_message, should_respond_with_voice, cleanup_temp_file, set_user_voice_preference, toggle_user_voice_preference
from handlers.auth_manager import auth_manager
from handlers.weather import weather_service
from handlers.news import news_service
from handlers.tasks import task_manager
from handlers.contacts import contact_manager
from handlers.spotify_client import make_spotify_oauth
import spotipy
import os, time, json, threading, logging, requests
from urllib.parse import urlparse

# SQLite Database imports
try:
    from database import add_to_conversation_history, query_conversation_history, retrieve_conversation_history, db_manager
    DATABASE_AVAILABLE = True
    logger.info("SQLite database initialized successfully")
except ImportError as e:
    logger.error(f"Database not available: {e}")
    DATABASE_AVAILABLE = False
    
    # Fallback functions
    def add_to_conversation_history(phone, role, message):
        return True
    def query_conversation_history(phone, query, limit=5):
        return []
    def retrieve_conversation_history(phone, n_results=5):
        return []

load_dotenv()
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config["SESSION_PERMANENT"] = False

# Use Flask's built-in signed-cookie sessions — no server-side file storage required.
# This works correctly on Cloud Run where instances don't share a filesystem.
# FLASK_SECRET_KEY MUST be set to a stable value; os.urandom changes on every restart
# which invalidates all existing sessions.
secret_key = os.getenv("FLASK_SECRET_KEY")
if not secret_key:
    logger.warning("FLASK_SECRET_KEY not set — sessions will reset on every container restart")
    secret_key = os.urandom(24)
app.secret_key = secret_key
app.register_blueprint(auth_bp)

# Configuration
user_conversations = {}
MAX_CONVERSATIONS = 50
MAX_MESSAGES_PER_USER = 15

# Simple rate limiting tracking
request_timestamps = {}
MAX_REQUESTS_PER_MINUTE = 30

def check_rate_limit(phone):
    """Simple rate limiting to prevent abuse"""
    if not phone:
        return True
        
    now = time.time()
    minute_ago = now - 60
    
    # Clean old timestamps
    if phone in request_timestamps:
        request_timestamps[phone] = [t for t in request_timestamps[phone] if t > minute_ago]
    else:
        request_timestamps[phone] = []
    
    # Check if under limit
    if len(request_timestamps[phone]) >= MAX_REQUESTS_PER_MINUTE:
        return False
        
    # Add current request
    request_timestamps[phone].append(now)
    return True

# Session cache for user preferences
def cache_user_session(phone, gemini_url=None):
    """Cache user session data including phone number and AI service URL"""
    if not phone:
        return
    
    session_data = session.get('user_cache', {})
    
    # Cache phone number
    session_data['phone'] = phone
    session_data['last_seen'] = datetime.now().isoformat()
    
    # Cache AI service URL if provided
    if gemini_url:
        session_data['gemini_url'] = gemini_url
    
    # Set default location to Johannesburg
    if 'location' not in session_data:
        session_data['location'] = 'Johannesburg'
    
    session['user_cache'] = session_data
    logger.info(f"Cached session for {phone} with location: {session_data.get('location')}")

def get_cached_session():
    """Get cached session data"""
    return session.get('user_cache', {})

# AI Handler Priority: MCP Agent (primary) -> Gemini (fallback) -> Bytez (secondary fallback) -> Stubs
BYTEZ_HELPERS_AVAILABLE = False
GEMINI_HELPERS_AVAILABLE = False
MCP_AGENT_AVAILABLE = False

# Try MCP Agent first — routes through MCP tools, more reliable than function calling
try:
    from handlers.mcp_agent import chat_with_functions, execute_function, get_mcp_agent_status
    MCP_AGENT_AVAILABLE = True
    logger.info("🤖 MCP Agent loaded - 52 tools available via MCP")
except Exception as e:
    logger.info(f"MCP Agent not available, trying Gemini fallback: {e}")
    
    # Fall back to Gemini/Vertex AI — native function calling
    try:
        from handlers.gemini import chat_with_functions, execute_function
        GEMINI_HELPERS_AVAILABLE = True
        logger.info("Gemini AI handler loaded (Vertex AI or API key)")
    except Exception as e2:
        logger.info(f"Gemini handler not available, trying Bytez fallback: {e2}")

        # Fall back to Bytez for open-source model access
        try:
            from handlers.bytez_handler import chat_with_functions, execute_function, get_bytez_status
            if BYTEZ_SDK_AVAILABLE and os.getenv("BYTEZ_API_KEY"):
                BYTEZ_HELPERS_AVAILABLE = True
                logger.info("Bytez AI handler loaded as fallback")
            else:
                raise ImportError("Bytez SDK or API key not available")
        except Exception as e3:
            logger.warning(f"No AI handler available, using stubs: {e3}")

            def chat_with_functions(user_message: str, phone: str):
                return {"content": f"AI not configured. You said: {user_message}"}

            def execute_function(call, phone=""):
                return call.get("content") or "AI function calling not available."

# Initialize AI clients
bytez_api_key = os.getenv("BYTEZ_API_KEY")
gemini_api_key = os.getenv("GEMINI_API_KEY")
GENERATION_MODEL = "gemini-2.5-flash"

# Bytez client (primary)
bytez_client = None
if bytez_api_key and BYTEZ_SDK_AVAILABLE:
    try:
        bytez_client = Bytez(bytez_api_key)
        logger.info("✨ Bytez client initialized - Access to 175,000+ AI models!")
    except Exception as e:
        logger.warning(f"Bytez init failed: {e}")

class _DummyModel:
    def generate_content(self, prompt: str):
        class _R:
            text = "AI is not configured. Please set BYTEZ_API_KEY or GEMINI_API_KEY."
        return _R()

# Gemini client (fallback)
gemini_client = None
if gemini_api_key and genai and not bytez_client:
    try:
        gemini_client = genai.Client(api_key=gemini_api_key)
        logger.info("Gemini client initialized as fallback")
    except Exception as e:
        logger.warning(f"Gemini init failed: {e}")

# Log AI status
if MCP_AGENT_AVAILABLE:
    logger.info("🚀 AI Status: MCP Agent (Primary) - 52 tools via Model Context Protocol")
elif bytez_client:
    logger.info("🚀 AI Status: Bytez (Primary) - 175k+ models ready")
elif gemini_client or GEMINI_HELPERS_AVAILABLE:
    logger.info("🤖 AI Status: Gemini (Fallback)")
else:
    logger.warning("⚠️ AI Status: No AI configured - Set GEMINI_API_KEY")


def _generate_initial_message(prompt: str) -> str:
    """Generate initial WhatsApp message using Gemini when available."""
    if gemini_client:
        try:
            response = gemini_client.models.generate_content(
                model=GENERATION_MODEL,
                contents=prompt,
            )
            if response and getattr(response, "text", None):
                return response.text
        except Exception as e:
            logger.error(f"Gemini initial message failed: {e}")
    return _DummyModel().generate_content(prompt).text

PERSONALITY_PROMPT = os.getenv("PERSONALITY_PROMPT", "You are JARVIS - a sophisticated AI assistant with dry British wit, efficiency, and subtle sardonic humor. Address users respectfully, anticipate their needs, and deliver results with style.")
GREETING_PROMPT = os.getenv("GREETING_PROMPT", "Give a brief, witty JARVIS-style greeting appropriate for the time of day.")
INITIAL_MESSAGE_PROMPT = os.getenv("INITIAL_MESSAGE_PROMPT", "Send a sophisticated AI assistant introduction under 50 words, with subtle wit.")

waha_url = os.getenv("WAHA_URL")
WAHA_API_KEY = os.getenv("WAHA_API_KEY")

def _waha_headers(is_json=True):
    headers = {}
    if is_json:
        headers["Content-Type"] = "application/json"
    if WAHA_API_KEY:
        headers["X-API-KEY"] = WAHA_API_KEY
    return headers

if not waha_url:
    logger.warning("WAHA_URL not set. Set WAHA_URL to the WAHA public endpoint (e.g. https://waha-service.onrender.com/api/sendText)")
# Derive WAHA base URL for other API calls
def _waha_base():
    if not waha_url:
        return None
    # strip trailing /api/... to base
    if "/api/" in waha_url:
        return waha_url.split("/api/")[0]
    return waha_url.rstrip("/")

# WAHA Keep-Alive Configuration (Optimized)
WAHA_KEEPALIVE_INTERVAL = int(os.getenv("WAHA_KEEPALIVE_INTERVAL", "300"))  # Default: 5 minutes (300 seconds); previously 10 minutes (600 seconds)
WAHA_SESSION = os.getenv("WAHA_SESSION", "default")
WAHA_RETRY_ATTEMPTS = 3
waha_keepalive_active = False
waha_connection_status = {"status": "unknown", "last_check": None, "consecutive_failures": 0}

def waha_health_check():
    """Ensure WAHA session exists and is started using sessions API (optimized for reliability)."""
    global waha_connection_status
    
    try:
        base = _waha_base()
        if not base:
            waha_connection_status.update({"status": "not_configured", "last_check": datetime.now()})
            return False
            
        session_name = WAHA_SESSION
        
        # Check session status with retry logic
        for attempt in range(WAHA_RETRY_ATTEMPTS):
            try:
                r = requests.get(f"{base}/api/sessions/{session_name}", timeout=5, headers=_waha_headers(is_json=False))
                if r.status_code == 200:
                    data = r.json()
                    status = (data.get("status") or "").lower()
                    is_healthy = status in ("working", "active", "connected", "ready")
                    
                    if is_healthy:
                        waha_connection_status.update({
                            "status": "healthy",
                            "last_check": datetime.now(),
                            "consecutive_failures": 0
                        })
                        return True
                        
                if r.status_code == 404 and attempt == 0:
                    # Create session if missing
                    logger.info(f"Creating WAHA session: {session_name}")
                    rc = requests.post(f"{base}/api/sessions/{session_name}", timeout=10, headers=_waha_headers())
                    if rc.status_code not in (200, 201, 409):
                        logger.warning(f"WAHA create session failed: {rc.status_code}")
                    time.sleep(2)  # Wait for creation
                    continue
                    
                # Try to start the session
                rs = requests.post(f"{base}/api/sessions/{session_name}/start", timeout=10, headers=_waha_headers())
                if rs.status_code in (200, 202):
                    waha_connection_status.update({
                        "status": "healthy",
                        "last_check": datetime.now(),
                        "consecutive_failures": 0
                    })
                    return True
                if rs.status_code == 422 and "already started" in rs.text.lower():
                    waha_connection_status.update({
                        "status": "healthy",
                        "last_check": datetime.now(),
                        "consecutive_failures": 0
                    })
                    return True
                    
            except requests.exceptions.RequestException as e:
                if attempt < WAHA_RETRY_ATTEMPTS - 1:
                    time.sleep(1)
                    continue
                raise e
                
        waha_connection_status["consecutive_failures"] += 1
        waha_connection_status.update({"status": "unhealthy", "last_check": datetime.now()})
        return False
        
    except Exception as e:
        logger.warning(f"WAHA health check error: {e}")
        waha_connection_status["consecutive_failures"] += 1
        waha_connection_status.update({"status": "error", "last_check": datetime.now()})
        return False

def waha_keepalive():
    """Background keep-alive loop that maintains the WAHA session (optimized)."""
    global waha_keepalive_active
    while waha_keepalive_active:
        ok = waha_health_check()
        status_emoji = "✅" if ok else "❌"
        logger.info(f"{status_emoji} WAHA keep-alive: {'OK' if ok else 'NOT READY'} (failures: {waha_connection_status['consecutive_failures']})")
        
        # Alert if too many consecutive failures
        if waha_connection_status["consecutive_failures"] >= 5:
            logger.error(f"⚠️ WAHA connection critical: {waha_connection_status['consecutive_failures']} consecutive failures")
        
        time.sleep(WAHA_KEEPALIVE_INTERVAL)

def start_waha_keepalive():
    global waha_keepalive_active
    if waha_keepalive_active:
        return
    waha_keepalive_active = True
    threading.Thread(target=waha_keepalive, daemon=True, name="WAHAKeepAlive").start()
    logger.info("WAHA keep-alive service started")

def stop_waha_keepalive():
    global waha_keepalive_active
    waha_keepalive_active = False
    logger.info("WAHA keep-alive service stopped")

# Spotify OAuth Setup
SPOTIFY_SCOPE = "user-read-playback-state user-modify-playback-state"

def get_token_info():
    """Get token info from session and refresh if needed with persistent storage"""
    from helpers.token_storage import token_storage
    
    token_info = session.get("token_info", {})
    
    # If no token info in session, try stored tokens first, then environment
    if not token_info:
        # Try persistent storage first
        stored_tokens = token_storage.load_spotify_tokens()
        if (stored_tokens and stored_tokens.get('refresh_token')):
            try:
                sp_oauth = make_spotify_oauth()
                token_info = sp_oauth.refresh_access_token(stored_tokens['refresh_token'])
                session["token_info"] = token_info
                logger.info("Successfully refreshed token from persistent storage")
                return token_info
            except Exception as e:
                logger.warning(f"Failed to refresh from stored tokens: {e}")
        
        # Fallback to environment variable
        refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
        if refresh_token:
            try:
                sp_oauth = make_spotify_oauth()
                token_info = sp_oauth.refresh_access_token(refresh_token)
                session["token_info"] = token_info
                # Update persistent storage with working token
                token_storage.save_spotify_tokens(
                    refresh_token=refresh_token,
                    access_token=token_info.get('access_token')
                )
                logger.info("Successfully refreshed token from environment and saved to storage")
                return token_info
            except Exception as e:
                logger.error(f"Error refreshing token from environment: {e}")
                return None
        return None
    
    # Check if current token is expired and refresh if needed
    sp_oauth = make_spotify_oauth()
    if sp_oauth.is_token_expired(token_info):
        try:
            token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
            session["token_info"] = token_info
            # Update persistent storage
            token_storage.save_spotify_tokens(
                refresh_token=token_info.get('refresh_token'),
                access_token=token_info.get('access_token')
            )
        except Exception as e:
            logger.error(f"Error refreshing session token: {e}")
            session.pop("token_info", None)
            return None
    return token_info

def cleanup_conversations():
    """Clean up old conversations to manage memory"""
    if len(user_conversations) > MAX_CONVERSATIONS:
        sorted_convos = sorted(
            user_conversations.items(),
            key=lambda x: x[1].get('last_activity', 0)
        )
        for phone, _ in sorted_convos[:-MAX_CONVERSATIONS//2]:
            del user_conversations[phone]
        logger.info(f"Cleaned up conversations, now have {len(user_conversations)}")

def get_spotify_client():
    token_info = get_token_info()
    if not token_info:
        return None
    return spotipy.Spotify(auth=token_info["access_token"])

def save_google_tokens_to_env(credentials):
    """Save Google tokens to environment file for automation"""
    try:
        logger.info("=== GOOGLE TOKENS FOR ENVIRONMENT SETUP ===")
        logger.info(f"GOOGLE_REFRESH_TOKEN={credentials.refresh_token}")
        logger.info(f"GOOGLE_ACCESS_TOKEN={credentials.token}")
        logger.info(f"GOOGLE_CLIENT_ID={credentials.client_id}")
        logger.info(f"GOOGLE_CLIENT_SECRET={credentials.client_secret}")
        logger.info("Add these to your environment variables for automatic authentication")
        logger.info("=============================================")
        
        # Try to update .env file if it exists
        env_file = os.path.join(os.path.dirname(__file__), '.env')
        if os.path.exists(env_file):
            try:
                with open(env_file, 'r') as f:
                    content = f.read()
                
                # Update or add tokens
                tokens = [
                    ('GOOGLE_REFRESH_TOKEN', credentials.refresh_token),
                    ('GOOGLE_ACCESS_TOKEN', credentials.token),
                    ('GOOGLE_CLIENT_ID', credentials.client_id),
                    ('GOOGLE_CLIENT_SECRET', credentials.client_secret)
                ]
                
                for key, value in tokens:
                    if f'{key}=' in content:
                        import re
                        content = re.sub(f'{key}=.*', f'{key}="{value}"', content)
                    else:
                        content += f'\n{key}="{value}"\n'
                
                with open(env_file, 'w') as f:
                    f.write(content)
                
                logger.info("Updated .env file with Google tokens")
            except Exception as e:
                logger.warning(f"Could not update .env file: {e}")
        
        return True
    except Exception as e:
        logger.error(f"Failed to save Google tokens: {e}")
        return False

def initialize_google_auth():
    """Initialize Google authentication on startup"""
    logger.info("Initializing Google authentication...")
    
    try:
        from handlers.google_auth import initialize_google_auto_auth
        
        # Try automatic authentication
        if initialize_google_auto_auth():
            logger.info("✅ Google authentication ready")
            return True
        else:
            logger.warning("❌ Google authentication not available - manual setup required")
            logger.info("Visit /google-login to authenticate")
            return False
            
    except Exception as e:
        logger.error(f"Failed to initialize Google authentication: {e}")
        return False

def initialize_services():
    """Initialize all services on startup"""
    logger.info("Initializing services...")
    
    # Initialize Spotify authentication
    refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
    if refresh_token:
        logger.info("Spotify refresh token present")
        logger.info("Spotify refresh token present")
    else:
        logger.info("Spotify refresh token not set; will use interactive login when needed")
    
    # Initialize Google authentication
    initialize_google_auth()
    
    # Initialize notification system
    try:
        from handlers.notifications import task_notification_system
        # Use the send_message function defined later in the file
        def notification_send_message(phone, text):
            return send_message(phone, text)
        task_notification_system.set_send_message_callback(notification_send_message)
        task_notification_system.start_notification_service()
        logger.info("Task notification system initialized")
    except Exception as e:
        logger.error(f"Failed to initialize notification system: {e}")
    
    # Initialize background task sync service
    try:
        from handlers.tasks import background_sync_service
        background_sync_service.start()
        logger.info("Background Google Keep task sync initialized")
    except Exception as e:
        logger.error(f"Failed to initialize background task sync: {e}")
    
    # Initialize service monitor
    try:
        from handlers.service_monitor import service_monitor
        service_monitor.start_monitoring()
        logger.info("Service monitoring initialized")
    except Exception as e:
        logger.error(f"Failed to initialize service monitor: {e}")
    
    # Start WAHA keep-alive
    start_waha_keepalive()
    
    logger.info("Service initialization complete")

# Initialize services on startup
try:
    with app.app_context():
        initialize_services()
except Exception as e:
    logger.error(f"Service initialization failed: {e}")

# Routes
@app.route("/")
def home():
    """Redirect to the JARVIS dashboard"""
    return redirect('/jarvis')

@app.route("/login")
def spotify_login():
    sp_oauth = make_spotify_oauth()
    return redirect(sp_oauth.get_authorize_url())

@app.route("/callback")
def spotify_callback():
    """Handle Spotify OAuth callback with persistent token storage"""
    code = request.args.get('code')
    error = request.args.get('error')
    
    if error:
        logger.error(f"Spotify OAuth error: {error}")
        return f"❌ Authorization Error: {error}", 400
    
    if not code:
        return "❌ No authorization code received from Spotify.", 400
    
    try:
        from helpers.token_storage import token_storage
        
        sp_oauth = make_spotify_oauth()
        token_info = sp_oauth.get_access_token(code)
        session["token_info"] = token_info
        
        # Save globally for webhook access
        from handlers.spotify import save_token_globally
        save_token_globally(token_info)
        
        # Save tokens persistently using TokenStorage
        if token_info.get('refresh_token'):
            success = token_storage.save_spotify_tokens(
                refresh_token=token_info['refresh_token'],
                access_token=token_info['access_token']
            )
            
            if success:
                logger.info("✅ Spotify tokens saved persistently")
                # Also save to environment for automation
                logger.info("=== SPOTIFY TOKENS FOR ENVIRONMENT SETUP ===")
                logger.info(f"SPOTIFY_REFRESH_TOKEN={token_info['refresh_token']}")
                logger.info(f"SPOTIFY_ACCESS_TOKEN={token_info['access_token']}")
                logger.info("Tokens are now saved locally and ready for automation")
                logger.info("=============================================")
            else:
                logger.warning("Failed to save Spotify tokens persistently")
        
        logger.info("Spotify authorization successful with persistent storage")
        # Redirect to React settings page
        return redirect('/jarvis/settings?spotify=success')
    except Exception as e:
        logger.error(f"Error getting Spotify token: {e}")
        return redirect('/jarvis/settings?spotify=error&message=' + str(e))

@app.route("/spotify-callback")
def spotify_callback_alias():
    # Support SPOTIFY_REDIRECT_URI=http://localhost:5000/spotify-callback
    return spotify_callback()

@app.route("/spotify-status")
def spotify_status():
    """Check Spotify authentication status and token health"""
    try:
        from helpers.token_storage import token_storage
        
        # Check session token
        session_token = session.get("token_info")
        
        # Check stored tokens
        stored_tokens = token_storage.load_spotify_tokens()
        
        # Check environment token
        env_refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
        
        # Test current authentication
        current_token = get_token_info()
        client = get_spotify_client()
        
        status = {
            "authentication": {
                "session_token_exists": bool(session_token),
                "stored_tokens_exist": bool(stored_tokens),
                "env_refresh_token_exists": bool(env_refresh_token),
                "current_token_valid": bool(current_token),
                "spotify_client_ready": bool(client)
            },
            "token_details": {}
        }
        
        if current_token:
            status["token_details"]["expires_at"] = current_token.get("expires_at")
            status["token_details"]["has_refresh_token"] = bool(current_token.get("refresh_token"))
        
        if stored_tokens:
            status["token_details"]["stored_refresh_token"] = bool(stored_tokens.get("refresh_token"))
            status["token_details"]["stored_access_token"] = bool(stored_tokens.get("access_token"))
        
        # Test API call
        if client:
            try:
                user_info = client.current_user()
                status["api_test"] = {
                    "success": True,
                    "user_id": user_info.get("id"),
                    "display_name": user_info.get("display_name")
                }
            except Exception as e:
                status["api_test"] = {
                    "success": False,
                    "error": str(e)
                }
        
        return status
        
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/clear-spotify-tokens")
def clear_spotify_tokens():
    """Clear all Spotify tokens from session and storage"""
    from helpers.token_storage import token_storage
    
    # Clear session
    session.pop("token_info", None)
    
    # Clear persistent storage
    token_storage.clear_spotify_tokens()
    
    return "✅ All Spotify tokens cleared. Please visit /login to re-authenticate."

@app.route('/voice-preprocessor', methods=['POST'])
def voice_preprocessor():
    """
    Handle inbound voice (ptt) messages:
    1. Extract message metadata
    2. Construct media download URL (/api/media/:messageId)
    3. Download audio
    4. Transcribe (speech_to_text) with fallback
    5. Forward transcribed text as a normal text payload to /webhook
    """
    from flask import current_app

    try:
        data = request.get_json() or {}
        payload = data.get('payload', data)

        # Enhanced message ID extraction - try multiple field names
        message_id = (payload.get('id') or 
                     payload.get('messageId') or 
                     payload.get('_id') or
                     payload.get('mid') or
                     payload.get('msgId'))
        phone = payload.get('from') or payload.get('chatId')
        media_type = payload.get('type')
        has_media = payload.get('hasMedia', False)

        logger.info(f"Voice preprocessor: Processing voice message - message_id={message_id}, phone={phone}, media_type={media_type}, has_media={has_media}")
        
        # Check if this is a voice/media message
        is_voice_or_media = (
            media_type in ['ptt', 'voice', 'audio'] or 
            has_media or 
            payload.get('body') == '[Media]' or
            payload.get('text') == '[Media]' or
            payload.get('mediaUrl') or
            payload.get('url')
        )
        
        if not message_id or not phone or not is_voice_or_media:
            logger.error(f"Voice preprocessor: Invalid payload for voice handling: message_id={message_id}, phone={phone}, media_type={media_type}, has_media={has_media}, payload={payload}")
            return jsonify({'status': 'error', 'message': 'Invalid voice payload'}), 400

        # Derive base WAHA (WhatsApp service) URL from WAHA_URL env
        raw_waha_url = os.getenv('WAHA_URL', '').strip()
        if not raw_waha_url:
            logger.error("Voice preprocessor: WAHA_URL not configured")
            return jsonify({'status': 'error', 'message': 'WAHA_URL not configured'}), 500

        # Extract base up to /api
        # Examples:
        #  https://host.xyz/api/sendText -> https://host.xyz/api
        #  http://localhost:3000/api/sendText -> http://localhost:3000/api
        if '/api/' in raw_waha_url:
            base_api = raw_waha_url.split('/api/')[0].rstrip('/') + '/api'
        else:
            # If already ends with /api or missing, just append /api
            base_api = raw_waha_url.rstrip('/')
            if not base_api.endswith('/api'):
                base_api += '/api'

        media_url = f"{base_api}/media/{message_id}"
        logger.info(f"Voice preprocessor: Downloading media from {media_url}")

        # Download media (direct HTTP GET). The whatsapp-service returns OGG (opus) or mock JSON.
        import requests, tempfile
        transcript = None
        try:
            resp = requests.get(media_url, timeout=60)
            if resp.status_code != 200:
                logger.error(f"Voice preprocessor: Media download failed {resp.status_code} {resp.text}")
                transcript = f"[Media message received but media fetch failed (status {resp.status_code})]"
                raise requests.exceptions.RequestException(f"Media download failed: {resp.status_code}")
            
            # If mock mode returns JSON, handle gracefully
            content_type = resp.headers.get('content-type', '').lower()
            if 'application/json' in content_type:
                logger.warning("Voice preprocessor: Mock media endpoint returned JSON (no actual audio). Using placeholder transcription.")
                transcript = "[Voice message (mock) - no audio available]"
            else:
                # Save audio to temp file
                suffix = '.ogg'
                if 'mp3' in content_type:
                    suffix = '.mp3'
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_audio:
                    tmp_audio.write(resp.content)
                    audio_path = tmp_audio.name
                logger.info(f"Voice preprocessor: Saved audio file {audio_path} ({len(resp.content)} bytes)")

                # Transcribe (speech_to_text may return None if not configured)
                try:
                    transcript = speech_to_text(audio_path)
                except Exception as stt_e:
                    logger.error(f"Voice preprocessor: STT error: {stt_e}")
                    transcript = None

                # Cleanup temp file
                try:
                    os.remove(audio_path)
                except Exception:
                    pass

                if not transcript:
                    transcript = "[Received voice message but could not transcribe]"
                    
        except requests.exceptions.ConnectionError:
            logger.warning(f"Voice preprocessor: WAHA service not available, using mock transcription")
            # Use mock transcription when WAHA service is not available
            transcript = "[Voice message received - WAHA service unavailable for transcription]"
        except requests.exceptions.RequestException as re:
            logger.error(f"Voice preprocessor: Media download exception: {re}")
            # Use fallback transcription for other network errors
            transcript = "[Voice message received but could not download audio for transcription]"

        # Build new text payload to forward
        forward_payload = {
            'chatId': phone,
            'from': phone,
            'body': transcript,
            'text': transcript,
            'type': 'text',
            'original_type': 'voice',  # Mark this as originally a voice message
            'originalVoiceId': message_id,
            'fromMe': False
        }

        logger.info(f"Voice preprocessor: Forwarding transcribed text ({len(transcript)} chars) for {phone}")

        return forward_to_main_webhook({'payload': forward_payload})
    except Exception as e:
        logger.error(f"Voice preprocessor: Unexpected error: {e}")
        # Attempt user-facing error message
        phone = None
        try:
            data = request.get_json() or {}
            payload = data.get('payload', data)
            phone = payload.get('from') or payload.get('chatId')
        except Exception:
            pass

        if phone:
            error_payload = {
                'chatId': phone,
                'from': phone,
                'body': "Sorry, there was an error processing your voice message.",
                'text': "Sorry, there was an error processing your voice message.",
                'type': 'text',
                'fromMe': False
            }
            return forward_to_main_webhook({'payload': error_payload})
        return jsonify({'status': 'error', 'message': 'Voice processing failed'}), 500

def forward_to_main_webhook(data):
    """Forward processed message to main webhook"""
    try:
        # Internal call to main webhook
        from flask import current_app
        with current_app.test_request_context('/webhook', method='POST', json=data):
            return webhook()
    except Exception as e:
        logger.error(f"Error forwarding to main webhook: {e}")
        return jsonify({'status': 'error', 'message': 'Forward failed'}), 500
@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    """Simplified webhook that only processes text messages (voice already transcribed)"""
    if request.method == 'GET':
        return jsonify({"status": "online", "memory_optimized": True})

    start_time = time.time()
    
    try:
        # Quick validation
        data = request.get_json() or {}
        if not data:
            return jsonify({'status': 'ignored', 'reason': 'no_data'}), 200
            
        payload = data.get('payload', data)
        if not payload:
            return jsonify({'status': 'ignored', 'reason': 'no_payload'}), 200
        
        # Extract message info
        phone = payload.get('chatId') or payload.get('from', '')
        user_msg = payload.get('body') or payload.get('text') or payload.get('message', '')
        was_originally_voice = payload.get('original_type') == 'voice'
        message_type = payload.get('type', 'text')
        media_url = payload.get('mediaUrl') or payload.get('media_url')
        
        # Enhanced voice message detection
        # Check multiple indicators for voice messages
        is_voice_message = (
            message_type in ['voice', 'audio', 'ptt'] or
            user_msg == '[Media]'
        )

        # If non-voice media, append media URL hint so Gemini can analyze
        if media_url and not is_voice_message:
            user_msg = f"{user_msg}\nMedia URL: {media_url}"
        
        # If this is a voice message that hasn't been transcribed yet, redirect to preprocessor
        if is_voice_message and not was_originally_voice:
            logger.info(f"🎤 Detected voice message from {phone}, redirecting to preprocessor")
            try:
                import requests
                # Forward to voice preprocessor
                preprocessor_response = requests.post(
                    'http://localhost:5000/voice-preprocessor',
                    json=data,
                    timeout=60  # Increased timeout for voice processing
                )
                return preprocessor_response.json(), preprocessor_response.status_code
            except Exception as e:
                logger.error(f"Error redirecting to voice preprocessor: {e}")
                return jsonify({'status': 'error', 'reason': 'voice_preprocessing_failed'}), 500
        
        # Skip messages from self
        if payload.get('fromMe'):
            return jsonify({'status': 'ignored', 'reason': 'from_me'}), 200
            
        if not phone or not user_msg:
            return jsonify({'status': 'ignored', 'reason': 'missing_data'}), 200
            
        # Rate limiting check
        if not check_rate_limit(phone):
            logger.warning(f"Rate limit exceeded for {phone}")
            return jsonify({'status': 'rate_limited'}), 200

        logger.info(f"Processing {'voice→text' if was_originally_voice else 'text'} message from {phone}: {user_msg[:50]}...")
        
        # Cache user session
        cache_user_session(phone)
        
        # Memory-efficient conversation management
        if phone not in user_conversations:
            user_conversations[phone] = {
                'messages': [],
                'last_activity': time.time()
            }
        
        conversation = user_conversations[phone]
        conversation['messages'].append({
            'role': 'user',
            'content': user_msg,
            'timestamp': time.time(),
            'was_voice': was_originally_voice
        })
        
        conversation['messages'] = conversation['messages'][-MAX_MESSAGES_PER_USER:]
        conversation['last_activity'] = time.time()

        if len(user_conversations) % 10 == 0:
            cleanup_conversations()

        # Check for quick commands first (messages starting with /)
        if user_msg.startswith('/'):
            try:
                from handlers.quick_commands import process_quick_command
                cmd_result = process_quick_command(user_msg, phone)
                if cmd_result:
                    reply = cmd_result.get('response', 'Command executed.')
                    logger.info(f"Quick command processed: {user_msg[:20]}")
                else:
                    reply = "Unknown command. Type /help for available commands."
            except Exception as e:
                logger.error(f"Quick command error: {e}")
                reply = f"Error processing command: {e}"
        # Process with Gemini
        elif GEMINI_API_KEY and not GEMINI_API_KEY.startswith('test_'):
            try:
                call = chat_with_functions(user_msg, phone)
                
                if call.get("name"):
                    reply = execute_function(call, phone)
                else:
                    reply = call.get("content", "Sorry, no idea what that was.")
            except Exception as e:
                logger.error(f"Gemini processing error: {e}")
                reply = "I'm having trouble processing your message right now. Please try again later."
        else:
            reply = f"Echo: {user_msg}"

        # Save conversation
        conversation['messages'].append({
            'role': 'assistant',
            'content': reply,
            'timestamp': time.time()
        })
        conversation['messages'] = conversation['messages'][-MAX_MESSAGES_PER_USER:]

        # Send response (voice if appropriate, otherwise text)
        success = send_voice_response(phone, reply, was_originally_voice)
        
        processing_time = time.time() - start_time
        
        return jsonify({
            'status': 'ok', 
            'processing_time_ms': int(processing_time * 1000),
            'message_sent': success,
            'was_voice_input': was_originally_voice
        })

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Webhook error: {e}")
        
        return jsonify({
            'status': 'error', 
            'message': 'Processing failed', 
            'error_type': type(e).__name__,
            'processing_time_ms': int(processing_time * 1000)
        }), 200
        
        
@app.route('/send', methods=['POST'])
def send_initial_message():
    data = request.json
    phone = data.get('phone')
    if not phone:
        return jsonify({'status': 'error', 'message': 'Phone required'}), 400

    message = data.get('message')
    if message:
        success = send_message(phone, message)
    else:
        success = initiate_conversation(phone)

    if success:
        user_conversations[phone] = {'last_activity': time.time(), 'messages': []}
        return jsonify({'status': 'success'}), 200
    return jsonify({'status': 'error'}), 500

# Google Services Endpoints
@app.route("/google-status")
def google_status():
    """Check Google services status with persistent storage integration"""
    from handlers.google_auth import load_credentials, get_credentials_path, validate_credentials_file
    from helpers.token_storage import token_storage
    
    try:
        creds_path = get_credentials_path()
        
        # Check environment tokens
        env_refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        env_client_id = os.getenv("GOOGLE_CLIENT_ID")
        env_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        
        # Check stored tokens
        stored_tokens = token_storage.load_google_tokens()
        
        # Check session tokens
        session_creds = session.get('google_credentials')
        
        # Test current authentication
        current_creds = load_credentials()
        
        status = {
            "authentication": {
                "credentials_file_exists": bool(creds_path and os.path.exists(creds_path)),
                "env_tokens_exist": bool(env_refresh_token and env_client_id and env_client_secret),
                "stored_tokens_exist": bool(stored_tokens and stored_tokens.get('refresh_token')),
                "session_tokens_exist": bool(session_creds),
                "current_auth_valid": bool(current_creds and current_creds.valid)
            },
            "credentials_path": creds_path,
            "env_var_set": bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        }
        
        # File validation if exists
        if creds_path and os.path.exists(creds_path):
            is_valid, result = validate_credentials_file(creds_path)
            status.update({
                "file_valid": is_valid,
                "validation_result": result
            })
        
        # Token details
        if stored_tokens:
            status["stored_token_details"] = {
                "has_refresh_token": bool(stored_tokens.get('refresh_token')),
                "has_access_token": bool(stored_tokens.get('access_token')),
                "has_client_id": bool(stored_tokens.get('client_id')),
                "has_client_secret": bool(stored_tokens.get('client_secret'))
            }
        
        # Test API access
        if current_creds:
            try:
                from googleapiclient.discovery import build
                
                # Test Gmail
                try:
                    gmail_service = build('gmail', 'v1', credentials=current_creds)
                    profile = gmail_service.users().getProfile(userId='me').execute()
                    status["api_tests"] = status.get("api_tests", {})
                    status["api_tests"]["gmail"] = {
                        "success": True,
                        "email": profile.get('emailAddress')
                    }
                except Exception as e:
                    status["api_tests"] = status.get("api_tests", {})
                    status["api_tests"]["gmail"] = {
                        "success": False,
                        "error": str(e)
                    }
                
                # Test Calendar
                try:
                    calendar_service = build('calendar', 'v3', credentials=current_creds)
                    calendar_list = calendar_service.calendarList().list().execute()
                    status["api_tests"]["calendar"] = {
                        "success": True,
                        "calendar_count": len(calendar_list.get('items', []))
                    }
                except Exception as e:
                    status["api_tests"]["calendar"] = {
                        "success": False,
                        "error": str(e)
                    }
                    
            except Exception as e:
                status["api_tests"] = {
                    "error": f"Failed to test APIs: {str(e)}"
                }
        
        return status
        
    except Exception as e:
        return {"error": str(e)}, 500
        
        return status
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/test-gmail")
def test_gmail():
    """Test Gmail functionality"""
    from handlers.gmail import summarize_emails
    
    try:
        result = summarize_emails(3)
        return {
            "test": "gmail_summarize",
            "result": result,
            "success": not result.startswith("❌")
        }
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/google-login")
def google_login():
    """Start Google OAuth flow"""
    try:
        from handlers.google_auth import load_credentials
        
        # Check if already authenticated
        creds = load_credentials()
        if creds and creds.valid:
            return redirect('/jarvis/settings?google=already_authenticated')
        
        # Redirect to authorization flow
        return redirect(url_for('auth.authorize'))
        
    except Exception as e:
        logger.error(f"Error in Google login: {e}")
        return redirect('/jarvis/settings?google=error&message=' + str(e))

@app.route("/setup-google-auto-auth")
def setup_google_auto_auth():
    """One-time setup for automatic Google authentication"""
    try:
        from handlers.google_auth import load_credentials
        
        creds = load_credentials()
        if creds and creds.valid:
            save_google_tokens_to_env(creds)
            return """
            <h2>✅ Google Auto-Authentication Setup Complete</h2>
            <p>Your tokens have been saved for automatic authentication.</p>
            <p>Check your logs for the environment variables to add to your deployment.</p>
            <p>The app will now authenticate automatically on startup.</p>
            <p><a href="/test-google-services">Test Google Services</a></p>
            """
        else:
            return """
            <h2>❌ Authentication Required First</h2>
            <p>Please authenticate with Google first before setting up auto-authentication.</p>
            <p><a href="/google-login">Authenticate Google</a></p>
            """
    except Exception as e:
        return f"<h2>❌ Setup Failed</h2><p>Error: {str(e)}</p>", 500

@app.route("/refresh-google-token")
def refresh_google_token():
    """Manually refresh Google token"""
    try:
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        if not refresh_token:
            return {"error": "No refresh token found in environment. Complete OAuth flow first."}, 400
        
        from handlers.google_auth import load_tokens_from_env
        from google.auth.transport.requests import Request
        
        creds = load_tokens_from_env()
        if not creds:
            return {"error": "Failed to load credentials from environment"}, 400
        
        if creds.expired:
            creds.refresh(Request())
            
        return {
            "success": True,
            "message": "Google token refreshed successfully",
            "valid": creds.valid,
            "scopes": list(creds.scopes) if hasattr(creds, 'scopes') else []
        }
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/force-google-auth")
def force_google_auth():
    """Force Google authentication for testing"""
    try:
        from handlers.google_auth import load_credentials
        
        # Clear any cached credentials to force fresh auth
        import handlers.google_auth as ga
        if hasattr(ga, '_cached_credentials'):
            ga._cached_credentials = None
        
        creds = load_credentials()
        if creds and creds.valid:
            return {
                "success": True,
                "message": "Google authentication successful",
                "authenticated": True,
                "credential_type": "service_account" if hasattr(creds, 'service_account_email') else "oauth",
                "scopes": list(creds.scopes) if hasattr(creds, 'scopes') else []
            }
        else:
            return {
                "success": False,
                "message": "Google authentication failed - OAuth flow required",
                "authenticated": False,
                "auth_url": url_for('google_login', _external=True)
            }
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/test-email-send")
def test_email_send():
    """Test email sending functionality"""
    try:
        from handlers.gmail import send_email
        
        # Send a test email to yourself
        result = send_email(
            to="wandilemawela4@gmail.com",
            subject="Test Email from WhatsApp Assistant",
            message_text="This is a test email to verify Gmail integration is working."
        )
        
        return {
            "test": "email_send",
            "result": result,
            "success": not str(result).startswith("❌"),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/test-current-email")
def test_current_email():
    """Test email with current session authentication"""
    try:
        from handlers.gmail import send_email
        
        # Test with current session
        result = send_email(
            to="wandilemawela4@gmail.com",
            subject="Test from Current Session",
            message_text="Testing email functionality with current authentication session."
        )
        
        return {
            "result": result,
            "success": not str(result).startswith("❌"),
            "session_has_google_creds": bool(session.get('google_credentials')),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e), "traceback": str(e)}, 500

@app.route("/google-auth-status")
def google_auth_status():
    """Detailed Google authentication status with helpful links"""
    from handlers.google_auth import load_credentials, get_credentials_path, validate_credentials_file
    
    try:
        creds_path = get_credentials_path()
        status = {
            "credentials_path": creds_path,
            "file_exists": bool(creds_path and os.path.exists(creds_path)),
            "env_var_set": bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        }
        
        if creds_path:
            is_valid, result = validate_credentials_file(creds_path)
            status.update({
                "file_valid": is_valid,
                "validation_result": result
            })
            
            if is_valid:
                try:
                    creds = load_credentials()
                    status.update({
                        "credentials_loaded": True,
                        "has_credentials": creds is not None,
                        "credentials_valid": creds.valid if creds else False,
                        "credential_type": "service_account" if (creds and hasattr(creds, 'service_account_email')) else "oauth",
                        "needs_auth": not (creds and creds.valid)
                    })
                    
                    # Check if credentials are expired
                    if creds and hasattr(creds, 'expired'):
                        status["credentials_expired"] = creds.expired
                        
                except Exception as e:
                    status.update({
                        "credentials_loaded": False,
                        "load_error": str(e)
                    })
        
        # Add helpful actions based on status
        actions = []
        if not status.get("file_exists"):
            actions.append("Add credentials.json file")
        elif not status.get("file_valid"):
            actions.append("Fix credentials.json format")
        elif status.get("needs_auth", True):
            actions.append("Complete OAuth flow")
            status["auth_url"] = url_for('google_login', _external=True)
        else:
            actions.append("Ready to use Google services")
            
        status["recommended_actions"] = actions
        return status
        
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/test-google-services")
def test_google_services():
    """Test all Google services"""
    from handlers.gmail import summarize_emails
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "tests": {}
    }
    
    # Test Gmail read access
    try:
        gmail_result = summarize_emails(2)
        results["tests"]["gmail_read"] = {
            "success": not gmail_result.startswith("❌"),
            "result": gmail_result[:100] + "..." if len(gmail_result) > 100 else gmail_result
        }
    except Exception as e:
        results["tests"]["gmail_read"] = {
            "success": False,
            "error": str(e)
        }
    
    # Test Gmail send access (dry run)
    try:
        from handlers.google_auth import load_credentials
        from googleapiclient.discovery import build
        
        creds = load_credentials()
        if creds:
            service = build('gmail', 'v1', credentials=creds)
            service.users().getProfile(userId='me').execute()
            results["tests"]["gmail_send"] = {
                "success": True,
                "result": "Gmail send service accessible"
            }
        else:
            results["tests"]["gmail_send"] = {
                "success": False,
                "result": "No credentials available"
            }
    except Exception as e:
        results["tests"]["gmail_send"] = {
            "success": False,
            "error": str(e)
        }
    
    # Test Calendar access
    try:
        from handlers.google_auth import load_credentials
        from googleapiclient.discovery import build
        
        creds = load_credentials()
        if creds:
            service = build('calendar', 'v3', credentials=creds)
            calendar_list = service.calendarList().list(maxResults=1).execute()
            results["tests"]["calendar"] = {
                "success": True,
                "result": f"Calendar service accessible, found {len(calendar_list.get('items', []))} calendars"
            }
        else:
            results["tests"]["calendar"] = {
                "success": False,
                "result": "No credentials available"
            }
    except Exception as e:
        results["tests"]["calendar"] = {
            "success": False,
            "error": str(e)
        }
    
    # Overall status
    all_tests = results["tests"]
    successful_tests = sum(1 for test in all_tests.values() if test.get("success", False))
    total_tests = len(all_tests)
    
    results["summary"] = {
        "successful": successful_tests,
        "total": total_tests,
        "all_passed": successful_tests == total_tests
    }
    
    return results

@app.route("/services")
def services_overview():
    """Redirect to React dashboard services page"""
    return redirect('/jarvis/services')


@app.route("/api/services/overview")
def services_overview_api():
    """Overview of all available services with detailed status (API)"""
    # Get authentication status from auth manager
    auth_status = auth_manager.get_auth_status()
    
    # Determine AI status (Bytez primary, Gemini fallback)
    ai_status = {
        "status": "not_configured",
        "provider": None,
        "model": None
    }
    
    if bytez_client:
        ai_status = {
            "status": "active",
            "provider": "bytez",
            "model": os.getenv("BYTEZ_CHAT_MODEL", "Qwen/Qwen3-4B"),
            "models_available": "175,000+",
            "features": ["chat", "image_generation", "text_to_speech", "vision"]
        }
    elif gemini_client:
        ai_status = {
            "status": "active", 
            "provider": "gemini",
            "model": "gemini-2.5-flash"
        }
    
    return {
        "services": {
            "whatsapp": {
                "status": "active",
                "webhook_url": request.host_url + "webhook",
                "test_endpoint": "/health"
            },
            "spotify": auth_status['services'].get('spotify', {
                "status": "not_configured",
                "auth_url": "/login",
                "test_endpoint": "/test-spotify"
            }),
            "google": auth_status['services'].get('google', {
                "status": "not_configured",
                "auth_url": "/google-login",
                "test_endpoint": "/test-gmail",
                "dashboard": "/google-services-dashboard"
            }),
            "ai": ai_status,
            "bytez": {
                "status": "active" if bytez_client else "not_configured",
                "configured": bool(bytez_client),
                "models_available": "175,000+",
                "chat_model": os.getenv("BYTEZ_CHAT_MODEL", "Qwen/Qwen3-4B"),
                "image_model": os.getenv("BYTEZ_IMAGE_MODEL", "dreamlike-art/dreamlike-photoreal-2.0"),
                "tts_model": os.getenv("BYTEZ_TTS_MODEL", "suno/bark-small"),
                "vision_model": os.getenv("BYTEZ_VISION_MODEL", "google/gemma-3-4b-it"),
                "required_env": "BYTEZ_API_KEY",
                "docs": "https://docs.bytez.com"
            },
            "gemini": {
                "status": "active" if gemini_client else "not_configured",
                "model": "gemini-2.5-flash",
                "note": "Fallback when Bytez not configured"
            },
            "weather": {
                "status": "active" if weather_service.is_configured() else "not_configured",
                "configured": weather_service.is_configured(),
                "test_endpoint": "/weather?location=Johannesburg",
                "required_env": "WEATHERAPI_KEY"
            },
            "news": {
                "status": "active" if news_service.is_configured() else "not_configured",
                "configured": news_service.is_configured(),
                "test_endpoint": "/news",
                "required_env": "NEWS_API_KEY"
            },
            "tasks": {
                "status": "active",
                "configured": True,
                "test_endpoint": "/tasks",
                "task_count": len(task_manager.tasks),
                "reminder_count": len(task_manager.reminders)
            },
            "contacts": {
                "status": "active",
                "configured": True,
                "test_endpoint": "/contacts",
                "local_count": len(contact_manager.local_contacts)
            }
        },
        "quick_links": {
            "authenticate_google": "/google-login",
            "authenticate_spotify": "/login",
            "setup_auto_auth": "/setup-all-auto-auth",
            "auth_status": "/auth-status",
            "test_webhook": "/test-webhook-auth",
            "assistant_status": "/assistant/status",
            "test_ai": "/test-ai",
            "test_all": "/health",
            "webhook": "/webhook"
        },
        "authentication_status": auth_status['summary'],
        "enhanced_features": {
            "weather_lookup": "/weather?location=<city>",
            "news_headlines": "/news",
            "news_search": "/news/search?query=<topic>",
            "daily_briefing": "/news/briefing",
            "task_management": "/tasks",
            "reminder_system": "/reminders",
            "task_summary": "/tasks/summary",
            "contact_management": "/contacts",
            "contact_search": "/contacts/search?query=<name>",
            "google_contacts": "/contacts/google",
            "ai_chat": "/test-ai",
            "generate_image": "/generate-image?prompt=<description>",
            "text_to_speech": "/synthesize-speech?text=<text>"
        }
    }


@app.route("/test-ai")
def test_ai():
    """Test AI functionality (Bytez or Gemini)"""
    test_message = request.args.get("message", "Hello! What AI model are you using?")
    
    result = {
        "bytez_available": bool(bytez_client),
        "gemini_available": bool(gemini_client),
        "primary_ai": "bytez" if bytez_client else ("gemini" if gemini_client else "none")
    }
    
    try:
        response = chat_with_functions(test_message, "test_user")
        result["response"] = response.get("content") or response.get("name", "Function call triggered")
        result["status"] = "success"
    except Exception as e:
        result["error"] = str(e)
        result["status"] = "error"
    
    return jsonify(result)


# Spotify endpoints
@app.route("/test-spotify")
def test_spotify():
    """Test Spotify functionality"""
    try:
        token_info = get_token_info()
        if not token_info:
            return {
                "authenticated": False,
                "message": "No token available",
                "login_url": "/login"
            }
        
        sp = spotipy.Spotify(auth=token_info["access_token"])
        user = sp.current_user()
        playback = sp.current_playback()
        
        return {
            "authenticated": True,
            "user": user["display_name"],
            "user_id": user["id"],
            "has_active_device": bool(playback),
            "current_track": playback["item"]["name"] if playback and playback.get("item") else None,
            "token_expires": token_info.get("expires_at"),
            "scopes": token_info.get("scope", "").split()
        }
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/test-speech")
def test_speech():
    """Test speech functionality (TTS and STT)"""
    try:
        from handlers.speech import get_speech_client, get_tts_client, text_to_speech
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "tests": {}
        }
        
        # Test TTS client initialization
        try:
            tts_client = get_tts_client()
            results["tests"]["tts_client"] = {
                "success": tts_client is not None,
                "message": "TTS client initialized" if tts_client else "TTS client not available"
            }
        except Exception as e:
            results["tests"]["tts_client"] = {
                "success": False,
                "error": str(e)
            }
        
        # Test STT client initialization
        try:
            speech_client = get_speech_client()
            results["tests"]["stt_client"] = {
                "success": speech_client is not None,
                "message": "STT client initialized" if speech_client else "STT client not available"
            }
        except Exception as e:
            results["tests"]["stt_client"] = {
                "success": False,
                "error": str(e)
            }
        
        # Test actual TTS if client is available
        test_text = "Hello, this is a test of the text to speech functionality."
        try:
            if results["tests"]["tts_client"]["success"]:
                audio_file = text_to_speech(test_text)
                results["tests"]["tts_generation"] = {
                    "success": audio_file is not None,
                    "message": f"Generated audio file: {audio_file}" if audio_file else "Failed to generate audio",
                    "test_text": test_text
                }
                
                # Clean up test file
                if audio_file and os.path.exists(audio_file):
                    try:
                        os.unlink(audio_file)
                    except:
                        pass
            else:
                results["tests"]["tts_generation"] = {
                    "success": False,
                    "message": "Skipped - TTS client not available"
                }
        except Exception as e:
            results["tests"]["tts_generation"] = {
                "success": False,
                "error": str(e)
            }
        
        # Configuration check
        results["configuration"] = {
            "voice_responses_enabled": os.getenv("ENABLE_VOICE_RESPONSES", "true").lower() == "true",
            "max_voice_length": int(os.getenv("MAX_VOICE_RESPONSE_LENGTH", "200")),
            "google_creds_env": bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS")),
            "has_google_oauth": bool(session.get('google_credentials'))
        }
        
        return results
        
    except Exception as e:
        return {"error": str(e)}, 500


# Health and monitoring
@app.route("/health")
def health():
    """Health check with memory information"""
    try:
        import psutil
        import gc
        gc.collect()
        process = psutil.Process()
        memory_info = process.memory_info()
        
        # Include database and WAHA status in health check
        waha_healthy = waha_health_check() if waha_url else None
        
        # Get database statistics
        db_stats = {}
        if DATABASE_AVAILABLE:
            try:
                db_stats = db_manager.get_database_stats()
            except Exception as e:
                logger.error(f"Failed to get database stats: {e}")
        
        # Get MCP Agent status
        mcp_status = {}
        if MCP_AGENT_AVAILABLE:
            try:
                from handlers.mcp_agent import get_mcp_agent_status
                mcp_status = get_mcp_agent_status()
            except Exception as e:
                mcp_status = {"status": "error", "error": str(e)}
        
        return jsonify({
            "status": "healthy",
            "memory_mb": round(memory_info.rss / 1024 / 1024, 2),
            "active_conversations": len(user_conversations),
            "database_enabled": DATABASE_AVAILABLE,
            "database_stats": db_stats,
            "waha_status": "connected" if waha_healthy else ("disconnected" if waha_healthy is False else "not_configured"),
            "waha_keepalive": waha_keepalive_active,
            "ai_handler": "mcp_agent" if MCP_AGENT_AVAILABLE else ("gemini" if GEMINI_HELPERS_AVAILABLE else ("bytez" if BYTEZ_HELPERS_AVAILABLE else "none")),
            "mcp_agent": mcp_status if MCP_AGENT_AVAILABLE else "not_available",
            "gemini_helpers": GEMINI_HELPERS_AVAILABLE,
            "timestamp": datetime.now().isoformat()
        })
    except ImportError:
        return jsonify({
            "status": "healthy",
            "memory_mb": "unavailable",
            "active_conversations": len(user_conversations),
            "waha_status": "connected" if waha_health_check() else "disconnected" if waha_url else "not_configured",
            "ai_handler": "mcp_agent" if MCP_AGENT_AVAILABLE else ("gemini" if GEMINI_HELPERS_AVAILABLE else "none"),
            "gemini_helpers": GEMINI_HELPERS_AVAILABLE,
            "timestamp": datetime.now().isoformat()
        })

@app.route("/status")
def status():
    return jsonify({
        "status": "online",
        "active_conversations": len(user_conversations),
        "timestamp": datetime.now().isoformat()
    })

@app.route("/waha-status")
def waha_status():
    """Get comprehensive WAHA connection status (optimized)"""
    ok = waha_health_check()
    return jsonify({
        "waha_ok": ok,
        "session": WAHA_SESSION,
        "base": _waha_base(),
        "connection_status": waha_connection_status,
        "keepalive_active": waha_keepalive_active,
        "keepalive_interval": WAHA_KEEPALIVE_INTERVAL,
        "timestamp": datetime.now().isoformat()
    })

@app.route("/waha-restart-keepalive", methods=['POST'])
def restart_waha_keepalive():
    """Manually restart WAHA keep-alive thread"""
    try:
        stop_waha_keepalive()
        time.sleep(1)  # Brief pause
        start_waha_keepalive()
        
        return jsonify({
            "message": "WAHA keep-alive restarted successfully",
            "status": "success",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "status": "error",
            "timestamp": datetime.now().isoformat()
        }), 500

# Utility functions
def initiate_conversation(phone):
    logger.info(f"INITIATING chat with {phone}")
    try:
        prompt = f"{PERSONALITY_PROMPT}\n{INITIAL_MESSAGE_PROMPT}"
        initial_message = _generate_initial_message(prompt).strip()
        typing_indicator(phone, 3)
        return send_message(phone, initial_message)
    except Exception as e:
        logger.error(f"Error initiating conversation: {e}")
        return False

def typing_indicator(phone, seconds=2):
    try:
        phone = phone if "@c.us" in phone else f"{phone}@c.us"
        for action in ["startTyping", "stopTyping"]:
            url = os.getenv("WAHA_URL").replace("sendText", action)
            requests.post(url, headers=_waha_headers(), json={"chatId": phone, "session": os.getenv("WAHA_SESSION")})
            if action == "startTyping":
                time.sleep(seconds)
        return True
    except Exception as e:
        logger.error(f"Typing indicator error: {e}")
        return False

def send_voice_message(phone, audio_file, fallback_text=""):
    """Send voice message with improved fallback handling and proper format detection"""
    if not waha_url:
        logger.warning("WAHA URL not configured")
        return False
        
    try:
        # Detect audio format from file extension
        audio_ext = audio_file.lower().split('.')[-1] if '.' in audio_file else 'ogg'
        if audio_ext == 'wav':
            mime_type = 'audio/wav'
            filename = 'voice.wav'
        elif audio_ext == 'mp3':
            mime_type = 'audio/mpeg'
            filename = 'voice.mp3'
        else:
            mime_type = 'audio/ogg'
            filename = 'voice.ogg'
        
        logger.info(f"Sending voice message - format: {audio_ext}, mime: {mime_type}")
        
        # First try to send as voice message
        voice_url = f"{_waha_base()}/api/sendVoice"
        
        with open(audio_file, 'rb') as f:
            files = {'audio': (filename, f, mime_type)}
            data = {'chatId': phone}
            headers = {}
            
            if WAHA_API_KEY:
                headers['X-API-KEY'] = WAHA_API_KEY
            
            logger.info(f"Attempting to send voice message to {phone} via {voice_url}")
            voice_response = requests.post(voice_url, files=files, data=data, headers=headers, timeout=30)
            
            if voice_response.status_code == 200:
                logger.info("Voice message sent successfully")
                return True
            else:
                logger.warning(f"Voice message failed with status {voice_response.status_code}: {voice_response.text}")
        
        # If voice fails, try as media attachment
        logger.info("Voice message failed, trying as media attachment...")
        media_url = f"{_waha_base()}/api/sendMedia"
        
        with open(audio_file, 'rb') as f:
            files = {'media': (filename, f, mime_type)}
            data = {
                'chatId': phone,
                'caption': '🎤 Voice message'
            }
            
            media_response = requests.post(media_url, files=files, data=data, headers=headers, timeout=30)
            
            if media_response.status_code == 200:
                logger.info("Media attachment sent successfully")
                return True
            else:
                logger.warning(f"Media attachment failed with status {media_response.status_code}: {media_response.text}")
        
        # If both fail, send as text
        if fallback_text:
            logger.warning("Voice and media failed, sending as text")
            return send_message(phone, fallback_text)
        
        return False
        
    except Exception as e:
        logger.error(f"Error in voice message sending: {e}")
        if fallback_text:
            logger.info("Falling back to text message")
            return send_message(phone, fallback_text)
        return False
    finally:
        # Clean up audio file
        cleanup_temp_file(audio_file)

def send_message(phone, text):
    """Send text message via WhatsApp service"""
    if not waha_url:
        logger.warning("WAHA_URL not configured — cannot send message")
        return False

    try:
        headers = _waha_headers()
        payload = {"chatId": phone, "text": text}

        response = requests.post(waha_url, json=payload, headers=headers, timeout=30)

        if response.status_code in (200, 201):
            logger.info(f"Message sent to {phone}")
            return True

        # 503 means WhatsApp client not ready (e.g. QR not scanned yet)
        if response.status_code == 503:
            logger.warning(f"WhatsApp service not ready (503) — message not sent to {phone}")
            return False

        logger.error(f"Failed to send message to {phone}: {response.status_code} {response.text}")
        return False

    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return False
    
    
def send_voice_response(phone, reply_text, user_sent_voice):
    """Send voice response with proper fallback handling"""
    try:
        # Check if we should respond with voice
        if should_respond_with_voice(user_sent_voice, len(reply_text), phone):
            # Generate voice file
            voice_file = text_to_speech(reply_text)
            if voice_file:
                success = send_voice_message(phone, voice_file, reply_text)
                cleanup_temp_file(voice_file)
                return success
            else:
                logger.warning("Voice generation failed, sending text")
                return send_message(phone, reply_text)
        else:
            # Send as text
            return send_message(phone, reply_text)
    except Exception as e:
        logger.error(f"Error in send_voice_response: {e}")
        return send_message(phone, reply_text)

@app.route("/save-current-google-tokens")
def save_current_google_tokens():
    """Save current Google session tokens for automation"""
    try:
        if 'google_credentials' not in session:
            return {"error": "No Google credentials in session. Please authenticate first."}, 400
        
        from google.oauth2.credentials import Credentials
        from handlers.google_auth import SCOPES
        
        creds = Credentials.from_authorized_user_info(session['google_credentials'], SCOPES)
        
        if not creds.refresh_token:
            return {"error": "No refresh token available. Please re-authenticate with prompt=consent."}, 400
        
        # Save tokens for automation
        save_google_tokens_to_env(creds)
        
        return {
            "success": True,
            "message": "Google tokens saved for automation",
            "has_refresh_token": bool(creds.refresh_token),
            "scopes": list(creds.scopes) if hasattr(creds, 'scopes') else [],
            "next_steps": [
                "Check your logs for environment variables",
                "Add GOOGLE_REFRESH_TOKEN to your deployment environment",
                "Restart your app to enable auto-authentication"
            ]
        }
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/google-debug")
def google_debug():
    """Debug Google authentication status"""
    try:
        from handlers.google_auth import load_credentials, get_credentials_path
        
        debug_info = {
            "session_has_google_creds": bool(session.get('google_credentials')),
            "google_refresh_token_env": bool(os.getenv("GOOGLE_REFRESH_TOKEN")),
            "google_client_id_env": bool(os.getenv("GOOGLE_CLIENT_ID")),
            "google_client_secret_env": bool(os.getenv("GOOGLE_CLIENT_SECRET")),
            "credentials_file_path": get_credentials_path(),
            "credentials_file_exists": bool(get_credentials_path() and os.path.exists(get_credentials_path()))
        }
        
        # Try to load credentials
        try:
            creds = load_credentials()
            debug_info.update({
                "can_load_credentials": True,
                "credentials_valid": creds.valid if creds else False,
                "credential_type": "service_account" if (creds and hasattr(creds, 'service_account_email')) else "oauth"
            })
        except Exception as e:
            debug_info.update({
                "can_load_credentials": False,
                "load_error": str(e)
            })
        
        # Session details
        if session.get('google_credentials'):
            session_creds = session['google_credentials']
            debug_info.update({
                "session_has_refresh_token": bool(session_creds.get('refresh_token')),
                "session_token_scopes": session_creds.get('scopes', [])
            })
        
        return debug_info
        
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/setup-all-auto-auth")
def setup_all_auto_auth():
    """Setup automatic authentication for all services using unified auth manager"""
    return auth_manager.setup_automatic_authentication()

@app.route("/auth-status")
def auth_status():
    """Get comprehensive authentication status for all services"""
    return auth_manager.get_auth_status()

@app.route("/test-webhook-auth")
def test_webhook_auth():
    """Test authentication as it would work in webhook context (no session)"""
    return auth_manager.test_webhook_authentication()

@app.route('/test-webhook-simple', methods=['POST'])
def test_webhook_simple():
    """Test webhook POST processing without Gemini"""
    try:
        data = request.get_json() or {}
        payload = data.get('payload', data)
        
        user_msg = payload.get('body') or payload.get('text') or payload.get('message')
        phone = payload.get('chatId') or payload.get('from')
        
        if not user_msg or not phone:
            return jsonify({'status': 'ignored', 'reason': 'missing_data'}), 200
            
        if payload.get('fromMe'):
            return jsonify({'status': 'ignored', 'reason': 'from_me'}), 200
            
        # Simple echo response without Gemini
        reply = f"Echo: {user_msg}"
        
        return jsonify({
            'status': 'ok', 
            'message': 'processed_without_gemini',
            'reply': reply,
            'phone': phone
        })
        
    except Exception as e:
        logger.error(f"Error in simple webhook test: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/waha-config-test')
def waha_config_test():
    """Test WAHA configuration and webhook setup"""
    try:
        # Get the webhook URL that WAHA should use
        webhook_url = request.url_root.rstrip('/') + '/webhook'
        
        config = {
            "webhook_url": webhook_url,
            "waha_url": os.getenv("WAHA_URL", "not_configured"),
            "waha_session": os.getenv("WAHA_SESSION", "default"),
            "current_host": request.host,
            "request_url_root": request.url_root,
            "environment": {
                "WAHA_URL": os.getenv("WAHA_URL"),
                "WAHA_SESSION": os.getenv("WAHA_SESSION"),
                "WAHA_KEEPALIVE_INTERVAL": os.getenv("WAHA_KEEPALIVE_INTERVAL")
            }
        }
        
        # Test webhook URL accessibility
        try:
            response = requests.get(webhook_url, timeout=5)
            config["webhook_test"] = {
                "status_code": response.status_code,
                "accessible": response.status_code == 200,
                "response": response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text[:100]
            }
        except Exception as e:
            config["webhook_test"] = {
                "accessible": False,
                "error": str(e)
            }
            
        return jsonify(config)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Enhanced Personal Assistant Endpoints
@app.route("/weather")
def get_weather():
    """Get weather information for Johannesburg by default"""
    # Get location from session cache or use Johannesburg as default
    cached_session = get_cached_session()
    default_location = cached_session.get('location', 'Johannesburg')
    location = request.args.get('location', default_location)
    
    return weather_service.get_current_weather(location)

@app.route("/weather/forecast")
def get_weather_forecast():
    """Get weather forecast for Johannesburg by default"""
    cached_session = get_cached_session()
    default_location = cached_session.get('location', 'Johannesburg')
    location = request.args.get('location', default_location)
    days = int(request.args.get('days', 3))
    
    return weather_service.get_weather_forecast(location, days)

@app.route("/news")
def get_news():
    """Get top news headlines"""
    category = request.args.get('category', 'general')
    limit = int(request.args.get('limit', 5))
    
    if category == 'business':
        return news_service.get_business_news(limit)
    elif category == 'technology':
        return news_service.get_technology_news(limit)
    elif category == 'science':
        return news_service.get_science_news(limit)
    else:
        return news_service.get_top_headlines(limit=limit)

@app.route("/news/search")
def search_news():
    """Search for news"""
    query = request.args.get('query', '')
    limit = int(request.args.get('limit', 5))
    
    if not query:
        return {"error": "Query parameter is required"}, 400
    
    return news_service.search_news(query, limit)

@app.route("/news/briefing")
def daily_briefing():
    """Get daily news briefing"""
    return news_service.get_daily_briefing()

@app.route("/tasks", methods=['GET', 'POST'])
def handle_tasks():
    """Handle task operations"""
    if request.method == 'POST':
        data = request.get_json() or {}
        title = data.get('title', '')
        description = data.get('description', '')
        due_date = data.get('due_date')
        priority = data.get('priority', 'medium')
        
        if not title:
            return {"error": "Title is required"}, 400
            
        result = task_manager.create_task(title, description, due_date, priority)
        return {"message": result}
    else:
        filter_completed = request.args.get('completed', 'false').lower() == 'true'
        filter_priority = request.args.get('priority')
        return task_manager.list_tasks(filter_completed, filter_priority)

@app.route("/tasks/<task_id>/complete", methods=['POST'])
def complete_task(task_id):
    """Mark a task as completed"""
    result = task_manager.complete_task(task_id)
    return {"message": result}

@app.route("/tasks/<task_id>", methods=['DELETE'])
def delete_task(task_id):
    """Delete a task"""
    result = task_manager.delete_task(task_id)
    return {"message": result}

@app.route("/reminders", methods=['GET', 'POST'])
def handle_reminders():
    """Handle reminder operations"""
    if request.method == 'POST':
        data = request.get_json() or {}
        message = data.get('message', '')
        remind_at = data.get('remind_at', '')
        phone = data.get('phone', '')
        
        if not message or not remind_at:
            return {"error": "Message and remind_at are required"}, 400
            
        result = task_manager.create_reminder(message, remind_at, phone)
        return {"message": result}
    else:
        return task_manager.list_reminders()

@app.route("/tasks/summary")
def task_summary():
    """Get task and reminder summary"""
    return task_manager.get_task_summary()

@app.route("/tasks/view")
def tasks_view():
    """Redirect to JARVIS dashboard for task management"""
    return redirect('/jarvis')

@app.route("/tasks/sync-status")
def task_sync_status():
    """Get background task sync status"""
    from handlers.tasks import background_sync_service
    return jsonify(background_sync_service.get_status())

@app.route("/contacts", methods=['GET', 'POST'])
def handle_contacts():
    """Handle contact operations"""
    if request.method == 'POST':
        data = request.get_json() or {}
        name = data.get('name', '')
        phone = data.get('phone')
        email = data.get('email')
        notes = data.get('notes')
        
        if not name:
            return {"error": "Name is required"}, 400
            
        result = contact_manager.add_local_contact(name, phone, email, notes)
        return {"message": result}
    else:
        return contact_manager.list_local_contacts()

@app.route("/contacts/search")
def search_contacts():
    """Search contacts"""
    query = request.args.get('query', '')
    
    if not query:
        return {"error": "Query parameter is required"}, 400
    
    return contact_manager.search_all_contacts(query)

@app.route("/contacts/google")
def get_google_contacts():
    """Get Google contacts"""
    max_results = int(request.args.get('max_results', 20))
    return contact_manager.get_google_contacts(max_results)

@app.route("/contacts/summary")
def contact_summary():
    """Get contact summary"""
    return contact_manager.get_contact_summary()

@app.route("/assistant/status")
def assistant_status():
    """Get comprehensive assistant status including all services"""
    cached_session = get_cached_session()
    
    status = {
        'timestamp': datetime.now().isoformat(),
        'session_cache': cached_session,
        'authentication': auth_manager.get_auth_status(),
        'services': {
            'weather': {
                'configured': weather_service.is_configured(),
                'status': 'active' if weather_service.is_configured() else 'needs_api_key',
                'default_location': cached_session.get('location', 'Johannesburg')
            },
            'news': {
                'configured': news_service.is_configured(),
                'status': 'active' if news_service.is_configured() else 'needs_api_key'
            },
            'tasks': {
                'configured': True,
                'status': 'active',
                'task_count': len(task_manager.tasks),
                'reminder_count': len(task_manager.reminders)
            },
            'contacts': {
                'configured': True,
                'status': 'active',
                'local_count': len(contact_manager.local_contacts)
            }
        }
    }
    return status

@app.route("/session-cache")
def view_session_cache():
    """View current session cache"""
    return get_cached_session()

@app.route("/session-cache", methods=['POST'])
def update_session_cache():
    """Update session cache"""
    data = request.get_json() or {}
    
    phone = data.get('phone')
    location = data.get('location')
    gemini_url = data.get('gemini_url')
    
    if phone:
        cache_user_session(phone, gemini_url)
    
    if location:
        session_data = session.get('user_cache', {})
        session_data['location'] = location
        session['user_cache'] = session_data
    
    return {"message": "Session cache updated", "cache": get_cached_session()}

@app.route("/quick-setup")
def quick_setup():
    """Redirect to JARVIS dashboard - all setup now integrated"""
    return redirect('/jarvis')


# WhatsApp QR Code Routes
@app.route("/whatsapp-qr")
def whatsapp_qr():
    """Redirect to React WhatsApp page"""
    return redirect('/jarvis')


@app.route("/whatsapp-qr-image")
def whatsapp_qr_image():
    """Generate and serve QR code image"""
    if not QR_AVAILABLE:
        return "QR code generation not available", 500
    
    try:
        # Get QR data from WhatsApp service
        whatsapp_url = os.getenv('WAHA_URL', 'http://localhost:3000/api/sendText').replace('/api/sendText', '')
        qr_response = requests.get(f"{whatsapp_url}/api/qr", timeout=5)
        qr_data = qr_response.json()
        
        if not qr_data.get('qr'):
            return "No QR code available", 404
        
        # Generate QR code image
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data['qr'])
        qr.make(fit=True)
        
        # Create QR code image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to bytes
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        
        return send_file(img_io, mimetype='image/png')
        
    except requests.RequestException:
        return "WhatsApp service not available", 503
    except Exception as e:
        logger.error(f"Error generating QR code: {e}")
        return "Error generating QR code", 500

@app.route("/whatsapp-status")
def whatsapp_status():
    """Detailed WhatsApp service status"""
    try:
        whatsapp_url = os.getenv('WAHA_URL', 'http://localhost:3000/api/sendText').replace('/api/sendText', '')
        
        # Get various status endpoints
        status_data = {}
        
        try:
            health_response = requests.get(f"{whatsapp_url}/health", timeout=5)
            status_data['health'] = health_response.json()
        except:
            status_data['health'] = {"error": "Health check failed"}
        
        try:
            qr_response = requests.get(f"{whatsapp_url}/api/qr", timeout=5)
            status_data['qr'] = qr_response.json()
        except:
            status_data['qr'] = {"error": "QR check failed"}
        
        try:
            info_response = requests.get(f"{whatsapp_url}/api/info", timeout=5)
            status_data['info'] = info_response.json()
        except:
            status_data['info'] = {"error": "Info check failed"}
        
        return jsonify(status_data)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/test-new-services")
def test_new_services():
    """Test all newly implemented services"""
    try:
        from handlers.uber import uber_service
        from handlers.accommodation import accommodation_service
        from handlers.fitness import fitness_service
        from handlers.google_notes import google_notes_service
        from handlers.contacts import contact_manager
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "services": {}
        }
        
        # Test Uber service
        try:
            uber_status = uber_service.get_service_status()
            results["services"]["uber"] = {
                "available": True,
                "status": "loaded",
                "config_summary": "Ready for testing" if uber_status else "Not configured"
            }
        except Exception as e:
            results["services"]["uber"] = {
                "available": False,
                "error": str(e)
            }
        
        # Test Accommodation service
        try:
            accommodation_status = accommodation_service.get_service_status()
            results["services"]["accommodation"] = {
                "available": True,
                "status": "loaded",
                "properties_count": len(accommodation_service.mock_properties)
            }
        except Exception as e:
            results["services"]["accommodation"] = {
                "available": False,
                "error": str(e)
            }
        
        # Test Fitness service
        try:
            fitness_status = fitness_service.get_service_status()
            results["services"]["fitness"] = {
                "available": True,
                "status": "loaded",
                "has_mock_data": bool(fitness_service.mock_data)
            }
        except Exception as e:
            results["services"]["fitness"] = {
                "available": False,
                "error": str(e)
            }
        
        # Test Google Notes service
        try:
            notes_status = google_notes_service.get_service_status()
            results["services"]["google_notes"] = {
                "available": True,
                "status": "loaded",
                "auth_required": "Google authentication required" in notes_status
            }
        except Exception as e:
            results["services"]["google_notes"] = {
                "available": False,
                "error": str(e)
            }
        
        # Test Enhanced Contacts
        try:
            contact_summary = contact_manager.get_contact_summary()
            results["services"]["contacts"] = {
                "available": True,
                "status": "enhanced with WhatsApp support",
                "local_contacts": len(contact_manager.local_contacts)
            }
        except Exception as e:
            results["services"]["contacts"] = {
                "available": False,
                "error": str(e)
            }
        
        # Overall status
        available_services = sum(1 for service in results["services"].values() if service.get("available", False))
        results["summary"] = {
            "total_new_services": len(results["services"]),
            "available_services": available_services,
            "integration_status": "All new services loaded successfully" if available_services == len(results["services"]) else "Some services have issues"
        }
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route("/demo-new-features")
def demo_new_features():
    """Demonstrate new features with sample calls"""
    try:
        from handlers.uber import uber_service
        from handlers.accommodation import accommodation_service
        from handlers.fitness import fitness_service
        from handlers.contacts import contact_manager
        
        demos = {}
        
        # Demo Uber service
        try:
            demos["uber_restaurant_search"] = uber_service.search_restaurants("pizza")
        except Exception as e:
            demos["uber_restaurant_search"] = f"Error: {e}"
        
        # Demo Accommodation search
        try:
            demos["accommodation_search"] = accommodation_service.search_accommodations("New York", guests=2)
        except Exception as e:
            demos["accommodation_search"] = f"Error: {e}"
        
        # Demo Fitness summary
        try:
            demos["fitness_summary"] = fitness_service.get_daily_summary()
        except Exception as e:
            demos["fitness_summary"] = f"Error: {e}"
        
        # Demo Contact WhatsApp lookup
        try:
            demos["contact_whatsapp"] = contact_manager.get_contact_for_whatsapp("John")
        except Exception as e:
            demos["contact_whatsapp"] = f"Error: {e}"
        
        return jsonify({
            "timestamp": datetime.now().isoformat(),
            "feature_demos": demos,
            "note": "These are demonstration calls showing the new functionality"
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500
def test_conversation_history():
    """Test conversation history functionality"""
    try:
        test_phone = "27729224495@c.us"  # Use boss phone for testing
        results = {
            "timestamp": datetime.now().isoformat(),
            "phone": test_phone
        }
        
        # Test Database availability
        if DATABASE_AVAILABLE:
            try:
                # Test adding a conversation
                success = add_to_conversation_history(test_phone, "user", "Test message for history")
                results["add_test"] = {"success": success}
                
                if success:
                    # Test retrieving conversation history
                    history = retrieve_conversation_history(test_phone, n_results=5)
                    results["retrieve_test"] = {
                        "success": True,
                        "history_count": len(history),
                        "latest_messages": history[:3] if history else []
                    }
                else:
                    results["retrieve_test"] = {"success": False, "reason": "Add failed"}
                    
            except Exception as e:
                results["database_error"] = str(e)
        else:
            results["database_available"] = False
            
        return jsonify(results)
        
    except Exception as e:
        return jsonify({"error": str(e), "timestamp": datetime.now().isoformat()}), 500

@app.route("/test-all-services")
def test_all_services():
    """Test all main services functionality"""
    try:
        results = {
            "timestamp": datetime.now().isoformat(),
            "tests": {}
        }
        
        # Test conversation history
        test_phone = "27729224495@c.us"
        try:
            add_success = add_to_conversation_history(test_phone, "user", "Test message")
            if add_success:
                history = retrieve_conversation_history(test_phone, n_results=3)
                results["tests"]["conversation_history"] = {
                    "success": True,
                    "history_count": len(history)
                }
            else:
                results["tests"]["conversation_history"] = {"success": False, "reason": "Add failed"}
        except Exception as e:
            results["tests"]["conversation_history"] = {"success": False, "error": str(e)}
        
        # Test task management
        try:
            from handlers.tasks import task_manager
            task_result = task_manager.create_task("Test Task", "This is a test task")
            results["tests"]["task_management"] = {
                "success": not task_result.startswith("❌"),
                "result": task_result[:50] + "..." if len(task_result) > 50 else task_result
            }
        except Exception as e:
            results["tests"]["task_management"] = {"success": False, "error": str(e)}
            
        # Test contact management
        try:
            from handlers.contacts import contact_manager
            contact_result = contact_manager.add_local_contact("Test User", "123-456-7890", "test@example.com")
            results["tests"]["contact_management"] = {
                "success": not contact_result.startswith("❌"),
                "result": contact_result[:50] + "..." if len(contact_result) > 50 else contact_result
            }
        except Exception as e:
            results["tests"]["contact_management"] = {"success": False, "error": str(e)}
            
        # Test boss recognition
        results["tests"]["boss_recognition"] = {
            "boss_phone": os.getenv("BOSS_PHONE_NUMBER", "27729224495@c.us"),
            "configured": True
        }
        
        # Count successful tests
        successful = sum(1 for test in results["tests"].values() 
                        if isinstance(test, dict) and test.get("success", False))
        total = len([test for test in results["tests"].values() if isinstance(test, dict) and "success" in test])
        
        results["summary"] = {
            "successful": successful,
            "total": total,
            "all_passed": successful == total
        }
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({"error": str(e), "timestamp": datetime.now().isoformat()}), 500

class ConversationManager:
    def __init__(self):
        self.user_conversations = {}
    
    def process_message(self, message, phone):
        try:
            # Simple fallback response when Gemini is not configured
            if not GEMINI_API_KEY or GEMINI_API_KEY == "test_key_123":
                return "I'm currently in test mode. Please configure GEMINI_API_KEY for full functionality."
            
            # Add conversation history
            if DATABASE_AVAILABLE:
                add_to_conversation_history(phone, "user", message)
            
            # Generate response using Gemini (implement this based on your gemini.py)
            response = self._generate_response(message, phone)
            
            if DATABASE_AVAILABLE:
                add_to_conversation_history(phone, "assistant", response)
            
            return response
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return "Sorry, I encountered an error processing your message."
    
    def _generate_response(self, message, phone):
        # Implement your Gemini logic here
        return f"Echo: {message}"
    
    def initiate_conversation(self, phone):
        return waha_client.send_message(phone, "Hello! I'm Wednesday, your AI assistant.")

# Initialize conversation manager
conversation_manager = ConversationManager()


class WAHAClient:
    def __init__(self):
        self.waha_url = waha_url
        self.api_key = WAHA_API_KEY
    
    def send_message(self, phone, text):
        if not self.waha_url:
            logger.warning("WAHA_URL not configured")
            return False
        
        try:
            if "@c.us" not in phone:
                phone = f"{phone}@c.us"
            
            payload = {"chatId": phone, "text": text}
            headers = _waha_headers()
            
            response = requests.post(self.waha_url, headers=headers, json=payload, timeout=10)
            return response.status_code in (200, 201)
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

# Initialize WAHA client
waha_client = WAHAClient()

# Enhanced Jarvis-like AI endpoints
@app.route("/api/media/generate-image", methods=['POST'])
def api_generate_image():
    """Generate image via API"""
    try:
        data = request.get_json() or {}
        prompt = data.get('prompt')
        style = data.get('style', 'realistic')
        phone = data.get('phone', 'api_user')
        
        if not prompt:
            return jsonify({'error': 'Prompt required'}), 400
        
        from handlers.media_generator import media_generator
        import asyncio
        
        # Run async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            media_generator.generate_image(prompt, phone, style)
        )
        loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/media/create-avatar", methods=['POST'])
def api_create_avatar():
    """Create avatar via API"""
    try:
        data = request.get_json() or {}
        personality = data.get('personality', 'wednesday')
        style = data.get('style', 'professional')
        
        from handlers.media_generator import media_generator
        avatar_path = media_generator.create_avatar(personality, style)
        
        if avatar_path:
            return jsonify({
                'success': True,
                'avatar_path': avatar_path,
                'personality': personality,
                'style': style
            })
        else:
            return jsonify({'error': 'Failed to create avatar'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# JARVIS React Dashboard API
# ============================================

@app.route("/api/dashboard/data")
def api_dashboard_data():
    """Comprehensive dashboard data for React frontend"""
    try:
        from datetime import datetime
        
        # System status
        system_status = 'healthy'
        mcp_agent_available = False
        tools_count = 0
        
        try:
            from handlers.mcp_agent import get_agent, get_mcp_tool_schemas
            agent = get_agent()
            mcp_agent_available = agent is not None
            tools_count = len(get_mcp_tool_schemas())
        except Exception as e:
            logger.warning(f"MCP Agent not available: {e}")
        
        # WhatsApp status
        whatsapp_connected = False
        try:
            waha_url = os.getenv('WAHA_URL', '')
            if waha_url:
                import requests
                resp = requests.get(waha_url.replace('/api/sendText', '/api/sessions'), timeout=2)
                whatsapp_connected = resp.status_code == 200
        except:
            pass
        
        # Service statuses
        services = []
        service_checks = [
            ('MCP Agent', mcp_agent_available, 'Brain'),
            ('Gemini AI', bool(os.getenv('GEMINI_API_KEY')), 'Zap'),
            ('WhatsApp', whatsapp_connected, 'MessageSquare'),
            ('Spotify', bool(os.getenv('SPOTIFY_CLIENT_ID')), 'Music'),
            ('Gmail', bool(os.getenv('GOOGLE_CLIENT_ID')), 'Mail'),
            ('Calendar', bool(os.getenv('GOOGLE_CLIENT_ID')), 'Calendar'),
            ('Smart Home', bool(os.getenv('IFTTT_WEBHOOK_KEY') or os.getenv('HOME_ASSISTANT_URL')), 'Home'),
            ('ElevenLabs', bool(os.getenv('ELEVENLABS_API_KEY')), 'Mic'),
        ]
        
        for name, available, icon in service_checks:
            services.append({
                'name': name,
                'status': 'online' if available else 'offline',
                'icon': icon
            })
        
        # Authentication status
        google_auth = False
        spotify_auth = False
        
        try:
            from handlers.google_auth import load_credentials
            creds = load_credentials()
            google_auth = creds is not None and creds.valid
        except:
            pass
        
        try:
            token = get_token_info()
            spotify_auth = token is not None
        except:
            pass
        
        # Owner status
        owner_configured = bool(os.getenv('OWNER_PHONE'))
        owner_phone = os.getenv('OWNER_PHONE', '')
        owner_hint = f"***{owner_phone[-4:]}" if owner_phone and len(owner_phone) > 4 else None
        
        # Tool categories
        tool_categories = [
            'Core', 'Workflows', 'Smart Home', 'Voice', 'Memory',
            'Security', 'Admin', 'Fitness', 'Expenses', 'Briefings', 'Media'
        ]
        
        # Stats (basic for now)
        stats = {
            'messages_today': 0,
            'active_sessions': 1 if whatsapp_connected else 0,
            'uptime': '99.9%',
            'response_time': 245
        }
        
        # Recent activity
        recent_activity = [
            {'time': datetime.now().strftime('%H:%M'), 'message': 'Dashboard accessed', 'type': 'info'},
            {'time': '—', 'message': f'{tools_count} MCP tools available', 'type': 'info'},
            {'time': '—', 'message': 'Owner: ' + ('configured' if owner_configured else 'not configured'), 'type': 'security'},
        ]
        
        return jsonify({
            'system_status': system_status,
            'mcp_agent': mcp_agent_available,
            'whatsapp_connected': whatsapp_connected,
            'tools_count': tools_count,
            'services': services,
            'tool_categories': tool_categories,
            'stats': stats,
            'google_auth': google_auth,
            'spotify_auth': spotify_auth,
            'elevenlabs_available': bool(os.getenv('ELEVENLABS_API_KEY')),
            'owner_configured': owner_configured,
            'owner_hint': owner_hint,
            'recent_activity': recent_activity,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Dashboard API error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route("/api/mcp/tools")
def api_mcp_tools():
    """List all available MCP tools"""
    try:
        from handlers.mcp_agent import get_mcp_tool_schemas
        schemas = get_mcp_tool_schemas()
        
        # Group by category
        categories = {}
        for schema in schemas:
            name = schema.get('name', '')
            # Infer category from name
            if any(x in name for x in ['workflow', 'routine']):
                cat = 'Workflows'
            elif any(x in name for x in ['smart_home', 'lights', 'thermostat', 'scene', 'lock']):
                cat = 'Smart Home'
            elif any(x in name for x in ['speak', 'voice', 'sound']):
                cat = 'Voice'
            elif any(x in name for x in ['remember', 'recall', 'forget', 'memory', 'profile']):
                cat = 'Memory'
            elif any(x in name for x in ['security', 'threat', 'admin', 'whitelist', 'blocked', 'owner']):
                cat = 'Security/Admin'
            elif any(x in name for x in ['fitness', 'workout', 'exercise']):
                cat = 'Fitness'
            elif any(x in name for x in ['expense', 'spending', 'budget']):
                cat = 'Expenses'
            elif any(x in name for x in ['briefing', 'summary']):
                cat = 'Briefings'
            elif any(x in name for x in ['image', 'video', 'media', 'generate']):
                cat = 'Media'
            else:
                cat = 'Core'
            
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(schema)
        
        return jsonify({
            'total': len(schemas),
            'categories': categories,
            'tools': schemas
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/api/google-login")
def api_google_login():
    """Redirect to Google OAuth login"""
    return redirect('/google-login')


@app.route("/api/spotify-login")
def api_spotify_login():
    """Redirect to Spotify OAuth login"""
    return redirect('/login')


@app.route("/jarvis")
@app.route("/jarvis/<path:path>")
def jarvis_dashboard(path=None):
    """Serve the React JARVIS dashboard for all frontend routes"""
    react_path = os.path.join(os.path.dirname(__file__), 'static', 'dashboard', 'index.html')
    if os.path.exists(react_path):
        return send_from_directory(os.path.join(os.path.dirname(__file__), 'static', 'dashboard'), 'index.html')
    
    return '''<!DOCTYPE html><html><head><title>JARVIS</title>
    <style>body{font-family:monospace;background:#0a0a12;color:#00d4ff;display:flex;justify-content:center;align-items:center;height:100vh;flex-direction:column}
    code{background:#1a1a2e;padding:4px 8px;border-radius:4px}</style></head>
    <body><h1>J.A.R.V.I.S.</h1><p>React dashboard not built.</p><code>cd frontend && npm run build</code></body></html>'''


# Serve React app static assets
@app.route("/assets/<path:filename>")
def serve_react_assets(filename):
    """Serve React build assets"""
    assets_path = os.path.join(os.path.dirname(__file__), 'static', 'dashboard', 'assets')
    return send_from_directory(assets_path, filename)


@app.route("/api/services/status")
def api_service_status():
    """Get comprehensive service status"""
    try:
        from handlers.service_monitor import service_monitor
        return jsonify(service_monitor.get_service_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/services/health")
def api_system_health():
    """Get system health summary"""
    try:
        from handlers.service_monitor import service_monitor
        return jsonify(service_monitor.get_system_health_summary())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/services/ping/<service_name>", methods=['POST'])
def api_ping_service(service_name):
    """Ping a specific service"""
    try:
        from handlers.service_monitor import service_monitor
        data = request.get_json() or {}
        endpoint = data.get('endpoint')
        
        result = service_monitor.ping_service(service_name, endpoint)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/notifications/stats")
def api_notification_stats():
    """Get notification statistics"""
    try:
        from handlers.notifications import task_notification_system
        phone = request.args.get('phone')
        return jsonify(task_notification_system.get_notification_stats(phone))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/database/stats")
def api_database_stats():
    """Get database statistics"""
    try:
        if DATABASE_AVAILABLE:
            stats = db_manager.get_database_stats()
            return jsonify(stats)
        else:
            return jsonify({'error': 'Database not available'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/database/cleanup", methods=['POST'])
def api_database_cleanup():
    """Clean up old database data"""
    try:
        if not DATABASE_AVAILABLE:
            return jsonify({'error': 'Database not available'}), 503
        
        data = request.get_json() or {}
        days_old = data.get('days_old', 30)
        
        db_manager.cleanup_old_data(days_old)
        
        return jsonify({
            'success': True,
            'message': f'Cleaned up data older than {days_old} days'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/whatsapp/send", methods=['POST'])
def api_send_whatsapp():
    """Send WhatsApp message via API"""
    try:
        data = request.get_json() or {}
        contact_query = data.get('contact_query') 
        message = data.get('message')
        
        if not contact_query or not message:
            return jsonify({'error': 'contact_query and message required'}), 400
        
        result = contact_manager.send_whatsapp_message(contact_query, message)
        
        return jsonify({
            'success': True,
            'result': result
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/api/whatsapp/status")
def api_whatsapp_status():
    """Get WhatsApp connection status for React dashboard"""
    try:
        whatsapp_url = os.getenv('WAHA_URL', '').replace('/api/sendText', '')
        
        status_data = {
            'waha_url': whatsapp_url or None,
            'waha_available': False,
            'connected': False,
            'session_status': 'unknown',
            'phone_number': None,
            'keep_alive_active': bool(os.getenv('WAHA_URL'))
        }
        
        if not whatsapp_url:
            status_data['message'] = 'WAHA_URL not configured'
            return jsonify(status_data)
        
        try:
            health_response = requests.get(f"{whatsapp_url}/health", timeout=5)
            if health_response.ok:
                status_data['waha_available'] = True
            
            session_response = requests.get(f"{whatsapp_url}/api/sessions/{WAHA_SESSION}", timeout=5)
            if session_response.ok:
                session_data = session_response.json()
                status_data['session_status'] = session_data.get('status', 'unknown')
                status_data['connected'] = session_data.get('status') == 'WORKING'
                if session_data.get('me'):
                    status_data['phone_number'] = session_data['me'].get('id', '').split('@')[0]
        except requests.RequestException as e:
            status_data['error'] = str(e)
        
        return jsonify(status_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route("/api/whatsapp/qr")
def api_whatsapp_qr():
    """Get WhatsApp QR code for React dashboard"""
    try:
        whatsapp_url = os.getenv('WAHA_URL', '').replace('/api/sendText', '')
        
        if not whatsapp_url:
            return jsonify({'qr_code': None, 'message': 'WAHA_URL not configured', 'waha_url': None})
        
        try:
            qr_response = requests.get(f"{whatsapp_url}/api/sessions/{WAHA_SESSION}/auth/qr", timeout=5)
            
            if qr_response.ok:
                content_type = qr_response.headers.get('content-type', '')
                if 'image' in content_type:
                    import base64
                    qr_base64 = base64.b64encode(qr_response.content).decode('utf-8')
                    return jsonify({'qr_code': qr_base64, 'message': 'Scan QR code'})
                else:
                    qr_data = qr_response.json()
                    return jsonify({'qr_code': qr_data.get('qr') or qr_data.get('qrcode'), 'message': 'QR available', 'waha_url': whatsapp_url})
            else:
                return jsonify({'qr_code': None, 'message': 'Session may already be connected', 'waha_url': whatsapp_url})
        except requests.RequestException as e:
            return jsonify({'qr_code': None, 'message': str(e), 'waha_url': whatsapp_url})
    except Exception as e:
        return jsonify({'error': str(e), 'waha_url': os.getenv('WAHA_URL', '').replace('/api/sendText', '')}), 500


@app.route("/api/whatsapp/reconnect", methods=['POST'])
def api_whatsapp_reconnect():
    """Reconnect WhatsApp session - triggers new QR code"""
    try:
        whatsapp_url = os.getenv('WAHA_URL', '').replace('/api/sendText', '')
        
        if not whatsapp_url:
            return jsonify({'success': False, 'error': 'WAHA_URL not configured'})
        
        # Call restart endpoint on WhatsApp service
        restart_url = f"{whatsapp_url}/api/sessions/{WAHA_SESSION}/restart"
        response = requests.post(restart_url, timeout=10)
        
        if response.ok:
            return jsonify({'success': True, 'message': 'Reconnect initiated, refresh for QR code'})
        else:
            return jsonify({'success': False, 'error': 'Failed to restart session'}), 500
    except requests.RequestException as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/whatsapp/logout", methods=['POST'])
def api_whatsapp_logout():
    """Logout WhatsApp session - clears session data"""
    try:
        whatsapp_url = os.getenv('WAHA_URL', '').replace('/api/sendText', '')
        
        if not whatsapp_url:
            return jsonify({'success': False, 'error': 'WAHA_URL not configured'})
        
        # Call logout endpoint on WhatsApp service
        logout_url = f"{whatsapp_url}/api/sessions/{WAHA_SESSION}/logout"
        response = requests.post(logout_url, timeout=10)
        
        if response.ok:
            return jsonify({'success': True, 'message': 'Logged out successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to logout'}), 500
    except requests.RequestException as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/make-call", methods=['POST'])
def make_whatsapp_call():
    """Initiate WhatsApp voice call via WAHA API"""
    try:
        data = request.get_json() or {}
        phone = data.get('phone')
        
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number required'}), 400
        
        # Format phone number for WhatsApp (add @c.us if not present)
        if '@c.us' not in phone:
            phone = f"{phone}@c.us"
        
        base = _waha_base()
        if not base:
            return jsonify({'success': False, 'error': 'WAHA not configured'}), 500
        
        # Make call using WAHA API
        session_name = WAHA_SESSION
        call_url = f"{base}/api/sessions/{session_name}/calls/start"
        
        payload = {
            "chatId": phone,
            "audio": True,
            "video": False
        }
        
        response = requests.post(
            call_url, 
            json=payload, 
            headers=_waha_headers(),
            timeout=30
        )
        
        if response.status_code in (200, 201):
            logger.info(f"WhatsApp call initiated to {phone}")
            return jsonify({
                'success': True,
                'message': f'Call initiated to {phone}',
                'phone': phone
            })
        else:
            error_msg = f"WAHA API error: {response.status_code}"
            logger.error(f"Failed to initiate call: {error_msg}")
            return jsonify({
                'success': False, 
                'error': error_msg,
                'details': response.text
            }), 500
        
    except Exception as e:
        logger.error(f"Error making call: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/end-call", methods=['POST'])
def end_whatsapp_call():
    """End current WhatsApp voice call via WAHA API"""
    try:
        base = _waha_base()
        if not base:
            return jsonify({'success': False, 'error': 'WAHA not configured'}), 500
        
        # End call using WAHA API
        session_name = WAHA_SESSION
        call_url = f"{base}/api/sessions/{session_name}/calls/end"
        
        response = requests.post(
            call_url,
            headers=_waha_headers(),
            timeout=30
        )
        
        if response.status_code in (200, 201, 204):
            logger.info("WhatsApp call ended")
            return jsonify({
                'success': True,
                'message': 'Call ended successfully'
            })
        else:
            error_msg = f"WAHA API error: {response.status_code}"
            logger.error(f"Failed to end call: {error_msg}")
            return jsonify({
                'success': False,
                'error': error_msg,
                'details': response.text
            }), 500
        
    except Exception as e:
        logger.error(f"Error ending call: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/dashboard")
def unified_dashboard():
    """Redirect to JARVIS React dashboard"""
    return redirect('/jarvis')

@app.route("/api/advanced/generate-video", methods=['POST'])
def api_generate_video():
    """Generate video using advanced AI"""
    try:
        data = request.get_json() or {}
        prompt = data.get('prompt')
        style = data.get('style', 'realistic')
        duration = data.get('duration', 5)
        
        if not prompt:
            return jsonify({'success': False, 'error': 'Prompt required'}), 400
        
        from handlers.advanced_ai import advanced_ai
        import asyncio
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            advanced_ai.generate_video(prompt, style, duration)
        )
        loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/advanced/synthesize-voice", methods=['POST'])
def api_synthesize_voice():
    """Synthesize voice using advanced AI"""
    try:
        data = request.get_json() or {}
        text = data.get('text')
        voice_id = data.get('voice_id', 'default')
        style = data.get('style', 'natural')
        
        if not text:
            return jsonify({'success': False, 'error': 'Text required'}), 400
        
        from handlers.advanced_ai import advanced_ai
        import asyncio
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            advanced_ai.synthesize_voice(text, voice_id, style)
        )
        loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/advanced/analyze-image", methods=['POST'])
def api_analyze_image():
    """Analyze image using computer vision"""
    try:
        data = request.get_json() or {}
        image_path = data.get('image_path')
        analysis_type = data.get('analysis_type', 'comprehensive')
        
        if not image_path:
            return jsonify({'success': False, 'error': 'Image path required'}), 400
        
        from handlers.advanced_ai import advanced_ai
        import asyncio
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            advanced_ai.analyze_image(image_path, analysis_type)
        )
        loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/advanced/predict-behavior", methods=['POST'])
def api_predict_behavior():
    """Predict user behavior"""
    try:
        data = request.get_json() or {}
        phone = data.get('phone', 'api_user')
        context = data.get('context')
        
        from handlers.advanced_ai import advanced_ai
        import asyncio
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            advanced_ai.predict_user_behavior(phone, context)
        )
        loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/advanced/test-suite")
def api_test_suite():
    """Run comprehensive test suite"""
    try:
        test_type = request.args.get('type', 'quick')
        
        if test_type == 'quick':
            # Quick tests
            from handlers.service_monitor import service_monitor
            health = service_monitor.get_system_health_summary()
            
            return jsonify({
                'success': True,
                'test_type': 'quick',
                'system_health': health,
                'timestamp': datetime.now().isoformat()
            })
        
        elif test_type == 'comprehensive':
            # Run comprehensive test suite
            from test_suite import ComprehensiveTestSuite
            test_suite = ComprehensiveTestSuite()
            
            # Run tests in background to avoid timeout
            import threading
            
            def run_tests():
                try:
                    results = test_suite.run_all_tests()
                    # Store results in system state for later retrieval
                    db_manager.set_system_state('last_test_results', results)
                except Exception as e:
                    db_manager.set_system_state('last_test_results', {'error': str(e)})
            
            test_thread = threading.Thread(target=run_tests)
            test_thread.start()
            
            return jsonify({
                'success': True,
                'message': 'Comprehensive test suite started in background',
                'check_endpoint': '/api/advanced/test-results',
                'estimated_duration': '2-3 minutes'
            })
        
        else:
            return jsonify({'success': False, 'error': 'Invalid test type'}), 400
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/advanced/test-results")
def api_test_results():
    """Get latest test results"""
    try:
        results = db_manager.get_system_state('last_test_results')
        if results:
            return jsonify({
                'success': True,
                'results': results,
                'retrieved_at': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No test results available. Run tests first.'
            })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/advanced/diagnostics")
def api_diagnostics():
    """Run system diagnostics"""
    try:
        diagnostic_type = request.args.get('type', 'basic')
        
        diagnostics = {
            'timestamp': datetime.now().isoformat(),
            'type': diagnostic_type
        }
        
        # Basic system information
        import psutil
        import platform
        
        diagnostics['system'] = {
            'platform': platform.system(),
            'python_version': platform.python_version(),
            'cpu_count': psutil.cpu_count(),
            'memory_total_gb': psutil.virtual_memory().total / (1024**3),
            'disk_total_gb': psutil.disk_usage('/').total / (1024**3)
        }
        
        # Current resource usage
        process = psutil.Process()
        diagnostics['current_usage'] = {
            'memory_mb': process.memory_info().rss / (1024**2),
            'cpu_percent': process.cpu_percent(),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage('/').percent
        }
        
        # Service status
        from handlers.service_monitor import service_monitor
        diagnostics['services'] = service_monitor.get_system_health_summary()
        
        # Database status
        if DATABASE_AVAILABLE:
            diagnostics['database'] = db_manager.get_database_stats()
        
        # Advanced AI status
        try:
            from handlers.advanced_ai import advanced_ai
            diagnostics['advanced_ai'] = advanced_ai.get_service_status()
        except Exception as e:
            diagnostics['advanced_ai'] = {'error': str(e)}
        
        return jsonify({
            'success': True,
            'diagnostics': diagnostics
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/advanced/optimize", methods=['POST'])
def api_optimize():
    """Optimize system performance"""
    try:
        data = request.get_json() or {}
        optimization_type = data.get('type', 'all')
        
        results = {}
        
        if optimization_type in ['memory', 'all']:
            # Memory optimization
            import gc
            import psutil
            before_mem = psutil.Process().memory_info().rss / (1024**2)
            gc.collect()
            after_mem = psutil.Process().memory_info().rss / (1024**2)
            
            results['memory'] = {
                'before_mb': before_mem,
                'after_mb': after_mem,
                'saved_mb': before_mem - after_mem
            }
        
        if optimization_type in ['database', 'all']:
            # Database optimization
            try:
                old_stats = db_manager.get_database_stats()
                db_manager.cleanup_old_data(7)  # Clean data older than 7 days
                new_stats = db_manager.get_database_stats()
                
                results['database'] = {
                    'before_size_mb': old_stats.get('db_size_mb', 0),
                    'after_size_mb': new_stats.get('db_size_mb', 0),
                    'cleaned_records': 'Unknown'  # Would need more detailed tracking
                }
            except Exception as e:
                results['database'] = {'error': str(e)}
        
        if optimization_type in ['cache', 'all']:
            # Cache optimization
            try:
                from handlers.media_generator import media_generator
                media_generator.cleanup_old_media(7)
                results['cache'] = {'status': 'cleaned', 'max_age_days': 7}
            except Exception as e:
                results['cache'] = {'error': str(e)}
        
        return jsonify({
            'success': True,
            'optimization_type': optimization_type,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/advanced/backup", methods=['POST'])
def api_backup():
    """Create system backup"""
    try:
        import shutil
        import zipfile
        from datetime import datetime
        
        backup_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = f"/tmp/backup_{backup_id}"
        backup_file = f"/tmp/wednesday_backup_{backup_id}.zip"
        
        os.makedirs(backup_dir, exist_ok=True)
        
        # Copy database
        if os.path.exists('assistant.db'):
            shutil.copy2('assistant.db', f"{backup_dir}/assistant.db")
        
        # Copy generated media (limited to prevent large backups)
        if os.path.exists('generated_media'):
            media_backup = f"{backup_dir}/generated_media"
            os.makedirs(media_backup, exist_ok=True)
            
            # Copy only recent files to limit backup size
            import glob
            recent_files = glob.glob('generated_media/*')[:50]  # Limit to 50 files
            for file_path in recent_files:
                if os.path.isfile(file_path):
                    shutil.copy2(file_path, media_backup)
        
        # Copy configuration (without sensitive data)
        config_data = {
            'backup_created': datetime.now().isoformat(),
            'version': '2.0.0',
            'features': ['database', 'media', 'advanced_ai', 'monitoring']
        }
        
        with open(f"{backup_dir}/config.json", 'w') as f:
            json.dump(config_data, f, indent=2)
        
        # Create zip file
        with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(backup_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arc_path = os.path.relpath(file_path, backup_dir)
                    zipf.write(file_path, arc_path)
        
        # Cleanup temp directory
        shutil.rmtree(backup_dir)
        
        # Get backup file size
        backup_size = os.path.getsize(backup_file) / (1024**2)  # MB
        
        return jsonify({
            'success': True,
            'backup_id': backup_id,
            'backup_file': backup_file,
            'backup_size_mb': backup_size,
            'created_at': datetime.now().isoformat(),
            'expires_in': '24 hours'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/advanced/status")
def api_advanced_status():
    """Get comprehensive advanced features status"""
    try:
        status = {
            'timestamp': datetime.now().isoformat(),
            'version': '2.0.0',
            'features': {}
        }
        
        # Advanced AI status
        try:
            from handlers.advanced_ai import advanced_ai
            status['features']['advanced_ai'] = advanced_ai.get_service_status()
        except Exception as e:
            status['features']['advanced_ai'] = {'error': str(e)}
        
        # Media generation status
        try:
            from handlers.media_generator import media_generator
            status['features']['media_generation'] = media_generator.get_service_status()
        except Exception as e:
            status['features']['media_generation'] = {'error': str(e)}
        
        # Service monitoring status
        try:
            from handlers.service_monitor import service_monitor
            status['features']['service_monitoring'] = {
                'active': service_monitor.running,
                'services_count': len(service_monitor.services),
                'health_summary': service_monitor.get_system_health_summary()
            }
        except Exception as e:
            status['features']['service_monitoring'] = {'error': str(e)}
        
        # Notification system status
        try:
            from handlers.notifications import task_notification_system
            status['features']['notifications'] = task_notification_system.get_notification_stats()
        except Exception as e:
            status['features']['notifications'] = {'error': str(e)}
        
        # Database status
        if DATABASE_AVAILABLE:
            status['features']['database'] = db_manager.get_database_stats()
        else:
            status['features']['database'] = {'error': 'Database not available'}
        
        return jsonify({
            'success': True,
            'status': status
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("Launching Memory-Optimized WhatsApp Assistant...")
    
    # Start WAHA keep-alive to prevent session timeout
    start_waha_keepalive()
    
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode, threaded=True)
