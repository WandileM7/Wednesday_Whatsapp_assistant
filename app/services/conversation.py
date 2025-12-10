"""
Conversation Manager Service
Handles conversation state and history management
"""
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversation state and history for users"""
    
    def __init__(self):
        self._conversations: Dict[str, List[Dict[str, Any]]] = {}
        self._max_history = 50
    
    def get_history(self, user_id: str) -> List[Dict[str, Any]]:
        """Get conversation history for a user"""
        return self._conversations.get(user_id, [])
    
    def add_message(self, user_id: str, role: str, content: str) -> None:
        """Add a message to conversation history"""
        if user_id not in self._conversations:
            self._conversations[user_id] = []
        
        self._conversations[user_id].append({
            "role": role,
            "content": content
        })
        
        # Trim history if too long
        if len(self._conversations[user_id]) > self._max_history:
            self._conversations[user_id] = self._conversations[user_id][-self._max_history:]
    
    def clear_history(self, user_id: str) -> None:
        """Clear conversation history for a user"""
        if user_id in self._conversations:
            del self._conversations[user_id]
    
    def get_context(self, user_id: str, num_messages: int = 10) -> List[Dict[str, Any]]:
        """Get recent conversation context"""
        history = self.get_history(user_id)
        return history[-num_messages:] if history else []
