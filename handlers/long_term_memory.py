"""
JARVIS Long-Term Memory System
==============================
Advanced conversation memory with context recall and learning.
"Remember what we discussed yesterday about the project"
"""

import os
import logging
import json
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)

# Try to import database
try:
    from database import db_manager
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    db_manager = None

# Try to import AI for summarization
try:
    from google import genai
    from config import GEMINI_API_KEY
    AI_AVAILABLE = bool(GEMINI_API_KEY)
    if AI_AVAILABLE:
        genai_client = genai.Client(api_key=GEMINI_API_KEY)
except:
    AI_AVAILABLE = False
    genai_client = None


@dataclass
class MemoryEntry:
    """A single memory entry"""
    id: str
    phone: str
    content: str
    summary: str
    category: str
    importance: float  # 0-1 scale
    timestamp: datetime
    references: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    recalled_count: int = 0
    last_recalled: datetime = None


@dataclass
class UserContext:
    """User's contextual information"""
    phone: str
    name: str = None
    preferences: Dict[str, Any] = field(default_factory=dict)
    facts: List[str] = field(default_factory=list)  # Known facts about user
    topics_of_interest: Dict[str, float] = field(default_factory=dict)
    conversation_style: str = "formal"
    timezone: str = "UTC"
    location: str = None
    last_interaction: datetime = None


