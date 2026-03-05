"""Bytez AI Integration Handler with Function Calling Support.

This module provides AI-powered conversation handling using Bytez's unified API
for 175,000+ AI models including chat, image generation, text-to-speech, and more.

Bytez supports models like:
- Chat: Qwen/Qwen3-4B, microsoft/Phi-3-mini-4k-instruct, DeepSeek models
- Image: dreamlike-art/dreamlike-photoreal-2.0, stability AI models
- Speech: suno/bark-small for text-to-speech
- Vision: google/gemma-3-4b-it for image analysis
"""

import json
import threading
import time
import logging
import os
from typing import Dict, Any, Optional, Callable, List, Union
from functools import wraps
from datetime import datetime
import pytz

try:
    from bytez import Bytez
    BYTEZ_AVAILABLE = True
except ImportError:
    BYTEZ_AVAILABLE = False
    Bytez = None

from config import PERSONALITY_PROMPT
from handlers.spotify import play_album, play_playlist, play_song, get_current_song
from handlers.gmail import send_email, summarize_emails
from handlers.calendar import create_event
from handlers.weather import weather_service
from handlers.news import news_service
from handlers.tasks import task_manager
from handlers.contacts import contact_manager
from handlers.uber import uber_service
from handlers.accommodation import accommodation_service
from handlers.fitness import fitness_service
from handlers.google_notes import google_notes_service
from handlers.daily_briefing import send_briefing_now, schedule_daily_briefing, cancel_daily_briefing
from handlers.expenses import expense_service
from handlers.mood_music import mood_music_service

# Memory search with Gemini dependency - optional
try:
    from handlers.memory_search import memory_service
    MEMORY_SEARCH_AVAILABLE = True
except ImportError:
    MEMORY_SEARCH_AVAILABLE = False
    memory_service = None

from database import add_to_conversation_history, query_conversation_history, retrieve_conversation_history

# Configure logging
logger = logging.getLogger("BytezHandler")

# Environment variables
BYTEZ_API_KEY = os.getenv("BYTEZ_API_KEY")

# Model Configuration - Bytez supports 175k+ models!
# Using the BEST available models for each task

# Chat models (Qwen3 is state-of-the-art)
CHAT_MODEL = os.getenv("BYTEZ_CHAT_MODEL", "openai/gpt-oss-20b")  # Best reasoning, MoE architecture
CHAT_MODEL_FAST = os.getenv("BYTEZ_CHAT_MODEL_FAST", "Qwen/Qwen3-30B-A3B")  # Fast but capable
CHAT_MODEL_FALLBACK = os.getenv("BYTEZ_CHAT_MODEL_FALLBACK", "Qwen/Qwen3-4B")  # Lightweight fallback

# Audio-to-Text model (speech recognition)
AUDIO_MODEL = os.getenv("BYTEZ_AUDIO_MODEL", "Qwen/Qwen2-Audio-7B-Instruct")  # Best audio understanding

# Image generation models (FLUX is state-of-the-art)
IMAGE_MODEL = os.getenv("BYTEZ_IMAGE_MODEL", "black-forest-labs/FLUX.1-dev")  # Best quality
IMAGE_MODEL_FAST = os.getenv("BYTEZ_IMAGE_MODEL_FAST", "black-forest-labs/FLUX.1-schnell")  # Fast generation

# Text-to-Speech model (Bark for natural speech)
TTS_MODEL = os.getenv("BYTEZ_TTS_MODEL", "suno/bark")  # Full bark model for best quality
TTS_MODEL_FAST = os.getenv("BYTEZ_TTS_MODEL_FAST", "suno/bark-small")  # Faster alternative

# Vision/Multimodal models
VISION_MODEL = os.getenv("BYTEZ_VISION_MODEL", "Qwen/Qwen2-VL-72B-Instruct")  # Best vision understanding
VISION_MODEL_FAST = os.getenv("BYTEZ_VISION_MODEL_FAST", "Qwen/Qwen2-VL-7B-Instruct")  # Faster alternative

# Constants
API_TIMEOUT = 60  # seconds - Bytez may need more time for larger models
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds
MAX_CONVERSATION_HISTORY = 10  # messages to include

# Bytez client state
bytez_client: Optional[Bytez] = None


class BytezError(Exception):
    """Base exception for Bytez-related errors."""
    pass


