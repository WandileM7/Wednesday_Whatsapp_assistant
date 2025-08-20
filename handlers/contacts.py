"""
Contact Management for WhatsApp Assistant

Provides contact management functionality with Google Contacts integration
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from handlers.google_auth import load_credentials

logger = logging.getLogger(__name__)

class ContactManager:
    """Contact management service"""
    
    def __init__(self):
        self.local_contacts_file = Path("task_data") / "contacts.json"
        self.local_contacts_file.parent.mkdir(exist_ok=True)
        self.local_contacts = self._load_local_contacts()
    
    def _load_local_contacts(self) -> Dict[str, Dict[str, Any]]:
        """Load local contacts from file"""
        try:
            if self.local_contacts_file.exists():
                with open(self.local_contacts_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading local contacts: {e}")
            return {}
    
    def _save_local_contacts(self):
        """Save local contacts to file"""
        try:
            with open(self.local_contacts_file, 'w') as f:
                json.dump(self.local_contacts, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving local contacts: {e}")
    
    def add_local_contact(self, name: str, phone: Optional[str] = None, 
                         email: Optional[str] = None, notes: Optional[str] = None) -> str:
        """Add a contact to local storage"""
        import uuid
        
        contact_id = str(uuid.uuid4())[:8]
        
        contact = {
            'id': contact_id,
            'name': name,
            'phone': phone,
            'email': email,
            'notes': notes,
            'created_at': datetime.now().isoformat()
        }
        
        self.local_contacts[contact_id] = contact
        self._save_local_contacts()
        
        return f"✅ Contact added: {name} (ID: {contact_id})"
    
    def search_local_contacts(self, query: str) -> str:
        """Search local contacts"""
        if not self.local_contacts:
            return "📇 No local contacts found. Add one with the add_contact function."
        
        query_lower = query.lower()
        matches = []
        
        for contact in self.local_contacts.values():
            if (query_lower in contact['name'].lower() or
                (contact.get('phone') and query_lower in contact.get('phone', '')) or
                (contact.get('email') and query_lower in contact.get('email', '').lower()) or
                (contact.get('notes') and query_lower in contact.get('notes', '').lower())):
                matches.append(contact)
        
        if not matches:
            return f"📇 No contacts found matching '{query}'"
        
        result = f"📇 Found {len(matches)} contact(s) matching '{query}':\n\n"
        
        for contact in matches:
            result += f"👤 {contact['name']} (#{contact['id']})\n"
            
            if contact.get('phone'):
                result += f"   📞 {contact['phone']}\n"
            
            if contact.get('email'):
                result += f"   📧 {contact['email']}\n"
            
            if contact.get('notes'):
                result += f"   📝 {contact['notes']}\n"
            
            result += "\n"
        
        return result.strip()
    
    def list_local_contacts(self) -> str:
        """List all local contacts"""
        if not self.local_contacts:
            return "📇 No local contacts found. Add one with the add_contact function."
        
        result = f"📇 Your Contacts ({len(self.local_contacts)}):\n"
        result += "=" * 20 + "\n\n"
        
        # Sort contacts by name
        sorted_contacts = sorted(self.local_contacts.values(), key=lambda c: c['name'].lower())
        
        for contact in sorted_contacts:
            result += f"👤 {contact['name']} (#{contact['id']})\n"
            
            if contact.get('phone'):
                result += f"   📞 {contact['phone']}\n"
            
            if contact.get('email'):
                result += f"   📧 {contact['email']}\n"
            
            if contact.get('notes'):
                result += f"   📝 {contact['notes']}\n"
            
            result += "\n"
        
        return result.strip()
    
    def get_google_contacts(self, max_results: int = 20) -> str:
        """Get contacts from Google Contacts API"""
        try:
            creds = load_credentials()
            if not creds:
                return "❌ Google authentication required to access contacts"
            
            from googleapiclient.discovery import build
            
            service = build('people', 'v1', credentials=creds)
            
            # Call the People API
            results = service.people().connections().list(
                resourceName='people/me',
                pageSize=max_results,
                personFields='names,phoneNumbers,emailAddresses'
            ).execute()
            
            connections = results.get('connections', [])
            
            if not connections:
                return "📇 No Google contacts found"
            
            result = f"📇 Google Contacts ({len(connections)}):\n"
            result += "=" * 25 + "\n\n"
            
            for person in connections:
                names = person.get('names', [])
                phones = person.get('phoneNumbers', [])
                emails = person.get('emailAddresses', [])
                
                if names:
                    name = names[0].get('displayName', 'Unknown')
                    result += f"👤 {name}\n"
                    
                    for phone in phones:
                        result += f"   📞 {phone.get('value', '')}\n"
                    
                    for email in emails:
                        result += f"   📧 {email.get('value', '')}\n"
                    
                    result += "\n"
            
            return result.strip()
            
        except Exception as e:
            logger.error(f"Error getting Google contacts: {e}")
            return f"❌ Error accessing Google contacts: {str(e)}"
    
    def search_all_contacts(self, query: str) -> str:
        """Search both local and Google contacts"""
        results = []
        
        # Search local contacts
        local_result = self.search_local_contacts(query)
        if not local_result.startswith("📇 No contacts found"):
            results.append("🏠 Local Contacts:\n" + local_result)
        
        # Search Google contacts (simplified search)
        try:
            google_contacts = self.get_google_contacts(50)
            if not google_contacts.startswith("❌") and not google_contacts.startswith("📇 No Google"):
                query_lower = query.lower()
                matching_lines = []
                current_contact = []
                
                for line in google_contacts.split('\n'):
                    if line.startswith('👤'):
                        if current_contact and any(query_lower in l.lower() for l in current_contact):
                            matching_lines.extend(current_contact)
                            matching_lines.append('')
                        current_contact = [line]
                    else:
                        current_contact.append(line)
                
                # Check last contact
                if current_contact and any(query_lower in l.lower() for l in current_contact):
                    matching_lines.extend(current_contact)
                
                if matching_lines:
                    results.append("☁️ Google Contacts:\n" + '\n'.join(matching_lines))
        
        except Exception as e:
            logger.error(f"Error searching Google contacts: {e}")
        
        if not results:
            return f"📇 No contacts found matching '{query}'"
        
        return "\n\n" + "=" * 40 + "\n\n".join(results)
    
    def get_contact_summary(self) -> str:
        """Get a summary of contacts"""
        local_count = len(self.local_contacts)
        
        summary = "📇 Contact Summary\n"
        summary += "=" * 17 + "\n\n"
        summary += f"🏠 Local contacts: {local_count}\n"
        
        try:
            google_contacts = self.get_google_contacts(100)
            if not google_contacts.startswith("❌") and not google_contacts.startswith("📇 No Google"):
                google_count = google_contacts.count('👤')
                summary += f"☁️ Google contacts: {google_count}\n"
            else:
                summary += "☁️ Google contacts: Not available\n"
        except:
            summary += "☁️ Google contacts: Not available\n"
        
        return summary


# Global contact manager instance
contact_manager = ContactManager()

# Fix import
from datetime import datetime