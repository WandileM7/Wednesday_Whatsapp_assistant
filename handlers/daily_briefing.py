"""
Daily Briefing Handler
Generates personalized morning briefings with weather, calendar, tasks, and news.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import threading
import time

logger = logging.getLogger(__name__)

# Store scheduled briefings
scheduled_briefings: Dict[str, Dict[str, Any]] = {}


def generate_daily_briefing(phone: str, location: str = "Johannesburg") -> str:
    """
    Generate a comprehensive daily briefing.
    
    Args:
        phone: User's phone number
        location: User's location for weather
        
    Returns:
        Formatted briefing message
    """
    briefing_parts = []
    current_time = datetime.now()
    
    # Greeting based on time of day
    hour = current_time.hour
    if hour < 12:
        greeting = "🌅 Good morning"
    elif hour < 17:
        greeting = "☀️ Good afternoon"
    else:
        greeting = "🌙 Good evening"
    
    briefing_parts.append(f"{greeting}! Here's your daily briefing for {current_time.strftime('%A, %B %d')}:\n")
    
    # Weather
    try:
        from handlers.weather import weather_service
        weather = weather_service.get_current_weather(location)
        if weather and 'error' not in weather:
            temp = weather.get('temperature', 'N/A')
            condition = weather.get('condition', 'Unknown')
            briefing_parts.append(f"🌤️ **Weather in {location}**\n{condition}, {temp}°C\n")
    except Exception as e:
        logger.warning(f"Could not fetch weather: {e}")
    
    # Calendar events for today
    try:
        from handlers.calendar import get_todays_events
        events = get_todays_events()
        if events:
            briefing_parts.append("📅 **Today's Events**")
            for event in events[:5]:  # Limit to 5 events
                event_time = event.get('time', '')
                event_title = event.get('title', 'Untitled')
                briefing_parts.append(f"  • {event_time} - {event_title}")
            briefing_parts.append("")
        else:
            briefing_parts.append("📅 **Calendar**: No events scheduled today\n")
    except Exception as e:
        logger.warning(f"Could not fetch calendar: {e}")
    
    # Tasks due today
    try:
        from handlers.tasks import task_manager
        tasks = task_manager.get_tasks()
        pending_tasks = [t for t in tasks if t.get('status') != 'completed']
        if pending_tasks:
            briefing_parts.append("✅ **Pending Tasks**")
            for task in pending_tasks[:5]:  # Limit to 5 tasks
                title = task.get('title', 'Untitled')
                priority = task.get('priority', 'normal')
                priority_emoji = "🔴" if priority == 'high' else "🟡" if priority == 'medium' else "🟢"
                briefing_parts.append(f"  {priority_emoji} {title}")
            briefing_parts.append("")
    except Exception as e:
        logger.warning(f"Could not fetch tasks: {e}")
    
    # News headlines
    try:
        from handlers.news import news_service
        news = news_service.get_top_headlines(country='za', limit=3)
        if news and isinstance(news, list):
            briefing_parts.append("📰 **Top Headlines**")
            for article in news[:3]:
                title = article.get('title', '')[:80]
                if title:
                    briefing_parts.append(f"  • {title}")
            briefing_parts.append("")
    except Exception as e:
        logger.warning(f"Could not fetch news: {e}")
    
    # Motivational closing
    closings = [
        "Have a productive day! 💪",
        "Make today count! ⭐",
        "You've got this! 🚀",
        "Wishing you a great day ahead! 🌟"
    ]
    import random
    briefing_parts.append(random.choice(closings))
    
    return "\n".join(briefing_parts)


def schedule_daily_briefing(phone: str, hour: int = 7, minute: int = 0, location: str = "Johannesburg") -> Dict[str, Any]:
    """
    Schedule a daily briefing for a user.
    
    Args:
        phone: User's phone number
        hour: Hour to send briefing (24h format)
        minute: Minute to send briefing
        location: User's location for weather
        
    Returns:
        Schedule confirmation
    """
    scheduled_briefings[phone] = {
        'hour': hour,
        'minute': minute,
        'location': location,
        'enabled': True,
        'created_at': datetime.now().isoformat()
    }
    
    return {
        'status': 'scheduled',
        'time': f"{hour:02d}:{minute:02d}",
        'location': location,
        'message': f"Daily briefing scheduled for {hour:02d}:{minute:02d} every day"
    }


def cancel_daily_briefing(phone: str) -> Dict[str, Any]:
    """Cancel scheduled daily briefing for a user."""
    if phone in scheduled_briefings:
        del scheduled_briefings[phone]
        return {'status': 'cancelled', 'message': 'Daily briefing cancelled'}
    return {'status': 'not_found', 'message': 'No briefing was scheduled'}


def get_briefing_status(phone: str) -> Dict[str, Any]:
    """Get the status of a user's daily briefing schedule."""
    if phone in scheduled_briefings:
        schedule = scheduled_briefings[phone]
        return {
            'scheduled': True,
            'time': f"{schedule['hour']:02d}:{schedule['minute']:02d}",
            'location': schedule['location'],
            'enabled': schedule['enabled']
        }
    return {'scheduled': False}


def send_briefing_now(phone: str, location: str = "Johannesburg") -> str:
    """Generate and return a briefing immediately."""
    return generate_daily_briefing(phone, location)


# Background thread for sending scheduled briefings
def _briefing_scheduler():
    """Background thread that checks and sends scheduled briefings."""
    while True:
        try:
            now = datetime.now()
            current_hour = now.hour
            current_minute = now.minute
            
            for phone, schedule in list(scheduled_briefings.items()):
                if (schedule.get('enabled') and 
                    schedule['hour'] == current_hour and 
                    schedule['minute'] == current_minute):
                    
                    # Check if we already sent today
                    last_sent = schedule.get('last_sent')
                    if last_sent:
                        last_sent_date = datetime.fromisoformat(last_sent).date()
                        if last_sent_date == now.date():
                            continue
                    
                    # Generate and send briefing
                    try:
                        briefing = generate_daily_briefing(phone, schedule['location'])
                        
                        # Send via WAHA
                        import requests
                        import os
                        waha_url = os.getenv('WAHA_URL', 'http://localhost:3000/api/sendText')
                        requests.post(waha_url, json={
                            'chatId': phone,
                            'text': briefing
                        }, timeout=30)
                        
                        schedule['last_sent'] = now.isoformat()
                        logger.info(f"Sent daily briefing to {phone}")
                        
                    except Exception as e:
                        logger.error(f"Failed to send briefing to {phone}: {e}")
            
            # Sleep for 60 seconds before checking again
            time.sleep(60)
            
        except Exception as e:
            logger.error(f"Briefing scheduler error: {e}")
            time.sleep(60)


# Start scheduler thread
_scheduler_thread = threading.Thread(target=_briefing_scheduler, daemon=True)
_scheduler_thread.start()
logger.info("Daily briefing scheduler started")
