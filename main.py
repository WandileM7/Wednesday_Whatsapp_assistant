import json
from dotenv import load_dotenv

from flask import Flask, redirect, request, jsonify, session, url_for
from handlers.gemini import chat_with_functions, execute_function
from handlers.google_auth import auth_bp
from handlers.speech import speech_to_text, text_to_speech, download_voice_message, should_respond_with_voice, cleanup_temp_file
import google.generativeai as genai
import sys
import os
import requests
import logging
import time
import threading
from flask_session import Session
from handlers.spotify_client import make_spotify_oauth

# ChromaDB imports with fallback
try:
    from chromedb import add_to_conversation_history, query_conversation_history
    CHROMADB_AVAILABLE = True
except ImportError as e:
    logger = logging.getLogger("WhatsAppAssistant")
    logger.warning(f"ChromaDB not available: {e}")
    CHROMADB_AVAILABLE = False
    
    # Fallback functions
    def add_to_conversation_history(phone, role, message):
        return True
    
    def query_conversation_history(phone, query, limit=5):
        return []

from datetime import datetime
from werkzeug.middleware.proxy_fix import ProxyFix
from spotipy.oauth2 import SpotifyOAuth
import spotipy

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Only console logging for memory efficiency
    ]
)
logger = logging.getLogger("WhatsAppAssistant")

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

# Initialize Gemini
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    logger.error("GEMINI_API_KEY is not set. Quitting.")
    sys.exit(1)

try:
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel('gemini-2.0-flash')
    logger.info("Gemini client initialized")
except Exception as e:
    logger.error(f"Gemini init failed: {e}")
    sys.exit(1)

PERSONALITY_PROMPT = os.getenv("PERSONALITY_PROMPT", "You are a sarcastic and sassy assistant.")
GREETING_PROMPT = os.getenv("GREETING_PROMPT", "Give a brief, sarcastic greeting.")
INITIAL_MESSAGE_PROMPT = os.getenv("INITIAL_MESSAGE_PROMPT", "Send a mysterious message under 50 words.")

waha_url = os.getenv("WAHA_URL")
if not waha_url:
    logger.warning("WAHA_URL not set!")

# WAHA Keep-Alive Configuration
WAHA_KEEPALIVE_INTERVAL = int(os.getenv("WAHA_KEEPALIVE_INTERVAL", "600"))  # 10 minutes default
WAHA_SESSION = os.getenv("WAHA_SESSION", "default")
waha_keepalive_active = False

def waha_health_check():
    """Check WAHA health status"""
    try:
        if not waha_url:
            return False
        
        # Try to get sessions list or status from WAHA
        health_url = waha_url.replace("/api/sendText", "/api/sessions")
        response = requests.get(health_url, timeout=10)
        
        if response.status_code == 200:
            sessions = response.json()
            # Check if our session exists and is active
            for session in sessions:
                if session.get("name") == WAHA_SESSION:
                    status = session.get("status", "").lower()
                    logger.info(f"WAHA session {WAHA_SESSION} status: {status}")
                    return status in ["working", "authenticated", "ready"]
            
            logger.warning(f"WAHA session {WAHA_SESSION} not found in active sessions")
            return False
        else:
            logger.warning(f"WAHA health check failed: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"WAHA health check error: {e}")
        return False

def waha_keepalive():
    """Send periodic keep-alive to WAHA to prevent session timeout"""
    global waha_keepalive_active
    
    while waha_keepalive_active:
        try:
            if waha_health_check():
                logger.info("WAHA session is healthy")
            else:
                logger.warning("WAHA session check failed - may need reconnection")
            
            # Wait for the specified interval
            time.sleep(WAHA_KEEPALIVE_INTERVAL)
            
        except Exception as e:
            logger.error(f"WAHA keep-alive error: {e}")
            time.sleep(60)  # Wait 1 minute on error before retrying

def start_waha_keepalive():
    """Start the WAHA keep-alive background thread"""
    global waha_keepalive_active
    
    if not waha_url:
        logger.warning("WAHA_URL not set, skipping keep-alive")
        return
    
    if waha_keepalive_active:
        logger.info("WAHA keep-alive already running")
        return
    
    waha_keepalive_active = True
    keepalive_thread = threading.Thread(target=waha_keepalive, daemon=True)
    keepalive_thread.start()
    logger.info(f"WAHA keep-alive started (interval: {WAHA_KEEPALIVE_INTERVAL}s)")

def stop_waha_keepalive():
    """Stop the WAHA keep-alive background thread"""
    global waha_keepalive_active
    waha_keepalive_active = False
    logger.info("WAHA keep-alive stopped")

# Spotify OAuth Setup
SPOTIFY_SCOPE = "user-read-playback-state user-modify-playback-state"

def make_spotify_oauth():
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
        scope=SPOTIFY_SCOPE,
        cache_path=None
    )

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

