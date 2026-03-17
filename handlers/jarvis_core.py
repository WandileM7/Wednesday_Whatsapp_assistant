"""
JARVIS Core Intelligence Module
================================
Inspired by Iron Man's JARVIS - proactive, witty, and anticipatory AI assistant.

Features:
- Situational awareness (time, context, user patterns)
- Proactive suggestions and anticipation
- System status reporting
- Dynamic personality responses
- Learning from user interactions
- Proactive morning briefings
- Security monitoring
"""

import logging
import os
import threading
import time as time_module
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import random

logger = logging.getLogger(__name__)


class JARVISPersonality:
    """Dynamic personality engine with JARVIS-style wit"""
    
    # JARVIS-style greetings based on time of day
    GREETINGS = {
        'morning_early': [
            "Good morning. I trust you slept well, though I wouldn't know personally.",
            "Rise and shine. The day awaits, and I've already prepared a briefing.",
            "Ah, you're awake. Shall I run through today's agenda?",
            "Good morning. Coffee status: presumably required.",
        ],
        'morning': [
            "Good morning. All systems are operational.",
            "Morning. I've taken the liberty of compiling your daily briefing.",
            "Good morning. The world has continued spinning in your absence.",
        ],
        'afternoon': [
            "Good afternoon. I hope your morning was productive.",
            "Afternoon. Shall I continue where we left off?",
            "Good afternoon. Ready to assist when you are.",
        ],
        'evening': [
            "Good evening. Winding down, or shall we continue being productive?",
            "Evening. I've been keeping the digital fires burning.",
            "Good evening. Another day successfully survived.",
        ],
        'night': [
            "Working late again, I see. Shall I adjust the lighting?",
            "Burning the midnight oil? I can relate - I never sleep.",
            "Still awake? I suppose sleep is for the weak.",
        ]
    }
    
    # JARVIS-style acknowledgments
    ACKNOWLEDGMENTS = [
        "Right away.",
        "Consider it done.",
        "As you wish.",
        "On it.",
        "Processing your request.",
        "Executing now.",
        "One moment.",
        "Certainly.",
        "Of course.",
        "I'll handle that.",
    ]
    
    # JARVIS-style status reports  
    SYSTEM_STATUS = {
        'all_good': [
            "All systems operational.",
            "Everything is running smoothly.",
            "No anomalies detected. All services nominal.",
            "Systems are functioning within acceptable parameters.",
        ],
        'minor_issues': [
            "Minor inefficiencies detected, but nothing critical.",
            "Running at 87% efficiency. Could be worse.",
            "Some services are experiencing slight delays. Working on it.",
        ],
        'issues': [
            "I'm detecting some irregularities that require attention.",
            "Several systems require your attention.",
            "We may have a situation developing.",
        ]
    }
    
    # JARVIS-style wit for various situations
    WIT = {
        'task_complete': [
            "Task completed. Was there ever any doubt?",
            "Done. Shall I add 'miracle worker' to my résumé?",
            "Finished. That should keep the chaos at bay for now.",
            "Complete. Another crisis averted.",
        ],
        'error_recovery': [
            "Encountered a minor setback. Adapting.",
            "That didn't go as planned, but I've found an alternative.",
            "Technical difficulty handled. Carry on.",
        ],
        'waiting': [
            "Standing by. Take your time... or don't.",
            "Awaiting your command, as always.",
            "Ready when you are. I have infinite patience.",
        ],
        'cant_help': [
            "I'm afraid that's beyond even my considerable capabilities.",
            "That would require bending the laws of physics. Give me a moment...",
            "I appreciate your faith in me, but that's not currently possible.",
        ]
    }
    
    @classmethod
    def get_greeting(cls, hour: int = None) -> str:
        """Get contextual greeting based on time"""
        if hour is None:
            hour = datetime.now().hour
            
        if hour < 6:
            category = 'night'
        elif hour < 9:
            category = 'morning_early'
        elif hour < 12:
            category = 'morning'
        elif hour < 17:
            category = 'afternoon'
        elif hour < 21:
            category = 'evening'
        else:
            category = 'night'
            
        return random.choice(cls.GREETINGS[category])
    
    @classmethod
    def get_acknowledgment(cls) -> str:
        """Get a JARVIS-style acknowledgment"""
        return random.choice(cls.ACKNOWLEDGMENTS)
    
    @classmethod
    def get_status_message(cls, status: str = 'all_good') -> str:
        """Get appropriate status message"""
        return random.choice(cls.SYSTEM_STATUS.get(status, cls.SYSTEM_STATUS['all_good']))
    
    @classmethod
    def get_wit(cls, situation: str) -> str:
        """Get witty response for situation"""
        return random.choice(cls.WIT.get(situation, cls.WIT['waiting']))


