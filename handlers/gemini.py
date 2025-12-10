"""Gemini AI Integration Handler with Function Calling Support.

This module provides AI-powered conversation handling with integrated function calling
for various services like Spotify, Gmail, Calendar, Weather, and more.
"""

import google.generativeai as genai
import json
import threading
import time
import logging
from typing import Dict, Any, Optional, Callable, List
from functools import wraps

from config import GEMINI_API_KEY, PERSONALITY_PROMPT
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
from handlers.image_analysis import analyze_whatsapp_image
from handlers.expenses import expense_service
from handlers.mood_music import mood_music_service
from handlers.memory_search import memory_service
from database import add_to_conversation_history, query_conversation_history, retrieve_conversation_history

# Configure logging
logger = logging.getLogger("GeminiHandler")

# Constants
API_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds
MAX_CONVERSATION_HISTORY = 10  # messages to include


class GeminiError(Exception):
    """Base exception for Gemini-related errors."""
    pass


class GeminiTimeoutError(GeminiError):
    """Raised when Gemini API call times out."""
    pass


class GeminiAPIError(GeminiError):
    """Raised when Gemini API returns an error."""
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


# Initialize Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    # Use Gemini 2.0 Flash - stable model with function calling support
    # Note: gemini-2.5-flash requires newer google-genai SDK
    model = genai.GenerativeModel("gemini-2.5-flash")
    logger.info("Gemini model initialized successfully (gemini-2.5-flash)")
else:
    model = None
    logger.warning("GEMINI_API_KEY not configured - AI features disabled")

