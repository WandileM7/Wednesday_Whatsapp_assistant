"""
SQLite Database Manager for Wednesday WhatsApp Assistant

Replaces ChromaDB with a lightweight, reliable SQLite database for:
- Conversation history
- Task management
- User preferences
- Media metadata
- System state
"""

import sqlite3
import logging
import os
import json
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import threading

logger = logging.getLogger(__name__)

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class DatabaseManager:
    """SQLite database manager for the WhatsApp Assistant"""
    
    def __init__(self, db_path: str = "assistant.db"):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Conversations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    role TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            ''')
            
            # Tasks table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    phone TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    due_date TEXT,
                    priority TEXT DEFAULT 'medium',
                    completed BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME,
                    tags TEXT,
                    metadata TEXT
                )
            ''')
            
            # Reminders table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    phone TEXT NOT NULL,
                    message TEXT NOT NULL,
                    remind_at DATETIME NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    notified BOOLEAN DEFAULT 0,
                    metadata TEXT
                )
            ''')
            
            # User preferences table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    phone TEXT PRIMARY KEY,
                    preferences TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Media metadata table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS media (
                    id TEXT PRIMARY KEY,
                    phone TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    file_path TEXT,
                    file_size INTEGER,
                    mime_type TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            ''')
            
            # System state table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes for better performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversations_phone ON conversations(phone)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_phone ON tasks(phone)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_completed ON tasks(completed)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reminders_phone ON reminders(phone)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reminders_remind_at ON reminders(remind_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_media_phone ON media(phone)')
            
            conn.commit()
            conn.close()
            logger.info(f"Database initialized: {self.db_path}")
    
    def add_conversation(self, phone: str, role: str, message: str, metadata: Dict = None) -> bool:
        """Add message to conversation history"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO conversations (phone, role, message, metadata)
                    VALUES (?, ?, ?, ?)
                ''', (phone, role, message, json.dumps(metadata) if metadata else None))
                
                conn.commit()
                conn.close()
                
                # Keep only last 1000 messages per phone to manage storage
                self._cleanup_old_conversations(phone)
                
                logger.debug(f"Added conversation: {phone} - {role}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to add conversation: {e}")
            return False
    
    def get_conversation_history(self, phone: str, limit: int = 10) -> List[str]:
        """Get recent conversation history"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT role, message FROM conversations 
                    WHERE phone = ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (phone, limit))
                
                results = cursor.fetchall()
                conn.close()
                
                # Return in chronological order (oldest first)
                return [f"{role}: {message}" for role, message in reversed(results)]
                
        except Exception as e:
            logger.error(f"Failed to get conversation history: {e}")
            return []
    
    def search_conversations(self, phone: str, query: str, limit: int = 5) -> List[str]:
        """Search conversation history"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT role, message FROM conversations 
                    WHERE phone = ? AND message LIKE ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (phone, f"%{query}%", limit))
                
                results = cursor.fetchall()
                conn.close()
                
                return [f"{role}: {message}" for role, message in results]
                
        except Exception as e:
            logger.error(f"Failed to search conversations: {e}")
            return []
    
    def add_task(self, task_data: Dict) -> bool:
        """Add a new task"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO tasks (id, phone, title, description, due_date, priority, tags, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_data['id'], task_data['phone'], task_data['title'],
                    task_data.get('description', ''), task_data.get('due_date'),
                    task_data.get('priority', 'medium'), 
                    json.dumps(task_data.get('tags', [])),
                    json.dumps(task_data.get('metadata', {}))
                ))
                
                conn.commit()
                conn.close()
                logger.debug(f"Added task: {task_data['id']}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to add task: {e}")
            return False
    
    def complete_task(self, task_id: str) -> bool:
        """Mark task as completed"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE tasks 
                    SET completed = 1, completed_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                ''', (task_id,))
                
                conn.commit()
                success = cursor.rowcount > 0
                conn.close()
                
                if success:
                    logger.info(f"Task completed: {task_id}")
                return success
                
        except Exception as e:
            logger.error(f"Failed to complete task: {e}")
            return False
    
    def get_tasks(self, phone: str, completed: Optional[bool] = None) -> List[Dict]:
        """Get tasks for a user"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                if completed is None:
                    cursor.execute('''
                        SELECT * FROM tasks WHERE phone = ? ORDER BY created_at DESC
                    ''', (phone,))
                else:
                    cursor.execute('''
                        SELECT * FROM tasks WHERE phone = ? AND completed = ? ORDER BY created_at DESC
                    ''', (phone, completed))
                
                columns = [description[0] for description in cursor.description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                conn.close()
                
                # Parse JSON fields
                for task in results:
                    task['tags'] = json.loads(task['tags']) if task['tags'] else []
                    task['metadata'] = json.loads(task['metadata']) if task['metadata'] else {}
                
                return results
                
        except Exception as e:
            logger.error(f"Failed to get tasks: {e}")
            return []
    
    def add_reminder(self, reminder_data: Dict) -> bool:
        """Add a new reminder"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO reminders (id, phone, message, remind_at, metadata)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    reminder_data['id'], reminder_data['phone'], reminder_data['message'],
                    reminder_data['remind_at'], json.dumps(reminder_data.get('metadata', {}))
                ))
                
                conn.commit()
                conn.close()
                logger.debug(f"Added reminder: {reminder_data['id']}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to add reminder: {e}")
            return False
    
    def get_due_reminders(self) -> List[Dict]:
        """Get reminders that are due"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT * FROM reminders 
                    WHERE remind_at <= CURRENT_TIMESTAMP AND notified = 0
                    ORDER BY remind_at ASC
                ''')
                
                columns = [description[0] for description in cursor.description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                conn.close()
                
                # Parse JSON fields
                for reminder in results:
                    reminder['metadata'] = json.loads(reminder['metadata']) if reminder['metadata'] else {}
                
                return results
                
        except Exception as e:
            logger.error(f"Failed to get due reminders: {e}")
            return []
    
    def mark_reminder_notified(self, reminder_id: str) -> bool:
        """Mark reminder as notified"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE reminders 
                    SET notified = 1 
                    WHERE id = ?
                ''', (reminder_id,))
                
                conn.commit()
                success = cursor.rowcount > 0
                conn.close()
                return success
                
        except Exception as e:
            logger.error(f"Failed to mark reminder notified: {e}")
            return False
    
    def save_user_preferences(self, phone: str, preferences: Dict) -> bool:
        """Save user preferences"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO user_preferences (phone, preferences, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                ''', (phone, json.dumps(preferences)))
                
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            logger.error(f"Failed to save user preferences: {e}")
            return False
    
    def get_user_preferences(self, phone: str) -> Dict:
        """Get user preferences"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT preferences FROM user_preferences WHERE phone = ?
                ''', (phone,))
                
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    return json.loads(result[0])
                return {}
                
        except Exception as e:
            logger.error(f"Failed to get user preferences: {e}")
            return {}
    
    def add_media(self, media_data: Dict) -> bool:
        """Add media metadata"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO media (id, phone, media_type, file_path, file_size, mime_type, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    media_data['id'], media_data['phone'], media_data['media_type'],
                    media_data.get('file_path'), media_data.get('file_size'),
                    media_data.get('mime_type'), json.dumps(media_data.get('metadata', {}))
                ))
                
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            logger.error(f"Failed to add media: {e}")
            return False
    
    def set_system_state(self, key: str, value: Any) -> bool:
        """Set system state value"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO system_state (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                ''', (key, json.dumps(value, cls=DateTimeEncoder)))
                
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            logger.error(f"Failed to set system state: {e}")
            return False
    
    def get_system_state(self, key: str, default: Any = None) -> Any:
        """Get system state value"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT value FROM system_state WHERE key = ?
                ''', (key,))
                
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    return json.loads(result[0])
                return default
                
        except Exception as e:
            logger.error(f"Failed to get system state: {e}")
            return default
    
    def _cleanup_old_conversations(self, phone: str, keep_count: int = 1000):
        """Keep only the most recent conversations"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM conversations 
                WHERE phone = ? AND id NOT IN (
                    SELECT id FROM conversations 
                    WHERE phone = ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                )
            ''', (phone, phone, keep_count))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to cleanup old conversations: {e}")
    
    def cleanup_old_data(self, days_old: int = 30):
        """Clean up old data to manage storage"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cutoff_date = (datetime.now() - timedelta(days=days_old)).isoformat()
                
                # Delete old completed tasks
                cursor.execute('''
                    DELETE FROM tasks 
                    WHERE completed = 1 AND completed_at < ?
                ''', (cutoff_date,))
                
                # Delete old notified reminders
                cursor.execute('''
                    DELETE FROM reminders 
                    WHERE notified = 1 AND remind_at < ?
                ''', (cutoff_date,))
                
                conn.commit()
                conn.close()
                logger.info(f"Cleaned up data older than {days_old} days")
                
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
    
    def get_database_stats(self) -> Dict:
        """Get database statistics"""
        try:
            with self.lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                stats = {}
                
                # Count records in each table
                tables = ['conversations', 'tasks', 'reminders', 'user_preferences', 'media', 'system_state']
                for table in tables:
                    cursor.execute(f'SELECT COUNT(*) FROM {table}')
                    stats[f'{table}_count'] = cursor.fetchone()[0]
                
                # Database file size
                stats['db_size_bytes'] = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                stats['db_size_mb'] = round(stats['db_size_bytes'] / (1024 * 1024), 2)
                
                conn.close()
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {}

# Global database instance
db_manager = DatabaseManager()

# Compatibility functions for existing code
def add_to_conversation_history(phone: str, role: str, message: str) -> bool:
    """Compatibility function for existing code"""
    return db_manager.add_conversation(phone, role, message)

def retrieve_conversation_history(phone: str, n_results: int = 5) -> List[str]:
    """Compatibility function for existing code"""
    return db_manager.get_conversation_history(phone, n_results)

def query_conversation_history(phone: str, query: str, limit: int = 5) -> List[str]:
    """Compatibility function for existing code"""
    return db_manager.search_conversations(phone, query, limit)