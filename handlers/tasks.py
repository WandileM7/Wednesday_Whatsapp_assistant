"""
Task and Reminder Management for WhatsApp Assistant

Provides task management functionality with persistent storage
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class Task:
    """Task data structure"""
    id: str
    title: str
    description: str = ""
    due_date: Optional[str] = None
    priority: str = "medium"  # low, medium, high, urgent
    completed: bool = False
    created_at: str = ""
    completed_at: Optional[str] = None
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

@dataclass
class Reminder:
    """Reminder data structure"""
    id: str
    message: str
    remind_at: str
    created_at: str = ""
    notified: bool = False
    phone: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

class TaskManager:
    """Task and reminder management service"""
    
    def __init__(self):
        self.data_dir = Path("task_data")
        self.data_dir.mkdir(exist_ok=True)
        self.tasks_file = self.data_dir / "tasks.json"
        self.reminders_file = self.data_dir / "reminders.json"
        
        self.tasks = self._load_tasks()
        self.reminders = self._load_reminders()
    
    def _load_tasks(self) -> Dict[str, Task]:
        """Load tasks from file"""
        try:
            if self.tasks_file.exists():
                with open(self.tasks_file, 'r') as f:
                    data = json.load(f)
                    return {task_id: Task(**task_data) for task_id, task_data in data.items()}
            return {}
        except Exception as e:
            logger.error(f"Error loading tasks: {e}")
            return {}
    
    def _save_tasks(self):
        """Save tasks to file"""
        try:
            data = {task_id: asdict(task) for task_id, task in self.tasks.items()}
            with open(self.tasks_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving tasks: {e}")
    
    def _load_reminders(self) -> Dict[str, Reminder]:
        """Load reminders from file"""
        try:
            if self.reminders_file.exists():
                with open(self.reminders_file, 'r') as f:
                    data = json.load(f)
                    return {reminder_id: Reminder(**reminder_data) for reminder_id, reminder_data in data.items()}
            return {}
        except Exception as e:
            logger.error(f"Error loading reminders: {e}")
            return {}
    
    def _save_reminders(self):
        """Save reminders to file"""
        try:
            data = {reminder_id: asdict(reminder) for reminder_id, reminder in self.reminders.items()}
            with open(self.reminders_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving reminders: {e}")
    
    def create_task(self, title: str, description: str = "", due_date: Optional[str] = None, 
                   priority: str = "medium", tags: List[str] = None, auto_sync: bool = True) -> str:
        """Create a new task with optional real-time sync to Google Keep/Tasks"""
        import uuid
        
        task_id = str(uuid.uuid4())[:8]
        task = Task(
            id=task_id,
            title=title,
            description=description,
            due_date=due_date,
            priority=priority,
            tags=tags or []
        )
        
        self.tasks[task_id] = task
        self._save_tasks()
        
        response = f"✅ Task created: '{title}' (ID: {task_id})"
        
        # Automatically sync to Google Keep/Tasks if enabled
        if auto_sync:
            try:
                sync_result = self._sync_single_task_to_google(task)
                if "✅" in sync_result:
                    response += f"\n☁️ Synced to Google Tasks/Keep"
                else:
                    response += f"\n⚠️ Local only (Google sync failed)"
            except Exception as e:
                logger.warning(f"Auto-sync to Google failed: {e}")
                response += f"\n⚠️ Local only (Google unavailable)"
        
        return response
    
    def list_tasks(self, filter_completed: bool = False, filter_priority: Optional[str] = None) -> str:
        """List all tasks"""
        if not self.tasks:
            return "📝 No tasks found. Create one with 'create task [title]'"
        
        filtered_tasks = []
        for task in self.tasks.values():
            if filter_completed and task.completed:
                continue
            if filter_priority and task.priority != filter_priority:
                continue
            filtered_tasks.append(task)
        
        if not filtered_tasks:
            return "📝 No tasks match your criteria."
        
        # Sort by priority and due date
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        filtered_tasks.sort(key=lambda t: (
            t.completed,
            priority_order.get(t.priority, 2),
            t.due_date or "9999-12-31"
        ))
        
        result = "📝 Your Tasks:\n"
        result += "=" * 15 + "\n\n"
        
        for task in filtered_tasks:
            status = "✅" if task.completed else "⏳"
            priority_emoji = self._get_priority_emoji(task.priority)
            
            result += f"{status} {priority_emoji} {task.title} (#{task.id})\n"
            
            if task.description:
                result += f"   📄 {task.description}\n"
            
            if task.due_date:
                due_str = self._format_due_date(task.due_date)
                result += f"   📅 Due: {due_str}\n"
            
            if task.tags:
                tags_str = " ".join([f"#{tag}" for tag in task.tags])
                result += f"   🏷️ {tags_str}\n"
            
            result += "\n"
        
        return result.strip()
    
    def complete_task(self, task_id: str) -> str:
        """Mark a task as completed"""
        if task_id not in self.tasks:
            return f"❌ Task #{task_id} not found."
        
        task = self.tasks[task_id]
        if task.completed:
            return f"✅ Task '{task.title}' is already completed."
        
        task.completed = True
        task.completed_at = datetime.now().isoformat()
        self._save_tasks()
        
        return f"🎉 Task completed: '{task.title}'"
    
    def delete_task(self, task_id: str) -> str:
        """Delete a task"""
        if task_id not in self.tasks:
            return f"❌ Task #{task_id} not found."
        
        task = self.tasks[task_id]
        del self.tasks[task_id]
        self._save_tasks()
        
        return f"🗑️ Task deleted: '{task.title}'"
    
    def create_reminder(self, message: str, remind_at: str, phone: str = "") -> str:
        """Create a new reminder"""
        import uuid
        
        try:
            # Validate remind_at format
            datetime.fromisoformat(remind_at)
        except ValueError:
            return "❌ Invalid date format. Use YYYY-MM-DD HH:MM format."
        
        reminder_id = str(uuid.uuid4())[:8]
        reminder = Reminder(
            id=reminder_id,
            message=message,
            remind_at=remind_at,
            phone=phone
        )
        
        self.reminders[reminder_id] = reminder
        self._save_reminders()
        
        return f"⏰ Reminder set: '{message}' at {remind_at} (ID: {reminder_id})"
    
    def list_reminders(self, include_past: bool = False) -> str:
        """List all reminders"""
        if not self.reminders:
            return "⏰ No reminders found. Create one with 'remind me [message] at [time]'"
        
        now = datetime.now()
        filtered_reminders = []
        
        for reminder in self.reminders.values():
            remind_datetime = datetime.fromisoformat(reminder.remind_at)
            
            if not include_past and remind_datetime < now and reminder.notified:
                continue
                
            filtered_reminders.append(reminder)
        
        if not filtered_reminders:
            return "⏰ No upcoming reminders."
        
        # Sort by remind_at time
        filtered_reminders.sort(key=lambda r: r.remind_at)
        
        result = "⏰ Your Reminders:\n"
        result += "=" * 18 + "\n\n"
        
        for reminder in filtered_reminders:
            status = "🔔" if not reminder.notified else "✅"
            remind_str = self._format_reminder_time(reminder.remind_at)
            
            result += f"{status} {reminder.message} (#{reminder.id})\n"
            result += f"   📅 {remind_str}\n\n"
        
        return result.strip()
    
    def get_due_reminders(self) -> List[Reminder]:
        """Get reminders that are due now"""
        now = datetime.now()
        due_reminders = []
        
        for reminder in self.reminders.values():
            if reminder.notified:
                continue
                
            remind_datetime = datetime.fromisoformat(reminder.remind_at)
            if remind_datetime <= now:
                due_reminders.append(reminder)
        
        return due_reminders
    
    def mark_reminder_notified(self, reminder_id: str):
        """Mark a reminder as notified"""
        if reminder_id in self.reminders:
            self.reminders[reminder_id].notified = True
            self._save_reminders()
    
    def get_task_summary(self) -> str:
        """Get a summary of tasks and reminders"""
        total_tasks = len(self.tasks)
        completed_tasks = sum(1 for task in self.tasks.values() if task.completed)
        pending_tasks = total_tasks - completed_tasks
        
        urgent_tasks = sum(1 for task in self.tasks.values() 
                          if not task.completed and task.priority == "urgent")
        
        total_reminders = len(self.reminders)
        due_reminders = len(self.get_due_reminders())
        
        result = "📊 Task & Reminder Summary\n"
        result += "=" * 25 + "\n\n"
        result += f"📝 Tasks: {pending_tasks} pending, {completed_tasks} completed\n"
        
        if urgent_tasks > 0:
            result += f"🚨 Urgent tasks: {urgent_tasks}\n"
        
        result += f"⏰ Reminders: {total_reminders} total"
        
        if due_reminders > 0:
            result += f", {due_reminders} due now!"
        
        return result
    
    def _get_priority_emoji(self, priority: str) -> str:
        """Get emoji for priority level"""
        priority_emojis = {
            "urgent": "🚨",
            "high": "🔴",
            "medium": "🟡",
            "low": "🟢"
        }
        return priority_emojis.get(priority, "🟡")
    
    def _format_due_date(self, due_date: str) -> str:
        """Format due date for display"""
        try:
            due_datetime = datetime.fromisoformat(due_date)
            now = datetime.now()
            
            if due_datetime.date() == now.date():
                return f"Today at {due_datetime.strftime('%H:%M')}"
            elif due_datetime.date() == (now + timedelta(days=1)).date():
                return f"Tomorrow at {due_datetime.strftime('%H:%M')}"
            else:
                return due_datetime.strftime('%Y-%m-%d %H:%M')
        except:
            return due_date
    
    def _format_reminder_time(self, remind_at: str) -> str:
        """Format reminder time for display"""
        try:
            remind_datetime = datetime.fromisoformat(remind_at)
            now = datetime.now()
            
            if remind_datetime.date() == now.date():
                return f"Today at {remind_datetime.strftime('%H:%M')}"
            elif remind_datetime.date() == (now + timedelta(days=1)).date():
                return f"Tomorrow at {remind_datetime.strftime('%H:%M')}"
            else:
                return remind_datetime.strftime('%Y-%m-%d %H:%M')
        except:
            return remind_at

    def _sync_single_task_to_google(self, task: Task) -> str:
        """Sync a single task to Google Keep/Tasks (internal helper)"""
        try:
            from handlers.google_notes import google_notes_service
            
            # Skip completed tasks
            if task.completed:
                return "⏭️ Skipped (completed)"
            
            # Create task content with details
            content = f"Description: {task.description}\n" if task.description else ""
            if task.priority != "medium":
                content += f"Priority: {task.priority}\n"
            if task.due_date:
                content += f"Due: {task.due_date}\n"
            if task.tags:
                content += f"Tags: {', '.join(task.tags)}\n"
            content += f"Created: {task.created_at}\n"
            content += f"Local ID: {task.id}"
            
            # Create note in Google Tasks
            result = google_notes_service.create_note(
                title=task.title,
                content=content,
                tags=task.tags + ["auto_synced"]
            )
            
            return result
            
        except ImportError:
            return "❌ Google Notes service not available"
        except Exception as e:
            logger.error(f"Error syncing single task: {e}")
            return f"❌ Sync failed: {str(e)}"
    
    def sync_to_google_keep(self) -> str:
        """Sync local tasks to Google Keep (via Google Tasks API)"""
        try:
            from handlers.google_notes import google_notes_service
            
            if not self.tasks:
                return "📝 No local tasks to sync"
            
            synced_count = 0
            failed_count = 0
            results = []
            
            for task_id, task in self.tasks.items():
                try:
                    # Skip already completed tasks unless specifically requested
                    if task.completed:
                        continue
                    
                    # Create task content with details
                    content = f"Description: {task.description}\n" if task.description else ""
                    if task.priority != "medium":
                        content += f"Priority: {task.priority}\n"
                    if task.due_date:
                        content += f"Due: {task.due_date}\n"
                    if task.tags:
                        content += f"Tags: {', '.join(task.tags)}\n"
                    content += f"Created: {task.created_at}\n"
                    content += f"Local ID: {task_id}"
                    
                    # Create note in Google Tasks
                    result = google_notes_service.create_note(
                        title=task.title,
                        content=content,
                        tags=task.tags + ["synced_from_local"]
                    )
                    
                    if "✅" in result:  # Success indicator
                        synced_count += 1
                        results.append(f"✅ {task.title}")
                    else:
                        failed_count += 1
                        results.append(f"❌ {task.title}: {result}")
                        
                except Exception as e:
                    failed_count += 1
                    results.append(f"❌ {task.title}: {str(e)}")
            
            response = f"🔄 Google Keep Sync Results\n"
            response += "=" * 25 + "\n\n"
            response += f"📊 Synced: {synced_count}, Failed: {failed_count}\n\n"
            
            if results:
                response += "📝 Details:\n"
                for result in results[:10]:  # Limit to 10 results
                    response += f"  {result}\n"
                
                if len(results) > 10:
                    response += f"  ... and {len(results) - 10} more\n"
            
            if synced_count > 0:
                response += "\n💡 Tasks are now available in Google Tasks/Keep"
            
            return response
            
        except ImportError:
            return "❌ Google Notes service not available"
        except Exception as e:
            logger.error(f"Error syncing to Google Keep: {e}")
            return f"❌ Sync failed: {str(e)}"
    
    def sync_from_google_keep(self) -> str:
        """Sync tasks from Google Keep (via Google Tasks API) to local storage"""
        try:
            from handlers.google_notes import google_notes_service
            
            # Get recent notes/tasks from Google
            google_tasks_response = google_notes_service.get_recent_notes(limit=20)
            
            if "❌" in google_tasks_response:
                return google_tasks_response
            
            # This is a simplified implementation - in practice you'd need to parse the response
            # For now, just return the sync status message
            response = "🔄 Google Keep → Local Sync\n"
            response += "=" * 25 + "\n\n"
            response += "⚠️ Automated sync from Google Tasks to local storage\n"
            response += "requires additional parsing implementation.\n\n"
            response += "💡 For now, you can:\n"
            response += "1. Use 'sync to google' to send local tasks to Google\n"
            response += "2. View Google tasks with 'recent notes'\n"
            response += "3. Create tasks directly in Google with 'create note'\n\n"
            response += "📋 Current Google Tasks status:\n"
            response += google_tasks_response[:200] + "..." if len(google_tasks_response) > 200 else google_tasks_response
            
            return response
            
        except ImportError:
            return "❌ Google Notes service not available"
        except Exception as e:
            logger.error(f"Error syncing from Google Keep: {e}")
            return f"❌ Sync failed: {str(e)}"
    
    def get_sync_status(self) -> str:
        """Get synchronization status with Google Keep"""
        try:
            from handlers.google_notes import google_notes_service
            
            status = "🔄 Google Keep Sync Status\n"
            status += "=" * 25 + "\n\n"
            
            # Local task counts
            total_local = len(self.tasks)
            pending_local = sum(1 for task in self.tasks.values() if not task.completed)
            
            status += f"🏠 Local Tasks: {pending_local} pending, {total_local - pending_local} completed\n"
            
            # Google service status
            google_status = google_notes_service.get_service_status()
            if "✅" in google_status:
                status += f"☁️ Google Tasks: Connected\n\n"
                status += "🔄 Available Sync Operations:\n"
                status += "  • sync to google - Send local tasks to Google\n"
                status += "  • sync from google - Import Google tasks to local\n"
                status += "  • create note [title] - Create task directly in Google\n"
                status += "  • search notes [query] - Search Google tasks\n"
            else:
                status += f"☁️ Google Tasks: ❌ Not authenticated\n\n"
                status += "⚠️ Google authentication required for sync\n"
                status += "Visit /google-login to authenticate\n"
            
            return status
            
        except ImportError:
            return "❌ Google Notes service not available"
        except Exception as e:
            logger.error(f"Error getting sync status: {e}")
            return f"❌ Status check failed: {str(e)}"


# Global task manager instance
task_manager = TaskManager()


# Background Task Sync Service
import threading
import time

class BackgroundTaskSync:
    """Background service for periodic task synchronization with Google Keep"""
    
    def __init__(self, task_manager: TaskManager, sync_interval: int = 1800):
        self.task_manager = task_manager
        self.sync_interval = sync_interval  # Default 30 minutes
        self.running = False
        self.thread = None
        self.last_sync = None
        self.sync_stats = {
            "total_syncs": 0,
            "successful_syncs": 0,
            "failed_syncs": 0,
            "last_sync_time": None,
            "last_error": None
        }
    
    def start(self):
        """Start the background sync service"""
        if self.running:
            logger.info("Background task sync already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._sync_loop, daemon=True, name="TaskSyncService")
        self.thread.start()
        logger.info(f"Background task sync service started (interval: {self.sync_interval}s)")
    
    def stop(self):
        """Stop the background sync service"""
        self.running = False
        logger.info("Background task sync service stopped")
    
    def _sync_loop(self):
        """Main sync loop that runs in background"""
        while self.running:
            try:
                # Wait for the sync interval
                time.sleep(self.sync_interval)
                
                if not self.running:
                    break
                
                # Perform sync
                self._perform_sync()
                
            except Exception as e:
                logger.error(f"Error in background task sync loop: {e}")
                self.sync_stats["last_error"] = str(e)
                # Continue running even if sync fails
                time.sleep(60)  # Wait a minute before retrying
    
    def _perform_sync(self):
        """Perform the actual synchronization"""
        try:
            logger.info("Starting background task sync to Google Keep...")
            self.sync_stats["total_syncs"] += 1
            
            # Get unsynced tasks (those created since last sync)
            unsynced_tasks = []
            for task in self.task_manager.tasks.values():
                if not task.completed:
                    # Check if task was created since last sync
                    if self.last_sync is None or task.created_at > self.last_sync:
                        unsynced_tasks.append(task)
            
            if not unsynced_tasks:
                logger.info("No new tasks to sync")
                self.last_sync = datetime.now().isoformat()
                return
            
            # Sync each unsynced task
            synced_count = 0
            failed_count = 0
            
            for task in unsynced_tasks:
                try:
                    result = self.task_manager._sync_single_task_to_google(task)
                    if "✅" in result:
                        synced_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    logger.warning(f"Failed to sync task {task.id}: {e}")
                    failed_count += 1
            
            # Update stats
            if failed_count == 0:
                self.sync_stats["successful_syncs"] += 1
            else:
                self.sync_stats["failed_syncs"] += 1
            
            self.last_sync = datetime.now().isoformat()
            self.sync_stats["last_sync_time"] = self.last_sync
            
            logger.info(f"Background sync complete: {synced_count} synced, {failed_count} failed")
            
        except Exception as e:
            logger.error(f"Error performing background sync: {e}")
            self.sync_stats["failed_syncs"] += 1
            self.sync_stats["last_error"] = str(e)
    
    def get_status(self) -> Dict[str, Any]:
        """Get sync service status"""
        return {
            "running": self.running,
            "sync_interval": self.sync_interval,
            "last_sync": self.last_sync,
            "stats": self.sync_stats
        }

# Global background sync service instance
background_sync_service = BackgroundTaskSync(task_manager, sync_interval=int(os.getenv("TASK_SYNC_INTERVAL", "1800")))