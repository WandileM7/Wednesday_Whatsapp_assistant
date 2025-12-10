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
from config import GEMINI_API_KEY
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

# Import Google Generative AI
try:
    import google.generativeai as genai
except ImportError:
    genai = None

# Timeout exception for webhook processing
class TimeoutException(Exception):
    pass

from flask import Flask, redirect, request, jsonify, session, url_for, send_file, Response
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
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))

Session(app)
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
    """Cache user session data including phone number and Gemini service URL"""
    if not phone:
        return
    
    session_data = session.get('user_cache', {})
    
    # Cache phone number
    session_data['phone'] = phone
    session_data['last_seen'] = datetime.now().isoformat()
    
    # Cache Gemini service URL if provided
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

# Try to import Gemini helpers; fallback to simple stubs if missing
try:
    from handlers.gemini import chat_with_functions, execute_function
    GEMINI_HELPERS_AVAILABLE = True
except Exception as e:
    GEMINI_HELPERS_AVAILABLE = False
    logger.warning(f"Using fallback Gemini stubs: {e}")

    def chat_with_functions(user_message: str, phone: str):
        # Simple echo-style fallback
        return {"content": f"I'm running in fallback mode. You said: {user_message}"}

    def execute_function(call, phone=""):
        # No function calling in fallback
        return call.get("content") or "Function calling is disabled in fallback mode."

# Initialize Gemini (non-fatal if missing)
gemini_api_key = os.getenv("GEMINI_API_KEY")
class _DummyModel:
    def generate_content(self, prompt: str):
        class _R:
            text = "Hello. Gemini is not configured; using a dummy response."
        return _R()

if gemini_api_key and genai:
    try:
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        logger.info("Gemini client initialized")
    except Exception as e:
        logger.warning(f"Gemini init failed; using dummy model: {e}")
        model = _DummyModel()
else:
    if not gemini_api_key:
        logger.warning("GEMINI_API_KEY not set. Using dummy model; app will still start.")
    elif not genai:
        logger.warning("google-generativeai not available. Using dummy model; app will still start.")
    model = _DummyModel()

