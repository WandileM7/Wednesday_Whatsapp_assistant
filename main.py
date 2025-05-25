from dotenv import load_dotenv
from flask import Flask, request, jsonify
import os
import requests
import google.generativeai as genai
import sys
import logging
import time
from datetime import datetime

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

# Check for required environment variables
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    logger.error("GEMINI_API_KEY environment variable is not set")
    logger.error("Please set this environment variable before running the application")
    sys.exit(1)

# Initialize Gemini client
try:
    # Fix the initialization method - use configure instead of Client
    genai.configure(api_key=gemini_api_key)
    # Test the connection by creating a model
    model = genai.GenerativeModel('gemini-2.0-flash')
    logger.info("Successfully initialized Gemini client")
except Exception as e:
    logger.error(f"ERROR initializing Gemini client: {e}")
    sys.exit(1)

# Load personality prompt
PERSONALITY_PROMPT = os.getenv("PERSONALITY_PROMPT", "You are a sarcastic and sassy assistant.")
GREETING_PROMPT = os.getenv("GREETING_PROMPT", "Generate a brief, sarcastic greeting to start a conversation with someone who just messaged you. Keep it under 50 words.")
INITIAL_MESSAGE_PROMPT = os.getenv("INITIAL_MESSAGE_PROMPT", "Generate a brief, intriguing initial message to send to someone to start a conversation. Make it mysterious and engaging, so they'll want to respond. Keep it under 50 words.")

# Check other required environment variables
waha_url = os.getenv("WAHA_URL")
if not waha_url:
    logger.warning("WAHA_URL environment variable is not set")

# Track conversations with users
user_conversations = {}

def initiate_conversation(phone):
    """
    Proactively start a conversation with a user by sending the first message
    """
    logger.info(f"----------------------------------------")
    logger.info(f"INITIATING NEW CONVERSATION with {phone}")
    
    try:
        # Generate initial message using Gemini
        initial_prompt = f"{PERSONALITY_PROMPT}\n{INITIAL_MESSAGE_PROMPT}"
        logger.info(f"Calling Gemini for initial message with prompt: {initial_prompt[:100]}...")
        
        model = genai.GenerativeModel('gemini-2.0-flash')
        initial_response = model.generate_content(contents=initial_prompt)
        initial_message = initial_response.text.strip()
        logger.info(f"INITIAL MESSAGE GENERATED: {initial_message}")
        
        # Show typing indicator before sending message
        typing_indicator(phone, 3)
        
        # Send the message
        message_sent = send_message(phone, initial_message)
        if message_sent:
            logger.info(f"✓ INITIAL MESSAGE SENT to {phone}")
            # Record that we've initiated conversation with this user
            user_conversations[phone] = datetime.now()
            return True
        else:
            logger.error(f"✗ FAILED to send initial message to {phone}")
            return False
            
    except Exception as e:
        logger.error(f"Error initiating conversation: {e}")
        return False