# Add these functions after your existing Spotify functions (around line 100)

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
        logger.error(f"Google auth initialization failed: {e}")
        return False

def save_google_tokens_to_env(credentials):
    """Save Google tokens to environment variables for automation"""
    try:
        if not credentials.refresh_token:
            logger.warning("No refresh token available - cannot save for automation")
            return False
            
        # Log the tokens so you can add them to your environment
        logger.info("=== GOOGLE TOKENS FOR ENVIRONMENT SETUP ===")
        logger.info(f"GOOGLE_REFRESH_TOKEN={credentials.refresh_token}")
        logger.info(f"GOOGLE_ACCESS_TOKEN={credentials.token}")
        logger.info(f"GOOGLE_CLIENT_ID={credentials.client_id}")
        logger.info(f"GOOGLE_CLIENT_SECRET={credentials.client_secret}")
        logger.info("Add these to your environment variables for automatic authentication")
        logger.info("=============================================")
        
        # Also try to update .env file if it exists
        try:
            env_file = ".env"
            if os.path.exists(env_file):
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

def initialize_services():
    """Initialize all services on startup"""
    logger.info("Initializing services...")
    
    # Initialize Spotify authentication
    refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
    if refresh_token:
        try:
            sp_oauth = make_spotify_oauth()
            token_info = sp_oauth.refresh_access_token(refresh_token)
            session["token_info"] = token_info
            
            # Also save globally for webhook access
            from handlers.spotify import save_token_globally
            save_token_globally(token_info)
            
            logger.info("✅ Spotify authentication ready (auto-refreshed)")
        except Exception as e:
            logger.error(f"Failed to initialize Spotify: {e}")
    else:
        logger.warning("❌ No Spotify refresh token - manual setup required")
    
    # Initialize Google authentication
    initialize_google_auth()
    
    logger.info("Service initialization complete")

# Add this after your app configuration but before the routes (around line 90):
# Initialize services on startup
try:
    with app.app_context():
        initialize_services()
except Exception as e:
    logger.error(f"Service initialization failed: {e}")

# Routes
@app.route("/")
def home():
    return jsonify({"status": "online", "services": ["spotify", "gmail", "gemini"]})

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

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    if request.method == 'GET':
        return jsonify({"status": "online", "memory_optimized": True})

    try:
        data = request.get_json() or {}
        payload = data.get('payload', data)
        
        # Handle both text and voice messages
        user_msg = payload.get('body') or payload.get('text') or payload.get('message')
        phone = payload.get('chatId') or payload.get('from')
        is_voice_message = False
        
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
            return jsonify({'status': 'ignored'}), 200

        if payload.get('fromMe'):
            return jsonify({'status': 'ignored'}), 200

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

        # Process with Gemini
        call = chat_with_functions(user_msg, phone)
        logger.debug(f"Gemini function response: {call}")

        if call.get("name"):
            reply = execute_function(call)
        else:
            reply = call.get("content", "Sorry, no idea what that was.")

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
            
        return jsonify({'status': 'ok', 'memory_optimized': True})

    except Exception as e:
        logger.error(f"Error during chat processing: {e}")
        return jsonify({'status': 'error', 'message': 'Processing failed'}), 500

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

