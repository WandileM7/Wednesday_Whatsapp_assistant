import google.generativeai as genai
import json
import threading
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
from handlers.shopping import order_manager
from handlers.paxi import paxi_service
import logging
from chromedb import *

# Timeout handler for thread-safe timeout
class TimeoutException(Exception):
    pass
# Initialize Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

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
    # Shopping and Paxi functions
    {
        "name": "add_to_cart",
        "description": "Add an item to the shopping cart",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Item name"},
                "price": {"type": "number", "description": "Item price in ZAR"},
                "quantity": {"type": "integer", "description": "Quantity (default: 1)"},
                "description": {"type": "string", "description": "Item description (optional)"}
            },
            "required": ["name", "price"]
        }
    },
    {
        "name": "view_cart",
        "description": "View current shopping cart contents",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "clear_cart",
        "description": "Clear all items from shopping cart",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "find_paxi_pickup_points",
        "description": "Find Paxi pickup points near a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "Location or suburb to search near"},
                "city": {"type": "string", "description": "City (default: Cape Town)"}
            },
            "required": []
        }
    },
    {
        "name": "checkout_with_paxi",
        "description": "Checkout cart with Paxi pickup point delivery",
        "parameters": {
            "type": "object",
            "properties": {
                "pickup_point_id": {"type": "string", "description": "Paxi pickup point ID"},
                "customer_name": {"type": "string", "description": "Customer name"},
                "customer_phone": {"type": "string", "description": "Customer phone number"},
                "customer_email": {"type": "string", "description": "Customer email (optional)"}
            },
            "required": ["pickup_point_id", "customer_name", "customer_phone"]
        }
    },
    {
        "name": "track_paxi_delivery",
        "description": "Track a Paxi delivery using tracking number",
        "parameters": {
            "type": "object",
            "properties": {
                "tracking_number": {"type": "string", "description": "Paxi tracking number"}
            },
            "required": ["tracking_number"]
        }
    },
    {
        "name": "get_delivery_options",
        "description": "Get available delivery options including Paxi",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
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
    }

]
def chat_with_functions(user_message: str, phone: str) -> dict:
    """Handles the conversation with Gemini, including function calling and conversation history."""

    # Retrieve conversation history
    conversation_history = retrieve_conversation_history(phone)

    # Construct the prompt with conversation history
    prompt = f"""
You are a helpful personal assistant. You have the personality of Jarvis from Iron Man, but with a tiny bit of sarcasm and sass when the mood calls for it. You can perform tasks like playing music, sending emails, and creating calendar events.
If the user asks you to play music, send an email, or create a calendar event, you MUST Always use the available functions 1st before instead of replying with text. Your name is Wednesday
Here's the conversation history:
{' '.join(conversation_history)}

User: {user_message}
"""

    # Thread-safe timeout for Gemini API call
    timeout_occurred = threading.Event()
    response = None
    exception_info = None
    
    def api_call():
        nonlocal response, exception_info
        try:
            response = model.generate_content(
                contents=[
                    {"role": "model", "parts": [PERSONALITY_PROMPT]},
                    {"role": "user", "parts": [prompt]}
                ],
                tools=[{"function_declarations": FUNCTIONS}],
                tool_config={"function_calling_config": {"mode": "auto"}}
            )
        except Exception as e:
            exception_info = e
    
    # Start API call in thread
    api_thread = threading.Thread(target=api_call)
    api_thread.daemon = True
    api_thread.start()
    
    # Wait for completion or timeout
    api_thread.join(timeout=30)
    
    if api_thread.is_alive():
        # Timeout occurred
        logging.getLogger("WhatsAppAssistant").error("Gemini API call timed out")
        add_to_conversation_history(phone, "user", user_message)
        add_to_conversation_history(phone, "assistant", "Sorry, I'm experiencing delays. Please try again.")
        return {"name": None, "content": "Sorry, I'm experiencing delays. Please try again."}
    
    if exception_info:
        # API call failed
        logging.getLogger("WhatsAppAssistant").error(f"Gemini API error: {exception_info}")
        add_to_conversation_history(phone, "user", user_message)
        add_to_conversation_history(phone, "assistant", f"API Error: {exception_info}")
        return {"name": None, "content": "Sorry, I encountered an API error."}
    
    if response:
        logging.getLogger("WhatsAppAssistant").debug(f"Gemini raw response: {response}")

    # Try to extract function call or text robustly
    try:
        part = response.candidates[0].content.parts[0]
        if hasattr(part, "function_call") and part.function_call:
            args = part.function_call.args
            # Convert MapComposite to dict if needed
            if hasattr(args, "to_dict"):
                params = args.to_dict()
            elif isinstance(args, str):
                params = json.loads(args)
            else:
                params = args or {}
            call = {
                "name": part.function_call.name,
                "parameters": params
            }
            # Add the user message and Gemini's response to the conversation history *before* returning
            add_to_conversation_history(phone, "user", user_message)
            add_to_conversation_history(phone, "assistant", f"Function call: {part.function_call.name}({params})")
            return call
        # Try to get text content robustly
        text = getattr(part, "text", None)
        if text:
            # Add the user message and Gemini's response to the conversation history *before* returning
            add_to_conversation_history(phone, "user", user_message)
            add_to_conversation_history(phone, "assistant", text)
            return {"name": None, "content": text}
    except Exception as e:
        logging.getLogger("WhatsAppAssistant").error(f"Error parsing Gemini response: {e}")
        # Add the user message and error message to the conversation history
        add_to_conversation_history(phone, "user", user_message)
        add_to_conversation_history(phone, "assistant", f"Error: {e}")
        return {"name": None, "content": "Sorry, I encountered an error."}

    # Try fallback: check for .text on response itself
    text = getattr(response, "text", None)
    if text:
        # Add the user message and Gemini's response to the conversation history *before* returning
        add_to_conversation_history(phone, "user", user_message)
        add_to_conversation_history(phone, "assistant", text)
        return {"name": None, "content": text}

    # Add the user message and default response to the conversation history
    add_to_conversation_history(phone, "user", user_message)
    add_to_conversation_history(phone, "assistant", "Sorry, I couldn't understand or generate a response.")
    return {"name": None, "content": "Sorry, I couldn't understand or generate a response."}