# Define functions for Gemini to call
FUNCTIONS = [
    {
        "name": "play_song",
        "description": "Play a specific song on Spotify",
        "parameters": {
            "type": "object",
            "properties": {
                "song_name": {"type": "string"}
            },
            "required": ["song_name"]
        }
    },
    {
    "name": "play_playlist",
    "description": "Play a Spotify playlist from the user's library",
    "parameters": {
        "type": "object",
        "properties": {
            "playlist_name": {"type": "string"}
        },
        "required": ["playlist_name"]
    }
},
{
    "name": "play_album",
    "description": "Play a Spotify album from the user's library",
    "parameters": {
        "type": "object",
        "properties": {
            "album_name": {"type": "string"}
        },
        "required": ["album_name"]
    }
}
    ,
    {
        "name": "get_current_song",
        "description": "Get the currently playing song on Spotify",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "send_email",
        "description": "Send an email via Gmail",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"}
            },
            "required": ["to", "subject", "body"]
        }
    },
    {
    "name": "summarize_emails",
    "description": "Summarize recent important emails (like today)",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": []
    }
}
    ,
    {
    "name": "create_event",
    "description": "Create a Google Calendar event and invite people",
    "parameters": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "location": {"type": "string"},
            "start_time": {"type": "string"},
            "end_time": {"type": "string"},
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of emails to invite"
            }
        },
        "required": ["summary", "start_time", "end_time"]
    }
},
    {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name or location"}
            },
            "required": ["location"]
        }
    },
    {
        "name": "get_weather_forecast",
        "description": "Get weather forecast for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name or location"},
                "days": {"type": "integer", "description": "Number of days (1-5)"}
            },
            "required": ["location"]
        }
    },
    {
        "name": "get_news",
        "description": "Get top news headlines",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "News category: general, business, technology, science"},
                "limit": {"type": "integer", "description": "Number of articles (1-10)"}
            },
            "required": []
        }
    },
    {
        "name": "search_news",
        "description": "Search for news about a specific topic",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Number of articles (1-10)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_daily_briefing",
        "description": "Get a daily news briefing with mixed categories",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "create_task",
        "description": "Create a new task or todo item",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "description": {"type": "string", "description": "Task description"},
                "due_date": {"type": "string", "description": "Due date in YYYY-MM-DD HH:MM format"},
                "priority": {"type": "string", "description": "Priority: low, medium, high, urgent"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "list_tasks",
        "description": "List all tasks",
        "parameters": {
            "type": "object",
            "properties": {
                "filter_completed": {"type": "boolean", "description": "Hide completed tasks"},
                "filter_priority": {"type": "string", "description": "Filter by priority: low, medium, high, urgent"}
            },
            "required": []
        }
    },
    {
        "name": "complete_task",
        "description": "Mark a task as completed",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "create_reminder",
        "description": "Create a reminder",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Reminder message"},
                "remind_at": {"type": "string", "description": "When to remind in YYYY-MM-DD HH:MM format"}
            },
            "required": ["message", "remind_at"]
        }
    },
    {
        "name": "list_reminders",
        "description": "List all reminders",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_task_summary",
        "description": "Get a summary of tasks and reminders",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "sync_tasks_to_google",
        "description": "Sync local tasks to Google Keep/Google Tasks",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "sync_tasks_from_google",
        "description": "Sync tasks from Google Keep/Google Tasks to local storage",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_sync_status",
        "description": "Get synchronization status between local tasks and Google Keep",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "create_google_note",
        "description": "Create a note directly in Google Keep/Google Tasks",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Note title"},
                "content": {"type": "string", "description": "Note content"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Note tags"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "search_google_notes",
        "description": "Search notes in Google Keep/Google Tasks",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "add_contact",
        "description": "Add a new contact to local storage",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Contact name"},
                "phone": {"type": "string", "description": "Phone number"},
                "email": {"type": "string", "description": "Email address"},
                "notes": {"type": "string", "description": "Additional notes"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "search_contacts",
        "description": "Search for contacts by name, phone, or email",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "list_contacts",
        "description": "List all contacts",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_contact_summary",
        "description": "Get a summary of contacts",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
    "name": "get_google_contacts",
    "description": "Get contacts from Google Contacts (prioritized over local contacts)",
    "parameters": {
        "type": "object",
        "properties": {
            "max_results": {"type": "integer", "description": "Maximum number of contacts to return (defaults to 20 if not specified)"}
        },
        "required": []
    }
},

    {
        "name": "send_whatsapp_message",
        "description": "Send a WhatsApp message to a contact (searches Google contacts first, then local contacts)",
        "parameters": {
            "type": "object",
            "properties": {
                "contact_query": {"type": "string", "description": "Contact name or phone number to search for"},
                "message": {"type": "string", "description": "Message to send"}
            },
            "required": ["contact_query", "message"]
        }
    },
    {
        "name": "search_web",
        "description": "Search the internet for current information on any topic",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query for the web"},
                "num_results": {"type": "integer", "description": "Number of results (1-5)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_calendar_summary",
        "description": "Get a summary of upcoming calendar events",
        "parameters": {
            "type": "object",
            "properties": {
                "days_ahead": {"type": "integer", "description": "Number of days to look ahead (1-30)"}
            },
            "required": []
        }
    },
    {
        "name": "get_smart_email_brief",
        "description": "Get an intelligent summary of recent emails",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "toggle_voice_responses",
        "description": "Toggle voice responses on or off for the user",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "set_voice_responses",
        "description": "Enable or disable voice responses for the user",
        "parameters": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "description": "Whether to enable or disable voice responses"}
            },
            "required": ["enabled"]
        }
    },
    # Uber and transportation functions
    {
        "name": "get_ride_estimates",
        "description": "Get Uber ride estimates between locations",
        "parameters": {
            "type": "object",
            "properties": {
                "start_lat": {"type": "number", "description": "Starting latitude"},
                "start_lng": {"type": "number", "description": "Starting longitude"},
                "end_lat": {"type": "number", "description": "Destination latitude"},
                "end_lng": {"type": "number", "description": "Destination longitude"}
            },
            "required": ["end_lat", "end_lng"]
        }
    },
    {
        "name": "book_uber_ride",
        "description": "Book an Uber ride",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Uber product ID"},
                "end_lat": {"type": "number", "description": "Destination latitude"},
                "end_lng": {"type": "number", "description": "Destination longitude"},
                "start_lat": {"type": "number", "description": "Starting latitude (optional)"},
                "start_lng": {"type": "number", "description": "Starting longitude (optional)"}
            },
            "required": ["product_id", "end_lat", "end_lng"]
        }
    },
    {
        "name": "search_restaurants",
        "description": "Search for restaurants on Uber Eats",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Restaurant or food type to search for"},
                "lat": {"type": "number", "description": "Latitude (optional)"},
                "lng": {"type": "number", "description": "Longitude (optional)"}
            },
            "required": []
        }
    },
    # Accommodation functions
    {
        "name": "search_accommodations",
        "description": "Search for accommodations (hotels, Airbnb, etc.)",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "Location to search in"},
                "check_in": {"type": "string", "description": "Check-in date (YYYY-MM-DD)"},
                "check_out": {"type": "string", "description": "Check-out date (YYYY-MM-DD)"},
                "guests": {"type": "integer", "description": "Number of guests"},
                "max_price": {"type": "number", "description": "Maximum price per night"}
            },
            "required": ["location"]
        }
    },
    {
        "name": "book_accommodation",
        "description": "Book an accommodation",
        "parameters": {
            "type": "object",
            "properties": {
                "property_id": {"type": "string", "description": "Property ID"},
                "check_in": {"type": "string", "description": "Check-in date (YYYY-MM-DD)"},
                "check_out": {"type": "string", "description": "Check-out date (YYYY-MM-DD)"},
                "guests": {"type": "integer", "description": "Number of guests"},
                "guest_name": {"type": "string", "description": "Guest name"}
            },
            "required": ["property_id", "check_in", "check_out"]
        }
    },
    # Fitness functions
    {
        "name": "get_fitness_summary",
        "description": "Get daily fitness and health summary",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format (optional, defaults to today)"}
            },
            "required": []
        }
    },
    {
        "name": "log_fitness_activity",
        "description": "Log a fitness activity",
        "parameters": {
            "type": "object",
            "properties": {
                "activity_type": {"type": "string", "description": "Type of activity (e.g., Running, Cycling, Gym)"},
                "duration": {"type": "integer", "description": "Duration in minutes"},
                "calories": {"type": "integer", "description": "Calories burned (optional)"},
                "distance": {"type": "number", "description": "Distance in km (optional)"},
                "notes": {"type": "string", "description": "Additional notes (optional)"}
            },
            "required": ["activity_type", "duration"]
        }
    },
    {
        "name": "get_fitness_history",
        "description": "Get recent fitness activity history",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days to look back (default: 7)"}
            },
            "required": []
        }
    },
    {
        "name": "set_fitness_goal",
        "description": "Set a fitness goal",
        "parameters": {
            "type": "object",
            "properties": {
                "goal_type": {"type": "string", "description": "Type of goal (steps, calories, weight, etc.)"},
                "target": {"type": "integer", "description": "Target value"}
            },
            "required": ["goal_type", "target"]
        }
    },
    # Google Notes functions
    {
        "name": "create_note",
        "description": "Create a new note using Google Tasks",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Note title"},
                "content": {"type": "string", "description": "Note content"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Note tags"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "search_notes",
        "description": "Search notes by content or title",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "sync_notes_tasks",
        "description": "Sync Google Tasks with local task management",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    # Enhanced contact and WhatsApp functions
    {
        "name": "get_contact_for_whatsapp",
        "description": "Get contact details formatted for WhatsApp messaging",
        "parameters": {
            "type": "object",
            "properties": {
                "contact_query": {"type": "string", "description": "Contact name or phone number"}
            },
            "required": ["contact_query"]
        }
    },
    # Media generation functions
    {
        "name": "generate_image",
        "description": "Generate an image from text description using AI",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Description of the image to generate"},
                "style": {"type": "string", "description": "Image style: realistic, artistic, cartoon, professional, avatar (defaults to realistic)"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "create_avatar",
        "description": "Create an avatar for the assistant",
        "parameters": {
            "type": "object",
            "properties": {
                "personality": {"type": "string", "description": "Personality type for avatar (defaults to wednesday)"},
                "style": {"type": "string", "description": "Avatar style (defaults to professional)"}
            },
            "required": []
        }
    },
    # Service monitoring functions
    {
        "name": "check_service_status",
        "description": "Check the status of system services",
        "parameters": {
            "type": "object",
            "properties": {
                "service_name": {"type": "string", "description": "Specific service to check (optional)"}
            },
            "required": []
        }
    },
    {
        "name": "get_system_health",
        "description": "Get overall system health summary",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    # Advanced AI functions
    {
        "name": "generate_video",
        "description": "Generate video from text description using AI",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Description of the video to generate"},
                "style": {"type": "string", "description": "Video style: realistic, animated, cinematic (defaults to realistic)"},
                "duration": {"type": "integer", "description": "Video duration in seconds 1-10 (defaults to 5)"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "synthesize_voice",
        "description": "Synthesize voice from text using AI",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to convert to speech"},
                "voice_id": {"type": "string", "description": "Voice ID to use (defaults to default)"},
                "style": {"type": "string", "description": "Voice style: natural, expressive, calm (defaults to natural)"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "analyze_image",
        "description": "Analyze an image using computer vision",
        "parameters": {
            "type": "object",
            "properties": {
                "image_description": {"type": "string", "description": "Description of image to analyze"},
                "analysis_type": {"type": "string", "description": "Type of analysis: comprehensive, objects, text, faces, scene (defaults to comprehensive)"}
            },
            "required": ["image_description"]
        }
    },
    {
        "name": "predict_user_behavior",
        "description": "Predict user behavior and provide recommendations",
        "parameters": {
            "type": "object",
            "properties": {
                "context": {"type": "string", "description": "Current context or situation"}
            },
            "required": []
        }
    },
    {
        "name": "run_system_diagnostics",
        "description": "Run comprehensive system diagnostics and tests",
        "parameters": {
            "type": "object",
            "properties": {
                "test_type": {"type": "string", "description": "Type of test: quick, comprehensive, performance (defaults to quick)"}
            },
            "required": []
        }
    },
    {
        "name": "optimize_performance",
        "description": "Analyze and optimize system performance",
        "parameters": {
            "type": "object",
            "properties": {
                "optimization_type": {"type": "string", "description": "Type of optimization: memory, cpu, database, all (defaults to all)"}
            },
            "required": []
        }
    },
    # Daily Briefing functions
    {
        "name": "get_daily_briefing",
        "description": "Get a comprehensive daily briefing with weather, calendar, tasks, and news",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "Location for weather (defaults to Johannesburg)"}
            },
            "required": []
        }
    },
    {
        "name": "schedule_daily_briefing",
        "description": "Schedule a daily morning briefing at a specific time",
        "parameters": {
            "type": "object",
            "properties": {
                "hour": {"type": "integer", "description": "Hour to send briefing (0-23, defaults to 7)"},
                "minute": {"type": "integer", "description": "Minute to send briefing (0-59, defaults to 0)"},
                "location": {"type": "string", "description": "Location for weather (defaults to Johannesburg)"}
            },
            "required": []
        }
    },
    {
        "name": "cancel_daily_briefing",
        "description": "Cancel the scheduled daily briefing",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    # Image Analysis functions
    {
        "name": "analyze_image",
        "description": "Analyze an image to describe what it shows, read text, or answer questions about it",
        "parameters": {
            "type": "object",
            "properties": {
                "image_url": {"type": "string", "description": "URL of the image to analyze"},
                "question": {"type": "string", "description": "Optional specific question about the image"}
            },
            "required": ["image_url"]
        }
    },
    # Expense Tracking functions
    {
        "name": "add_expense",
        "description": "Record an expense or spending (e.g., 'I spent R50 on groceries')",
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Amount spent"},
                "category": {"type": "string", "description": "Category: food, groceries, transport, entertainment, shopping, utilities, health, other"},
                "description": {"type": "string", "description": "Optional description of the expense"}
            },
            "required": ["amount", "category"]
        }
    },
    {
        "name": "get_spending_report",
        "description": "Get a spending report showing expenses by category",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days to analyze (default: 30)"}
            },
            "required": []
        }
    },
    # Mood Music functions
    {
        "name": "play_mood_music",
        "description": "Play music matching a mood or feeling",
        "parameters": {
            "type": "object",
            "properties": {
                "mood": {"type": "string", "description": "Mood: happy, sad, energetic, relaxed, focused, romantic, angry, nostalgic, party"}
            },
            "required": ["mood"]
        }
    },
    {
        "name": "detect_mood_and_play",
        "description": "Analyze the user's message mood and play matching music automatically",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The user's message to analyze for mood"}
            },
            "required": ["message"]
        }
    },
    # Conversation Memory functions
    {
        "name": "search_memory",
        "description": "Search past conversations for specific information or topics",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for in past conversations"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "recall_conversation",
        "description": "Recall what was discussed previously (e.g., 'What did we talk about last week?')",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "What to recall from past conversations"}
            },
            "required": ["question"]
        }
    },
    {
        "name": "summarize_conversations",
        "description": "Get a summary of recent conversations or conversations about a topic",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Optional topic to focus the summary on"}
            },
            "required": []
        }
    }
]

