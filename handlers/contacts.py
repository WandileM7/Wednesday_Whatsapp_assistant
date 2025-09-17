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
    
    def search_google_contacts_by_query(self, query: str) -> list:
        """Search Google contacts and return matching contacts as list"""
        try:
            creds = load_credentials()
            if not creds:
                logger.warning("Google authentication not available for contacts search")
                return []
            
            from googleapiclient.discovery import build
            
            service = build('people', 'v1', credentials=creds)
            
            # Call the People API with more results for better searching
            results = service.people().connections().list(
                resourceName='people/me',
                pageSize=100,  # Get more contacts for better search
                personFields='names,phoneNumbers,emailAddresses'
            ).execute()
            
            connections = results.get('connections', [])
            
            if not connections:
                return []
            
            query_lower = query.lower()
            matching_contacts = []
            
            for person in connections:
                names = person.get('names', [])
                phones = person.get('phoneNumbers', [])
                emails = person.get('emailAddresses', [])
                
                # Check if query matches name, phone, or email
                match_found = False
                
                for name in names:
                    if query_lower in name.get('displayName', '').lower():
                        match_found = True
                        break
                
                if not match_found:
                    for phone in phones:
                        if query_lower in phone.get('value', '').lower():
                            match_found = True
                            break
                
                if not match_found:
                    for email in emails:
                        if query_lower in email.get('value', '').lower():
                            match_found = True
                            break
                
                if match_found:
                    matching_contacts.append({
                        'name': names[0].get('displayName', 'Unknown') if names else 'Unknown',
                        'phones': [phone.get('value', '') for phone in phones],
                        'emails': [email.get('value', '') for email in emails],
                        'source': 'google'
                    })
            
            return matching_contacts
            
        except Exception as e:
            logger.error(f"Error searching Google contacts: {e}")
            return []

    def search_all_contacts(self, query: str) -> str:
        """Search both Google and local contacts, prioritizing Google contacts"""
        google_matches = []
        local_matches = []
        
        # Search Google contacts first (prioritized)
        try:
            google_contacts = self.search_google_contacts_by_query(query)
            if google_contacts:
                google_result = f"☁️ Google Contacts ({len(google_contacts)} found):\n"
                google_result += "=" * 35 + "\n\n"
                
                for contact in google_contacts:
                    google_result += f"👤 {contact['name']}\n"
                    
                    for phone in contact['phones']:
                        google_result += f"   📞 {phone}\n"
                    
                    for email in contact['emails']:
                        google_result += f"   📧 {email}\n"
                    
                    google_result += "\n"
                
                google_matches.append(google_result.strip())
        
        except Exception as e:
            logger.error(f"Error searching Google contacts: {e}")
        
        # Search local contacts
        local_result = self.search_local_contacts(query)
        if not local_result.startswith("📇 No contacts found"):
            local_matches.append("🏠 Local Contacts:\n" + local_result)
        
        # Combine results with Google contacts first
        all_results = google_matches + local_matches
        
        if not all_results:
            return f"📇 No contacts found matching '{query}'"
        
        return "\n\n" + "=" * 40 + "\n\n".join(all_results)
    
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
    
    def send_whatsapp_message(self, contact_query: str, message: str) -> str:
        """Send WhatsApp message to a contact, prioritizing Google contacts"""
        try:
            # Search Google contacts first
            google_contacts = self.search_google_contacts_by_query(contact_query)
            matching_contacts = []
            
            # Process Google contacts first (prioritized)
            for contact in google_contacts:
                if contact['phones']:  # Only include contacts with phone numbers
                    matching_contacts.append({
                        'name': contact['name'],
                        'phone': contact['phones'][0],  # Use first phone number
                        'source': 'google',
                        'email': contact['emails'][0] if contact['emails'] else None
                    })
            
            # If no Google contacts found, search local contacts
            if not matching_contacts:
                query_lower = contact_query.lower()
                for contact in self.local_contacts.values():
                    if (query_lower in contact['name'].lower() or
                        (contact.get('phone') and query_lower in contact.get('phone', ''))):
                        matching_contacts.append({
                            'name': contact['name'],
                            'phone': contact.get('phone'),
                            'source': 'local',
                            'email': contact.get('email')
                        })
            
            if not matching_contacts:
                return f"❌ No contact found matching '{contact_query}'"
            
            if len(matching_contacts) > 1:
                result = f"🤔 Multiple contacts found for '{contact_query}':\n\n"
                for i, contact in enumerate(matching_contacts[:3], 1):
                    source_icon = "☁️" if contact['source'] == 'google' else "🏠"
                    result += f"{i}. {source_icon} {contact['name']}"
                    if contact.get('phone'):
                        result += f" - {contact['phone']}"
                    result += "\n"
                result += "\nPlease be more specific with the contact name or phone number."
                return result
            
            contact = matching_contacts[0]
            phone_number = contact.get('phone')
            
            if not phone_number:
                return f"❌ No phone number found for {contact['name']}"
            
            # Format phone number for WhatsApp (remove formatting, add country code if needed)
            formatted_phone = phone_number.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
            if not formatted_phone.startswith('+'):
                # Assume US number if no country code
                if len(formatted_phone) == 10:
                    formatted_phone = '+1' + formatted_phone
                elif len(formatted_phone) == 11 and formatted_phone.startswith('1'):
                    formatted_phone = '+' + formatted_phone
                else:
                    formatted_phone = '+' + formatted_phone
            
            # WhatsApp format: phone@c.us
            whatsapp_id = formatted_phone.replace('+', '') + '@c.us'
            
            # Actually send the WhatsApp message
            try:
                # Import the message sending function from main
                import requests
                import os
                
                waha_url = os.getenv("WAHA_URL", "http://localhost:3000/api/sendText")
                
                # Prepare the message payload
                payload = {
                    "chatId": whatsapp_id,
                    "text": message,
                    "session": os.getenv("WAHA_SESSION", "default")
                }
                
                # Send the message
                response_request = requests.post(
                    waha_url,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=10
                )
                
                if response_request.status_code == 200:
                    # Message sent successfully
                    source_icon = "☁️" if contact['source'] == 'google' else "🏠"
                    response = f"✅ **WhatsApp Message Sent!** {source_icon}\n\n"
                    response += f"👤 To: {contact['name']}\n"
                    response += f"📞 Phone: {phone_number}\n"
                    response += f"💬 Message: \"{message}\"\n"
                    response += f"🕒 Sent: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                    response += "📱 Message delivered via WhatsApp!"
                    
                    # Log the successful message sending
                    logger.info(f"WhatsApp message sent to {contact['name']} ({whatsapp_id})")
                    
                    return response
                else:
                    # Failed to send
                    error_msg = f"HTTP {response_request.status_code}"
                    source_icon = "☁️" if contact['source'] == 'google' else "🏠"
                    response = f"❌ **Failed to send WhatsApp message** {source_icon}\n\n"
                    response += f"👤 To: {contact['name']}\n"
                    response += f"📞 Phone: {phone_number}\n"
                    response += f"💬 Message: \"{message}\"\n"
                    response += f"⚠️ Error: {error_msg}\n\n"
                    response += "🔧 Please check WhatsApp service connection."
                    
                    logger.error(f"Failed to send WhatsApp message: {error_msg}")
                    return response
                    
            except requests.exceptions.ConnectionError:
                # WhatsApp service not available
                source_icon = "☁️" if contact['source'] == 'google' else "🏠"
                response = f"⚠️ **WhatsApp Service Unavailable** {source_icon}\n\n"
                response += f"👤 Contact: {contact['name']}\n"
                response += f"📞 Phone: {phone_number}\n"
                response += f"🆔 WhatsApp ID: {whatsapp_id}\n"
                response += f"📍 Source: {'Google Contacts' if contact['source'] == 'google' else 'Local Contacts'}\n"
                response += f"💬 Message: \"{message}\"\n\n"
                response += "🔧 WhatsApp service is not running. Message prepared but not sent.\n"
                response += "💡 Start the WhatsApp service to enable messaging."
                
                logger.warning("WhatsApp service not available for message sending")
                return response
                
            except Exception as e:
                # Other errors
                logger.error(f"Error sending WhatsApp message: {e}")
                source_icon = "☁️" if contact['source'] == 'google' else "🏠"
                response = f"❌ **Error sending message** {source_icon}\n\n"
                response += f"👤 To: {contact['name']}\n"
                response += f"⚠️ Error: {str(e)}\n\n"
                response += "🔧 Please try again or check service status."
                
                return response
            response += "💡 Integration with WhatsApp service pending"
            
            return response
            
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            return f"❌ Error sending WhatsApp message: {str(e)}"
    
    def get_contact_for_whatsapp(self, contact_query: str) -> str:
        """Get contact details formatted for WhatsApp, prioritizing Google contacts"""
        try:
            # Search Google contacts first
            google_contacts = self.search_google_contacts_by_query(contact_query)
            matching_contacts = []
            
            # Process Google contacts first (prioritized)
            for contact in google_contacts:
                if contact['phones']:  # Only include contacts with phone numbers
                    matching_contacts.append({
                        'name': contact['name'],
                        'phone': contact['phones'][0],  # Use first phone number
                        'source': 'google',
                        'email': contact['emails'][0] if contact['emails'] else None
                    })
            
            # If no Google contacts found, search local contacts
            if not matching_contacts:
                query_lower = contact_query.lower()
                for contact in self.local_contacts.values():
                    if (query_lower in contact['name'].lower() or
                        (contact.get('phone') and query_lower in contact.get('phone', ''))):
                        matching_contacts.append({
                            'name': contact['name'],
                            'phone': contact.get('phone'),
                            'source': 'local',
                            'email': contact.get('email'),
                            'notes': contact.get('notes')
                        })
            
            if not matching_contacts:
                return f"❌ No contact found matching '{contact_query}'"
            
            if len(matching_contacts) > 1:
                result = f"🤔 Multiple contacts found for '{contact_query}':\n\n"
                for i, contact in enumerate(matching_contacts[:5], 1):
                    source_icon = "☁️" if contact['source'] == 'google' else "🏠"
                    phone = contact.get('phone', 'No phone')
                    result += f"{i}. {source_icon} {contact['name']} - {phone}\n"
                result += "\nPlease be more specific."
                return result
            
            contact = matching_contacts[0]
            phone_number = contact.get('phone')
            
            if not phone_number:
                return f"❌ No phone number found for {contact['name']}"
            
            # Format for WhatsApp
            formatted_phone = phone_number.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
            if not formatted_phone.startswith('+'):
                if len(formatted_phone) == 10:
                    formatted_phone = '+1' + formatted_phone
                elif len(formatted_phone) == 11 and formatted_phone.startswith('1'):
                    formatted_phone = '+' + formatted_phone
                else:
                    formatted_phone = '+' + formatted_phone
            
            whatsapp_id = formatted_phone.replace('+', '') + '@c.us'
            
            source_icon = "☁️" if contact['source'] == 'google' else "🏠"
            response = f"📱 WhatsApp Contact Details {source_icon}\n\n"
            response += f"👤 Name: {contact['name']}\n"
            response += f"📞 Phone: {phone_number}\n"
            response += f"🆔 WhatsApp ID: {whatsapp_id}\n"
            response += f"📍 Source: {'Google Contacts' if contact['source'] == 'google' else 'Local Contacts'}\n"
            
            if contact.get('email'):
                response += f"📧 Email: {contact['email']}\n"
            
            if contact.get('notes'):
                response += f"📝 Notes: {contact['notes']}\n"
            
            response += f"\n💡 Use: send_whatsapp_message \"{contact['name']}\" \"your message\""
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting contact for WhatsApp: {e}")
            return f"❌ Error getting contact: {str(e)}"


# Global contact manager instance
contact_manager = ContactManager()

# Fix import
from datetime import datetime