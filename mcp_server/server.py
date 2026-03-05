#!/usr/bin/env python3
"""
Wednesday WhatsApp Assistant - MCP Server

Exposes the assistant's functionality as MCP tools for AI consumption.
Simplifies the complex codebase into a clean, structured API.

Run: python -m mcp_server.server
Or:  uvx mcp run mcp_server/server.py
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# MCP SDK imports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
    ListToolsResult,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wednesday-mcp")

# Initialize MCP server
server = Server("wednesday-assistant")

# ============================================
# Service Imports (lazy loaded)
# ============================================

_services_loaded = False
_bytez_handler = None
_gmail_service = None
_calendar_service = None
_spotify_service = None
_task_manager = None
_contact_manager = None
_weather_service = None
_news_service = None
_db_manager = None


def load_services():
    """Lazy load services to avoid startup overhead"""
    global _services_loaded, _bytez_handler, _gmail_service, _calendar_service
    global _spotify_service, _task_manager, _contact_manager, _weather_service
    global _news_service, _db_manager
    
    if _services_loaded:
        return
    
    try:
        from handlers.bytez_handler import bytez_handler
        _bytez_handler = bytez_handler
    except ImportError as e:
        logger.warning(f"Bytez handler not available: {e}")
    
    try:
        from handlers.gmail import GmailService
        _gmail_service = GmailService()
    except Exception as e:
        logger.warning(f"Gmail service not available: {e}")
    
    try:
        from handlers.calendar import CalendarService
        _calendar_service = CalendarService()
    except Exception as e:
        logger.warning(f"Calendar service not available: {e}")
    
    try:
        from handlers.spotify import SpotifyHandler
        _spotify_service = SpotifyHandler()
    except Exception as e:
        logger.warning(f"Spotify service not available: {e}")
    
    try:
        from handlers.tasks import task_manager
        _task_manager = task_manager
    except Exception as e:
        logger.warning(f"Task manager not available: {e}")
    
    try:
        from handlers.contacts import contact_manager
        _contact_manager = contact_manager
    except Exception as e:
        logger.warning(f"Contact manager not available: {e}")
    
    try:
        from handlers.weather import weather_service
        _weather_service = weather_service
    except Exception as e:
        logger.warning(f"Weather service not available: {e}")
    
    try:
        from handlers.news import news_service
        _news_service = news_service
    except Exception as e:
        logger.warning(f"News service not available: {e}")
    
    try:
        from database import db_manager
        _db_manager = db_manager
    except Exception as e:
        logger.warning(f"Database manager not available: {e}")
    
    _services_loaded = True
    logger.info("Services loaded successfully")


# ============================================
# Tool Definitions
# ============================================

TOOLS = [
    # === AI/Chat Tools ===
    Tool(
        name="chat",
        description="Send a message to the Wednesday AI assistant and get a response. Uses Bytez AI with 175k+ models.",
        inputSchema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message to send to the AI"
                },
                "phone": {
                    "type": "string",
                    "description": "Phone number for context (optional)",
                    "default": "mcp_user"
                },
                "include_history": {
                    "type": "boolean",
                    "description": "Include conversation history",
                    "default": True
                }
            },
            "required": ["message"]
        }
    ),
    
    # === WhatsApp Messaging Tools ===
    Tool(
        name="send_whatsapp",
        description="Send a WhatsApp message to a phone number or contact name",
        inputSchema={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Phone number (with country code) or contact name"
                },
                "message": {
                    "type": "string",
                    "description": "Message content to send"
                }
            },
            "required": ["to", "message"]
        }
    ),
    
    # === Calendar Tools ===
    Tool(
        name="get_calendar_events",
        description="Get upcoming calendar events from Google Calendar",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look ahead",
                    "default": 7
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of events to return",
                    "default": 10
                }
            }
        }
    ),
    Tool(
        name="create_calendar_event",
        description="Create a new calendar event",
        inputSchema={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Event title"
                },
                "start_time": {
                    "type": "string",
                    "description": "Start time in ISO format (YYYY-MM-DDTHH:MM:SS)"
                },
                "end_time": {
                    "type": "string",
                    "description": "End time in ISO format (optional, defaults to 1 hour after start)"
                },
                "description": {
                    "type": "string",
                    "description": "Event description (optional)"
                },
                "location": {
                    "type": "string",
                    "description": "Event location (optional)"
                }
            },
            "required": ["title", "start_time"]
        }
    ),
    
    # === Email Tools ===
    Tool(
        name="get_emails",
        description="Get recent emails from Gmail inbox",
        inputSchema={
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of emails to return",
                    "default": 10
                },
                "query": {
                    "type": "string",
                    "description": "Gmail search query (optional)"
                },
                "unread_only": {
                    "type": "boolean",
                    "description": "Only return unread emails",
                    "default": False
                }
            }
        }
    ),
    Tool(
        name="send_email",
        description="Send an email via Gmail",
        inputSchema={
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address"
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject"
                },
                "body": {
                    "type": "string",
                    "description": "Email body content"
                }
            },
            "required": ["to", "subject", "body"]
        }
    ),
    
    # === Task Management Tools ===
    Tool(
        name="get_tasks",
        description="Get all tasks and reminders",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status: all, pending, completed",
                    "enum": ["all", "pending", "completed"],
                    "default": "all"
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (optional)"
                }
            }
        }
    ),
    Tool(
        name="create_task",
        description="Create a new task or reminder",
        inputSchema={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Task title"
                },
                "description": {
                    "type": "string",
                    "description": "Task description (optional)"
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date in ISO format (optional)"
                },
                "priority": {
                    "type": "string",
                    "description": "Priority level",
                    "enum": ["low", "medium", "high"],
                    "default": "medium"
                },
                "category": {
                    "type": "string",
                    "description": "Task category (optional)"
                }
            },
            "required": ["title"]
        }
    ),
    Tool(
        name="complete_task",
        description="Mark a task as completed",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "ID of the task to complete"
                }
            },
            "required": ["task_id"]
        }
    ),
    
    # === Contact Tools ===
    Tool(
        name="search_contacts",
        description="Search for contacts by name, phone, or email",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (name, phone number, or email)"
                }
            },
            "required": ["query"]
        }
    ),
    Tool(
        name="add_contact",
        description="Add a new contact",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Contact name"
                },
                "phone": {
                    "type": "string",
                    "description": "Phone number"
                },
                "email": {
                    "type": "string",
                    "description": "Email address (optional)"
                }
            },
            "required": ["name", "phone"]
        }
    ),
    
    # === Spotify Tools ===
    Tool(
        name="spotify_play",
        description="Play music on Spotify - search and play a track, artist, album, or playlist",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (song name, artist, album, or playlist)"
                },
                "type": {
                    "type": "string",
                    "description": "Type of content to search",
                    "enum": ["track", "artist", "album", "playlist"],
                    "default": "track"
                }
            },
            "required": ["query"]
        }
    ),
    Tool(
        name="spotify_control",
        description="Control Spotify playback (play, pause, skip, previous, volume)",
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Playback action",
                    "enum": ["play", "pause", "next", "previous", "shuffle_on", "shuffle_off", "repeat_track", "repeat_off"]
                },
                "volume": {
                    "type": "integer",
                    "description": "Volume level 0-100 (only used with volume action)",
                    "minimum": 0,
                    "maximum": 100
                }
            },
            "required": ["action"]
        }
    ),
    Tool(
        name="spotify_now_playing",
        description="Get currently playing track on Spotify",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    
    # === Weather Tools ===
    Tool(
        name="get_weather",
        description="Get current weather and forecast for a location",
        inputSchema={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name or location"
                },
                "days": {
                    "type": "integer",
                    "description": "Number of forecast days (1-7)",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 7
                }
            },
            "required": ["location"]
        }
    ),
    
    # === News Tools ===
    Tool(
        name="get_news",
        description="Get latest news headlines",
        inputSchema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "News category",
                    "enum": ["general", "business", "technology", "sports", "entertainment", "health", "science"],
                    "default": "general"
                },
                "query": {
                    "type": "string",
                    "description": "Search query for specific news (optional)"
                },
                "count": {
                    "type": "integer",
                    "description": "Number of articles to return",
                    "default": 5,
                    "maximum": 20
                }
            }
        }
    ),
    
    # === Memory/History Tools ===
    Tool(
        name="search_memory",
        description="Search conversation history and stored information",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "phone": {
                    "type": "string",
                    "description": "Phone number to search history for",
                    "default": "mcp_user"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    ),
    
    # === System Tools ===
    Tool(
        name="service_status",
        description="Get the status of all Wednesday assistant services",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
]


# ============================================
# Tool Handlers
# ============================================

@server.list_tools()
async def list_tools() -> ListToolsResult:
    """Return list of available tools"""
    return ListToolsResult(tools=TOOLS)


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    """Handle tool calls"""
    load_services()
    
    try:
        result = await handle_tool(name, arguments)
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
        )
    except Exception as e:
        logger.error(f"Error handling tool {name}: {e}")
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps({
                "error": str(e),
                "tool": name
            }))]
        )


async def handle_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Route tool calls to appropriate handlers"""
    
    # === AI/Chat ===
    if name == "chat":
        return await handle_chat(args)
    
    # === WhatsApp ===
    elif name == "send_whatsapp":
        return await handle_send_whatsapp(args)
    
    # === Calendar ===
    elif name == "get_calendar_events":
        return await handle_get_calendar_events(args)
    elif name == "create_calendar_event":
        return await handle_create_calendar_event(args)
    
    # === Email ===
    elif name == "get_emails":
        return await handle_get_emails(args)
    elif name == "send_email":
        return await handle_send_email(args)
    
    # === Tasks ===
    elif name == "get_tasks":
        return await handle_get_tasks(args)
    elif name == "create_task":
        return await handle_create_task(args)
    elif name == "complete_task":
        return await handle_complete_task(args)
    
    # === Contacts ===
    elif name == "search_contacts":
        return await handle_search_contacts(args)
    elif name == "add_contact":
        return await handle_add_contact(args)
    
    # === Spotify ===
    elif name == "spotify_play":
        return await handle_spotify_play(args)
    elif name == "spotify_control":
        return await handle_spotify_control(args)
    elif name == "spotify_now_playing":
        return await handle_spotify_now_playing(args)
    
    # === Weather ===
    elif name == "get_weather":
        return await handle_get_weather(args)
    
    # === News ===
    elif name == "get_news":
        return await handle_get_news(args)
    
    # === Memory ===
    elif name == "search_memory":
        return await handle_search_memory(args)
    
    # === System ===
    elif name == "service_status":
        return await handle_service_status(args)
    
    else:
        raise ValueError(f"Unknown tool: {name}")


