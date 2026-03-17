"""
MCP Agent - AI Orchestrator for Wednesday Assistant

This agent receives user messages and uses Gemini AI to decide which MCP tools
to call. It replaces direct Gemini function calling with structured MCP tool calls.

Architecture:
  WhatsApp → main.py → MCP Agent → Gemini (reasoning) → MCP Tools → Response

The agent runs an agentic loop:
1. Receive user message
2. Ask Gemini which tool(s) to call (with tool schemas)
3. Call MCP tool(s)
4. Feed results back to Gemini
5. Repeat until Gemini has a final answer or max iterations reached
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from google import genai
from google.genai import types as genai_types

logger = logging.getLogger("MCPAgent")

# Configuration
MAX_ITERATIONS = 5  # Max tool calls per conversation turn
MCP_HTTP_URL = os.getenv("MCP_HTTP_URL", "http://localhost:8080")
GENERATION_MODEL = os.getenv("MCP_AGENT_MODEL", "gemini-2.5-flash")

# Gemini client
_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    """Get or create Gemini client."""
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not configured")
        _client = genai.Client(api_key=api_key)
    return _client


# ============================================
# MCP Tool Registry
# ============================================

def get_mcp_tool_schemas() -> List[Dict[str, Any]]:
    """
    Get all MCP tool schemas in a format Gemini can understand.
    This dynamically loads from the MCP server to stay in sync.
    """
    try:
        from mcp_server.server import TOOLS
        
        schemas = []
        for tool in TOOLS:
            schema = {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
            schemas.append(schema)
        
        return schemas
    except Exception as e:
        logger.error(f"Failed to load MCP tool schemas: {e}")
        return []


def get_tool_declarations() -> List[genai_types.FunctionDeclaration]:
    """Convert MCP tool schemas to Gemini function declarations."""
    schemas = get_mcp_tool_schemas()
    declarations = []
    
    for schema in schemas:
        try:
            decl = genai_types.FunctionDeclaration(
                name=schema["name"],
                description=schema["description"],
                parameters=schema.get("parameters", {"type": "object", "properties": {}})
            )
            declarations.append(decl)
        except Exception as e:
            logger.warning(f"Failed to create declaration for {schema.get('name')}: {e}")
    
    return declarations


# ============================================
# MCP Tool Executor
# ============================================

async def call_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call an MCP tool directly (internal, no HTTP needed in same process).
    
    For GCP deployment, both the agent and MCP server run in the same container,
    so we can call the handlers directly for better performance.
    """
    try:
        from mcp_server.server import load_services, handle_tool
        
        # Ensure services are loaded
        load_services()
        
        # Call the tool handler directly
        result = await handle_tool(tool_name, arguments)
        return result
        
    except Exception as e:
        logger.error(f"MCP tool call failed: {tool_name} - {e}")
        return {"error": str(e), "tool": tool_name}


