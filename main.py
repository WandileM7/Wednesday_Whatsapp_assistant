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

# Timeout exception for webhook processing
class TimeoutException(Exception):
    pass

from flask import Flask, redirect, request, jsonify, session, url_for
from flask_session import Session
from werkzeug.middleware.proxy_fix import ProxyFix

# Import handlers
from handlers.google_auth import auth_bp
from handlers.speech import speech_to_text, text_to_speech, download_voice_message, should_respond_with_voice, cleanup_temp_file
from handlers.auth_manager import auth_manager
from handlers.weather import weather_service
from handlers.news import news_service
from handlers.tasks import task_manager
from handlers.contacts import contact_manager
from handlers.spotify_client import make_spotify_oauth

# Google and Spotify imports
import google.generativeai as genai
from spotipy.oauth2 import SpotifyOAuth
import spotipy

# Set up logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Only console logging for memory efficiency
    ]
)
logger = logging.getLogger("WhatsAppAssistant")

# ChromaDB imports with fallback
try:
    from chromedb import add_to_conversation_history, query_conversation_history
    CHROMADB_AVAILABLE = True
except ImportError as e:
    logger.warning(f"ChromaDB not available: {e}")
    CHROMADB_AVAILABLE = False
    
    # Fallback functions
    def add_to_conversation_history(phone, role, message):
        return True
    def query_conversation_history(phone, query, limit=5):
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

    def execute_function(call):
        # No function calling in fallback
        return call.get("content") or "Function calling is disabled in fallback mode."

# Initialize Gemini (non-fatal if missing)
gemini_api_key = os.getenv("GEMINI_API_KEY")
class _DummyModel:
    def generate_content(self, prompt: str):
        class _R:
            text = "Hello. Gemini is not configured; using a dummy response."
        return _R()

if gemini_api_key:
    try:
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        logger.info("Gemini client initialized")
    except Exception as e:
        logger.warning(f"Gemini init failed; using dummy model: {e}")
        model = _DummyModel()
else:
    logger.warning("GEMINI_API_KEY not set. Using dummy model; app will still start.")
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
    logger.warning("WAHA_URL not set. Set WAHA_URL to the WAHA public endpoint (e.g.https://waha-service-ypoa.onrender.com/api/sendText)")

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
        session_name = WAHA_SESSION or "default"
        h = _waha_headers()
        r = requests.get(f"{base}/api/sessions/{session_name}", headers=h, timeout=10)
        if r.status_code == 200:
            data = r.json()
            status = (data.get("status") or "").lower()
            return status in ("working", "active", "connected", "ready")
        if r.status_code == 404:
            rc = requests.post(f"{base}/api/sessions/{session_name}", headers=h, timeout=15)
            if rc.status_code not in (200, 201, 409):
                logger.warning(f"WAHA create session failed: {rc.status_code} {rc.text}")
        rs = requests.post(f"{base}/api/sessions/{session_name}/start", headers=h, timeout=20)
        if rs.status_code in (200, 202):
            return True
        if rs.status_code == 422 and "already started" in rs.text.lower():
            return True
        logger.warning(f"WAHA start session response: {rs.status_code} {rs.text}")
        return False
    except Exception as e:
        logger.warning(f"WAHA health check error: {e}")
        return False

def waha_keepalive():
    """Background keep-alive loop that maintains the WAHA session."""
    global waha_keepalive_active
    while waha_keepalive_active:
        ok = waha_health_check()
        logger.info(f"WAHA keep-alive: {'OK' if ok else 'NOT READY'}")
        time.sleep(WAHA_KEEPALIVE_INTERVAL)

def start_waha_keepalive():
    global waha_keepalive_active
    if waha_keepalive_active:
        return
    waha_keepalive_active = True
    threading.Thread(target=waha_keepalive, daemon=True).start()

def stop_waha_keepalive():
    global waha_keepalive_active
    waha_keepalive_active = False

# Spotify OAuth Setup
SPOTIFY_SCOPE = "user-read-playback-state user-modify-playback-state"

