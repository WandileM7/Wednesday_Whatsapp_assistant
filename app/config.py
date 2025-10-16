"""
Application Configuration
"""
import os
from datetime import timedelta

class Config:
    """Base configuration"""
    # Flask settings
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", os.urandom(24))
    SESSION_TYPE = "filesystem"
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.getenv("FLASK_ENV") == "production"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # Application settings
    MAX_CONVERSATIONS = int(os.getenv("MAX_CONVERSATIONS", "50"))
    MAX_MESSAGES_PER_USER = int(os.getenv("MAX_MESSAGES_PER_USER", "15"))
    
    # WAHA settings
    WAHA_URL = os.getenv("WAHA_URL")
    WAHA_API_KEY = os.getenv("WAHA_API_KEY")
    WAHA_SESSION = os.getenv("WAHA_SESSION", "default")
    WAHA_KEEPALIVE_INTERVAL = int(os.getenv("WAHA_KEEPALIVE_INTERVAL", "600"))
    
    # AI settings
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    PERSONALITY_PROMPT = os.getenv("PERSONALITY_PROMPT", "You are a helpful assistant named Wednesday.")
    GREETING_PROMPT = os.getenv("GREETING_PROMPT", "Give a brief, friendly greeting.")
    INITIAL_MESSAGE_PROMPT = os.getenv("INITIAL_MESSAGE_PROMPT", "Send a friendly message under 50 words.")
    
    # Speech settings
    ENABLE_VOICE_RESPONSES = os.getenv("ENABLE_VOICE_RESPONSES", "true").lower() == "true"
    MAX_VOICE_RESPONSE_LENGTH = int(os.getenv("MAX_VOICE_RESPONSE_LENGTH", "200"))

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}