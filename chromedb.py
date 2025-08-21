import chromadb
import logging
import os
from typing import Optional
import datetime
import time

logger = logging.getLogger(__name__)

# Use a lighter, in-memory client with minimal configuration
def get_chroma_client():
    """Get ChromaDB client with memory-optimized settings"""
    try:
        # Disable all external connections for ChromaDB 
        settings = chromadb.Settings(
            anonymized_telemetry=False,  # Disable telemetry
            allow_reset=True
        )
        
        # Use ephemeral client (in-memory) to save disk space
        # Or use persistent with minimal settings
        if os.getenv("USE_MEMORY_DB", "true").lower() == "true":
            logger.info("Using in-memory ChromaDB client")
            client = chromadb.EphemeralClient(settings=settings)
        else:
            logger.info("Using persistent ChromaDB client")
            client = chromadb.PersistentClient(
                path="./chroma_db",
                settings=settings
            )
        return client
    except Exception as e:
        logger.error(f"ChromaDB initialization failed: {e}")
        return None

# Initialize client lazily
_chroma_client = None

def get_collection():
    """Get or create conversation collection with lazy loading"""
    global _chroma_client
    
    if _chroma_client is None:
        _chroma_client = get_chroma_client()
        if _chroma_client is None:
            return None
    
    try:
        # Use default embedding function (lighter than downloading models)
        collection = _chroma_client.get_or_create_collection(
            name="conversations",
            metadata={"description": "WhatsApp conversation history"}
        )
        return collection
    except Exception as e:
        logger.error(f"Failed to get collection: {e}")
        return None

def add_to_conversation_history(phone: str, role: str, message: str) -> bool:
    """Add message to conversation history with error handling"""
    try:
        collection = get_collection()
        if collection is None:
            logger.warning("ChromaDB not available, using fallback storage")
            return _add_to_fallback_history(phone, role, message)
        
        # Create a simple document ID
        doc_id = f"{phone}_{role}_{hash(message) % 10000}"
        
        collection.add(
            documents=[message],
            ids=[doc_id],
            metadatas=[{
                "phone": phone,
                "role": role,
                "timestamp": str(int(time.time()))
            }]
        )
        
        logger.debug(f"Added message to ChromaDB: {doc_id}")
        return True
        
    except Exception as e:
        logger.warning(f"Failed to add to conversation history: {e}")
        # Fallback to simple in-memory storage
        return _add_to_fallback_history(phone, role, message)

# Simple in-memory fallback for conversation history
_fallback_history = {}

def _add_to_fallback_history(phone: str, role: str, message: str) -> bool:
    """Fallback conversation history storage"""
    try:
        if phone not in _fallback_history:
            _fallback_history[phone] = []
        
        _fallback_history[phone].append({
            "role": role,
            "message": message,
            "timestamp": int(time.time())
        })
        
        # Keep only last 50 messages per phone
        _fallback_history[phone] = _fallback_history[phone][-50:]
        logger.debug(f"Added message to fallback history for {phone}")
        return True
    except Exception as e:
        logger.error(f"Fallback history storage failed: {e}")
        return False

def _retrieve_fallback_history(phone: str, n_results: int = 5) -> list:
    """Retrieve from fallback conversation history"""
    try:
        if phone not in _fallback_history:
            return []
        
        messages = _fallback_history[phone][-n_results:]
        return [f"{msg['role']}: {msg['message']}" for msg in messages]
    except Exception as e:
        logger.error(f"Fallback history retrieval failed: {e}")
        return []

def retrieve_conversation_history(phone, n_results=5):
    """Retrieves the most recent messages from the conversation history."""
    try:
        collection = get_collection()
        if collection is None:
            logger.warning("ChromaDB not available, using fallback history")
            return _retrieve_fallback_history(phone, n_results)
        
        # Use the phone as a dummy query text to satisfy ChromaDB's requirement
        results = collection.query(
            query_texts=[phone],
            n_results=20,    # Fetch more to allow filtering
            where={"phone": phone}
        )
        
        # Flatten and sort by timestamp descending in Python
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])
        history = []
        items = []
        for doc, meta in zip(docs[0] if docs else [], metas[0] if metas else []):
            timestamp = meta.get("timestamp")
            items.append((timestamp, doc))
        # Sort by timestamp descending
        items.sort(reverse=True)
        for _, doc in items[:n_results]:
            history.append(doc)
        return history
    
    except Exception as e:
        logger.warning(f"Failed to query conversation history: {e}")
        # Fallback to simple in-memory storage
        return _retrieve_fallback_history(phone, n_results)

def query_conversation_history(phone, query, limit=5):
    """Query conversation history - alias for retrieve_conversation_history"""
    return retrieve_conversation_history(phone, n_results=limit)

def clear_old_conversations(days_old: int = 7) -> bool:
    """Clear old conversations to manage memory"""
    try:
        collection = get_collection()
        if collection is None:
            return False
        
        cutoff_time = str(int(time.time()) - (days_old * 24 * 60 * 60))
        
        # This is a simplified approach - ChromaDB doesn't have direct timestamp filtering
        # In a production app, you'd implement this differently
        logger.info(f"Would clear conversations older than {days_old} days")
        return True
        
    except Exception as e:
        logger.error(f"Failed to clear old conversations: {e}")
        return False