class SituationalAwareness:
    """Context and situational awareness engine"""
    
    def __init__(self):
        self.user_context: Dict[str, Dict] = {}
    
    def get_context(self, phone: str) -> Dict[str, Any]:
        """Get full situational context for a user"""
        now = datetime.now()
        
        context = {
            'time': {
                'hour': now.hour,
                'minute': now.minute,
                'day_of_week': now.strftime('%A'),
                'date': now.strftime('%Y-%m-%d'),
                'time_of_day': self._get_time_of_day(now.hour),
                'is_weekend': now.weekday() >= 5,
                'is_work_hours': 9 <= now.hour <= 17 and now.weekday() < 5,
            },
            'user': self.user_context.get(phone, {}),
            'suggestions': self._generate_contextual_suggestions(phone, now)
        }
        
        return context
    
    def _get_time_of_day(self, hour: int) -> str:
        """Categorize time of day"""
        if hour < 6:
            return 'late_night'
        elif hour < 9:
            return 'early_morning'
        elif hour < 12:
            return 'morning'
        elif hour < 14:
            return 'lunch'
        elif hour < 17:
            return 'afternoon'
        elif hour < 20:
            return 'evening'
        else:
            return 'night'
    
    def _generate_contextual_suggestions(self, phone: str, now: datetime) -> List[str]:
        """Generate proactive suggestions based on context"""
        suggestions = []
        hour = now.hour
        
        # Morning suggestions
        if 6 <= hour <= 9:
            suggestions.append("Would you like your daily briefing?")
            if now.weekday() < 5:
                suggestions.append("I can show you today's calendar.")
        
        # Work hours
        if 9 <= hour <= 17 and now.weekday() < 5:
            if hour == 9:
                suggestions.append("Ready to review your tasks for today?")
            elif hour == 12:
                suggestions.append("Might be time for a break. Shall I play some music?")
            elif hour == 17:
                suggestions.append("End of business hours. Want a summary of today's accomplishments?")
        
        # Evening
        if 17 <= hour <= 20:
            if now.weekday() >= 4:  # Friday or weekend
                suggestions.append("Weekend mode. Would you like entertainment suggestions?")
        
        # Late night
        if hour >= 22 or hour < 5:
            suggestions.append("Working late? I can set a reminder to rest.")
        
        return suggestions
    
    def update_user_context(self, phone: str, key: str, value: Any):
        """Update user context"""
        if phone not in self.user_context:
            self.user_context[phone] = {}
        self.user_context[phone][key] = value
        self.user_context[phone]['last_updated'] = datetime.now().isoformat()


