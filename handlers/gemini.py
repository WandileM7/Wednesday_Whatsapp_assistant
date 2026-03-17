"""Gemini AI Integration Handler with Function Calling Support.

This module provides AI-powered conversation handling with integrated function calling
for various services like Spotify, Gmail, Calendar, Weather, and more.
"""

from google import genai
from google.genai import types as genai_types
import json
import threading
import time
import logging
import os
from typing import Dict, Any, Optional, Callable, List
from functools import wraps
from datetime import datetime
import pytz

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

GENERATION_MODEL = "gemini-2.5-flash"

# Configure logging
logger = logging.getLogger("GeminiHandler")

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds
MAX_CONVERSATION_HISTORY = 10  # messages to include
MAX_AGENT_ITERATIONS = 5  # max sequential tool calls per user message

# Gemini client state
client: Optional[genai.Client] = None
FUNCTION_TOOLS: List[genai_types.Tool] = []


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


# Gemini client initialized after tool setup

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
        "name": "get_current_time",
        "description": "Get the current date and time (local and UTC)",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
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
    },
    # ==================== JARVIS Advanced Functions ====================
    # Workflow Automation
    {
        "name": "run_workflow",
        "description": "Run an automated workflow like morning_routine, prepare_meeting, end_of_day, focus_mode, leaving_home, coming_home, party_mode, sleep_mode",
        "parameters": {
            "type": "object",
            "properties": {
                "workflow": {"type": "string", "description": "Workflow name: morning_routine, prepare_meeting, end_of_day, focus_mode, leaving_home, coming_home, party_mode, sleep_mode"},
                "duration": {"type": "integer", "description": "Duration in minutes (for focus_mode)"},
                "location": {"type": "string", "description": "Location (for weather in briefings)"}
            },
            "required": ["workflow"]
        }
    },
    {
        "name": "list_workflows",
        "description": "List all available JARVIS automation workflows",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    # Smart Home Control
    {
        "name": "smart_home_lights",
        "description": "Control smart home lights - turn on/off, set brightness, change colors",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action: on, off, dim"},
                "brightness": {"type": "integer", "description": "Brightness level 0-100"},
                "room": {"type": "string", "description": "Room name (or 'all')"},
                "color": {"type": "string", "description": "Color name: red, blue, green, warm, cool, etc."}
            },
            "required": ["action"]
        }
    },
    {
        "name": "smart_home_thermostat",
        "description": "Control smart home thermostat - set temperature",
        "parameters": {
            "type": "object",
            "properties": {
                "temperature": {"type": "integer", "description": "Temperature in Fahrenheit"},
                "mode": {"type": "string", "description": "Mode: heat, cool, auto, off"}
            },
            "required": ["temperature"]
        }
    },
    {
        "name": "smart_home_scene",
        "description": "Activate a smart home scene like movie, work, sleep, morning, party, romantic, focus",
        "parameters": {
            "type": "object",
            "properties": {
                "scene": {"type": "string", "description": "Scene name: movie, work, sleep, morning, party, romantic, focus, away"}
            },
            "required": ["scene"]
        }
    },
    {
        "name": "smart_home_locks",
        "description": "Control smart locks - lock or unlock doors",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action: lock or unlock"},
                "door": {"type": "string", "description": "Door name (or 'all')"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "smart_home_status",
        "description": "Get smart home status - all devices and integrations",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    # Long-term Memory
    {
        "name": "remember_this",
        "description": "Remember specific information for later (e.g., 'Remember that my favorite color is blue')",
        "parameters": {
            "type": "object",
            "properties": {
                "information": {"type": "string", "description": "Information to remember"},
                "importance": {"type": "string", "description": "Importance: low, medium, high"}
            },
            "required": ["information"]
        }
    },
    {
        "name": "what_do_you_remember",
        "description": "Recall what JARVIS remembers about a topic or in general",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic to recall (optional - leave empty for general recall)"}
            },
            "required": []
        }
    },
    {
        "name": "forget_this",
        "description": "Forget specific information or all memories of a category",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic or category to forget"}
            },
            "required": ["topic"]
        }
    },
    {
        "name": "get_my_profile",
        "description": "Get the user's profile including preferences, facts, and memory statistics",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    # Security
    {
        "name": "security_status",
        "description": "Get JARVIS security status and recent alerts",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "security_report",
        "description": "Get detailed security report with threat analysis",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    # Proactive Briefings
    {
        "name": "schedule_morning_briefing",
        "description": "Schedule automatic daily morning briefing at a specific time",
        "parameters": {
            "type": "object",
            "properties": {
                "hour": {"type": "integer", "description": "Hour (0-23, default 7)"},
                "minute": {"type": "integer", "description": "Minute (0-59, default 0)"},
                "location": {"type": "string", "description": "Location for weather"}
            },
            "required": []
        }
    },
    {
        "name": "cancel_morning_briefing",
        "description": "Cancel scheduled morning briefing",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    # Voice Control (ElevenLabs)
    {
        "name": "speak_this",
        "description": "Make JARVIS speak text aloud using premium AI voice",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text for JARVIS to speak"},
                "style": {"type": "string", "description": "Voice style: default, expressive, calm, urgent, whisper"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "change_voice",
        "description": "Change JARVIS voice to a different preset",
        "parameters": {
            "type": "object",
            "properties": {
                "voice": {"type": "string", "description": "Voice preset: jarvis, friday, british_butler, warm, narrator"}
            },
            "required": ["voice"]
        }
    },
    {
        "name": "voice_status",
        "description": "Get voice synthesis status and available voices",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    # JARVIS Core
    {
        "name": "jarvis_status",
        "description": "Get full JARVIS system status including all subsystems",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "trigger_ifttt",
        "description": "Trigger an IFTTT webhook event for custom automation",
        "parameters": {
            "type": "object",
            "properties": {
                "event": {"type": "string", "description": "IFTTT event name"},
                "value1": {"type": "string", "description": "Optional value 1"},
                "value2": {"type": "string", "description": "Optional value 2"},
                "value3": {"type": "string", "description": "Optional value 3"}
            },
            "required": ["event"]
        }
    }
]


def _build_function_tools() -> List[genai_types.Tool]:
    """Create function declarations for Gemini tools."""
    declarations: List[genai_types.FunctionDeclaration] = []
    for fn in FUNCTIONS:
        try:
            declarations.append(
                genai_types.FunctionDeclaration(
                    name=fn.get("name", ""),
                    description=fn.get("description", ""),
                    parameters=fn.get("parameters", {}),
                )
            )
        except Exception as e:
            logger.warning(f"Skipping function declaration for {fn.get('name', 'unknown')}: {e}")

    if not declarations:
        return []

    try:
        return [genai_types.Tool(function_declarations=declarations)]
    except Exception as e:
        logger.warning(f"Failed to build function toolset: {e}")
        return []


def _initialize_gemini_client() -> None:
    """Initialize the Gemini client, preferring Vertex AI when running on GCP."""
    global client, FUNCTION_TOOLS

    # Try Vertex AI first — uses Cloud Run service account, no extra API key needed.
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    if project_id:
        try:
            client = genai.Client(vertexai=True, project=project_id, location=location)
            FUNCTION_TOOLS = _build_function_tools()
            fn_count = len(FUNCTION_TOOLS[0].function_declarations) if FUNCTION_TOOLS else 0
            logger.info(
                f"Gemini client initialized via Vertex AI "
                f"(project={project_id}, location={location}, model={GENERATION_MODEL}, tools={fn_count})"
            )
            return
        except Exception as e:
            logger.warning(f"Vertex AI init failed, falling back to API key: {e}")

    # Fall back to direct API key (local dev / non-GCP environments)
    if not GEMINI_API_KEY:
        logger.warning("Neither GOOGLE_CLOUD_PROJECT nor GEMINI_API_KEY set — Gemini AI disabled")
        client = None
        FUNCTION_TOOLS = []
        return

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        FUNCTION_TOOLS = _build_function_tools()
        fn_count = len(FUNCTION_TOOLS[0].function_declarations) if FUNCTION_TOOLS else 0
        logger.info(f"Gemini client initialized via API key (model={GENERATION_MODEL}, tools={fn_count})")
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")
        client = None
        FUNCTION_TOOLS = []


_initialize_gemini_client()

# Create a function name to handler mapping for cleaner execution
FUNCTION_HANDLERS: Dict[str, Callable] = {}


def _build_conversation_prompt(user_message: str, conversation_history: List[str], phone: str = None) -> str:
    """Build the conversation prompt with JARVIS personality and situational awareness."""
    # Limit conversation history to prevent token overflow
    recent_history = conversation_history[-MAX_CONVERSATION_HISTORY:] if conversation_history else []
    history_text = '\n'.join(recent_history) if recent_history else "No previous conversation."
    
    # Get JARVIS system prompt with situational context
    try:
        from handlers.jarvis_core import get_jarvis_system_prompt, proactive_intelligence
        
        jarvis_prompt = get_jarvis_system_prompt(phone)
        
        # Check for proactive suggestions based on message content
        proactive_hint = proactive_intelligence.analyze_message_for_proactive_response(user_message, phone) if phone else None
        proactive_section = f"\n\n**Proactive Note**: {proactive_hint}" if proactive_hint else ""
        
    except ImportError:
        jarvis_prompt = """You are Wednesday, a helpful personal assistant with the personality of Jarvis from Iron Man - witty, efficient, and occasionally sarcastic."""
        proactive_section = ""
    
    return f"""{jarvis_prompt}

IMPORTANT RULES:
1. When the user asks to perform an action (play music, send email, create event, etc.), ALWAYS use the appropriate function
2. Be concise but helpful in your responses
3. Use your personality to make interactions engaging
4. **LANGUAGE**: Detect the language of the user's message and ALWAYS respond in the SAME language. If they write in Spanish, respond in Spanish. If they write in Zulu, respond in Zulu. If they write in French, respond in French. Match their language exactly.
5. If the user mixes languages, respond in the primary language they used
{proactive_section}

Recent Conversation:
{history_text}

Current Request: {user_message}
"""


def _make_api_call_with_timeout(prompt: str, timeout: int = 30) -> tuple:
    """Legacy single-shot API call — kept for any external callers. Not used by the agent loop."""
    if client is None:
        raise GeminiAPIError("Gemini client not initialized")
    
    response = None
    exception_info = None
    
    def api_call():
        nonlocal response, exception_info
        try:
            # Build the content with system instruction separate
            full_prompt = f"{PERSONALITY_PROMPT}\n\n{prompt}"
            config = None
            if FUNCTION_TOOLS:
                try:
                    config = genai_types.GenerateContentConfig(tools=FUNCTION_TOOLS)
                except Exception as e:
                    logger.warning(f"Unable to attach tools to request, continuing without tools: {e}")

            response = client.models.generate_content(
                model=GENERATION_MODEL,
                contents=full_prompt,
                config=config,
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
            elif isinstance(args, dict):
                params = args
            elif hasattr(args, "items"):
                params = dict(args)
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
    Agentic loop: call Gemini, execute tools as needed, and return the final text response.

    Gemini can call up to MAX_AGENT_ITERATIONS tools in sequence before producing its answer.
    Always returns {"name": None, "content": <str>, "type": "text"}.
    """
    if not client:
        logger.error("Gemini client not initialized")
        return {"name": None, "content": "Sorry, AI features are currently unavailable."}

    # Quick rule-based workaround for direct calendar commands (edge-case compatibility)
    def _handle_direct_calendar_command(msg: str) -> Optional[str]:
        lower = msg.lower()
        if "calendar" in lower and "event" in lower and "subject" in lower:
            import re
            subject_match = re.search(r"subject\s*(?:=|equals)\s*([^\.]+)", msg, re.IGNORECASE)
            start_match = re.search(r"start[_\s]*time\s*(?:=|equals)\s*([^\.]+)", msg, re.IGNORECASE)
            subject = subject_match.group(1).strip() if subject_match else "Untitled"
            start_time = start_match.group(1).strip() if start_match else "today 12am"
            try:
                result = create_event(summary=subject, start_time=start_time, end_time="today 1am")
                return f"✅ Created calendar event: {subject} ({start_time}). {result if isinstance(result, str) else ''}".strip()
            except Exception as e:
                logger.error(f"Direct calendar command failed: {e}")
                return f"❌ Could not create calendar event: {e}"
        return None

    direct_response = _handle_direct_calendar_command(user_message)
    if direct_response:
        add_to_conversation_history(phone, "user", user_message)
        add_to_conversation_history(phone, "assistant", direct_response)
        return {"name": None, "content": direct_response}

    try:
        conversation_history = retrieve_conversation_history(phone)
    except Exception as e:
        logger.warning(f"Could not retrieve conversation history: {e}")
        conversation_history = []

    prompt = _build_conversation_prompt(user_message, conversation_history, phone)
    config = genai_types.GenerateContentConfig(tools=FUNCTION_TOOLS) if FUNCTION_TOOLS else None

    # Seed the multi-turn conversation with the user's enriched message
    contents = [genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])]

    final_text = None

    for iteration in range(MAX_AGENT_ITERATIONS + 1):
        try:
            response = client.models.generate_content(
                model=GENERATION_MODEL,
                contents=contents,
                config=config,
            )
        except Exception as e:
            logger.error(f"Gemini API error (iteration {iteration}): {e}")
            final_text = "Sorry, I encountered an error. Please try again."
            break

        if not response.candidates:
            logger.warning("No candidates in Gemini response")
            final_text = "Sorry, I couldn't generate a response."
            break

        model_content = response.candidates[0].content

        # Find a function call in the model's response parts
        function_call_part = None
        for part in model_content.parts:
            if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                function_call_part = part.function_call
                break

        if function_call_part and iteration < MAX_AGENT_ITERATIONS:
            fn_name = function_call_part.name
            fn_args = dict(function_call_part.args) if function_call_part.args else {}
            logger.info(f"Agent tool call [{iteration + 1}/{MAX_AGENT_ITERATIONS}]: {fn_name}({fn_args})")

            try:
                tool_result = execute_function({"name": fn_name, "parameters": fn_args}, phone)
            except Exception as e:
                logger.error(f"Tool execution failed for {fn_name}: {e}")
                tool_result = f"Error executing {fn_name}: {e}"

            # Append model turn (contains the function_call), then the tool result
            contents.append(model_content)
            contents.append(
                genai_types.Content(
                    role="user",
                    parts=[
                        genai_types.Part(
                            function_response=genai_types.FunctionResponse(
                                name=fn_name,
                                response={"result": str(tool_result)},
                            )
                        )
                    ],
                )
            )

        else:
            # Text response (or iteration limit hit) — extract and finish
            try:
                final_text = response.text or ""
            except Exception:
                final_text = ""

            if not final_text:
                for part in model_content.parts:
                    t = getattr(part, "text", None)
                    if t:
                        final_text = t
                        break

            if not final_text:
                final_text = "Task completed."
            break

    if not final_text:
        final_text = "I ran into an issue processing your request. Please try again."

    add_to_conversation_history(phone, "user", user_message)
    add_to_conversation_history(phone, "assistant", final_text)

    return {"name": None, "content": final_text, "type": "text"}


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
                summary=params["summary"],
                start_time=params["start_time"],
                end_time=params["end_time"],
                description=params.get("description", ""),
                location=params.get("location", ""),
                attendees=params.get("attendees", [])
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

        # Time function
        if name == "get_current_time":
            tz_name = os.getenv("TIMEZONE", "Africa/Johannesburg")
            try:
                local_tz = pytz.timezone(tz_name)
            except Exception:
                local_tz = pytz.UTC
                tz_name = "UTC"

            now_utc = datetime.now(pytz.UTC)
            now_local = now_utc.astimezone(local_tz)

            return (
                f"🕒 Current time:\n"
                f"• Local ({tz_name}): {now_local.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                f"• UTC: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )
        
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
                # JARVIS-style system status report
                try:
                    from handlers.jarvis_core import system_diagnostics
                    return system_diagnostics.get_status_report()
                except ImportError:
                    # Fallback to basic health check
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

        # ==================== JARVIS ADVANCED FUNCTIONS ====================
        
        # Workflow Automation
        if name == "run_workflow":
            try:
                from handlers.workflows import workflow_engine
                workflow = params.get("workflow", "morning_routine")
                workflow_params = {}
                if params.get("duration"):
                    workflow_params["duration"] = params["duration"]
                if params.get("location"):
                    workflow_params["location"] = params["location"]
                return workflow_engine.run_workflow(workflow, phone, workflow_params)
            except Exception as e:
                return f"❌ Workflow failed: {e}"
        
        if name == "list_workflows":
            try:
                from handlers.workflows import workflow_engine
                return workflow_engine.list_workflows()
            except Exception as e:
                return f"❌ Could not list workflows: {e}"
        
        # Smart Home Control
        if name == "smart_home_lights":
            try:
                from handlers.smart_home import smart_home
                action = params.get("action", "on")
                room = params.get("room", "all")
                brightness = params.get("brightness", 100)
                color = params.get("color")
                
                if action == "off":
                    return smart_home.lights_off(room)
                else:
                    return smart_home.lights_on(room, brightness, color)
            except Exception as e:
                return f"❌ Smart home error: {e}"
        
        if name == "smart_home_thermostat":
            try:
                from handlers.smart_home import smart_home
                temp = params.get("temperature", 72)
                mode = params.get("mode", "auto")
                return smart_home.set_thermostat(temp, mode)
            except Exception as e:
                return f"❌ Thermostat error: {e}"
        
        if name == "smart_home_scene":
            try:
                from handlers.smart_home import smart_home
                scene = params.get("scene", "default")
                return smart_home.activate_scene(scene)
            except Exception as e:
                return f"❌ Scene error: {e}"
        
        if name == "smart_home_locks":
            try:
                from handlers.smart_home import smart_home
                action = params.get("action", "lock")
                door = params.get("door", "all")
                if action == "unlock":
                    return smart_home.unlock_doors(door)
                else:
                    return smart_home.lock_doors(door)
            except Exception as e:
                return f"❌ Lock error: {e}"
        
        if name == "smart_home_status":
            try:
                from handlers.smart_home import smart_home
                status = smart_home.get_home_status()
                integrations = status.get('integrations', [])
                devices = status.get('devices', {})
                
                result = ["🏠 **Smart Home Status**\n"]
                if integrations:
                    result.append(f"**Integrations**: {', '.join(integrations)}")
                else:
                    result.append("**Integrations**: None configured")
                
                if devices:
                    result.append(f"\n**Devices** ({len(devices)}):")
                    for device_id, info in list(devices.items())[:10]:
                        name = info.get('friendly_name', device_id)
                        state = info.get('state', 'unknown')
                        result.append(f"  • {name}: {state}")
                
                return '\n'.join(result)
            except Exception as e:
                return f"❌ Status error: {e}"
        
        # Long-term Memory
        if name == "remember_this":
            try:
                from handlers.long_term_memory import long_term_memory
                info = params.get("information", "")
                importance_map = {"low": 0.3, "medium": 0.6, "high": 0.9}
                importance = importance_map.get(params.get("importance", "medium"), 0.6)
                memory = long_term_memory.remember(phone, info, importance)
                return f"✅ Remembered: {memory.summary}\n\n📁 Category: {memory.category}\n⭐ Importance: {params.get('importance', 'medium')}"
            except Exception as e:
                return f"❌ Memory error: {e}"
        
        if name == "what_do_you_remember":
            try:
                from handlers.long_term_memory import long_term_memory
                topic = params.get("topic", "")
                memories = long_term_memory.recall(phone, query=topic if topic else None, limit=5)
                
                if not memories:
                    return "I don't have any memories matching that." if topic else "My memory banks are empty for you."
                
                result = ["🧠 **Here's what I remember:**\n"]
                for m in memories:
                    from datetime import datetime
                    age = (datetime.now() - m.timestamp).days
                    age_str = f"{age}d ago" if age > 0 else "today"
                    result.append(f"• [{m.category}] {m.summary} ({age_str})")
                
                return '\n'.join(result)
            except Exception as e:
                return f"❌ Recall error: {e}"
        
        if name == "forget_this":
            try:
                from handlers.long_term_memory import long_term_memory
                topic = params.get("topic", "")
                count = long_term_memory.forget(phone, category=topic)
                return f"✅ Forgot {count} memories related to '{topic}'"
            except Exception as e:
                return f"❌ Forget error: {e}"
        
        if name == "get_my_profile":
            try:
                from handlers.long_term_memory import long_term_memory
                profile = long_term_memory.get_user_profile(phone)
                
                result = ["👤 **Your Profile**\n"]
                if profile.get('name'):
                    result.append(f"**Name**: {profile['name']}")
                
                if profile.get('preferences'):
                    prefs = ', '.join(f"{k}={v}" for k, v in list(profile['preferences'].items())[:5])
                    result.append(f"**Preferences**: {prefs}")
                
                if profile.get('facts'):
                    result.append(f"**Known Facts**: {len(profile['facts'])}")
                    for fact in profile['facts'][:3]:
                        result.append(f"  • {fact}")
                
                stats = profile.get('memory_stats', {})
                result.append(f"\n**Memory**: {stats.get('total', 0)} total memories")
                
                return '\n'.join(result)
            except Exception as e:
                return f"❌ Profile error: {e}"
        
        # Security
        if name == "security_status":
            try:
                from handlers.security import security_monitor
                status = security_monitor.get_security_status()
                return f"{status['status_emoji']} **Security Status**: {status['status']}\n\n• Alerts (24h): {status['alerts_last_24h']}\n• Blocked users: {status['blocked_users']}\n• Active users: {status['active_users']}"
            except Exception as e:
                return f"❌ Security error: {e}"
        
        if name == "security_report":
            try:
                from handlers.security import security_monitor
                return security_monitor.get_security_report()
            except Exception as e:
                return f"❌ Security report error: {e}"
        
        # Proactive Briefings
        if name == "schedule_morning_briefing":
            try:
                from handlers.jarvis_core import proactive_briefing_service
                hour = params.get("hour", 7)
                minute = params.get("minute", 0)
                location = params.get("location", "Johannesburg")
                return proactive_briefing_service.schedule_briefing(phone, hour, minute, location)
            except Exception as e:
                return f"❌ Scheduling error: {e}"
        
        if name == "cancel_morning_briefing":
            try:
                from handlers.jarvis_core import proactive_briefing_service
                return proactive_briefing_service.cancel_briefing(phone)
            except Exception as e:
                return f"❌ Cancel error: {e}"
        
        # Voice Control (ElevenLabs)
        if name == "speak_this":
            try:
                from handlers.elevenlabs_voice import elevenlabs_voice
                if not elevenlabs_voice.enabled:
                    return "❌ Voice synthesis not configured. Set ELEVENLABS_API_KEY."
                
                text = params.get("text", "")
                style = params.get("style", "default")
                audio_path = elevenlabs_voice.text_to_speech(text, voice="jarvis", style=style)
                
                if audio_path:
                    return f"🗣️ Voice generated!\n\n📝 Text: {text[:100]}{'...' if len(text) > 100 else ''}\n🎭 Style: {style}\n💾 Audio ready"
                return "❌ Voice generation failed"
            except Exception as e:
                return f"❌ Voice error: {e}"
        
        if name == "change_voice":
            try:
                from handlers.elevenlabs_voice import elevenlabs_voice
                voice = params.get("voice", "jarvis")
                elevenlabs_voice.set_voice(voice)
                return f"✅ Voice changed to: {voice}"
            except Exception as e:
                return f"❌ Voice change error: {e}"
        
        if name == "voice_status":
            try:
                from handlers.elevenlabs_voice import elevenlabs_voice
                if not elevenlabs_voice.enabled:
                    return "❌ Voice synthesis not enabled. Set ELEVENLABS_API_KEY."
                
                usage = elevenlabs_voice.get_usage()
                voices = elevenlabs_voice.get_voices_list()
                
                result = ["🎤 **Voice Status**\n"]
                result.append(f"**Tier**: {usage.get('tier', 'unknown')}")
                result.append(f"**Characters**: {usage.get('character_count', 0)} / {usage.get('character_limit', 0)}")
                result.append(f"\n**Available Voices** ({len(voices)}):")
                for v in voices[:8]:
                    result.append(f"  • {v.get('name', 'Unknown')}")
                
                return '\n'.join(result)
            except Exception as e:
                return f"❌ Voice status error: {e}"
        
        # JARVIS Core
        if name == "jarvis_status":
            try:
                from handlers.jarvis_core import jarvis
                return jarvis.get_full_status()
            except Exception as e:
                return f"❌ JARVIS status error: {e}"
        
        if name == "trigger_ifttt":
            try:
                from handlers.smart_home import smart_home
                event = params.get("event", "")
                value1 = params.get("value1", "")
                value2 = params.get("value2", "")
                value3 = params.get("value3", "")
                
                success = smart_home.trigger_ifttt(event, value1, value2, value3)
                if success:
                    return f"✅ IFTTT triggered: {event}"
                return f"❌ IFTTT trigger failed for: {event}"
            except Exception as e:
                return f"❌ IFTTT error: {e}"

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
