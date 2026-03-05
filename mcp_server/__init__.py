# Wednesday WhatsApp Assistant - MCP Server
"""
Model Context Protocol (MCP) Server for Wednesday WhatsApp Assistant

This MCP server exposes the Wednesday assistant's capabilities as structured tools
that AI models can easily call. This reduces complexity by providing a clean API
layer between AI and the underlying services.

Available Tool Categories:
- messaging: WhatsApp message sending/receiving
- calendar: Google Calendar integration
- email: Gmail integration
- tasks: Task and reminder management
- contacts: Contact lookup and management
- spotify: Music playback control
- weather: Weather information
- news: News updates
- ai: Direct AI conversation
"""

__version__ = "1.0.0"
