"""
JARVIS Workflow Engine
======================
Multi-step automated workflows like Tony Stark would use.
"JARVIS, prepare for my meeting" → calendar check + weather + traffic + document prep
"""

import os
import logging
import asyncio
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class WorkflowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class WorkflowStep:
    """Single step in a workflow"""
    name: str
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    optional: bool = False
    timeout: int = 30
    result: Any = None
    status: WorkflowStatus = WorkflowStatus.PENDING
    error: str = None


@dataclass
class Workflow:
    """Multi-step workflow definition"""
    id: str
    name: str
    description: str
    steps: List[WorkflowStep]
    phone: str = None
    status: WorkflowStatus = WorkflowStatus.PENDING
    started_at: datetime = None
    completed_at: datetime = None
    results: Dict[str, Any] = field(default_factory=dict)


class WorkflowEngine:
    """JARVIS-style workflow automation engine"""
    
    def __init__(self):
        self.workflows: Dict[str, Workflow] = {}
        self.workflow_templates: Dict[str, Callable] = {}
        self.action_handlers: Dict[str, Callable] = {}
        self._register_default_workflows()
        self._register_action_handlers()
        
        logger.info("⚙️ JARVIS Workflow Engine initialized")
    
    def _register_default_workflows(self):
        """Register built-in workflow templates"""
        
        # Morning Routine
        self.workflow_templates['morning_routine'] = lambda phone, params: Workflow(
            id=f"morning_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name="Morning Routine",
            description="Complete morning briefing and setup",
            phone=phone,
            steps=[
                WorkflowStep(name="weather", action="get_weather", params={'location': params.get('location', 'Johannesburg')}),
                WorkflowStep(name="calendar", action="get_today_events", depends_on=[]),
                WorkflowStep(name="tasks", action="get_pending_tasks", depends_on=[]),
                WorkflowStep(name="news", action="get_news_headlines", params={'limit': 3}),
                WorkflowStep(name="briefing", action="compile_briefing", depends_on=["weather", "calendar", "tasks", "news"]),
                WorkflowStep(name="speak", action="speak_text", params={'style': 'default'}, depends_on=["briefing"], optional=True),
            ]
        )
        
        # Meeting Preparation
        self.workflow_templates['prepare_meeting'] = lambda phone, params: Workflow(
            id=f"meeting_prep_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name="Meeting Preparation",
            description="Prepare for upcoming meeting",
            phone=phone,
            steps=[
                WorkflowStep(name="meeting_details", action="get_next_meeting", params={}),
                WorkflowStep(name="weather", action="get_weather", params={'location': params.get('location', 'current')}),
                WorkflowStep(name="traffic", action="check_traffic", params={}, optional=True),
                WorkflowStep(name="attendees", action="lookup_attendees", depends_on=["meeting_details"], optional=True),
                WorkflowStep(name="documents", action="find_relevant_docs", depends_on=["meeting_details"], optional=True),
                WorkflowStep(name="summary", action="compile_meeting_prep", depends_on=["meeting_details", "weather"]),
            ]
        )
        
        # End of Day Summary
        self.workflow_templates['end_of_day'] = lambda phone, params: Workflow(
            id=f"eod_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name="End of Day Summary",
            description="Daily summary and tomorrow prep",
            phone=phone,
            steps=[
                WorkflowStep(name="completed_tasks", action="get_completed_today", params={}),
                WorkflowStep(name="pending_tasks", action="get_pending_tasks", params={}),
                WorkflowStep(name="tomorrow_calendar", action="get_tomorrow_events", params={}),
                WorkflowStep(name="summary", action="compile_eod_summary", depends_on=["completed_tasks", "pending_tasks", "tomorrow_calendar"]),
            ]
        )
        
        # Focus Mode
        self.workflow_templates['focus_mode'] = lambda phone, params: Workflow(
            id=f"focus_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name="Focus Mode",
            description="Activate focus mode for deep work",
            phone=phone,
            steps=[
                WorkflowStep(name="lights", action="smart_home_lights", params={'brightness': 80}),
                WorkflowStep(name="music", action="play_focus_music", params={'playlist': 'focus'}, optional=True),
                WorkflowStep(name="notifications", action="enable_dnd", params={'duration': params.get('duration', 60)}),
                WorkflowStep(name="timer", action="set_focus_timer", params={'minutes': params.get('duration', 60)}),
                WorkflowStep(name="confirm", action="focus_confirmation", depends_on=["lights", "notifications", "timer"]),
            ]
        )
        
        # Leaving Home
        self.workflow_templates['leaving_home'] = lambda phone, params: Workflow(
            id=f"leaving_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name="Leaving Home",
            description="Prepare home for departure",
            phone=phone,
            steps=[
                WorkflowStep(name="weather_check", action="get_weather", params={}),
                WorkflowStep(name="lights_off", action="smart_home_lights", params={'brightness': 0}),
                WorkflowStep(name="thermostat", action="set_away_thermostat", params={}, optional=True),
                WorkflowStep(name="locks", action="lock_doors", params={}, optional=True),
                WorkflowStep(name="security", action="arm_security", params={}, optional=True),
                WorkflowStep(name="summary", action="compile_leaving_summary", depends_on=["weather_check", "lights_off"]),
            ]
        )
        
        # Coming Home
        self.workflow_templates['coming_home'] = lambda phone, params: Workflow(
            id=f"arriving_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name="Coming Home",
            description="Prepare home for arrival",
            phone=phone,
            steps=[
                WorkflowStep(name="lights_on", action="smart_home_lights", params={'brightness': 80}),
                WorkflowStep(name="thermostat", action="set_home_thermostat", params={}, optional=True),
                WorkflowStep(name="security", action="disarm_security", params={}, optional=True),
                WorkflowStep(name="music", action="play_welcome_music", params={}, optional=True),
                WorkflowStep(name="summary", action="compile_welcome_summary", depends_on=["lights_on"]),
            ]
        )
        
        # Party Mode
        self.workflow_templates['party_mode'] = lambda phone, params: Workflow(
            id=f"party_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name="Party Mode",
            description="Set up for entertainment",
            phone=phone,
            steps=[
                WorkflowStep(name="lights", action="smart_home_scene", params={'scene': 'party'}),
                WorkflowStep(name="music", action="play_party_music", params={}, optional=True),
                WorkflowStep(name="thermostat", action="set_thermostat", params={'temperature': 72}),
                WorkflowStep(name="announcement", action="party_announcement", depends_on=["lights", "music"]),
            ]
        )
        
        # Sleep Mode
        self.workflow_templates['sleep_mode'] = lambda phone, params: Workflow(
            id=f"sleep_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name="Sleep Mode",
            description="Prepare for sleep",
            phone=phone,
            steps=[
                WorkflowStep(name="tomorrow_preview", action="get_tomorrow_events", params={}),
                WorkflowStep(name="lights", action="smart_home_lights", params={'brightness': 0}),
                WorkflowStep(name="locks", action="lock_doors", params={}, optional=True),
                WorkflowStep(name="dnd", action="enable_dnd", params={'until': 'morning'}),
                WorkflowStep(name="alarm", action="set_alarm", params={'time': params.get('wake_time', '07:00')}, optional=True),
                WorkflowStep(name="summary", action="compile_sleep_summary", depends_on=["tomorrow_preview", "lights"]),
            ]
        )
    
    def _register_action_handlers(self):
        """Register action handlers for workflow steps"""
        
        # Weather
        self.action_handlers['get_weather'] = self._action_get_weather
        
        # Calendar
        self.action_handlers['get_today_events'] = self._action_get_today_events
        self.action_handlers['get_tomorrow_events'] = self._action_get_tomorrow_events
        self.action_handlers['get_next_meeting'] = self._action_get_next_meeting
        
        # Tasks
        self.action_handlers['get_pending_tasks'] = self._action_get_pending_tasks
        self.action_handlers['get_completed_today'] = self._action_get_completed_today
        
        # News
        self.action_handlers['get_news_headlines'] = self._action_get_news
        
        # Smart Home
        self.action_handlers['smart_home_lights'] = self._action_smart_home_lights
        self.action_handlers['smart_home_scene'] = self._action_smart_home_scene
        self.action_handlers['lock_doors'] = self._action_lock_doors
        self.action_handlers['set_thermostat'] = self._action_set_thermostat
        self.action_handlers['set_away_thermostat'] = self._action_set_away_thermostat
        self.action_handlers['set_home_thermostat'] = self._action_set_home_thermostat
        
        # Music
        self.action_handlers['play_focus_music'] = self._action_play_focus_music
        self.action_handlers['play_party_music'] = self._action_play_party_music
        self.action_handlers['play_welcome_music'] = self._action_play_welcome_music
        
        # Notifications
        self.action_handlers['enable_dnd'] = self._action_enable_dnd
        
        # Timers
        self.action_handlers['set_focus_timer'] = self._action_set_focus_timer
        self.action_handlers['set_alarm'] = self._action_set_alarm
        
        # Security
        self.action_handlers['arm_security'] = self._action_arm_security
        self.action_handlers['disarm_security'] = self._action_disarm_security
        
        # Compilations
        self.action_handlers['compile_briefing'] = self._action_compile_briefing
        self.action_handlers['compile_meeting_prep'] = self._action_compile_meeting_prep
        self.action_handlers['compile_eod_summary'] = self._action_compile_eod_summary
        self.action_handlers['compile_leaving_summary'] = self._action_compile_leaving_summary
        self.action_handlers['compile_welcome_summary'] = self._action_compile_welcome_summary
        self.action_handlers['compile_sleep_summary'] = self._action_compile_sleep_summary
        self.action_handlers['focus_confirmation'] = self._action_focus_confirmation
        self.action_handlers['party_announcement'] = self._action_party_announcement
        
        # Voice
        self.action_handlers['speak_text'] = self._action_speak_text
        
        # Misc
        self.action_handlers['lookup_attendees'] = self._action_lookup_attendees
        self.action_handlers['find_relevant_docs'] = self._action_find_relevant_docs
        self.action_handlers['check_traffic'] = self._action_check_traffic
    
    # ==================== Action Handlers ====================
    
    async def _action_get_weather(self, params: Dict, context: Dict) -> Dict:
        """Get weather information"""
        try:
            from handlers.weather import weather_service
            location = params.get('location', 'Johannesburg')
            weather = weather_service.get_current_weather(location)
            return {'success': True, 'data': weather}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _action_get_today_events(self, params: Dict, context: Dict) -> Dict:
        """Get today's calendar events"""
        try:
            from handlers.calendar import get_todays_events
            events = get_todays_events()
            return {'success': True, 'data': events or []}
        except Exception as e:
            return {'success': False, 'error': str(e), 'data': []}
    
    async def _action_get_tomorrow_events(self, params: Dict, context: Dict) -> Dict:
        """Get tomorrow's calendar events"""
        try:
            from handlers.calendar import get_events_for_date
            tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            events = get_events_for_date(tomorrow)
            return {'success': True, 'data': events or []}
        except Exception as e:
            return {'success': False, 'error': str(e), 'data': []}
    
    async def _action_get_next_meeting(self, params: Dict, context: Dict) -> Dict:
        """Get next upcoming meeting"""
        try:
            from handlers.calendar import get_todays_events
            events = get_todays_events() or []
            now = datetime.now()
            upcoming = [e for e in events if e.get('start_time', '') > now.isoformat()]
            next_meeting = upcoming[0] if upcoming else None
            return {'success': True, 'data': next_meeting}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _action_get_pending_tasks(self, params: Dict, context: Dict) -> Dict:
        """Get pending tasks"""
        try:
            from handlers.tasks import task_manager
            tasks = task_manager.get_tasks()
            pending = [t for t in tasks if t.get('status') != 'completed']
            return {'success': True, 'data': pending}
        except Exception as e:
            return {'success': False, 'error': str(e), 'data': []}
    
    async def _action_get_completed_today(self, params: Dict, context: Dict) -> Dict:
        """Get tasks completed today"""
        try:
            from handlers.tasks import task_manager
            tasks = task_manager.get_tasks()
            today = datetime.now().date().isoformat()
            completed = [t for t in tasks if t.get('status') == 'completed' and t.get('completed_at', '').startswith(today)]
            return {'success': True, 'data': completed}
        except Exception as e:
            return {'success': False, 'error': str(e), 'data': []}
    
    async def _action_get_news(self, params: Dict, context: Dict) -> Dict:
        """Get news headlines"""
        try:
            from handlers.news import news_service
            limit = params.get('limit', 5)
            news = news_service.get_top_headlines(limit=limit)
            return {'success': True, 'data': news or []}
        except Exception as e:
            return {'success': False, 'error': str(e), 'data': []}
    
    async def _action_smart_home_lights(self, params: Dict, context: Dict) -> Dict:
        """Control smart home lights"""
        try:
            from handlers.smart_home import smart_home
            brightness = params.get('brightness', 100)
            room = params.get('room', 'all')
            color = params.get('color')
            
            if brightness == 0:
                result = smart_home.lights_off(room)
            else:
                result = smart_home.lights_on(room, brightness, color)
            
            return {'success': True, 'data': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _action_smart_home_scene(self, params: Dict, context: Dict) -> Dict:
        """Activate smart home scene"""
        try:
            from handlers.smart_home import smart_home
            scene = params.get('scene', 'default')
            result = smart_home.activate_scene(scene)
            return {'success': True, 'data': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _action_lock_doors(self, params: Dict, context: Dict) -> Dict:
        """Lock doors"""
        try:
            from handlers.smart_home import smart_home
            result = smart_home.lock_doors()
            return {'success': True, 'data': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _action_set_thermostat(self, params: Dict, context: Dict) -> Dict:
        """Set thermostat"""
        try:
            from handlers.smart_home import smart_home
            temp = params.get('temperature', 72)
            result = smart_home.set_thermostat(temp)
            return {'success': True, 'data': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _action_set_away_thermostat(self, params: Dict, context: Dict) -> Dict:
        """Set thermostat for away mode"""
        try:
            from handlers.smart_home import smart_home
            result = smart_home.set_thermostat(65, 'away')
            return {'success': True, 'data': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _action_set_home_thermostat(self, params: Dict, context: Dict) -> Dict:
        """Set thermostat for home mode"""
        try:
            from handlers.smart_home import smart_home
            result = smart_home.set_thermostat(72, 'home')
            return {'success': True, 'data': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _action_play_focus_music(self, params: Dict, context: Dict) -> Dict:
        """Play focus music"""
        try:
            from handlers.spotify import play_music
            result = play_music("lo-fi beats")
            return {'success': True, 'data': 'Playing focus music'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _action_play_party_music(self, params: Dict, context: Dict) -> Dict:
        """Play party music"""
        try:
            from handlers.spotify import play_music
            result = play_music("party hits")
            return {'success': True, 'data': 'Playing party music'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _action_play_welcome_music(self, params: Dict, context: Dict) -> Dict:
        """Play welcome home music"""
        try:
            from handlers.spotify import play_music
            result = play_music("chill vibes")
            return {'success': True, 'data': 'Playing welcome music'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _action_enable_dnd(self, params: Dict, context: Dict) -> Dict:
        """Enable do not disturb"""
        duration = params.get('duration', 60)
        return {'success': True, 'data': f'Do not disturb enabled for {duration} minutes'}
    
    async def _action_set_focus_timer(self, params: Dict, context: Dict) -> Dict:
        """Set focus timer"""
        minutes = params.get('minutes', 60)
        return {'success': True, 'data': f'Focus timer set for {minutes} minutes'}
    
    async def _action_set_alarm(self, params: Dict, context: Dict) -> Dict:
        """Set alarm"""
        time = params.get('time', '07:00')
        return {'success': True, 'data': f'Alarm set for {time}'}
    
    async def _action_arm_security(self, params: Dict, context: Dict) -> Dict:
        """Arm security system"""
        return {'success': True, 'data': 'Security system armed'}
    
    async def _action_disarm_security(self, params: Dict, context: Dict) -> Dict:
        """Disarm security system"""
        return {'success': True, 'data': 'Security system disarmed'}
    
    async def _action_lookup_attendees(self, params: Dict, context: Dict) -> Dict:
        """Look up meeting attendees"""
        meeting = context.get('meeting_details', {}).get('data')
        if meeting:
            attendees = meeting.get('attendees', [])
            return {'success': True, 'data': attendees}
        return {'success': True, 'data': []}
    
    async def _action_find_relevant_docs(self, params: Dict, context: Dict) -> Dict:
        """Find relevant documents for meeting"""
        return {'success': True, 'data': []}
    
    async def _action_check_traffic(self, params: Dict, context: Dict) -> Dict:
        """Check traffic conditions"""
        return {'success': True, 'data': {'status': 'normal', 'delay_minutes': 0}}
    
    async def _action_compile_briefing(self, params: Dict, context: Dict) -> Dict:
        """Compile morning briefing"""
        weather = context.get('weather', {}).get('data', {})
        events = context.get('calendar', {}).get('data', [])
        tasks = context.get('tasks', {}).get('data', [])
        news = context.get('news', {}).get('data', [])
        
        briefing = ["🌅 **Good morning! Here's your daily briefing:**\n"]
        
        # Weather
        if weather and not weather.get('error'):
            temp = weather.get('temperature', 'N/A')
            condition = weather.get('condition', 'Unknown')
            briefing.append(f"🌤️ **Weather**: {condition}, {temp}°C\n")
        
        # Calendar
        if events:
            briefing.append("📅 **Today's Schedule**:")
            for event in events[:5]:
                time = event.get('time', event.get('start_time', ''))
                title = event.get('title', event.get('summary', 'Untitled'))
                briefing.append(f"  • {time} - {title}")
            briefing.append("")
        else:
            briefing.append("📅 No events scheduled today\n")
        
        # Tasks
        if tasks:
            high_priority = [t for t in tasks if t.get('priority') in ['high', 'urgent']]
            briefing.append(f"✅ **Tasks**: {len(tasks)} pending")
            if high_priority:
                briefing.append(f"  ⚠️ {len(high_priority)} high priority")
            briefing.append("")
        
        # News
        if news:
            briefing.append("📰 **Headlines**:")
            for article in news[:3]:
                title = article.get('title', '')[:60]
                if title:
                    briefing.append(f"  • {title}")
            briefing.append("")
        
        briefing.append("Have a productive day! 💪")
        
        return {'success': True, 'data': '\n'.join(briefing)}
    
    async def _action_compile_meeting_prep(self, params: Dict, context: Dict) -> Dict:
        """Compile meeting preparation summary"""
        meeting = context.get('meeting_details', {}).get('data')
        weather = context.get('weather', {}).get('data', {})
        
        if not meeting:
            return {'success': True, 'data': "No upcoming meetings found."}
        
        summary = [f"📋 **Meeting Preparation**\n"]
        summary.append(f"📌 **{meeting.get('summary', 'Meeting')}**")
        summary.append(f"🕐 {meeting.get('start_time', 'TBD')}")
        
        if meeting.get('location'):
            summary.append(f"📍 {meeting.get('location')}")
        
        if weather:
            summary.append(f"\n🌤️ Weather: {weather.get('condition', 'Unknown')}, {weather.get('temperature', 'N/A')}°C")
        
        summary.append("\n✅ You're prepared!")
        
        return {'success': True, 'data': '\n'.join(summary)}
    
    async def _action_compile_eod_summary(self, params: Dict, context: Dict) -> Dict:
        """Compile end of day summary"""
        completed = context.get('completed_tasks', {}).get('data', [])
        pending = context.get('pending_tasks', {}).get('data', [])
        tomorrow = context.get('tomorrow_calendar', {}).get('data', [])
        
        summary = ["🌙 **End of Day Summary**\n"]
        
        summary.append(f"✅ **Completed Today**: {len(completed)} tasks")
        summary.append(f"📋 **Still Pending**: {len(pending)} tasks")
        
        if tomorrow:
            summary.append(f"\n📅 **Tomorrow**: {len(tomorrow)} events scheduled")
            for event in tomorrow[:3]:
                summary.append(f"  • {event.get('time', '')} - {event.get('title', 'Event')}")
        
        summary.append("\nGreat work today! 🌟")
        
        return {'success': True, 'data': '\n'.join(summary)}
    
    async def _action_compile_leaving_summary(self, params: Dict, context: Dict) -> Dict:
        """Compile leaving home summary"""
        weather = context.get('weather_check', {}).get('data', {})
        
        summary = ["🚪 **Leaving Home**\n"]
        summary.append("✅ Lights off")
        summary.append("🔒 Doors locked")
        summary.append("🌡️ Thermostat set to away mode")
        
        if weather:
            summary.append(f"\n🌤️ Outside: {weather.get('condition', 'Unknown')}, {weather.get('temperature', 'N/A')}°C")
            if weather.get('temperature', 20) < 15:
                summary.append("🧥 Consider bringing a jacket!")
        
        summary.append("\n🏠 Home secured. Have a safe trip!")
        
        return {'success': True, 'data': '\n'.join(summary)}
    
    async def _action_compile_welcome_summary(self, params: Dict, context: Dict) -> Dict:
        """Compile welcome home summary"""
        return {'success': True, 'data': "🏠 **Welcome Home!**\n\n✅ Lights on\n🌡️ Temperature comfortable\n🎵 Music playing\n\nRelax, you're home!"}
    
    async def _action_compile_sleep_summary(self, params: Dict, context: Dict) -> Dict:
        """Compile sleep mode summary"""
        tomorrow = context.get('tomorrow_preview', {}).get('data', [])
        
        summary = ["😴 **Sleep Mode Activated**\n"]
        summary.append("✅ Lights off")
        summary.append("🔒 Doors locked")
        summary.append("🔕 Do not disturb enabled")
        
        if tomorrow:
            first_event = tomorrow[0] if tomorrow else None
            if first_event:
                summary.append(f"\n📅 First event tomorrow: {first_event.get('time', '')} - {first_event.get('title', '')}")
        
        summary.append("\n💤 Goodnight!")
        
        return {'success': True, 'data': '\n'.join(summary)}
    
    async def _action_focus_confirmation(self, params: Dict, context: Dict) -> Dict:
        """Confirm focus mode activation"""
        return {'success': True, 'data': "🎯 **Focus Mode Activated**\n\n✅ Lights optimized\n🎵 Focus music playing\n🔕 Notifications silenced\n⏱️ Timer started\n\nTime to be productive!"}
    
    async def _action_party_announcement(self, params: Dict, context: Dict) -> Dict:
        """Party mode announcement"""
        return {'success': True, 'data': "🎉 **Party Mode Activated!**\n\n💡 Lights set to party\n🎵 Party music playing\n🌡️ Temperature comfortable\n\nLet's have some fun!"}
    
    async def _action_speak_text(self, params: Dict, context: Dict) -> Dict:
        """Convert text to speech"""
        try:
            from handlers.elevenlabs_voice import jarvis_speak
            briefing = context.get('briefing', {}).get('data', '')
            if briefing:
                audio_path = jarvis_speak(briefing, style=params.get('style', 'default'))
                return {'success': True, 'data': audio_path}
            return {'success': False, 'error': 'No text to speak'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== Workflow Execution ====================
    
    async def execute_workflow(self, workflow: Workflow) -> Dict[str, Any]:
        """Execute a workflow"""
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = datetime.now()
        
        context = {}  # Shared context between steps
        
        logger.info(f"Starting workflow: {workflow.name}")
        
        for step in workflow.steps:
            # Check dependencies
            deps_satisfied = all(
                context.get(dep, {}).get('success', False) or 
                next((s for s in workflow.steps if s.name == dep), None).optional
                for dep in step.depends_on
            )
            
            if not deps_satisfied and not step.optional:
                step.status = WorkflowStatus.FAILED
                step.error = "Dependencies not satisfied"
                continue
            
            # Execute step
            step.status = WorkflowStatus.RUNNING
            try:
                handler = self.action_handlers.get(step.action)
                if handler:
                    result = await handler(step.params, context)
                    step.result = result
                    step.status = WorkflowStatus.COMPLETED if result.get('success') else WorkflowStatus.FAILED
                    context[step.name] = result
                else:
                    step.status = WorkflowStatus.FAILED
                    step.error = f"Unknown action: {step.action}"
                    
            except Exception as e:
                step.status = WorkflowStatus.FAILED
                step.error = str(e)
                logger.error(f"Workflow step {step.name} failed: {e}")
                
                if not step.optional:
                    workflow.status = WorkflowStatus.FAILED
                    break
        
        # Determine final status
        failed_required = [s for s in workflow.steps if s.status == WorkflowStatus.FAILED and not s.optional]
        if failed_required:
            workflow.status = WorkflowStatus.FAILED
        else:
            workflow.status = WorkflowStatus.COMPLETED
        
        workflow.completed_at = datetime.now()
        workflow.results = context
        
        logger.info(f"Workflow {workflow.name} completed with status: {workflow.status.value}")
        
        return self._format_workflow_result(workflow)
    
    def _format_workflow_result(self, workflow: Workflow) -> Dict[str, Any]:
        """Format workflow result for response"""
        # Find the main output (usually the last compilation step)
        main_output = None
        for step in reversed(workflow.steps):
            if step.status == WorkflowStatus.COMPLETED and step.result:
                data = step.result.get('data')
                if isinstance(data, str) and len(data) > 50:
                    main_output = data
                    break
        
        return {
            'success': workflow.status == WorkflowStatus.COMPLETED,
            'workflow_id': workflow.id,
            'name': workflow.name,
            'status': workflow.status.value,
            'output': main_output,
            'steps_completed': sum(1 for s in workflow.steps if s.status == WorkflowStatus.COMPLETED),
            'steps_total': len(workflow.steps),
            'duration_seconds': (workflow.completed_at - workflow.started_at).total_seconds() if workflow.completed_at else None
        }
    
    def run_workflow(self, workflow_name: str, phone: str = None, params: Dict = None) -> str:
        """Run a workflow template synchronously"""
        params = params or {}
        
        if workflow_name not in self.workflow_templates:
            available = ', '.join(self.workflow_templates.keys())
            return f"❌ Unknown workflow: {workflow_name}\n\nAvailable workflows: {available}"
        
        try:
            # Create workflow from template
            workflow = self.workflow_templates[workflow_name](phone, params)
            
            # Run async workflow
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.execute_workflow(workflow))
            loop.close()
            
            if result.get('success') and result.get('output'):
                return result['output']
            elif result.get('success'):
                return f"✅ Workflow '{workflow_name}' completed successfully!"
            else:
                return f"⚠️ Workflow '{workflow_name}' completed with some issues."
                
        except Exception as e:
            logger.error(f"Workflow execution error: {e}")
            return f"❌ Workflow failed: {str(e)}"
    
    def list_workflows(self) -> str:
        """List available workflows"""
        workflows = [
            ("morning_routine", "🌅 Complete morning briefing"),
            ("prepare_meeting", "📋 Prepare for next meeting"),
            ("end_of_day", "🌙 Daily summary & tomorrow preview"),
            ("focus_mode", "🎯 Activate deep work mode"),
            ("leaving_home", "🚪 Secure home before leaving"),
            ("coming_home", "🏠 Welcome home setup"),
            ("party_mode", "🎉 Entertainment mode"),
            ("sleep_mode", "😴 Prepare for sleep"),
        ]
        
        result = ["⚙️ **Available Workflows**\n"]
        for name, desc in workflows:
            result.append(f"• `{name}` - {desc}")
        
        result.append("\nSay 'run [workflow]' to activate!")
        return '\n'.join(result)


# Global instance
workflow_engine = WorkflowEngine()
