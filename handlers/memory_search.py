"""
Conversation Memory Search Handler
Search and recall past conversations.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from google import genai
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

GENERATION_MODEL = "gemini-2.5-flash"

try:
    genai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
except Exception as e:
    logger.warning(f"Gemini client unavailable: {e}")
    genai_client = None


def search_conversation_history(
    phone: str,
    query: str,
    days: int = 30,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Search conversation history for a query.
    
    Args:
        phone: User's phone number
        query: Search query
        days: Number of days to search back
        limit: Maximum results to return
        
    Returns:
        List of matching conversation entries
    """
    try:
        from database import query_conversation_history
        
        results = query_conversation_history(phone, query, limit=limit)
        
        if results:
            return [
                {
                    'content': r if isinstance(r, str) else r.get('content', str(r)),
                    'relevance': 1.0 - (i * 0.1)  # Decreasing relevance
                }
                for i, r in enumerate(results)
            ]
        return []
        
    except Exception as e:
        logger.error(f"Error searching conversation history: {e}")
        return []


def get_recent_conversations(phone: str, count: int = 10) -> List[Dict[str, Any]]:
    """
    Get recent conversations for a user.
    
    Args:
        phone: User's phone number
        count: Number of recent messages to retrieve
        
    Returns:
        List of recent conversation entries
    """
    try:
        from database import retrieve_conversation_history
        
        history = retrieve_conversation_history(phone, n_results=count)
        
        return [
            {'content': msg, 'index': i}
            for i, msg in enumerate(history)
        ]
        
    except Exception as e:
        logger.error(f"Error getting recent conversations: {e}")
        return []


def summarize_past_conversations(phone: str, topic: str = None) -> str:
    """
    Summarize past conversations, optionally filtered by topic.
    
    Args:
        phone: User's phone number
        topic: Optional topic to focus on
        
    Returns:
        Summary string
    """
    try:
        if not genai_client:
            return "AI summarization not available"
        
        # Get conversation history
        if topic:
            history = search_conversation_history(phone, topic, limit=20)
        else:
            history = get_recent_conversations(phone, count=20)
        
        if not history:
            return "No conversation history found."
        
        # Extract content
        messages = [h.get('content', str(h)) for h in history]
        conversation_text = '\n'.join(messages[-20:])  # Last 20 messages
        
        prompt = f"""Summarize the following conversation history. Focus on:
1. Key topics discussed
2. Important information shared
3. Any tasks or reminders mentioned
4. Decisions made

{"Focus specifically on: " + topic if topic else ""}

Conversation:
{conversation_text}

Provide a concise summary in 3-5 bullet points."""
        response = genai_client.models.generate_content(
            model=GENERATION_MODEL,
            contents=prompt,
        )

        if response and getattr(response, "text", None):
            return response.text
        return "Could not generate summary"
            
    except Exception as e:
        logger.error(f"Error summarizing conversations: {e}")
        return f"Error generating summary: {e}"


def recall_information(phone: str, question: str) -> str:
    """
    Recall specific information from past conversations.
    
    Args:
        phone: User's phone number
        question: What to recall (e.g., "What did we talk about last week?")
        
    Returns:
        Recalled information
    """
    try:
        if not genai_client:
            return "AI recall not available"
        
        # Search for relevant history
        results = search_conversation_history(phone, question, limit=15)
        
        if not results:
            return "I don't have any relevant conversation history to recall."
        
        messages = [r.get('content', str(r)) for r in results]
        history_text = '\n'.join(messages)
        
        prompt = f"""Based on the following conversation history, answer the user's question.
        
User's question: {question}

Conversation history:
{history_text}

Answer the question based on the conversation history. If the information isn't in the history, say so.
Be specific and include relevant details from the conversations."""

        response = genai_client.models.generate_content(
            model=GENERATION_MODEL,
            contents=prompt,
        )

        if response and getattr(response, "text", None):
            return response.text
        return "Could not recall that information"
            
    except Exception as e:
        logger.error(f"Error recalling information: {e}")
        return f"Error recalling: {e}"


def get_conversation_stats(phone: str) -> Dict[str, Any]:
    """
    Get statistics about conversation history.
    
    Args:
        phone: User's phone number
        
    Returns:
        Statistics dictionary
    """
    try:
        history = get_recent_conversations(phone, count=100)
        
        if not history:
            return {
                'total_messages': 0,
                'message': 'No conversation history yet'
            }
        
        # Analyze content
        total_words = sum(len(h.get('content', '').split()) for h in history)
        
        return {
            'total_messages': len(history),
            'total_words': total_words,
            'avg_words_per_message': total_words / len(history) if history else 0
        }
        
    except Exception as e:
        logger.error(f"Error getting conversation stats: {e}")
        return {'error': str(e)}


def format_memory_search(phone: str, query: str) -> str:
    """
    Search memory and format results nicely.
    
    Args:
        phone: User's phone number
        query: Search query
        
    Returns:
        Formatted search results
    """
    results = search_conversation_history(phone, query, limit=5)
    
    if not results:
        return f"🔍 No conversations found matching '{query}'"
    
    response = f"🔍 **Memory Search: '{query}'**\n\n"
    
    for i, result in enumerate(results, 1):
        content = result.get('content', str(result))
        # Truncate long messages
        if len(content) > 150:
            content = content[:150] + "..."
        response += f"{i}. {content}\n\n"
    
    return response


def what_did_we_discuss(phone: str, timeframe: str = "recently") -> str:
    """
    Answer "what did we discuss" type questions.
    
    Args:
        phone: User's phone number
        timeframe: Time reference (recently, yesterday, last week, etc.)
        
    Returns:
        Summary of discussions
    """
    # Map timeframe to days
    timeframe_days = {
        'recently': 3,
        'today': 1,
        'yesterday': 2,
        'this week': 7,
        'last week': 14,
        'this month': 30
    }
    
    days = timeframe_days.get(timeframe.lower(), 7)
    
    return summarize_past_conversations(phone)


# Service class
class MemoryService:
    """Service for conversation memory search."""
    
    def search(self, phone: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        return search_conversation_history(phone, query, limit=limit)
    
    def recall(self, phone: str, question: str) -> str:
        return recall_information(phone, question)
    
    def summarize(self, phone: str, topic: str = None) -> str:
        return summarize_past_conversations(phone, topic)
    
    def format_search(self, phone: str, query: str) -> str:
        return format_memory_search(phone, query)
    
    def get_stats(self, phone: str) -> Dict[str, Any]:
        return get_conversation_stats(phone)


memory_service = MemoryService()
