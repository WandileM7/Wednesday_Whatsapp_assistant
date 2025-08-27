"""
Accommodation Booking Integration for WhatsApp Assistant

Provides accommodation search and booking functionality
"""

import os
import json
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class AccommodationService:
    """Accommodation booking service (Airbnb, Booking.com style)"""
    
    def __init__(self):
        # Note: Real APIs would require actual API keys
        self.booking_api_key = os.getenv("BOOKING_COM_API_KEY")
        self.airbnb_api_key = os.getenv("AIRBNB_API_KEY")
        
        # Mock data for demonstration since public APIs are limited
        self.mock_properties = [
            {
                "id": "prop_001",
                "name": "Cozy Downtown Apartment",
                "type": "Entire apartment",
                "location": "New York, NY",
                "price_per_night": 150,
                "rating": 4.8,
                "reviews": 127,
                "amenities": ["WiFi", "Kitchen", "Air conditioning", "Washing machine"],
                "max_guests": 4,
                "bedrooms": 2,
                "bathrooms": 1
            },
            {
                "id": "prop_002", 
                "name": "Luxury Hotel Suite",
                "type": "Hotel room",
                "location": "Manhattan, NY",
                "price_per_night": 300,
                "rating": 4.9,
                "reviews": 89,
                "amenities": ["WiFi", "Room service", "Gym", "Pool", "Concierge"],
                "max_guests": 2,
                "bedrooms": 1,
                "bathrooms": 1
            },
            {
                "id": "prop_003",
                "name": "Beach House Retreat",
                "type": "Entire house",
                "location": "Malibu, CA",
                "price_per_night": 450,
                "rating": 4.7,
                "reviews": 203,
                "amenities": ["WiFi", "Kitchen", "Beach access", "Pool", "BBQ"],
                "max_guests": 8,
                "bedrooms": 4,
                "bathrooms": 3
            }
        ]
    
    def search_accommodations(self, location: str, check_in: str = None, 
                            check_out: str = None, guests: int = 2,
                            max_price: float = None) -> str:
        """Search for accommodations"""
        try:
            # Parse dates
            if check_in:
                try:
                    check_in_date = datetime.strptime(check_in, "%Y-%m-%d")
                except ValueError:
                    return "❌ Invalid check-in date format. Use YYYY-MM-DD"
            else:
                check_in_date = datetime.now() + timedelta(days=1)
                check_in = check_in_date.strftime("%Y-%m-%d")
            
            if check_out:
                try:
                    check_out_date = datetime.strptime(check_out, "%Y-%m-%d")
                except ValueError:
                    return "❌ Invalid check-out date format. Use YYYY-MM-DD"
            else:
                check_out_date = check_in_date + timedelta(days=2)
                check_out = check_out_date.strftime("%Y-%m-%d")
            
            if check_out_date <= check_in_date:
                return "❌ Check-out date must be after check-in date"
            
            nights = (check_out_date - check_in_date).days
            
            # Filter properties based on search criteria
            filtered_properties = []
            for prop in self.mock_properties:
                # Location filter (simple contains check)
                if location.lower() in prop["location"].lower():
                    # Guest capacity filter
                    if prop["max_guests"] >= guests:
                        # Price filter
                        if max_price is None or prop["price_per_night"] <= max_price:
                            filtered_properties.append(prop)
            
            if not filtered_properties:
                return f"🏨 No accommodations found in {location} for {guests} guests"
            
            response = f"🏨 Accommodation Search Results\n"
            response += f"📍 Location: {location}\n"
            response += f"📅 Check-in: {check_in}\n"
            response += f"📅 Check-out: {check_out}\n"
            response += f"👥 Guests: {guests}\n"
            response += f"🌙 Nights: {nights}\n\n"
            response += "=" * 35 + "\n\n"
            
            for i, prop in enumerate(filtered_properties[:5], 1):  # Limit to 5 results
                total_cost = prop["price_per_night"] * nights
                
                response += f"{i}. 🏠 {prop['name']}\n"
                response += f"   📍 {prop['location']}\n"
                response += f"   🏷️ {prop['type']}\n"
                response += f"   ⭐ {prop['rating']}/5 ({prop['reviews']} reviews)\n"
                response += f"   💰 ${prop['price_per_night']}/night (${total_cost} total)\n"
                response += f"   👥 Up to {prop['max_guests']} guests\n"
                response += f"   🛏️ {prop['bedrooms']} bedrooms, {prop['bathrooms']} bathrooms\n"
                response += f"   ✨ {', '.join(prop['amenities'][:3])}...\n"
                response += f"   🆔 Property ID: {prop['id']}\n\n"
            
            response += "💡 To book, use: book_accommodation <property_id>\n"
            response += "ℹ️ This is a demonstration - real booking integration pending"
            
            return response
            
        except Exception as e:
            logger.error(f"Error searching accommodations: {e}")
            return f"❌ Error searching accommodations: {str(e)}"
    
    def get_property_details(self, property_id: str) -> str:
        """Get detailed information about a specific property"""
        try:
            # Find property in mock data
            property_data = None
            for prop in self.mock_properties:
                if prop["id"] == property_id:
                    property_data = prop
                    break
            
            if not property_data:
                return f"❌ Property {property_id} not found"
            
            response = f"🏠 Property Details\n"
            response += "=" * 20 + "\n\n"
            response += f"📝 Name: {property_data['name']}\n"
            response += f"🏷️ Type: {property_data['type']}\n"
            response += f"📍 Location: {property_data['location']}\n"
            response += f"⭐ Rating: {property_data['rating']}/5\n"
            response += f"💬 Reviews: {property_data['reviews']}\n"
            response += f"💰 Price: ${property_data['price_per_night']}/night\n"
            response += f"👥 Max Guests: {property_data['max_guests']}\n"
            response += f"🛏️ Bedrooms: {property_data['bedrooms']}\n"
            response += f"🚿 Bathrooms: {property_data['bathrooms']}\n\n"
            
            response += "✨ Amenities:\n"
            for amenity in property_data['amenities']:
                response += f"   • {amenity}\n"
            
            response += f"\n💡 To book this property, use: book_accommodation {property_id}"
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting property details: {e}")
            return f"❌ Error getting property details: {str(e)}"
    
    def book_accommodation(self, property_id: str, check_in: str, check_out: str,
                          guests: int = 2, guest_name: str = "Guest") -> str:
        """Book an accommodation (simulation)"""
        try:
            # Find property
            property_data = None
            for prop in self.mock_properties:
                if prop["id"] == property_id:
                    property_data = prop
                    break
            
            if not property_data:
                return f"❌ Property {property_id} not found"
            
            # Validate dates
            try:
                check_in_date = datetime.strptime(check_in, "%Y-%m-%d")
                check_out_date = datetime.strptime(check_out, "%Y-%m-%d")
            except ValueError:
                return "❌ Invalid date format. Use YYYY-MM-DD"
            
            if check_out_date <= check_in_date:
                return "❌ Check-out date must be after check-in date"
            
            if guests > property_data["max_guests"]:
                return f"❌ Property can accommodate max {property_data['max_guests']} guests"
            
            nights = (check_out_date - check_in_date).days
            total_cost = property_data["price_per_night"] * nights
            
            # Generate booking confirmation
            booking_id = f"BK{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            response = "✅ Accommodation Booked Successfully!\n\n"
            response += f"🆔 Booking ID: {booking_id}\n"
            response += f"🏠 Property: {property_data['name']}\n"
            response += f"📍 Location: {property_data['location']}\n"
            response += f"👤 Guest: {guest_name}\n"
            response += f"👥 Guests: {guests}\n"
            response += f"📅 Check-in: {check_in}\n"
            response += f"📅 Check-out: {check_out}\n"
            response += f"🌙 Nights: {nights}\n"
            response += f"💰 Total Cost: ${total_cost}\n\n"
            response += "📧 Confirmation email sent\n"
            response += "🔔 You'll receive check-in instructions 24 hours before arrival\n\n"
            response += "⚠️ This is a simulation - no actual booking was made"
            
            return response
            
        except Exception as e:
            logger.error(f"Error booking accommodation: {e}")
            return f"❌ Error booking accommodation: {str(e)}"
    
    def get_bookings(self, guest_name: str = "Guest") -> str:
        """Get list of bookings (simulation)"""
        # This would typically query a database
        # For demo, return a sample booking
        
        response = f"📋 Your Bookings ({guest_name})\n"
        response += "=" * 25 + "\n\n"
        response += "🆔 BK20250101120000\n"
        response += "🏠 Cozy Downtown Apartment\n"
        response += "📍 New York, NY\n"
        response += "📅 Jan 15-17, 2025 (2 nights)\n"
        response += "💰 $300 total\n"
        response += "✅ Confirmed\n\n"
        response += "ℹ️ This is sample data - real booking history requires integration"
        
        return response
    
    def cancel_booking(self, booking_id: str) -> str:
        """Cancel a booking (simulation)"""
        response = f"✅ Booking {booking_id} cancelled successfully\n\n"
        response += "💰 Refund will be processed within 3-5 business days\n"
        response += "📧 Cancellation confirmation sent\n\n"
        response += "⚠️ This is a simulation - no actual cancellation was processed"
        
        return response
    
    def get_service_status(self) -> str:
        """Get accommodation service status"""
        status = "🏨 Accommodation Service Status\n"
        status += "=" * 30 + "\n\n"
        
        status += f"🔑 Booking.com API: {'✅ Set' if self.booking_api_key else '❌ Not set'}\n"
        status += f"🔑 Airbnb API: {'✅ Set' if self.airbnb_api_key else '❌ Not set'}\n"
        status += f"📊 Mock Properties: {len(self.mock_properties)} available\n\n"
        
        if not any([self.booking_api_key, self.airbnb_api_key]):
            status += "⚠️ Real accommodation APIs not configured\n"
            status += "Using mock data for demonstration\n"
            status += "Set BOOKING_COM_API_KEY and AIRBNB_API_KEY for real integration"
        else:
            status += "✅ Accommodation services ready"
        
        return status

# Global accommodation service instance
accommodation_service = AccommodationService()