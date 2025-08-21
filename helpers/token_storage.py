import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class TokenStorage:
    """Simple persistent token storage for authentication"""
    
    def __init__(self, storage_dir="task_data"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        self.google_token_file = self.storage_dir / "google_tokens.json"
        self.spotify_token_file = self.storage_dir / "spotify_tokens.json"
    
    def save_google_tokens(self, refresh_token, access_token=None, client_id=None, client_secret=None):
        """Save Google OAuth tokens for persistence"""
        try:
            tokens = {
                "refresh_token": refresh_token,
                "access_token": access_token,
                "client_id": client_id,
                "client_secret": client_secret
            }
            
            with open(self.google_token_file, 'w') as f:
                json.dump(tokens, f)
            
            logger.info(f"Google tokens saved to {self.google_token_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save Google tokens: {e}")
            return False
    
    def load_google_tokens(self):
        """Load Google OAuth tokens from storage"""
        try:
            if not self.google_token_file.exists():
                return None
            
            with open(self.google_token_file, 'r') as f:
                tokens = json.load(f)
            
            return tokens
        except Exception as e:
            logger.error(f"Failed to load Google tokens: {e}")
            return None
    
    def save_spotify_tokens(self, refresh_token, access_token=None):
        """Save Spotify OAuth tokens for persistence"""
        try:
            tokens = {
                "refresh_token": refresh_token,
                "access_token": access_token
            }
            
            with open(self.spotify_token_file, 'w') as f:
                json.dump(tokens, f)
            
            logger.info(f"Spotify tokens saved to {self.spotify_token_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save Spotify tokens: {e}")
            return False
    
    def load_spotify_tokens(self):
        """Load Spotify OAuth tokens from storage"""
        try:
            if not self.spotify_token_file.exists():
                return None
            
            with open(self.spotify_token_file, 'r') as f:
                tokens = json.load(f)
            
            return tokens
        except Exception as e:
            logger.error(f"Failed to load Spotify tokens: {e}")
            return None
    
    def clear_google_tokens(self):
        """Clear stored Google tokens"""
        try:
            if self.google_token_file.exists():
                self.google_token_file.unlink()
            return True
        except Exception as e:
            logger.error(f"Failed to clear Google tokens: {e}")
            return False
    
    def clear_spotify_tokens(self):
        """Clear stored Spotify tokens"""
        try:
            if self.spotify_token_file.exists():
                self.spotify_token_file.unlink()
            return True
        except Exception as e:
            logger.error(f"Failed to clear Spotify tokens: {e}")
            return False

# Global instance
token_storage = TokenStorage()