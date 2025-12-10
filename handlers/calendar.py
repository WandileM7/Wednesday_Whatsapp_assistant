from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta, timezone
from handlers.google_auth import load_credentials
import logging

logger = logging.getLogger(__name__)

def get_calendar_service():
    """Get authenticated Calendar service"""
    try:
        creds = load_credentials()
        if not creds:
            raise Exception("No valid credentials available")
        
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Failed to create calendar service: {e}")
        raise

def list_events(max_results=10):
    """List upcoming calendar events"""
    try:
        service = get_calendar_service()
        
        # Get events starting from now
        now = datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        
        logger.info(f"Fetching calendar events from {now}")
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        logger.info(f"Found {len(events)} upcoming events")
        
        if not events:
            return "No upcoming events found."
        
        # Format events for display
        event_list = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'No title')
            
            # Parse and format the datetime
            try:
                if 'T' in start:  # DateTime format
                    dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    formatted_time = dt.strftime('%Y-%m-%d %H:%M')
                else:  # Date format
                    formatted_time = start
                
                event_list.append(f"• {summary} - {formatted_time}")
            except Exception as e:
                logger.warning(f"Error formatting event time: {e}")
                event_list.append(f"• {summary} - {start}")
        
        return "Upcoming events:\n" + "\n".join(event_list)
        
    except HttpError as e:
        logger.error(f"Calendar API error: {e}")
        return f"❌ Calendar error: {e.resp.status} - {e.content.decode()}"
    except Exception as e:
        logger.error(f"Error listing events: {e}")
        return f"❌ Error accessing calendar: {str(e)}"

def create_event(summary, start_time, end_time, description="", location="", attendees=None):
    """Create a calendar event with improved datetime handling"""
    try:
        service = get_calendar_service()
        
        # Parse and validate datetime inputs
        start_dt = parse_datetime(start_time)
        end_dt = parse_datetime(end_time)
        
        if start_dt >= end_dt:
            return "❌ Error: Start time must be before end time"
        
        # Create event object
        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'UTC',
            },
        }
        
        # Add location if provided
        if location:
            event['location'] = location
        
        # Add attendees if provided
        if attendees:
            if isinstance(attendees, str):
                attendees = [attendees]
            event['attendees'] = [{'email': email.strip()} for email in attendees if email.strip()]
        
        # Add reminders
        event['reminders'] = {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                {'method': 'popup', 'minutes': 30},       # 30 minutes before
            ],
        }
        
        logger.info(f"Creating event: {summary} from {start_dt} to {end_dt}")
        
        # Create the event
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        
        event_link = created_event.get('htmlLink', 'No link available')
        event_id = created_event.get('id', 'No ID')
        
        logger.info(f"Event created successfully: {event_id}")
        
        return f"✅ Event '{summary}' created successfully!\n📅 {start_dt.strftime('%Y-%m-%d %H:%M')} - {end_dt.strftime('%H:%M')}\n🔗 {event_link}"
        
    except HttpError as e:
        error_details = e.content.decode() if e.content else str(e)
        logger.error(f"Calendar API error: {e.resp.status} - {error_details}")
        
        if e.resp.status == 400:
            return f"❌ Invalid event data: Please check the date/time format and try again"
        elif e.resp.status == 403:
            return f"❌ Permission denied: Please ensure calendar access is granted"
        else:
            return f"❌ Calendar error: {e.resp.status} - {error_details}"
            
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        return f"❌ Error creating event: {str(e)}"

def parse_datetime(dt_input):
    """Parse various datetime input formats using built-in modules"""
    if isinstance(dt_input, datetime):
        # If already a datetime, ensure it has UTC timezone
        if dt_input.tzinfo is None:
            return dt_input.replace(tzinfo=timezone.utc)
        else:
            return dt_input.astimezone(timezone.utc)
    
    if isinstance(dt_input, str):
        dt_input = dt_input.strip()
        if not dt_input:
            raise ValueError("Empty datetime string")
        # Common formats to try
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%m/%d/%Y %H:%M',
            '%d/%m/%Y %H:%M',
            '%Y-%m-%d',
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(dt_input, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        
        # Try parsing ISO format with timezone
        try:
            dt = datetime.fromisoformat(dt_input.replace('Z', '+00:00'))
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass

        # Best-effort fallback using dateutil if available
        try:
            from dateutil import parser as date_parser
            dt = date_parser.parse(dt_input)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    
    raise ValueError(f"Unable to parse datetime: {dt_input}")

def create_quick_event(summary, duration_hours=1, start_offset_hours=0):
    """Create a quick event starting now or with an offset"""
    try:
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        start_time = now + timedelta(hours=start_offset_hours)
        end_time = start_time + timedelta(hours=duration_hours)
        
        return create_event(summary, start_time, end_time)
        
    except Exception as e:
        logger.error(f"Error creating quick event: {e}")
        return f"❌ Error creating quick event: {str(e)}"

def delete_event(event_id):
    """Delete a calendar event"""
    try:
        service = get_calendar_service()
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return f"✅ Event deleted successfully"
        
    except HttpError as e:
        if e.resp.status == 404:
            return "❌ Event not found"
        else:
            return f"❌ Error deleting event: {e.resp.status}"
    except Exception as e:
        return f"❌ Error deleting event: {str(e)}"

def get_today_events():
    """Get events for today"""
    try:
        service = get_calendar_service()
        
        # Get start and end of today in UTC
        now = datetime.utcnow()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_of_day.isoformat() + 'Z',
            timeMax=end_of_day.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return "No events scheduled for today."
        
        event_list = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'No title')
            
            try:
                if 'T' in start:
                    dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    time_str = dt.strftime('%H:%M')
                else:
                    time_str = "All day"
                
                event_list.append(f"• {time_str} - {summary}")
            except Exception:
                event_list.append(f"• {summary}")
        
        return "Today's events:\n" + "\n".join(event_list)
        
    except Exception as e:
        logger.error(f"Error getting today's events: {e}")
        return f"❌ Error accessing today's events: {str(e)}"

