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

# Updated Google OAuth scopes - include all the scopes that are being requested
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/contacts.readonly',
    'https://www.googleapis.com/auth/cloud-platform',  # Cloud Speech & TTS
    'openid'
]

# Global variable to store credentials for automation
_cached_credentials = None

def initialize_google_auto_auth():
    """Initialize automatic Google authentication on startup"""
    global _cached_credentials
    
    try:
        # Try to load from environment variables first
        creds = load_tokens_from_env()
        if creds and creds.valid:
            _cached_credentials = creds
            logger.info("✅ Google authentication ready (auto-loaded from environment)")
            return True
        
        logger.info("❌ Google auto-authentication not available - manual setup required")
        return False
        
    except Exception as e:
        logger.error(f"Google auto-auth initialization failed: {e}")
        return False

def load_tokens_from_env():
    """Load Google tokens from environment variables with persistent storage fallback"""
    try:
        # First try environment variables
        refresh_token = os.getenv('GOOGLE_REFRESH_TOKEN')
        if refresh_token:
            creds_info = {
                'refresh_token': refresh_token,
                'token': os.getenv('GOOGLE_ACCESS_TOKEN'),
                'client_id': os.getenv('GOOGLE_CLIENT_ID'),
                'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
                'token_uri': 'https://oauth2.googleapis.com/token',
                'scopes': SCOPES
            }
            
            # Validate that we have the minimum required info
            if all([creds_info['client_id'], creds_info['client_secret']]):
                creds = Credentials.from_authorized_user_info(creds_info, SCOPES)
                
                # Refresh if needed
                if creds.expired and creds.refresh_token:
                    logger.info("Refreshing Google credentials from environment...")
                    try:
                        creds.refresh(Request())
                        os.environ['GOOGLE_ACCESS_TOKEN'] = creds.token
                        logger.info("Google credentials refreshed successfully")
                    except RefreshError as e:
                        logger.error(f"Failed to refresh Google credentials from environment: {e}")
                        return None
                    
                return creds
            else:
                logger.warning("Missing client_id or client_secret in environment variables")
        
        # Fallback to persistent storage
        try:
            from helpers.token_storage import token_storage
            stored_tokens = token_storage.load_google_tokens()
            
            if stored_tokens and stored_tokens.get('refresh_token'):
                logger.info("Trying stored Google tokens...")
                creds_info = {
                    'refresh_token': stored_tokens['refresh_token'],
                    'token': stored_tokens.get('access_token'),
                    'client_id': stored_tokens.get('client_id'),
                    'client_secret': stored_tokens.get('client_secret'),
                    'token_uri': 'https://oauth2.googleapis.com/token',
                    'scopes': SCOPES
                }
                
                if all([creds_info['client_id'], creds_info['client_secret']]):
                    creds = Credentials.from_authorized_user_info(creds_info, SCOPES)
                    
                    # Refresh if needed
                    if creds.expired and creds.refresh_token:
                        logger.info("Refreshing Google credentials from storage...")
                        creds.refresh(Request())
                        # Update storage with new token
                        token_storage.save_google_tokens(
                            refresh_token=creds.refresh_token,
                            access_token=creds.token,
                            client_id=creds.client_id,
                            client_secret=creds.client_secret
                        )
                        logger.info("Google credentials refreshed and updated in storage")
                        
                    return creds
                else:
                    logger.warning("Missing client_id or client_secret in stored tokens")
            else:
                logger.debug("No stored Google tokens available")
        except Exception as e:
            logger.warning(f"Failed to load from storage: {e}")
        
        logger.debug("No valid Google tokens found in environment or storage")
        return None
        
    except Exception as e:
        logger.error(f"Failed to load Google tokens: {e}")
        return None

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
        
        # Check if file is readable and not empty
        if not os.path.exists(path):
            return False, "File does not exist"
        
        if os.path.getsize(path) == 0:
            return False, "File is empty"
        
        with open(path, 'r') as f:
            content = f.read().strip()
            if not content:
                return False, "File contains no content"
            
            try:
                creds_data = json.loads(content)
            except json.JSONDecodeError as e:
                return False, f"Invalid JSON: {e}"
        
        logger.debug(f"Credentials file keys: {list(creds_data.keys())}")
        
        # Check if it's a valid OAuth client credentials file
        if 'installed' in creds_data:
            logger.info("Found OAuth client credentials (installed app)")
            required_keys = ['client_id', 'client_secret', 'auth_uri', 'token_uri']
            missing_keys = [key for key in required_keys if key not in creds_data['installed']]
            if missing_keys:
                return False, f"Missing required keys in 'installed': {missing_keys}"
            return True, "oauth_client"
        elif 'web' in creds_data:
            logger.info("Found OAuth client credentials (web app)")
            required_keys = ['client_id', 'client_secret', 'auth_uri', 'token_uri']
            missing_keys = [key for key in required_keys if key not in creds_data['web']]
            if missing_keys:
                return False, f"Missing required keys in 'web': {missing_keys}"
            return True, "oauth_client"
        elif 'type' in creds_data and creds_data['type'] == 'service_account':
            logger.info("Found service account credentials")
            required_keys = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
            missing_keys = [key for key in required_keys if key not in creds_data]
            if missing_keys:
                return False, f"Missing required keys for service account: {missing_keys}"
            return True, "service_account"
        else:
            error_msg = f"Invalid format. Found keys: {list(creds_data.keys())}. Expected 'installed', 'web', or 'type': 'service_account'"
            logger.error(error_msg)
            return False, error_msg
            
    except Exception as e:
        error_msg = f"Error reading file: {e}"
        logger.error(error_msg)
        return False, error_msg

