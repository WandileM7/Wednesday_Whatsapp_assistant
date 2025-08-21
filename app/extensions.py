"""
Flask Extensions Initialization
"""
import logging
from flask_session import Session

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger("WhatsAppAssistant")

# Initialize session
session = Session()

def init_extensions(app):
    """Initialize Flask extensions"""
    session.init_app(app)
    
    # Log successful initialization
    logger.info("Flask extensions initialized")