"""
Firebase Manager for Wednesday WhatsApp Assistant

Handles Firestore operations for:
- Conversation history
- Task management
- User preferences
- Media metadata
- System state
"""
import os
import firebase_admin
from firebase_admin import credentials, firestore
from typing import List, Dict, Optional, Any

# Initialize Firebase app
if not firebase_admin._apps:
    cred_path = os.getenv("FIREBASE_CREDENTIALS", "firebase_credentials.json")
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
db = firestore.client()

class FirebaseManager:
    def __init__(self):
        self.db = db

    # Example: Add conversation
    def add_conversation(self, phone: str, role: str, message: str, metadata: Dict = None) -> bool:
        doc_ref = self.db.collection("conversations").document(phone).collection("messages").document()
        data = {
            "role": role,
            "message": message,
            "metadata": metadata or {},
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        doc_ref.set(data)
        return True

    # Example: Get conversation history
    def get_conversation_history(self, phone: str, limit: int = 10) -> List[Dict]:
        messages = (
            self.db.collection("conversations")
            .document(phone)
            .collection("messages")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        return [msg.to_dict() for msg in messages]

    # TODO: Implement other methods (tasks, reminders, preferences, media, etc.)

firebase_manager = FirebaseManager()
