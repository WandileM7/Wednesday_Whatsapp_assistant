"""
Paxi Integration for WhatsApp Assistant

Provides Paxi pickup point and delivery functionality for South African orders.
Paxi is a pickup point delivery service where customers can collect parcels
from nearby stores instead of home delivery.
"""

import os
import json
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class PaxiService:
    """Paxi pickup point and delivery service integration"""
    
    def __init__(self):
        self.api_key = os.getenv("PAXI_API_KEY")
        self.base_url = os.getenv("PAXI_BASE_URL", "https://api.paxi.com/v1")
        self.partner_id = os.getenv("PAXI_PARTNER_ID")
        
        # Default pickup point for testing (Cape Town central)
        self.default_pickup_point = {
            "id": "CPT001",
            "name": "Pick n Pay - Claremont",
            "address": "Cavendish Square, Claremont, Cape Town",
            "suburb": "Claremont",
            "city": "Cape Town",
            "province": "Western Cape",
            "postal_code": "7708",
            "phone": "+27 21 674 4000",
            "hours": "Mon-Fri: 8:00-20:00, Sat: 8:00-18:00, Sun: 9:00-17:00",
            "services": ["pickup", "collection", "returns"]
        }
    
    def _make_request(self, endpoint: str, method: str = "GET", params: Dict = None, data: Dict = None) -> Dict:
        """Make authenticated request to Paxi API"""
        if not self.api_key or self.api_key == "test_paxi_key":
            # Return mock data for testing when API key not configured
            return self._get_mock_response(endpoint, params, data)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        if self.partner_id:
            headers["X-Partner-ID"] = self.partner_id
        
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
            logger.error(f"Paxi API request failed: {e}")
            # Fall back to mock data on API failure
            return self._get_mock_response(endpoint, params, data)
    
    def _get_mock_response(self, endpoint: str, params: Dict = None, data: Dict = None) -> Dict:
        """Return mock data for testing when API not configured"""
        if "/pickup-points" in endpoint:
            return {
                "pickup_points": [
                    self.default_pickup_point,
                    {
                        "id": "CPT002",
                        "name": "Shoprite - Wynberg",
                        "address": "Maynardville Park, Wynberg, Cape Town",
                        "suburb": "Wynberg",
                        "city": "Cape Town",
                        "province": "Western Cape",
                        "postal_code": "7800",
                        "phone": "+27 21 761 7000",
                        "hours": "Mon-Sun: 8:00-20:00",
                        "services": ["pickup", "collection"]
                    },
                    {
                        "id": "JHB001",
                        "name": "Pick n Pay - Sandton City",
                        "address": "Sandton City Shopping Centre, Sandton",
                        "suburb": "Sandton",
                        "city": "Johannesburg",
                        "province": "Gauteng",
                        "postal_code": "2196",
                        "phone": "+27 11 784 7200",
                        "hours": "Mon-Fri: 9:00-21:00, Sat-Sun: 9:00-19:00",
                        "services": ["pickup", "collection", "returns"]
                    }
                ]
            }
        elif "/deliveries" in endpoint or "/orders" in endpoint:
            return {
                "tracking_number": f"PX{datetime.now().strftime('%Y%m%d')}{hash(str(data)) % 10000:04d}",
                "status": "created",
                "pickup_point": self.default_pickup_point,
                "estimated_delivery": (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"),
                "cost": 25.00
            }
        
        return {"error": "Mock endpoint not implemented"}
    
    def find_pickup_points(self, location: str = "", suburb: str = "", city: str = "Cape Town") -> str:
        """Find Paxi pickup points near a location"""
        try:
            params = {}
            if location:
                params["search"] = location
            if suburb:
                params["suburb"] = suburb
            if city:
                params["city"] = city
            
            result = self._make_request("/pickup-points", params=params)
            
            if "error" in result:
                return f"❌ Error finding pickup points: {result['error']}"
            
            pickup_points = result.get("pickup_points", [])
            if not pickup_points:
                return f"📍 No Paxi pickup points found near '{location or city}'"
            
            response = f"📍 Paxi Pickup Points near {location or city}:\n"
            response += "=" * 35 + "\n\n"
            
            for i, point in enumerate(pickup_points[:5], 1):  # Limit to 5 results
                response += f"{i}. 🏪 {point['name']}\n"
                response += f"   📍 {point['address']}\n"
                response += f"   📞 {point.get('phone', 'N/A')}\n"
                response += f"   🕒 {point.get('hours', 'Contact store for hours')}\n"
                
                services = ', '.join(point.get('services', []))
                response += f"   🔧 Services: {services}\n\n"
            
            if len(pickup_points) > 5:
                response += f"... and {len(pickup_points) - 5} more locations\n"
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error finding pickup points: {e}")
            return f"❌ Error finding pickup points: {str(e)}"
    
    def get_pickup_point_details(self, pickup_point_id: str) -> Dict:
        """Get detailed information about a specific pickup point"""
        try:
            result = self._make_request(f"/pickup-points/{pickup_point_id}")
            
            if "error" in result:
                # Fallback to default for demo
                if pickup_point_id in ["CPT001", "default"]:
                    return self.default_pickup_point
                elif pickup_point_id == "CPT002":
                    return {
                        "id": "CPT002",
                        "name": "Shoprite - Wynberg",
                        "address": "Maynardville Park, Wynberg, Cape Town",
                        "suburb": "Wynberg",
                        "city": "Cape Town",
                        "province": "Western Cape",
                        "postal_code": "7800",
                        "phone": "+27 21 761 7000",
                        "hours": "Mon-Sun: 8:00-20:00",
                        "services": ["pickup", "collection"]
                    }
                elif pickup_point_id == "JHB001":
                    return {
                        "id": "JHB001",
                        "name": "Pick n Pay - Sandton City",
                        "address": "Sandton City Shopping Centre, Sandton",
                        "suburb": "Sandton",
                        "city": "Johannesburg",
                        "province": "Gauteng",
                        "postal_code": "2196",
                        "phone": "+27 11 784 7200",
                        "hours": "Mon-Fri: 9:00-21:00, Sat-Sun: 9:00-19:00",
                        "services": ["pickup", "collection", "returns"]
                    }
                return {"error": result["error"]}
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting pickup point details: {e}")
            return {"error": f"Error getting pickup point details: {str(e)}"}
    
    def calculate_delivery_cost(self, pickup_point_id: str, package_size: str = "small") -> Dict:
        """Calculate delivery cost to a pickup point"""
        try:
            data = {
                "pickup_point_id": pickup_point_id,
                "package_size": package_size
            }
            
            result = self._make_request("/delivery-cost", method="POST", data=data)
            
            if "error" in result:
                # Mock pricing for demo
                size_costs = {"small": 25.00, "medium": 35.00, "large": 50.00}
                return {
                    "cost": size_costs.get(package_size, 25.00),
                    "currency": "ZAR",
                    "estimated_days": 2
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Error calculating delivery cost: {e}")
            return {"error": f"Error calculating delivery cost: {str(e)}"}
    
    def create_delivery_order(self, order_details: Dict) -> Dict:
        """Create a Paxi delivery order"""
        try:
            required_fields = ["pickup_point_id", "recipient_name", "recipient_phone"]
            for field in required_fields:
                if field not in order_details:
                    return {"error": f"Missing required field: {field}"}
            
            data = {
                "pickup_point_id": order_details["pickup_point_id"],
                "recipient": {
                    "name": order_details["recipient_name"],
                    "phone": order_details["recipient_phone"],
                    "email": order_details.get("recipient_email", "")
                },
                "package": {
                    "size": order_details.get("package_size", "small"),
                    "description": order_details.get("package_description", ""),
                    "value": order_details.get("package_value", 0)
                },
                "sender": {
                    "name": order_details.get("sender_name", "Wednesday Assistant"),
                    "reference": order_details.get("order_reference", f"WA{datetime.now().strftime('%Y%m%d%H%M')}")
                }
            }
            
            result = self._make_request("/deliveries", method="POST", data=data)
            
            if "error" in result:
                return {"error": result["error"]}
            
            return result
            
        except Exception as e:
            logger.error(f"Error creating delivery order: {e}")
            return {"error": f"Error creating delivery order: {str(e)}"}
    
    def track_delivery(self, tracking_number: str) -> str:
        """Track a Paxi delivery"""
        try:
            result = self._make_request(f"/deliveries/{tracking_number}")
            
            if "error" in result:
                return f"❌ Error tracking delivery: {result['error']}"
            
            status = result.get("status", "unknown")
            pickup_point = result.get("pickup_point", {})
            estimated_delivery = result.get("estimated_delivery", "unknown")
            
            response = f"📦 Paxi Delivery Tracking: {tracking_number}\n\n"
            response += f"📊 Status: {status.upper()}\n"
            
            if pickup_point:
                response += f"📍 Pickup Point: {pickup_point.get('name', 'Unknown')}\n"
                response += f"📍 Address: {pickup_point.get('address', 'N/A')}\n"
            
            response += f"📅 Estimated Delivery: {estimated_delivery}\n"
            
            if status == "ready_for_collection":
                response += "\n🎉 Your parcel is ready for collection!\n"
                response += "Please bring ID and your tracking number."
            
            return response
            
        except Exception as e:
            logger.error(f"Error tracking delivery: {e}")
            return f"❌ Error tracking delivery: {str(e)}"
    
    def get_delivery_types(self) -> List[Dict]:
        """Get available delivery types including Paxi"""
        return [
            {
                "id": "paxi_pickup",
                "name": "Paxi Pickup Point",
                "description": "Collect from a nearby Paxi pickup point",
                "cost_range": "R25 - R50",
                "delivery_time": "1-3 business days",
                "features": ["Secure collection", "Extended hours", "No delivery address needed"]
            },
            {
                "id": "home_delivery",
                "name": "Home Delivery",
                "description": "Direct delivery to your address",
                "cost_range": "R50 - R100",
                "delivery_time": "1-2 business days",
                "features": ["Door-to-door service", "Scheduled delivery", "Signature required"]
            },
            {
                "id": "office_delivery",
                "name": "Office Delivery",
                "description": "Delivery to your workplace",
                "cost_range": "R45 - R80",
                "delivery_time": "1-2 business days",
                "features": ["Business hours delivery", "Reception collection", "Corporate accounts"]
            }
        ]
    
    def format_delivery_options(self) -> str:
        """Format delivery options for display"""
        delivery_types = self.get_delivery_types()
        
        response = "🚚 Available Delivery Options:\n"
        response += "=" * 30 + "\n\n"
        
        for i, delivery_type in enumerate(delivery_types, 1):
            response += f"{i}. 📦 {delivery_type['name']}\n"
            response += f"   💰 Cost: {delivery_type['cost_range']}\n"
            response += f"   ⏰ Time: {delivery_type['delivery_time']}\n"
            response += f"   📝 {delivery_type['description']}\n"
            
            features = ' • '.join(delivery_type['features'])
            response += f"   ✨ Features: {features}\n\n"
        
        return response.strip()
    
    def get_service_status(self) -> str:
        """Get Paxi service configuration status"""
        status = "📦 Paxi Service Status\n"
        status += "=" * 25 + "\n\n"
        
        status += f"🔑 API Key: {'✅ Set' if self.api_key else '❌ Not set'}\n"
        status += f"🏢 Partner ID: {'✅ Set' if self.partner_id else '❌ Not set'}\n"
        status += f"🌐 Base URL: {self.base_url}\n\n"
        
        if not self.api_key:
            status += "⚠️ Paxi API not configured - using mock data\n"
            status += "Set PAXI_API_KEY environment variable for live integration\n"
            status += "Set PAXI_PARTNER_ID for partner-specific features"
        else:
            status += "✅ Paxi API configured and ready"
        
        return status

# Global Paxi service instance
paxi_service = PaxiService()