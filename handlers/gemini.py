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

def execute_function(call: dict) -> str:
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

        return "I couldn't handle that function call."
    except Exception as e:
        return f"Error executing {name}: {e}"