def get_token_info():
    """Get token info from session and refresh if needed"""
    token_info = session.get("token_info", {})
    if not token_info:
        refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
        if refresh_token:
            try:
                sp_oauth = make_spotify_oauth()
                token_info = sp_oauth.refresh_access_token(refresh_token)
                session["token_info"] = token_info
                return token_info
            except Exception as e:
                logger.error(f"Error refreshing token from environment: {e}")
                return None
        return None
    
    sp_oauth = make_spotify_oauth()
    if sp_oauth.is_token_expired(token_info):
        try:
            token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
            session["token_info"] = token_info
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
    return jsonify({"status": "online", "services": ["spotify", "gmail", "gemini", "weather", "tasks", "contacts"]})

@app.route("/login")
def spotify_login():
    sp_oauth = make_spotify_oauth()
    return redirect(sp_oauth.get_authorize_url())

@app.route("/callback")
def spotify_callback():
    """Handle Spotify OAuth callback with auto-save"""
    code = request.args.get('code')
    error = request.args.get('error')
    
    if error:
        logger.error(f"Spotify OAuth error: {error}")
        return f"❌ Authorization Error: {error}", 400
    
    if not code:
        return "❌ No authorization code received from Spotify.", 400
    
    try:
        sp_oauth = make_spotify_oauth()
        token_info = sp_oauth.get_access_token(code)
        session["token_info"] = token_info
        
        # Save globally for webhook access
        from handlers.spotify import save_token_globally
        save_token_globally(token_info)
        
        # Save tokens for future automation
        if token_info.get('refresh_token'):
            logger.info("=== SPOTIFY TOKENS FOR ENVIRONMENT SETUP ===")
            logger.info(f"SPOTIFY_REFRESH_TOKEN={token_info['refresh_token']}")
            logger.info(f"SPOTIFY_ACCESS_TOKEN={token_info['access_token']}")
            logger.info("Add these to your environment variables for automatic authentication")
            logger.info("=============================================")
        
        logger.info("Spotify authorization successful")
        return """
        <h2>✅ Spotify Authorization Successful!</h2>
        <p>Your tokens have been saved for automatic authentication.</p>
        <p>Check your logs for environment variables to add to your deployment.</p>
        <h3>Quick Tests</h3>
        <ul>
            <li><a href="/test-spotify">Test Spotify</a></li>
        </ul>
        """
    except Exception as e:
        logger.error(f"Error getting Spotify token: {e}")
        return f"❌ Error getting token: {str(e)}", 500

