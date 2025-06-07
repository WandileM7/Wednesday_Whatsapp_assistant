import json
from dotenv import load_dotenv
from fastapi import params
from flask import Flask, redirect, request, jsonify, session
from handlers.gemini import chat_with_functions, execute_function
from handlers.google_auth import auth_bp
import google.generativeai as genai
import sys
import os  # Add this missing import
import requests  # Add this missing import
import logging  # Move this import up
import time
from flask_session import Session
from handlers.spotify_client import make_spotify_oauth

from chromedb import add_to_conversation_history
from datetime import datetime
from werkzeug.middleware.proxy_fix import ProxyFix
from spotipy.oauth2 import SpotifyOAuth  # Add this import
import spotipy  # Add this import

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("whatsapp_assistant.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("WhatsAppAssistant")

load_dotenv()
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config["SESSION_TYPE"] = "filesystem"
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))
Session(app)

app.register_blueprint(auth_bp)       # <--- makes /authorize and /oauth2callback active
# Validate environment
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

user_conversations = {}

# ─── SPOTIFY OAUTH SETUP ────────────────────────────────────────
SPOTIFY_SCOPE = "user-read-playback-state user-modify-playback-state"

def make_spotify_oauth():
    return SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_SECRET"),  # Fixed: was SPOTIFY_CLIENT_SECRET
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
        scope=SPOTIFY_SCOPE,
        cache_path=None
    )

def get_token_info():
    """Get token info from session and refresh if needed"""
    token_info = session.get("token_info", {})
    if not token_info:
        # Try to use refresh token from environment
        refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
        if refresh_token:
            try:
                sp_oauth = make_spotify_oauth()
                # Remove as_dict parameter
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
            # Remove as_dict parameter
            token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
            session["token_info"] = token_info
        except Exception as e:
            logger.error(f"Error refreshing session token: {e}")
            # Clear invalid token
            session.pop("token_info", None)
            return None
    return token_info

def get_spotify_client():
    token_info = get_token_info()
    if not token_info:
        return None
    return spotipy.Spotify(auth=token_info["access_token"])  # Fixed: was Spotify

# ─── SPOTIFY AUTH ROUTES ────────────────────────────────────────
@app.route("/login")
def spotify_login():
    sp_oauth = make_spotify_oauth()
    return redirect(sp_oauth.get_authorize_url())

@app.route("/callback")
def spotify_callback():
    """Handle Spotify OAuth callback"""
    code = request.args.get('code')
    error = request.args.get('error')
    
    if error:
        logger.error(f"Spotify OAuth error: {error}")
        return f"""
        <h2>❌ Authorization Error</h2>
        <p>Error: {error}</p>
        <p>Description: {request.args.get('error_description', 'No description provided')}</p>
        """, 400
    
    if not code:
        return """
        <h2>❌ No Authorization Code</h2>
        <p>No authorization code received from Spotify.</p>
        """, 400
    
    try:
        sp_oauth = make_spotify_oauth()
        # Remove as_dict parameter - not supported in all versions
        token_info = sp_oauth.get_access_token(code)
        session["token_info"] = token_info
        logger.info("Spotify authorization successful")
        return "✅ Spotify authorization successful. You can now use playback endpoints."
    except Exception as e:
        logger.error(f"Error getting Spotify token: {e}")
        return f"<h2>❌ Error getting token:</h2><p>{str(e)}</p>", 500



# --- FUNCTION: Initial conversation starter ---
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
        user_conversations[phone] = datetime.now()
        return jsonify({'status': 'success'}), 200
    return jsonify({'status': 'error'}), 500

# --- FUNCTION: WhatsApp webhook handler ---
@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    if request.method == 'GET':
        return "Webhook is active", 200
    
    logger.info("Webhook received.")
    
    try:
        data = request.get_json()
        if not data:
            return "No data received", 400
        
        # Only process message events
        if data.get("event") != "message":
            return "OK", 200
        
        payload = data.get("payload", {})
        phone = payload.get("from", "")
        message_text = payload.get("body", "").strip()
        
        # Skip empty messages or media-only messages
        if not message_text or payload.get("hasMedia"):
            return "OK", 200
        
        # Skip messages from ourselves
        if payload.get("fromMe"):
            return "OK", 200
        
        logger.info(f"Processing message from {phone}: {message_text[:50]}...")
        
        # Show typing indicator
        typing_indicator(phone, 2)
        
        # Get conversation context
        conversation_context = user_conversations.get(phone, [])
        
        # Add user message to context
        conversation_context.append({"role": "user", "content": message_text})
        user_conversations[phone] = conversation_context[-10:]  # Keep last 10 messages
        
        # Add to ChromaDB for long-term memory
        add_to_conversation_history(phone, message_text, "user")
        
        # Generate response using Gemini with function calling
        response_text = chat_with_functions(message_text, phone)
        
        # Add assistant response to context
        conversation_context.append({"role": "assistant", "content": response_text})
        user_conversations[phone] = conversation_context[-10:]
        
        # Add assistant response to ChromaDB
        add_to_conversation_history(phone, response_text, "assistant")
        
        # Send response
        success = send_message(phone, response_text)
        
        if success:
            logger.info(f"Response sent successfully to {phone}")
        else:
            logger.error(f"Failed to send response to {phone}")
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error processing webhook", 500


