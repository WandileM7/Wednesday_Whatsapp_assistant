"""
Quick Commands Handler
Provides shortcut commands for common actions.
"""

import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

# Command registry
COMMANDS: Dict[str, Dict[str, Any]] = {}


def register_command(name: str, description: str, handler: Callable, aliases: list = None):
    """Register a quick command."""
    COMMANDS[name] = {
        'description': description,
        'handler': handler,
        'aliases': aliases or []
    }
    # Register aliases
    for alias in (aliases or []):
        COMMANDS[alias] = COMMANDS[name]


def process_quick_command(message: str, phone: str) -> Optional[Dict[str, Any]]:
    """
    Process a message as a quick command if it starts with /.
    
    Args:
        message: User's message
        phone: User's phone number
        
    Returns:
        Command result or None if not a command
    """
    if not message.startswith('/'):
        return None
    
    # Parse command and arguments
    parts = message[1:].split(' ', 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ''
    
    if command in COMMANDS:
        try:
            return COMMANDS[command]['handler'](args, phone)
        except Exception as e:
            logger.error(f"Error executing command /{command}: {e}")
            return {'error': str(e), 'response': f"Error executing /{command}: {e}"}
    
    # Command not found - show help
    return {
        'response': f"Unknown command: /{command}\n\nType /help for available commands."
    }


# ============ COMMAND HANDLERS ============

def cmd_help(args: str, phone: str) -> Dict[str, Any]:
    """Show available commands."""
    help_text = "📋 **Quick Commands**\n\n"
    
    seen = set()
    for name, cmd in COMMANDS.items():
        if name in seen or name in cmd.get('aliases', []):
            continue
        seen.add(name)
        
        aliases = cmd.get('aliases', [])
        alias_text = f" (or /{', /'.join(aliases)})" if aliases else ""
        help_text += f"/{name}{alias_text}\n  {cmd['description']}\n\n"
    
    return {'response': help_text}


def cmd_weather(args: str, phone: str) -> Dict[str, Any]:
    """Get current weather."""
    location = args.strip() if args else "Johannesburg"
    
    try:
        from handlers.weather import weather_service
        weather = weather_service.get_current_weather(location)
        
        if weather and 'error' not in weather:
            temp = weather.get('temperature', 'N/A')
            condition = weather.get('condition', 'Unknown')
            humidity = weather.get('humidity', 'N/A')
            
            return {
                'response': f"🌤️ **Weather in {location}**\n\n"
                           f"Condition: {condition}\n"
                           f"Temperature: {temp}°C\n"
                           f"Humidity: {humidity}%"
            }
        return {'response': f"Couldn't get weather for {location}"}
    except Exception as e:
        return {'response': f"Weather service error: {e}"}


def cmd_tasks(args: str, phone: str) -> Dict[str, Any]:
    """List or manage tasks."""
    try:
        from handlers.tasks import task_manager
        
        if args.startswith('add '):
            # Add new task
            title = args[4:].strip()
            result = task_manager.create_task(title=title)
            return {'response': f"✅ Task added: {title}"}
        
        elif args.startswith('done '):
            # Complete task
            task_id = args[5:].strip()
            result = task_manager.complete_task(task_id)
            return {'response': f"✅ Task completed!"}
        
        else:
            # List tasks
            tasks = task_manager.get_tasks()
            pending = [t for t in tasks if t.get('status') != 'completed']
            
            if not pending:
                return {'response': "✅ No pending tasks! You're all caught up."}
            
            response = "📝 **Your Tasks**\n\n"
            for i, task in enumerate(pending[:10], 1):
                title = task.get('title', 'Untitled')
                priority = task.get('priority', 'normal')
                emoji = "🔴" if priority == 'high' else "🟡" if priority == 'medium' else "🟢"
                response += f"{i}. {emoji} {title}\n"
            
            response += "\n_Use /tasks add <task> to add a task_"
            return {'response': response}
            
    except Exception as e:
        return {'response': f"Task error: {e}"}


def cmd_news(args: str, phone: str) -> Dict[str, Any]:
    """Get news headlines."""
    try:
        from handlers.news import news_service
        
        category = args.strip().lower() if args else None
        
        if category:
            news = news_service.get_top_headlines(category=category, limit=5)
        else:
            news = news_service.get_top_headlines(country='za', limit=5)
        
        if news and isinstance(news, list):
            response = f"📰 **{'Top ' + category.title() + ' ' if category else ''}Headlines**\n\n"
            for i, article in enumerate(news[:5], 1):
                title = article.get('title', '')[:100]
                response += f"{i}. {title}\n\n"
            return {'response': response}
        
        return {'response': "Couldn't fetch news right now."}
    except Exception as e:
        return {'response': f"News error: {e}"}


def cmd_play(args: str, phone: str) -> Dict[str, Any]:
    """Play music on Spotify."""
    if not args:
        return {'response': "What would you like to play?\n\nUsage: /play <song name>"}
    
    try:
        from handlers.spotify import play_song
        result = play_song(args.strip())
        return {'response': f"🎵 Now playing: {args}"}
    except Exception as e:
        return {'response': f"Couldn't play music: {e}"}


def cmd_pause(args: str, phone: str) -> Dict[str, Any]:
    """Pause Spotify playback."""
    try:
        from handlers.spotify import pause_playback
        pause_playback()
        return {'response': "⏸️ Playback paused"}
    except Exception as e:
        return {'response': f"Couldn't pause: {e}"}


def cmd_briefing(args: str, phone: str) -> Dict[str, Any]:
    """Get your daily briefing now."""
    try:
        from handlers.daily_briefing import send_briefing_now
        location = args.strip() if args else "Johannesburg"
        briefing = send_briefing_now(phone, location)
        return {'response': briefing}
    except Exception as e:
        return {'response': f"Couldn't generate briefing: {e}"}


def cmd_calendar(args: str, phone: str) -> Dict[str, Any]:
    """Show today's calendar events."""
    try:
        from handlers.calendar import get_todays_events
        events = get_todays_events()
        
        if not events:
            return {'response': "📅 No events scheduled for today."}
        
        response = "📅 **Today's Events**\n\n"
        for event in events[:10]:
            time_str = event.get('time', '')
            title = event.get('title', 'Untitled')
            response += f"• {time_str} - {title}\n"
        
        return {'response': response}
    except Exception as e:
        return {'response': f"Calendar error: {e}"}


def cmd_remind(args: str, phone: str) -> Dict[str, Any]:
    """Set a reminder."""
    if not args:
        return {'response': "What should I remind you about?\n\nUsage: /remind <message>"}
    
    try:
        from handlers.tasks import task_manager
        result = task_manager.create_reminder(message=args.strip(), phone=phone)
        return {'response': f"⏰ Reminder set: {args}"}
    except Exception as e:
        return {'response': f"Couldn't set reminder: {e}"}


def cmd_email(args: str, phone: str) -> Dict[str, Any]:
    """Check recent emails."""
    try:
        from handlers.gmail import summarize_emails
        summary = summarize_emails(count=5)
        return {'response': f"📧 **Recent Emails**\n\n{summary}"}
    except Exception as e:
        return {'response': f"Email error: {e}"}


def cmd_time(args: str, phone: str) -> Dict[str, Any]:
    """Get current time."""
    now = datetime.now()
    return {'response': f"🕐 Current time: {now.strftime('%H:%M:%S')}\n📅 Date: {now.strftime('%A, %B %d, %Y')}"}


def cmd_status(args: str, phone: str) -> Dict[str, Any]:
    """Check system status."""
    try:
        import psutil
        cpu = psutil.cpu_percent()
        memory = psutil.virtual_memory().percent
        
        return {
            'response': f"🤖 **Wednesday Status**\n\n"
                       f"✅ Online and ready\n"
                       f"💻 CPU: {cpu}%\n"
                       f"🧠 Memory: {memory}%\n"
                       f"⏰ Server time: {datetime.now().strftime('%H:%M')}"
        }
    except:
        return {'response': "✅ Wednesday is online and ready!"}


def cmd_expense(args: str, phone: str) -> Dict[str, Any]:
    """Track an expense."""
    if not args:
        # Show spending report
        try:
            from handlers.expenses import expense_service
            report = expense_service.get_report(phone, 30)
            return {'response': report}
        except Exception as e:
            return {'response': f"Error: {e}"}
    
    try:
        from handlers.expenses import parse_expense_from_text
        result = parse_expense_from_text(args, phone)
        if result.get('error'):
            return {'response': f"❌ {result['error']}"}
        return {'response': result.get('message', 'Expense recorded')}
    except Exception as e:
        return {'response': f"Error: {e}"}


def cmd_mood(args: str, phone: str) -> Dict[str, Any]:
    """Play music matching your mood."""
    try:
        from handlers.mood_music import mood_music_service
        if args:
            return {'response': mood_music_service.play_for_mood(args.strip(), phone)}
        else:
            return {'response': mood_music_service.get_suggestions('relaxed')}
    except Exception as e:
        return {'response': f"Error: {e}"}


def cmd_memory(args: str, phone: str) -> Dict[str, Any]:
    """Search conversation memory."""
    if not args:
        return {'response': "What would you like to search for?\n\nUsage: /memory <search query>"}
    
    try:
        from handlers.memory_search import memory_service
        return {'response': memory_service.format_search(phone, args)}
    except Exception as e:
        return {'response': f"Error: {e}"}


def cmd_recall(args: str, phone: str) -> Dict[str, Any]:
    """Recall past conversations."""
    query = args if args else "what did we discuss recently"
    try:
        from handlers.memory_search import memory_service
        return {'response': memory_service.recall(phone, query)}
    except Exception as e:
        return {'response': f"Error: {e}"}


# ============ REGISTER ALL COMMANDS ============

register_command('help', 'Show all available commands', cmd_help, ['h', '?'])
register_command('weather', 'Get current weather (usage: /weather [location])', cmd_weather, ['w'])
register_command('tasks', 'List/manage tasks (usage: /tasks, /tasks add <task>)', cmd_tasks, ['t', 'todo'])
register_command('news', 'Get news headlines (usage: /news [category])', cmd_news, ['n'])
register_command('play', 'Play music on Spotify', cmd_play, ['p', 'music'])
register_command('pause', 'Pause Spotify playback', cmd_pause, ['stop'])
register_command('briefing', 'Get your daily briefing', cmd_briefing, ['brief', 'morning'])
register_command('calendar', 'Show today\'s events', cmd_calendar, ['cal', 'events'])
register_command('remind', 'Set a reminder', cmd_remind, ['r', 'reminder'])
register_command('email', 'Check recent emails', cmd_email, ['mail'])
register_command('time', 'Get current time', cmd_time)
register_command('status', 'Check system status', cmd_status, ['ping'])
register_command('expense', 'Track expenses (usage: /expense R50 groceries)', cmd_expense, ['spent', 'money'])
register_command('mood', 'Play music for your mood (usage: /mood happy)', cmd_mood, ['vibe', 'feeling'])
register_command('memory', 'Search past conversations', cmd_memory, ['search', 'find'])
register_command('recall', 'Recall what we discussed', cmd_recall, ['remember'])

# Count unique commands (excluding aliases)
_unique_commands = len([name for name, cmd in COMMANDS.items() if name not in cmd.get('aliases', [])])
logger.info(f"Quick commands loaded: {_unique_commands} commands registered")