@app.route("/spotify-callback")
def spotify_callback_alias():
    # Support SPOTIFY_REDIRECT_URI=http://localhost:5000/spotify-callback
    return spotify_callback()

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    """Enhanced webhook with robust error handling to prevent 503 errors"""
    if request.method == 'GET':
        return jsonify({"status": "online", "memory_optimized": True})

    start_time = time.time()
    try:
        # Quick validation to prevent processing invalid requests
        data = request.get_json() or {}
        if not data:
            return jsonify({'status': 'ignored', 'reason': 'no_data'}), 200
            
        payload = data.get('payload', data)
        if not payload:
            return jsonify({'status': 'ignored', 'reason': 'no_payload'}), 200
        
        # Handle both text and voice messages
        user_msg = payload.get('body') or payload.get('text') or payload.get('message')
        phone = payload.get('chatId') or payload.get('from')
        is_voice_message = False
        
        # Cache user session data
        cache_user_session(phone)
        
        # Check for voice message
        if not user_msg and payload.get('type') == 'voice':
            voice_data = payload.get('voice') or payload.get('media')
            if voice_data:
                voice_url = voice_data.get('url') or voice_data.get('downloadUrl')
                if voice_url:
                    logger.info(f"Processing voice message from {phone}")
                    # Download and transcribe voice message
                    audio_file = download_voice_message(voice_url, os.getenv("WAHA_SESSION"))
                    if audio_file:
                        user_msg = speech_to_text(audio_file)
                        is_voice_message = True
                        if user_msg:
                            logger.info(f"Voice transcribed: {user_msg[:50]}...")
                        else:
                            logger.warning("Could not transcribe voice message")
                            return jsonify({'status': 'ignored'}), 200

        if not user_msg or not phone:
            return jsonify({'status': 'ignored', 'reason': 'missing_data'}), 200

        if payload.get('fromMe'):
            return jsonify({'status': 'ignored', 'reason': 'from_me'}), 200
            
        # Rate limiting check
        if not check_rate_limit(phone):
            logger.warning(f"Rate limit exceeded for {phone}")
            return jsonify({'status': 'rate_limited', 'message': 'Too many requests'}), 200

        logger.info(f"Processing {'voice' if is_voice_message else 'text'} message from {phone}: {user_msg[:30]}...")
        
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
            'timestamp': time.time()
        })
        
        conversation['messages'] = conversation['messages'][-MAX_MESSAGES_PER_USER:]
        conversation['last_activity'] = time.time()

        if len(user_conversations) % 10 == 0:
            cleanup_conversations()

        # Process with Gemini with timeout protection
        try:
            # Check if API key looks valid (not a test key)
            if GEMINI_API_KEY and not GEMINI_API_KEY.startswith('test_'):
                call = chat_with_functions(user_msg, phone)
                logger.debug(f"Gemini function response: {call}")

                if call.get("name"):
                    reply = execute_function(call)
                else:
                    reply = call.get("content", "Sorry, no idea what that was.")
            else:
                # Fallback mode for invalid/test API keys
                logger.warning("Using fallback mode: Gemini API key not properly configured")
                reply = f"Echo (fallback mode): {user_msg}. Please configure a valid Gemini API key for full functionality."
        except Exception as e:
            logger.error(f"Gemini processing error: {e}")
            reply = "I'm having trouble processing your message right now. Please try again later."

        # Save to ChromaDB if enabled
        if CHROMADB_AVAILABLE and os.getenv("ENABLE_CHROMADB", "false").lower() == "true":
            try:
                add_to_conversation_history(phone, "user", user_msg)
                add_to_conversation_history(phone, "assistant", reply)
            except Exception as e:
                logger.warning(f"ChromaDB save error: {e}")

        conversation['messages'].append({
            'role': 'assistant',
            'content': reply,
            'timestamp': time.time()
        })
        conversation['messages'] = conversation['messages'][-MAX_MESSAGES_PER_USER:]

        # Decide whether to send voice or text response
        if should_respond_with_voice(is_voice_message, len(reply)):
            success = send_voice_message(phone, reply)
            if not success:
                # Fallback to text if voice fails
                logger.warning("Voice response failed, falling back to text")
                send_message(phone, reply)
        else:
            send_message(phone, reply)
            
        # Log processing time for monitoring
        processing_time = time.time() - start_time
        logger.debug(f"Webhook processed in {processing_time:.2f}s")
        
        return jsonify({
            'status': 'ok', 
            'memory_optimized': True,
            'processing_time_ms': int(processing_time * 1000)
        })

    except MemoryError:
        logger.error("Memory error in webhook processing")
        return jsonify({'status': 'error', 'message': 'Memory limit exceeded'}), 503
    except TimeoutException:
        logger.error("Timeout in webhook processing")  
        return jsonify({'status': 'error', 'message': 'Request timeout'}), 503
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Error during chat processing after {processing_time:.2f}s: {e}")
        
        # Return 200 instead of 500 to prevent webhook retries from WAHA
        return jsonify({
            'status': 'error', 
            'message': 'Processing failed', 
            'error_type': type(e).__name__,
            'processing_time_ms': int(processing_time * 1000)
        }), 200  # Changed from 500 to 200

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
    """Check Google services status"""
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
                        "credential_type": "service_account" if hasattr(creds, 'service_account_email') else "oauth"
                    })
                except Exception as e:
                    status.update({
                        "credentials_loaded": False,
                        "load_error": str(e)
                    })
        
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
                "required_env": "OPENWEATHER_API_KEY"
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

