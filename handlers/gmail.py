from datetime import datetime, timedelta
from googleapiclient.discovery import build
from handlers.google_auth import load_credentials
import logging
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

def get_gmail_service():
    """Get authenticated Gmail service"""
    try:
        creds = load_credentials()
        if not creds:
            raise Exception("No valid credentials available")
        
        service = build('gmail', 'v1', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Failed to create Gmail service: {e}")
        raise

def list_emails(max_results=10, query=""):
    """List emails with optional query filter"""
    try:
        service = get_gmail_service()
        
        # Build query with optional filters
        search_query = query if query else "in:inbox"
        
        results = service.users().messages().list(
            userId='me', 
            maxResults=max_results,
            q=search_query
        ).execute()
        messages = results.get('messages', [])

        emails = []
        for msg in messages:
            msg_detail = service.users().messages().get(userId='me', id=msg['id']).execute()
            
            # Extract headers
            headers = {h['name']: h['value'] for h in msg_detail['payload'].get('headers', [])}
            
            email_info = {
                'id': msg['id'],
                'subject': headers.get('Subject', 'No Subject'),
                'from': headers.get('From', 'Unknown Sender'),
                'date': headers.get('Date', 'Unknown Date'),
                'snippet': msg_detail.get('snippet', ''),
                'unread': 'UNREAD' in msg_detail.get('labelIds', [])
            }
            emails.append(email_info)
            
        return emails
    except Exception as e:
        logger.error(f"Error listing emails: {e}")
        return []

def send_email(to, subject, message_text, message_html=None):
    """Send email with improved formatting and error handling"""
    try:
        service = get_gmail_service()

        # Create message
        if message_html:
            message = MIMEMultipart('alternative')
            text_part = MIMEText(message_text, 'plain')
            html_part = MIMEText(message_html, 'html')
            message.attach(text_part)
            message.attach(html_part)
        else:
            message = MIMEText(message_text, 'plain')
        
        message['to'] = to
        message['subject'] = subject
        
        # Get user's email for 'from' field
        try:
            profile = service.users().getProfile(userId='me').execute()
            message['from'] = profile.get('emailAddress', 'me')
        except:
            pass
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        result = service.users().messages().send(userId="me", body={'raw': raw}).execute()
        logger.info(f"Email sent successfully: {result.get('id')}")
        return f"✅ Email sent successfully to {to}"
        
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return f"❌ Failed to send email: {str(e)}"

def summarize_emails(limit=10, days_back=1):
    """Create an intelligent email summary"""
    try:
        service = get_gmail_service()
        
        # Get emails from the last N days
        date_filter = f"newer_than:{days_back}d"
        query = f"in:inbox {date_filter}"
        
        results = service.users().messages().list(
            userId='me', 
            maxResults=limit,
            q=query
        ).execute()
        messages = results.get('messages', [])

        if not messages:
            return f"📧 No emails found in the last {days_back} day(s)."

        # Categorize emails
        important_emails = []
        unread_emails = []
        sender_counts = {}
        
        for msg in messages:
            try:
                msg_detail = service.users().messages().get(userId='me', id=msg['id']).execute()
                
                # Extract headers
                headers = {h['name']: h['value'] for h in msg_detail['payload'].get('headers', [])}
                
                subject = headers.get('Subject', 'No Subject')
                sender = headers.get('From', 'Unknown Sender')
                date = headers.get('Date', 'Unknown Date')
                snippet = msg_detail.get('snippet', '')
                is_unread = 'UNREAD' in msg_detail.get('labelIds', [])
                
                # Extract sender email for counting
                sender_email = sender.split('<')[-1].replace('>', '') if '<' in sender else sender
                sender_counts[sender_email] = sender_counts.get(sender_email, 0) + 1
                
                email_info = {
                    'subject': subject,
                    'sender': sender,
                    'date': date,
                    'snippet': snippet,
                    'unread': is_unread
                }
                
                # Categorize
                if is_unread:
                    unread_emails.append(email_info)
                
                # Check for importance indicators
                importance_keywords = ['urgent', 'important', 'asap', 'deadline', 'meeting', 'call']
                if any(keyword in subject.lower() or keyword in snippet.lower() for keyword in importance_keywords):
                    important_emails.append(email_info)
                    
            except Exception as e:
                logger.warning(f"Error processing email: {e}")
                continue

        # Build summary
        summary_parts = [f"📧 Email Summary (Last {days_back} day(s)):\n"]
        
        # Statistics
        total_emails = len(messages)
        unread_count = len(unread_emails)
        important_count = len(important_emails)
        
        summary_parts.append(f"📊 **Overview:**")
        summary_parts.append(f"   • Total emails: {total_emails}")
        summary_parts.append(f"   • Unread: {unread_count}")
        summary_parts.append(f"   • Flagged as important: {important_count}")
        summary_parts.append("")
        
        # Unread emails (most important)
        if unread_emails:
            summary_parts.append("🔴 **Unread Emails:**")
            for email in unread_emails[:5]:  # Top 5 unread
                summary_parts.append(f"   • **{email['subject']}**")
                summary_parts.append(f"     From: {email['sender']}")
                summary_parts.append(f"     Preview: {email['snippet'][:100]}...")
                summary_parts.append("")
        
        # Important emails
        if important_emails and len(important_emails) > len(unread_emails):
            summary_parts.append("⚡ **Important/Urgent Emails:**")
            shown_important = [e for e in important_emails if not e['unread']][:3]
            for email in shown_important:
                summary_parts.append(f"   • **{email['subject']}**")
                summary_parts.append(f"     From: {email['sender']}")
                summary_parts.append("")
        
        # Top senders
        if sender_counts:
            top_senders = sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            summary_parts.append("👥 **Most Active Senders:**")
            for sender, count in top_senders:
                summary_parts.append(f"   • {sender}: {count} emails")
            summary_parts.append("")
        
        # Add actionable suggestions
        if unread_count > 5:
            summary_parts.append("💡 **Suggestion:** You have many unread emails. Consider prioritizing the important ones.")
        elif unread_count == 0:
            summary_parts.append("✅ **Great!** You're all caught up on emails.")
        
        return "\n".join(summary_parts)
        
    except Exception as e:
        logger.error(f"Error summarizing emails: {e}")
        return f"❌ Error accessing emails: {str(e)}"

def search_emails(query, max_results=10):
    """Search emails with natural language query"""
    try:
        service = get_gmail_service()
        
        # Build Gmail search query
        search_query = query
        
        # Add some common filters if not specified
        if 'from:' not in query and 'to:' not in query and 'subject:' not in query:
            # Search in subject and body
            search_query = f"({query})"
        
        results = service.users().messages().list(
            userId='me',
            maxResults=max_results,
            q=search_query
        ).execute()
        
        messages = results.get('messages', [])
        
        if not messages:
            return f"📧 No emails found matching: {query}"
        
        found_emails = []
        for msg in messages:
            try:
                msg_detail = service.users().messages().get(userId='me', id=msg['id']).execute()
                headers = {h['name']: h['value'] for h in msg_detail['payload'].get('headers', [])}
                
                found_emails.append({
                    'subject': headers.get('Subject', 'No Subject'),
                    'from': headers.get('From', 'Unknown'),
                    'date': headers.get('Date', 'Unknown'),
                    'snippet': msg_detail.get('snippet', '')
                })
            except Exception as e:
                logger.warning(f"Error processing search result: {e}")
                continue
        
        # Format results
        result_parts = [f"🔍 **Email Search Results for: {query}**\n"]
        
        for i, email in enumerate(found_emails[:5], 1):
            result_parts.append(f"{i}. **{email['subject']}**")
            result_parts.append(f"   From: {email['from']}")
            result_parts.append(f"   Date: {email['date']}")
            result_parts.append(f"   Preview: {email['snippet'][:100]}...")
            result_parts.append("")
        
        if len(messages) > 5:
            result_parts.append(f"... and {len(messages) - 5} more results")
        
        return "\n".join(result_parts)
        
    except Exception as e:
        logger.error(f"Error searching emails: {e}")
        return f"❌ Error searching emails: {str(e)}"

def get_smart_email_brief():
    """Get an AI-friendly email brief for the assistant"""
    try:
        summary = summarize_emails(15, 1)  # Last day, more emails for better analysis
        return summary
    except Exception as e:
        logger.error(f"Error getting smart email brief: {e}")
        return "❌ Unable to access email summary"
