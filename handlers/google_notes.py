"""
Google Notes/Keep Integration for WhatsApp Assistant

Provides Google Keep notes and Google Tasks synchronization
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from handlers.google_auth import load_credentials

logger = logging.getLogger(__name__)

class GoogleNotesService:
    """Google Keep and Google Tasks integration service"""
    
    def __init__(self):
        # Note: Google Keep doesn't have a public API
        # This service focuses on Google Tasks API integration
        # and local notes that sync conceptually with Keep workflow
        self.tasks_scope = ['https://www.googleapis.com/auth/tasks']
        
    def _get_tasks_service(self):
        """Get authenticated Google Tasks service"""
        try:
            creds = load_credentials()
            if not creds:
                return None
            
            from googleapiclient.discovery import build
            return build('tasks', 'v1', credentials=creds)
        except Exception as e:
            logger.error(f"Error getting Tasks service: {e}")
            return None
    
    def create_note(self, title: str, content: str = "", tags: List[str] = None) -> str:
        """Create a new note (using Google Tasks as backend)"""
        try:
            service = self._get_tasks_service()
            if not service:
                return "❌ Google Tasks authentication required"
            
            # Get default task list
            task_lists = service.tasklists().list().execute()
            if not task_lists.get('items'):
                return "❌ No task lists found"
            
            default_list_id = task_lists['items'][0]['id']
            
            # Create task with note content
            task_body = {
                'title': title,
                'notes': content
            }
            
            if tags:
                task_body['notes'] = f"{content}\n\nTags: {', '.join(tags)}"
            
            result = service.tasks().insert(
                tasklist=default_list_id,
                body=task_body
            ).execute()
            
            response = "✅ Note created successfully!\n\n"
            response += f"📝 Title: {title}\n"
            response += f"🆔 Task ID: {result['id']}\n"
            
            if content:
                response += f"📄 Content: {content[:100]}{'...' if len(content) > 100 else ''}\n"
            
            if tags:
                response += f"🏷️ Tags: {', '.join(tags)}\n"
            
            return response
            
        except Exception as e:
            logger.error(f"Error creating note: {e}")
            return f"❌ Error creating note: {str(e)}"
    
    def search_notes(self, query: str) -> str:
        """Search notes in Google Tasks"""
        try:
            service = self._get_tasks_service()
            if not service:
                return "❌ Google Tasks authentication required"
            
            # Get all task lists
            task_lists = service.tasklists().list().execute()
            all_tasks = []
            
            for task_list in task_lists.get('items', []):
                tasks_result = service.tasks().list(
                    tasklist=task_list['id'],
                    showCompleted=True,
                    showHidden=True
                ).execute()
                
                for task in tasks_result.get('items', []):
                    # Search in title and notes
                    if (query.lower() in task.get('title', '').lower() or 
                        query.lower() in task.get('notes', '').lower()):
                        task['list_name'] = task_list['title']
                        all_tasks.append(task)
            
            if not all_tasks:
                return f"📝 No notes found matching '{query}'"
            
            response = f"🔍 Search Results for '{query}'\n"
            response += "=" * 30 + "\n\n"
            
            for i, task in enumerate(all_tasks[:10], 1):  # Limit to 10 results
                response += f"{i}. 📝 {task.get('title', 'Untitled')}\n"
                response += f"   📁 List: {task.get('list_name', 'Default')}\n"
                
                if task.get('notes'):
                    notes_preview = task['notes'][:100]
                    response += f"   📄 {notes_preview}{'...' if len(task['notes']) > 100 else ''}\n"
                
                if task.get('updated'):
                    updated = task['updated'][:10]  # Just the date part
                    response += f"   📅 Updated: {updated}\n"
                
                response += f"   🆔 ID: {task['id']}\n\n"
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error searching notes: {e}")
            return f"❌ Error searching notes: {str(e)}"
    
    def get_recent_notes(self, limit: int = 10) -> str:
        """Get recent notes from Google Tasks"""
        try:
            service = self._get_tasks_service()
            if not service:
                return "❌ Google Tasks authentication required"
            
            # Get all task lists
            task_lists = service.tasklists().list().execute()
            all_tasks = []
            
            for task_list in task_lists.get('items', []):
                tasks_result = service.tasks().list(
                    tasklist=task_list['id'],
                    showCompleted=True,
                    showHidden=True,
                    maxResults=20  # Get more to sort by date
                ).execute()
                
                for task in tasks_result.get('items', []):
                    task['list_name'] = task_list['title']
                    all_tasks.append(task)
            
            if not all_tasks:
                return "📝 No notes found"
            
            # Sort by updated date (most recent first)
            all_tasks.sort(key=lambda x: x.get('updated', ''), reverse=True)
            recent_tasks = all_tasks[:limit]
            
            response = f"📝 Recent Notes ({len(recent_tasks)})\n"
            response += "=" * 20 + "\n\n"
            
            for i, task in enumerate(recent_tasks, 1):
                response += f"{i}. 📝 {task.get('title', 'Untitled')}\n"
                response += f"   📁 List: {task.get('list_name', 'Default')}\n"
                
                if task.get('notes'):
                    notes_preview = task['notes'][:80]
                    response += f"   📄 {notes_preview}{'...' if len(task['notes']) > 80 else ''}\n"
                
                if task.get('updated'):
                    updated = task['updated'][:10]
                    response += f"   📅 {updated}\n"
                
                if task.get('status') == 'completed':
                    response += f"   ✅ Completed\n"
                
                response += "\n"
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error getting recent notes: {e}")
            return f"❌ Error getting recent notes: {str(e)}"
    
    def update_note(self, task_id: str, title: str = None, content: str = None) -> str:
        """Update an existing note"""
        try:
            service = self._get_tasks_service()
            if not service:
                return "❌ Google Tasks authentication required"
            
            # Find the task across all lists
            task_lists = service.tasklists().list().execute()
            found_task = None
            found_list_id = None
            
            for task_list in task_lists.get('items', []):
                try:
                    task = service.tasks().get(
                        tasklist=task_list['id'],
                        task=task_id
                    ).execute()
                    found_task = task
                    found_list_id = task_list['id']
                    break
                except:
                    continue
            
            if not found_task:
                return f"❌ Note with ID {task_id} not found"
            
            # Update task
            update_body = {}
            if title:
                update_body['title'] = title
            if content:
                update_body['notes'] = content
            
            if not update_body:
                return "❌ No updates provided"
            
            # Preserve existing values if not updating
            if 'title' not in update_body:
                update_body['title'] = found_task.get('title', '')
            if 'notes' not in update_body:
                update_body['notes'] = found_task.get('notes', '')
            
            update_body['id'] = task_id
            
            result = service.tasks().update(
                tasklist=found_list_id,
                task=task_id,
                body=update_body
            ).execute()
            
            response = "✅ Note updated successfully!\n\n"
            response += f"📝 Title: {result.get('title', 'Untitled')}\n"
            response += f"🆔 ID: {task_id}\n"
            
            if result.get('notes'):
                notes_preview = result['notes'][:100]
                response += f"📄 Content: {notes_preview}{'...' if len(result['notes']) > 100 else ''}\n"
            
            return response
            
        except Exception as e:
            logger.error(f"Error updating note: {e}")
            return f"❌ Error updating note: {str(e)}"
    
    def delete_note(self, task_id: str) -> str:
        """Delete a note"""
        try:
            service = self._get_tasks_service()
            if not service:
                return "❌ Google Tasks authentication required"
            
            # Find the task across all lists
            task_lists = service.tasklists().list().execute()
            found_list_id = None
            
            for task_list in task_lists.get('items', []):
                try:
                    service.tasks().get(
                        tasklist=task_list['id'],
                        task=task_id
                    ).execute()
                    found_list_id = task_list['id']
                    break
                except:
                    continue
            
            if not found_list_id:
                return f"❌ Note with ID {task_id} not found"
            
            service.tasks().delete(
                tasklist=found_list_id,
                task=task_id
            ).execute()
            
            return f"✅ Note {task_id} deleted successfully"
            
        except Exception as e:
            logger.error(f"Error deleting note: {e}")
            return f"❌ Error deleting note: {str(e)}"
    
    def sync_with_local_tasks(self) -> str:
        """Sync Google Tasks with local task management"""
        try:
            from handlers.tasks import task_manager
            
            service = self._get_tasks_service()
            if not service:
                return "❌ Google Tasks authentication required"
            
            # Get Google Tasks
            task_lists = service.tasklists().list().execute()
            google_tasks = []
            
            for task_list in task_lists.get('items', []):
                tasks_result = service.tasks().list(
                    tasklist=task_list['id'],
                    showCompleted=False
                ).execute()
                
                for task in tasks_result.get('items', []):
                    google_tasks.append({
                        'id': task['id'],
                        'title': task.get('title', ''),
                        'notes': task.get('notes', ''),
                        'due': task.get('due'),
                        'status': task.get('status'),
                        'list_name': task_list['title']
                    })
            
            # Sync with local tasks
            synced_count = 0
            for gtask in google_tasks:
                # Create or update local task
                local_task_id = task_manager.add_task(
                    title=gtask['title'],
                    description=gtask['notes'],
                    priority='medium',
                    tags=[f"google_sync", f"list_{gtask['list_name']}"]
                )
                synced_count += 1
            
            response = f"🔄 Sync completed successfully!\n\n"
            response += f"📊 Google Tasks found: {len(google_tasks)}\n"
            response += f"📝 Tasks synced to local: {synced_count}\n\n"
            response += "💡 Use 'list tasks' to see all synced tasks"
            
            return response
            
        except Exception as e:
            logger.error(f"Error syncing tasks: {e}")
            return f"❌ Error syncing tasks: {str(e)}"
    
    def get_service_status(self) -> str:
        """Get Google Notes service status"""
        status = "📝 Google Notes Service Status\n"
        status += "=" * 30 + "\n\n"
        
        # Check Google authentication
        creds = load_credentials()
        status += f"🔑 Google Auth: {'✅ Available' if creds else '❌ Not authenticated'}\n"
        
        # Check Tasks API access
        if creds:
            try:
                service = self._get_tasks_service()
                if service:
                    task_lists = service.tasklists().list().execute()
                    list_count = len(task_lists.get('items', []))
                    status += f"📋 Task Lists: {list_count} available\n"
                    status += f"🔌 Tasks API: ✅ Connected\n"
                else:
                    status += f"🔌 Tasks API: ❌ Connection failed\n"
            except Exception as e:
                status += f"🔌 Tasks API: ❌ Error - {str(e)[:50]}\n"
        
        status += f"📝 Google Keep: ⚠️ No public API (using Tasks as backend)\n\n"
        
        if not creds:
            status += "⚠️ Google authentication required\n"
            status += "Visit /google-login to authenticate"
        else:
            status += "✅ Notes service ready\n"
            status += "💡 Notes are stored as Google Tasks for API access"
        
        return status

# Global Google Notes service instance
google_notes_service = GoogleNotesService()