class BytezTimeoutError(BytezError):
    """Raised when Bytez API call times out."""
    pass


class BytezAPIError(BytezError):
    """Raised when Bytez API returns an error."""
    pass


def retry_on_failure(max_retries: int = MAX_RETRIES, delay: float = RETRY_DELAY):
    """Decorator to retry function calls on failure."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))  # Exponential backoff
            raise last_exception
        return wrapper
    return decorator


# Define functions that the AI can call
# Bytez chat models understand function calling through instruction prompting
FUNCTIONS = [
    {
        "name": "play_song",
        "description": "Play a specific song on Spotify",
        "parameters": {"song_name": "string (required)"}
    },
    {
        "name": "play_playlist",
        "description": "Play a Spotify playlist from the user's library",
        "parameters": {"playlist_name": "string (required)"}
    },
    {
        "name": "play_album",
        "description": "Play a Spotify album from the user's library",
        "parameters": {"album_name": "string (required)"}
    },
    {
        "name": "get_current_song",
        "description": "Get the currently playing song on Spotify",
        "parameters": {}
    },
    {
        "name": "send_email",
        "description": "Send an email via Gmail",
        "parameters": {"to": "string (required)", "subject": "string (required)", "body": "string (required)"}
    },
    {
        "name": "summarize_emails",
        "description": "Summarize recent important emails",
        "parameters": {}
    },
    {
        "name": "create_event",
        "description": "Create a Google Calendar event",
        "parameters": {"summary": "string (required)", "start_time": "string (required)", "end_time": "string (required)", "location": "string (optional)", "attendees": "array of emails (optional)"}
    },
    {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {"location": "string (required)"}
    },
    {
        "name": "get_weather_forecast",
        "description": "Get weather forecast for a location",
        "parameters": {"location": "string (required)", "days": "integer 1-5 (optional)"}
    },
    {
        "name": "get_current_time",
        "description": "Get the current date and time",
        "parameters": {}
    },
    {
        "name": "get_news",
        "description": "Get top news headlines",
        "parameters": {"category": "string: general/business/technology/science (optional)", "limit": "integer 1-10 (optional)"}
    },
    {
        "name": "search_news",
        "description": "Search for news about a specific topic",
        "parameters": {"query": "string (required)", "limit": "integer 1-10 (optional)"}
    },
    {
        "name": "create_task",
        "description": "Create a new task or todo item",
        "parameters": {"title": "string (required)", "description": "string (optional)", "due_date": "string YYYY-MM-DD HH:MM (optional)", "priority": "string low/medium/high/urgent (optional)"}
    },
    {
        "name": "list_tasks",
        "description": "List all tasks",
        "parameters": {"filter_completed": "boolean (optional)", "filter_priority": "string (optional)"}
    },
    {
        "name": "complete_task",
        "description": "Mark a task as completed",
        "parameters": {"task_id": "string (required)"}
    },
    {
        "name": "create_reminder",
        "description": "Create a reminder",
        "parameters": {"message": "string (required)", "remind_at": "string YYYY-MM-DD HH:MM (required)"}
    },
    {
        "name": "list_reminders",
        "description": "List all reminders",
        "parameters": {}
    },
    {
        "name": "get_task_summary",
        "description": "Get a summary of tasks and reminders",
        "parameters": {}
    },
    {
        "name": "add_contact",
        "description": "Add a new contact",
        "parameters": {"name": "string (required)", "phone": "string (optional)", "email": "string (optional)"}
    },
    {
        "name": "search_contacts",
        "description": "Search for contacts by name, phone, or email",
        "parameters": {"query": "string (required)"}
    },
    {
        "name": "send_whatsapp_message",
        "description": "Send a WhatsApp message to a contact",
        "parameters": {"contact_query": "string (required)", "message": "string (required)"}
    },
    {
        "name": "search_web",
        "description": "Search the internet for current information",
        "parameters": {"query": "string (required)", "num_results": "integer 1-5 (optional)"}
    },
    {
        "name": "get_calendar_summary",
        "description": "Get a summary of upcoming calendar events",
        "parameters": {"days_ahead": "integer 1-30 (optional)"}
    },
    {
        "name": "toggle_voice_responses",
        "description": "Toggle voice responses on or off",
        "parameters": {}
    },
    {
        "name": "get_daily_briefing",
        "description": "Get a comprehensive daily briefing",
        "parameters": {"location": "string (optional)"}
    },
    {
        "name": "add_expense",
        "description": "Record an expense",
        "parameters": {"amount": "number (required)", "category": "string: food/groceries/transport/entertainment/shopping/utilities/health/other (required)", "description": "string (optional)"}
    },
    {
        "name": "get_spending_report",
        "description": "Get a spending report",
        "parameters": {"days": "integer (optional, default 30)"}
    },
    {
        "name": "play_mood_music",
        "description": "Play music matching a mood",
        "parameters": {"mood": "string: happy/sad/energetic/relaxed/focused/romantic/angry/nostalgic/party (required)"}
    },
    {
        "name": "search_memory",
        "description": "Search past conversations",
        "parameters": {"query": "string (required)"}
    },
    {
        "name": "generate_image",
        "description": "Generate an image from text description",
        "parameters": {"prompt": "string (required)", "style": "string: realistic/artistic/cartoon/professional (optional)"}
    },
    {
        "name": "synthesize_speech",
        "description": "Convert text to speech audio",
        "parameters": {"text": "string (required)"}
    },
    {
        "name": "analyze_image",
        "description": "Analyze an image to describe what it shows",
        "parameters": {"image_url": "string (required)", "question": "string (optional)"}
    }
]


def _build_function_prompt() -> str:
    """Build the function calling instruction prompt for the AI."""
    functions_desc = "\n".join([
        f"- {f['name']}: {f['description']} | Parameters: {json.dumps(f['parameters'])}"
        for f in FUNCTIONS
    ])
    
    return f"""You have access to the following functions. When the user asks you to perform an action, respond with a JSON function call.

