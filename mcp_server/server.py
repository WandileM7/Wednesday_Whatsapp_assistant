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
# JARVIS Services
_workflow_engine = None
_smart_home = None
_elevenlabs = None
_long_term_memory = None
_security_monitor = None
_fitness_service = None
_expense_service = None
_daily_briefing = None
_jarvis_core = None
_mood_music = None
_media_generator = None


def load_services():
    """Lazy load services to avoid startup overhead"""
    global _services_loaded, _bytez_handler, _gmail_service, _calendar_service
    global _spotify_service, _task_manager, _contact_manager, _weather_service
    global _news_service, _db_manager
    # JARVIS globals
    global _workflow_engine, _smart_home, _elevenlabs, _long_term_memory
    global _security_monitor, _fitness_service, _expense_service, _daily_briefing
    global _jarvis_core, _mood_music, _media_generator
    
    if _services_loaded:
        return
    
    try:
        from handlers.bytez_handler import chat_with_functions, generate_image as bytez_generate_image
        _bytez_handler = True  # Flag to indicate bytez is available
    except ImportError as e:
        logger.warning(f"Bytez handler not available: {e}")
    
    try:
        from handlers.gmail import get_gmail_service, list_emails, send_email as gmail_send_email
        _gmail_service = True  # Flag to indicate gmail is available
    except Exception as e:
        logger.warning(f"Gmail service not available: {e}")
    
    try:
        from handlers.calendar import get_calendar_service, list_events, create_event as calendar_create_event
        _calendar_service = True  # Flag to indicate calendar is available
    except Exception as e:
        logger.warning(f"Calendar service not available: {e}")
    
    try:
        from handlers.spotify import play_song, play_album, play_playlist, get_current_song
        _spotify_service = True  # Flag to indicate spotify is available
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
    
    # ============================================
    # JARVIS Services
    # ============================================
    
    try:
        from handlers.workflows import workflow_engine
        _workflow_engine = workflow_engine
    except Exception as e:
        logger.warning(f"Workflow engine not available: {e}")
    
    try:
        from handlers.smart_home import smart_home
        _smart_home = smart_home
    except Exception as e:
        logger.warning(f"Smart home not available: {e}")
    
    try:
        from handlers.elevenlabs_voice import elevenlabs_voice
        _elevenlabs = elevenlabs_voice
    except Exception as e:
        logger.warning(f"ElevenLabs not available: {e}")
    
    try:
        from handlers.long_term_memory import long_term_memory
        _long_term_memory = long_term_memory
    except Exception as e:
        logger.warning(f"Long-term memory not available: {e}")
    
    try:
        from handlers.security import security_monitor
        _security_monitor = security_monitor
    except Exception as e:
        logger.warning(f"Security monitor not available: {e}")
    
    try:
        from handlers.fitness import fitness_service
        _fitness_service = fitness_service
    except Exception as e:
        logger.warning(f"Fitness service not available: {e}")
    
    try:
        from handlers.expenses import expense_service
        _expense_service = expense_service
    except Exception as e:
        logger.warning(f"Expense service not available: {e}")
    
    try:
        from handlers.daily_briefing import generate_daily_briefing, schedule_daily_briefing, cancel_daily_briefing
        _daily_briefing = True  # Flag to indicate daily briefing is available
    except Exception as e:
        logger.warning(f"Daily briefing not available: {e}")
    
    try:
        from handlers.jarvis_core import JARVISCore
        _jarvis_core = JARVISCore()
    except Exception as e:
        logger.warning(f"JARVIS core not available: {e}")
    
    try:
        from handlers.mood_music import mood_music_service
        _mood_music = mood_music_service
    except Exception as e:
        logger.warning(f"Mood music not available: {e}")
    
    try:
        from handlers.media_generator import media_generator
        _media_generator = media_generator
    except Exception as e:
        logger.warning(f"Media generator not available: {e}")
    
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
    
    # ============================================
    # JARVIS ADVANCED TOOLS
    # ============================================
    
    # === Workflow Automation Tools ===
    Tool(
        name="run_workflow",
        description="Run an automated JARVIS workflow like morning_routine, prepare_meeting, end_of_day, focus_mode, leaving_home, coming_home, party_mode, sleep_mode",
        inputSchema={
            "type": "object",
            "properties": {
                "workflow": {
                    "type": "string",
                    "description": "Workflow name: morning_routine, prepare_meeting, end_of_day, focus_mode, leaving_home, coming_home, party_mode, sleep_mode",
                    "enum": ["morning_routine", "prepare_meeting", "end_of_day", "focus_mode", "leaving_home", "coming_home", "party_mode", "sleep_mode"]
                },
                "duration": {
                    "type": "integer",
                    "description": "Duration in minutes (for focus_mode)"
                },
                "location": {
                    "type": "string",
                    "description": "Location for weather in briefings"
                }
            },
            "required": ["workflow"]
        }
    ),
    Tool(
        name="list_workflows",
        description="List all available JARVIS automation workflows with descriptions",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    
    # === Smart Home Control Tools ===
    Tool(
        name="smart_home_lights",
        description="Control smart home lights - turn on/off, set brightness, change colors",
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: on, off, dim",
                    "enum": ["on", "off", "dim"]
                },
                "brightness": {
                    "type": "integer",
                    "description": "Brightness level 0-100",
                    "minimum": 0,
                    "maximum": 100
                },
                "room": {
                    "type": "string",
                    "description": "Room name (or 'all' for all rooms)"
                },
                "color": {
                    "type": "string",
                    "description": "Color: red, blue, green, warm, cool, white, purple, orange"
                }
            },
            "required": ["action"]
        }
    ),
    Tool(
        name="smart_home_thermostat",
        description="Control smart home thermostat - set temperature and mode",
        inputSchema={
            "type": "object",
            "properties": {
                "temperature": {
                    "type": "integer",
                    "description": "Temperature in Fahrenheit (60-85)"
                },
                "mode": {
                    "type": "string",
                    "description": "Mode: heat, cool, auto, off",
                    "enum": ["heat", "cool", "auto", "off"]
                }
            },
            "required": ["temperature"]
        }
    ),
    Tool(
        name="smart_home_scene",
        description="Activate a smart home scene preset",
        inputSchema={
            "type": "object",
            "properties": {
                "scene": {
                    "type": "string",
                    "description": "Scene: movie, work, sleep, morning, party, romantic, focus, away",
                    "enum": ["movie", "work", "sleep", "morning", "party", "romantic", "focus", "away"]
                }
            },
            "required": ["scene"]
        }
    ),
    Tool(
        name="smart_home_locks",
        description="Control smart door locks - lock or unlock",
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: lock or unlock",
                    "enum": ["lock", "unlock"]
                },
                "door": {
                    "type": "string",
                    "description": "Door name (or 'all' for all doors)"
                }
            },
            "required": ["action"]
        }
    ),
    Tool(
        name="smart_home_status",
        description="Get comprehensive smart home status - all devices, integrations, and states",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    
    # === ElevenLabs Voice Tools ===
    Tool(
        name="speak_this",
        description="Use premium ElevenLabs AI voice to speak text aloud with natural intonation",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to speak"
                },
                "voice": {
                    "type": "string",
                    "description": "Voice preset: jarvis (default), friday, butler",
                    "enum": ["jarvis", "friday", "butler"]
                },
                "style": {
                    "type": "string",
                    "description": "Speaking style: natural, dramatic, calm, urgent"
                }
            },
            "required": ["text"]
        }
    ),
    Tool(
        name="change_voice",
        description="Change the assistant's voice to a different preset",
        inputSchema={
            "type": "object",
            "properties": {
                "voice": {
                    "type": "string",
                    "description": "Voice preset: jarvis, friday, butler",
                    "enum": ["jarvis", "friday", "butler"]
                }
            },
            "required": ["voice"]
        }
    ),
    Tool(
        name="voice_status",
        description="Get ElevenLabs voice status including usage and available voices",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    Tool(
        name="toggle_voice_mode",
        description="Enable or disable voice message responses. When ON, all assistant responses are sent as voice messages. When OFF, voice only for voice input.",
        inputSchema={
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "description": "True to enable always-voice mode, False to disable"
                },
                "caller_phone": {
                    "type": "string",
                    "description": "User's phone number (auto-injected)"
                }
            },
            "required": ["enabled"]
        }
    ),
    
    # === Long-term Memory Tools ===
    Tool(
        name="remember_this",
        description="Store information in JARVIS long-term memory for future recall (e.g., preferences, facts, events)",
        inputSchema={
            "type": "object",
            "properties": {
                "information": {
                    "type": "string",
                    "description": "Information to remember"
                },
                "category": {
                    "type": "string",
                    "description": "Category: personal, task, preference, event, topic, instruction, relationship, location",
                    "enum": ["personal", "task", "preference", "event", "topic", "instruction", "relationship", "location"]
                },
                "importance": {
                    "type": "string",
                    "description": "Importance level: low, medium, high",
                    "enum": ["low", "medium", "high"]
                }
            },
            "required": ["information"]
        }
    ),
    Tool(
        name="recall_memory",
        description="Recall information from JARVIS long-term memory about a specific topic",
        inputSchema={
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic or query to recall"
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (optional)"
                }
            },
            "required": ["topic"]
        }
    ),
    Tool(
        name="forget_memory",
        description="Remove specific memories or all memories in a category",
        inputSchema={
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic or category to forget"
                }
            },
            "required": ["topic"]
        }
    ),
    Tool(
        name="get_user_profile",
        description="Get complete user profile including preferences, learned facts, and memory statistics",
        inputSchema={
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "description": "Phone number (optional, defaults to mcp_user)"
                }
            }
        }
    ),
    Tool(
        name="memory_stats",
        description="Get memory system statistics - total memories, categories, storage usage",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    
    # === Security Tools ===
    Tool(
        name="security_status",
        description="Get current JARVIS security status including threat level and recent alerts",
        inputSchema={
            "type": "object",
            "properties": {}
        }
    ),
    Tool(
        name="security_report",
        description="Get detailed security report with threat analysis, anomalies, and recommendations",
        inputSchema={
            "type": "object",
            "properties": {
                "include_history": {
                    "type": "boolean",
                    "description": "Include historical security events",
                    "default": True
                }
            }
        }
    ),
    Tool(
        name="check_threat",
        description="Analyze a message or request for potential security threats",
        inputSchema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message to analyze for threats"
                }
            },
            "required": ["message"]
        }
    ),
    
    # === Admin/Owner Tools ===
    Tool(
        name="admin_status",
        description="[OWNER ONLY] Get comprehensive system admin status including owner info, whitelist, blocked users",
        inputSchema={
            "type": "object",
            "properties": {
                "caller_phone": {
                    "type": "string",
                    "description": "Phone number of the caller (for authorization)"
                }
            },
            "required": ["caller_phone"]
        }
    ),
    Tool(
        name="manage_whitelist",
        description="[OWNER ONLY] Add or remove users from the trusted whitelist",
        inputSchema={
            "type": "object",
            "properties": {
                "caller_phone": {
                    "type": "string",
                    "description": "Phone number of the caller (for authorization)"
                },
                "action": {
                    "type": "string",
                    "enum": ["add", "remove", "list"],
                    "description": "Action to perform on whitelist"
                },
                "target_phone": {
                    "type": "string",
                    "description": "Phone number to add/remove (not required for list)"
                }
            },
            "required": ["caller_phone", "action"]
        }
    ),
    Tool(
        name="manage_blocked",
        description="[OWNER ONLY] Block or unblock users from the system",
        inputSchema={
            "type": "object",
            "properties": {
                "caller_phone": {
                    "type": "string",
                    "description": "Phone number of the caller (for authorization)"
                },
                "action": {
                    "type": "string",
                    "enum": ["block", "unblock", "list"],
                    "description": "Action to perform"
                },
                "target_phone": {
                    "type": "string",
                    "description": "Phone number to block/unblock (not required for list)"
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for blocking (optional)"
                }
            },
            "required": ["caller_phone", "action"]
        }
    ),
    Tool(
        name="verify_owner",
        description="Check if the caller is the system owner/creator",
        inputSchema={
            "type": "object",
            "properties": {
                "caller_phone": {
                    "type": "string",
                    "description": "Phone number to verify"
                }
            },
            "required": ["caller_phone"]
        }
    ),
    
    # === Fitness Tools ===
    Tool(
        name="log_fitness",
        description="Log a fitness activity (workout, run, gym session, etc.)",
        inputSchema={
            "type": "object",
            "properties": {
                "activity_type": {
                    "type": "string",
                    "description": "Type: running, cycling, gym, swimming, walking, yoga, hiit, strength"
                },
                "duration": {
                    "type": "integer",
                    "description": "Duration in minutes"
                },
                "calories": {
                    "type": "integer",
                    "description": "Calories burned (optional)"
                },
                "distance": {
                    "type": "number",
                    "description": "Distance in km (optional)"
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes"
                }
            },
            "required": ["activity_type", "duration"]
        }
    ),
    Tool(
        name="get_fitness_summary",
        description="Get fitness summary for today or a specific date",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format (defaults to today)"
                }
            }
        }
    ),
    Tool(
        name="get_fitness_history",
        description="Get fitness activity history for the past N days",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back (default: 7)",
                    "default": 7
                }
            }
        }
    ),
    Tool(
        name="set_fitness_goal",
        description="Set a fitness goal (steps, calories, workouts per week, etc.)",
        inputSchema={
            "type": "object",
            "properties": {
                "goal_type": {
                    "type": "string",
                    "description": "Goal type: steps, calories, workouts, distance, weight"
                },
                "target": {
                    "type": "integer",
                    "description": "Target value"
                }
            },
            "required": ["goal_type", "target"]
        }
    ),
    
    # === Expense Tracking Tools ===
    Tool(
        name="add_expense",
        description="Record an expense (e.g., 'I spent R50 on groceries')",
        inputSchema={
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Amount spent"
                },
                "category": {
                    "type": "string",
                    "description": "Category: food, groceries, transport, entertainment, shopping, utilities, health, other",
                    "enum": ["food", "groceries", "transport", "entertainment", "shopping", "utilities", "health", "other"]
                },
                "description": {
                    "type": "string",
                    "description": "Description of the expense"
                }
            },
            "required": ["amount", "category"]
        }
    ),
    Tool(
        name="get_spending_report",
        description="Get spending report with breakdown by category",
        inputSchema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to analyze (default: 30)",
                    "default": 30
                }
            }
        }
    ),
    Tool(
        name="set_budget",
        description="Set a budget limit for a spending category",
        inputSchema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Spending category"
                },
                "limit": {
                    "type": "number",
                    "description": "Budget limit amount"
                },
                "period": {
                    "type": "string",
                    "description": "Period: daily, weekly, monthly",
                    "enum": ["daily", "weekly", "monthly"]
                }
            },
            "required": ["category", "limit"]
        }
    ),
    
    # === Daily Briefing Tools ===
    Tool(
        name="get_daily_briefing",
        description="Get comprehensive daily briefing with weather, calendar, tasks, emails, and news",
        inputSchema={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Location for weather (defaults to Johannesburg)"
                }
            }
        }
    ),
    Tool(
        name="schedule_briefing",
        description="Schedule automatic daily morning briefing at a specific time",
        inputSchema={
            "type": "object",
            "properties": {
                "hour": {
                    "type": "integer",
                    "description": "Hour to send briefing (0-23, default: 7)",
                    "minimum": 0,
                    "maximum": 23
                },
                "minute": {
                    "type": "integer",
                    "description": "Minute (0-59, default: 0)",
                    "minimum": 0,
                    "maximum": 59
                },
                "location": {
                    "type": "string",
                    "description": "Location for weather"
                },
                "phone": {
                    "type": "string",
                    "description": "Phone number to send briefing to"
                }
            }
        }
    ),
    Tool(
        name="cancel_briefing",
        description="Cancel the scheduled daily briefing",
        inputSchema={
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "description": "Phone number (optional)"
                }
            }
        }
    ),
    
    # === Mood Music Tools ===
    Tool(
        name="play_mood_music",
        description="Play music matching a specific mood or feeling",
        inputSchema={
            "type": "object",
            "properties": {
                "mood": {
                    "type": "string",
                    "description": "Mood: happy, sad, energetic, relaxed, focused, romantic, angry, nostalgic, party",
                    "enum": ["happy", "sad", "energetic", "relaxed", "focused", "romantic", "angry", "nostalgic", "party"]
                }
            },
            "required": ["mood"]
        }
    ),
    
    # === Media Generation Tools ===
    Tool(
        name="generate_image",
        description="Generate an image from text description using AI",
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Description of the image to generate"
                },
                "style": {
                    "type": "string",
                    "description": "Style: realistic, artistic, cartoon, professional, avatar",
                    "enum": ["realistic", "artistic", "cartoon", "professional", "avatar"]
                }
            },
            "required": ["prompt"]
        }
    ),
    Tool(
        name="generate_video",
        description="Generate video from text description using AI",
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Description of the video to generate"
                },
                "style": {
                    "type": "string",
                    "description": "Style: realistic, animated, cinematic",
                    "enum": ["realistic", "animated", "cinematic"]
                },
                "duration": {
                    "type": "integer",
                    "description": "Duration in seconds (1-10)",
                    "minimum": 1,
                    "maximum": 10
                }
            },
            "required": ["prompt"]
        }
    ),
    
    # === JARVIS Core Tools ===
    Tool(
        name="jarvis_greeting",
        description="Get a contextual JARVIS greeting based on time of day and situation",
        inputSchema={
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Current context or situation (optional)"
                }
            }
        }
    ),
    Tool(
        name="proactive_suggestions",
        description="Get proactive suggestions based on current context, time, and user patterns",
        inputSchema={
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Current context or user message"
                }
            }
        }
    ),
    Tool(
        name="jarvis_status",
        description="Get comprehensive JARVIS system status including all subsystems",
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
    
    # ============================================
    # JARVIS Advanced Tool Handlers
    # ============================================
    
    # === Workflows ===
    elif name == "run_workflow":
        return await handle_run_workflow(args)
    elif name == "list_workflows":
        return await handle_list_workflows(args)
    
    # === Smart Home ===
    elif name == "smart_home_lights":
        return await handle_smart_home_lights(args)
    elif name == "smart_home_thermostat":
        return await handle_smart_home_thermostat(args)
    elif name == "smart_home_scene":
        return await handle_smart_home_scene(args)
    elif name == "smart_home_locks":
        return await handle_smart_home_locks(args)
    elif name == "smart_home_status":
        return await handle_smart_home_status(args)
    
    # === ElevenLabs Voice ===
    elif name == "speak_this":
        return await handle_speak_this(args)
    elif name == "change_voice":
        return await handle_change_voice(args)
    elif name == "voice_status":
        return await handle_voice_status(args)
    elif name == "toggle_voice_mode":
        return await handle_toggle_voice_mode(args)
        return await handle_voice_status(args)
    
    # === Long-term Memory ===
    elif name == "remember_this":
        return await handle_remember_this(args)
    elif name == "recall_memory":
        return await handle_recall_memory(args)
    elif name == "forget_memory":
        return await handle_forget_memory(args)
    elif name == "get_user_profile":
        return await handle_get_user_profile(args)
    elif name == "memory_stats":
        return await handle_memory_stats(args)
    
    # === Security ===
    elif name == "security_status":
        return await handle_security_status(args)
    elif name == "security_report":
        return await handle_security_report(args)
    elif name == "check_threat":
        return await handle_check_threat(args)
    
    # === Admin/Owner ===
    elif name == "admin_status":
        return await handle_admin_status(args)
    elif name == "manage_whitelist":
        return await handle_manage_whitelist(args)
    elif name == "manage_blocked":
        return await handle_manage_blocked(args)
    elif name == "verify_owner":
        return await handle_verify_owner(args)
    
    # === Fitness ===
    elif name == "log_fitness":
        return await handle_log_fitness(args)
    elif name == "get_fitness_summary":
        return await handle_get_fitness_summary(args)
    elif name == "get_fitness_history":
        return await handle_get_fitness_history(args)
    elif name == "set_fitness_goal":
        return await handle_set_fitness_goal(args)
    
    # === Expenses ===
    elif name == "add_expense":
        return await handle_add_expense(args)
    elif name == "get_spending_report":
        return await handle_get_spending_report(args)
    elif name == "set_budget":
        return await handle_set_budget(args)
    
    # === Daily Briefing ===
    elif name == "get_daily_briefing":
        return await handle_get_daily_briefing(args)
    elif name == "schedule_briefing":
        return await handle_schedule_briefing(args)
    elif name == "cancel_briefing":
        return await handle_cancel_briefing(args)
    
    # === Mood Music ===
    elif name == "play_mood_music":
        return await handle_play_mood_music(args)
    
    # === Media Generation ===
    elif name == "generate_image":
        return await handle_generate_image(args)
    elif name == "generate_video":
        return await handle_generate_video(args)
    
    # === JARVIS Core ===
    elif name == "jarvis_greeting":
        return await handle_jarvis_greeting(args)
    elif name == "proactive_suggestions":
        return await handle_proactive_suggestions(args)
    elif name == "jarvis_status":
        return await handle_jarvis_status(args)
    
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
    
    # Call AI using the chat_with_functions from bytez_handler
    try:
        from handlers.bytez_handler import chat_with_functions
        result = chat_with_functions(message, phone)
        response = result.get("response", str(result))
        
        # Store conversation
        if _db_manager:
            _db_manager.add_conversation(phone, "user", message)
            _db_manager.add_conversation(phone, "assistant", response)
        
        return {
            "response": response,
            "model": os.getenv("BYTEZ_CHAT_MODEL", "openai/gpt-oss-20b")
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
    
    max_results = args.get("max_results", 10)
    
    try:
        from handlers.calendar import list_events
        events = list_events(max_results=max_results)
        # If it returns a string, it's a formatted message
        if isinstance(events, str):
            return {"events": events, "count": 0}
        return {"events": events, "count": len(events) if events else 0}
    except Exception as e:
        return {"error": f"Calendar error: {str(e)}"}


async def handle_create_calendar_event(args: Dict[str, Any]) -> Dict[str, Any]:
    """Create calendar event"""
    if not _calendar_service:
        return {"error": "Calendar service not available"}
    
    try:
        from handlers.calendar import create_event
        event = create_event(
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
        from handlers.gmail import list_emails
        query = args.get("query", "")
        if args.get("unread_only", False):
            query = f"is:unread {query}".strip()
        emails = list_emails(
            max_results=args.get("max_results", 10),
            query=query
        )
        return {"emails": emails, "count": len(emails) if emails else 0}
    except Exception as e:
        return {"error": f"Gmail error: {str(e)}"}


async def handle_send_email(args: Dict[str, Any]) -> Dict[str, Any]:
    """Send email via Gmail"""
    if not _gmail_service:
        return {"error": "Gmail service not available"}
    
    try:
        from handlers.gmail import send_email
        result = send_email(
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
        from handlers.spotify import play_song, play_playlist, play_album
        query = args.get("query")
        content_type = args.get("type", "track")
        
        if content_type == "playlist":
            result = play_playlist(query)
        elif content_type == "album":
            result = play_album(query)
        else:
            result = play_song(query)
        
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": f"Spotify error: {str(e)}"}


async def handle_spotify_control(args: Dict[str, Any]) -> Dict[str, Any]:
    """Control Spotify playback"""
    if not _spotify_service:
        return {"error": "Spotify not available"}
    
    action = args.get("action")
    
    try:
        # Spotify control commands use the spotify_client
        from handlers.spotify_client import get_spotify_client
        sp = get_spotify_client()
        
        if action == "play":
            sp.start_playback()
            result = "Playback started"
        elif action == "pause":
            sp.pause_playback()
            result = "Playback paused"
        elif action == "next":
            sp.next_track()
            result = "Skipped to next track"
        elif action == "previous":
            sp.previous_track()
            result = "Went to previous track"
        elif action == "shuffle_on":
            sp.shuffle(True)
            result = "Shuffle enabled"
        elif action == "shuffle_off":
            sp.shuffle(False)
            result = "Shuffle disabled"
        elif action == "repeat_track":
            sp.repeat("track")
            result = "Repeat track enabled"
        elif action == "repeat_off":
            sp.repeat("off")
            result = "Repeat disabled"
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
        from handlers.spotify import get_current_song
        track = get_current_song()
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
            "database": "available" if _db_manager else "unavailable",
            # JARVIS Services
            "workflows": "available" if _workflow_engine else "unavailable",
            "smart_home": "available" if _smart_home else "unavailable",
            "elevenlabs": "available" if _elevenlabs and _elevenlabs.enabled else "unavailable",
            "long_term_memory": "available" if _long_term_memory else "unavailable",
            "security": "available" if _security_monitor else "unavailable",
            "fitness": "available" if _fitness_service else "unavailable",
            "expenses": "available" if _expense_service else "unavailable",
            "daily_briefing": "available" if _daily_briefing else "unavailable",
            "jarvis_core": "available" if _jarvis_core else "unavailable",
            "mood_music": "available" if _mood_music else "unavailable",
        },
        "environment": {
            "bytez_configured": bool(os.getenv("BYTEZ_API_KEY")),
            "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
            "spotify_configured": bool(os.getenv("SPOTIFY_CLIENT_ID")),
            "elevenlabs_configured": bool(os.getenv("ELEVENLABS_API_KEY")),
            "ifttt_configured": bool(os.getenv("IFTTT_WEBHOOK_KEY")),
            "home_assistant_configured": bool(os.getenv("HOME_ASSISTANT_URL")),
            "waha_url": os.getenv("WAHA_URL", "not configured")
        },
        "version": "2.0.0-jarvis"
    }


# ============================================
# JARVIS Tool Handler Implementations
# ============================================

# === Workflow Handlers ===

async def handle_run_workflow(args: Dict[str, Any]) -> Dict[str, Any]:
    """Run a JARVIS workflow"""
    if not _workflow_engine:
        return {"error": "Workflow engine not available"}
    
    workflow = args.get("workflow")
    duration = args.get("duration")
    location = args.get("location", "Johannesburg")
    
    try:
        result = await _workflow_engine.run_workflow(workflow, duration=duration, location=location)
        return {"success": True, "workflow": workflow, "result": result}
    except Exception as e:
        return {"error": f"Workflow error: {str(e)}"}


async def handle_list_workflows(args: Dict[str, Any]) -> Dict[str, Any]:
    """List available workflows"""
    if not _workflow_engine:
        return {"error": "Workflow engine not available"}
    
    try:
        workflows = _workflow_engine.list_workflows()
        return {"workflows": workflows, "count": len(workflows)}
    except Exception as e:
        return {"error": f"Error listing workflows: {str(e)}"}


# === Smart Home Handlers ===

async def handle_smart_home_lights(args: Dict[str, Any]) -> Dict[str, Any]:
    """Control lights"""
    if not _smart_home:
        return {"error": "Smart home not available", "hint": "Configure IFTTT_WEBHOOK_KEY or HOME_ASSISTANT_URL"}
    
    action = args.get("action")
    brightness = args.get("brightness")
    room = args.get("room", "all")
    color = args.get("color")
    
    try:
        if action == "on":
            result = await _smart_home.lights_on(room=room, brightness=brightness, color=color)
        elif action == "off":
            result = await _smart_home.lights_off(room=room)
        elif action == "dim":
            result = await _smart_home.set_brightness(brightness or 50, room=room)
        else:
            return {"error": f"Unknown action: {action}"}
        return {"success": True, "action": action, "room": room, "result": result}
    except Exception as e:
        return {"error": f"Light control error: {str(e)}"}


async def handle_smart_home_thermostat(args: Dict[str, Any]) -> Dict[str, Any]:
    """Control thermostat"""
    if not _smart_home:
        return {"error": "Smart home not available"}
    
    temperature = args.get("temperature")
    mode = args.get("mode", "auto")
    
    try:
        result = await _smart_home.set_thermostat(temperature, mode=mode)
        return {"success": True, "temperature": temperature, "mode": mode, "result": result}
    except Exception as e:
        return {"error": f"Thermostat error: {str(e)}"}


async def handle_smart_home_scene(args: Dict[str, Any]) -> Dict[str, Any]:
    """Activate a scene"""
    if not _smart_home:
        return {"error": "Smart home not available"}
    
    scene = args.get("scene")
    
    try:
        result = await _smart_home.activate_scene(scene)
        return {"success": True, "scene": scene, "result": result}
    except Exception as e:
        return {"error": f"Scene error: {str(e)}"}


async def handle_smart_home_locks(args: Dict[str, Any]) -> Dict[str, Any]:
    """Control locks"""
    if not _smart_home:
        return {"error": "Smart home not available"}
    
    action = args.get("action")
    door = args.get("door", "all")
    
    try:
        if action == "lock":
            result = await _smart_home.lock_doors(door=door)
        elif action == "unlock":
            result = await _smart_home.unlock_doors(door=door)
        else:
            return {"error": f"Unknown action: {action}"}
        return {"success": True, "action": action, "door": door, "result": result}
    except Exception as e:
        return {"error": f"Lock control error: {str(e)}"}


async def handle_smart_home_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get smart home status"""
    if not _smart_home:
        return {"error": "Smart home not available"}
    
    try:
        status = _smart_home.get_status()
        return {"status": status}
    except Exception as e:
        return {"error": f"Status error: {str(e)}"}


# === Voice Handlers (Google Cloud TTS) ===

async def handle_speak_this(args: Dict[str, Any]) -> Dict[str, Any]:
    """Speak text using Google Cloud TTS"""
    text = args.get("text")
    
    if not text:
        return {"error": "No text provided"}
    
    try:
        from handlers.speech import text_to_speech
        audio_path = text_to_speech(text)
        if audio_path:
            return {"success": True, "audio_path": audio_path, "provider": "Google Cloud TTS"}
        return {"error": "TTS generation failed"}
    except Exception as e:
        return {"error": f"Voice synthesis error: {str(e)}"}


async def handle_change_voice(args: Dict[str, Any]) -> Dict[str, Any]:
    """Change voice preset - not supported with Google Cloud TTS basic"""
    return {
        "success": False, 
        "message": "Voice presets not available with Google Cloud TTS. Using default voice.",
        "provider": "Google Cloud TTS"
    }


async def handle_voice_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get voice status - uses Google Cloud TTS"""
    try:
        from handlers.speech import get_tts_client
        tts_client = get_tts_client()
        return {
            "enabled": tts_client is not None,
            "provider": "Google Cloud TTS",
            "message": "Voice synthesis available via Google Cloud TTS" if tts_client else "TTS not configured"
        }
    except Exception as e:
        return {"enabled": False, "error": f"Status error: {str(e)}"}


async def handle_toggle_voice_mode(args: Dict[str, Any]) -> Dict[str, Any]:
    """Toggle voice message response mode"""
    try:
        from handlers.speech import set_user_voice_preference, get_user_voice_preference
        
        enabled = args.get("enabled", True)
        phone = args.get("caller_phone", "")
        
        if not phone:
            return {"error": "Phone number required to set voice preference"}
        
        result = set_user_voice_preference(phone, enabled)
        current = get_user_voice_preference(phone)
        
        if enabled:
            return {
                "success": True,
                "voice_mode": "enabled",
                "message": "🔊 Voice mode ON! All my responses will now be sent as voice messages."
            }
        else:
            return {
                "success": True,
                "voice_mode": "disabled", 
                "message": "🔇 Voice mode OFF. I'll respond with text for text messages, voice for voice messages."
            }
    except Exception as e:
        return {"error": f"Failed to toggle voice mode: {str(e)}"}


# === Long-term Memory Handlers ===

async def handle_remember_this(args: Dict[str, Any]) -> Dict[str, Any]:
    """Store information in memory"""
    if not _long_term_memory:
        return {"error": "Long-term memory not available"}
    
    information = args.get("information")
    category = args.get("category", "topic")
    importance = args.get("importance", "medium")
    
    try:
        result = _long_term_memory.remember(information, category=category, importance=importance)
        return {"success": True, "stored": information, "category": category, "result": result}
    except Exception as e:
        return {"error": f"Memory error: {str(e)}"}


async def handle_recall_memory(args: Dict[str, Any]) -> Dict[str, Any]:
    """Recall information from memory"""
    if not _long_term_memory:
        return {"error": "Long-term memory not available"}
    
    topic = args.get("topic")
    category = args.get("category")
    
    try:
        results = _long_term_memory.recall(topic, category=category)
        return {"memories": results, "count": len(results) if results else 0}
    except Exception as e:
        return {"error": f"Recall error: {str(e)}"}


async def handle_forget_memory(args: Dict[str, Any]) -> Dict[str, Any]:
    """Forget information"""
    if not _long_term_memory:
        return {"error": "Long-term memory not available"}
    
    topic = args.get("topic")
    
    try:
        result = _long_term_memory.forget(topic)
        return {"success": True, "forgotten": topic, "result": result}
    except Exception as e:
        return {"error": f"Forget error: {str(e)}"}


async def handle_get_user_profile(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get user profile from memory"""
    if not _long_term_memory:
        return {"error": "Long-term memory not available"}
    
    phone = args.get("phone", "mcp_user")
    
    try:
        profile = _long_term_memory.get_user_profile(phone)
        return {"profile": profile}
    except Exception as e:
        return {"error": f"Profile error: {str(e)}"}


async def handle_memory_stats(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get memory statistics"""
    if not _long_term_memory:
        return {"error": "Long-term memory not available"}
    
    try:
        stats = _long_term_memory.get_stats()
        return {"stats": stats}
    except Exception as e:
        return {"error": f"Stats error: {str(e)}"}


# === Security Handlers ===

async def handle_security_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get security status"""
    if not _security_monitor:
        return {"error": "Security monitor not available"}
    
    try:
        status = _security_monitor.get_security_status()
        return status
    except Exception as e:
        return {"error": f"Security status error: {str(e)}"}


async def handle_security_report(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get detailed security report"""
    if not _security_monitor:
        return {"error": "Security monitor not available"}
    
    include_history = args.get("include_history", True)
    
    try:
        report = _security_monitor.get_security_report(include_history=include_history)
        return {"report": report}
    except Exception as e:
        return {"error": f"Security report error: {str(e)}"}


async def handle_check_threat(args: Dict[str, Any]) -> Dict[str, Any]:
    """Check message for threats"""
    if not _security_monitor:
        return {"error": "Security monitor not available"}
    
    message = args.get("message")
    
    try:
        result = _security_monitor.analyze_message(message)
        return result
    except Exception as e:
        return {"error": f"Threat check error: {str(e)}"}


# === Admin/Owner Handlers ===

async def handle_admin_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get comprehensive admin status (owner only)"""
    if not _security_monitor:
        return {"error": "Security monitor not available"}
    
    caller_phone = args.get("caller_phone")
    
    is_authorized, message = _security_monitor.require_owner(caller_phone, "view admin status")
    if not is_authorized:
        return {"error": message, "authorized": False}
    
    try:
        owner_status = _security_monitor.get_owner_status()
        security_status = _security_monitor.get_security_status() if hasattr(_security_monitor, 'get_security_status') else {}
        
        return {
            "authorized": True,
            "owner_status": owner_status,
            "security_status": security_status,
            "whitelisted_users": list(_security_monitor.whitelisted_users),
            "blocked_users": list(_security_monitor.blocked_users),
            "alerts_count": len(_security_monitor.alerts) if hasattr(_security_monitor, 'alerts') else 0
        }
    except Exception as e:
        return {"error": f"Admin status error: {str(e)}"}


async def handle_manage_whitelist(args: Dict[str, Any]) -> Dict[str, Any]:
    """Manage user whitelist (owner only)"""
    if not _security_monitor:
        return {"error": "Security monitor not available"}
    
    caller_phone = args.get("caller_phone")
    action = args.get("action")
    target_phone = args.get("target_phone")
    
    is_authorized, message = _security_monitor.require_owner(caller_phone, "manage whitelist")
    if not is_authorized:
        return {"error": message, "authorized": False}
    
    try:
        if action == "list":
            return {
                "authorized": True,
                "action": "list",
                "whitelisted_users": list(_security_monitor.whitelisted_users),
                "count": len(_security_monitor.whitelisted_users)
            }
        
        if not target_phone:
            return {"error": "target_phone required for add/remove"}
        
        if action == "add":
            _security_monitor.whitelisted_users.add(target_phone)
            return {
                "authorized": True,
                "action": "add",
                "target": target_phone,
                "success": True,
                "message": f"Added {target_phone} to whitelist"
            }
        
        elif action == "remove":
            # Don't allow removing the owner
            if _security_monitor.is_owner(target_phone):
                return {"error": "Cannot remove owner from whitelist"}
            
            _security_monitor.whitelisted_users.discard(target_phone)
            return {
                "authorized": True,
                "action": "remove",
                "target": target_phone,
                "success": True,
                "message": f"Removed {target_phone} from whitelist"
            }
        
        return {"error": f"Unknown action: {action}"}
    except Exception as e:
        return {"error": f"Whitelist error: {str(e)}"}


async def handle_manage_blocked(args: Dict[str, Any]) -> Dict[str, Any]:
    """Manage blocked users (owner only)"""
    if not _security_monitor:
        return {"error": "Security monitor not available"}
    
    caller_phone = args.get("caller_phone")
    action = args.get("action")
    target_phone = args.get("target_phone")
    reason = args.get("reason", "Admin action")
    
    is_authorized, message = _security_monitor.require_owner(caller_phone, "manage blocked users")
    if not is_authorized:
        return {"error": message, "authorized": False}
    
    try:
        if action == "list":
            return {
                "authorized": True,
                "action": "list",
                "blocked_users": list(_security_monitor.blocked_users),
                "count": len(_security_monitor.blocked_users)
            }
        
        if not target_phone:
            return {"error": "target_phone required for block/unblock"}
        
        # Don't allow blocking the owner
        if _security_monitor.is_owner(target_phone):
            return {"error": "Cannot block the owner"}
        
        if action == "block":
            _security_monitor.blocked_users.add(target_phone)
            # Also remove from whitelist
            _security_monitor.whitelisted_users.discard(target_phone)
            return {
                "authorized": True,
                "action": "block",
                "target": target_phone,
                "reason": reason,
                "success": True,
                "message": f"Blocked {target_phone}: {reason}"
            }
        
        elif action == "unblock":
            _security_monitor.blocked_users.discard(target_phone)
            return {
                "authorized": True,
                "action": "unblock",
                "target": target_phone,
                "success": True,
                "message": f"Unblocked {target_phone}"
            }
        
        return {"error": f"Unknown action: {action}"}
    except Exception as e:
        return {"error": f"Blocked users error: {str(e)}"}


async def handle_verify_owner(args: Dict[str, Any]) -> Dict[str, Any]:
    """Verify if caller is the system owner"""
    if not _security_monitor:
        return {"error": "Security monitor not available"}
    
    caller_phone = args.get("caller_phone")
    
    try:
        is_owner = _security_monitor.is_owner(caller_phone)
        role = _security_monitor.get_user_role(caller_phone)
        
        return {
            "phone": caller_phone[-4:] if len(caller_phone) > 4 else "****",
            "is_owner": is_owner,
            "role": role,
            "message": "You are the system owner and creator. Full admin access granted." if is_owner else f"You are a {role} user."
        }
    except Exception as e:
        return {"error": f"Verification error: {str(e)}"}


# === Fitness Handlers ===

async def handle_log_fitness(args: Dict[str, Any]) -> Dict[str, Any]:
    """Log fitness activity"""
    if not _fitness_service:
        return {"error": "Fitness service not available"}
    
    try:
        result = _fitness_service.log_activity(
            activity_type=args.get("activity_type"),
            duration=args.get("duration"),
            calories=args.get("calories"),
            distance=args.get("distance"),
            notes=args.get("notes")
        )
        return {"success": True, "activity": result}
    except Exception as e:
        return {"error": f"Fitness logging error: {str(e)}"}


async def handle_get_fitness_summary(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get fitness summary"""
    if not _fitness_service:
        return {"error": "Fitness service not available"}
    
    date = args.get("date")
    
    try:
        summary = _fitness_service.get_daily_summary(date=date)
        return {"summary": summary}
    except Exception as e:
        return {"error": f"Fitness summary error: {str(e)}"}


async def handle_get_fitness_history(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get fitness history"""
    if not _fitness_service:
        return {"error": "Fitness service not available"}
    
    days = args.get("days", 7)
    
    try:
        history = _fitness_service.get_history(days=days)
        return {"history": history, "days": days}
    except Exception as e:
        return {"error": f"Fitness history error: {str(e)}"}


async def handle_set_fitness_goal(args: Dict[str, Any]) -> Dict[str, Any]:
    """Set fitness goal"""
    if not _fitness_service:
        return {"error": "Fitness service not available"}
    
    goal_type = args.get("goal_type")
    target = args.get("target")
    
    try:
        result = _fitness_service.set_goal(goal_type=goal_type, target=target)
        return {"success": True, "goal": result}
    except Exception as e:
        return {"error": f"Goal setting error: {str(e)}"}


# === Expense Handlers ===

async def handle_add_expense(args: Dict[str, Any]) -> Dict[str, Any]:
    """Add expense"""
    if not _expense_service:
        return {"error": "Expense service not available"}
    
    amount = args.get("amount")
    category = args.get("category")
    description = args.get("description")
    
    try:
        result = _expense_service.add_expense(amount, category, description)
        return {"success": True, "expense": result}
    except Exception as e:
        return {"error": f"Expense error: {str(e)}"}


async def handle_get_spending_report(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get spending report"""
    if not _expense_service:
        return {"error": "Expense service not available"}
    
    days = args.get("days", 30)
    
    try:
        report = _expense_service.get_report(days=days)
        return {"report": report}
    except Exception as e:
        return {"error": f"Spending report error: {str(e)}"}


async def handle_set_budget(args: Dict[str, Any]) -> Dict[str, Any]:
    """Set budget"""
    if not _expense_service:
        return {"error": "Expense service not available"}
    
    category = args.get("category")
    limit = args.get("limit")
    period = args.get("period", "monthly")
    
    try:
        result = _expense_service.set_budget(category, limit, period)
        return {"success": True, "budget": result}
    except Exception as e:
        return {"error": f"Budget setting error: {str(e)}"}


# === Daily Briefing Handlers ===

async def handle_get_daily_briefing(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get daily briefing"""
    if not _daily_briefing:
        return {"error": "Daily briefing not available"}
    
    location = args.get("location", "Johannesburg")
    phone = args.get("phone", "mcp_user")
    
    try:
        from handlers.daily_briefing import generate_daily_briefing
        briefing = generate_daily_briefing(phone, location=location)
        return {"briefing": briefing}
    except Exception as e:
        return {"error": f"Briefing error: {str(e)}"}


async def handle_schedule_briefing(args: Dict[str, Any]) -> Dict[str, Any]:
    """Schedule daily briefing"""
    if not _daily_briefing:
        return {"error": "Daily briefing not available"}
    
    hour = args.get("hour", 7)
    minute = args.get("minute", 0)
    location = args.get("location", "Johannesburg")
    phone = args.get("phone", "mcp_user")
    
    try:
        from handlers.daily_briefing import schedule_daily_briefing
        result = schedule_daily_briefing(phone, hour=hour, minute=minute, location=location)
        return {"success": True, "scheduled": f"{hour:02d}:{minute:02d}", "result": result}
    except Exception as e:
        return {"error": f"Scheduling error: {str(e)}"}


async def handle_cancel_briefing(args: Dict[str, Any]) -> Dict[str, Any]:
    """Cancel daily briefing"""
    if not _daily_briefing:
        return {"error": "Daily briefing not available"}
    
    phone = args.get("phone", "mcp_user")
    
    try:
        from handlers.daily_briefing import cancel_daily_briefing
        result = cancel_daily_briefing(phone)
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": f"Cancel error: {str(e)}"}


# === Mood Music Handlers ===

async def handle_play_mood_music(args: Dict[str, Any]) -> Dict[str, Any]:
    """Play mood-based music"""
    if not _mood_music:
        return {"error": "Mood music not available"}
    
    mood = args.get("mood")
    
    try:
        result = _mood_music.play_for_mood(mood)
        return {"success": True, "mood": mood, "result": result}
    except Exception as e:
        return {"error": f"Mood music error: {str(e)}"}


# === Media Generation Handlers ===

async def handle_generate_image(args: Dict[str, Any]) -> Dict[str, Any]:
    """Generate image"""
    if not _media_generator:
        return {"error": "Media generator not available"}
    
    prompt = args.get("prompt")
    style = args.get("style", "realistic")
    
    try:
        result = await _media_generator.generate_image(prompt, style=style)
        return {"success": True, "image": result}
    except Exception as e:
        return {"error": f"Image generation error: {str(e)}"}


async def handle_generate_video(args: Dict[str, Any]) -> Dict[str, Any]:
    """Generate video"""
    if not _media_generator:
        return {"error": "Media generator not available"}
    
    prompt = args.get("prompt")
    style = args.get("style", "realistic")
    duration = args.get("duration", 5)
    
    try:
        result = await _media_generator.generate_video(prompt, style=style, duration=duration)
        return {"success": True, "video": result}
    except Exception as e:
        return {"error": f"Video generation error: {str(e)}"}


# === JARVIS Core Handlers ===

async def handle_jarvis_greeting(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get JARVIS greeting"""
    if not _jarvis_core:
        return {"error": "JARVIS core not available"}
    
    context = args.get("context")
    
    try:
        greeting = _jarvis_core.get_greeting(context=context)
        return {"greeting": greeting}
    except Exception as e:
        return {"error": f"Greeting error: {str(e)}"}


async def handle_proactive_suggestions(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get proactive suggestions"""
    if not _jarvis_core:
        return {"error": "JARVIS core not available"}
    
    context = args.get("context")
    
    try:
        suggestions = _jarvis_core.get_proactive_suggestions(context=context)
        return {"suggestions": suggestions}
    except Exception as e:
        return {"error": f"Suggestions error: {str(e)}"}


async def handle_jarvis_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get JARVIS system status"""
    if not _jarvis_core:
        return {"error": "JARVIS core not available"}
    
    try:
        status = _jarvis_core.get_system_status()
        return {"status": status}
    except Exception as e:
        return {"error": f"Status error: {str(e)}"}


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
