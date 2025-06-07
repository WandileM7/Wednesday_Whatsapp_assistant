import os
import json
import logging
from flask import Blueprint, redirect, request, session, url_for
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)

# Google OAuth scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/calendar'
]

def get_credentials_path():
    """Get the path to credentials file, checking multiple locations"""
    # First check GOOGLE_APPLICATION_CREDENTIALS environment variable
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path:
        logger.info(f"Found GOOGLE_APPLICATION_CREDENTIALS: {env_path}")
        if os.path.exists(env_path):
            logger.info(f"Credentials file exists at: {env_path}")
            return env_path
        else:
            logger.warning(f"GOOGLE_APPLICATION_CREDENTIALS points to non-existent file: {env_path}")
    
    # Fallback to other locations
    possible_paths = [
        "./credentials.json",
        "./handlers/credentials.json",
        "/etc/secrets/credentials.json"
    ]
    
    for path in possible_paths:
        if path and os.path.exists(path):
            logger.info(f"Found credentials file at fallback location: {path}")
            return path
    
    logger.error("No credentials file found in any location")
    return None

def validate_credentials_file(path):
    """Validate that the credentials file has the correct format"""
    try:
        logger.info(f"Validating credentials file: {path}")
        with open(path, 'r') as f:
            creds_data = json.load(f)
        
        logger.debug(f"Credentials file keys: {list(creds_data.keys())}")
        
        # Check if it's a valid OAuth client credentials file
        if 'installed' in creds_data:
            logger.info("Found OAuth client credentials (installed app)")
            return True, "oauth_client"
        elif 'web' in creds_data:
            logger.info("Found OAuth client credentials (web app)")
            return True, "oauth_client"
        elif 'type' in creds_data and creds_data['type'] == 'service_account':
            logger.info("Found service account credentials")
            return True, "service_account"
        else:
            error_msg = f"Invalid format. Found keys: {list(creds_data.keys())}"
            logger.error(error_msg)
            return False, error_msg
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON format: {e}"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Error reading file: {e}"
        logger.error(error_msg)
        return False, error_msg

def load_credentials():
    """Load and return valid Google credentials"""
    logger.info("Loading Google credentials...")
    
    # First try to load from session
    if 'google_credentials' in session:
        logger.info("Found credentials in session, validating...")
        try:
            creds = Credentials.from_authorized_user_info(session['google_credentials'], SCOPES)
            if creds and creds.valid:
                logger.info("Session credentials are valid")
                return creds
            elif creds and creds.expired and creds.refresh_token:
                logger.info("Session credentials expired, attempting refresh...")
                creds.refresh(Request())
                session['google_credentials'] = {
                    'token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'token_uri': creds.token_uri,
                    'client_id': creds.client_id,
                    'client_secret': creds.client_secret,
                    'scopes': creds.scopes
                }
                logger.info("Credentials refreshed successfully")
                return creds
        except RefreshError as e:
            logger.warning(f"Failed to refresh credentials: {e}")
            # Clear invalid credentials
            session.pop('google_credentials', None)
        except Exception as e:
            logger.error(f"Error loading session credentials: {e}")
            session.pop('google_credentials', None)
    
    # Try to load from file
    logger.info("Loading credentials from file...")
    creds_path = get_credentials_path()
    if not creds_path:
        error_msg = "No Google credentials file found. Please set GOOGLE_APPLICATION_CREDENTIALS or add credentials.json"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    is_valid, result = validate_credentials_file(creds_path)
    if not is_valid:
        error_msg = f"Invalid credentials file: {result}"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    if result == "service_account":
        logger.info("Loading service account credentials...")
        # Handle service account credentials
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            creds_path, scopes=SCOPES)
        logger.info("Service account credentials loaded successfully")
        return creds
    else:
        # Handle OAuth client credentials - need to go through auth flow
        logger.info("OAuth client credentials found, auth flow required")
        return None

@auth_bp.route('/authorize')
def authorize():
    """Start the OAuth flow"""
    logger.info("Starting OAuth authorization flow...")
    creds_path = get_credentials_path()
    if not creds_path:
        error_msg = "Error: No credentials.json file found"
        logger.error(error_msg)
        return error_msg, 500
    
    is_valid, result = validate_credentials_file(creds_path)
    if not is_valid:
        error_msg = f"Error: {result}"
        logger.error(error_msg)
        return error_msg, 500
    
    try:
        flow = Flow.from_client_secrets_file(
            creds_path,
            scopes=SCOPES,
            redirect_uri=url_for('auth.oauth2callback', _external=True)
        )
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        
        session['state'] = state
        logger.info("Redirecting to Google OAuth...")
        return redirect(authorization_url)
    except Exception as e:
        error_msg = f"Error starting OAuth flow: {e}"
        logger.error(error_msg)
        return error_msg, 500

@auth_bp.route('/oauth2callback')
def oauth2callback():
    """Handle the OAuth callback"""
    logger.info("Handling OAuth callback...")
    try:
        creds_path = get_credentials_path()
        flow = Flow.from_client_secrets_file(
            creds_path,
            scopes=SCOPES,
            state=session['state'],
            redirect_uri=url_for('auth.oauth2callback', _external=True)
        )
        
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        
        # Store credentials in session
        session['google_credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        logger.info("OAuth flow completed successfully")
        return "✅ Google authorization successful! You can now use Gmail and Calendar features."
    except Exception as e:
        error_msg = f"Error in OAuth callback: {e}"
        logger.error(error_msg)
        return error_msg, 500

@auth_bp.route('/auth-status')
def auth_status():
    """Check authentication status"""
    try:
        creds = load_credentials()
        if creds:
            return {
                "authenticated": True,
                "scopes": creds.scopes if hasattr(creds, 'scopes') else SCOPES,
                "credentials_path": get_credentials_path()
            }
        else:
            return {
                "authenticated": False,
                "auth_url": url_for('auth.authorize', _external=True),
                "credentials_path": get_credentials_path()
            }
    except Exception as e:
        logger.error(f"Error checking auth status: {e}")
        return {
            "error": str(e),
            "credentials_path": get_credentials_path(),
            "env_var": os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        }, 500

@auth_bp.route('/debug-credentials')
def debug_credentials():
    """Debug endpoint to check credential file status"""
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    creds_path = get_credentials_path()
    
    debug_info = {
        "GOOGLE_APPLICATION_CREDENTIALS": env_path,
        "env_file_exists": bool(env_path and os.path.exists(env_path)),
        "found_credentials_path": creds_path,
        "file_exists": bool(creds_path and os.path.exists(creds_path))
    }
    
    if creds_path:
        try:
            is_valid, result = validate_credentials_file(creds_path)
            debug_info["file_valid"] = is_valid
            debug_info["file_type"] = result
            
            # Read first few characters to check if it's readable
            with open(creds_path, 'r') as f:
                first_chars = f.read(100)
                debug_info["file_readable"] = True
                debug_info["starts_with"] = first_chars[:50] + "..." if len(first_chars) > 50 else first_chars
        except Exception as e:
            debug_info["file_error"] = str(e)
    
    return debug_info

