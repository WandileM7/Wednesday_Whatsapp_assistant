from googleapiclient.discovery import build
from datetime import datetime, timedelta
from handlers.google_auth import load_credentials

def list_events():
    creds = load_credentials()
    service = build('calendar', 'v3', credentials=creds)
    now = datetime.utcnow().isoformat() + 'Z'
    events_result = service.events().list(
        calendarId='primary', timeMin=now, maxResults=5, singleEvents=True,
        orderBy='startTime').execute()
    return events_result.get('items', [])

def create_event(summary, location, start_time, end_time, attendees=None):
    creds = load_credentials()
    service = build('calendar', 'v3', credentials=creds)

    event = {
        'summary': summary,
        'location': location,
        'start': {'dateTime': start_time, 'timeZone': 'UTC'},
        'end': {'dateTime': end_time, 'timeZone': 'UTC'},
        'attendees': [{'email': email} for email in attendees] if attendees else []
    }

    return service.events().insert(calendarId='primary', body=event).execute()

