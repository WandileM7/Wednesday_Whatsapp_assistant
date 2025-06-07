import json
from dotenv import load_dotenv
from fastapi import params
from flask import Flask, request, jsonify
import os
from handlers.google_auth import auth_bp
import requests
import google.generativeai as genai
import sys
import logging
import os  # Add this line
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time
from chromedb import add_to_conversation_history
from datetime import datetime
from werkzeug.middleware.proxy_fix import ProxyFix

from handlers.gemini import chat_with_functions, execute_function, model

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
    logger.info("Webhook received.")

    if request.method == 'GET':
        return jsonify({"status": "online"})

    data = request.get_json() or {}
    payload = data.get('payload', data)
    user_msg = payload.get('body') or payload.get('text') or payload.get('message')
    phone = payload.get('chatId') or payload.get('from')

    if not user_msg or not phone:
        return jsonify({'status': 'ignored'}), 200

    try:
        # Step 1: Ask Gemini for its response (which may be a function call)
        call = chat_with_functions(user_msg, phone)
        logger.debug(f"Gemini function response: {call}")

        # Step 2: Decide whether to execute a function or just take its text
        if call.get("name"):
            # Gemini wants you to call a function
            reply = execute_function(call)
        else:
            # Gemini returned a plain-text answer
            reply = call.get("content", "Sorry, no idea what that was.")

        # Step 3: Save both user→assistant messages into ChromaDB
        try:
            add_to_conversation_history(phone, "user", user_msg)
            add_to_conversation_history(phone, "assistant", reply)
        except Exception as e:
            logger.error(f"ChromaDB save error: {e}")
        # Step 5: Send response back to user
        send_message(phone, reply)
        return jsonify({'status': 'ok'})

    except Exception as e:
        logger.error(f"Error during chat_with_functions: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


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

# Add this new route after your existing routes
@app.route('/callback')
def spotify_callback():
    """Handle Spotify OAuth callback"""
    code = request.args.get('code')
    error = request.args.get('error')
    
    if error:
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
    
    return f"""
    <h2>✅ Authorization Successful!</h2>
    <p><strong>Authorization Code:</strong></p>
    <textarea style="width: 100%; height: 100px; font-family: monospace; margin: 10px 0;">{code}</textarea>
    
    <p><strong>Next Steps:</strong></p>
    <ol>
        <li>Copy the authorization code above</li>
        <li>Go to your local token generator: <code>http://localhost:8888/callback?code=PASTE_CODE_HERE</code></li>
        <li>Get your refresh token from there</li>
        <li>Set it as <code>SPOTIFY_REFRESH_TOKEN</code> in your environment variables</li>
    </ol>
    
    <p><em>This page is just showing you the authorization code. You still need to exchange it for tokens using your local script.</em></p>
    """

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

def send_message(phone, text):
    try:
        phone = phone if "@c.us" in phone else f"{phone}@c.us"
        payload = {
            "chatId": phone,
            "text": text,
            "session": os.getenv("WAHA_SESSION", "default"),
            "linkPreview": True
        }
        r = requests.post(os.getenv("WAHA_URL"), json=payload)
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return False

if __name__ == '__main__':
    logger.info("Launching WhatsApp Assistant...")
    app.run(host="0.0.0.0", port=5000)
