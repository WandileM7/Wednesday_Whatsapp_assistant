"""
Weather service for WhatsApp Assistant

Provides weather information using OpenWeatherMap API
"""

import os
import requests
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

class WeatherService:
    """Weather information service"""
    
    def __init__(self):
        self.api_key = os.getenv("OPENWEATHER_API_KEY")
        self.base_url = "http://api.openweathermap.org/data/2.5"
        
    def is_configured(self) -> bool:
        """Check if weather service is properly configured"""
        return bool(self.api_key)
    
    def get_current_weather(self, location: str) -> str:
        """Get current weather for a location"""
        if not self.is_configured():
            return "Weather service not configured. Please set OPENWEATHER_API_KEY environment variable."
        
        try:
            # Get coordinates for the location
            geo_url = f"http://api.openweathermap.org/geo/1.0/direct"
            geo_params = {
                'q': location,
                'limit': 1,
                'appid': self.api_key
            }
            
            geo_response = requests.get(geo_url, params=geo_params, timeout=10)
            geo_response.raise_for_status()
            geo_data = geo_response.json()
            
            if not geo_data:
                return f"Location '{location}' not found. Please try a different location."
            
            lat = geo_data[0]['lat']
            lon = geo_data[0]['lon']
            
            # Get current weather
            weather_url = f"{self.base_url}/weather"
            weather_params = {
                'lat': lat,
                'lon': lon,
                'appid': self.api_key,
                'units': 'metric'
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
            return "Weather service not configured. Please set OPENWEATHER_API_KEY environment variable."
        
        try:
            # Get coordinates for the location
            geo_url = f"http://api.openweathermap.org/geo/1.0/direct"
            geo_params = {
                'q': location,
                'limit': 1,
                'appid': self.api_key
            }
            
            geo_response = requests.get(geo_url, params=geo_params, timeout=10)
            geo_response.raise_for_status()
            geo_data = geo_response.json()
            
            if not geo_data:
                return f"Location '{location}' not found. Please try a different location."
            
            lat = geo_data[0]['lat']
            lon = geo_data[0]['lon']
            
            # Get forecast
            forecast_url = f"{self.base_url}/forecast"
            forecast_params = {
                'lat': lat,
                'lon': lon,
                'appid': self.api_key,
                'units': 'metric'
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
            weather = data['weather'][0]
            main = data['main']
            wind = data.get('wind', {})
            
            temp = round(main['temp'])
            feels_like = round(main['feels_like'])
            humidity = main['humidity']
            description = weather['description'].title()
            
            result = f"🌤️ Current weather in {location}:\n"
            result += f"🌡️ Temperature: {temp}°C (feels like {feels_like}°C)\n"
            result += f"☁️ Condition: {description}\n"
            result += f"💧 Humidity: {humidity}%\n"
            
            if 'speed' in wind:
                wind_speed = round(wind['speed'] * 3.6)  # Convert m/s to km/h
                result += f"💨 Wind: {wind_speed} km/h\n"
            
            return result.strip()
            
        except KeyError as e:
            logger.error(f"Error formatting weather data: {e}")
            return "Error formatting weather information"
    
    def _format_forecast(self, data: Dict[str, Any], location: str, days: int) -> str:
        """Format weather forecast data for display"""
        try:
            forecasts = data['list']
            result = f"📅 {days}-day weather forecast for {location}:\n\n"
            
            # Group forecasts by date
            daily_forecasts = {}
            for forecast in forecasts[:days * 8]:  # 8 forecasts per day (3-hour intervals)
                date = forecast['dt_txt'][:10]  # Get date part (YYYY-MM-DD)
                
                if date not in daily_forecasts:
                    daily_forecasts[date] = []
                daily_forecasts[date].append(forecast)
            
            for date, day_forecasts in list(daily_forecasts.items())[:days]:
                # Get midday forecast for the day
                midday_forecast = day_forecasts[len(day_forecasts)//2] if day_forecasts else day_forecasts[0]
                
                weather = midday_forecast['weather'][0]
                main = midday_forecast['main']
                
                temp = round(main['temp'])
                description = weather['description'].title()
                
                # Format date
                from datetime import datetime
                date_obj = datetime.strptime(date, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%A, %B %d')
                
                result += f"📆 {formatted_date}: {temp}°C, {description}\n"
            
            return result.strip()
            
        except (KeyError, IndexError) as e:
            logger.error(f"Error formatting forecast data: {e}")
            return "Error formatting weather forecast"


# Global weather service instance
weather_service = WeatherService()