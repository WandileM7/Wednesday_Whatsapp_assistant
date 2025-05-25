import random
from pprint import pprint
from time import sleep
import logging
import os
from datetime import datetime

import requests
from flask import Flask, request, jsonify

# Set up logging at the top of your file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("whatsapp_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("WhatsAppBot")

app = Flask(__name__)


def send_message(chat_id, text):
    """
    Send message to chat_id.
    :param chat_id: Phone number + "@c.us" suffix - 1231231231@c.us
    :param text: Message for the recipient
    """
    logger.info(f"FUNCTION START: send_message to {chat_id}")
    
    # Ensure phone number format is valid for WhatsApp
    if "@c.us" not in chat_id and "@g.us" not in chat_id:
        chat_id = f"{chat_id}@c.us"
        logger.info(f"Reformatted chat_id to: {chat_id}")
    
    try:
        # Send a text back via WhatsApp HTTP API
        logger.info(f"Sending message: '{text[:50]}...' to {chat_id}")
        response = requests.post(
            "http://localhost:3000/api/sendText",
            json={
                "chatId": chat_id,
                "text": text,
                "session": "default",
            },
        )
        response.raise_for_status()
        logger.info(f"Message sent successfully. Status code: {response.status_code}")
        logger.debug(f"Full response: {response.text}")
        return True
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return False
    finally:
        logger.info("FUNCTION END: send_message")

def reply(chat_id, message_id, text):
    response = requests.post(
        "http://localhost:3000/api/reply",
        json={
            "chatId": chat_id,
            "text": text,
            "reply_to": message_id,
            "session": "default",
        },
    )
    response.raise_for_status()


def send_seen(chat_id, message_id, participant):
    response = requests.post(
        "http://localhost:3000/api/sendSeen",
        json={
            "session": "default",
            "chatId": chat_id,
            "messageId": message_id,
            "participant": participant,
        },
    )
    response.raise_for_status()

def start_typing(chat_id):
    response = requests.post(
        "http://localhost:3000/api/startTyping",
        json={
            "session": "default",
            "chatId": chat_id,
        },
    )
    response.raise_for_status()

def stop_typing(chat_id):
    response = requests.post(
        "http://localhost:3000/api/stopTyping",
        json={
            "session": "default",
            "chatId": chat_id,
        },
    )
    response.raise_for_status()

def typing(chat_id, seconds):
    start_typing(chat_id=chat_id)
    sleep(seconds)
    stop_typing(chat_id=chat_id)

@app.route("/")
def whatsapp_echo():
    return "WhatsApp Echo Bot is ready!"


@app.route("/bot", methods=["GET", "POST"])
def whatsapp_webhook():
    if request.method == "GET":
        logger.info("GET request received at /bot endpoint")
        return jsonify({"status": "online", "version": "1.0.0"})

    logger.info("POST request received at /bot endpoint")
    data = request.get_json()
    logger.info(f"Received webhook data: {data}")
    
    if data["event"] != "message":
        logger.info(f"Ignoring non-message event: {data['event']}")
        return f"Unknown event {data['event']}"

    # Extract message details
    payload = data["payload"]
    text = payload.get("body", "")
    chat_id = payload.get("from", "")
    message_id = payload.get("id", "")
    participant = payload.get("participant")
    
    logger.info(f"Processing message: {text[:50]}... from {chat_id}")
    
    if not text or not chat_id:
        logger.warning("Missing text or chat_id in message payload")
        return "OK"

    # Process message flow
    steps_completed = []
    
    try:
        # Step 1: Mark message as seen
        logger.info("Step 1: Marking message as seen")
        send_seen(chat_id=chat_id, message_id=message_id, participant=participant)
        steps_completed.append("seen")
        
        # Step 2: Show typing and send direct message
        logger.info("Step 2: Showing typing indicator and sending message")
        typing_time = random.random() * 3
        typing(chat_id=chat_id, seconds=typing_time)
        if send_message(chat_id=chat_id, text=text):
            steps_completed.append("send_message")
        
        # Step 3: Show typing and send reply to the message
        logger.info("Step 3: Showing typing indicator and sending reply")
        typing_time = random.random() * 3
        typing(chat_id=chat_id, seconds=typing_time)
        reply(chat_id=chat_id, message_id=message_id, text=text)
        steps_completed.append("reply")
        
        logger.info(f"All steps completed successfully: {', '.join(steps_completed)}")
        return "OK"
    except Exception as e:
        logger.error(f"Error in webhook processing: {e}")
        logger.error(f"Completed steps before error: {', '.join(steps_completed)}")
        return "Error", 500
      
@app.route("/api/server/stop", methods=["OPTIONS", "GET"])
def fake_server_stop():
    return jsonify({"status": "ok", "message": "server stop route exists"})

@app.route("/status", methods=["GET"])
def status_check():
    """Endpoint to check if the bot is running properly"""
    status = {
        "bot_running": True,
        "waha_connection": check_waha_connection(),
        "timestamp": datetime.now().isoformat(),
        "uptime": get_uptime()
    }
    return jsonify(status)

def check_waha_connection():
    """Check if the WAHA server is accessible"""
    try:
        response = requests.get("http://localhost:3000/api/status", timeout=5)
        return response.status_code == 200
    except:
        return False

def get_uptime():
    """Get system uptime"""
    return os.popen("uptime -p").read().strip()
  
  
if __name__ == '__main__':
    # Test send_message function directly before starting the server
    # The format should be: countrycode+phonenumber@c.us (without +)
    test_chat_id = "27729224495@c.us"  # South African number format
    
    # Alternative format (for testing different formats)
    # test_chat_id = "27729224495"  # Function will add @c.us if missing
    
    test_message = "This is a test message from the WhatsApp Echo Bot"
    
    print("Testing send_message function:")
    try:
        success = send_message(test_chat_id, test_message)
        if success:
            print("Test completed successfully")
        else:
            print("Test completed but message sending failed")
    except Exception as e:
        print(f"Test failed with exception: {e}")
    
    # Continue with normal server startup
    print("Starting Flask server...")
    app.run(host="0.0.0.0", port=5000)