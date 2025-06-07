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
app.config["SESSION_TYPE"] = "null"  # In-memory sessions
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))

# Only initialize Session if needed
if os.getenv("ENABLE_SESSIONS", "false").lower() == "true":
    Session(app)


app.register_blueprint(auth_bp)       # <--- makes /authorize and /oauth2callback active
# Validate environment

user_conversations = {}
MAX_CONVERSATIONS = 50  # Limit stored conversations
MAX_MESSAGES_PER_USER = 15
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
def cleanup_conversations():
    """Clean up old conversations to manage memory"""
    if len(user_conversations) > MAX_CONVERSATIONS:
        # Remove oldest conversations
        sorted_convos = sorted(
            user_conversations.items(),
            key=lambda x: x[1].get('last_activity', 0)
        )
        
        # Keep only the most recent conversations
        for phone, _ in sorted_convos[:-MAX_CONVERSATIONS//2]:
            del user_conversations[phone]
        
        logger.info(f"Cleaned up conversations, now have {len(user_conversations)}")
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
        return jsonify({"status": "online", "memory_optimized": True})

    try:
        data = request.get_json() or {}
        payload = data.get('payload', data)
        user_msg = payload.get('body') or payload.get('text') or payload.get('message')
        phone = payload.get('chatId') or payload.get('from')

        if not user_msg or not phone:
            return jsonify({'status': 'ignored'}), 200

        # Skip messages from self
        if payload.get('fromMe'):
            return jsonify({'status': 'ignored'}), 200

        logger.info(f"Processing message from {phone}: {user_msg[:30]}...")
        if phone not in user_conversations:
            user_conversations[phone] = {
                'messages': [],
                'last_activity': time.time()
            }
        
        # Limit messages per conversation
        conversation = user_conversations[phone]
        conversation['messages'].append({
            'role': 'user',
            'content': user_msg,
            'timestamp': time.time()
        })
        
        # Keep only recent messages
        conversation['messages'] = conversation['messages'][-MAX_MESSAGES_PER_USER:]
        conversation['last_activity'] = time.time()

        # Clean up conversations periodically
        if len(user_conversations) % 10 == 0:
            cleanup_conversations()
        call = chat_with_functions(user_msg, phone)
        logger.debug(f"Gemini function response: {call}")

        # Step 2: Decide whether to execute a function or just take its text
        if call.get("name"):
            # Gemini wants you to call a function
            reply = execute_function(call)
        else:
            # Gemini returned a plain-text answer
            reply = call.get("content", "Sorry, no idea what that was.")

        # Step 3: Save to ChromaDB only if available and enabled
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

        # Step 4: Send response back to user
        send_message(phone, reply)
        return jsonify({'status': 'ok', 'memory_optimized': True})

    except Exception as e:
        logger.error(f"Error during chat processing: {e}")
        return jsonify({'status': 'error', 'message': 'Processing failed'}), 500






@app.route('/chat', methods=['POST'])
def direct_chat():
    data = request.json
    user_msg = data.get('message', '')
    response = model.chat(messages=[
        {'role': 'system', 'content': PERSONALITY_PROMPT},
        {'role': 'user', 'content': user_msg}
    ])
    return jsonify({'response': response.text})


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "status": "online",
        "active_conversations": len(user_conversations),
        "timestamp": datetime.now().isoformat()
    })
    
@app.route("/health")
def health():
    """Health check with memory information"""
    import psutil
    import gc
    
    # Force garbage collection
    gc.collect()
    
    # Get memory usage
    process = psutil.Process()
    memory_info = process.memory_info()
    
    return jsonify({
        "status": "healthy",
        "memory_mb": round(memory_info.rss / 1024 / 1024, 2),
        "active_conversations": len(user_conversations),
        "chromadb_enabled": CHROMADB_AVAILABLE and os.getenv("ENABLE_CHROMADB", "false").lower() == "true",
        "timestamp": datetime.now().isoformat()
    })
    
@app.route("/memory-cleanup")
def memory_cleanup():
    """Manual memory cleanup endpoint"""
    import gc
    
    # Clear old conversations
    cleanup_conversations()
    
    # Force garbage collection
    collected = gc.collect()
    
    return jsonify({
        "status": "cleanup_completed",
        "objects_collected": collected,
        "active_conversations": len(user_conversations)
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
    
if __name__ == '__main__':
    logger.info("Launching WhatsApp Assistant...")
    app.run(host="0.0.0.0", port=5000, threaded=True, debug=True)