def load_credentials():
    """Enhanced load_credentials with auto-auth support and proper OAuth handling"""
    global _cached_credentials
    
    logger.info("Loading Google credentials...")
    
    # First try cached credentials from auto-auth
    if _cached_credentials and _cached_credentials.valid:
        logger.info("Using cached auto-auth credentials")
        return _cached_credentials
    
    # Try to refresh cached credentials if expired
    if _cached_credentials and _cached_credentials.expired and _cached_credentials.refresh_token:
        try:
            logger.info("Refreshing cached credentials...")
            _cached_credentials.refresh(Request())
            logger.info("Cached credentials refreshed successfully")
            return _cached_credentials
        except RefreshError as e:
            logger.warning(f"Failed to refresh cached credentials: {e}")
            _cached_credentials = None
    
    # Try to load from environment variables
    env_creds = load_tokens_from_env()
    if env_creds and env_creds.valid:
        _cached_credentials = env_creds
        return env_creds
    
    # Fall back to session-based OAuth
    if 'google_credentials' in session:
        logger.info("Found credentials in session, validating...")
        try:
            creds = Credentials.from_authorized_user_info(session['google_credentials'], SCOPES)
            if creds and creds.valid:
                logger.info("Session credentials are valid")
                return creds
            elif creds and creds.expired and creds.refresh_token:
                logger.info("Session credentials expired, attempting refresh...")
                try:
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
                    session.pop('google_credentials', None)
        except Exception as e:
            logger.error(f"Error loading session credentials: {e}")
            session.pop('google_credentials', None)
    
    # Try to load from file (service account only)
    logger.info("Loading credentials from file...")
    creds_path = get_credentials_path()
    if not creds_path:
        logger.error("No Google credentials file found. Please set GOOGLE_APPLICATION_CREDENTIALS or add credentials.json")
        return None
    
    is_valid, result = validate_credentials_file(creds_path)
    if not is_valid:
        logger.error(f"Invalid credentials file at {creds_path}: {result}")
        return None
    
    if result == "service_account":
        logger.info("Loading service account credentials...")
        try:
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(
                creds_path, scopes=SCOPES)
            _cached_credentials = creds  # Cache for future use
            logger.info("Service account credentials loaded successfully")
            return creds
        except Exception as e:
            logger.error(f"Failed to load service account credentials: {e}")
            return None
    else:
        # Handle OAuth client credentials - need to go through auth flow
        logger.info("OAuth client credentials found, auth flow required")
        return None

