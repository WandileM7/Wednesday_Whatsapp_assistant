"""
WhatsApp Assistant Application Factory
"""
import os
import logging
from flask import Flask
from flask_session import Session
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

from .config import Config
from .extensions import init_extensions
from .routes import register_blueprints
from .services import initialize_services

def create_app(config_class=Config):
    """Create and configure Flask application"""
    load_dotenv()
    
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
    # Initialize extensions
    init_extensions(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Initialize services
    with app.app_context():
        initialize_services()
    
    return app