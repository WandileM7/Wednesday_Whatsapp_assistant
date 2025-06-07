import google.generativeai as genai
import json
from config import GEMINI_API_KEY, PERSONALITY_PROMPT
from handlers.spotify import play_album, play_playlist, play_song, get_current_song
from handlers.gmail import send_email, summarize_emails
from handlers.calendar import create_event
import logging
from chromedb import *
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

    response = model.generate_content(
        contents=[
            {"role": "model", "parts": [PERSONALITY_PROMPT]},
            {"role": "user", "parts": [prompt]}
        ],
        tools=[{"function_declarations": FUNCTIONS}],
        tool_config={"function_calling_config": {"mode": "auto"}}
    )
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
        if name == "play_song":
            return play_song(params["song_name"])
        if name == "get_current_song":
            return get_current_song()
        if name == "send_email":
            return send_email(params["to"], params["subject"], params["body"])
        if name == "play_playlist":
            return play_playlist(params["playlist_name"])
        if name == "play_album":
            return play_album(params["album_name"])
        if name == "summarize_emails":
            return summarize_emails()
        if name == "create_event":
            return create_event(
                params["summary"],
                params.get("location", ""),
                params["start_time"],
                params["end_time"],
                params.get("attendees", [])
            )

        return "I couldn't handle that function call."
    except Exception as e:
        return f"Error executing {name}: {e}"