AVAILABLE FUNCTIONS:
{functions_desc}

RESPONSE FORMAT:
- For function calls, respond ONLY with: {{"function": "function_name", "parameters": {{"param1": "value1"}}}}
- For regular conversation, respond naturally without JSON.

IMPORTANT:
- Only output JSON when calling a function
- Match function parameters exactly as specified
- If a function is not needed, just respond conversationally
"""


def _initialize_bytez_client() -> None:
    """Initialize the Bytez client."""
    global bytez_client

    if not BYTEZ_AVAILABLE:
        logger.warning("Bytez package not installed - run: pip install bytez")
        bytez_client = None
        return

    if not BYTEZ_API_KEY:
        logger.warning("BYTEZ_API_KEY not configured - AI features disabled")
        bytez_client = None
        return

    try:
        bytez_client = Bytez(BYTEZ_API_KEY)
        logger.info(f"Bytez client initialized with chat model: {CHAT_MODEL}")
    except Exception as e:
        logger.error(f"Failed to initialize Bytez client: {e}")
        bytez_client = None


_initialize_bytez_client()


def _build_conversation_prompt(user_message: str, conversation_history: List[str]) -> List[Dict]:
    """Build the conversation messages for Bytez chat API."""
    # Limit conversation history
    recent_history = conversation_history[-MAX_CONVERSATION_HISTORY:] if conversation_history else []
    history_text = '\n'.join(recent_history) if recent_history else "No previous conversation."
    
    # Personality prompt
    personality = PERSONALITY_PROMPT or "You are Wednesday, a helpful personal assistant with the personality of Jarvis from Iron Man - witty, efficient, and occasionally sarcastic."
    
    # Build messages in chat format
    messages = [
        {
            "role": "system",
            "content": f"""{personality}

{_build_function_prompt()}

IMPORTANT LANGUAGE RULE: Detect the language of the user's message and ALWAYS respond in the SAME language. If they write in Spanish, respond in Spanish. If they write in Zulu, respond in Zulu.