@auth_bp.route('/authorize')
def authorize():
    """Start the OAuth flow with consistent scopes"""
    logger.info("Starting OAuth authorization flow...")
    creds_path = get_credentials_path()
    if not creds_path:
        error_msg = "Error: No credentials.json file found. Please check your GOOGLE_APPLICATION_CREDENTIALS environment variable or place credentials.json in the project directory."
        logger.error(error_msg)
        return error_msg, 500
    
    is_valid, result = validate_credentials_file(creds_path)
    if not is_valid:
        error_msg = f"Error: Invalid credentials file - {result}"
        logger.error(error_msg)
        return error_msg, 500
    
    if result == "service_account":
        return "Service account credentials detected. OAuth flow not needed.", 200
    
    try:
        # Clear any existing credentials to force fresh auth
        session.pop('google_credentials', None)
        session.pop('state', None)
        
        flow = Flow.from_client_secrets_file(
            creds_path,
            scopes=SCOPES,  # Use the updated SCOPES list
            redirect_uri=url_for('auth.oauth2callback', _external=True)
        )
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'  # Force consent screen to ensure fresh tokens
        )
        
        session['state'] = state
        session['oauth_scopes'] = SCOPES  # Store the scopes we're requesting
        logger.info(f"Redirecting to Google OAuth with scopes: {SCOPES}")
        return redirect(authorization_url)
    except Exception as e:
        error_msg = f"Error starting OAuth flow: {e}"
        logger.error(error_msg)
        return error_msg, 500

@auth_bp.route('/oauth2callback')
def oauth2callback():
    """Handle the OAuth callback with token saving for automation"""
    logger.info("Handling OAuth callback...")
    
    # Check for errors in the callback
    error = request.args.get('error')
    if error:
        error_description = request.args.get('error_description', 'No description provided')
        error_msg = f"OAuth error: {error} - {error_description}"
        logger.error(error_msg)
        return f"""
        <h2>❌ Authorization Error</h2>
        <p><strong>Error:</strong> {error}</p>
        <p><strong>Description:</strong> {error_description}</p>
        <p><a href="/google-login">Try Again</a></p>
        """, 400
    
    try:
        creds_path = get_credentials_path()
        if not creds_path:
            raise Exception("Credentials file not found")
        
        # Verify state parameter
        if 'state' not in session:
            raise Exception("Missing state parameter in session")
        
        # Use the same scopes that were stored during authorization
        requested_scopes = session.get('oauth_scopes', SCOPES)
        
        flow = Flow.from_client_secrets_file(
            creds_path,
            scopes=requested_scopes,  # Use the scopes from session
            state=session['state'],
            redirect_uri=url_for('auth.oauth2callback', _external=True)
        )
        
        # Fetch the token
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
        
        # Cache credentials globally
        global _cached_credentials
        _cached_credentials = credentials
        
        # Save tokens persistently using TokenStorage
        try:
            from helpers.token_storage import token_storage
            success = token_storage.save_google_tokens(
                refresh_token=credentials.refresh_token,
                access_token=credentials.token,
                client_id=credentials.client_id,
                client_secret=credentials.client_secret
            )
            
            if success:
                logger.info("✅ Google tokens saved persistently")
            else:
                logger.warning("Failed to save Google tokens persistently")
        except Exception as e:
            logger.error(f"Error saving Google tokens to storage: {e}")
        
        # Clean up session
        session.pop('state', None)
        session.pop('oauth_scopes', None)
        
        logger.info("OAuth flow completed successfully with persistent storage")
        return """
        <h2>✅ Google Authorization Successful!</h2>
        <p>Google services are now authenticated and tokens saved persistently!</p>
        <p>Your Google authentication will persist across app restarts.</p>
        <h3>Quick Tests</h3>
        <ul>
            <li><a href="/test-gmail">Test Gmail</a></li>
            <li><a href="/test-google-services">Test All Google Services</a></li>
            <li><a href="/google-status">Check Google Status</a></li>
        </ul>
        <h3>Next Steps</h3>
        <ul>
            <li><a href="/save-current-google-tokens">Save Tokens for Environment Setup</a></li>
        </ul>
        """
    except Exception as e:
        error_msg = f"Error in OAuth callback: {e}"
        logger.error(error_msg)
        # Clear any partial session data
        session.pop('google_credentials', None)
        session.pop('state', None)
        session.pop('oauth_scopes', None)
        return f"""
        <h2>❌ Error completing authorization</h2>
        <p><strong>Error:</strong> {str(e)}</p>
        <p><a href="/google-login">Try Again</a></p>
        <p><a href="/google-auth-status">Check Auth Status</a></p>
        """, 500

