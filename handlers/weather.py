"""
Weather service for WhatsApp Assistant

Provides weather information using WeatherAPI (free weather API)
"""

import os
import requests
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

class WeatherService:
    """Weather information service"""
    
    def __init__(self):
        self.api_key = os.getenv("WEATHERAPI_KEY")
        self.base_url = "http://api.weatherapi.com/v1"
        
    def is_configured(self) -> bool:
        """Check if weather service is properly configured"""
        return bool(self.api_key)
    
    def get_current_weather(self, location: str) -> str:
        """Get current weather for a location"""
        if not self.is_configured():
            return "Weather service not configured. Please set WEATHERAPI_KEY environment variable."
        
        try:
            # Get current weather using WeatherAPI
            weather_url = f"{self.base_url}/current.json"
            weather_params = {
                'key': self.api_key,
                'q': location,
                'aqi': 'no'
            }
            
            weather_response = requests.get(weather_url, params=weather_params, timeout=10)
            weather_response.raise_for_status()
            weather_data = weather_response.json()
            
            return self._format_current_weather(weather_data, location)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Weather API request failed: {e}")
            return f"Failed to get weather information: {str(e)}"
        except Exception as e:
            logger.error(f"Weather service error: {e}")
            return f"Weather service error: {str(e)}"
    
    def get_weather_forecast(self, location: str, days: int = 3) -> str:
        """Get weather forecast for a location"""
        if not self.is_configured():
            return "Weather service not configured. Please set WEATHERAPI_KEY environment variable."
        
        try:
            # Get forecast using WeatherAPI
            forecast_url = f"{self.base_url}/forecast.json"
            forecast_params = {
                'key': self.api_key,
                'q': location,
                'days': min(days, 10),  # WeatherAPI free tier supports up to 10 days
                'aqi': 'no',
                'alerts': 'no'
            }
            
            forecast_response = requests.get(forecast_url, params=forecast_params, timeout=10)
            forecast_response.raise_for_status()
            forecast_data = forecast_response.json()
            
            return self._format_forecast(forecast_data, location, days)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Weather forecast API request failed: {e}")
            return f"Failed to get weather forecast: {str(e)}"
        except Exception as e:
            logger.error(f"Weather forecast service error: {e}")
            return f"Weather forecast service error: {str(e)}"
    
    def _format_current_weather(self, data: Dict[str, Any], location: str) -> str:
        """Format current weather data for display"""
        try:
            current = data['current']
            location_data = data['location']
            
            temp = round(current['temp_c'])
            feels_like = round(current['feelslike_c'])
            humidity = current['humidity']
            description = current['condition']['text']
            wind_speed = round(current['wind_kph'])
            
            location_name = f"{location_data['name']}, {location_data['country']}"
            
            result = f"🌤️ Current weather in {location_name}:\n"
            result += f"🌡️ Temperature: {temp}°C (feels like {feels_like}°C)\n"
            result += f"☁️ Condition: {description}\n"
            result += f"💧 Humidity: {humidity}%\n"
            result += f"💨 Wind: {wind_speed} km/h\n"
            
            return result.strip()
            
        except KeyError as e:
            logger.error(f"Error formatting weather data: {e}")
            return "Error formatting weather information"
    
    def _format_forecast(self, data: Dict[str, Any], location: str, days: int) -> str:
        """Format weather forecast data for display"""
        try:
            forecast_days = data['forecast']['forecastday']
            location_data = data['location']
            location_name = f"{location_data['name']}, {location_data['country']}"
            
            result = f"📅 {days}-day weather forecast for {location_name}:\n\n"
            
            for day_data in forecast_days[:days]:
                date = day_data['date']
                day_info = day_data['day']
                
                max_temp = round(day_info['maxtemp_c'])
                min_temp = round(day_info['mintemp_c'])
                condition = day_info['condition']['text']
                
                # Format date
                from datetime import datetime
                date_obj = datetime.strptime(date, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%A, %B %d')
                
                result += f"📆 {formatted_date}: {max_temp}°C/{min_temp}°C, {condition}\n"
            
            return result.strip()
            
        except (KeyError, IndexError) as e:
            logger.error(f"Error formatting forecast data: {e}")
            return "Error formatting weather forecast"
    
    def get_weather_by_coordinates(self, lat: float, lon: float) -> str:
        """Get weather by GPS coordinates"""
        if not self.is_configured():
            return "Weather service not configured. Please set WEATHERAPI_KEY environment variable."
        
        try:
            # Get current weather using coordinates
            weather_url = f"{self.base_url}/current.json"
            weather_params = {
                'key': self.api_key,
                'q': f"{lat},{lon}",
                'aqi': 'no'
            }
            
            weather_response = requests.get(weather_url, params=weather_params, timeout=10)
            weather_response.raise_for_status()
            weather_data = weather_response.json()
            
            # Get location name from response
            location_data = weather_data['location']
            location_name = f"{location_data['name']}, {location_data['country']}"
            
            return self._format_current_weather(weather_data, location_name)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Weather API request failed: {e}")
            return f"Failed to get weather information: {str(e)}"
        except Exception as e:
            logger.error(f"Weather service error: {e}")
            return f"Weather service error: {str(e)}"
    
    def detect_location_from_message(self, message: str) -> Optional[str]:
        """Extract location from message text"""
        import re
        
        # Common location patterns
        patterns = [
            r"weather in ([A-Za-z\s,]+)",
            r"weather for ([A-Za-z\s,]+)",
            r"weather at ([A-Za-z\s,]+)",
            r"how is the weather in ([A-Za-z\s,]+)",
            r"what's the weather like in ([A-Za-z\s,]+)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                location = match.group(1).strip()
                return location
        
        return None
    
    def get_smart_weather_response(self, message: str, user_location: Optional[Dict] = None) -> str:
        """Get intelligent weather response based on message and location"""
        try:
            # First try to extract location from message
            detected_location = self.detect_location_from_message(message)
            
            if detected_location:
                logger.info(f"Detected location from message: {detected_location}")
                return self.get_current_weather(detected_location)
            
            # If user sent location coordinates (WhatsApp location sharing)
            if user_location and 'latitude' in user_location and 'longitude' in user_location:
                lat = float(user_location['latitude'])
                lon = float(user_location['longitude'])
                logger.info(f"Using shared coordinates: {lat}, {lon}")
                return self.get_weather_by_coordinates(lat, lon)
            
            # Default to asking for location
            return ("🌤️ I'd be happy to check the weather for you! Please either:\n"
                   "• Send me your location using WhatsApp's location sharing\n"
                   "• Tell me the city name (e.g., 'weather in London')\n"
                   "• Ask like 'What's the weather like in Paris?'")
            
        except Exception as e:
            logger.error(f"Smart weather response error: {e}")
            return f"❌ Weather service error: {str(e)}"


# Global weather service instance
weather_service = WeatherService()