PERSONALITY_PROMPT = os.getenv("PERSONALITY_PROMPT", "You are a sarcastic and sassy assistant.")
GREETING_PROMPT = os.getenv("GREETING_PROMPT", "Give a brief, sarcastic greeting.")
INITIAL_MESSAGE_PROMPT = os.getenv("INITIAL_MESSAGE_PROMPT", "Send a mysterious message under 50 words.")

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
    """Redirect to the unified dashboard"""
    return redirect(url_for('unified_dashboard'))

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
        return """
        <h2>✅ Spotify Authorization Successful!</h2>
        <p>Your tokens have been saved persistently and won't expire every 30 minutes!</p>
        <p>The assistant will now automatically refresh your Spotify tokens as needed.</p>
        <h3>Quick Tests</h3>
        <ul>
            <li><a href="/test-spotify">Test Spotify</a></li>
            <li><a href="/spotify-status">Check Spotify Status</a></li>
        </ul>
        <h3>Next Steps</h3>
        <p>Your Spotify integration is now persistent. The assistant can control your music even after restarts!</p>
        """
    except Exception as e:
        logger.error(f"Error getting Spotify token: {e}")
        return f"❌ Error getting token: {str(e)}", 500

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
                raise RuntimeError(f"Media download failed: {resp.status_code}")
            
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
        
        # Enhanced voice message detection
        # Check multiple indicators for voice messages
        is_voice_message = (
            message_type == 'voice' or 
            payload.get('hasMedia') or 
            user_msg == '[Media]' or  # Common WhatsApp voice message indicator
            payload.get('mediaUrl') or 
            payload.get('url')
        )
        
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
            return """
            <h2>✅ Already Authenticated</h2>
            <p>Google services are already authenticated and ready to use.</p>
            <p><a href="/test-gmail">Test Gmail</a> | <a href="/google-status">Check Status</a></p>
            """
        
        # Redirect to authorization flow
        return redirect(url_for('auth.authorize'))
        
    except Exception as e:
        logger.error(f"Error in Google login: {e}")
        return f"""
        <h2>❌ Google Login Error</h2>
        <p>Error: {str(e)}</p>
        <p><a href="/google-status">Check Google Status</a></p>
        """, 500

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
    """Overview of all available services with detailed status"""
    # Get authentication status from auth manager
    auth_status = auth_manager.get_auth_status()
    
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
            "gemini": {
                "status": "active" if os.getenv("GEMINI_API_KEY") else "not_configured",
                "model": "gemini-2.0-flash"
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
            "google_contacts": "/contacts/google"
        }
    }

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
        
        return jsonify({
            "status": "healthy",
            "memory_mb": round(memory_info.rss / 1024 / 1024, 2),
            "active_conversations": len(user_conversations),
            "database_enabled": DATABASE_AVAILABLE,
            "database_stats": db_stats,
            "waha_status": "connected" if waha_healthy else ("disconnected" if waha_healthy is False else "not_configured"),
            "waha_keepalive": waha_keepalive_active,
            "gemini_helpers": GEMINI_HELPERS_AVAILABLE,
            "timestamp": datetime.now().isoformat()
        })
    except ImportError:
        return jsonify({
            "status": "healthy",
            "memory_mb": "unavailable",
            "active_conversations": len(user_conversations),
            "waha_status": "connected" if waha_health_check() else "disconnected" if waha_url else "not_configured",
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
        response = model.generate_content(prompt)
        initial_message = response.text.strip()
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

def send_message(phone, text):
    """Memory-efficient message sending"""
    try:
        if not waha_health_check():
            logger.warning("WAHA not ready; message not sent")
            return False
        headers = {"Content-Type": "application/json"}
        session_name = os.getenv("WAHA_SESSION", "default")
        payload = {
            "chatId": phone, 
            "text": text,
            "session": session_name
        }
        # Primary (legacy) endpoint
        r = requests.post(waha_url, headers=headers, data=json.dumps(payload), timeout=20)
        if r.status_code in (200, 201):
            return True
        # Fallback to session-scoped messages API
        base = _waha_base()
        alt = f"{base}/api/sessions/{session_name}/messages/text"
        r2 = requests.post(alt, headers=headers, data=json.dumps(payload), timeout=20)
        if r2.status_code in (200, 201):
            return True
        logger.error(f"WAHA send_message failed: {r.status_code} {r.text} | alt={r2.status_code} {r2.text}")
        return False
    except Exception as e:
        logger.error(f"WAHA send_message error: {e}")
        return False

def send_voice_message(phone, audio_file, fallback_text=""):
    """Send voice message with improved fallback handling"""
    if not waha_url:
        logger.warning("WAHA URL not configured")
        return False
        
    try:
        # First try to send as voice message
        voice_url = f"{_waha_base()}/api/sendVoice"
        
        with open(audio_file, 'rb') as f:
            files = {'audio': ('voice.ogg', f, 'audio/ogg')}
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
            files = {'media': ('voice.ogg', f, 'audio/ogg')}
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
    """Send text message with improved error handling"""
    if not waha_url:
        logger.warning("WAHA URL not configured")
        return False
        
    try:
        headers = _waha_headers()
        payload = {"chatId": phone, "text": text}
        
        # Check if WAHA is ready first
        health_check = waha_health_check()
        if not health_check:
            logger.warning("WAHA not ready; message not sent")
            return False
        
        response = requests.post(waha_url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            logger.info(f"Text message sent successfully to {phone}")
            return True
        else:
            logger.error(f"Failed to send message. Status: {response.status_code}, Response: {response.text}")
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
    """Quick setup page with all necessary links"""
    cached_session = get_cached_session()
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>WhatsApp Assistant - Quick Setup</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin: 20px 0; }}
            .success {{ border-color: #28a745; background-color: #d4edda; }}
            .warning {{ border-color: #ffc107; background-color: #fff3cd; }}
            .error {{ border-color: #dc3545; background-color: #f8d7da; }}
            .button {{ display: inline-block; padding: 10px 20px; margin: 5px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
            .button:hover {{ background: #0056b3; }}
            .step {{ margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <h1>WhatsApp Assistant - Quick Setup</h1>
        
        <div class="card success">
            <h3>📱 Session Cache Status</h3>
            <p><strong>Phone:</strong> {cached_session.get('phone', 'Not cached')}</p>
            <p><strong>Location:</strong> {cached_session.get('location', 'Johannesburg (default)')}</p>
            <p><strong>Gemini URL:</strong> {cached_session.get('gemini_url', 'Not set')}</p>
            <p><strong>Last Seen:</strong> {cached_session.get('last_seen', 'Never')}</p>
            <a href="/session-cache" class="button">View Cache</a>
        </div>
        
        <div class="card warning">
            <h3>🚀 Authentication Setup</h3>
            <p>Set up automatic authentication for all services:</p>
            
            <div class="step">
                <strong>Step 1:</strong> Authenticate Services
                <br>
                <a href="/google-login" class="button">Authenticate Google</a>
                <a href="/login" class="button">Authenticate Spotify</a>
            </div>
            
            <div class="step">
                <strong>Step 2:</strong> Save Tokens for Auto-Auth
                <br>
                <a href="/setup-all-auto-auth" class="button">Setup All Auto-Auth</a>
                <a href="/save-current-google-tokens" class="button">Save Google Tokens</a>
            </div>
            
            <div class="step">
                <strong>Step 3:</strong> Test Everything
                <br>
                <a href="/test-webhook-auth" class="button">Test Webhook Auth</a>
                <a href="/services" class="button">Check Status</a>
            </div>
        </div>
        
        <div class="card">
            <h3>📱 WhatsApp Integration</h3>
            <p>Connect your WhatsApp to the assistant:</p>
            
            <div class="step">
                <strong>Step 1:</strong> View WhatsApp QR Code
                <br>
                <a href="/whatsapp-qr" class="button">📱 Show QR Code</a>
                <a href="/whatsapp-status" class="button">📊 Service Status</a>
            </div>
            
            <div class="step">
                <strong>Step 2:</strong> Scan QR Code with WhatsApp
                <br>
                <small>Open WhatsApp → Settings → Linked Devices → Link a Device</small>
            </div>
            
            <div class="step">
                <strong>Step 3:</strong> Test Connection
                <br>
                <a href="/test-webhook-auth" class="button">🔗 Test Webhook</a>
                <small style="display: block; margin-top: 5px;">Send a message to your WhatsApp number to test</small>
            </div>
        </div>
        
        <div class="card">
            <h3>🌟 Enhanced Personal Assistant Features</h3>
            <a href="/weather?location=Johannesburg" class="button">Test Weather</a>
            <a href="/news" class="button">Test News</a>
            <a href="/news/briefing" class="button">Daily Briefing</a>
            <a href="/tasks" class="button">View Tasks</a>
            <a href="/reminders" class="button">View Reminders</a>
            <a href="/tasks/summary" class="button">Task Summary</a>
            <a href="/contacts" class="button">View Contacts</a>
            <a href="/contacts/summary" class="button">Contact Summary</a>
        </div>
        
        <div class="card">
            <h3>📊 Dashboard</h3>
            <a href="/dashboard" class="button">📊 Main Dashboard</a>
            <a href="/services" class="button">Services Overview</a>
            <a href="/health" class="button">System Health</a>
        </div>
        
        <div class="card">
            <h3>⚡ Quick Actions</h3>
            <a href="/clear-spotify-tokens" class="button">Clear Spotify</a>
            <a href="/auth/clear-auth" class="button">Clear Google</a>
            <a href="/refresh-google-token" class="button">Refresh Google</a>
        </div>
        
        <div class="card">
            <h3>📝 Environment Variables Needed</h3>
            <p>After authentication, add these to your deployment:</p>
            <p><strong>Core Services:</strong></p>
            <code>
                SPOTIFY_REFRESH_TOKEN=your_token_here<br>
                GOOGLE_REFRESH_TOKEN=your_token_here<br>
                GOOGLE_CLIENT_ID=your_client_id<br>
                GOOGLE_CLIENT_SECRET=your_secret
            </code>
            <p><strong>Enhanced Features (Optional):</strong></p>
            <code>
                WEATHERAPI_KEY=your_weatherapi_key<br>
                NEWS_API_KEY=your_newsapi_key
            </code>
        </div>
    </body>
    </html>
    """

# WhatsApp QR Code Routes
@app.route("/whatsapp-qr")
def whatsapp_qr():
    """Display WhatsApp QR code status and visual QR code"""
    try:
        # Get QR data from WhatsApp service
        whatsapp_url = os.getenv('WAHA_URL', 'http://localhost:3000/api/sendText').replace('/api/sendText', '')
        qr_response = requests.get(f"{whatsapp_url}/api/qr", timeout=5)
        qr_data = qr_response.json()
        
        # Check if we have QR code data
        if qr_data.get('qr'):
            qr_text = qr_data['qr']
            mode = qr_data.get('mode', 'unknown')
            timestamp = qr_data.get('timestamp', 'unknown')
            
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>WhatsApp QR Code</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 40px; text-align: center; }}
                    .qr-container {{ margin: 20px auto; max-width: 400px; }}
                    .status {{ padding: 15px; border-radius: 5px; margin: 20px; }}
                    .success {{ background-color: #d4edda; border: 1px solid #28a745; color: #155724; }}
                    .warning {{ background-color: #fff3cd; border: 1px solid #ffc107; color: #856404; }}
                    .button {{ display: inline-block; padding: 10px 20px; margin: 10px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
                    .button:hover {{ background: #0056b3; }}
                    .qr-info {{ margin: 20px; font-size: 14px; color: #666; }}
                </style>
                <script>
                    // Auto-refresh every 30 seconds to check for status changes
                    setTimeout(() => window.location.reload(), 30000);
                </script>
            </head>
            <body>
                <h1>📱 WhatsApp QR Code</h1>
                
                <div class="status {"success" if mode == "production" else "warning"}">
                    <h3>Status: {'🟢 Production Mode' if mode == 'production' else '🟡 Mock Mode'}</h3>
                    <p><strong>Timestamp:</strong> {timestamp}</p>
                    <p><strong>Service Mode:</strong> {mode.title()}</p>
                </div>
                
                <div class="qr-container">
                    <h3>Scan this QR code with WhatsApp:</h3>
                    <img src="/whatsapp-qr-image" alt="WhatsApp QR Code" style="max-width: 100%; border: 1px solid #ddd; padding: 10px;">
                </div>
                
                <div class="qr-info">
                    <p><strong>Instructions:</strong></p>
                    <ol style="text-align: left; max-width: 500px; margin: 0 auto;">
                        <li>Open WhatsApp on your phone</li>
                        <li>Go to Settings → Linked Devices</li>
                        <li>Tap "Link a Device"</li>
                        <li>Scan the QR code above</li>
                    </ol>
                </div>
                
                <div>
                    <a href="/whatsapp-qr" class="button">🔄 Refresh</a>
                    <a href="/quick-setup" class="button">← Back to Setup</a>
                    <a href="/whatsapp-status" class="button">📊 Status</a>
                </div>
                
                <div class="qr-info">
                    <p><em>This page automatically refreshes every 30 seconds</em></p>
                    <p><strong>QR Data:</strong> <code style="word-break: break-all; font-size: 12px;">{qr_text[:50]}...</code></p>
                </div>
            </body>
            </html>
            """
        else:
            # No QR code available
            status = qr_data.get('status', 'unknown')
            message = qr_data.get('message', 'No status message')
            mode = qr_data.get('mode', 'unknown')
            
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>WhatsApp Status</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 40px; text-align: center; }}
                    .status {{ padding: 15px; border-radius: 5px; margin: 20px; }}
                    .success {{ background-color: #d4edda; border: 1px solid #28a745; color: #155724; }}
                    .warning {{ background-color: #fff3cd; border: 1px solid #ffc107; color: #856404; }}
                    .error {{ background-color: #f8d7da; border: 1px solid #dc3545; color: #721c24; }}
                    .button {{ display: inline-block; padding: 10px 20px; margin: 10px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
                    .button:hover {{ background: #0056b3; }}
                </style>
                <script>
                    // Auto-refresh every 10 seconds when waiting for QR
                    setTimeout(() => window.location.reload(), 10000);
                </script>
            </head>
            <body>
                <h1>📱 WhatsApp Status</h1>
                
                <div class="status {"success" if status == "authenticated" else "warning" if status == "waiting" else "error"}">
                    <h3>{'✅ Connected!' if status == "authenticated" else '⏳ Waiting...' if status == "waiting" else '❌ Error'}</h3>
                    <p><strong>Status:</strong> {status.title()}</p>
                    <p><strong>Message:</strong> {message}</p>
                    <p><strong>Mode:</strong> {mode.title()}</p>
                </div>
                
                <div>
                    <a href="/whatsapp-qr" class="button">🔄 Refresh</a>
                    <a href="/quick-setup" class="button">← Back to Setup</a>
                    <a href="/whatsapp-status" class="button">📊 Detailed Status</a>
                </div>
                
                <div style="margin: 20px; font-size: 14px; color: #666;">
                    <p><em>This page automatically refreshes every 10 seconds</em></p>
                </div>
            </body>
            </html>
            """
    except requests.RequestException as e:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>WhatsApp Service Error</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; text-align: center; }}
                .error {{ padding: 15px; border-radius: 5px; margin: 20px; background-color: #f8d7da; border: 1px solid #dc3545; color: #721c24; }}
                .button {{ display: inline-block; padding: 10px 20px; margin: 10px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>❌ WhatsApp Service Error</h1>
            <div class="error">
                <h3>Cannot connect to WhatsApp service</h3>
                <p><strong>Error:</strong> {str(e)}</p>
                <p>Make sure the WhatsApp service is running on port 3000</p>
            </div>
            <a href="/quick-setup" class="button">← Back to Setup</a>
        </body>
        </html>
        """

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
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>WhatsApp Service Status</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .status-card {{ border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin: 20px 0; }}
                .success {{ border-color: #28a745; background-color: #d4edda; }}
                .warning {{ border-color: #ffc107; background-color: #fff3cd; }}
                .error {{ border-color: #dc3545; background-color: #f8d7da; }}
                .button {{ display: inline-block; padding: 10px 20px; margin: 5px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
                .json {{ background: #f8f9fa; padding: 10px; border-radius: 5px; font-family: monospace; white-space: pre-wrap; overflow-x: auto; }}
            </style>
        </head>
        <body>
            <h1>📊 WhatsApp Service Status</h1>
            
            <div class="status-card">
                <h3>🏥 Health Status</h3>
                <div class="json">{json.dumps(status_data['health'], indent=2)}</div>
            </div>
            
            <div class="status-card">
                <h3>📱 QR Code Status</h3>
                <div class="json">{json.dumps(status_data['qr'], indent=2)}</div>
            </div>
            
            <div class="status-card">
                <h3>ℹ️ Service Info</h3>
                <div class="json">{json.dumps(status_data['info'], indent=2)}</div>
            </div>
            
            <div>
                <a href="/whatsapp-qr" class="button">📱 View QR Code</a>
                <a href="/whatsapp-status" class="button">🔄 Refresh Status</a>
                <a href="/quick-setup" class="button">← Back to Setup</a>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        return f"""
        <h1>❌ Error</h1>
        <p>Could not get WhatsApp service status: {str(e)}</p>
        <a href="/quick-setup">← Back to Setup</a>
        """



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
    """Beautiful unified dashboard combining all functionality"""
    try:
        from handlers.service_monitor import service_monitor
        from handlers.notifications import task_notification_system
        from helpers.token_storage import token_storage
        
        # Get comprehensive system status
        services_status = service_monitor.get_service_status()
        health_summary = service_monitor.get_system_health_summary()
        notification_stats = task_notification_system.get_notification_stats()
        
        # Get task sync status
        from handlers.tasks import background_sync_service
        sync_status = background_sync_service.get_status()
        
        # Get authentication status
        spotify_tokens = token_storage.load_spotify_tokens()
        google_tokens = token_storage.load_google_tokens()
        
        env_spotify_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
        env_google_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        
        session_spotify = session.get("token_info")
        session_google = session.get("google_credentials")
        
        # Test current connections
        spotify_working = False
        google_working = False
        
        try:
            test_token = get_token_info()
            spotify_working = test_token is not None
        except:
            pass
        
        try:
            from handlers.google_auth import load_credentials
            test_creds = load_credentials()
            google_working = test_creds is not None and test_creds.valid
        except:
            pass
        
        if DATABASE_AVAILABLE:
            db_stats = db_manager.get_database_stats()
        else:
            db_stats = {'error': 'Database not available'}
        
        # Build service cards HTML
        service_cards = ""
        for service_name, service_info in services_status.get('services', {}).items():
            status = service_info.get('status', 'unknown')
            status_class = 'healthy' if status == 'healthy' else 'error' if status in ['error', 'unhealthy'] else 'warning'
            critical_badge = '<span class="critical-badge">CRITICAL</span>' if service_info.get('critical') else ''
            
            service_cards += f"""
                <div class="service-card {status_class}">
                    <div class="service-header">
                        <span class="service-name">{service_name.replace('_', ' ').title()}</span>
                        {critical_badge}
                    </div>
                    <div class="service-status">
                        <span class="status-dot {status_class}"></span>
                        <span>{status.title()}</span>
                    </div>
                    <div class="service-meta">Last check: {service_info.get('last_check', 'Never')[:19] if service_info.get('last_check') else 'Never'}</div>
                </div>
            """
        
        dashboard_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wednesday Assistant</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --secondary: #8b5cf6;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --dark: #1e1b4b;
            --light: #f8fafc;
            --gray-100: #f1f5f9;
            --gray-200: #e2e8f0;
            --gray-300: #cbd5e1;
            --gray-600: #475569;
            --gray-800: #1e293b;
            --radius: 16px;
            --radius-sm: 8px;
            --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
            --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1);
            --shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
        }}
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, var(--dark) 0%, #312e81 50%, var(--dark) 100%);
            min-height: 100vh;
            color: var(--gray-800);
        }}
        
        .dashboard {{
            max-width: 1600px;
            margin: 0 auto;
            padding: 24px;
        }}
        
        /* Header */
        .header {{
            text-align: center;
            padding: 40px 20px;
            color: white;
        }}
        
        .header h1 {{
            font-size: 3rem;
            font-weight: 800;
            background: linear-gradient(135deg, #fff 0%, #c7d2fe 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }}
        
        .header .subtitle {{
            font-size: 1.1rem;
            opacity: 0.8;
            font-weight: 400;
        }}
        
        .header .timestamp {{
            font-size: 0.85rem;
            opacity: 0.6;
            margin-top: 12px;
        }}
        
        /* Grid Layout */
        .grid {{
            display: grid;
            gap: 24px;
        }}
        
        .grid-2 {{ grid-template-columns: repeat(2, 1fr); }}
        .grid-3 {{ grid-template-columns: repeat(3, 1fr); }}
        .grid-4 {{ grid-template-columns: repeat(4, 1fr); }}
        
        @media (max-width: 1200px) {{
            .grid-4 {{ grid-template-columns: repeat(2, 1fr); }}
            .grid-3 {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        
        @media (max-width: 768px) {{
            .grid-4, .grid-3, .grid-2 {{ grid-template-columns: 1fr; }}
        }}
        
        /* Cards */
        .card {{
            background: white;
            border-radius: var(--radius);
            padding: 24px;
            box-shadow: var(--shadow-lg);
        }}
        
        .card-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 2px solid var(--gray-100);
        }}
        
        .card-header .icon {{
            width: 40px;
            height: 40px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.3rem;
        }}
        
        .card-header .icon.primary {{ background: linear-gradient(135deg, var(--primary), var(--secondary)); }}
        .card-header .icon.success {{ background: linear-gradient(135deg, var(--success), #059669); }}
        .card-header .icon.warning {{ background: linear-gradient(135deg, var(--warning), #d97706); }}
        .card-header .icon.danger {{ background: linear-gradient(135deg, var(--danger), #dc2626); }}
        
        .card-header h2 {{
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--gray-800);
        }}
        
        /* Stats Grid */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 24px;
        }}
        
        @media (max-width: 1200px) {{ .stats-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
        @media (max-width: 600px) {{ .stats-grid {{ grid-template-columns: 1fr; }} }}
        
        .stat-card {{
            background: white;
            border-radius: var(--radius);
            padding: 24px;
            box-shadow: var(--shadow);
            position: relative;
            overflow: hidden;
        }}
        
        .stat-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
        }}
        
        .stat-card.primary::before {{ background: linear-gradient(90deg, var(--primary), var(--secondary)); }}
        .stat-card.success::before {{ background: var(--success); }}
        .stat-card.warning::before {{ background: var(--warning); }}
        .stat-card.danger::before {{ background: var(--danger); }}
        
        .stat-value {{
            font-size: 2rem;
            font-weight: 700;
            color: var(--gray-800);
        }}
        
        .stat-label {{
            font-size: 0.8rem;
            color: var(--gray-600);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 4px;
        }}
        
        /* Status Badge */
        .status-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }}
        
        .status-badge.healthy {{ background: #d1fae5; color: #065f46; }}
        .status-badge.warning {{ background: #fef3c7; color: #92400e; }}
        .status-badge.error {{ background: #fee2e2; color: #991b1b; }}
        
        .status-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }}
        
        .status-dot.healthy {{ background: var(--success); }}
        .status-dot.warning {{ background: var(--warning); }}
        .status-dot.error {{ background: var(--danger); }}
        
        /* Auth Cards */
        .auth-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
        }}
        
        @media (max-width: 900px) {{ .auth-grid {{ grid-template-columns: 1fr; }} }}
        
        .auth-card {{
            background: white;
            border-radius: var(--radius);
            padding: 24px;
            box-shadow: var(--shadow);
            border-left: 4px solid var(--gray-300);
        }}
        
        .auth-card.connected {{ border-left-color: var(--success); }}
        .auth-card.disconnected {{ border-left-color: var(--danger); }}
        
        .auth-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }}
        
        .auth-title {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 1.1rem;
            font-weight: 600;
        }}
        
        .auth-row {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid var(--gray-100);
            font-size: 0.9rem;
        }}
        
        .auth-row:last-child {{ border-bottom: none; }}
        
        .auth-label {{ color: var(--gray-600); }}
        .auth-value {{ font-weight: 500; }}
        .auth-value.yes {{ color: var(--success); }}
        .auth-value.no {{ color: var(--danger); }}
        
        /* Service Cards */
        .services-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 16px;
        }}
        
        .service-card {{
            background: var(--gray-100);
            border-radius: var(--radius-sm);
            padding: 16px;
            border-left: 3px solid var(--gray-300);
        }}
        
        .service-card.healthy {{ border-left-color: var(--success); background: #f0fdf4; }}
        .service-card.warning {{ border-left-color: var(--warning); background: #fffbeb; }}
        .service-card.error {{ border-left-color: var(--danger); background: #fef2f2; }}
        
        .service-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
        }}
        
        .service-name {{
            font-weight: 600;
            font-size: 0.9rem;
        }}
        
        .critical-badge {{
            font-size: 0.6rem;
            background: var(--danger);
            color: white;
            padding: 2px 6px;
            border-radius: 4px;
        }}
        
        .service-status {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.85rem;
            margin-bottom: 4px;
        }}
        
        .service-meta {{
            font-size: 0.75rem;
            color: var(--gray-600);
        }}
        
        /* Buttons */
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 10px 20px;
            border-radius: var(--radius-sm);
            font-size: 0.875rem;
            font-weight: 600;
            text-decoration: none;
            cursor: pointer;
            border: none;
            transition: all 0.2s ease;
        }}
        
        .btn-primary {{
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: white;
            box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
        }}
        
        .btn-primary:hover {{ transform: translateY(-2px); box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5); }}
        
        .btn-success {{
            background: linear-gradient(135deg, var(--success), #059669);
            color: white;
        }}
        
        .btn-danger {{
            background: linear-gradient(135deg, var(--danger), #dc2626);
            color: white;
        }}
        
        .btn-outline {{
            background: transparent;
            border: 2px solid var(--gray-200);
            color: var(--gray-600);
        }}
        
        .btn-outline:hover {{ border-color: var(--primary); color: var(--primary); }}
        
        .btn-group {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 16px;
        }}
        
        /* Quick Actions */
        .actions-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 16px;
        }}
        
        .action-section {{
            background: var(--gray-100);
            border-radius: var(--radius-sm);
            padding: 16px;
        }}
        
        .action-section h4 {{
            font-size: 0.85rem;
            color: var(--gray-600);
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        /* WhatsApp Section */
        .whatsapp-section {{
            background: linear-gradient(135deg, #25D366 0%, #128C7E 100%);
            border-radius: var(--radius);
            padding: 32px;
            color: white;
        }}
        
        .whatsapp-section h3 {{
            font-size: 1.3rem;
            margin-bottom: 12px;
        }}
        
        .whatsapp-input {{
            padding: 14px 18px;
            border: 2px solid rgba(255,255,255,0.3);
            background: rgba(255,255,255,0.1);
            border-radius: var(--radius-sm);
            font-size: 1rem;
            color: white;
            width: 300px;
            max-width: 100%;
        }}
        
        .whatsapp-input::placeholder {{ color: rgba(255,255,255,0.7); }}
        .whatsapp-input:focus {{ outline: none; border-color: white; background: rgba(255,255,255,0.2); }}
        
        /* Footer */
        .footer {{
            text-align: center;
            padding: 32px 20px;
            color: rgba(255,255,255,0.6);
            font-size: 0.85rem;
        }}
        
        .footer a {{ color: rgba(255,255,255,0.8); text-decoration: none; }}
        .footer a:hover {{ color: white; }}
        
        /* Animations */
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
        
        .pulse {{ animation: pulse 2s infinite; }}
    </style>
</head>
<body>
    <div class="dashboard">
        <header class="header">
            <h1>🤖 Wednesday Assistant</h1>
            <p class="subtitle">Your AI-Powered Personal Assistant Dashboard</p>
            <p class="timestamp">Last updated: {datetime.now().strftime('%B %d, %Y at %H:%M:%S')} • Auto-refreshes every 60s</p>
        </header>
        
        <!-- Stats Overview -->
        <div class="stats-grid">
            <div class="stat-card {'success' if health_summary.get('overall_status') == 'healthy' else 'danger'}">
                <div class="stat-value">{health_summary.get('overall_status', 'Unknown').title()}</div>
                <div class="stat-label">System Status</div>
            </div>
            <div class="stat-card primary">
                <div class="stat-value">{health_summary.get('healthy_services', 0)}/{health_summary.get('total_services', 0)}</div>
                <div class="stat-label">Services Healthy</div>
            </div>
            <div class="stat-card primary">
                <div class="stat-value">{len(user_conversations)}</div>
                <div class="stat-label">Active Conversations</div>
            </div>
            <div class="stat-card {'success' if waha_connection_status.get('status') == 'healthy' else 'warning' if waha_connection_status.get('status') == 'degraded' else 'danger'}">
                <div class="stat-value">{waha_connection_status.get('status', 'Unknown').title()}</div>
                <div class="stat-label">WhatsApp Status</div>
            </div>
        </div>
        
        <div class="grid grid-2" style="margin-bottom: 24px;">
            <!-- Authentication Status -->
            <div class="card">
                <div class="card-header">
                    <div class="icon primary">🔐</div>
                    <h2>Authentication Status</h2>
                </div>
                <div class="auth-grid">
                    <div class="auth-card {'connected' if spotify_working else 'disconnected'}">
                        <div class="auth-header">
                            <div class="auth-title">
                                <span>🎵</span>
                                <span>Spotify</span>
                            </div>
                            <span class="status-badge {'healthy' if spotify_working else 'error'}">
                                <span class="status-dot {'healthy' if spotify_working else 'error'}"></span>
                                {'Connected' if spotify_working else 'Disconnected'}
                            </span>
                        </div>
                        <div class="auth-row">
                            <span class="auth-label">Session Token</span>
                            <span class="auth-value {'yes' if session_spotify else 'no'}">{'✓ Available' if session_spotify else '✗ Missing'}</span>
                        </div>
                        <div class="auth-row">
                            <span class="auth-label">Stored Token</span>
                            <span class="auth-value {'yes' if spotify_tokens else 'no'}">{'✓ Available' if spotify_tokens else '✗ Missing'}</span>
                        </div>
                        <div class="auth-row">
                            <span class="auth-label">Environment</span>
                            <span class="auth-value {'yes' if env_spotify_token else 'no'}">{'✓ Set' if env_spotify_token else '✗ Not Set'}</span>
                        </div>
                        <div class="btn-group">
                            {'<a href="/test-spotify" class="btn btn-success">Test</a>' if spotify_working else '<a href="/login" class="btn btn-primary">Connect</a>'}
                            <a href="/spotify-status" class="btn btn-outline">Details</a>
                        </div>
                    </div>
                    
                    <div class="auth-card {'connected' if google_working else 'disconnected'}">
                        <div class="auth-header">
                            <div class="auth-title">
                                <span>📧</span>
                                <span>Google</span>
                            </div>
                            <span class="status-badge {'healthy' if google_working else 'error'}">
                                <span class="status-dot {'healthy' if google_working else 'error'}"></span>
                                {'Connected' if google_working else 'Disconnected'}
                            </span>
                        </div>
                        <div class="auth-row">
                            <span class="auth-label">Session Token</span>
                            <span class="auth-value {'yes' if session_google else 'no'}">{'✓ Available' if session_google else '✗ Missing'}</span>
                        </div>
                        <div class="auth-row">
                            <span class="auth-label">Stored Token</span>
                            <span class="auth-value {'yes' if google_tokens else 'no'}">{'✓ Available' if google_tokens else '✗ Missing'}</span>
                        </div>
                        <div class="auth-row">
                            <span class="auth-label">Environment</span>
                            <span class="auth-value {'yes' if env_google_token else 'no'}">{'✓ Set' if env_google_token else '✗ Not Set'}</span>
                        </div>
                        <div class="btn-group">
                            {'<a href="/test-google-services" class="btn btn-success">Test</a>' if google_working else '<a href="/google-login" class="btn btn-primary">Connect</a>'}
                            <a href="/google-auth-status" class="btn btn-outline">Details</a>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- System Metrics -->
            <div class="card">
                <div class="card-header">
                    <div class="icon success">📊</div>
                    <h2>System Metrics</h2>
                </div>
                <div class="stats-grid" style="margin-bottom: 0;">
                    <div class="stat-card primary">
                        <div class="stat-value">{health_summary.get('system_metrics', {}).get('memory_percent', 'N/A')}%</div>
                        <div class="stat-label">Memory Usage</div>
                    </div>
                    <div class="stat-card primary">
                        <div class="stat-value">{health_summary.get('system_metrics', {}).get('cpu_percent', 'N/A')}%</div>
                        <div class="stat-label">CPU Usage</div>
                    </div>
                    <div class="stat-card primary">
                        <div class="stat-value">{db_stats.get('db_size_mb', 'N/A')}</div>
                        <div class="stat-label">DB Size (MB)</div>
                    </div>
                    <div class="stat-card primary">
                        <div class="stat-value">{db_stats.get('conversations_count', 0)}</div>
                        <div class="stat-label">Conversations</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Services Status -->
        <div class="card" style="margin-bottom: 24px;">
            <div class="card-header">
                <div class="icon warning">⚡</div>
                <h2>Service Status</h2>
            </div>
            <div class="services-grid">
                {service_cards}
            </div>
        </div>
        
        <!-- Quick Actions -->
        <div class="card" style="margin-bottom: 24px;">
            <div class="card-header">
                <div class="icon primary">🛠️</div>
                <h2>Quick Actions</h2>
            </div>
            <div class="actions-grid">
                <div class="action-section">
                    <h4>System</h4>
                    <div class="btn-group">
                        <a href="/health" class="btn btn-outline">Health Check</a>
                        <a href="/services" class="btn btn-outline">Services JSON</a>
                        <a href="javascript:location.reload()" class="btn btn-primary">Refresh</a>
                    </div>
                </div>
                <div class="action-section">
                    <h4>Authentication</h4>
                    <div class="btn-group">
                        <a href="/login" class="btn btn-outline">Spotify Login</a>
                        <a href="/google-login" class="btn btn-outline">Google Login</a>
                        <a href="/setup-all-auto-auth" class="btn btn-success">Auto Setup</a>
                    </div>
                </div>
                <div class="action-section">
                    <h4>Tasks & Notes</h4>
                    <div class="btn-group">
                        <a href="/test-tasks" class="btn btn-outline">View Tasks</a>
                        <a href="/test-google-notes" class="btn btn-outline">Google Sync</a>
                    </div>
                </div>
                <div class="action-section">
                    <h4>Diagnostics</h4>
                    <div class="btn-group">
                        <a href="/test-webhook-auth" class="btn btn-outline">Test Webhook</a>
                        <a href="/whatsapp-qr" class="btn btn-outline">WhatsApp QR</a>
                        <a href="/quick-setup" class="btn btn-outline">Setup Guide</a>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- WhatsApp Calling -->
        <div class="whatsapp-section">
            <h3>📞 WhatsApp Voice Calls</h3>
            <p style="opacity: 0.9; margin-bottom: 20px;">Make voice calls directly from this dashboard. Requires active WhatsApp connection.</p>
            <form id="callForm" onsubmit="makeCall(event)" style="display: flex; flex-wrap: wrap; gap: 12px; align-items: center;">
                <input type="text" id="phoneNumber" class="whatsapp-input" placeholder="Phone number (e.g., 27729224495)" required>
                <button type="submit" class="btn btn-success">📞 Call</button>
                <button type="button" onclick="endCall()" class="btn btn-danger">✕ End</button>
            </form>
            <div id="callStatus" style="margin-top: 16px; padding: 12px 16px; background: rgba(0,0,0,0.2); border-radius: 8px; display: none;">
                <span id="statusText"></span>
            </div>
        </div>
        
        <footer class="footer">
            <p>Wednesday WhatsApp Assistant • Built with Flask & AI</p>
            <p style="margin-top: 8px;"><a href="/quick-setup">Setup Guide</a> • <a href="/health">API Health</a> • <a href="/services">Services</a></p>
        </footer>
    </div>
    
    <script>
        // Auto-refresh
        setTimeout(() => location.reload(), 60000);
        
        function makeCall(event) {{
            event.preventDefault();
            const phone = document.getElementById('phoneNumber').value;
            const statusDiv = document.getElementById('callStatus');
            const statusText = document.getElementById('statusText');
            
            statusDiv.style.display = 'block';
            statusText.textContent = '📞 Initiating call to ' + phone + '...';
            
            fetch('/api/make-call', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ phone: phone }})
            }})
            .then(r => r.json())
            .then(data => {{
                statusText.textContent = data.success ? '✅ Call initiated to ' + phone : '❌ ' + (data.error || 'Failed');
            }})
            .catch(e => {{ statusText.textContent = '❌ Error: ' + e.message; }});
        }}
        
        function endCall() {{
            const statusDiv = document.getElementById('callStatus');
            const statusText = document.getElementById('statusText');
            
            statusDiv.style.display = 'block';
            statusText.textContent = 'Ending call...';
            
            fetch('/api/end-call', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }} }})
            .then(r => r.json())
            .then(data => {{
                statusText.textContent = data.success ? '✅ Call ended' : '❌ ' + (data.error || 'Failed');
            }})
            .catch(e => {{ statusText.textContent = '❌ Error: ' + e.message; }});
        }}
    </script>
</body>
</html>
        """
        
        return dashboard_html
        
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return f"""
<!DOCTYPE html>
<html>
<head><title>Dashboard Error</title></head>
<body style="font-family: sans-serif; padding: 40px; text-align: center;">
    <h1>⚠️ Dashboard Error</h1>
    <p style="color: #666;">{str(e)}</p>
    <a href="/health" style="color: #007bff;">Check System Health</a>
</body>
</html>
        """, 500

# Redirect old dashboard routes to unified dashboard
@app.route("/auth-dashboard")
def auth_dashboard_redirect():
    """Redirect to unified dashboard"""
    return redirect(url_for('unified_dashboard'))

@app.route("/google-services-dashboard")
def google_services_dashboard_redirect():
    """Redirect to unified dashboard"""
    return redirect(url_for('unified_dashboard'))

# Advanced AI endpoints
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
