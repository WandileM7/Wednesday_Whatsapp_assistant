from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
import pytz
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
    """Parse various datetime input formats"""
    if isinstance(dt_input, datetime):
        return dt_input.replace(tzinfo=pytz.UTC) if dt_input.tzinfo is None else dt_input.astimezone(pytz.UTC)
    
    if isinstance(dt_input, str):
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
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(dt_input, fmt)
                return dt.replace(tzinfo=pytz.UTC)
            except ValueError:
                continue
        
        # Try parsing ISO format with timezone
        try:
            dt = datetime.fromisoformat(dt_input.replace('Z', '+00:00'))
            return dt.astimezone(pytz.UTC)
        except ValueError:
            pass
    
    raise ValueError(f"Unable to parse datetime: {dt_input}")

def create_quick_event(summary, duration_hours=1, start_offset_hours=0):
    """Create a quick event starting now or with an offset"""
    try:
        now = datetime.utcnow().replace(tzinfo=pytz.UTC)
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