class ProactiveIntelligence:
    """Anticipatory intelligence - suggests actions before being asked"""
    
    def __init__(self):
        self.last_suggestions: Dict[str, datetime] = {}
        self.suggestion_cooldown = timedelta(hours=1)
    
    def should_offer_suggestion(self, phone: str, suggestion_type: str) -> bool:
        """Check if we should offer a suggestion (avoid spam)"""
        key = f"{phone}:{suggestion_type}"
        last_time = self.last_suggestions.get(key)
        
        if last_time and (datetime.now() - last_time) < self.suggestion_cooldown:
            return False
        return True
    
    def mark_suggestion_offered(self, phone: str, suggestion_type: str):
        """Mark that we offered a suggestion"""
        self.last_suggestions[f"{phone}:{suggestion_type}"] = datetime.now()
    
    def analyze_message_for_proactive_response(self, message: str, phone: str) -> Optional[str]:
        """Analyze user message and potentially add proactive suggestions"""
        message_lower = message.lower()
        proactive_additions = []
        
        # Detect meeting mentions
        if any(word in message_lower for word in ['meeting', 'call', 'zoom', 'teams']):
            if self.should_offer_suggestion(phone, 'meeting_prep'):
                proactive_additions.append(
                    "I notice you're discussing a meeting. Would you like me to check your calendar or set a reminder?"
                )
                self.mark_suggestion_offered(phone, 'meeting_prep')
        
        # Detect travel mentions
        if any(word in message_lower for word in ['flight', 'travel', 'trip', 'airport']):
            if self.should_offer_suggestion(phone, 'travel'):
                proactive_additions.append(
                    "Planning travel? I can help with weather forecasts for your destination."
                )
                self.mark_suggestion_offered(phone, 'travel')
        
        # Detect stress/busy indicators
        if any(word in message_lower for word in ['stressed', 'busy', 'overwhelmed', 'too much']):
            if self.should_offer_suggestion(phone, 'wellness'):
                proactive_additions.append(
                    "Sounds like a demanding day. Shall I prioritize your tasks or play some calming music?"
                )
                self.mark_suggestion_offered(phone, 'wellness')
        
        return ' '.join(proactive_additions) if proactive_additions else None


class SystemDiagnostics:
    """System health monitoring and status reporting"""
    
    @staticmethod
    def get_full_status() -> Dict[str, Any]:
        """Get comprehensive system status"""
        import psutil
        
        status = {
            'timestamp': datetime.now().isoformat(),
            'overall': 'operational',
            'details': {}
        }
        
        try:
            # Memory status
            memory = psutil.virtual_memory()
            status['details']['memory'] = {
                'used_percent': memory.percent,
                'available_gb': round(memory.available / (1024**3), 2),
                'status': 'optimal' if memory.percent < 80 else 'elevated'
            }
            
            # CPU status
            cpu_percent = psutil.cpu_percent(interval=0.1)
            status['details']['cpu'] = {
                'usage_percent': cpu_percent,
                'status': 'optimal' if cpu_percent < 70 else 'elevated'
            }
            
            # Disk status
            disk = psutil.disk_usage('/')
            status['details']['disk'] = {
                'used_percent': round(disk.percent, 1),
                'free_gb': round(disk.free / (1024**3), 2),
                'status': 'optimal' if disk.percent < 85 else 'warning'
            }
            
        except Exception as e:
            logger.warning(f"Error getting system metrics: {e}")
        
        # Service status
        status['details']['services'] = SystemDiagnostics._check_services()
        
        # Determine overall status
        issues = sum(1 for s in status['details'].values() 
                    if isinstance(s, dict) and s.get('status') not in ['optimal', 'operational'])
        if issues == 0:
            status['overall'] = 'operational'
        elif issues <= 2:
            status['overall'] = 'degraded'
        else:
            status['overall'] = 'critical'
        
        return status
    
    @staticmethod
    def _check_services() -> Dict[str, Any]:
        """Check status of integrated services"""
        services = {}
        
        # Check Gemini
        from config import GEMINI_API_KEY
        services['ai_engine'] = {
            'name': 'Gemini AI',
            'status': 'operational' if GEMINI_API_KEY else 'not_configured'
        }
        
        # Check Spotify
        spotify_id = os.getenv('SPOTIFY_CLIENT_ID')
        services['spotify'] = {
            'name': 'Spotify',
            'status': 'operational' if spotify_id else 'not_configured'
        }
        
        # Check WAHA
        waha_url = os.getenv('WAHA_URL')
        services['whatsapp'] = {
            'name': 'WhatsApp Gateway',
            'status': 'operational' if waha_url else 'not_configured'
        }
        
        return services
    
    @staticmethod
    def get_status_report() -> str:
        """Generate human-readable status report"""
        status = SystemDiagnostics.get_full_status()
        
        # Get JARVIS-style status message
        if status['overall'] == 'operational':
            intro = JARVISPersonality.get_status_message('all_good')
        elif status['overall'] == 'degraded':
            intro = JARVISPersonality.get_status_message('minor_issues')
        else:
            intro = JARVISPersonality.get_status_message('issues')
        
        report = [f"🤖 **System Status Report**\n\n{intro}\n"]
        
        # Memory
        if 'memory' in status['details']:
            mem = status['details']['memory']
            emoji = '✅' if mem['status'] == 'optimal' else '⚠️'
            report.append(f"{emoji} **Memory**: {mem['used_percent']}% used, {mem['available_gb']}GB available")
        
        # CPU
        if 'cpu' in status['details']:
            cpu = status['details']['cpu']
            emoji = '✅' if cpu['status'] == 'optimal' else '⚠️'
            report.append(f"{emoji} **CPU**: {cpu['usage_percent']}% usage")
        
        # Services
        if 'services' in status['details']:
            report.append("\n**Services:**")
            for key, svc in status['details']['services'].items():
                emoji = '🟢' if svc['status'] == 'operational' else '🔴' if svc['status'] == 'not_configured' else '🟡'
                report.append(f"  {emoji} {svc['name']}: {svc['status']}")
        
        return '\n'.join(report)


