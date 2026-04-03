"""
n8n Integration Handler for Wednesday WhatsApp Assistant

This module provides integration with self-hosted n8n for workflow automation.
When n8n is enabled, messages can be routed through n8n workflows for
enhanced AI agent capabilities with MCP tools (Gmail, Calendar, Tasks, etc.)
"""

import os
import logging
import requests
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# n8n Configuration
N8N_ENABLED = os.getenv("N8N_ENABLED", "false").lower() == "true"
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://n8n:5678")
N8N_WEBHOOK_PATH = os.getenv("N8N_WEBHOOK_PATH", "/webhook/whatsapp-webhook")
N8N_TIMEOUT = int(os.getenv("N8N_TIMEOUT", "60"))


class N8NClient:
    """Client for interacting with n8n workflows"""
    
    def __init__(self):
        self.enabled = N8N_ENABLED
        self.base_url = N8N_WEBHOOK_URL.rstrip('/')
        self.webhook_path = N8N_WEBHOOK_PATH
        self.timeout = N8N_TIMEOUT
        
    @property
    def webhook_url(self) -> str:
        """Full URL for the WhatsApp webhook"""
        return f"{self.base_url}{self.webhook_path}"
    
    def is_available(self) -> bool:
        """Check if n8n is available and responding"""
        if not self.enabled:
            return False
            
        try:
            response = requests.get(
                f"{self.base_url}/healthz",
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"n8n health check failed: {e}")
            return False
    
    def forward_message(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Forward a WhatsApp message payload to n8n workflow
        
        Args:
            payload: WhatsApp message payload containing:
                - chatId: User's WhatsApp ID
                - body/text: Message content
                - type: Message type (text, voice, etc.)
                
        Returns:
            n8n response or None if failed
        """
        if not self.enabled:
            logger.debug("n8n integration disabled")
            return None
            
        try:
            logger.info(f"Forwarding message to n8n: {self.webhook_url}")
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"n8n workflow executed successfully")
                return result
            else:
                logger.error(f"n8n webhook returned {response.status_code}: {response.text}")
                return None
                
        except requests.Timeout:
            logger.error(f"n8n webhook timed out after {self.timeout}s")
            return None
        except Exception as e:
            logger.error(f"Error forwarding to n8n: {e}")
            return None
    
    def trigger_workflow(self, workflow_path: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Trigger a specific n8n workflow by path
        
        Args:
            workflow_path: Webhook path for the workflow (e.g., /webhook/daily-briefing)
            data: Data to send to the workflow
            
        Returns:
            Workflow response or None if failed
        """
        if not self.enabled:
            return None
            
        try:
            url = f"{self.base_url}{workflow_path}"
            response = requests.post(
                url,
                json=data,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Workflow {workflow_path} returned {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error triggering workflow {workflow_path}: {e}")
            return None


# Global client instance
n8n_client = N8NClient()


def should_use_n8n(message: str) -> bool:
    """
    Determine if a message should be processed by n8n instead of local handlers
    
    n8n is preferred for:
    - Complex multi-tool operations (email + calendar coordination)
    - MCP-based integrations (Gmail API, Calendar API, Tasks API)
    - Expense tracking (Google Sheets integration)
    
    Local processing is preferred for:
    - Quick commands (/help, /status)
    - Spotify playback control (real-time responsiveness needed)
    - Weather queries (simple API call)
    - News summaries
    """
    if not n8n_client.enabled:
        return False
    
    # Keywords that suggest MCP tool usage (better handled by n8n)
    n8n_keywords = [
        'email', 'mail', 'inbox', 'send email', 'draft',
        'calendar', 'schedule', 'meeting', 'appointment', 'event',
        'task', 'todo', 'reminder', 'due',
        'expense', 'spent', 'budget', 'track expense',
        'contact', 'address book'
    ]
    
    message_lower = message.lower()
    
    for keyword in n8n_keywords:
        if keyword in message_lower:
            return True
    
    return False


def process_via_n8n(phone: str, message: str, payload: Dict[str, Any]) -> Optional[str]:
    """
    Process a message through n8n workflow
    
    Args:
        phone: User's phone/chat ID
        message: Message content
        payload: Full WhatsApp webhook payload
        
    Returns:
        Response string from n8n or None if failed
    """
    if not n8n_client.enabled:
        return None
    
    # Ensure payload has consistent structure
    normalized_payload = {
        "payload": {
            "chatId": phone,
            "body": message,
            "text": message,
            "type": payload.get("type", "text"),
            "from": phone,
            "timestamp": payload.get("timestamp"),
            "messageId": payload.get("id") or payload.get("messageId")
        },
        "from": phone,
        "text": message
    }
    
    result = n8n_client.forward_message(normalized_payload)
    
    if result:
        # Extract response from n8n result
        # n8n workflow should return {"reply": "...", "chatId": "..."}
        return result.get("reply") or result.get("response") or result.get("output")
    
    return None


def get_n8n_status() -> Dict[str, Any]:
    """Get n8n integration status for health checks"""
    return {
        "enabled": n8n_client.enabled,
        "base_url": n8n_client.base_url,
        "webhook_url": n8n_client.webhook_url,
        "available": n8n_client.is_available() if n8n_client.enabled else False
    }
