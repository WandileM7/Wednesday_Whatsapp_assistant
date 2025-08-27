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

# QR Code generation
try:
    import qrcode
    from PIL import Image
    QR_AVAILABLE = True
except ImportError:
    logger.warning("QR code generation not available")
    QR_AVAILABLE = False

# Initialize logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

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
import os, time, json, threading, logging, requests
from urllib.parse import urlparse

# ChromaDB imports with fallback
try:
    from chromedb import add_to_conversation_history, query_conversation_history, retrieve_conversation_history
    CHROMADB_AVAILABLE = True
except ImportError as e:
    logger.warning(f"ChromaDB not available: {e}")
    CHROMADB_AVAILABLE = False
    
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

# WAHA Keep-Alive Configuration
WAHA_KEEPALIVE_INTERVAL = int(os.getenv("WAHA_KEEPALIVE_INTERVAL", "600"))  # 10 minutes default
WAHA_SESSION = os.getenv("WAHA_SESSION", "default")
waha_keepalive_active = False

def waha_health_check():
    """Ensure WAHA session exists and is started using sessions API (no Apps dependency)."""
    try:
        base = _waha_base()
        if not base:
            return False
        session_name = "default"
        # Check session status
        r = requests.get(f"{base}/api/sessions/{session_name}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            status = (data.get("status") or "").lower()
            return status in ("working", "active", "connected", "ready")
        if r.status_code == 404:
            # Create session if missing
            rc = requests.post(f"{base}/api/sessions/{session_name}", timeout=15)
            if rc.status_code not in (200, 201, 409):
                logger.warning(f"WAHA create session failed: {rc.status_code} {rc.text}")
        # Try to start the session (safe even if already started)
        rs = requests.post(f"{base}/api/sessions/{session_name}/start", timeout=20)
        if rs.status_code in (200, 202):
            return True
        if rs.status_code == 422 and "already started" in rs.text.lower():
            return True
        logger.warning(f"WAHA start session response: {rs.status_code} {rs.text}")
        return False
    except Exception as e:
        logger.warning(f"WAHA health check error: {e}")
        logger.warning(f"WAHA health check error: {e}")
        return False

def waha_keepalive():
    """Background keep-alive loop that maintains the WAHA session."""
    """Background keep-alive loop that maintains the WAHA session."""
    global waha_keepalive_active
    while waha_keepalive_active:
        ok = waha_health_check()
        logger.info(f"WAHA keep-alive: {'OK' if ok else 'NOT READY'}")
        time.sleep(WAHA_KEEPALIVE_INTERVAL)
        ok = waha_health_check()
        logger.info(f"WAHA keep-alive: {'OK' if ok else 'NOT READY'}")
        time.sleep(WAHA_KEEPALIVE_INTERVAL)

def start_waha_keepalive():
    global waha_keepalive_active
    if waha_keepalive_active:
        return
    waha_keepalive_active = True
    threading.Thread(target=waha_keepalive, daemon=True).start()
    threading.Thread(target=waha_keepalive, daemon=True).start()

def stop_waha_keepalive():
    global waha_keepalive_active
    waha_keepalive_active = False

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
    """Redirect to the main authentication dashboard"""
    return redirect(url_for('auth_dashboard'))

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

        # Process with Gemini
        try:
            if GEMINI_API_KEY and not GEMINI_API_KEY.startswith('test_'):
                call = chat_with_functions(user_msg, phone)
                
                if call.get("name"):
                    reply = execute_function(call, phone)
                else:
                    reply = call.get("content", "Sorry, no idea what that was.")
            else:
                reply = f"Echo: {user_msg}"
        except Exception as e:
            logger.error(f"Gemini processing error: {e}")
            reply = "I'm having trouble processing your message right now. Please try again later."

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

@app.route("/google-services-dashboard")
def google_services_dashboard():
    """HTML dashboard for Google services"""
    from handlers.google_auth import load_credentials
    
    try:
        creds = load_credentials()
        is_authenticated = creds and creds.valid
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Google Services Dashboard</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .status {{ padding: 10px; margin: 10px 0; border-radius: 5px; }}
                .success {{ background-color: #d4edda; color: #155724; }}
                .warning {{ background-color: #fff3cd; color: #856404; }}
                .error {{ background-color: #f8d7da; color: #721c24; }}
                .button {{ padding: 10px 20px; margin: 5px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }}
                .button:hover {{ background: #0056b3; }}
            </style>
        </head>
        <body>
            <h1>Google Services Dashboard</h1>
            
            <div class="status {'success' if is_authenticated else 'error'}">
                <h3>Authentication Status</h3>
                <p>{'✅ Authenticated and ready' if is_authenticated else '❌ Not authenticated'}</p>
            </div>
            
            <h3>Quick Actions</h3>
            {'<a href="/test-gmail" class="button">Test Gmail</a>' if is_authenticated else '<a href="/google-login" class="button">Authenticate Google</a>'}
            <a href="/google-auth-status" class="button">Check Status</a>
            <a href="/test-google-services" class="button">Test All Services</a>
            
            <h3>Available Services</h3>
            <ul>
                <li>📧 Gmail (Read & Send)</li>
                <li>📅 Google Calendar</li>
            </ul>
            
            <h3>Debug Information</h3>
            <p><strong>Credentials Path:</strong> {os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "Not set")}</p>
            <p><strong>Environment:</strong> {'Production' if not os.getenv("FLASK_DEBUG") else 'Development'}</p>
            
        </body>
        </html>
        """
        return html
        
    except Exception as e:
        return f"""
        <h1>Google Services Dashboard</h1>
        <div class="status error">
            <h3>Error</h3>
            <p>Failed to load dashboard: {str(e)}</p>
        </div>
        <a href="/google-status" class="button">Check Raw Status</a>
        """, 500

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
        
        # Include WAHA status in health check
        waha_healthy = waha_health_check() if waha_url else None
        
        return jsonify({
            "status": "healthy",
            "memory_mb": round(memory_info.rss / 1024 / 1024, 2),
            "active_conversations": len(user_conversations),
            "chromadb_enabled": CHROMADB_AVAILABLE and os.getenv("ENABLE_CHROMADB", "false").lower() == "true",
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
    ok = waha_health_check()
    return jsonify({"waha_ok": ok, "session": WAHA_SESSION, "base": _waha_base()})

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
            <h3>📊 Dashboards</h3>
            <a href="/google-services-dashboard" class="button">Google Dashboard</a>
            <a href="/services" class="button">Services Overview</a>
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

@app.route("/auth-dashboard")
def auth_dashboard():
    """Comprehensive authentication dashboard"""
    try:
        from helpers.token_storage import token_storage
        
        # Get status of all authentication methods
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
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Wednesday Assistant - Authentication Dashboard</title>
            <style>
                body {{ 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 0; padding: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: #333; min-height: 100vh;
                }}
                .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
                .header {{ text-align: center; color: white; margin-bottom: 40px; }}
                .auth-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; }}
                .auth-card {{ 
                    background: white; border-radius: 15px; padding: 25px; box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                    transition: transform 0.3s ease; border-left: 5px solid #007bff;
                }}
                .auth-card:hover {{ transform: translateY(-5px); }}
                .service-header {{ display: flex; align-items: center; margin-bottom: 20px; }}
                .service-icon {{ font-size: 2em; margin-right: 15px; }}
                .service-title {{ font-size: 1.4em; font-weight: bold; margin: 0; }}
                .status-indicator {{ 
                    display: inline-block; width: 12px; height: 12px; border-radius: 50%;
                    margin-left: 10px;
                }}
                .status-connected {{ background: #28a745; }}
                .status-disconnected {{ background: #dc3545; }}
                .status-partial {{ background: #ffc107; }}
                .auth-details {{ margin: 15px 0; }}
                .auth-row {{ display: flex; justify-content: space-between; margin: 8px 0; }}
                .auth-label {{ font-weight: 500; color: #666; }}
                .auth-value {{ font-weight: 600; }}
                .success {{ color: #28a745; }}
                .warning {{ color: #ffc107; }}
                .error {{ color: #dc3545; }}
                .button {{ 
                    display: inline-block; padding: 10px 20px; margin: 5px;
                    background: #007bff; color: white; text-decoration: none;
                    border-radius: 5px; transition: background 0.3s ease;
                }}
                .button:hover {{ background: #0056b3; }}
                .button.success {{ background: #28a745; }}
                .button.success:hover {{ background: #1e7e34; }}
                .button.warning {{ background: #ffc107; color: #212529; }}
                .button.warning:hover {{ background: #e0a800; }}
                .button.danger {{ background: #dc3545; }}
                .button.danger:hover {{ background: #c82333; }}
                .footer {{ text-align: center; margin-top: 40px; color: white; opacity: 0.8; }}
                .info-box {{ 
                    background: #f8f9fa; border-radius: 8px; padding: 15px; margin: 15px 0;
                    border-left: 4px solid #17a2b8;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🤖 Wednesday Assistant</h1>
                    <h2>Authentication Dashboard</h2>
                    <p>Manage your service connections and authentication status</p>
                </div>
                
                <div class="auth-grid">
                    <!-- Spotify Authentication Card -->
                    <div class="auth-card">
                        <div class="service-header">
                            <div class="service-icon">🎵</div>
                            <div class="service-title">Spotify</div>
                            <div class="status-indicator {'status-connected' if spotify_working else 'status-disconnected'}"></div>
                        </div>
                        
                        <div class="auth-details">
                            <div class="auth-row">
                                <span class="auth-label">Status:</span>
                                <span class="auth-value {'success' if spotify_working else 'error'}">
                                    {'✅ Connected' if spotify_working else '❌ Not Connected'}
                                </span>
                            </div>
                            <div class="auth-row">
                                <span class="auth-label">Session Token:</span>
                                <span class="auth-value {'success' if session_spotify else 'error'}">
                                    {'✅ Available' if session_spotify else '❌ Missing'}
                                </span>
                            </div>
                            <div class="auth-row">
                                <span class="auth-label">Stored Token:</span>
                                <span class="auth-value {'success' if spotify_tokens else 'error'}">
                                    {'✅ Available' if spotify_tokens else '❌ Missing'}
                                </span>
                            </div>
                            <div class="auth-row">
                                <span class="auth-label">Environment Token:</span>
                                <span class="auth-value {'success' if env_spotify_token else 'error'}">
                                    {'✅ Available' if env_spotify_token else '❌ Missing'}
                                </span>
                            </div>
                        </div>
                        
                        <div style="text-align: center;">
                            <a href="/login" class="button">🔐 Login to Spotify</a>
                            <a href="/spotify-status" class="button warning">📊 Check Status</a>
                            <a href="/clear-spotify-tokens" class="button danger">🗑️ Clear Tokens</a>
                        </div>
                        
                        <div class="info-box">
                            <strong>What this enables:</strong>
                            <ul style="margin: 5px 0; padding-left: 20px;">
                                <li>Music playback control</li>
                                <li>Play songs, albums, playlists</li>
                                <li>Current song information</li>
                            </ul>
                        </div>
                    </div>
                    
                    <!-- Google Authentication Card -->
                    <div class="auth-card">
                        <div class="service-header">
                            <div class="service-icon">📧</div>
                            <div class="service-title">Google Services</div>
                            <div class="status-indicator {'status-connected' if google_working else 'status-disconnected'}"></div>
                        </div>
                        
                        <div class="auth-details">
                            <div class="auth-row">
                                <span class="auth-label">Status:</span>
                                <span class="auth-value {'success' if google_working else 'error'}">
                                    {'✅ Connected' if google_working else '❌ Not Connected'}
                                </span>
                            </div>
                            <div class="auth-row">
                                <span class="auth-label">Session Token:</span>
                                <span class="auth-value {'success' if session_google else 'error'}">
                                    {'✅ Available' if session_google else '❌ Missing'}
                                </span>
                            </div>
                            <div class="auth-row">
                                <span class="auth-label">Stored Token:</span>
                                <span class="auth-value {'success' if google_tokens else 'error'}">
                                    {'✅ Available' if google_tokens else '❌ Missing'}
                                </span>
                            </div>
                            <div class="auth-row">
                                <span class="auth-label">Environment Token:</span>
                                <span class="auth-value {'success' if env_google_token else 'error'}">
                                    {'✅ Available' if env_google_token else '❌ Missing'}
                                </span>
                            </div>
                        </div>
                        
                        <div style="text-align: center;">
                            <a href="/google-login" class="button">🔐 Login to Google</a>
                            <a href="/google-status" class="button warning">📊 Check Status</a>
                            <a href="/test-google-services" class="button success">🧪 Test Services</a>
                        </div>
                        
                        <div class="info-box">
                            <strong>What this enables:</strong>
                            <ul style="margin: 5px 0; padding-left: 20px;">
                                <li>Email reading and sending</li>
                                <li>Calendar management</li>
                                <li>Voice to text and text to speech</li>
                                <li>Contact management</li>
                            </ul>
                        </div>
                    </div>
                    
                    <!-- Optional Services Card -->
                    <div class="auth-card">
                        <div class="service-header">
                            <div class="service-icon">🌟</div>
                            <div class="service-title">Optional Services</div>
                            <div class="status-indicator status-partial"></div>
                        </div>
                        
                        <div class="auth-details">
                            <div class="auth-row">
                                <span class="auth-label">Weather API:</span>
                                <span class="auth-value {'success' if os.getenv('WEATHERAPI_KEY') else 'warning'}">
                                    {'✅ Configured' if os.getenv('WEATHERAPI_KEY') else '⚠️ Not Set'}
                                </span>
                            </div>
                            <div class="auth-row">
                                <span class="auth-label">News API:</span>
                                <span class="auth-value {'success' if os.getenv('NEWS_API_KEY') else 'warning'}">
                                    {'✅ Configured' if os.getenv('NEWS_API_KEY') else '⚠️ Not Set'}
                                </span>
                            </div>
                            <div class="auth-row">
                                <span class="auth-label">Search API:</span>
                                <span class="auth-value warning">⚠️ Configure for web search</span>
                            </div>
                        </div>
                        
                        <div style="text-align: center;">
                            <a href="/weather?location=London" class="button warning">🌤️ Test Weather</a>
                            <a href="/news" class="button warning">📰 Test News</a>
                            <a href="/test-speech" class="button warning">🎙️ Test Speech</a>
                        </div>
                        
                        <div class="info-box">
                            <strong>To enable these features:</strong>
                            <ol style="margin: 5px 0; padding-left: 20px; font-size: 0.9em;">
                                <li>Get API keys from respective services</li>
                                <li>Add them to your environment variables</li>
                                <li>Restart the application</li>
                            </ol>
                        </div>
                    </div>
                </div>
                
                <!-- Quick Actions Section -->
                <div style="margin-top: 40px; text-align: center;">
                    <h3 style="color: white;">Quick Actions</h3>
                    <a href="/health" class="button success">📊 System Health</a>
                    <a href="/services" class="button">🔧 All Services</a>
                    <a href="/quick-setup" class="button warning">⚡ Quick Setup</a>
                    <a href="/test-webhook-auth" class="button">📨 Test Webhook</a>
                </div>
                
                <div class="footer">
                    <p>Wednesday WhatsApp Assistant v2.0 | Enhanced with Persistent Authentication</p>
                    <p>🔐 Your tokens are stored securely and will persist across restarts</p>
                </div>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        return f"""
        <h1>❌ Error Loading Authentication Dashboard</h1>
        <p>Error: {str(e)}</p>
        <a href="/quick-setup">← Back to Setup</a>
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
        
        # Test ChromaDB availability
        if CHROMADB_AVAILABLE:
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
                results["chromadb_error"] = str(e)
        else:
            results["chromadb_available"] = False
            
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
            if CHROMADB_AVAILABLE:
                add_to_conversation_history(phone, "user", message)
            
            # Generate response using Gemini (implement this based on your gemini.py)
            response = self._generate_response(message, phone)
            
            if CHROMADB_AVAILABLE:
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

if __name__ == '__main__':
    logger.info("Launching Memory-Optimized WhatsApp Assistant...")
    
    # Start WAHA keep-alive to prevent session timeout
    start_waha_keepalive()
    
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode, threaded=True)