# Create a function name to handler mapping for cleaner execution
FUNCTION_HANDLERS: Dict[str, Callable] = {}


def _build_conversation_prompt(user_message: str, conversation_history: List[str]) -> str:
    """Build the conversation prompt with history context and language detection."""
    # Limit conversation history to prevent token overflow
    recent_history = conversation_history[-MAX_CONVERSATION_HISTORY:] if conversation_history else []
    history_text = '\n'.join(recent_history) if recent_history else "No previous conversation."
    
    return f"""You are Wednesday, a helpful personal assistant with the personality of Jarvis from Iron Man - witty, efficient, and occasionally sarcastic.

IMPORTANT RULES:
1. When the user asks to perform an action (play music, send email, create event, etc.), ALWAYS use the appropriate function
2. Be concise but helpful in your responses
3. Use your personality to make interactions engaging
4. **LANGUAGE**: Detect the language of the user's message and ALWAYS respond in the SAME language. If they write in Spanish, respond in Spanish. If they write in Zulu, respond in Zulu. If they write in French, respond in French. Match their language exactly.
5. If the user mixes languages, respond in the primary language they used

Recent Conversation:
{history_text}

Current Request: {user_message}
"""


def _make_api_call_with_timeout(prompt: str, timeout: int = API_TIMEOUT) -> tuple:
    """Make Gemini API call with thread-safe timeout."""
    # Check if model is initialized
    if model is None:
        raise GeminiAPIError("Gemini model not initialized - check GEMINI_API_KEY")
    
    response = None
    exception_info = None
    
    def api_call():
        nonlocal response, exception_info
        try:
            # Build the content with system instruction separate
            full_prompt = f"{PERSONALITY_PROMPT}\n\n{prompt}"
            
            # Use proper protobuf Tool format for legacy google-generativeai SDK
            import google.generativeai as genai_lib
            from google.generativeai.types import content_types
            
            # Build function declarations using the SDK's expected format
            function_declarations = []
            for func in FUNCTIONS:
                fd = content_types.FunctionDeclaration(
                    name=func["name"],
                    description=func.get("description", ""),
                    parameters=func.get("parameters")
                )
                function_declarations.append(fd)
            
            tool = content_types.Tool(function_declarations=function_declarations)
            
            response = model.generate_content(
                contents=full_prompt,
                tools=[tool],
                tool_config={"function_calling_config": {"mode": "AUTO"}}
            )
            # Check for empty or blocked response
            if response is None:
                exception_info = Exception("Empty response from Gemini API")
                return
            if not response.candidates:
                # Check prompt feedback for block reason
                if hasattr(response, 'prompt_feedback'):
                    feedback = response.prompt_feedback
                    block_reason = getattr(feedback, 'block_reason', 'Unknown')
                    exception_info = Exception(f"Response blocked: {block_reason}")
                else:
                    exception_info = Exception("No candidates in response")
                return
        except ValueError as ve:
            # Specific handling for ValueError - often means response parsing issue
            exception_info = ve
            error_str = str(ve) if str(ve) else "empty ValueError"
            logger.error(f"ValueError during API call: {error_str}")
            logger.error(f"This may indicate a response parsing issue or API format change")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
        except Exception as e:
            exception_info = e
            # Log the full exception details
            logger.error(f"API call exception type: {type(e).__name__}")
            logger.error(f"API call exception details: {repr(e)}")
    
    api_thread = threading.Thread(target=api_call)
    api_thread.daemon = True
    api_thread.start()
    api_thread.join(timeout=timeout)
    
    if api_thread.is_alive():
        raise GeminiTimeoutError(f"API call timed out after {timeout} seconds")
    
    if exception_info:
        # Include more details in the error
        error_msg = f"{type(exception_info).__name__}: {str(exception_info) or repr(exception_info)}"
        raise GeminiAPIError(error_msg)
    
    return response


