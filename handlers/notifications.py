"""
Task Completion Notification System for Wednesday WhatsApp Assistant

Provides proactive task management and completion notifications:
- Real-time task completion tracking
- Automated status updates to users
- Smart reminder systems
- Progress monitoring and reporting
"""

import logging
import threading
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from database import db_manager
import json

logger = logging.getLogger(__name__)

class TaskNotificationSystem:
    """Advanced task completion and notification system"""
    
    def __init__(self, send_message_callback=None):
        self.send_message_callback = send_message_callback
        self.notification_thread = None
        self.running = False
        self.check_interval = 30  # Check every 30 seconds
        self.notification_history = {}
        
    def start_notification_service(self):
        """Start the background notification service"""
        if self.running:
            logger.warning("Notification service already running")
            return
        
        self.running = True
        self.notification_thread = threading.Thread(target=self._notification_worker, daemon=True)
        self.notification_thread.start()
        logger.info("Task notification service started")
    
    def stop_notification_service(self):
        """Stop the background notification service"""
        self.running = False
        if self.notification_thread:
            self.notification_thread.join(timeout=5)
        logger.info("Task notification service stopped")
    
    def _notification_worker(self):
        """Background worker for checking and sending notifications"""
        while self.running:
            try:
                self._check_due_reminders()
                self._check_task_deadlines()
                self._send_proactive_updates()
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Notification worker error: {e}")
                time.sleep(60)  # Wait longer on error
    
    def _check_due_reminders(self):
        """Check for due reminders and send notifications"""
        try:
            due_reminders = db_manager.get_due_reminders()
            
            for reminder in due_reminders:
                success = self._send_reminder_notification(reminder)
                if success:
                    db_manager.mark_reminder_notified(reminder['id'])
                    
        except Exception as e:
            logger.error(f"Failed to check due reminders: {e}")
    
    def _check_task_deadlines(self):
        """Check for approaching task deadlines"""
        try:
            # Get all incomplete tasks
            # This would need to be implemented in database.py
            # For now, we'll use a placeholder approach
            
            # Check tasks due in next 24 hours
            tomorrow = (datetime.now() + timedelta(days=1)).isoformat()
            
            # Placeholder: In a real implementation, you'd query the database
            # for tasks with due_date approaching
            
        except Exception as e:
            logger.error(f"Failed to check task deadlines: {e}")
    
    def _send_proactive_updates(self):
        """Send proactive updates about task progress"""
        try:
            # Send daily summaries, weekly reports, etc.
            current_hour = datetime.now().hour
            
            # Send morning summary at 9 AM
            if current_hour == 9:
                self._send_morning_summary()
            
            # Send evening summary at 6 PM
            elif current_hour == 18:
                self._send_evening_summary()
                
        except Exception as e:
            logger.error(f"Failed to send proactive updates: {e}")
    
    def _send_reminder_notification(self, reminder: Dict) -> bool:
        """Send reminder notification to user"""
        try:
            if not self.send_message_callback:
                logger.warning("No send message callback configured")
                return False
            
            phone = reminder['phone']
            message = f"⏰ **Reminder**\n\n{reminder['message']}"
            
            # Add contextual information
            if reminder.get('metadata'):
                metadata = json.loads(reminder['metadata']) if isinstance(reminder['metadata'], str) else reminder['metadata']
                if metadata.get('priority'):
                    priority_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(metadata['priority'], '⚪')
                    message = f"{priority_emoji} {message}"
            
            success = self.send_message_callback(phone, message)
            
            if success:
                logger.info(f"Sent reminder notification to {phone}")
                self._log_notification(phone, 'reminder', reminder['id'])
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to send reminder notification: {e}")
            return False
    
    def notify_task_completion(self, phone: str, task_id: str, task_title: str, completion_details: Dict = None):
        """Send task completion notification"""
        try:
            if not self.send_message_callback:
                logger.warning("No send message callback configured")
                return False
            
            # Create completion message
            message = f"✅ **Task Completed!**\n\n📋 {task_title}\n🕒 Completed: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            # Add additional details if provided
            if completion_details:
                if completion_details.get('duration'):
                    message += f"\n⏱️ Duration: {completion_details['duration']}"
                if completion_details.get('notes'):
                    message += f"\n📝 Notes: {completion_details['notes']}"
            
            # Add encouraging message
            encouraging_messages = [
                "Great job! 🎉",
                "Well done! 👏",
                "Task accomplished! 🌟",
                "Excellent work! 💪",
                "Mission complete! 🚀"
            ]
            
            import random
            encouragement = random.choice(encouraging_messages)
            message += f"\n\n{encouragement}"
            
            success = self.send_message_callback(phone, message)
            
            if success:
                logger.info(f"Sent task completion notification to {phone}")
                self._log_notification(phone, 'task_completion', task_id)
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to send task completion notification: {e}")
            return False
    
    def notify_email_sent(self, phone: str, email_details: Dict):
        """Notify user that email was sent successfully"""
        try:
            if not self.send_message_callback:
                return False
            
            recipient = email_details.get('to', 'recipient')
            subject = email_details.get('subject', 'your email')
            
            message = f"📧 **Email Sent Successfully!**\n\n"
            message += f"📬 To: {recipient}\n"
            message += f"📋 Subject: {subject}\n"
            message += f"🕒 Sent: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            message += "✅ Your email has been delivered!"
            
            success = self.send_message_callback(phone, message)
            
            if success:
                self._log_notification(phone, 'email_sent', email_details.get('message_id', 'unknown'))
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            return False
    
    def notify_calendar_event_created(self, phone: str, event_details: Dict):
        """Notify user that calendar event was created"""
        try:
            if not self.send_message_callback:
                return False
            
            title = event_details.get('title', 'New Event')
            start_time = event_details.get('start_time', 'TBD')
            
            message = f"📅 **Calendar Event Created!**\n\n"
            message += f"📋 Event: {title}\n"
            message += f"🕒 Time: {start_time}\n"
            message += f"✅ Added to your calendar successfully!"
            
            if event_details.get('meeting_link'):
                message += f"\n🔗 Meeting Link: {event_details['meeting_link']}"
            
            success = self.send_message_callback(phone, message)
            
            if success:
                self._log_notification(phone, 'calendar_event', event_details.get('event_id', 'unknown'))
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to send calendar notification: {e}")
            return False
    
    def notify_action_completed(self, phone: str, action_type: str, action_details: Dict):
        """Generic notification for completed actions"""
        try:
            if not self.send_message_callback:
                return False
            
            action_emojis = {
                'music_played': '🎵',
                'weather_checked': '🌤️',
                'news_fetched': '📰',
                'contact_messaged': '💬',
                'file_saved': '💾',
                'search_completed': '🔍',
                'reminder_set': '⏰',
                'note_created': '📝'
            }
            
            emoji = action_emojis.get(action_type, '✅')
            action_name = action_type.replace('_', ' ').title()
            
            message = f"{emoji} **{action_name}**\n\n"
            
            # Add specific details based on action type
            if action_type == 'music_played':
                message += f"🎧 Now playing: {action_details.get('track', 'Unknown')}\n"
                message += f"🎤 Artist: {action_details.get('artist', 'Unknown')}"
            
            elif action_type == 'contact_messaged':
                message += f"👤 Contact: {action_details.get('contact_name', 'Unknown')}\n"
                message += f"📱 Message sent successfully!"
            
            elif action_type == 'file_saved':
                message += f"📁 File: {action_details.get('filename', 'Unknown')}\n"
                message += f"💾 Saved to: {action_details.get('location', 'Default location')}"
            
            else:
                # Generic success message
                message += f"✅ {action_name} completed successfully!"
                
                if action_details.get('summary'):
                    message += f"\n\n📋 Summary: {action_details['summary']}"
            
            message += f"\n\n🕒 Completed: {datetime.now().strftime('%H:%M')}"
            
            success = self.send_message_callback(phone, message)
            
            if success:
                self._log_notification(phone, action_type, str(action_details))
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to send action notification: {e}")
            return False
    
    def _send_morning_summary(self):
        """Send morning task summary to active users"""
        try:
            # Get all users with active tasks or reminders
            # This would query the database for active users
            # For now, we'll use a placeholder
            
            logger.info("Morning summary feature not yet implemented")
            
        except Exception as e:
            logger.error(f"Failed to send morning summary: {e}")
    
    def _send_evening_summary(self):
        """Send evening progress summary to active users"""
        try:
            # Get task completion stats for the day
            # Send progress reports
            
            logger.info("Evening summary feature not yet implemented")
            
        except Exception as e:
            logger.error(f"Failed to send evening summary: {e}")
    
    def _log_notification(self, phone: str, notification_type: str, reference_id: str):
        """Log notification for tracking and preventing duplicates"""
        try:
            timestamp = datetime.now().isoformat()
            
            if phone not in self.notification_history:
                self.notification_history[phone] = []
            
            self.notification_history[phone].append({
                'type': notification_type,
                'reference_id': reference_id,
                'timestamp': timestamp
            })
            
            # Keep only last 100 notifications per user
            self.notification_history[phone] = self.notification_history[phone][-100:]
            
        except Exception as e:
            logger.error(f"Failed to log notification: {e}")
    
    def get_notification_stats(self, phone: str = None) -> Dict:
        """Get notification statistics"""
        try:
            if phone:
                user_notifications = self.notification_history.get(phone, [])
                return {
                    'total_notifications': len(user_notifications),
                    'recent_notifications': user_notifications[-10:],
                    'notification_types': self._count_notification_types(user_notifications)
                }
            else:
                total_notifications = sum(len(notifications) for notifications in self.notification_history.values())
                active_users = len(self.notification_history)
                
                return {
                    'total_notifications': total_notifications,
                    'active_users': active_users,
                    'service_running': self.running,
                    'check_interval': self.check_interval
                }
                
        except Exception as e:
            logger.error(f"Failed to get notification stats: {e}")
            return {}
    
    def _count_notification_types(self, notifications: List[Dict]) -> Dict:
        """Count notification types for statistics"""
        counts = {}
        for notification in notifications:
            notification_type = notification.get('type', 'unknown')
            counts[notification_type] = counts.get(notification_type, 0) + 1
        return counts
    
    def set_send_message_callback(self, callback):
        """Set the callback function for sending messages"""
        self.send_message_callback = callback
        logger.info("Send message callback configured for notifications")

# Global notification system instance
task_notification_system = TaskNotificationSystem()