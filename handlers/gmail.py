from googleapiclient.discovery import build
from handlers.google_auth import load_credentials

def list_emails():
    creds = load_credentials()
    service = build('gmail', 'v1', credentials=creds)
    results = service.users().messages().list(userId='me', maxResults=5).execute()
    messages = results.get('messages', [])

    emails = []
    for msg in messages:
        msg_detail = service.users().messages().get(userId='me', id=msg['id']).execute()
        snippet = msg_detail.get('snippet')
        emails.append(snippet)
    return emails

def send_email(to, subject, message_text):
    from email.mime.text import MIMEText
    import base64

    creds = load_credentials()
    service = build('gmail', 'v1', credentials=creds)

    message = MIMEText(message_text)
    message['to'] = to
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    return service.users().messages().send(userId="me", body={'raw': raw}).execute()


def summarize_emails(limit=5):
    creds = load_credentials()
    service = build('gmail', 'v1', credentials=creds)
    now = datetime.utcnow().isoformat() + 'Z'
    results = service.users().messages().list(userId='me', maxResults=limit, q="newer_than:1d").execute()
    messages = results.get('messages', [])

    summaries = []
    for msg in messages:
        msg_detail = service.users().messages().get(userId='me', id=msg['id']).execute()
        snippet = msg_detail.get('snippet')
        summaries.append(snippet)
    return "\n\n".join(summaries) if summaries else "No important emails today."
