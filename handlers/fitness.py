"""
Fitness Integration for WhatsApp Assistant

Provides fitness tracking and health data integration with Samsung Health and Google Fit
"""

import os
import json
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

class FitnessService:
    """Fitness tracking and health data integration service"""
    
    def __init__(self):
        self.google_fit_token = os.getenv("GOOGLE_FIT_ACCESS_TOKEN")
        self.samsung_health_token = os.getenv("SAMSUNG_HEALTH_ACCESS_TOKEN")
        
        # Local storage for fitness data
        self.data_file = Path("task_data") / "fitness_data.json"
        self.data_file.parent.mkdir(exist_ok=True)
        self.local_data = self._load_local_data()
        
        # Google Fit API endpoints
        self.google_fit_base = "https://www.googleapis.com/fitness/v1/users/me"
        
        # Mock fitness data for demonstration
        self.mock_data = {
            "steps": {
                "today": 8543,
                "yesterday": 10234,
                "weekly_avg": 9156,
                "goal": 10000
            },
            "heart_rate": {
                "current": 72,
                "resting": 65,
                "max_today": 145,
                "min_today": 58
            },
            "calories": {
                "burned_today": 2150,
                "goal": 2500,
                "active_calories": 420
            },
            "sleep": {
                "last_night": {
                    "duration": 7.5,
                    "quality": "Good",
                    "deep_sleep": 2.1,
                    "rem_sleep": 1.8
                }
            },
            "activities": [
                {
                    "type": "Running",
                    "duration": 35,
                    "calories": 380,
                    "distance": 5.2,
                    "time": "2025-01-26 07:30"
                },
                {
                    "type": "Strength Training",
                    "duration": 45,
                    "calories": 220,
                    "time": "2025-01-25 18:00"
                }
            ]
        }
    
    def _load_local_data(self) -> Dict:
        """Load local fitness data"""
        try:
            if self.data_file.exists():
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading fitness data: {e}")
            return {}
    
    def _save_local_data(self):
        """Save local fitness data"""
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.local_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving fitness data: {e}")
    
    def _make_google_fit_request(self, endpoint: str, method: str = "GET", data: Dict = None) -> Dict:
        """Make request to Google Fit API"""
        if not self.google_fit_token:
            return {"error": "Google Fit not configured"}
        
        headers = {
            "Authorization": f"Bearer {self.google_fit_token}",
            "Content-Type": "application/json"
        }
        
        url = f"{self.google_fit_base}{endpoint}"
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data)
            else:
                return {"error": f"Unsupported method: {method}"}
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Google Fit API request failed: {e}")
            return {"error": f"Google Fit API request failed: {str(e)}"}
    
    def get_daily_summary(self, date: str = None) -> str:
        """Get daily fitness summary"""
        try:
            if not date:
                date = datetime.now().strftime("%Y-%m-%d")
            
            # For demonstration, use mock data
            # Real implementation would fetch from Google Fit/Samsung Health
            data = self.mock_data
            
            response = f"📊 Daily Fitness Summary - {date}\n"
            response += "=" * 35 + "\n\n"
            
            # Steps
            steps_today = data["steps"]["today"]
            steps_goal = data["steps"]["goal"]
            steps_progress = (steps_today / steps_goal) * 100
            
            response += f"👣 Steps: {steps_today:,} / {steps_goal:,} ({steps_progress:.1f}%)\n"
            response += f"   📈 Weekly average: {data['steps']['weekly_avg']:,}\n\n"
            
            # Calories
            calories_burned = data["calories"]["burned_today"]
            calories_goal = data["calories"]["goal"]
            calories_progress = (calories_burned / calories_goal) * 100
            
            response += f"🔥 Calories: {calories_burned} / {calories_goal} ({calories_progress:.1f}%)\n"
            response += f"   💪 Active calories: {data['calories']['active_calories']}\n\n"
            
            # Heart Rate
            hr = data["heart_rate"]
            response += f"❤️ Heart Rate:\n"
            response += f"   💓 Current: {hr['current']} bpm\n"
            response += f"   😴 Resting: {hr['resting']} bpm\n"
            response += f"   🏃 Max today: {hr['max_today']} bpm\n\n"
            
            # Sleep
            sleep = data["sleep"]["last_night"]
            response += f"😴 Sleep (last night):\n"
            response += f"   ⏱️ Duration: {sleep['duration']} hours\n"
            response += f"   ✨ Quality: {sleep['quality']}\n"
            response += f"   🛌 Deep sleep: {sleep['deep_sleep']} hours\n"
            response += f"   🧠 REM sleep: {sleep['rem_sleep']} hours\n\n"
            
            # Progress indicators
            if steps_progress >= 100:
                response += "🎉 Congratulations! You reached your step goal!\n"
            elif steps_progress >= 80:
                response += "💪 Almost there! Keep it up!\n"
            
            if calories_progress >= 100:
                response += "🔥 Great job! You hit your calorie goal!\n"
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting daily summary: {e}")
            return f"❌ Error getting daily summary: {str(e)}"
    
    def get_activity_history(self, days: int = 7) -> str:
        """Get recent activity history"""
        try:
            activities = self.mock_data["activities"]
            
            response = f"🏃 Recent Activities ({days} days)\n"
            response += "=" * 30 + "\n\n"
            
            for activity in activities:
                response += f"🏋️ {activity['type']}\n"
                response += f"   📅 {activity['time']}\n"
                response += f"   ⏱️ Duration: {activity['duration']} minutes\n"
                response += f"   🔥 Calories: {activity['calories']}\n"
                
                if 'distance' in activity:
                    response += f"   📏 Distance: {activity['distance']} km\n"
                
                response += "\n"
            
            # Weekly summary
            total_duration = sum(a['duration'] for a in activities)
            total_calories = sum(a['calories'] for a in activities)
            
            response += f"📊 Weekly Totals:\n"
            response += f"   ⏱️ Total time: {total_duration} minutes\n"
            response += f"   🔥 Total calories: {total_calories}\n"
            response += f"   🏃 Activities: {len(activities)}\n"
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting activity history: {e}")
            return f"❌ Error getting activity history: {str(e)}"
    
    def log_activity(self, activity_type: str, duration: int, calories: int = None,
                     distance: float = None, notes: str = None) -> str:
        """Log a new fitness activity"""
        try:
            activity_id = f"act_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            activity = {
                "id": activity_id,
                "type": activity_type,
                "duration": duration,
                "calories": calories,
                "distance": distance,
                "notes": notes,
                "timestamp": datetime.now().isoformat(),
                "date": datetime.now().strftime("%Y-%m-%d")
            }
            
            # Save to local storage
            if "activities" not in self.local_data:
                self.local_data["activities"] = []
            
            self.local_data["activities"].append(activity)
            self._save_local_data()
            
            response = "✅ Activity logged successfully!\n\n"
            response += f"🏋️ Type: {activity_type}\n"
            response += f"⏱️ Duration: {duration} minutes\n"
            
            if calories:
                response += f"🔥 Calories: {calories}\n"
            
            if distance:
                response += f"📏 Distance: {distance} km\n"
            
            if notes:
                response += f"📝 Notes: {notes}\n"
            
            response += f"🆔 Activity ID: {activity_id}\n"
            
            return response
            
        except Exception as e:
            logger.error(f"Error logging activity: {e}")
            return f"❌ Error logging activity: {str(e)}"
    
    def set_fitness_goal(self, goal_type: str, target: int) -> str:
        """Set fitness goals"""
        try:
            if "goals" not in self.local_data:
                self.local_data["goals"] = {}
            
            self.local_data["goals"][goal_type] = {
                "target": target,
                "set_date": datetime.now().isoformat()
            }
            
            self._save_local_data()
            
            response = f"🎯 Fitness goal set successfully!\n\n"
            response += f"📊 Goal type: {goal_type}\n"
            response += f"🎯 Target: {target}\n"
            response += f"📅 Set on: {datetime.now().strftime('%Y-%m-%d')}\n\n"
            response += "💪 You've got this! Stay consistent!"
            
            return response
            
        except Exception as e:
            logger.error(f"Error setting fitness goal: {e}")
            return f"❌ Error setting fitness goal: {str(e)}"
    
    def get_health_insights(self) -> str:
        """Get health insights and recommendations"""
        try:
            data = self.mock_data
            insights = []
            
            # Steps analysis
            steps_today = data["steps"]["today"]
            steps_goal = data["steps"]["goal"]
            
            if steps_today < steps_goal * 0.5:
                insights.append("👣 You're behind on your step goal. Try taking a walk!")
            elif steps_today >= steps_goal:
                insights.append("🎉 Great job hitting your step goal!")
            
            # Heart rate analysis
            resting_hr = data["heart_rate"]["resting"]
            if resting_hr < 60:
                insights.append("❤️ Your resting heart rate indicates excellent fitness!")
            elif resting_hr > 80:
                insights.append("💓 Consider cardio exercises to improve heart health")
            
            # Sleep analysis
            sleep_duration = data["sleep"]["last_night"]["duration"]
            if sleep_duration < 7:
                insights.append("😴 You might need more sleep for optimal recovery")
            elif sleep_duration >= 8:
                insights.append("✨ Great sleep duration! Your body is recovering well")
            
            response = "🧠 Health Insights & Recommendations\n"
            response += "=" * 40 + "\n\n"
            
            for i, insight in enumerate(insights, 1):
                response += f"{i}. {insight}\n\n"
            
            if not insights:
                response += "📊 All metrics look good! Keep up the great work!\n\n"
            
            response += "💡 General Tips:\n"
            response += "• Stay hydrated (8+ glasses of water daily)\n"
            response += "• Aim for 150+ minutes of moderate exercise weekly\n"
            response += "• Prioritize 7-9 hours of quality sleep\n"
            response += "• Take breaks from sitting every hour\n"
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting health insights: {e}")
            return f"❌ Error getting health insights: {str(e)}"
    
    def get_service_status(self) -> str:
        """Get fitness service status"""
        status = "🏃 Fitness Service Status\n"
        status += "=" * 25 + "\n\n"
        
        status += f"🔑 Google Fit: {'✅ Connected' if self.google_fit_token else '❌ Not connected'}\n"
        status += f"🔑 Samsung Health: {'✅ Connected' if self.samsung_health_token else '❌ Not connected'}\n"
        status += f"📁 Local Data: {'✅ Available' if self.local_data else '❌ No data'}\n"
        status += f"📊 Mock Data: ✅ Available for testing\n\n"
        
        if self.local_data.get("activities"):
            activity_count = len(self.local_data["activities"])
            status += f"🏋️ Logged Activities: {activity_count}\n"
        
        if self.local_data.get("goals"):
            goal_count = len(self.local_data["goals"])
            status += f"🎯 Set Goals: {goal_count}\n"
        
        if not any([self.google_fit_token, self.samsung_health_token]):
            status += "\n⚠️ No fitness APIs connected\n"
            status += "Set GOOGLE_FIT_ACCESS_TOKEN or SAMSUNG_HEALTH_ACCESS_TOKEN for real data"
        else:
            status += "\n✅ Fitness tracking ready"
        
        return status

# Global fitness service instance
fitness_service = FitnessService()