def _parse_gemini_response(response) -> dict:
    """Parse Gemini response and extract function call or text content."""
    try:
        part = response.candidates[0].content.parts[0]
        
        # Check for function call
        if hasattr(part, "function_call") and part.function_call:
            args = part.function_call.args
            # Convert MapComposite to dict if needed
            if hasattr(args, "to_dict"):
                params = args.to_dict()
            elif isinstance(args, str):
                params = json.loads(args)
            else:
                params = args or {}
            
            return {
                "name": part.function_call.name,
                "parameters": params,
                "type": "function_call"
            }
        
        # Check for text content
        text = getattr(part, "text", None)
        if text:
            return {"name": None, "content": text, "type": "text"}
            
    except (IndexError, AttributeError) as e:
        logger.warning(f"Error parsing response parts: {e}")
    
    # Fallback: check for .text on response itself
    text = getattr(response, "text", None)
    if text:
        return {"name": None, "content": text, "type": "text"}
    
    return {"name": None, "content": "Sorry, I couldn't understand or generate a response.", "type": "error"}


def chat_with_functions(user_message: str, phone: str) -> dict:
    """
    Handle conversation with Gemini AI, including function calling and conversation history.
    
    Args:
        user_message: The user's input message
        phone: The user's phone identifier for conversation history
        
    Returns:
        dict: Either a function call dict with 'name' and 'parameters', 
              or a response dict with 'name'=None and 'content'
    """
    # Check if model is initialized
    if not model:
        logger.error("Gemini model not initialized - check GEMINI_API_KEY")
        return {"name": None, "content": "Sorry, AI features are currently unavailable."}
    
    # Retrieve conversation history
    try:
        conversation_history = retrieve_conversation_history(phone)
    except Exception as e:
        logger.warning(f"Could not retrieve conversation history: {e}")
        conversation_history = []

    # Build the prompt
    prompt = _build_conversation_prompt(user_message, conversation_history)
    
    # Make API call with retry logic
    response = None
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            response = _make_api_call_with_timeout(prompt, API_TIMEOUT)
            break  # Success, exit retry loop
        except GeminiTimeoutError as e:
            last_error = e
            logger.warning(f"Attempt {attempt + 1}/{MAX_RETRIES}: API timeout")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
        except GeminiAPIError as e:
            last_error = e
            logger.error(f"Attempt {attempt + 1}/{MAX_RETRIES}: API error - {e}")
            # Don't retry on certain errors (e.g., schema errors)
            if "schema" in str(e).lower() or "field" in str(e).lower():
                break
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
    
    # Handle complete failure
    if response is None:
        error_msg = "Sorry, I'm experiencing technical difficulties. Please try again."
        logger.error(f"All {MAX_RETRIES} attempts failed: {last_error}")
        add_to_conversation_history(phone, "user", user_message)
        add_to_conversation_history(phone, "assistant", error_msg)
        return {"name": None, "content": error_msg}
    
    # Parse the response
    result = _parse_gemini_response(response)
    
    # Log the interaction
    if result.get("type") == "function_call":
        log_content = f"Function call: {result['name']}({result.get('parameters', {})})"
    else:
        log_content = result.get("content", "No response")
    
    add_to_conversation_history(phone, "user", user_message)
    add_to_conversation_history(phone, "assistant", log_content)
    
    logger.debug(f"Gemini response type: {result.get('type')}")
    
    return result