Recent Conversation Context:
{history_text}"""
        },
        {
            "role": "user",
            "content": user_message
        }
    ]
    
    return messages


def _parse_function_call(response_text: str) -> Optional[Dict]:
    """Parse a function call from the AI response."""
    try:
        # Try to extract JSON from the response
        text = response_text.strip()
        
        # Look for JSON pattern
        if text.startswith("{") and "function" in text:
            # Find the JSON object
            brace_count = 0
            json_end = 0
            for i, char in enumerate(text):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break
            
            json_str = text[:json_end]
            data = json.loads(json_str)
            
            if "function" in data:
                return {
                    "name": data["function"],
                    "parameters": data.get("parameters", {}),
                    "type": "function_call"
                }
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.debug(f"Response is not a function call: {e}")
    
    return None


@retry_on_failure(max_retries=MAX_RETRIES)
def _make_chat_request(messages: List[Dict], model: str = None, stream: bool = False) -> str:
    """Make a chat request to Bytez API."""
    if bytez_client is None:
        raise BytezAPIError("Bytez client not initialized")
    
    model_id = model or CHAT_MODEL
    chat_model = bytez_client.model(model_id)
    
    params = {
        "temperature": 0.7,
        "max_new_tokens": 1024
    }
    
    if stream:
        # Streaming response
        stream_response = chat_model.run(messages, params, stream=True)
        text = ""
        for chunk in stream_response:
            text += chunk
        return text
    else:
        # Non-streaming response
        result = chat_model.run(messages, params)
        
        if result.error:
            raise BytezAPIError(f"Bytez API error: {result.error}")
        
        # Handle different response formats
        output = result.output
        if isinstance(output, dict):
            # Chat model response format
            return output.get("content", str(output))
        elif isinstance(output, str):
            return output
        else:
            return str(output)


def chat_with_functions(user_message: str, phone: str) -> dict:
    """
    Handle conversation with Bytez AI, including function calling.
    
    Args:
        user_message: The user's input message
        phone: The user's phone identifier for conversation history
        
    Returns:
        dict: Either a function call dict with 'name' and 'parameters', 
              or a response dict with 'name'=None and 'content'
    """
    if bytez_client is None:
        logger.error("Bytez client not initialized - check BYTEZ_API_KEY")
        return {"name": None, "content": "Sorry, AI features are currently unavailable. Please configure BYTEZ_API_KEY."}

    # Retrieve conversation history
    try:
        conversation_history = retrieve_conversation_history(phone)
    except Exception as e:
        logger.warning(f"Could not retrieve conversation history: {e}")
        conversation_history = []

    # Build the conversation
    messages = _build_conversation_prompt(user_message, conversation_history)
    
    try:
        # Make the API call
        response_text = _make_chat_request(messages)
        
        # Check if it's a function call
        function_call = _parse_function_call(response_text)
        if function_call:
            log_content = f"Function call: {function_call['name']}({function_call.get('parameters', {})})"
            add_to_conversation_history(phone, "user", user_message)
            add_to_conversation_history(phone, "assistant", log_content)
            return function_call
        
        # Regular text response
        add_to_conversation_history(phone, "user", user_message)
        add_to_conversation_history(phone, "assistant", response_text)
        
        return {"name": None, "content": response_text, "type": "text"}
        
    except Exception as e:
        error_msg = f"Sorry, I encountered an error: {str(e)}"
        logger.error(f"Chat error: {e}")
        add_to_conversation_history(phone, "user", user_message)
        add_to_conversation_history(phone, "assistant", error_msg)
        return {"name": None, "content": error_msg, "type": "error"}


def execute_function(call: dict, phone: str = "") -> str:
    """
    Execute a function called by the AI.
    
    Args:
        call: Dict containing 'name' and 'parameters' of the function to execute
        phone: The user's phone identifier for context
        
    Returns:
        str: The result of the function execution
    """
    name = call.get("name")
    params = call.get("parameters", {})
    
    if not name:
        return "No function specified."
    
    logger.info(f"Executing function: {name} with params: {params}")
    
    try:
        # Spotify functions
        if name == "play_song":
            return play_song(params.get("song_name", ""))
        if name == "get_current_song":
            return get_current_song()
        if name == "play_playlist":
            return play_playlist(params.get("playlist_name", ""))
        if name == "play_album":
            return play_album(params.get("album_name", ""))
        
        # Gmail functions
        if name == "send_email":
            return send_email(params.get("to", ""), params.get("subject", ""), params.get("body", ""))
        if name == "summarize_emails":
            return summarize_emails()
        
        # Calendar functions
        if name == "create_event":
            return create_event(
                summary=params.get("summary", "Untitled"),
                start_time=params.get("start_time", ""),
                end_time=params.get("end_time", ""),
                description=params.get("description", ""),
                location=params.get("location", ""),
                attendees=params.get("attendees", [])
            )
        
        # Weather functions
        if name == "get_weather":
            return weather_service.get_current_weather(params.get("location", ""))
        if name == "get_weather_forecast":
            return weather_service.get_weather_forecast(
                params.get("location", ""), 
                params.get("days", 3)
            )
        
        # Time function
        if name == "get_current_time":
            now = datetime.now()
            utc_now = datetime.now(pytz.UTC)
            local_tz = pytz.timezone(os.getenv("TIMEZONE", "Africa/Johannesburg"))
            local_now = datetime.now(local_tz)
            return f"🕐 Current time:\n• Local: {local_now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n• UTC: {utc_now.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        
        # News functions
        if name == "get_news":
            category = params.get("category")
            limit = params.get("limit", 5)
            if category == "business":
                return news_service.get_business_news(limit)
            elif category == "technology":
                return news_service.get_technology_news(limit)
            elif category == "science":
                return news_service.get_science_news(limit)
            else:
                return news_service.get_top_headlines(limit=limit)
        
        if name == "search_news":
            return news_service.search_news(params.get("query", ""), params.get("limit", 5))
        
        # Task management functions
        if name == "create_task":
            return task_manager.create_task(
                params.get("title", ""),
                params.get("description", ""),
                params.get("due_date"),
                params.get("priority", "medium")
            )
        
        if name == "list_tasks":
            return task_manager.list_tasks(
                params.get("filter_completed", False),
                params.get("filter_priority")
            )
        
        if name == "complete_task":
            return task_manager.complete_task(params.get("task_id", ""))
        
        if name == "create_reminder":
            return task_manager.create_reminder(
                params.get("message", ""),
                params.get("remind_at", "")
            )
        
        if name == "list_reminders":
            return task_manager.list_reminders()
        
        if name == "get_task_summary":
            return task_manager.get_task_summary()
        
        # Contact management functions
        if name == "add_contact":
            return contact_manager.add_local_contact(
                params.get("name", ""),
                params.get("phone"),
                params.get("email"),
                params.get("notes")
            )
        
        if name == "search_contacts":
            return contact_manager.search_all_contacts(params.get("query", ""))
        
        # Voice functions
        if name == "toggle_voice_responses":
            from handlers.speech import toggle_user_voice_preference
            return toggle_user_voice_preference(phone)
        
        # Daily briefing
        if name == "get_daily_briefing":
            return send_briefing_now(params.get("location", "Johannesburg"))
        
        # Expense tracking
        if name == "add_expense":
            return expense_service.add_expense(
                params.get("amount", 0),
                params.get("category", "other"),
                params.get("description", "")
            )
        
        if name == "get_spending_report":
            return expense_service.get_spending_report(params.get("days", 30))
        
        # Mood music
        if name == "play_mood_music":
            return mood_music_service.play_mood_music(params.get("mood", "relaxed"))
        
        # Memory search (requires Gemini - optional)
        if name == "search_memory":
            if MEMORY_SEARCH_AVAILABLE and memory_service:
                return memory_service.search_memory(phone, params.get("query", ""))
            return "Memory search not available (requires Gemini SDK)"
        
        # Image generation using Bytez
        if name == "generate_image":
            return generate_image(params.get("prompt", ""), params.get("style", "realistic"))
        
        # Text-to-speech using Bytez
        if name == "synthesize_speech":
            return synthesize_speech(params.get("text", ""))
        
        # Image analysis using Bytez
        if name == "analyze_image":
            return analyze_image(params.get("image_url", ""), params.get("question"))
        
        # Calendar summary
        if name == "get_calendar_summary":
            from handlers.calendar import get_upcoming_events
            events = get_upcoming_events(params.get("days_ahead", 7))
            return events if events else "No upcoming events found."
        
        # WhatsApp message
        if name == "send_whatsapp_message":
            contact = contact_manager.search_all_contacts(params.get("contact_query", ""))
            if "not found" in contact.lower():
                return f"Could not find contact: {params.get('contact_query')}"
            # Extract phone number and send
            return f"Message prepared for: {params.get('contact_query')}\nMessage: {params.get('message', '')}\n(WhatsApp sending requires WAHA integration)"
        
        # Web search
        if name == "search_web":
            from handlers.search import web_search
            return web_search(params.get("query", ""), params.get("num_results", 3))
        
        return f"Function '{name}' not implemented yet."
        
    except Exception as e:
        logger.error(f"Function execution error for {name}: {e}")
        return f"Error executing {name}: {str(e)}"


# ========== BYTEZ-POWERED AI FEATURES ==========

def generate_image(prompt: str, style: str = "realistic") -> str:
    """
    Generate an image using Bytez's text-to-image models.
    
    Args:
        prompt: Description of the image to generate
        style: Image style (realistic, artistic, cartoon, professional)
    
    Returns:
        str: URL to the generated image or error message
    """
    if bytez_client is None:
        return "Image generation unavailable - Bytez not configured"
    
    try:
        model = bytez_client.model(IMAGE_MODEL)
        
        # Enhance prompt based on style
        style_prompts = {
            "realistic": "highly detailed, photorealistic, 8k",
            "artistic": "artistic, oil painting style, vibrant colors",
            "cartoon": "cartoon style, animated, colorful",
            "professional": "professional quality, clean, corporate"
        }
        
        enhanced_prompt = f"{prompt}, {style_prompts.get(style, style_prompts['realistic'])}"
        
        result = model.run(enhanced_prompt)
        
        if result.error:
            return f"Image generation failed: {result.error}"
        
        # Bytez returns a URL to the generated image
        image_url = result.output
        return f"🎨 Image generated!\n{image_url}"
        
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return f"Image generation failed: {str(e)}"


def synthesize_speech(text: str, fast: bool = False) -> str:
    """
    Convert text to speech using Bytez's TTS models.
    
    Args:
        text: Text to convert to speech
        fast: Use faster model if True
    
    Returns:
        str: URL to the audio file or error message
    """
    if bytez_client is None:
        return "Speech synthesis unavailable - Bytez not configured"
    
    try:
        model_name = TTS_MODEL_FAST if fast else TTS_MODEL
        model = bytez_client.model(model_name)
        result = model.run(text)
        
        if result.error:
            return f"Speech synthesis failed: {result.error}"
        
        # Bytez returns a URL to the audio file
        audio_url = result.output
        return f"🔊 Speech generated!\n{audio_url}"
        
    except Exception as e:
        logger.error(f"Speech synthesis error: {e}")
        return f"Speech synthesis failed: {str(e)}"


def transcribe_audio(audio_input: str, prompt: str = None) -> str:
    """
    Transcribe audio to text using Bytez's Qwen2-Audio model.
    Supports audio-text-to-text for contextual understanding.
    
    Args:
        audio_input: URL to audio file or base64 encoded audio
        prompt: Optional prompt for context (e.g., "Transcribe this voice message")
    
    Returns:
        str: Transcribed text from the audio
    """
    if bytez_client is None:
        return None  # Return None to allow fallback to other STT methods
    
    try:
        model = bytez_client.model(AUDIO_MODEL)
        
        # Build multimodal input for audio-text-to-text
        prompt_text = prompt or "Transcribe this audio message accurately. If it's a voice message, capture the speaker's words and intent."
        
        input_content = [
            {
                "role": "user", 
                "content": [
                    {
                        "type": "text",
                        "text": prompt_text
                    },
                    {
                        "type": "audio",
                        "url": audio_input
                    }
                ]
            }
        ]
        
        result = model.run(input_content)
        
        if result.error:
            logger.error(f"Audio transcription failed: {result.error}")
            return None
        
        # Extract transcription from response
        transcription = result.output
        if isinstance(transcription, dict):
            transcription = transcription.get("text", str(transcription))
        
        logger.info(f"Bytez audio transcription: {transcription}")
        return str(transcription).strip()
        
    except Exception as e:
        logger.error(f"Audio transcription error: {e}")
        return None


def audio_to_audio(audio_input: str, instruction: str = None) -> str:
    """
    Process audio and generate audio response (audio-to-audio).
    Uses Qwen2-Audio for understanding and TTS for response.
    
    Args:
        audio_input: URL to audio file
        instruction: Optional instruction for how to respond
    
    Returns:
        str: URL to the response audio or error message
    """
    if bytez_client is None:
        return "Audio processing unavailable - Bytez not configured"
    
    try:
        # First, understand the audio input
        audio_model = bytez_client.model(AUDIO_MODEL)
        
        prompt = instruction or "Listen to this audio and provide a helpful, conversational response."
        
        input_content = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text", 
                        "text": prompt
                    },
                    {
                        "type": "audio",
                        "url": audio_input
                    }
                ]
            }
        ]
        
        result = audio_model.run(input_content)
        
        if result.error:
            return f"Audio processing failed: {result.error}"
        
        # Get the text response
        response_text = result.output
        if isinstance(response_text, dict):
            response_text = response_text.get("text", str(response_text))
        
        # Convert response to speech
        tts_model = bytez_client.model(TTS_MODEL_FAST)
        audio_result = tts_model.run(str(response_text))
        
        if audio_result.error:
            # Return text if TTS fails
            return f"📝 {response_text}"
        
        return f"🔊 {audio_result.output}"
        
    except Exception as e:
        logger.error(f"Audio-to-audio error: {e}")
        return f"Audio processing failed: {str(e)}"


def analyze_image(image_url: str, question: str = None) -> str:
    """
    Analyze an image using Bytez's vision models.
    
    Args:
        image_url: URL of the image to analyze
        question: Optional specific question about the image
    
    Returns:
        str: Description or analysis of the image
    """
    if bytez_client is None:
        return "Image analysis unavailable - Bytez not configured"
    
    try:
        model = bytez_client.model(VISION_MODEL)
        
        # Build multimodal input
        input_content = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": question or "Describe this image in detail. What do you see?"
                    },
                    {
                        "type": "image",
                        "url": image_url
                    }
                ]
            }
        ]
        
        result = model.run(input_content)
        
        if result.error:
            return f"Image analysis failed: {result.error}"
        
        # Extract the description
        output = result.output
        if isinstance(output, dict):
            return output.get("content", str(output))
        return str(output)
        
    except Exception as e:
        logger.error(f"Image analysis error: {e}")
        return f"Image analysis failed: {str(e)}"


def list_available_models() -> str:
    """List some of the available Bytez models."""
    if bytez_client is None:
        return "Bytez not configured"
    
    try:
        result = bytez_client.list.models()
        if result.error:
            return f"Could not list models: {result.error}"
        
        models = result.output[:20]  # First 20 models
        model_list = "\n".join([f"• {m.get('id', 'Unknown')}" for m in models])
        return f"🤖 Available Bytez Models (showing 20 of 175,000+):\n{model_list}"
        
    except Exception as e:
        return f"Error listing models: {e}"


# ========== STREAMING CHAT ==========

def chat_with_streaming(user_message: str, phone: str) -> str:
    """
    Stream a chat response from Bytez.
    Useful for real-time responses in supported interfaces.
    """
    if bytez_client is None:
        return "Bytez not configured"
    
    try:
        conversation_history = retrieve_conversation_history(phone)
        messages = _build_conversation_prompt(user_message, conversation_history)
        
        model = bytez_client.model(CHAT_MODEL)
        params = {"temperature": 0.7, "max_new_tokens": 1024}
        
        stream = model.run(messages, params, stream=True)
        
        full_response = ""
        for chunk in stream:
            full_response += chunk
            # In a real application, you'd yield chunks here
        
        add_to_conversation_history(phone, "user", user_message)
        add_to_conversation_history(phone, "assistant", full_response)
        
        return full_response
        
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        return f"Error: {e}"


# ========== UTILITY FUNCTIONS ==========

def get_bytez_status() -> Dict[str, Any]:
    """Get the current status of Bytez integration."""
    return {
        "available": BYTEZ_AVAILABLE,
        "configured": bytez_client is not None,
        "chat_model": CHAT_MODEL,
        "chat_model_fast": CHAT_MODEL_FAST,
        "audio_model": AUDIO_MODEL,
        "image_model": IMAGE_MODEL,
        "image_model_fast": IMAGE_MODEL_FAST,
        "tts_model": TTS_MODEL,
        "tts_model_fast": TTS_MODEL_FAST,
        "vision_model": VISION_MODEL,
        "vision_model_fast": VISION_MODEL_FAST,
        "api_key_set": bool(BYTEZ_API_KEY)
    }


def reinitialize_client() -> bool:
    """Reinitialize the Bytez client (useful after config changes)."""
    global bytez_client
    _initialize_bytez_client()
    return bytez_client is not None