# Add the new Google service routes here:
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
        
        # Send a test email to yourself (fix the email address)
        result = send_email(
            to="wandilemawela4@gmail.com",  # Fixed - removed the extra .com
            subject="Test Email from WhatsApp Assistant",
            body="This is a test email to verify Gmail integration is working."
        )
        
        return {
            "test": "email_send",
            "result": result,
            "success": not result.startswith("❌"),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}, 500

# Add the test current email route
@app.route("/test-current-email")
def test_current_email():
    """Test email with current session authentication"""
    try:
        from handlers.gmail import send_email
        
        # Test with current session
        result = send_email(
            to="wandilemawela4@gmail.com",  # Your email
            subject="Test from Current Session",
            body="Testing email functionality with current authentication session."
        )
        
        return {
            "result": result,
            "success": not result.startswith("❌"),
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
    # Check Spotify status
    spotify_status = "not_configured"
    spotify_refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
    if os.getenv("SPOTIFY_CLIENT_ID"):
        if spotify_refresh_token:
            spotify_status = "auto_configured"
        elif session.get("token_info"):
            spotify_status = "session_configured"
        else:
            spotify_status = "configured"
    
    # Check Google status
    google_status = "not_configured"
    google_refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        if google_refresh_token:
            google_status = "auto_configured"
        else:
            try:
                from handlers.google_auth import load_credentials
                creds = load_credentials()
                if creds and creds.valid:
                    google_status = "authenticated"
                else:
                    google_status = "configured"
            except:
                google_status = "configured"
    
    return {
        "services": {
            "whatsapp": {
                "status": "active",
                "webhook_url": request.host_url + "webhook",
                "test_endpoint": "/health"
            },
            "spotify": {
                "status": spotify_status,
                "auth_url": "/login",
                "test_endpoint": "/test-spotify",
                "has_refresh_token": bool(spotify_refresh_token),
                "session_active": bool(session.get("token_info"))
            },
            "google": {
                "status": google_status,
                "auth_url": "/google-login",
                "test_endpoint": "/test-gmail",
                "dashboard": "/google-services-dashboard",
                "has_refresh_token": bool(google_refresh_token),
                "setup_auto_auth": "/setup-google-auto-auth"
            },
            "gemini": {
                "status": "active" if os.getenv("GEMINI_API_KEY") else "not_configured",
                "model": "gemini-2.0-flash"
            }
        },
        "quick_links": {
            "authenticate_google": "/google-login",
            "authenticate_spotify": "/login",
            "setup_google_auto_auth": "/setup-google-auto-auth",
            "test_all": "/health",
            "webhook": "/webhook",
            "force_google_auth": "/force-google-auth"
        },
        "authentication_status": {
            "spotify_auto": bool(spotify_refresh_token),
            "google_auto": bool(google_refresh_token),
            "requires_manual_setup": not (spotify_refresh_token and google_refresh_token)
        }
    }

# Spotify endpoints (continue with existing Spotify routes...)
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
            "timestamp": datetime.now().isoformat()
        })
    except ImportError:
        return jsonify({
            "status": "healthy",
            "memory_mb": "unavailable",
            "active_conversations": len(user_conversations),
            "waha_status": "connected" if waha_health_check() else "disconnected" if waha_url else "not_configured",
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
    """Check WAHA connection status and keep-alive status"""
    global waha_keepalive_active
    
    try:
        waha_healthy = waha_health_check()
        
        return jsonify({
            "waha_url": waha_url,
            "waha_session": WAHA_SESSION,
            "waha_healthy": waha_healthy,
            "keepalive_active": waha_keepalive_active,
            "keepalive_interval": WAHA_KEEPALIVE_INTERVAL,
            "status": "connected" if waha_healthy else "disconnected",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "status": "error",
            "timestamp": datetime.now().isoformat()
        }), 500

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
            requests.post(url, json={"chatId": phone, "session": os.getenv("WAHA_SESSION")})
            if action == "startTyping":
                time.sleep(seconds)
        return True
    except Exception as e:
        logger.error(f"Typing indicator error: {e}")
        return False

def send_message(phone, text):
    """Memory-efficient message sending"""
    try:
        phone = phone if "@c.us" in phone else f"{phone}@c.us"
        
        payload = {
            "session": os.getenv("WAHA_SESSION", "default"),
            "chatId": phone,
            "text": text
        }
        
        r = requests.post(os.getenv("WAHA_URL"), json=payload, timeout=15)
        
        if r.status_code in [200, 201]:
            logger.info(f"Message sent successfully to {phone}")
            return True
        else:
            logger.error(f"Failed to send message: {r.status_code} - {r.text}")
            return False
        
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return False

def send_voice_message(phone, text):
    """Send voice message by converting text to speech"""
    try:
        phone = phone if "@c.us" in phone else f"{phone}@c.us"
        
        # Convert text to speech
        audio_file = text_to_speech(text)
        if not audio_file:
            logger.error("Failed to generate voice from text")
            return False
        
        try:
            # Upload voice file to WAHA
            voice_url = os.getenv("WAHA_URL").replace("sendText", "sendVoice")
            
            with open(audio_file, 'rb') as f:
                files = {'file': f}
                data = {
                    'session': os.getenv("WAHA_SESSION", "default"),
                    'chatId': phone
                }
                
                r = requests.post(voice_url, files=files, data=data, timeout=30)
                
                if r.status_code in [200, 201]:
                    logger.info(f"Voice message sent successfully to {phone}")
                    return True
                else:
                    logger.error(f"Failed to send voice message: {r.status_code} - {r.text}")
                    return False
                    
        finally:
            # Clean up temporary file
            cleanup_temp_file(audio_file)
        
    except Exception as e:
        logger.error(f"Error sending voice message: {e}")
        return False

# Add this route after your existing Google routes (around line 580)

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
    """Setup automatic authentication for all services"""
    results = {
        "timestamp": datetime.now().isoformat(),
        "services": {}
    }
    
    # Setup Spotify auto-auth
    try:
        token_info = get_token_info()
        if token_info and token_info.get('refresh_token'):
            spotify_refresh = token_info['refresh_token']
            results["services"]["spotify"] = {
                "success": True,
                "message": "Spotify refresh token available",
                "refresh_token": spotify_refresh[:20] + "...",
                "env_var": f"SPOTIFY_REFRESH_TOKEN={spotify_refresh}"
            }
        else:
            results["services"]["spotify"] = {
                "success": False,
                "message": "No Spotify refresh token available",
                "action": "Visit /login to authenticate Spotify"
            }
    except Exception as e:
        results["services"]["spotify"] = {
            "success": False,
            "error": str(e)
        }
    
    # Setup Google auto-auth
    try:
        if 'google_credentials' in session:
            from google.oauth2.credentials import Credentials
            from handlers.google_auth import SCOPES
            
            creds = Credentials.from_authorized_user_info(session['google_credentials'], SCOPES)
            
            if creds.refresh_token:
                save_google_tokens_to_env(creds)
                results["services"]["google"] = {
                    "success": True,
                    "message": "Google tokens saved for automation",
                    "refresh_token": creds.refresh_token[:20] + "...",
                    "env_vars": {
                        "GOOGLE_REFRESH_TOKEN": creds.refresh_token,
                        "GOOGLE_CLIENT_ID": creds.client_id,
                        "GOOGLE_CLIENT_SECRET": creds.client_secret
                    }
                }
            else:
                results["services"]["google"] = {
                    "success": False,
                    "message": "No Google refresh token available",
                    "action": "Re-authenticate at /google-login with prompt=consent"
                }
        else:
            results["services"]["google"] = {
                "success": False,
                "message": "No Google credentials in session",
                "action": "Visit /google-login to authenticate"
            }
    except Exception as e:
        results["services"]["google"] = {
            "success": False,
            "error": str(e)
        }
    
    # Summary
    successful_services = sum(1 for service in results["services"].values() if service.get("success", False))
    total_services = len(results["services"])
    
    results["summary"] = {
        "successful": successful_services,
        "total": total_services,
        "all_configured": successful_services == total_services,
        "next_steps": [
            "Copy the environment variables from the logs",
            "Add them to your deployment platform",
            "Restart your application",
            "Verify with /services endpoint"
        ]
    }
    
    return results

@app.route("/test-webhook-auth")
def test_webhook_auth():
    """Test authentication as it would work in webhook context (no session)"""
    # Clear any session data to simulate webhook environment
    original_session = dict(session)
    session.clear()
    
    try:
        results = {
            "timestamp": datetime.now().isoformat(),
            "webhook_simulation": True,
            "tests": {}
        }
        
        # Test Spotify authentication without session
        try:
            token_info = get_token_info()  # This should work with environment refresh token
            if token_info:
                sp = spotipy.Spotify(auth=token_info["access_token"])
                user = sp.current_user()
                results["tests"]["spotify"] = {
                    "success": True,
                    "message": f"Spotify authenticated as {user['display_name']}",
                    "user_id": user["id"]
                }
            else:
                results["tests"]["spotify"] = {
                    "success": False,
                    "message": "No Spotify token available in webhook context"
                }
        except Exception as e:
            results["tests"]["spotify"] = {
                "success": False,
                "error": str(e)
            }
        
        # Test Google authentication without session
        try:
            from handlers.google_auth import load_credentials
            creds = load_credentials()
            if creds and creds.valid:
                results["tests"]["google"] = {
                    "success": True,
                    "message": "Google authenticated successfully",
                    "credential_type": "service_account" if hasattr(creds, 'service_account_email') else "oauth"
                }
            else:
                results["tests"]["google"] = {
                    "success": False,
                    "message": "No valid Google credentials in webhook context"
                }
        except Exception as e:
            results["tests"]["google"] = {
                "success": False,
                "error": str(e)
            }
        
        # Test email sending in webhook context
        try:
            from handlers.gmail import send_email
            result = send_email(
                to="wandilemawela4@gmail.com",
                subject="Webhook Auth Test",
                body="Testing email functionality in webhook context (no session)."
            )
            results["tests"]["email_send"] = {
                "success": not result.startswith("❌"),
                "result": result
            }
        except Exception as e:
            results["tests"]["email_send"] = {
                "success": False,
                "error": str(e)
            }
        
        # Summary
        successful_tests = sum(1 for test in results["tests"].values() if test.get("success", False))
        total_tests = len(results["tests"])
        
        results["summary"] = {
            "webhook_ready": successful_tests == total_tests,
            "successful": successful_tests,
            "total": total_tests,
            "message": "Webhook authentication ready" if successful_tests == total_tests else "Webhook authentication needs setup"
        }
        
        return results
        
    finally:
        # Restore original session
        session.clear()
        session.update(original_session)

@app.route("/quick-setup")
def quick_setup():
    """Quick setup page with all necessary links"""
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
            <h3>🧪 Testing & Debugging</h3>
            <a href="/test-current-email" class="button">Test Email</a>
            <a href="/test-spotify" class="button">Test Spotify</a>
            <a href="/google-debug" class="button">Debug Google</a>
            <a href="/health" class="button">Health Check</a>
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
            <code>
                SPOTIFY_REFRESH_TOKEN=your_token_here<br>
                GOOGLE_REFRESH_TOKEN=your_token_here<br>
                GOOGLE_CLIENT_ID=your_client_id<br>
                GOOGLE_CLIENT_SECRET=your_secret
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