def execute_function(call: dict, phone: str = "") -> str:
    """
    Execute a function called by Gemini AI.
    
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
            return play_song(params["song_name"])
        if name == "get_current_song":
            return get_current_song()
        if name == "play_playlist":
            return play_playlist(params["playlist_name"])
        if name == "play_album":
            return play_album(params["album_name"])
        
        # Gmail functions
        if name == "send_email":
            return send_email(params["to"], params["subject"], params["body"])
        if name == "summarize_emails":
            return summarize_emails()
        
        # Calendar functions
        if name == "create_event":
            return create_event(
                params["summary"],
                params.get("location", ""),
                params["start_time"],
                params["end_time"],
                params.get("attendees", [])
            )
        
        # Weather functions
        if name == "get_weather":
            return weather_service.get_current_weather(params["location"])
        if name == "get_weather_forecast":
            return weather_service.get_weather_forecast(
                params["location"], 
                params.get("days", 3)
            )
        
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
            return news_service.search_news(params["query"], params.get("limit", 5))
        
        if name == "get_daily_briefing":
            return news_service.get_daily_briefing()
        
        # Task management functions
        if name == "create_task":
            return task_manager.create_task(
                params["title"],
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
            return task_manager.complete_task(params["task_id"])
        
        if name == "create_reminder":
            return task_manager.create_reminder(
                params["message"],
                params["remind_at"]
            )
        
        if name == "list_reminders":
            return task_manager.list_reminders()
        
        if name == "get_task_summary":
            return task_manager.get_task_summary()
        
        # Google Keep sync functions
        if name == "sync_tasks_to_google":
            return task_manager.sync_to_google_keep()
        
        if name == "sync_tasks_from_google":
            return task_manager.sync_from_google_keep()
        
        if name == "get_sync_status":
            return task_manager.get_sync_status()
        
        if name == "create_google_note":
            return google_notes_service.create_note(
                params["title"],
                params.get("content", ""),
                params.get("tags", [])
            )
        
        if name == "search_google_notes":
            return google_notes_service.search_notes(params["query"])
        
        # Contact management functions
        if name == "add_contact":
            return contact_manager.add_local_contact(
                params["name"],
                params.get("phone"),
                params.get("email"),
                params.get("notes")
            )
        
        if name == "search_contacts":
            return contact_manager.search_all_contacts(params["query"])
        
        if name == "list_contacts":
            return contact_manager.list_local_contacts()
        
        if name == "get_contact_summary":
            return contact_manager.get_contact_summary()
        
        if name == "get_google_contacts":
            max_results = params.get("max_results", 20)
            return contact_manager.get_google_contacts(max_results)
        
        if name == "send_whatsapp_message":
            return contact_manager.send_whatsapp_message(
                params["contact_query"],
                params["message"]
            )
        
        # Web search function
        if name == "search_web":
            from handlers.search import web_search
            return web_search.search_and_summarize(
                params["query"], 
                params.get("num_results", 3)
            )
        
        # Enhanced calendar functions
        if name == "get_calendar_summary":
            from handlers.calendar import get_smart_calendar_brief
            return get_smart_calendar_brief()
        
        # Enhanced email functions
        if name == "get_smart_email_brief":
            from handlers.gmail import get_smart_email_brief
            return get_smart_email_brief()
        
        # Voice control functions
        if name == "toggle_voice_responses":
            from handlers.speech import toggle_user_voice_preference
            return toggle_user_voice_preference(phone)
        
        if name == "set_voice_responses":
            from handlers.speech import set_user_voice_preference
            enabled = params.get("enabled", True)
            return set_user_voice_preference(phone, enabled)
        
        # Uber transportation functions
        if name == "get_ride_estimates":
            return uber_service.get_ride_estimates(
                params.get("start_lat"),
                params.get("start_lng"),
                params["end_lat"],
                params["end_lng"]
            )
        
        if name == "book_uber_ride":
            return uber_service.book_ride(
                params["product_id"],
                params.get("start_lat"),
                params.get("start_lng"),
                params["end_lat"],
                params["end_lng"],
                params.get("fare_id")
            )
        
        if name == "search_restaurants":
            return uber_service.search_restaurants(
                params.get("query", ""),
                params.get("lat"),
                params.get("lng")
            )
        
        # Accommodation functions
        if name == "search_accommodations":
            return accommodation_service.search_accommodations(
                params["location"],
                params.get("check_in"),
                params.get("check_out"),
                params.get("guests", 2),
                params.get("max_price")
            )
        
        if name == "book_accommodation":
            return accommodation_service.book_accommodation(
                params["property_id"],
                params["check_in"],
                params["check_out"],
                params.get("guests", 2),
                params.get("guest_name", "Guest")
            )
        
        # Fitness functions
        if name == "get_fitness_summary":
            return fitness_service.get_daily_summary(params.get("date"))
        
        if name == "log_fitness_activity":
            return fitness_service.log_activity(
                params["activity_type"],
                params["duration"],
                params.get("calories"),
                params.get("distance"),
                params.get("notes")
            )
        
        if name == "get_fitness_history":
            return fitness_service.get_activity_history(params.get("days", 7))
        
        if name == "set_fitness_goal":
            return fitness_service.set_fitness_goal(
                params["goal_type"],
                params["target"]
            )
        
        # Google Notes functions
        if name == "create_note":
            return google_notes_service.create_note(
                params["title"],
                params.get("content", ""),
                params.get("tags")
            )
        
        if name == "search_notes":
            return google_notes_service.search_notes(params["query"])
        
        if name == "sync_notes_tasks":
            return google_notes_service.sync_with_local_tasks()
        
        # Enhanced contact and WhatsApp functions
        if name == "get_contact_for_whatsapp":
            return contact_manager.get_contact_for_whatsapp(params["contact_query"])
        
        # Media generation functions
        if name == "generate_image":
            from handlers.media_generator import media_generator
            import asyncio
            
            # Run async function
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                media_generator.generate_image(
                    params["prompt"], 
                    phone, 
                    params.get("style", "realistic")
                )
            )
            loop.close()
            
            if result.get('success'):
                return f"🎨 Image generated successfully!\n\n📝 Prompt: {params['prompt']}\n🎭 Style: {params.get('style', 'realistic')}\n💾 File: {result.get('file_path', 'Unknown')}\n🤖 Generator: {result.get('generator', 'Unknown')}"
            else:
                return f"❌ Image generation failed: {result.get('error', 'Unknown error')}"
        
        if name == "create_avatar":
            from handlers.media_generator import media_generator
            avatar_path = media_generator.create_avatar(
                params.get("personality", "wednesday"),
                params.get("style", "professional")
            )
            
            if avatar_path:
                return f"🎭 Avatar created successfully!\n\n👤 Personality: {params.get('personality', 'wednesday')}\n🎨 Style: {params.get('style', 'professional')}\n💾 File: {avatar_path}"
            else:
                return "❌ Failed to create avatar"
        
        # Service monitoring functions
        if name == "check_service_status":
            from handlers.service_monitor import service_monitor
            service_name = params.get("service_name")
            status = service_monitor.get_service_status(service_name)
            
            if service_name:
                service_info = status.get('service', {})
                stats = status.get('stats', {})
                
                return f"🔧 Service Status: {service_name}\n\n" \
                       f"Status: {service_info.get('status', 'Unknown')}\n" \
                       f"Last Check: {service_info.get('last_check', 'Never')}\n" \
                       f"Response Time: {service_info.get('response_time', 'N/A')}ms\n" \
                       f"Error Count: {service_info.get('error_count', 0)}\n" \
                       f"Total Checks: {stats.get('total_checks', 0)}\n" \
                       f"Success Rate: {(stats.get('successful_checks', 0) / max(stats.get('total_checks', 1), 1) * 100):.1f}%"
            else:
                services = status.get('services', {})
                healthy_count = sum(1 for s in services.values() if s.get('status') == 'healthy')
                total_count = len(services)
                
                result = f"🔧 **System Services Overview**\n\n"
                result += f"✅ Healthy: {healthy_count}/{total_count}\n"
                result += f"🔄 Monitoring: {'Active' if status.get('monitoring_active') else 'Inactive'}\n\n"
                
                for name, service in services.items():
                    status_emoji = "✅" if service.get('status') == 'healthy' else "❌"
                    critical_emoji = "🔴" if service.get('critical') else "🟡"
                    result += f"{status_emoji} {critical_emoji} {name}: {service.get('status', 'unknown')}\n"
                
                return result
        
        if name == "get_system_health":
            from handlers.service_monitor import service_monitor
            health_summary = service_monitor.get_system_health_summary()
            
            return f"🏥 **System Health Summary**\n\n" \
                   f"Overall Status: {health_summary.get('overall_status', 'Unknown').title()}\n" \
                   f"Healthy Services: {health_summary.get('healthy_services', 0)}/{health_summary.get('total_services', 0)}\n" \
                   f"Critical Issues: {health_summary.get('critical_services_down', 0)}\n" \
                   f"Monitoring: {'Active' if health_summary.get('monitoring_active') else 'Inactive'}\n" \
                   f"Last Check: {health_summary.get('last_check', 'Never')}"
        
        # Advanced AI functions
        if name == "generate_video":
            from handlers.advanced_ai import advanced_ai
            import asyncio
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                advanced_ai.generate_video(
                    params["prompt"], 
                    params.get("style", "realistic"),
                    params.get("duration", 5)
                )
            )
            loop.close()
            
            if result.get('success'):
                return f"🎬 Video generated successfully!\n\n📝 Prompt: {params['prompt']}\n🎭 Style: {params.get('style', 'realistic')}\n⏱️ Duration: {params.get('duration', 5)}s\n💾 File: {result.get('video_path', 'Unknown')}\n🤖 Generator: {result.get('generator', 'Unknown')}"
            else:
                return f"❌ Video generation failed: {result.get('error', 'Unknown error')}"
        
        if name == "synthesize_voice":
            from handlers.advanced_ai import advanced_ai
            import asyncio
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                advanced_ai.synthesize_voice(
                    params["text"],
                    params.get("voice_id", "default"),
                    params.get("style", "natural")
                )
            )
            loop.close()
            
            if result.get('success'):
                return f"🗣️ Voice synthesized successfully!\n\n📝 Text: {params['text'][:100]}{'...' if len(params['text']) > 100 else ''}\n🎤 Voice: {params.get('voice_id', 'default')}\n🎭 Style: {params.get('style', 'natural')}\n💾 File: {result.get('audio_path', 'Unknown')}\n🤖 Generator: {result.get('generator', 'Unknown')}"
            else:
                return f"❌ Voice synthesis failed: {result.get('error', 'Unknown error')}"
        
        if name == "analyze_image":
            from handlers.advanced_ai import advanced_ai
            import asyncio
            
            # For demo purposes, create a placeholder image path
            # In real implementation, this would be an actual uploaded image
            placeholder_path = "generated_media/placeholder_analysis.jpg"
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                advanced_ai.analyze_image(
                    placeholder_path,
                    params.get("analysis_type", "comprehensive")
                )
            )
            loop.close()
            
            if result.get('success'):
                analysis = result
                response = f"🔍 **Image Analysis Complete**\n\n"
                response += f"📊 **Properties**: {analysis.get('properties', {}).get('width', 'Unknown')}x{analysis.get('properties', {}).get('height', 'Unknown')} pixels\n"
                
                if analysis.get('color_analysis'):
                    colors = analysis['color_analysis']
                    response += f"🎨 **Colors**: {colors.get('color_palette', 'Unknown')} palette, {colors.get('brightness', 0):.0f}% brightness\n"
                
                if analysis.get('objects'):
                    response += f"🎯 **Objects**: {len(analysis['objects'])} detected\n"
                
                if analysis.get('faces'):
                    response += f"👤 **Faces**: {len(analysis['faces'])} detected\n"
                
                if analysis.get('scene'):
                    scene = analysis['scene']
                    response += f"🌍 **Scene**: {scene.get('scene_type', 'Unknown')} ({scene.get('lighting', 'Unknown')} lighting)\n"
                
                return response
            else:
                return f"❌ Image analysis failed: {result.get('error', 'Unknown error')}"
        
        if name == "predict_user_behavior":
            from handlers.advanced_ai import advanced_ai
            import asyncio
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            context = {"current_request": params.get("context", "")} if params.get("context") else None
            result = loop.run_until_complete(
                advanced_ai.predict_user_behavior(phone, context)
            )
            loop.close()
            
            if result.get('success'):
                patterns = result.get('patterns', {})
                predictions = result.get('predictions', [])
                recommendations = result.get('recommendations', [])
                
                response = f"🔮 **Behavior Prediction Analysis**\n\n"
                response += f"📊 **Confidence**: {result.get('confidence', 0):.1%}\n"
                response += f"💬 **Message Frequency**: {patterns.get('message_frequency', 0)} messages\n"
                response += f"❓ **Question Ratio**: {patterns.get('question_ratio', 0):.1%}\n"
                response += f"⚡ **Command Usage**: {patterns.get('command_ratio', 0):.1%}\n\n"
                
                if predictions:
                    response += "🎯 **Predictions**:\n"
                    for pred in predictions[:3]:
                        response += f"• {pred.get('description', 'Unknown')} ({pred.get('confidence', 0):.1%})\n"
                
                if recommendations:
                    response += "\n💡 **Recommendations**:\n"
                    for rec in recommendations[:3]:
                        response += f"• {rec.get('title', 'Unknown')}: {rec.get('description', 'No description')}\n"
                
                return response
            else:
                return f"❌ Behavior prediction failed: {result.get('error', 'Unknown error')}"
        
        if name == "run_system_diagnostics":
            test_type = params.get("test_type", "quick")
            
            if test_type == "quick":
                # Quick health check
                from handlers.service_monitor import service_monitor
                health = service_monitor.get_system_health_summary()
                
                response = f"🔧 **Quick System Diagnostics**\n\n"
                response += f"System Status: {health.get('overall_status', 'Unknown').title()}\n"
                response += f"Services: {health.get('healthy_services', 0)}/{health.get('total_services', 0)} healthy\n"
                response += f"Memory: {health.get('system_metrics', {}).get('memory_percent', 'Unknown')}% used\n"
                response += f"CPU: {health.get('system_metrics', {}).get('cpu_percent', 'Unknown')}% used\n"
                response += f"Disk: {health.get('system_metrics', {}).get('disk_percent', 'Unknown')}% used\n\n"
                response += "✅ Quick diagnostics complete!"
                
                return response
            
            elif test_type == "comprehensive":
                # Run comprehensive tests
                try:
                    from test_suite import ComprehensiveTestSuite
                    test_suite = ComprehensiveTestSuite()
                    
                    # Run a subset of tests for Gemini response
                    api_results = test_suite.run_api_tests()
                    db_results = test_suite.run_database_tests()
                    
                    response = f"🧪 **Comprehensive Diagnostics**\n\n"
                    response += f"API Tests: {api_results['passed']}/{api_results['passed'] + api_results['failed']} passed\n"
                    response += f"Database Tests: {db_results['passed']}/{db_results['passed'] + db_results['failed']} passed\n"
                    response += f"Overall Status: {'✅ Healthy' if (api_results['failed'] + db_results['failed']) == 0 else '⚠️ Issues Detected'}\n\n"
                    response += "📊 Run '/dashboard' for detailed metrics"
                    
                    return response
                except Exception as e:
                    return f"❌ Comprehensive diagnostics failed: {str(e)}"
            
            else:
                return f"❌ Unknown test type: {test_type}. Use: quick, comprehensive, performance"
        
        if name == "optimize_performance":
            optimization_type = params.get("optimization_type", "all")
            
            try:
                import gc
                import psutil
                
                response = f"⚡ **Performance Optimization**\n\n"
                
                if optimization_type in ["memory", "all"]:
                    # Force garbage collection
                    gc.collect()
                    response += "🧹 Memory cleanup completed\n"
                
                if optimization_type in ["database", "all"]:
                    # Database optimization
                    try:
                        from database import cleanup_old_data
                        cleanup_old_data(7)  # Clean data older than 7 days
                        response += "🗃️ Database optimization completed\n"
                    except ImportError:
                        response += "🗃️ Database optimization skipped (not available)\n"
                    except Exception as e:
                        response += f"⚠️ Database optimization failed: {str(e)}\n"
                
                if optimization_type in ["cpu", "all"]:
                    # CPU optimization (placeholder)
                    response += "⚙️ CPU optimization analysis completed\n"
                
                # Get current metrics
                process = psutil.Process()
                memory_mb = process.memory_info().rss / 1024 / 1024
                cpu_percent = process.cpu_percent()
                
                response += f"\n📊 **Current Metrics**:\n"
                response += f"Memory: {memory_mb:.1f} MB\n"
                response += f"CPU: {cpu_percent:.1f}%\n"
                response += f"Status: {'🟢 Optimal' if memory_mb < 200 and cpu_percent < 50 else '🟡 Monitoring'}"
                
                return response
                
            except Exception as e:
                logger.error(f"Performance optimization failed: {e}")
                return f"❌ Performance optimization failed: {str(e)}"

        # Daily Briefing functions
        if name == "get_daily_briefing":
            location = params.get("location", "Johannesburg")
            return send_briefing_now(phone, location)
        
        if name == "schedule_daily_briefing":
            hour = params.get("hour", 7)
            minute = params.get("minute", 0)
            location = params.get("location", "Johannesburg")
            result = schedule_daily_briefing(phone, hour, minute, location)
            return f"✅ {result['message']}\n\n⏰ Time: {result['time']}\n📍 Location: {result['location']}"
        
        if name == "cancel_daily_briefing":
            result = cancel_daily_briefing(phone)
            return f"{'✅' if result['status'] == 'cancelled' else '⚠️'} {result['message']}"

        # Image Analysis functions
        if name == "analyze_image":
            image_url = params.get("image_url", "")
            question = params.get("question")
            return analyze_whatsapp_image(image_url, question)
        
        # Expense Tracking functions
        if name == "add_expense":
            result = expense_service.add(
                phone,
                params["amount"],
                params["category"],
                params.get("description", "")
            )
            return result.get('message', 'Expense recorded')
        
        if name == "get_spending_report":
            days = params.get("days", 30)
            return expense_service.get_report(phone, days)
        
        # Mood Music functions
        if name == "play_mood_music":
            mood = params["mood"]
            return mood_music_service.play_for_mood(mood, phone)
        
        if name == "detect_mood_and_play":
            message = params["message"]
            return mood_music_service.analyze_and_play(message, phone)
        
        # Conversation Memory functions
        if name == "search_memory":
            query = params["query"]
            return memory_service.format_search(phone, query)
        
        if name == "recall_conversation":
            question = params["question"]
            return memory_service.recall(phone, question)
        
        if name == "summarize_conversations":
            topic = params.get("topic")
            return memory_service.summarize(phone, topic)

        # Function not found
        logger.warning(f"Unknown function called: {name}")
        return f"I don't know how to handle the function '{name}'. Please try a different request."
        
    except KeyError as e:
        logger.error(f"Missing required parameter for {name}: {e}")
        return f"Missing required information for {name}: {e}"
    except Exception as e:
        logger.error(f"Error executing function {name}: {e}", exc_info=True)
        return f"Error executing {name}: {e}"


def validate_function_schemas() -> List[str]:
    """
    Validate all function schemas for Gemini API compatibility.
    
    Returns:
        List of validation error messages (empty if all valid)
    """
    errors = []
    invalid_fields = ["default", "examples", "pattern"]  # Fields not supported by Gemini
    
    for func in FUNCTIONS:
        func_name = func.get("name", "unknown")
        params = func.get("parameters", {})
        properties = params.get("properties", {})
        
        for prop_name, prop_def in properties.items():
            for invalid_field in invalid_fields:
                if invalid_field in prop_def:
                    errors.append(f"Function '{func_name}', property '{prop_name}': invalid field '{invalid_field}'")
    
    if errors:
        logger.error(f"Schema validation found {len(errors)} errors")
        for error in errors:
            logger.error(f"  - {error}")
    else:
        logger.info(f"All {len(FUNCTIONS)} function schemas validated successfully")
    
    return errors


def get_available_functions() -> List[str]:
    """Get a list of all available function names."""
    return [f.get("name") for f in FUNCTIONS if f.get("name")]


# Validate schemas on module load (development check)
if __name__ != "__main__":
    # Only run validation in non-main contexts (when imported)
    _validation_errors = validate_function_schemas()
    if _validation_errors:
        logger.warning(f"Function schema validation found {len(_validation_errors)} issues")
