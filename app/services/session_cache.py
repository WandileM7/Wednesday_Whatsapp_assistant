"""
Session Cache Management
"""
from datetime import datetime
from flask import session
import logging

logger = logging.getLogger(__name__)

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

def update_session_location(location):
    """Update location in session cache"""
    session_data = session.get('user_cache', {})
    session_data['location'] = location
    session['user_cache'] = session_data
    return session_data