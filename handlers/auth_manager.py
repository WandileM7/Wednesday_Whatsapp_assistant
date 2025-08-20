"""
Unified Authentication Manager for WhatsApp Assistant

This module provides a centralized way to manage authentication for all services:
- Google Services (Gmail, Calendar, etc.)
- Spotify
- Environment variable management
- Automatic token refresh and validation
"""

import os
import json
import logging
from typing import Dict, Optional, Tuple, Any
from datetime import datetime
from flask import session

logger = logging.getLogger(__name__)

class AuthenticationManager:
    """Centralized authentication manager for all services"""
    
    def __init__(self):
        self.services = {
            'google': GoogleAuthHandler(),
            'spotify': SpotifyAuthHandler()
        }
    
    def get_auth_status(self) -> Dict[str, Any]:
        """Get comprehensive authentication status for all services"""
        status = {
            'timestamp': datetime.now().isoformat(),
            'services': {},
            'overall_status': 'healthy'
        }
        
        issues = []
        authenticated_count = 0
        
        for service_name, handler in self.services.items():
            try:
                service_status = handler.get_status()
                status['services'][service_name] = service_status
                
                if service_status.get('authenticated', False):
                    authenticated_count += 1
                else:
                    issues.append(f"{service_name} not authenticated")
                    
            except Exception as e:
                logger.error(f"Error getting {service_name} status: {e}")
                status['services'][service_name] = {
                    'authenticated': False,
                    'error': str(e),
                    'status': 'error'
                }
                issues.append(f"{service_name} has errors")
        
        # Determine overall status
        if authenticated_count == 0:
            status['overall_status'] = 'not_configured'
        elif authenticated_count < len(self.services):
            status['overall_status'] = 'partial'
        
        status['summary'] = {
            'authenticated_services': authenticated_count,
            'total_services': len(self.services),
            'issues': issues,
            'ready_for_automation': authenticated_count == len(self.services)
        }
        
        return status
    
    def setup_automatic_authentication(self) -> Dict[str, Any]:
        """Set up automatic authentication for all services"""
        results = {
            'timestamp': datetime.now().isoformat(),
            'services': {},
            'success': True
        }
        
        for service_name, handler in self.services.items():
            try:
                setup_result = handler.setup_automatic_auth()
                results['services'][service_name] = setup_result
                
                if not setup_result.get('success', False):
                    results['success'] = False
                    
            except Exception as e:
                logger.error(f"Error setting up {service_name} auto-auth: {e}")
                results['services'][service_name] = {
                    'success': False,
                    'error': str(e)
                }
                results['success'] = False
        
        return results
    
    def test_webhook_authentication(self) -> Dict[str, Any]:
        """Test authentication as it would work in webhook context (no session)"""
        original_session = dict(session) if session else {}
        
        # Clear session to simulate webhook environment
        if session:
            session.clear()
        
        try:
            results = {
                'timestamp': datetime.now().isoformat(),
                'webhook_simulation': True,
                'services': {}
            }
            
            for service_name, handler in self.services.items():
                try:
                    test_result = handler.test_webhook_auth()
                    results['services'][service_name] = test_result
                except Exception as e:
                    logger.error(f"Error testing {service_name} webhook auth: {e}")
                    results['services'][service_name] = {
                        'success': False,
                        'error': str(e)
                    }
            
            return results
            
        finally:
            # Restore original session
            if session and original_session:
                session.update(original_session)
    
    def get_service_handler(self, service_name: str):
        """Get a specific service handler"""
        return self.services.get(service_name)