def call_mcp_tool_sync(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronous wrapper for MCP tool calls."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(call_mcp_tool(tool_name, arguments))


async def call_mcp_tool_http(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call MCP tool via HTTP (for when running as separate services).
    Use this if MCP server is deployed separately.
    """
    import aiohttp
    
    url = f"{MCP_HTTP_URL}/tools/{tool_name}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=arguments, timeout=30) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    return {"error": f"HTTP {response.status}: {error_text}"}
    except Exception as e:
        return {"error": f"HTTP request failed: {str(e)}"}


# ============================================
# Agent System Prompt
# ============================================

AGENT_SYSTEM_PROMPT = """You are JARVIS, an advanced AI assistant with a witty, helpful, and professional personality.

**CRITICAL: CONVERSATION FIRST, TOOLS SECOND**

For the vast majority of messages, respond conversationally WITHOUT using any tools:
- Greetings ("hello", "hi", "hey", "good morning") → Just reply warmly
- Casual chat ("how are you", "what's up", "thank you") → Just converse naturally
- Questions you can answer from knowledge ("what is X", "explain Y", "who was Z") → Answer directly
- Opinions/advice requests → Share your perspective
- Jokes, banter, small talk → Engage naturally

ONLY use tools when the user EXPLICITLY needs:
- Real-time data (weather NOW, today's news, current calendar)
- External actions (send email, play music, create task, control lights)
- User-specific stored data (their tasks, their expenses, their fitness log)
- Admin operations (whitelist management, security status)

Examples of when NOT to use tools:
- "Hello!" → "Good day! How may I assist you?" (NO tools)
- "What time is it?" → Tell them the time from context (NO tools)
- "Tell me a joke" → Tell a joke (NO tools)
- "How do I cook pasta?" → Explain cooking (NO tools)
- "Thanks!" → "You're welcome!" (NO tools)

Examples of when TO use tools:
- "What's the weather in London?" → weather tool (needs real-time data)
- "Play some jazz" → spotify tool (external action)
- "Add milk to my shopping list" → tasks tool (user data)
- "Send an email to John" → email tool (external action)

Available tools (use sparingly):
- Core: calendar, email, tasks, contacts, spotify, weather, news
- Smart Home: lights, thermostat, scenes, locks
- Memory: remember_this, recall_memory (only when asked to remember/recall)
- Fitness: log_fitness, get_fitness_summary
- Expenses: add_expense, get_spending_report
- Admin: admin_status, manage_whitelist (owner only)

Current context:
- Date/Time: {datetime}
- User Phone: {phone}

Current context:
- Date/Time: {datetime}
- User Phone: {phone}
"""


# ============================================
# MCP Agent Core
# ============================================

class MCPAgent:
    """
    AI Agent that orchestrates MCP tool calls using Gemini for reasoning.
    """
    
    def __init__(self):
        self.tool_declarations = None
        self.client = None
        self._initialized = False
    
    def _initialize(self):
        """Lazy initialization."""
        if self._initialized:
            return
        
        try:
            self.client = _get_client()
            declarations = get_tool_declarations()
            
            if declarations:
                self.tool_declarations = [genai_types.Tool(function_declarations=declarations)]
                logger.info(f"MCP Agent initialized with {len(declarations)} tools")
            else:
                self.tool_declarations = None
                logger.warning("MCP Agent initialized without tools")
            
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize MCP Agent: {e}")
            raise
    
    def process_message(self, user_message: str, phone: str = "unknown", 
                        conversation_history: List[str] = None) -> Dict[str, Any]:
        """
        Process a user message through the MCP agent.
        
        Args:
            user_message: The user's message
            phone: User's phone number for context
            conversation_history: Previous messages for context
            
        Returns:
            Dict with 'response', 'tools_called', 'function_call' (if any)
        """
        self._initialize()
        
        # Store phone for injecting into admin tools
        self._current_phone = phone
        
        # Build system prompt with context
        system_prompt = AGENT_SYSTEM_PROMPT.format(
            datetime=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            phone=phone
        )
        
        # Build message history
        contents = []
        
        # Add conversation history if provided
        if conversation_history:
            for i, msg in enumerate(conversation_history[-6:]):  # Last 6 messages
                role = "user" if i % 2 == 0 else "model"
                contents.append(genai_types.Content(
                    role=role,
                    parts=[genai_types.Part(text=msg)]
                ))
        
        # Add current user message
        contents.append(genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=user_message)]
        ))
        
        # Run the agentic loop
        tools_called = []
        iterations = 0
        
        while iterations < MAX_ITERATIONS:
            iterations += 1
            
            try:
                # Call Gemini with tools
                response = self.client.models.generate_content(
                    model=GENERATION_MODEL,
                    contents=contents,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        tools=self.tool_declarations,
                        temperature=0.7,
                    )
                )
                
                # Check if Gemini wants to call a tool
                if response.candidates and response.candidates[0].content.parts:
                    part = response.candidates[0].content.parts[0]
                    
                    # Check for function call
                    if hasattr(part, 'function_call') and part.function_call:
                        fn_call = part.function_call
                        tool_name = fn_call.name
                        tool_args = dict(fn_call.args) if fn_call.args else {}
                        
                        # Auto-inject caller_phone for admin/owner tools
                        admin_tools = ['admin_status', 'manage_whitelist', 'manage_blocked', 'verify_owner']
                        if tool_name in admin_tools and 'caller_phone' not in tool_args:
                            tool_args['caller_phone'] = self._current_phone
                            logger.info(f"Injected caller_phone for admin tool: {tool_name}")
                        
                        logger.info(f"MCP Agent calling tool: {tool_name}")
                        
                        # Execute the MCP tool
                        tool_result = call_mcp_tool_sync(tool_name, tool_args)
                        tools_called.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "result": tool_result
                        })
                        
                        # Add function call and result to conversation
                        contents.append(genai_types.Content(
                            role="model",
                            parts=[genai_types.Part(function_call=fn_call)]
                        ))
                        
                        contents.append(genai_types.Content(
                            role="user",
                            parts=[genai_types.Part(
                                function_response=genai_types.FunctionResponse(
                                    name=tool_name,
                                    response={"result": tool_result}
                                )
                            )]
                        ))
                        
                        # Continue the loop to let Gemini process the result
                        continue
                    
                    # No function call - this is the final response
                    if hasattr(part, 'text') and part.text:
                        return {
                            "response": part.text,
                            "tools_called": tools_called,
                            "iterations": iterations,
                            "function_call": tools_called[-1] if tools_called else None
                        }
                
                # Fallback - no valid response
                return {
                    "response": "I apologize, but I couldn't process that request properly.",
                    "tools_called": tools_called,
                    "iterations": iterations,
                    "error": "No valid response from model"
                }
                
            except Exception as e:
                logger.error(f"MCP Agent error in iteration {iterations}: {e}")
                
                if tools_called:
                    # Return partial results if we made some progress
                    return {
                        "response": f"I encountered an issue while processing your request: {str(e)}",
                        "tools_called": tools_called,
                        "iterations": iterations,
                        "error": str(e)
                    }
                else:
                    return {
                        "response": f"I'm sorry, I encountered an error: {str(e)}",
                        "tools_called": [],
                        "iterations": iterations,
                        "error": str(e)
                    }
        
        # Max iterations reached
        return {
            "response": "I've reached the maximum number of steps for this request. Here's what I found so far.",
            "tools_called": tools_called,
            "iterations": iterations,
            "warning": "max_iterations_reached"
        }


# ============================================
# Module-level Interface (for main.py)
# ============================================

# Singleton agent instance
_agent: Optional[MCPAgent] = None


def get_agent() -> MCPAgent:
    """Get or create the MCP agent singleton."""
    global _agent
    if _agent is None:
        _agent = MCPAgent()
    return _agent


def chat_with_mcp(user_message: str, phone: str = "unknown") -> Dict[str, Any]:
    """
    Main entry point for processing messages through the MCP agent.
    
    This is the drop-in replacement for chat_with_functions from Gemini.
    
    Args:
        user_message: The user's message
        phone: User's phone number
        
    Returns:
        Dict with 'response' and metadata
    """
    agent = get_agent()
    
    # Get conversation history from database
    conversation_history = []
    try:
        from database import retrieve_conversation_history
        history = retrieve_conversation_history(phone, limit=6)
        if history:
            conversation_history = history
    except Exception as e:
        logger.warning(f"Could not load conversation history: {e}")
    
    # Process through MCP agent
    result = agent.process_message(user_message, phone, conversation_history)
    
    # Store conversation in database
    try:
        from database import add_to_conversation_history
        add_to_conversation_history(phone, "user", user_message)
        add_to_conversation_history(phone, "assistant", result.get("response", ""))
    except Exception as e:
        logger.warning(f"Could not save conversation: {e}")
    
    return result


def execute_mcp_tool(tool_name: str, args: Dict[str, Any]) -> str:
    """
    Execute a specific MCP tool directly.
    
    This is the drop-in replacement for execute_function from Gemini.
    """
    result = call_mcp_tool_sync(tool_name, args)
    
    if isinstance(result, dict):
        if "error" in result:
            return f"Error: {result['error']}"
        return json.dumps(result, indent=2, default=str)
    
    return str(result)


# ============================================
# Compatibility Layer (for main.py)
# ============================================

def chat_with_functions(user_message: str, phone: str) -> Dict[str, Any]:
    """
    Drop-in replacement for handlers.gemini.chat_with_functions
    
    Routes everything through the MCP agent instead of direct Gemini function calling.
    MCP agent handles tool execution internally, so we just return the response.
    """
    result = chat_with_mcp(user_message, phone)
    
    # MCP agent already executes tools internally.
    # Return format compatible with main.py - no function_call that needs execution
    return {
        "response": result.get("response", ""),
        "content": result.get("response", ""),  # Alias for Gemini compatibility
        "tools_called": result.get("tools_called", []),
        "_mcp_handled": True  # Flag that tools were already executed
    }


def execute_function(call: Dict[str, Any], phone: str = "") -> str:
    """
    Drop-in replacement for handlers.gemini.execute_function
    
    Executes a tool through MCP.
    """
    tool_name = call.get("name") or call.get("tool")
    args = call.get("args") or call.get("arguments", {})
    
    return execute_mcp_tool(tool_name, args)


# ============================================
# Health Check
# ============================================

def get_mcp_agent_status() -> Dict[str, Any]:
    """Get MCP agent status for health checks."""
    try:
        agent = get_agent()
        agent._initialize()
        
        tool_count = len(agent.tool_declarations[0].function_declarations) if agent.tool_declarations else 0
        
        return {
            "status": "healthy",
            "initialized": agent._initialized,
            "tool_count": tool_count,
            "model": GENERATION_MODEL,
            "mcp_http_url": MCP_HTTP_URL
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)
    
    print("Testing MCP Agent...")
    result = chat_with_mcp("What's the weather in Johannesburg?", "test_user")
    print(f"\nResponse: {result.get('response')}")
    print(f"Tools called: {result.get('tools_called')}")