# ============================================
# Tool Handler Implementations
# ============================================

async def handle_chat(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle AI chat"""
    if not _bytez_handler:
        return {"error": "AI service not available", "hint": "Set BYTEZ_API_KEY in environment"}
    
    message = args.get("message")
    phone = args.get("phone", "mcp_user")
    include_history = args.get("include_history", True)
    
    # Get conversation history if requested
    context = ""
    if include_history and _db_manager:
        try:
            history = _db_manager.get_conversation_history(phone, limit=5)
            if history:
                context = "\n".join(history)
        except Exception as e:
            logger.warning(f"Could not load history: {e}")
    
    # Call AI
    try:
        response = _bytez_handler.chat(message, context=context)
        
        # Store conversation
        if _db_manager:
            _db_manager.add_conversation(phone, "user", message)
            _db_manager.add_conversation(phone, "assistant", response)
        
        return {
            "response": response,
            "model": os.getenv("BYTEZ_CHAT_MODEL", "Qwen/Qwen3-4B")
        }
    except Exception as e:
        return {"error": f"AI error: {str(e)}"}


async def handle_send_whatsapp(args: Dict[str, Any]) -> Dict[str, Any]:
    """Send WhatsApp message"""
    import requests
    
    to = args.get("to")
    message = args.get("message")
    
    # Check if 'to' is a contact name
    if _contact_manager and not to.startswith("+"):
        contact = _contact_manager.find_contact(to)
        if contact:
            to = contact.get("phone", to)
    
    waha_url = os.getenv("WAHA_URL", "http://localhost:3000/api/sendText")
    
    try:
        response = requests.post(waha_url, json={
            "chatId": f"{to}@c.us" if not to.endswith("@c.us") else to,
            "text": message,
            "session": "default"
        }, timeout=10)
        
        if response.ok:
            return {"success": True, "to": to, "message": message}
        else:
            return {"error": f"Failed to send: {response.text}"}
    except Exception as e:
        return {"error": f"WhatsApp service error: {str(e)}"}


async def handle_get_calendar_events(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get calendar events"""
    if not _calendar_service:
        return {"error": "Calendar service not available", "hint": "Configure Google OAuth"}
    
    days = args.get("days", 7)
    max_results = args.get("max_results", 10)
    
    try:
        events = _calendar_service.get_upcoming_events(days=days, max_results=max_results)
        return {"events": events, "count": len(events)}
    except Exception as e:
        return {"error": f"Calendar error: {str(e)}"}


async def handle_create_calendar_event(args: Dict[str, Any]) -> Dict[str, Any]:
    """Create calendar event"""
    if not _calendar_service:
        return {"error": "Calendar service not available"}
    
    try:
        event = _calendar_service.create_event(
            summary=args.get("title"),
            start_time=args.get("start_time"),
            end_time=args.get("end_time"),
            description=args.get("description"),
            location=args.get("location")
        )
        return {"success": True, "event": event}
    except Exception as e:
        return {"error": f"Failed to create event: {str(e)}"}


async def handle_get_emails(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get emails from Gmail"""
    if not _gmail_service:
        return {"error": "Gmail service not available", "hint": "Configure Google OAuth"}
    
    try:
        emails = _gmail_service.get_messages(
            max_results=args.get("max_results", 10),
            query=args.get("query", ""),
            unread_only=args.get("unread_only", False)
        )
        return {"emails": emails, "count": len(emails)}
    except Exception as e:
        return {"error": f"Gmail error: {str(e)}"}


async def handle_send_email(args: Dict[str, Any]) -> Dict[str, Any]:
    """Send email via Gmail"""
    if not _gmail_service:
        return {"error": "Gmail service not available"}
    
    try:
        result = _gmail_service.send_email(
            to=args.get("to"),
            subject=args.get("subject"),
            body=args.get("body")
        )
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": f"Failed to send email: {str(e)}"}


async def handle_get_tasks(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get tasks"""
    if not _task_manager:
        return {"error": "Task manager not available"}
    
    try:
        tasks = _task_manager.get_tasks(
            status=args.get("status", "all"),
            category=args.get("category")
        )
        return {"tasks": tasks, "count": len(tasks)}
    except Exception as e:
        return {"error": f"Task error: {str(e)}"}


async def handle_create_task(args: Dict[str, Any]) -> Dict[str, Any]:
    """Create task"""
    if not _task_manager:
        return {"error": "Task manager not available"}
    
    try:
        task = _task_manager.create_task(
            title=args.get("title"),
            description=args.get("description"),
            due_date=args.get("due_date"),
            priority=args.get("priority", "medium"),
            category=args.get("category")
        )
        return {"success": True, "task": task}
    except Exception as e:
        return {"error": f"Failed to create task: {str(e)}"}


async def handle_complete_task(args: Dict[str, Any]) -> Dict[str, Any]:
    """Complete task"""
    if not _task_manager:
        return {"error": "Task manager not available"}
    
    try:
        result = _task_manager.complete_task(args.get("task_id"))
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": f"Failed to complete task: {str(e)}"}


async def handle_search_contacts(args: Dict[str, Any]) -> Dict[str, Any]:
    """Search contacts"""
    if not _contact_manager:
        return {"error": "Contact manager not available"}
    
    try:
        contacts = _contact_manager.search(args.get("query"))
        return {"contacts": contacts, "count": len(contacts)}
    except Exception as e:
        return {"error": f"Contact search error: {str(e)}"}


async def handle_add_contact(args: Dict[str, Any]) -> Dict[str, Any]:
    """Add contact"""
    if not _contact_manager:
        return {"error": "Contact manager not available"}
    
    try:
        contact = _contact_manager.add_contact(
            name=args.get("name"),
            phone=args.get("phone"),
            email=args.get("email")
        )
        return {"success": True, "contact": contact}
    except Exception as e:
        return {"error": f"Failed to add contact: {str(e)}"}


async def handle_spotify_play(args: Dict[str, Any]) -> Dict[str, Any]:
    """Play Spotify content"""
    if not _spotify_service:
        return {"error": "Spotify not available", "hint": "Configure Spotify OAuth"}
    
    try:
        result = _spotify_service.search_and_play(
            query=args.get("query"),
            content_type=args.get("type", "track")
        )
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": f"Spotify error: {str(e)}"}


async def handle_spotify_control(args: Dict[str, Any]) -> Dict[str, Any]:
    """Control Spotify playback"""
    if not _spotify_service:
        return {"error": "Spotify not available"}
    
    action = args.get("action")
    
    try:
        if action == "play":
            result = _spotify_service.resume()
        elif action == "pause":
            result = _spotify_service.pause()
        elif action == "next":
            result = _spotify_service.next_track()
        elif action == "previous":
            result = _spotify_service.previous_track()
        elif action == "shuffle_on":
            result = _spotify_service.set_shuffle(True)
        elif action == "shuffle_off":
            result = _spotify_service.set_shuffle(False)
        elif action == "repeat_track":
            result = _spotify_service.set_repeat("track")
        elif action == "repeat_off":
            result = _spotify_service.set_repeat("off")
        else:
            return {"error": f"Unknown action: {action}"}
        
        return {"success": True, "action": action, "result": result}
    except Exception as e:
        return {"error": f"Spotify control error: {str(e)}"}


async def handle_spotify_now_playing(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get currently playing Spotify track"""
    if not _spotify_service:
        return {"error": "Spotify not available"}
    
    try:
        track = _spotify_service.get_current_track()
        return {"now_playing": track}
    except Exception as e:
        return {"error": f"Spotify error: {str(e)}"}


async def handle_get_weather(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get weather"""
    if not _weather_service:
        return {"error": "Weather service not available"}
    
    try:
        weather = _weather_service.get_weather(
            location=args.get("location"),
            days=args.get("days", 1)
        )
        return {"weather": weather}
    except Exception as e:
        return {"error": f"Weather error: {str(e)}"}


async def handle_get_news(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get news"""
    if not _news_service:
        return {"error": "News service not available"}
    
    try:
        news = _news_service.get_headlines(
            category=args.get("category", "general"),
            query=args.get("query"),
            count=args.get("count", 5)
        )
        return {"articles": news, "count": len(news)}
    except Exception as e:
        return {"error": f"News error: {str(e)}"}


async def handle_search_memory(args: Dict[str, Any]) -> Dict[str, Any]:
    """Search conversation history"""
    if not _db_manager:
        return {"error": "Database not available"}
    
    try:
        results = _db_manager.search_conversations(
            phone=args.get("phone", "mcp_user"),
            query=args.get("query"),
            limit=args.get("limit", 10)
        )
        return {"results": results, "count": len(results)}
    except Exception as e:
        return {"error": f"Search error: {str(e)}"}


async def handle_service_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get service status"""
    return {
        "services": {
            "ai": "available" if _bytez_handler else "unavailable",
            "gmail": "available" if _gmail_service else "unavailable",
            "calendar": "available" if _calendar_service else "unavailable",
            "spotify": "available" if _spotify_service else "unavailable",
            "tasks": "available" if _task_manager else "unavailable",
            "contacts": "available" if _contact_manager else "unavailable",
            "weather": "available" if _weather_service else "unavailable",
            "news": "available" if _news_service else "unavailable",
            "database": "available" if _db_manager else "unavailable"
        },
        "environment": {
            "bytez_configured": bool(os.getenv("BYTEZ_API_KEY")),
            "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
            "spotify_configured": bool(os.getenv("SPOTIFY_CLIENT_ID")),
            "waha_url": os.getenv("WAHA_URL", "not configured")
        },
        "version": "1.0.0"
    }


# ============================================
# Main Entry Point
# ============================================

async def main():
    """Run the MCP server"""
    logger.info("Starting Wednesday MCP Server...")
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