class LongTermMemory:
    """JARVIS Long-Term Memory System"""
    
    def __init__(self):
        self.memories: Dict[str, List[MemoryEntry]] = defaultdict(list)
        self.user_contexts: Dict[str, UserContext] = {}
        self.conversation_summaries: Dict[str, List[Dict]] = defaultdict(list)
        
        # Memory categories
        self.categories = [
            "personal",      # Personal info about user
            "task",          # Task-related memories
            "preference",    # User preferences
            "event",         # Important events
            "topic",         # Discussion topics
            "instruction",   # User instructions/rules
            "relationship",  # People mentioned
            "location",      # Places mentioned
        ]
        
        # Keywords for category detection
        self.category_keywords = {
            "personal": ["my name", "i am", "i'm", "my birthday", "my age", "i work", "i live"],
            "task": ["remind me", "todo", "task", "deadline", "need to", "have to", "should"],
            "preference": ["i like", "i prefer", "i don't like", "favorite", "i hate", "always", "never"],
            "event": ["meeting", "appointment", "event", "party", "wedding", "birthday", "holiday"],
            "instruction": ["always", "never", "don't", "make sure", "remember to"],
            "relationship": ["my friend", "my family", "my boss", "my wife", "my husband", "my colleague"],
            "location": ["home", "office", "work", "address", "located", "city", "country"],
        }
        
        logger.info("🧠 JARVIS Long-Term Memory initialized")
    
    def remember(
        self,
        phone: str,
        content: str,
        importance: float = 0.5,
        category: str = None,
        metadata: Dict = None
    ) -> MemoryEntry:
        """
        Store a new memory.
        
        Args:
            phone: User's phone number
            content: Content to remember
            importance: 0-1 importance score
            category: Memory category (auto-detected if not provided)
            metadata: Additional metadata
            
        Returns:
            Created MemoryEntry
        """
        # Auto-detect category if not provided
        if not category:
            category = self._detect_category(content)
        
        # Generate summary
        summary = self._summarize(content)
        
        # Create memory entry
        memory = MemoryEntry(
            id=self._generate_id(phone, content),
            phone=phone,
            content=content,
            summary=summary,
            category=category,
            importance=importance,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )
        
        self.memories[phone].append(memory)
        
        # Update user context
        self._update_user_context(phone, content, category)
        
        # Persist to database if available
        self._persist_memory(memory)
        
        logger.info(f"Memory stored for {phone}: {summary[:50]}...")
        
        return memory
    
    def recall(
        self,
        phone: str,
        query: str = None,
        category: str = None,
        limit: int = 5,
        min_importance: float = 0.0
    ) -> List[MemoryEntry]:
        """
        Recall memories.
        
        Args:
            phone: User's phone number
            query: Search query
            category: Filter by category
            limit: Maximum memories to return
            min_importance: Minimum importance threshold
            
        Returns:
            List of matching memories
        """
        user_memories = self.memories.get(phone, [])
        
        # Filter by category
        if category:
            user_memories = [m for m in user_memories if m.category == category]
        
        # Filter by importance
        user_memories = [m for m in user_memories if m.importance >= min_importance]
        
        # Search by query
        if query:
            query_lower = query.lower()
            scored_memories = []
            for memory in user_memories:
                score = self._calculate_relevance(memory, query_lower)
                if score > 0:
                    scored_memories.append((memory, score))
            
            # Sort by relevance
            scored_memories.sort(key=lambda x: x[1], reverse=True)
            user_memories = [m for m, _ in scored_memories[:limit]]
        else:
            # Sort by recency and importance
            user_memories.sort(key=lambda m: (m.importance, m.timestamp), reverse=True)
            user_memories = user_memories[:limit]
        
        # Update recall counts
        for memory in user_memories:
            memory.recalled_count += 1
            memory.last_recalled = datetime.now()
        
        return user_memories
    
    def recall_context(self, phone: str, current_message: str) -> str:
        """
        Generate contextual memory recall for the current conversation.
        Returns a string that can be injected into the AI prompt.
        """
        context_parts = []
        
        # Get user context
        user_ctx = self.user_contexts.get(phone)
        if user_ctx:
            if user_ctx.name:
                context_parts.append(f"User's name: {user_ctx.name}")
            if user_ctx.preferences:
                prefs = ', '.join(f"{k}: {v}" for k, v in list(user_ctx.preferences.items())[:5])
                context_parts.append(f"Preferences: {prefs}")
            if user_ctx.facts:
                context_parts.append(f"Known facts: {'; '.join(user_ctx.facts[:5])}")
        
        # Recall relevant memories
        relevant = self.recall(phone, query=current_message, limit=3, min_importance=0.3)
        if relevant:
            context_parts.append("\nRelevant memories:")
            for memory in relevant:
                age = (datetime.now() - memory.timestamp).days
                age_str = f"{age}d ago" if age > 0 else "today"
                context_parts.append(f"  - [{memory.category}] {memory.summary} ({age_str})")
        
        # Get recent conversation summary
        summaries = self.conversation_summaries.get(phone, [])
        if summaries:
            recent = summaries[-1]
            context_parts.append(f"\nLast conversation summary: {recent.get('summary', 'N/A')}")
        
        if context_parts:
            return "**User Context from Memory:**\n" + '\n'.join(context_parts)
        return ""
    
    def learn_from_message(self, phone: str, message: str, is_user: bool = True):
        """
        Automatically learn from conversation messages.
        Extracts important information to remember.
        """
        message_lower = message.lower()
        
        # Detect personal information
        if is_user:
            # Name detection
            name_patterns = [
                r"my name is (\w+)",
                r"i'm (\w+)",
                r"call me (\w+)",
            ]
            import re
            for pattern in name_patterns:
                match = re.search(pattern, message_lower)
                if match:
                    name = match.group(1).capitalize()
                    self._update_user_name(phone, name)
                    self.remember(phone, f"User's name is {name}", importance=0.9, category="personal")
            
            # Preference detection
            if any(pref in message_lower for pref in ["i like", "i prefer", "i love", "favorite"]):
                self.remember(phone, message, importance=0.7, category="preference")
            
            # Instruction detection
            if any(inst in message_lower for inst in ["always", "never", "don't", "remember to"]):
                self.remember(phone, message, importance=0.8, category="instruction")
            
            # Location detection
            if any(loc in message_lower for loc in ["i live in", "i'm in", "my address", "located in"]):
                self.remember(phone, message, importance=0.6, category="location")
            
            # Relationship mentions
            if any(rel in message_lower for rel in ["my friend", "my family", "my wife", "my husband", "my boss"]):
                self.remember(phone, message, importance=0.5, category="relationship")
    
    def summarize_conversation(self, phone: str, messages: List[Dict]) -> str:
        """
        Summarize a conversation and store for future reference.
        """
        if not messages:
            return ""
        
        # Create conversation text
        conv_text = '\n'.join([
            f"{'User' if m.get('role') == 'user' else 'Assistant'}: {m.get('content', '')}"
            for m in messages[-20:]  # Last 20 messages
        ])
        
        # Generate summary
        summary = self._ai_summarize_conversation(conv_text)
        
        if summary:
            self.conversation_summaries[phone].append({
                'timestamp': datetime.now().isoformat(),
                'summary': summary,
                'message_count': len(messages)
            })
            
            # Keep only last 30 summaries
            self.conversation_summaries[phone] = self.conversation_summaries[phone][-30:]
        
        return summary
    
    def get_user_profile(self, phone: str) -> Dict[str, Any]:
        """Get complete user profile from memory"""
        ctx = self.user_contexts.get(phone, UserContext(phone=phone))
        memories = self.memories.get(phone, [])
        
        # Categorize memories
        by_category = defaultdict(list)
        for m in memories:
            by_category[m.category].append(m)
        
        return {
            'phone': phone,
            'name': ctx.name,
            'preferences': ctx.preferences,
            'facts': ctx.facts,
            'topics_of_interest': ctx.topics_of_interest,
            'conversation_style': ctx.conversation_style,
            'location': ctx.location,
            'last_interaction': ctx.last_interaction.isoformat() if ctx.last_interaction else None,
            'memory_stats': {
                'total': len(memories),
                'by_category': {cat: len(mems) for cat, mems in by_category.items()},
            },
            'recent_memories': [
                {'summary': m.summary, 'category': m.category, 'timestamp': m.timestamp.isoformat()}
                for m in sorted(memories, key=lambda x: x.timestamp, reverse=True)[:5]
            ]
        }
    
    def forget(self, phone: str, memory_id: str = None, category: str = None) -> int:
        """
        Forget memories.
        
        Args:
            phone: User's phone number
            memory_id: Specific memory to forget
            category: Forget all memories in category
            
        Returns:
            Number of memories forgotten
        """
        if phone not in self.memories:
            return 0
        
        original_count = len(self.memories[phone])
        
        if memory_id:
            self.memories[phone] = [m for m in self.memories[phone] if m.id != memory_id]
        elif category:
            self.memories[phone] = [m for m in self.memories[phone] if m.category != category]
        else:
            self.memories[phone] = []
        
        forgotten = original_count - len(self.memories[phone])
        logger.info(f"Forgot {forgotten} memories for {phone}")
        return forgotten
    
    def _detect_category(self, content: str) -> str:
        """Auto-detect memory category"""
        content_lower = content.lower()
        
        for category, keywords in self.category_keywords.items():
            if any(kw in content_lower for kw in keywords):
                return category
        
        return "topic"  # Default category
    
    def _summarize(self, content: str) -> str:
        """Generate short summary of content"""
        if len(content) <= 100:
            return content
        
        # Try AI summarization
        if AI_AVAILABLE:
            try:
                response = genai_client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=f"Summarize this in 1 short sentence (max 50 words): {content}"
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                logger.warning(f"AI summarization failed: {e}")
        
        # Fallback: truncate
        return content[:97] + "..."
    
    def _ai_summarize_conversation(self, conv_text: str) -> str:
        """AI-powered conversation summarization"""
        if not AI_AVAILABLE:
            return f"Conversation with {len(conv_text.split(chr(10)))} messages"
        
        try:
            response = genai_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"""Summarize this conversation in 2-3 sentences. Focus on:
- Main topics discussed
- Key decisions or outcomes
- Any action items

Conversation:
{conv_text}"""
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            logger.warning(f"Conversation summarization failed: {e}")
        
        return f"Conversation with {len(conv_text.split(chr(10)))} exchanges"
    
    def _calculate_relevance(self, memory: MemoryEntry, query: str) -> float:
        """Calculate relevance score for a memory"""
        score = 0.0
        
        # Content match
        if query in memory.content.lower():
            score += 0.5
        
        # Summary match
        if query in memory.summary.lower():
            score += 0.3
        
        # Word overlap
        query_words = set(query.split())
        content_words = set(memory.content.lower().split())
        overlap = len(query_words & content_words)
        score += overlap * 0.1
        
        # Recency boost (newer memories score higher)
        age_days = (datetime.now() - memory.timestamp).days
        if age_days < 1:
            score += 0.3
        elif age_days < 7:
            score += 0.2
        elif age_days < 30:
            score += 0.1
        
        # Importance boost
        score += memory.importance * 0.2
        
        return score
    
    def _update_user_context(self, phone: str, content: str, category: str):
        """Update user context based on new memory"""
        if phone not in self.user_contexts:
            self.user_contexts[phone] = UserContext(phone=phone)
        
        ctx = self.user_contexts[phone]
        ctx.last_interaction = datetime.now()
        
        # Update topics of interest
        words = content.lower().split()
        for word in words:
            if len(word) > 4:  # Skip short words
                ctx.topics_of_interest[word] = ctx.topics_of_interest.get(word, 0) + 0.1
        
        # Keep top 20 topics
        if len(ctx.topics_of_interest) > 20:
            sorted_topics = sorted(ctx.topics_of_interest.items(), key=lambda x: x[1], reverse=True)
            ctx.topics_of_interest = dict(sorted_topics[:20])
    
    def _update_user_name(self, phone: str, name: str):
        """Update user's name"""
        if phone not in self.user_contexts:
            self.user_contexts[phone] = UserContext(phone=phone)
        self.user_contexts[phone].name = name
        logger.info(f"Learned user name: {name}")
    
    def _generate_id(self, phone: str, content: str) -> str:
        """Generate unique memory ID"""
        data = f"{phone}:{content}:{datetime.now().isoformat()}"
        return hashlib.md5(data.encode()).hexdigest()[:12]
    
    def _persist_memory(self, memory: MemoryEntry):
        """Persist memory to database"""
        if not DB_AVAILABLE or not db_manager:
            return
        
        try:
            # Store as conversation history entry with metadata
            db_manager.add_to_conversation_history(
                memory.phone,
                "memory",
                json.dumps({
                    'id': memory.id,
                    'content': memory.content,
                    'summary': memory.summary,
                    'category': memory.category,
                    'importance': memory.importance,
                    'timestamp': memory.timestamp.isoformat()
                })
            )
        except Exception as e:
            logger.error(f"Failed to persist memory: {e}")


# Global instance
long_term_memory = LongTermMemory()


def remember(phone: str, content: str, importance: float = 0.5) -> str:
    """Convenience function to remember something"""
    memory = long_term_memory.remember(phone, content, importance)
    return f"✅ Remembered: {memory.summary}"


def recall(phone: str, query: str) -> str:
    """Convenience function to recall memories"""
    memories = long_term_memory.recall(phone, query=query, limit=5)
    
    if not memories:
        return "I don't have any memories matching that."
    
    result = ["🧠 **Here's what I remember:**\n"]
    for m in memories:
        age = (datetime.now() - m.timestamp).days
        age_str = f"{age}d ago" if age > 0 else "today"
        result.append(f"• [{m.category}] {m.summary} ({age_str})")
    
    return '\n'.join(result)


def get_context_for_prompt(phone: str, message: str) -> str:
    """Get memory context for AI prompt injection"""
    return long_term_memory.recall_context(phone, message)