def search_events(query, max_results=10):
    """Search for events by text"""
    try:
        service = get_calendar_service()
        
        now = datetime.utcnow().isoformat() + 'Z'
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime',
            q=query
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return f"No events found matching '{query}'"
        
        event_list = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'No title')
            
            try:
                if 'T' in start:
                    dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    formatted_time = dt.strftime('%Y-%m-%d %H:%M')
                else:
                    formatted_time = start
                
                event_list.append(f"• {summary} - {formatted_time}")
            except Exception:
                event_list.append(f"• {summary} - {start}")
        
        return f"Events matching '{query}':\n" + "\n".join(event_list)
        
    except Exception as e:
        logger.error(f"Error searching events: {e}")
        return f"❌ Error searching events: {str(e)}"

def get_calendar_summary(days_ahead=7):
    """Get an intelligent summary of upcoming calendar events"""
    try:
        service = get_calendar_service()
        
        # Get events for the next week
        now = datetime.utcnow()
        end_time = now + timedelta(days=days_ahead)
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now.isoformat() + 'Z',
            timeMax=end_time.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return f"📅 No events scheduled for the next {days_ahead} days."
        
        # Organize events by day
        events_by_day = {}
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'No title')
            description = event.get('description', '')
            location = event.get('location', '')
            
            try:
                if 'T' in start:
                    dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    day_key = dt.strftime('%A, %B %d')
                    time_str = dt.strftime('%H:%M')
                else:
                    # All-day event
                    dt = datetime.fromisoformat(start)
                    day_key = dt.strftime('%A, %B %d')
                    time_str = "All day"
                
                if day_key not in events_by_day:
                    events_by_day[day_key] = []
                
                event_info = {
                    'time': time_str,
                    'summary': summary,
                    'description': description,
                    'location': location
                }
                events_by_day[day_key].append(event_info)
                
            except Exception as e:
                logger.warning(f"Error parsing event time: {e}")
                continue
        
        # Format the summary
        summary_parts = [f"📅 Calendar Summary (Next {days_ahead} days):\n"]
        
        for day, day_events in events_by_day.items():
            summary_parts.append(f"\n🗓️ {day}")
            for event in day_events:
                event_line = f"  • {event['time']} - {event['summary']}"
                if event['location']:
                    event_line += f" 📍 {event['location']}"
                summary_parts.append(event_line)
        
        # Add quick stats
        total_events = len(events)
        days_with_events = len(events_by_day)
        summary_parts.append(f"\n📊 Summary: {total_events} events across {days_with_events} days")
        
        return "\n".join(summary_parts)
        
    except Exception as e:
        logger.error(f"Error getting calendar summary: {e}")
        return f"❌ Error getting calendar summary: {str(e)}"

def get_smart_calendar_brief():
    """Get an AI-friendly calendar brief for the assistant"""
    try:
        # Get raw calendar data
        calendar_summary = get_calendar_summary(7)
        today_events = get_today_events()
        
        # Create a simple intelligent summary without depending on gemini
        summary_parts = ["📅 Smart Calendar Brief:\n"]
        
        # Today's focus
        if "No events" not in today_events:
            summary_parts.append("🔥 Today's Focus:")
            summary_parts.append(today_events)
            summary_parts.append("")
        
        # Weekly overview
        summary_parts.append("📊 This Week:")
        summary_parts.append(calendar_summary)
        
        return "\n".join(summary_parts)
        
    except Exception as e:
        logger.error(f"Error generating smart calendar brief: {e}")
        # Fallback to simple summary
        return get_calendar_summary(7)