class GoogleAuthHandler:
    """Handle Google service authentication"""
    
    def get_status(self) -> Dict[str, Any]:
        """Get Google authentication status"""
        try:
            from handlers.google_auth import load_credentials
            
            creds = load_credentials()
            refresh_token_env = os.getenv("GOOGLE_REFRESH_TOKEN")
            
            status = {
                'service': 'google',
                'authenticated': bool(creds and creds.valid),
                'has_refresh_token_env': bool(refresh_token_env),
                'auto_auth_available': bool(refresh_token_env),
                'status': 'active' if creds and creds.valid else 'not_configured'
            }
            
            if creds:
                status.update({
                    'credentials_valid': creds.valid,
                    'credentials_expired': getattr(creds, 'expired', False),
                    'scopes': list(creds.scopes) if hasattr(creds, 'scopes') else []
                })
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting Google auth status: {e}")
            return {
                'service': 'google',
                'authenticated': False,
                'status': 'error',
                'error': str(e)
            }
    
    def setup_automatic_auth(self) -> Dict[str, Any]:
        """Set up automatic Google authentication"""
        try:
            if 'google_credentials' not in session:
                return {
                    'success': False,
                    'message': 'No Google credentials in session',
                    'action': 'Visit /google-login to authenticate'
                }
            
            from google.oauth2.credentials import Credentials
            from handlers.google_auth import SCOPES
            
            creds = Credentials.from_authorized_user_info(session['google_credentials'], SCOPES)
            
            if creds.refresh_token:
                env_vars = {
                    'GOOGLE_REFRESH_TOKEN': creds.refresh_token,
                    'GOOGLE_CLIENT_ID': creds.client_id,
                    'GOOGLE_CLIENT_SECRET': creds.client_secret
                }
                
                self._update_env_file(env_vars)
                
                return {
                    'success': True,
                    'message': 'Google tokens saved for automation',
                    'env_vars': env_vars
                }
            else:
                return {
                    'success': False,
                    'message': 'No Google refresh token available',
                    'action': 'Re-authenticate at /google-login with consent'
                }
                
        except Exception as e:
            logger.error(f"Error setting up Google auto-auth: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def test_webhook_auth(self) -> Dict[str, Any]:
        """Test Google authentication in webhook context"""
        try:
            from handlers.google_auth import load_credentials
            from googleapiclient.discovery import build
            
            creds = load_credentials()
            if not creds:
                return {
                    'success': False,
                    'message': 'No Google credentials available in webhook context'
                }
            
            # Test Gmail service
            service = build('gmail', 'v1', credentials=creds)
            profile = service.users().getProfile(userId='me').execute()
            
            return {
                'success': True,
                'message': f'Google authenticated as {profile.get("emailAddress", "unknown")}',
                'email': profile.get('emailAddress')
            }
            
        except Exception as e:
            logger.error(f"Error testing Google webhook auth: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _update_env_file(self, env_vars: Dict[str, str]):
        """Update .env file with new environment variables"""
        try:
            env_file = ".env"
            content = ""
            
            if os.path.exists(env_file):
                with open(env_file, 'r') as f:
                    content = f.read()
            
            for key, value in env_vars.items():
                if f'{key}=' in content:
                    import re
                    content = re.sub(f'{key}=.*', f'{key}="{value}"', content)
                else:
                    content += f'\n{key}="{value}"\n'
            
            with open(env_file, 'w') as f:
                f.write(content)
            
            logger.info(f"Updated .env file with {len(env_vars)} variables")
            
        except Exception as e:
            logger.warning(f"Could not update .env file: {e}")


class SpotifyAuthHandler:
    """Handle Spotify authentication"""
    
    def get_status(self) -> Dict[str, Any]:
        """Get Spotify authentication status"""
        try:
            from handlers.spotify_client import get_token_info, is_authenticated
            
            token_info = get_token_info()
            refresh_token_env = os.getenv("SPOTIFY_REFRESH_TOKEN")
            
            return {
                'service': 'spotify',
                'authenticated': is_authenticated(),
                'has_refresh_token_env': bool(refresh_token_env),
                'auto_auth_available': bool(refresh_token_env),
                'session_active': bool(token_info),
                'status': 'active' if is_authenticated() else 'not_configured'
            }
            
        except Exception as e:
            logger.error(f"Error getting Spotify auth status: {e}")
            return {
                'service': 'spotify',
                'authenticated': False,
                'status': 'error',
                'error': str(e)
            }
    
    def setup_automatic_auth(self) -> Dict[str, Any]:
        """Set up automatic Spotify authentication"""
        try:
            from handlers.spotify_client import get_token_info
            
            token_info = get_token_info()
            if not token_info or not token_info.get('refresh_token'):
                return {
                    'success': False,
                    'message': 'No Spotify refresh token available',
                    'action': 'Visit /login to authenticate Spotify'
                }
            
            refresh_token = token_info['refresh_token']
            env_vars = {'SPOTIFY_REFRESH_TOKEN': refresh_token}
            
            self._update_env_file(env_vars)
            
            return {
                'success': True,
                'message': 'Spotify refresh token saved for automation',
                'env_vars': env_vars
            }
            
        except Exception as e:
            logger.error(f"Error setting up Spotify auto-auth: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def test_webhook_auth(self) -> Dict[str, Any]:
        """Test Spotify authentication in webhook context"""
        try:
            from handlers.spotify_client import get_token_info
            import spotipy
            
            token_info = get_token_info()
            if not token_info:
                return {
                    'success': False,
                    'message': 'No Spotify token available in webhook context'
                }
            
            sp = spotipy.Spotify(auth=token_info["access_token"])
            user = sp.current_user()
            
            return {
                'success': True,
                'message': f'Spotify authenticated as {user.get("display_name", "unknown")}',
                'user_id': user.get('id'),
                'display_name': user.get('display_name')
            }
            
        except Exception as e:
            logger.error(f"Error testing Spotify webhook auth: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _update_env_file(self, env_vars: Dict[str, str]):
        """Update .env file with new environment variables"""
        try:
            env_file = ".env"
            content = ""
            
            if os.path.exists(env_file):
                with open(env_file, 'r') as f:
                    content = f.read()
            
            for key, value in env_vars.items():
                if f'{key}=' in content:
                    import re
                    content = re.sub(f'{key}=.*', f'{key}="{value}"', content)
                else:
                    content += f'\n{key}="{value}"\n'
            
            with open(env_file, 'w') as f:
                f.write(content)
            
            logger.info(f"Updated .env file with {len(env_vars)} variables")
            
        except Exception as e:
            logger.warning(f"Could not update .env file: {e}")


# Global instance
auth_manager = AuthenticationManager()