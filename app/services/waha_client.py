"""
WAHA WhatsApp Client
"""
import json
import time
import requests
import threading
from flask import current_app
import logging

logger = logging.getLogger(__name__)

class WAHAClient:
    """WAHA WhatsApp API client"""
    
    def __init__(self):
        self.base_url = None
        self.api_key = None
        self.session_name = None
        self.keepalive_active = False
        self._initialize_config()
    
    def _initialize_config(self):
        """Initialize WAHA configuration from app config"""
        if current_app:
            config = current_app.config
            self.waha_url = config.get('WAHA_URL')
            self.api_key = config.get('WAHA_API_KEY')
            self.session_name = config.get('WAHA_SESSION', 'default')
            self.keepalive_interval = config.get('WAHA_KEEPALIVE_INTERVAL', 600)
            self.base_url = self._get_base_url()
    
    def _get_base_url(self):
        """Extract base URL from WAHA_URL"""
        if not self.waha_url:
            return None
        if "/api/" in self.waha_url:
            return self.waha_url.split("/api/")[0]
        return self.waha_url.rstrip("/")
    
    def _get_headers(self, is_json=True):
        """Get request headers"""
        headers = {}
        if is_json:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        return headers
    
    def health_check(self):
        """Check if WAHA session is healthy"""
        try:
            if not self.base_url:
                return False
            
            headers = self._get_headers()
            url = f"{self.base_url}/api/sessions/{self.session_name}"
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                status = (data.get("status") or "").lower()
                return status in ("working", "active", "connected", "ready")
            
            # Try to create and start session if not found
            if response.status_code == 404:
                self._create_session()
                self._start_session()
                return True
                
            return False
            
        except Exception as e:
            logger.warning(f"WAHA health check error: {e}")
            return False
    
    def _create_session(self):
        """Create WAHA session"""
        try:
            headers = self._get_headers()
            url = f"{self.base_url}/api/sessions/{self.session_name}"
            response = requests.post(url, headers=headers, timeout=15)
            
            if response.status_code not in (200, 201, 409):
                logger.warning(f"WAHA create session failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error creating WAHA session: {e}")
    
    def _start_session(self):
        """Start WAHA session"""
        try:
            headers = self._get_headers()
            url = f"{self.base_url}/api/sessions/{self.session_name}/start"
            response = requests.post(url, headers=headers, timeout=20)
            
            if response.status_code in (200, 202):
                return True
            if response.status_code == 422 and "already started" in response.text.lower():
                return True
                
            logger.warning(f"WAHA start session failed: {response.status_code}")
            return False
            
        except Exception as e:
            logger.error(f"Error starting WAHA session: {e}")
            return False
    
    def send_message(self, phone, text):
        """Send text message"""
        try:
            if not self.health_check():
                logger.warning("WAHA not ready; message not sent")
                return False
            
            # Ensure phone has correct format
            if "@c.us" not in phone:
                phone = f"{phone}@c.us"
            
            payload = {"chatId": phone, "text": text}
            headers = self._get_headers()
            
            # Try primary endpoint
            if self.waha_url:
                response = requests.post(
                    self.waha_url, 
                    headers=headers, 
                    data=json.dumps(payload), 
                    timeout=20
                )
                if response.status_code in (200, 201):
                    return True
            
            # Try alternative endpoint
            alt_url = f"{self.base_url}/api/sessions/{self.session_name}/messages/text"
            response = requests.post(
                alt_url, 
                headers=headers, 
                data=json.dumps(payload), 
                timeout=20
            )
            
            if response.status_code in (200, 201):
                return True
            
            logger.error(f"WAHA send_message failed: {response.status_code} {response.text}")
            return False
            
        except Exception as e:
            logger.error(f"WAHA send_message error: {e}")
            return False
    
    def start_keepalive(self):
        """Start keep-alive thread"""
        if self.keepalive_active:
            return
        
        self.keepalive_active = True
        threading.Thread(target=self._keepalive_loop, daemon=True).start()
        logger.info("WAHA keep-alive started")
    
    def stop_keepalive(self):
        """Stop keep-alive thread"""
        self.keepalive_active = False
        logger.info("WAHA keep-alive stopped")
    
    def _keepalive_loop(self):
        """Keep-alive background loop"""
        while self.keepalive_active:
            ok = self.health_check()
            logger.info(f"WAHA keep-alive: {'OK' if ok else 'NOT READY'}")
            time.sleep(self.keepalive_interval)