@app.route('/send', methods=['POST'])
def send_initial_message():
    """Endpoint to trigger sending an initial message to a phone number"""
    data = request.json
    
    if not data or 'phone' not in data:
        return jsonify({'status': 'error', 'message': 'Phone number required'}), 400
    
    phone = data['phone']
    custom_message = data.get('message', None)
    
    # If custom message is provided, send it directly
    if custom_message:
        success = send_message(phone, custom_message)
        if success:
            user_conversations[phone] = datetime.now()
            return jsonify({'status': 'success', 'message': 'Custom message sent'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Failed to send custom message'}), 500
    
    # Otherwise generate and send an initial message
    success = initiate_conversation(phone)
    if success:
        return jsonify({'status': 'success', 'message': 'Initial message sent'}), 200
    else:
        return jsonify({'status': 'error', 'message': 'Failed to send initial message'}), 500

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    logger.info("----------------------------------------")
    logger.info("Received webhook request - CONVERSATION START")
    if request.method == 'GET':
        return jsonify({"status": "online", "message": "Webhook is ready!"})

    data = request.get_json()
    logger.debug(f"Webhook payload: {data}")
    
    user_msg = data.get('message', '')
    phone = data.get('from')

    if not user_msg or not phone:
        logger.warning("Missing message or phone number in webhook data")
        return jsonify({'status': 'ignored'}), 200

    logger.info(f"Processing message from {phone}: {user_msg[:50]}...")
    
    # Check if this is the first message from this user
    is_first_message = phone not in user_conversations or (datetime.now() - user_conversations.get(phone, datetime.min)).total_seconds() > 3600
    
    if is_first_message:
        logger.info(f"FIRST INTERACTION with {phone} - Initiating conversation with greeting")
        
        # STEP 1: Generate greeting from Gemini FIRST
        try:
            # Generate greeting before doing anything else
            greeting_prompt = f"{PERSONALITY_PROMPT}\n{GREETING_PROMPT}"
            logger.info(f"Calling Gemini for greeting with prompt: {greeting_prompt[:100]}...")
            
            greeting_response = genai.GenerativeModel('gemini-2.0-flash').generate_content(
                model="gemini-2.0-flash",
                contents=greeting_prompt
            )
            greeting = greeting_response.text.strip()
            logger.info(f"GREETING GENERATED: {greeting}")
            
            # Show typing indicator before sending greeting
            typing_indicator(phone, 2)
            
            # Send the greeting as the first message
            greeting_sent = send_message(phone, greeting)
            if greeting_sent:
                logger.info(f"✓ GREETING SENT to {phone}")
            else:
                logger.error(f"✗ FAILED to send greeting to {phone}")
                
            # Record that we've initiated conversation with this user
            user_conversations[phone] = datetime.now()
            
            # Add a pause between greeting and response
            time.sleep(2)
        except Exception as e:
            logger.error(f"Error generating greeting: {e}")
            greeting = "Well, hello there. What do you want?"
            send_message(phone, greeting)
            logger.info(f"Sent fallback greeting to {phone}")
    else:
        logger.info(f"Continuing existing conversation with {phone}")
    
    # STEP 2: Now respond to the actual message
    logger.info(f"Generating response to: {user_msg}")
    try:
        response_prompt = f"{PERSONALITY_PROMPT}\nUser: {user_msg}\nAssistant:"
        logger.info(f"Calling Gemini for response with prompt: {response_prompt[:100]}...")
        
        # Show typing indicator for natural feel
        typing_indicator(phone, 3)
        
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(contents=response_prompt)
        reply = response.text.strip()
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        reply = "Sorry, I'm having trouble thinking of a sarcastic response right now. Try again later."
    
    # STEP 3: Send the response
    success = send_message(phone, reply)
    if success:
        logger.info(f"✓ RESPONSE SENT to {phone}")
    else:
        logger.error(f"✗ FAILED to send response to {phone}")
    
    # Update conversation timestamp
    user_conversations[phone] = datetime.now()
    logger.info("CONVERSATION COMPLETE ----------------------------------------")
    
    return jsonify({'status': 'ok'})

def typing_indicator(phone, seconds=2):
    """Show typing indicator to make conversation feel more natural"""
    try:
        # Format phone number if needed
        if "@c.us" not in phone and "@g.us" not in phone:
            phone = f"{phone}@c.us"
            
        # Start typing
        start_typing_payload = {
            "chatId": phone,
            "session": os.getenv("WAHA_SESSION", "default")
        }
        requests.post(f"{os.getenv('WAHA_URL').replace('sendText', 'startTyping')}", 
                      json=start_typing_payload, 
                      headers={"Content-Type": "application/json"})
        
        # Wait for specified time
        time.sleep(seconds)
        
        # Stop typing
        stop_typing_payload = {
            "chatId": phone,
            "session": os.getenv("WAHA_SESSION", "default")
        }
        requests.post(f"{os.getenv('WAHA_URL').replace('sendText', 'stopTyping')}", 
                     json=stop_typing_payload, 
                     headers={"Content-Type": "application/json"})
        
        logger.debug(f"Typing indicator shown for {seconds} seconds")
        return True
    except Exception as e:
        logger.error(f"Error showing typing indicator: {e}")
        return False

def send_message(phone, text):
    logger.info(f"Sending message to {phone}: {text[:50]}...")
    
    # Ensure phone number format is valid for WhatsApp
    if "@c.us" not in phone and "@g.us" not in phone:
        phone = f"{phone}@c.us"
        logger.debug(f"Reformatted phone to: {phone}")
    
    payload = {
        "chatId": phone,
        "text": text,
        "session": os.getenv("WAHA_SESSION", "default"),
        "linkPreview": True,
        "linkPreviewHighQuality": False
    }
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(os.getenv("WAHA_URL"), json=payload, headers=headers)
        response.raise_for_status()
        logger.info(f"Message sent successfully. Status code: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return False
    
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "online"})


@app.route('/status', methods=['GET'])
def status():
    """Simple endpoint to check if service is running"""
    return jsonify({
        'status': 'online',
        'active_conversations': len(user_conversations),
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    logger.info("Starting WhatsApp Assistant")
    app.run(host='0.0.0.0', port=5000)
