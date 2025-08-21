"""
Main Application Routes
"""
from flask import Blueprint, jsonify, request
from app.services.session_cache import cache_user_session, get_cached_session
from app.services.conversation import ConversationManager
from app.services.waha_client import WAHAClient

main_bp = Blueprint('main', __name__)
conversation_manager = ConversationManager()
waha_client = WAHAClient()

@main_bp.route("/")
def home():
    """Application status endpoint"""
    return jsonify({
        "status": "online", 
        "services": ["spotify", "gmail", "gemini", "weather", "tasks", "contacts"],
        "version": "2.0.0"
    })

@main_bp.route('/webhook', methods=['POST', 'GET'])
def webhook():
    """WhatsApp webhook endpoint"""
    if request.method == 'GET':
        return jsonify({"status": "online", "webhook": "ready"})

    try:
        data = request.get_json() or {}
        payload = data.get('payload', data)
        
        # Extract message data
        user_msg = payload.get('body') or payload.get('text') or payload.get('message')
        phone = payload.get('chatId') or payload.get('from')
        
        if not user_msg or not phone or payload.get('fromMe'):
            return jsonify({'status': 'ignored'}), 200

        # Cache user session
        cache_user_session(phone)
        
        # Process message
        reply = conversation_manager.process_message(user_msg, phone)
        
        # Send response
        success = waha_client.send_message(phone, reply)
        
        if success:
            return jsonify({'status': 'ok'})
        else:
            return jsonify({'status': 'error', 'message': 'Failed to send message'}), 500
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@main_bp.route('/send', methods=['POST'])
def send_initial_message():
    """Send initial message to a phone number"""
    data = request.json
    phone = data.get('phone')
    message = data.get('message')
    
    if not phone:
        return jsonify({'status': 'error', 'message': 'Phone required'}), 400

    if message:
        success = waha_client.send_message(phone, message)
    else:
        success = conversation_manager.initiate_conversation(phone)

    if success:
        return jsonify({'status': 'success'}), 200
    return jsonify({'status': 'error'}), 500