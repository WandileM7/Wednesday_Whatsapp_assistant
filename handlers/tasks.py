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
                   priority: str = "medium", tags: List[str] = None) -> str:
        """Create a new task"""
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
        
        return f"✅ Task created: '{title}' (ID: {task_id})"
    
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


# Global task manager instance
task_manager = TaskManager()