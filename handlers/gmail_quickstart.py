from __future__ import print_function
import base64
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def send_email_via_gmail(to, subject, body):
    creds = Credentials.from_authorized_user_file(
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS"), SCOPES)
    service = build('gmail', 'v1', credentials=creds)
    message = MIMEText(body)
    message['to'] = to
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    send_req = {'raw': raw}
    sent = service.users().messages().send(userId="me", body=send_req).execute()
    return f"Email sent to {to} (ID: {sent['id']})."