@auth_bp.route('/auth-status')
def auth_status():
    """Check authentication status with auto-auth info"""
    try:
        creds = load_credentials()
        refresh_token_env = os.getenv("GOOGLE_REFRESH_TOKEN")
        
        status = {
            "authenticated": bool(creds and creds.valid),
            "has_refresh_token_env": bool(refresh_token_env),
            "auto_auth_available": bool(refresh_token_env),
            "credentials_path": get_credentials_path(),
            "required_scopes": SCOPES
        }
        
        if creds:
            status.update({
                "scopes": list(creds.scopes) if hasattr(creds, 'scopes') else SCOPES,
                "credential_type": "service_account" if hasattr(creds, 'service_account_email') else "oauth",
                "credentials_valid": creds.valid,
                "credentials_expired": getattr(creds, 'expired', False)
            })
        else:
            status.update({
                "auth_url": url_for('auth.authorize', _external=True)
            })
        
        # Add recommendations
        actions = []
        if not status["authenticated"]:
            if not status["has_refresh_token_env"]:
                actions.append("Complete OAuth flow to get refresh token")
            else:
                actions.append("Check refresh token validity")
        else:
            actions.append("Google services ready to use")
            
        status["recommended_actions"] = actions
        return status
    except Exception as e:
        logger.error(f"Error checking auth status: {e}")
        return {
            "error": str(e),
            "credentials_path": get_credentials_path(),
            "env_var": os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            "required_scopes": SCOPES
        }, 500

@auth_bp.route('/clear-auth')
def clear_auth():
    """Clear stored authentication data"""
    global _cached_credentials
    _cached_credentials = None
    session.pop('google_credentials', None)
    session.pop('state', None)
    session.pop('oauth_scopes', None)
    return """
    <h2>✅ Authentication Cleared</h2>
    <p>All stored Google authentication data has been cleared.</p>
    <p><a href="/google-login">Re-authenticate</a></p>
    """

@auth_bp.route('/debug-credentials')
def debug_credentials():
    """Debug endpoint to check credential file status"""
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    creds_path = get_credentials_path()
    
    debug_info = {
        "GOOGLE_APPLICATION_CREDENTIALS": env_path,
        "env_file_exists": bool(env_path and os.path.exists(env_path)),
        "found_credentials_path": creds_path,
        "file_exists": bool(creds_path and os.path.exists(creds_path)),
        "required_scopes": SCOPES
    }
    
    if creds_path:
        try:
            debug_info["file_size"] = os.path.getsize(creds_path)
            
            with open(creds_path, 'r') as f:
                content = f.read()
                debug_info["file_readable"] = True
                debug_info["content_length"] = len(content)
                debug_info["starts_with"] = content[:100] + "..." if len(content) > 100 else content
                
                try:
                    data = json.loads(content)
                    debug_info["valid_json"] = True
                    debug_info["json_keys"] = list(data.keys())
                except json.JSONDecodeError as e:
                    debug_info["valid_json"] = False
                    debug_info["json_error"] = str(e)
            
            is_valid, result = validate_credentials_file(creds_path)
            debug_info["file_valid"] = is_valid
            debug_info["validation_result"] = result
            
        except Exception as e:
            debug_info["file_error"] = str(e)
    
    return debug_info

