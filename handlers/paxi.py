"""
PAXI API integration for delivery management
"""
import os
import requests
import json
import logging
from typing import Dict, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class PaxiAPI:
    """PAXI delivery API integration"""
    
    def __init__(self):
        self.api_key = os.getenv('PAXI_API_KEY', '')
        self.base_url = os.getenv('PAXI_BASE_URL', 'https://api.paxi.co.za/v1')
        self.merchant_id = os.getenv('PAXI_MERCHANT_ID', '')
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def is_configured(self) -> bool:
        """Check if PAXI API is properly configured"""
        return bool(self.api_key and self.merchant_id)
    
    def get_pickup_points(self, city: str = "", postal_code: str = "") -> List[Dict]:
        """Get available PAXI pickup points"""
        try:
            if not self.is_configured():
                logger.warning("PAXI API not configured, returning mock data")
                return self._get_mock_pickup_points(city)
            
            params = {}
            if city:
                params['city'] = city
            if postal_code:
                params['postal_code'] = postal_code
            
            response = requests.get(
                f"{self.base_url}/pickup-points",
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('pickup_points', [])
            else:
                logger.error(f"PAXI API error: {response.status_code} - {response.text}")
                return self._get_mock_pickup_points(city)
                
        except Exception as e:
            logger.error(f"Error fetching PAXI pickup points: {e}")
            return self._get_mock_pickup_points(city)
    
    def create_delivery(self, order_data: Dict) -> Dict:
        """Create a delivery with PAXI"""
        try:
            if not self.is_configured():
                logger.warning("PAXI API not configured, returning mock tracking")
                return self._create_mock_delivery(order_data)
            
            delivery_request = {
                'merchant_id': self.merchant_id,
                'reference': order_data.get('order_number'),
                'recipient': {
                    'name': order_data.get('recipient_name'),
                    'phone': order_data.get('recipient_phone'),
                    'email': order_data.get('recipient_email', '')
                },
                'pickup_point_id': order_data.get('pickup_point_id'),
                'package': {
                    'description': order_data.get('package_description', 'Online order'),
                    'value': order_data.get('package_value', 0),
                    'weight': order_data.get('package_weight', 1.0),
                    'dimensions': {
                        'length': order_data.get('length', 20),
                        'width': order_data.get('width', 20),
                        'height': order_data.get('height', 10)
                    }
                },
                'service_level': order_data.get('service_level', 'standard'),
                'notifications': {
                    'sms': True,
                    'email': bool(order_data.get('recipient_email'))
                }
            }
            
            response = requests.post(
                f"{self.base_url}/deliveries",
                headers=self.headers,
                json=delivery_request,
                timeout=15
            )
            
            if response.status_code == 201:
                data = response.json()
                return {
                    'success': True,
                    'tracking_number': data.get('tracking_number'),
                    'delivery_id': data.get('delivery_id'),
                    'estimated_delivery': data.get('estimated_delivery_date'),
                    'pickup_point': data.get('pickup_point_details'),
                    'cost': data.get('delivery_cost', 0)
                }
            else:
                logger.error(f"PAXI delivery creation failed: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'error': f"PAXI API error: {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"Error creating PAXI delivery: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def track_delivery(self, tracking_number: str) -> Dict:
        """Track a PAXI delivery"""
        try:
            if not self.is_configured():
                return self._get_mock_tracking_status(tracking_number)
            
            response = requests.get(
                f"{self.base_url}/deliveries/{tracking_number}/status",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'status': data.get('status'),
                    'status_description': data.get('status_description'),
                    'location': data.get('current_location'),
                    'estimated_delivery': data.get('estimated_delivery_date'),
                    'pickup_point': data.get('pickup_point_details'),
                    'tracking_history': data.get('tracking_events', [])
                }
            else:
                logger.error(f"PAXI tracking failed: {response.status_code} - {response.text}")
                return self._get_mock_tracking_status(tracking_number)
                
        except Exception as e:
            logger.error(f"Error tracking PAXI delivery: {e}")
            return self._get_mock_tracking_status(tracking_number)
    
    def calculate_delivery_cost(self, pickup_point_id: str, package_weight: float = 1.0) -> Dict:
        """Calculate delivery cost"""
        try:
            if not self.is_configured():
                return self._get_mock_delivery_cost(package_weight)
            
            cost_request = {
                'pickup_point_id': pickup_point_id,
                'package': {
                    'weight': package_weight,
                    'service_level': 'standard'
                }
            }
            
            response = requests.post(
                f"{self.base_url}/deliveries/calculate-cost",
                headers=self.headers,
                json=cost_request,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'cost': data.get('cost'),
                    'currency': data.get('currency', 'ZAR'),
                    'estimated_delivery_days': data.get('estimated_delivery_days', 3)
                }
            else:
                logger.error(f"PAXI cost calculation failed: {response.status_code}")
                return self._get_mock_delivery_cost(package_weight)
                
        except Exception as e:
            logger.error(f"Error calculating PAXI delivery cost: {e}")
            return self._get_mock_delivery_cost(package_weight)
    
    def cancel_delivery(self, tracking_number: str) -> Dict:
        """Cancel a PAXI delivery"""
        try:
            if not self.is_configured():
                return {'success': True, 'message': 'Mock cancellation successful'}
            
            response = requests.delete(
                f"{self.base_url}/deliveries/{tracking_number}",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return {'success': True, 'message': 'Delivery cancelled successfully'}
            else:
                logger.error(f"PAXI cancellation failed: {response.status_code}")
                return {'success': False, 'error': f"Cancellation failed: {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Error cancelling PAXI delivery: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_service_status(self) -> Dict:
        """Get PAXI service configuration status"""
        return {
            'service': 'PAXI Delivery',
            'configured': self.is_configured(),
            'api_key_set': bool(self.api_key),
            'merchant_id_set': bool(self.merchant_id),
            'base_url': self.base_url,
            'test_mode': not self.is_configured()
        }
    
    # Mock data methods for testing without API access
    def _get_mock_pickup_points(self, city: str = "") -> List[Dict]:
        """Return mock pickup points for testing"""
        mock_points = [
            {
                'id': 'JHB001',
                'name': 'PAXI Sandton City',
                'address': 'Sandton City Shopping Centre, Johannesburg',
                'city': 'Johannesburg',
                'postal_code': '2196',
                'operating_hours': 'Mon-Fri: 9AM-6PM, Sat: 9AM-5PM, Sun: 10AM-4PM',
                'phone': '+27 11 123 4567',
                'coordinates': {'lat': -26.1076, 'lng': 28.0567}
            },
            {
                'id': 'CPT001',
                'name': 'PAXI V&A Waterfront',
                'address': 'V&A Waterfront, Cape Town',
                'city': 'Cape Town',
                'postal_code': '8001',
                'operating_hours': 'Mon-Sun: 9AM-9PM',
                'phone': '+27 21 987 6543',
                'coordinates': {'lat': -33.9025, 'lng': 18.4187}
            },
            {
                'id': 'DBN001',
                'name': 'PAXI Gateway Theatre',
                'address': 'Gateway Theatre of Shopping, Durban',
                'city': 'Durban',
                'postal_code': '4051',
                'operating_hours': 'Mon-Fri: 9AM-6PM, Sat-Sun: 9AM-5PM',
                'phone': '+27 31 555 0123',
                'coordinates': {'lat': -29.7391, 'lng': 31.0218}
            }
        ]
        
        if city:
            return [point for point in mock_points if city.lower() in point['city'].lower()]
        
        return mock_points
    
    def _create_mock_delivery(self, order_data: Dict) -> Dict:
        """Create mock delivery for testing"""
        import uuid
        tracking_number = f"PX{datetime.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"
        
        return {
            'success': True,
            'tracking_number': tracking_number,
            'delivery_id': f"DEL{str(uuid.uuid4())[:8].upper()}",
            'estimated_delivery': (datetime.now().strftime('%Y-%m-%d')),
            'pickup_point': {
                'name': 'PAXI Sandton City',
                'address': 'Sandton City Shopping Centre, Johannesburg'
            },
            'cost': 45.00,
            'message': 'Mock delivery created for testing'
        }
    
    def _get_mock_tracking_status(self, tracking_number: str) -> Dict:
        """Get mock tracking status for testing"""
        statuses = ['collected', 'in_transit', 'at_pickup_point', 'delivered']
        import random
        
        return {
            'success': True,
            'status': random.choice(statuses),
            'status_description': 'Package is being processed',
            'location': 'Johannesburg Distribution Centre',
            'estimated_delivery': datetime.now().strftime('%Y-%m-%d'),
            'pickup_point': {
                'name': 'PAXI Sandton City',
                'address': 'Sandton City Shopping Centre'
            },
            'tracking_history': [
                {
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'status': 'collected',
                    'description': 'Package collected from sender',
                    'location': 'Origin'
                }
            ]
        }
    
    def _get_mock_delivery_cost(self, weight: float) -> Dict:
        """Get mock delivery cost for testing"""
        base_cost = 35.00
        weight_cost = max(0, (weight - 1.0) * 5.00)  # R5 per additional kg
        
        return {
            'success': True,
            'cost': base_cost + weight_cost,
            'currency': 'ZAR',
            'estimated_delivery_days': 3
        }

# Global PAXI instance
paxi_api = PaxiAPI()

# Integration functions for the main application
def get_delivery_options(city: str = "", postal_code: str = "") -> Dict:
    """Get available delivery options for a location"""
    try:
        pickup_points = paxi_api.get_pickup_points(city, postal_code)
        
        return {
            'success': True,
            'pickup_points': pickup_points,
            'service_available': len(pickup_points) > 0,
            'message': f"Found {len(pickup_points)} pickup points"
        }
        
    except Exception as e:
        logger.error(f"Error getting delivery options: {e}")
        return {
            'success': False,
            'error': str(e),
            'pickup_points': []
        }

def create_order_delivery(order_number: str, customer_data: Dict, pickup_point_id: str) -> Dict:
    """Create delivery for an order"""
    try:
        order_data = {
            'order_number': order_number,
            'recipient_name': customer_data.get('name'),
            'recipient_phone': customer_data.get('phone') or customer_data.get('whatsapp_number'),
            'recipient_email': customer_data.get('email'),
            'pickup_point_id': pickup_point_id,
            'package_description': f"Order {order_number}",
            'package_value': customer_data.get('total_amount', 0),
            'package_weight': customer_data.get('weight', 1.0)
        }
        
        result = paxi_api.create_delivery(order_data)
        
        if result.get('success'):
            logger.info(f"PAXI delivery created for order {order_number}: {result.get('tracking_number')}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error creating order delivery: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def track_order_delivery(tracking_number: str) -> Dict:
    """Track an order delivery"""
    return paxi_api.track_delivery(tracking_number)

def calculate_shipping_cost(pickup_point_id: str, weight: float = 1.0) -> Dict:
    """Calculate shipping cost for an order"""
    return paxi_api.calculate_delivery_cost(pickup_point_id, weight)

def get_paxi_service_status() -> Dict:
    """Get PAXI service status for admin dashboard"""
    return paxi_api.get_service_status()