@app.route("/clear-spotify-tokens")
def clear_spotify_tokens():
    """Clear all Spotify tokens"""
    session.pop("token_info", None)
    return "✅ Spotify tokens cleared. Please visit /login to re-authenticate."

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
        payload = {"chatId": phone, "text": text}
        r = requests.post(waha_url, headers=_waha_headers(), data=json.dumps(payload), timeout=20)
        if r.status_code in (200, 201):
            return True
        base = _waha_base()
        session_name = WAHA_SESSION or "default"
        alt = f"{base}/api/sessions/{session_name}/messages/text"
        r2 = requests.post(alt, headers=_waha_headers(), data=json.dumps(payload), timeout=20)
        if r2.status_code in (200, 201):
            return True
        logger.error(f"WAHA send_message failed: {r.status_code} {r.text} | alt={r2.status_code} {r2.text}")
        return False
    except Exception as e:
        logger.error(f"WAHA send_message error: {e}")
        return False

def send_voice_message(phone, text):
    """Send voice message by converting text to speech"""
    try:
        phone = phone if "@c.us" in phone else f"{phone}@c.us"
        audio_file = text_to_speech(text)
        if not audio_file:
            logger.error("Failed to generate voice from text")
            return False
        if not waha_health_check():
            return False
        base = _waha_base()
        session_name = WAHA_SESSION or "default"
        files = {
            "file": open(audio_file, "rb"),
            "chatId": (None, phone),
            "filename": (None, os.path.basename(audio_file)),
        }
        ep1 = f"{base}/api/sendFile"
        ep2 = f"{base}/api/sessions/{session_name}/messages/file"
        for ep in (ep1, ep2):
            try:
                resp = requests.post(ep, headers=_waha_headers(is_json=False), files=files, timeout=60)
                if resp.status_code in (200, 201):
                    cleanup_temp_file(audio_file)
                    return True
            except Exception:
                pass
        logger.warning(f"WAHA voice send failed via {ep1} and {ep2}")
        cleanup_temp_file(audio_file)
        return False
    except Exception as e:
        logger.error(f"WAHA voice send error: {e}")
        return False

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
                OPENWEATHER_API_KEY=your_openweather_key<br>
                NEWS_API_KEY=your_newsapi_key
            </code>
        </div>
    </body>
    </html>
    """

@app.route("/test-speech")
def test_speech():
    """Test speech functionality"""
    results = {
        "timestamp": datetime.now().isoformat(),
        "speech_tests": {}
    }
    
    # Test voice response logic
    os.environ.setdefault("ENABLE_VOICE_RESPONSES", "true")
    os.environ.setdefault("MAX_VOICE_RESPONSE_LENGTH", "200")
    
    results["speech_tests"]["voice_logic"] = {
        "user_voice_short": should_respond_with_voice(True, 50),
        "user_voice_long": should_respond_with_voice(True, 300),
        "user_text_short": should_respond_with_voice(False, 50),
        "user_text_long": should_respond_with_voice(False, 300),
        "settings": {
            "voice_enabled": os.getenv("ENABLE_VOICE_RESPONSES", "true"),
            "max_length": os.getenv("MAX_VOICE_RESPONSE_LENGTH", "200")
        }
    }
    
    # Test TTS client availability
    try:
        from handlers.speech import get_tts_client, get_speech_client
        tts_client = get_tts_client()
        speech_client = get_speech_client()
        
        results["speech_tests"]["clients"] = {
            "tts_available": tts_client is not None,
            "stt_available": speech_client is not None
        }
    except Exception as e:
        results["speech_tests"]["clients"] = {
            "error": str(e)
        }
    
    # Test simple TTS if available
    try:
        test_audio = text_to_speech("Hello, this is a test.")
        if test_audio:
            cleanup_temp_file(test_audio)
            results["speech_tests"]["tts_test"] = {"success": True}
        else:
            results["speech_tests"]["tts_test"] = {"success": False, "reason": "No audio generated"}
    except Exception as e:
        results["speech_tests"]["tts_test"] = {"success": False, "error": str(e)}
    
    return jsonify(results)

if __name__ == '__main__':
    logger.info("Launching Memory-Optimized WhatsApp Assistant...")
    
    # Start WAHA keep-alive to prevent session timeout
    start_waha_keepalive()
    
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode, threaded=True)