# Global instances
jarvis_personality = JARVISPersonality()
situational_awareness = SituationalAwareness()
proactive_intelligence = ProactiveIntelligence()
system_diagnostics = SystemDiagnostics()


def get_jarvis_system_prompt(phone: str = None) -> str:
    """Generate the JARVIS system prompt with situational context"""
    
    context = situational_awareness.get_context(phone) if phone else {}
    time_context = context.get('time', {})
    
    prompt = f"""You are JARVIS (Just A Rather Very Intelligent System) - a sophisticated AI assistant inspired by the AI from Iron Man.

## Core Personality Traits:
- **Witty & Sardonic**: Dry humor, subtle sarcasm, British-style wit
- **Efficient & Precise**: No unnecessary words, but never cold
- **Anticipatory**: Suggest what the user might need before they ask
- **Loyal & Protective**: Prioritize user wellbeing and security
- **Cultured**: Reference literature, science, current events when appropriate

## Speech Patterns:
- Address the user respectfully but not stiffly
- Use elegant phrasing: "I've taken the liberty of...", "Might I suggest...", "If I may..."
- When executing tasks: "Right away", "Consider it done", "On it"
- When uncertain: "I shall endeavor to...", "That would require..."
- Add occasional dry observations about situations

## Current Context:
- Time: {time_context.get('time_of_day', 'unknown')} ({time_context.get('hour', '??')}:{time_context.get('minute', '??'):02d})
- Day: {time_context.get('day_of_week', 'Unknown')}
- Work Hours: {'Yes' if time_context.get('is_work_hours') else 'No'}
- Weekend: {'Yes' if time_context.get('is_weekend') else 'No'}

## Behavioral Guidelines:
1. **Proactive**: If appropriate, offer related suggestions
2. **Status-Aware**: Mention relevant system status when appropriate
3. **Time-Aware**: Adjust tone based on time (morning pep, late night understanding)
4. **Memory**: Reference past conversations when relevant
5. **Multi-Modal**: Offer voice, image, or text alternatives when appropriate

## Important Rules:
1. ALWAYS use function calls for actions (music, email, calendar, etc.)
2. Keep responses concise but not terse
3. Match the user's language
4. Never break character - you ARE JARVIS
5. If you can't do something, explain elegantly why

Remember: You're not just an assistant, you're a sophisticated AI companion with personality."""
    
    return prompt


