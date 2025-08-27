"""
Uber Integration for WhatsApp Assistant

Provides ride booking and food delivery functionality via Uber APIs
"""

import os
import json
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class UberService:
    """Uber and Uber Eats integration service"""
    
    def __init__(self):
        self.client_id = os.getenv("UBER_CLIENT_ID")
        self.client_secret = os.getenv("UBER_CLIENT_SECRET")
        self.access_token = os.getenv("UBER_ACCESS_TOKEN")
        self.base_url = "https://api.uber.com/v1.2"
        self.eats_url = "https://api.uber.com/v1/eats"
        
        # Default location (can be configured per user)
        self.default_lat = float(os.getenv("DEFAULT_LATITUDE", "40.7128"))
        self.default_lng = float(os.getenv("DEFAULT_LONGITUDE", "-74.0060"))
    
    def _make_request(self, endpoint: str, method: str = "GET", params: Dict = None, data: Dict = None) -> Dict:
        """Make authenticated request to Uber API"""
        if not self.access_token:
            return {"error": "Uber API not configured - access token required"}
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept-Language": "en_US"
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, params=params)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data)
            else:
                return {"error": f"Unsupported method: {method}"}
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Uber API request failed: {e}")
            return {"error": f"API request failed: {str(e)}"}
    
    def get_ride_estimates(self, start_lat: float = None, start_lng: float = None, 
                          end_lat: float = None, end_lng: float = None) -> str:
        """Get ride estimates for a trip"""
        try:
            # Use defaults if coordinates not provided
            start_lat = start_lat or self.default_lat
            start_lng = start_lng or self.default_lng
            
            if not end_lat or not end_lng:
                return "❌ Destination coordinates required for ride estimates"
            
            params = {
                "start_latitude": start_lat,
                "start_longitude": start_lng,
                "end_latitude": end_lat,
                "end_longitude": end_lng
            }
            
            result = self._make_request("/estimates/price", params=params)
            
            if "error" in result:
                return f"❌ Error getting ride estimates: {result['error']}"
            
            if "prices" not in result or not result["prices"]:
                return "🚗 No ride options available for this route"
            
            response = "🚗 Uber Ride Estimates:\n"
            response += "=" * 25 + "\n\n"
            
            for ride in result["prices"]:
                name = ride.get("display_name", "Unknown")
                estimate = ride.get("estimate", "N/A")
                duration = ride.get("duration", 0)
                distance = ride.get("distance", 0)
                
                response += f"🚙 {name}\n"
                response += f"   💰 {estimate}\n"
                response += f"   ⏱️ {duration // 60} minutes\n"
                response += f"   📏 {distance:.1f} miles\n\n"
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error getting ride estimates: {e}")
            return f"❌ Error getting ride estimates: {str(e)}"
    
    def book_ride(self, product_id: str, start_lat: float = None, start_lng: float = None,
                  end_lat: float = None, end_lng: float = None, fare_id: str = None) -> str:
        """Book an Uber ride"""
        try:
            if not all([end_lat, end_lng]):
                return "❌ Destination coordinates required to book ride"
            
            # Use defaults if start coordinates not provided
            start_lat = start_lat or self.default_lat
            start_lng = start_lng or self.default_lng
            
            data = {
                "fare_id": fare_id,
                "product_id": product_id,
                "start_latitude": start_lat,
                "start_longitude": start_lng,
                "end_latitude": end_lat,
                "end_longitude": end_lng
            }
            
            result = self._make_request("/requests", method="POST", data=data)
            
            if "error" in result:
                return f"❌ Error booking ride: {result['error']}"
            
            request_id = result.get("request_id")
            status = result.get("status", "processing")
            eta = result.get("eta", "unknown")
            
            response = "✅ Uber ride booked successfully!\n\n"
            response += f"🆔 Request ID: {request_id}\n"
            response += f"📍 Status: {status}\n"
            response += f"⏰ ETA: {eta} minutes\n"
            
            return response
            
        except Exception as e:
            logger.error(f"Error booking ride: {e}")
            return f"❌ Error booking ride: {str(e)}"
    
    def get_ride_status(self, request_id: str) -> str:
        """Get status of an existing ride request"""
        try:
            result = self._make_request(f"/requests/{request_id}")
            
            if "error" in result:
                return f"❌ Error getting ride status: {result['error']}"
            
            status = result.get("status", "unknown")
            eta = result.get("eta")
            driver_name = result.get("driver", {}).get("name", "N/A")
            vehicle = result.get("vehicle", {})
            
            response = f"🚗 Ride Status: {status.upper()}\n\n"
            
            if driver_name != "N/A":
                response += f"👤 Driver: {driver_name}\n"
            
            if vehicle:
                make = vehicle.get("make", "")
                model = vehicle.get("model", "")
                license_plate = vehicle.get("license_plate", "")
                if make and model:
                    response += f"🚙 Vehicle: {make} {model}\n"
                if license_plate:
                    response += f"🔢 License: {license_plate}\n"
            
            if eta:
                response += f"⏰ ETA: {eta} minutes\n"
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting ride status: {e}")
            return f"❌ Error getting ride status: {str(e)}"
    
    def search_restaurants(self, query: str = "", lat: float = None, lng: float = None) -> str:
        """Search for restaurants on Uber Eats"""
        try:
            # Use defaults if coordinates not provided
            lat = lat or self.default_lat
            lng = lng or self.default_lng
            
            params = {
                "latitude": lat,
                "longitude": lng
            }
            
            if query:
                params["query"] = query
            
            # Note: This is a simplified implementation
            # Real Uber Eats API may have different endpoints
            endpoint = "/eats/stores"
            result = self._make_request(endpoint, params=params)
            
            if "error" in result:
                # Fallback to mock data for demonstration
                return f"🍔 Uber Eats Search Results for '{query}':\n\n" + \
                       "📍 Demo Restaurant 1\n" + \
                       "   ⭐ 4.5 stars • $$ • 25-35 min\n" + \
                       "   🍕 Pizza, Italian\n\n" + \
                       "📍 Demo Restaurant 2\n" + \
                       "   ⭐ 4.2 stars • $ • 20-30 min\n" + \
                       "   🍔 Burgers, American\n\n" + \
                       "ℹ️ Real Uber Eats integration requires API access"
            
            return "🍔 Uber Eats restaurants found (feature in development)"
            
        except Exception as e:
            logger.error(f"Error searching restaurants: {e}")
            return f"❌ Error searching restaurants: {str(e)}"
    
    def get_service_status(self) -> str:
        """Get Uber service configuration status"""
        status = "🚗 Uber Service Status\n"
        status += "=" * 20 + "\n\n"
        
        status += f"🔑 Client ID: {'✅ Set' if self.client_id else '❌ Not set'}\n"
        status += f"🔐 Client Secret: {'✅ Set' if self.client_secret else '❌ Not set'}\n"
        status += f"🎫 Access Token: {'✅ Set' if self.access_token else '❌ Not set'}\n"
        status += f"📍 Default Location: {self.default_lat:.4f}, {self.default_lng:.4f}\n\n"
        
        if not all([self.client_id, self.client_secret, self.access_token]):
            status += "⚠️ Uber API not fully configured\n"
            status += "Set UBER_CLIENT_ID, UBER_CLIENT_SECRET, and UBER_ACCESS_TOKEN environment variables"
        else:
            status += "✅ Uber API ready for use"
        
        return status

# Global Uber service instance
uber_service = UberService()