#!/usr/bin/env python3
"""
Wednesday MCP Server - HTTP/SSE Transport

HTTP-based transport for the MCP server, suitable for Kubernetes deployment.
Provides a REST API and Server-Sent Events (SSE) for real-time communication.

Run: python -m mcp_server.http_server
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, Response
import queue
import threading

# Import the main MCP server logic
from mcp_server.server import load_services, handle_tool, TOOLS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wednesday-mcp-http")

app = Flask(__name__)

# SSE clients
sse_clients = []


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Kubernetes probes"""
    return jsonify({
        "status": "healthy",
        "service": "wednesday-mcp",
        "timestamp": datetime.now().isoformat()
    })


@app.route('/tools', methods=['GET'])
def list_tools():
    """List all available MCP tools"""
    tools_list = []
    for tool in TOOLS:
        tools_list.append({
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.inputSchema
        })
    return jsonify({
        "tools": tools_list,
        "count": len(tools_list)
    })


@app.route('/tools/<tool_name>', methods=['POST'])
def call_tool(tool_name: str):
    """Call a specific MCP tool"""
    load_services()
    
    try:
        arguments = request.get_json() or {}
        
        # Run the async handler in an event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(handle_tool(tool_name, arguments))
        finally:
            loop.close()
        
        return jsonify({
            "success": True,
            "tool": tool_name,
            "result": result
        })
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
    except Exception as e:
        logger.error(f"Error calling tool {tool_name}: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/call', methods=['POST'])
def unified_call():
    """Unified endpoint to call any tool by name"""
    load_services()
    
    data = request.get_json()
    if not data or 'tool' not in data:
        return jsonify({
            "success": False,
            "error": "Missing 'tool' in request body"
        }), 400
    
    tool_name = data['tool']
    arguments = data.get('arguments', {})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(handle_tool(tool_name, arguments))
        finally:
            loop.close()
        
        return jsonify({
            "success": True,
            "tool": tool_name,
            "result": result
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/events', methods=['GET'])
def sse_events():
    """Server-Sent Events endpoint for real-time updates"""
    def event_stream():
        q = queue.Queue()
        sse_clients.append(q)
        try:
            while True:
                try:
                    message = q.get(timeout=30)
                    yield f"data: {json.dumps(message)}\n\n"
                except queue.Empty:
                    # Send keepalive
                    yield f": keepalive {datetime.now().isoformat()}\n\n"
        finally:
            sse_clients.remove(q)
    
    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


def broadcast_event(event_type: str, data: Dict[str, Any]):
    """Broadcast an event to all SSE clients"""
    message = {
        "type": event_type,
        "data": data,
        "timestamp": datetime.now().isoformat()
    }
    for client in sse_clients:
        try:
            client.put_nowait(message)
        except queue.Full:
            pass


@app.route('/status', methods=['GET'])
def status():
    """Get server status and service availability"""
    load_services()
    
    from mcp_server.server import (
        _bytez_handler, _gmail_service, _calendar_service,
        _spotify_service, _task_manager, _contact_manager,
        _weather_service, _news_service, _db_manager,
        # JARVIS services
        _workflow_engine, _smart_home, _elevenlabs, _long_term_memory,
        _security_monitor, _fitness_service, _expense_service, _daily_briefing,
        _jarvis_core, _mood_music
    )
    
    return jsonify({
        "server": "wednesday-mcp-http",
        "version": "2.0.0-jarvis",
        "sse_clients": len(sse_clients),
        "tool_count": len(TOOLS),
        "services": {
            # Core services
            "ai": "available" if _bytez_handler else "unavailable",
            "gmail": "available" if _gmail_service else "unavailable",
            "calendar": "available" if _calendar_service else "unavailable",
            "spotify": "available" if _spotify_service else "unavailable",
            "tasks": "available" if _task_manager else "unavailable",
            "contacts": "available" if _contact_manager else "unavailable",
            "weather": "available" if _weather_service else "unavailable",
            "news": "available" if _news_service else "unavailable",
            "database": "available" if _db_manager else "unavailable",
            # JARVIS services
            "workflows": "available" if _workflow_engine else "unavailable",
            "smart_home": "available" if _smart_home else "unavailable",
            "elevenlabs": "available" if _elevenlabs and _elevenlabs.enabled else "unavailable",
            "long_term_memory": "available" if _long_term_memory else "unavailable",
            "security": "available" if _security_monitor else "unavailable",
            "fitness": "available" if _fitness_service else "unavailable",
            "expenses": "available" if _expense_service else "unavailable",
            "daily_briefing": "available" if _daily_briefing else "unavailable",
            "jarvis_core": "available" if _jarvis_core else "unavailable",
            "mood_music": "available" if _mood_music else "unavailable"
        },
        "environment": {
            "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
            "elevenlabs_configured": bool(os.getenv("ELEVENLABS_API_KEY")),
            "ifttt_configured": bool(os.getenv("IFTTT_WEBHOOK_KEY")),
            "home_assistant_configured": bool(os.getenv("HOME_ASSISTANT_URL"))
        }
    })


@app.route('/', methods=['GET'])
def index():
    """Root endpoint with API documentation"""
    return jsonify({
        "service": "Wednesday MCP Server (JARVIS Edition)",
        "version": "2.0.0-jarvis",
        "tool_count": len(TOOLS),
        "description": "Model Context Protocol server for Wednesday WhatsApp Assistant with 52 JARVIS tools",
        "endpoints": {
            "GET /": "This documentation",
            "GET /health": "Health check for Kubernetes",
            "GET /status": "Server status and service availability",
            "GET /tools": "List all available tools",
            "POST /tools/<name>": "Call a specific tool",
            "POST /call": "Unified tool call endpoint",
            "GET /events": "Server-Sent Events for real-time updates"
        },
        "example": {
            "endpoint": "POST /call",
            "body": {
                "tool": "chat",
                "arguments": {
                    "message": "What's on my calendar today?"
                }
            }
        }
    })


def main():
    """Run the HTTP server"""
    port = int(os.getenv("MCP_PORT", "8080"))
    host = os.getenv("MCP_HOST", "0.0.0.0")
    debug = os.getenv("MCP_DEBUG", "false").lower() == "true"
    
    logger.info(f"Starting Wednesday MCP HTTP Server on {host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    main()