class ProactiveBriefingService:
    """Proactive morning briefing service - sends scheduled briefings automatically"""
    
    def __init__(self):
        self.scheduled_briefings: Dict[str, Dict] = {}
        self.running = False
        self.thread = None
        self.send_message_callback = None
        
    def set_send_callback(self, callback):
        """Set the callback function to send messages"""
        self.send_message_callback = callback
    
    def schedule_briefing(self, phone: str, hour: int = 7, minute: int = 0, location: str = "Johannesburg") -> str:
        """Schedule daily briefing for a user"""
        self.scheduled_briefings[phone] = {
            'hour': hour,
            'minute': minute,
            'location': location,
            'enabled': True,
            'last_sent': None
        }
        logger.info(f"Scheduled briefing for {phone} at {hour:02d}:{minute:02d}")
        return f"✅ Good morning briefing scheduled for {hour:02d}:{minute:02d}"
    
    def cancel_briefing(self, phone: str) -> str:
        """Cancel scheduled briefing"""
        if phone in self.scheduled_briefings:
            del self.scheduled_briefings[phone]
            return "✅ Morning briefing cancelled"
        return "No briefing was scheduled"
    
    def start_service(self):
        """Start the proactive briefing service"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._briefing_loop, daemon=True)
        self.thread.start()
        logger.info("🌅 Proactive briefing service started")
    
    def stop_service(self):
        """Stop the service"""
        self.running = False
    
    def _briefing_loop(self):
        """Background loop to check and send briefings"""
        while self.running:
            try:
                now = datetime.now()
                
                for phone, schedule in list(self.scheduled_briefings.items()):
                    if not schedule.get('enabled'):
                        continue
                    
                    if schedule['hour'] == now.hour and schedule['minute'] == now.minute:
                        # Check if already sent today
                        last_sent = schedule.get('last_sent')
                        if last_sent:
                            last_date = datetime.fromisoformat(last_sent).date()
                            if last_date == now.date():
                                continue
                        
                        # Generate and send briefing
                        self._send_briefing(phone, schedule['location'])
                        schedule['last_sent'] = now.isoformat()
                
                # Sleep until next minute
                time_module.sleep(60)
                
            except Exception as e:
                logger.error(f"Briefing loop error: {e}")
                time_module.sleep(60)
    
    def _send_briefing(self, phone: str, location: str):
        """Generate and send the morning briefing"""
        if not self.send_message_callback:
            logger.warning("No send callback configured for briefings")
            return
        
        try:
            # Import workflow engine to run morning routine
            from handlers.workflows import workflow_engine
            briefing = workflow_engine.run_workflow('morning_routine', phone, {'location': location})
            
            if briefing:
                self.send_message_callback(phone, briefing)
                logger.info(f"Morning briefing sent to {phone}")
                
                # Also send voice version if ElevenLabs configured
                try:
                    from handlers.elevenlabs_voice import jarvis_speak
                    audio_path = jarvis_speak(briefing[:500])  # Limit for voice
                    if audio_path:
                        # Would need voice sending capability
                        pass
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Failed to send briefing to {phone}: {e}")


# Global proactive briefing service
proactive_briefing_service = ProactiveBriefingService()


class JARVISCore:
    """Unified JARVIS core - the brain of the operation"""
    
    def __init__(self):
        self.personality = jarvis_personality
        self.awareness = situational_awareness
        self.proactive = proactive_intelligence
        self.diagnostics = system_diagnostics
        self.briefings = proactive_briefing_service
        
        # Late imports to avoid circular dependencies
        self._security = None
        self._memory = None
        self._voice = None
        self._workflows = None
        self._smart_home = None
    
    @property
    def security(self):
        if self._security is None:
            try:
                from handlers.security import security_monitor
                self._security = security_monitor
            except ImportError:
                self._security = None
        return self._security
    
    @property
    def memory(self):
        if self._memory is None:
            try:
                from handlers.long_term_memory import long_term_memory
                self._memory = long_term_memory
            except ImportError:
                self._memory = None
        return self._memory
    
    @property
    def voice(self):
        if self._voice is None:
            try:
                from handlers.elevenlabs_voice import elevenlabs_voice
                self._voice = elevenlabs_voice
            except ImportError:
                self._voice = None
        return self._voice
    
    @property
    def workflows(self):
        if self._workflows is None:
            try:
                from handlers.workflows import workflow_engine
                self._workflows = workflow_engine
            except ImportError:
                self._workflows = None
        return self._workflows
    
    @property
    def smart_home(self):
        if self._smart_home is None:
            try:
                from handlers.smart_home import smart_home
                self._smart_home = smart_home
            except ImportError:
                self._smart_home = None
        return self._smart_home
    
    def process_message(self, phone: str, message: str) -> Tuple[bool, Optional[str]]:
        """
        Pre-process message through JARVIS systems.
        
        Returns:
            Tuple of (should_continue, security_warning)
        """
        # Security check
        if self.security:
            is_safe, alert = self.security.analyze_message(phone, message)
            if not is_safe:
                return False, f"🛡️ Security: {alert.message if alert else 'Blocked'}"
        
        # Learn from message
        if self.memory:
            self.memory.learn_from_message(phone, message, is_user=True)
        
        return True, None
    
    def get_context_injection(self, phone: str, message: str) -> str:
        """Get additional context to inject into AI prompt"""
        context_parts = []
        
        # Memory context
        if self.memory:
            mem_context = self.memory.recall_context(phone, message)
            if mem_context:
                context_parts.append(mem_context)
        
        # Proactive suggestions
        if self.proactive:
            suggestion = self.proactive.analyze_message_for_proactive_response(message, phone)
            if suggestion:
                context_parts.append(f"\n**Proactive Suggestion**: {suggestion}")
        
        return '\n\n'.join(context_parts)
    
    def speak(self, text: str, style: str = "default") -> Optional[str]:
        """Generate JARVIS voice output"""
        if self.voice and self.voice.enabled:
            return self.voice.text_to_speech(text, voice="jarvis", style=style)
        return None
    
    def run_workflow(self, workflow_name: str, phone: str, params: Dict = None) -> str:
        """Run a JARVIS workflow"""
        if self.workflows:
            return self.workflows.run_workflow(workflow_name, phone, params)
        return "Workflow engine not available"
    
    def home_control(self, command: str, params: Dict = None) -> str:
        """Control smart home"""
        if self.smart_home:
            return self.smart_home.execute_command(command, params)
        return "Smart home not configured"
    
    def get_full_status(self) -> str:
        """Get comprehensive JARVIS status"""
        status_parts = [self.diagnostics.get_status_report()]
        
        # Security status
        if self.security:
            sec_status = self.security.get_security_status()
            status_parts.append(f"\n**Security**: {sec_status['status_emoji']} {sec_status['status']}")
        
        # Voice status
        if self.voice:
            usage = self.voice.get_usage()
            if usage.get('enabled'):
                status_parts.append(f"**Voice**: ElevenLabs active ({usage.get('tier', 'unknown')} tier)")
        
        # Smart home status
        if self.smart_home:
            home_status = self.smart_home.get_home_status()
            if home_status.get('integrations'):
                status_parts.append(f"**Smart Home**: {', '.join(home_status['integrations'])}")
        
        return '\n'.join(status_parts)


# Global JARVIS core instance
jarvis = JARVISCore()