@app.route('/chat', methods=['POST'])
def direct_chat():
    data = request.json
    user_msg = data.get('message', '')
    response = model.chat(messages=[
        {'role': 'system', 'content': PERSONALITY_PROMPT},
        {'role': 'user', 'content': user_msg}
    ])
    return jsonify({'response': response.text})

@app.route("/test-waha")
def test_waha():
    url = os.getenv("WAHA_URL", "https://waha-gemini-assistant.onrender.com/api/sendText")
    payload = {
        "session": "default",
        "chatId": "27729224495@c.us",
        "text": "Hello from Flask!"
    }
    try:
        response = requests.post(waha_url, json=payload)
        return f"WAHA responded: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Failed to reach WAHA: {e}"

@app.route("/test-waha-debug")
def test_waha_debug():
    """Debug WAHA connection with detailed logging"""
    waha_url = os.getenv("WAHA_URL")
    session_name = os.getenv("WAHA_SESSION", "default")
    
    # First, check if WAHA is running
    try:
        base_url = waha_url.replace("/api/sendText", "")
        status_response = requests.get(f"{base_url}/api/sessions", timeout=10)
        logger.info(f"WAHA status check: {status_response.status_code}")
        logger.info(f"WAHA sessions: {status_response.text}")
    except Exception as e:
        logger.error(f"Failed to check WAHA status: {e}")
        return f"WAHA status check failed: {e}"
    
    # Test sending a message
    test_payload = {
        "session": session_name,
        "chatId": "27729224495@c.us",  # Your test number
        "text": "Test message from debug endpoint"
    }
    
    try:
        logger.info(f"Testing WAHA with payload: {test_payload}")
        response = requests.post(waha_url, json=test_payload, timeout=10)
        
        return f"""
        <h2>WAHA Debug Results</h2>
        <p><strong>URL:</strong> {waha_url}</p>
        <p><strong>Session:</strong> {session_name}</p>
        <p><strong>Status Code:</strong> {response.status_code}</p>
        <p><strong>Response Headers:</strong> {dict(response.headers)}</p>
        <p><strong>Response Body:</strong> {response.text}</p>
        <p><strong>Payload Sent:</strong> {test_payload}</p>
        """
    except Exception as e:
        return f"WAHA test failed: {e}"

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "status": "online",
        "active_conversations": len(user_conversations),
        "timestamp": datetime.now().isoformat()
    })

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "online"})


# --- UTILITIES ---
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

def send_message_alternative(phone, text):
    """Alternative message sending with different payload format"""
    try:
        phone = phone if "@c.us" in phone else f"{phone}@c.us"
        
        # Try the format that WAHA expects
        payload = {
            "session": os.getenv("WAHA_SESSION", "default"),
            "chatId": phone,
            "text": text
        }
        
        logger.info(f"Trying alternative format for {phone}")
        logger.debug(f"Alternative payload: {payload}")
        
        r = requests.post(os.getenv("WAHA_URL"), json=payload, timeout=10)
        logger.debug(f"Alternative response: {r.status_code} - {r.text}")
        
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Alternative send failed: {e}")
        return False

# Update the main send_message to try both formats
def send_message(phone, text):
    # Try the original format first
    success = send_message_original(phone, text)
    if not success:
        logger.info("Trying alternative message format...")
        success = send_message_alternative(phone, text)
    return success

def send_message_original(phone, text):
    try:
        phone = phone if "@c.us" in phone else f"{phone}@c.us"
        payload = {
            "chatId": phone,
            "text": text,
            "session": os.getenv("WAHA_SESSION", "default"),
            "linkPreview": True
        }
        
        r = requests.post(os.getenv("WAHA_URL"), json=payload, timeout=10)
        r.raise_for_status()
        return True
    except:
        return False

@app.route("/spotify-status")
def spotify_status():
    """Check Spotify authentication status"""
    token_info = get_token_info()
    if token_info:
        try:
            sp = spotipy.Spotify(auth=token_info["access_token"])
            user = sp.current_user()
            return {
                "authenticated": True,
                "user": user["display_name"],
                "user_id": user["id"],
                "token_expires": token_info.get("expires_at"),
                "scopes": token_info.get("scope", "").split()
            }
        except Exception as e:
            return {
                "authenticated": False,
                "error": str(e),
                "login_url": "/login"
            }
    else:
        return {
            "authenticated": False,
            "message": "No valid token found",
            "login_url": "/login"
        }

@app.route("/clear-spotify-tokens")
def clear_spotify_tokens():
    """Clear all Spotify tokens (for debugging)"""
    session.pop("token_info", None)
    return "✅ Spotify tokens cleared. Please visit /login to re-authenticate."

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
        
        # Test basic API call
        user = sp.current_user()
        
        # Test playback state
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
    except spotipy.exceptions.SpotifyException as e:
        return {
            "error": f"Spotify API error: {e}",
            "status_code": e.http_status,
            "login_url": "/login" if e.http_status == 401 else None
        }, e.http_status
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/spotify-quick-check")
def spotify_quick_check():
    """Quick check of Spotify functionality"""
    from handlers.spotify_client import is_authenticated
    from handlers.spotify import get_current_song
    
    if not is_authenticated():
        return {
            "authenticated": False,
            "login_url": "/login"
        }
    
    # Test a simple function
    current_song = get_current_song()
    
    return {
        "authenticated": True,
        "current_song_result": current_song,
        "spotify_working": not current_song.startswith("❌")
    }

if __name__ == '__main__':
    logger.info("Launching WhatsApp Assistant...")
    app.run(host="0.0.0.0", port=5000)