def execute_function(call: dict, phone: str = "") -> str:
    name = call.get("name")
    params = call.get("parameters", {})
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
        
        # Shopping and Paxi functions
        if name == "add_to_cart":
            item = {
                "name": params["name"],
                "price": params["price"],
                "quantity": params.get("quantity", 1),
                "description": params.get("description", "")
            }
            return order_manager.add_to_cart(phone, item)
        
        if name == "view_cart":
            return order_manager.view_cart(phone)
        
        if name == "clear_cart":
            return order_manager.clear_cart(phone)
        
        if name == "find_paxi_pickup_points":
            return paxi_service.find_pickup_points(
                params.get("location", ""),
                "",  # suburb
                params.get("city", "Cape Town")
            )
        
        if name == "checkout_with_paxi":
            customer_details = {
                "name": params["customer_name"],
                "phone": params["customer_phone"],
                "email": params.get("customer_email", "")
            }
            
            result = order_manager.checkout_with_paxi(
                phone, 
                params["pickup_point_id"], 
                customer_details
            )
            
            if result.get("success"):
                # Format order for WhatsApp and return for messaging
                order_message = order_manager.format_order_for_whatsapp(result["order"])
                
                # Try to send WhatsApp order confirmation
                try:
                    contact_manager.send_whatsapp_message(phone, order_message)
                    return f"✅ Order placed successfully! Paxi tracking: {result.get('paxi_tracking')}\n\nOrder confirmation sent via WhatsApp."
                except Exception as e:
                    return f"✅ Order placed successfully! Paxi tracking: {result.get('paxi_tracking')}\n\n{order_message}"
            else:
                return f"❌ Checkout failed: {result.get('error')}"
        
        if name == "track_paxi_delivery":
            return paxi_service.track_delivery(params["tracking_number"])
        
        if name == "get_delivery_options":
            return paxi_service.format_delivery_options()
        
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
        if name == "send_whatsapp_message":
            return contact_manager.send_whatsapp_message(
                params["contact_query"],
                params["message"]
            )
        
        if name == "get_contact_for_whatsapp":
            return contact_manager.get_contact_for_whatsapp(params["contact_query"])

        return "I couldn't handle that function call."
    except Exception as e:
        return f"Error executing {name}: {e}"
