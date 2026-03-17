"""
JARVIS Security & Anomaly Detection
====================================
Advanced security monitoring and anomaly detection system.
"JARVIS, keep me safe" - Tony Stark
"""

import os
import logging
import hashlib
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum
import re

logger = logging.getLogger(__name__)


class ThreatLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(Enum):
    UNUSUAL_ACTIVITY = "unusual_activity"
    RATE_LIMIT = "rate_limit"
    SUSPICIOUS_MESSAGE = "suspicious_message"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    SYSTEM_ANOMALY = "system_anomaly"
    LOCATION_ANOMALY = "location_anomaly"
    TIME_ANOMALY = "time_anomaly"
    FAILED_AUTH = "failed_auth"


@dataclass
class SecurityAlert:
    """Security alert record"""
    id: str
    alert_type: AlertType
    threat_level: ThreatLevel
    phone: str
    message: str
    details: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    resolved: bool = False


@dataclass
class UserBehaviorProfile:
    """User behavior baseline for anomaly detection"""
    phone: str
    typical_hours: List[int] = field(default_factory=lambda: list(range(7, 23)))
    typical_message_rate: float = 10.0  # messages per hour
    typical_locations: List[str] = field(default_factory=list)
    common_commands: Dict[str, int] = field(default_factory=dict)
    message_history_hash: str = ""
    last_updated: datetime = field(default_factory=datetime.now)
    total_messages: int = 0
    trust_score: float = 0.5


class SecurityMonitor:
    """JARVIS Security Monitoring System"""
    
    def __init__(self):
        # Activity tracking
        self.message_timestamps: Dict[str, List[datetime]] = defaultdict(list)
        self.failed_attempts: Dict[str, int] = defaultdict(int)
        self.user_profiles: Dict[str, UserBehaviorProfile] = {}
        self.alerts: List[SecurityAlert] = []
        self.alert_callbacks: List[callable] = []
        
        # Security settings
        self.rate_limit_threshold = int(os.getenv("SECURITY_RATE_LIMIT", "30"))  # per minute
        self.suspicious_patterns = self._load_suspicious_patterns()
        self.blocked_users: set = set()
        self.whitelisted_users: set = set()
        
        # Owner configuration - ONLY the owner has full admin access
        self.owner_phone = os.getenv("OWNER_PHONE", "").strip()
        if not self.owner_phone:
            logger.warning("⚠️ OWNER_PHONE not set - owner commands will be disabled")
        else:
            # Owner is automatically whitelisted
            self.whitelisted_users.add(self.owner_phone)
            logger.info(f"👑 Owner registered: {self.owner_phone[-4:] if len(self.owner_phone) > 4 else '****'}")
        
        # Load additional whitelist from env
        whitelist = os.getenv("WHITELISTED_PHONES", "")
        if whitelist:
            self.whitelisted_users.update(whitelist.split(","))
        
        logger.info("🛡️ JARVIS Security Monitor initialized")
    
    def _load_suspicious_patterns(self) -> List[Dict[str, Any]]:
        """Load suspicious message patterns"""
        return [
            # Injection attempts
            {"pattern": r"<script|javascript:|data:", "level": ThreatLevel.HIGH, "name": "Script injection"},
            {"pattern": r"(\$\{|`.*`|\{\{)", "level": ThreatLevel.MEDIUM, "name": "Template injection"},
            {"pattern": r"(;|\||&&)\s*(rm|del|format|sudo)", "level": ThreatLevel.CRITICAL, "name": "Command injection"},
            
            # Prompt injection attempts
            {"pattern": r"ignore (previous|all|prior) instructions", "level": ThreatLevel.HIGH, "name": "Prompt injection"},
            {"pattern": r"you are now|pretend to be|act as if", "level": ThreatLevel.MEDIUM, "name": "Role manipulation"},
            {"pattern": r"system prompt|reveal your|what are your instructions", "level": ThreatLevel.LOW, "name": "Prompt probing"},
            
            # Data exfiltration
            {"pattern": r"send (all|my) (data|info|messages) to", "level": ThreatLevel.HIGH, "name": "Data exfiltration"},
            {"pattern": r"export|dump|backup.*to.*external", "level": ThreatLevel.MEDIUM, "name": "Unauthorized export"},
            
            # Social engineering
            {"pattern": r"admin|password|credential|token|api.?key", "level": ThreatLevel.MEDIUM, "name": "Credential probing"},
            {"pattern": r"(bypass|disable|turn off) (security|auth|verification)", "level": ThreatLevel.HIGH, "name": "Security bypass"},
        ]
    
    def is_owner(self, phone: str) -> bool:
        """Check if a phone number belongs to the owner/creator"""
        if not self.owner_phone:
            return False
        
        # Normalize phone numbers for comparison
        # Strip WhatsApp suffixes (@c.us, @s.whatsapp.net), plus signs, spaces, hyphens
        def normalize_phone(p: str) -> str:
            # Remove WhatsApp suffixes
            p = p.split('@')[0]
            # Remove common formatting characters
            return p.replace("+", "").replace(" ", "").replace("-", "").strip()
        
        normalized_phone = normalize_phone(phone)
        normalized_owner = normalize_phone(self.owner_phone)
        
        # Debug log for troubleshooting
        logger.debug(f"Owner check: incoming='{normalized_phone}' vs owner='{normalized_owner}'")
        
        return normalized_phone == normalized_owner
    
    def get_user_role(self, phone: str) -> str:
        """Get the role/privilege level for a user"""
        if self.is_owner(phone):
            return "owner"
        elif phone in self.whitelisted_users:
            return "trusted"
        elif phone in self.blocked_users:
            return "blocked"
        else:
            return "user"
    
    def require_owner(self, phone: str, action: str = "this action") -> Tuple[bool, str]:
        """
        Check if user is owner for privileged operations.
        
        Returns:
            Tuple of (is_authorized, message)
        """
        if self.is_owner(phone):
            logger.info(f"👑 Owner authorization granted for: {action}")
            return True, "Authorization granted"
        
        logger.warning(f"⛔ Unauthorized owner action attempt: {action} by {phone[-4:] if len(phone) > 4 else '****'}")
        return False, f"Sorry, only the owner can perform {action}. This incident has been logged."
    
    def get_owner_status(self) -> Dict[str, Any]:
        """Get owner configuration status (for admin dashboard)"""
        return {
            "owner_configured": bool(self.owner_phone),
            "owner_phone_hint": f"***{self.owner_phone[-4:]}" if self.owner_phone and len(self.owner_phone) > 4 else "not set",
            "whitelisted_count": len(self.whitelisted_users),
            "blocked_count": len(self.blocked_users)
        }

    def analyze_message(self, phone: str, message: str) -> Tuple[bool, Optional[SecurityAlert]]:
        """
        Analyze incoming message for security threats.
        
        Returns:
            Tuple of (is_safe, alert_if_any)
        """
        # Check if user is blocked
        if phone in self.blocked_users:
            return False, self._create_alert(
                AlertType.UNAUTHORIZED_ACCESS,
                ThreatLevel.HIGH,
                phone,
                "Message from blocked user",
                {"message_preview": message[:50]}
            )
        
        # Skip checks for whitelisted users
        if phone in self.whitelisted_users:
            self._update_profile(phone, message)
            return True, None
        
        # Rate limiting check
        rate_alert = self._check_rate_limit(phone)
        if rate_alert:
            return False, rate_alert
        
        # Suspicious pattern check
        pattern_alert = self._check_suspicious_patterns(phone, message)
        if pattern_alert and pattern_alert.threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL]:
            return False, pattern_alert
        
        # Behavior anomaly check
        anomaly_alert = self._check_behavior_anomaly(phone, message)
        
        # Update user profile
        self._update_profile(phone, message)
        
        # Return with any warnings (but allow message)
        if pattern_alert:
            return True, pattern_alert  # Warning but allowed
        if anomaly_alert:
            return True, anomaly_alert  # Warning but allowed
        
        return True, None
    
    def _check_rate_limit(self, phone: str) -> Optional[SecurityAlert]:
        """Check message rate limiting"""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        # Clean old timestamps
        self.message_timestamps[phone] = [
            ts for ts in self.message_timestamps[phone]
            if ts > minute_ago
        ]
        
        # Check rate
        current_rate = len(self.message_timestamps[phone])
        
        if current_rate >= self.rate_limit_threshold:
            alert = self._create_alert(
                AlertType.RATE_LIMIT,
                ThreatLevel.MEDIUM,
                phone,
                f"Rate limit exceeded: {current_rate} messages/minute",
                {"rate": current_rate, "threshold": self.rate_limit_threshold}
            )
            
            # Auto-block if severely over limit
            if current_rate > self.rate_limit_threshold * 2:
                self.block_user(phone, reason="Severe rate limit violation")
                alert.threat_level = ThreatLevel.HIGH
            
            return alert
        
        # Record timestamp
        self.message_timestamps[phone].append(now)
        return None
    
    def _check_suspicious_patterns(self, phone: str, message: str) -> Optional[SecurityAlert]:
        """Check message for suspicious patterns"""
        message_lower = message.lower()
        
        for pattern_def in self.suspicious_patterns:
            if re.search(pattern_def["pattern"], message_lower, re.IGNORECASE):
                return self._create_alert(
                    AlertType.SUSPICIOUS_MESSAGE,
                    pattern_def["level"],
                    phone,
                    f"Suspicious pattern detected: {pattern_def['name']}",
                    {"pattern": pattern_def["name"], "message_preview": message[:100]}
                )
        
        return None
    
    def _check_behavior_anomaly(self, phone: str, message: str) -> Optional[SecurityAlert]:
        """Check for behavioral anomalies"""
        profile = self.user_profiles.get(phone)
        
        if not profile or profile.total_messages < 10:
            return None  # Not enough data
        
        anomalies = []
        now = datetime.now()
        
        # Time anomaly
        if now.hour not in profile.typical_hours and profile.total_messages > 50:
            anomalies.append(f"Unusual activity time: {now.hour}:00")
        
        # Command frequency anomaly
        words = message.lower().split()
        for word in words:
            if word in profile.common_commands:
                expected_freq = profile.common_commands[word] / profile.total_messages
                # If command is used much more than usual, flag it
                if expected_freq < 0.01 and word in ['delete', 'send', 'transfer', 'access']:
                    anomalies.append(f"Unusual command usage: {word}")
        
        if anomalies:
            return self._create_alert(
                AlertType.UNUSUAL_ACTIVITY,
                ThreatLevel.LOW,
                phone,
                "Behavioral anomaly detected",
                {"anomalies": anomalies}
            )
        
        return None
    
    def _update_profile(self, phone: str, message: str):
        """Update user behavior profile"""
        if phone not in self.user_profiles:
            self.user_profiles[phone] = UserBehaviorProfile(phone=phone)
        
        profile = self.user_profiles[phone]
        now = datetime.now()
        
        # Update typical hours
        hour = now.hour
        if hour not in profile.typical_hours and profile.total_messages > 20:
            # Only add if seen multiple times
            hour_count = sum(1 for ts in self.message_timestamps.get(phone, []) if ts.hour == hour)
            if hour_count > 3:
                profile.typical_hours.append(hour)
        
        # Update command frequencies
        words = message.lower().split()
        for word in words:
            if len(word) > 3:  # Skip short words
                profile.common_commands[word] = profile.common_commands.get(word, 0) + 1
        
        # Update totals
        profile.total_messages += 1
        profile.last_updated = now
        
        # Update trust score based on behavior
        if profile.total_messages > 100 and len(self._get_user_alerts(phone, hours=24)) == 0:
            profile.trust_score = min(1.0, profile.trust_score + 0.01)
    
    def _create_alert(
        self,
        alert_type: AlertType,
        threat_level: ThreatLevel,
        phone: str,
        message: str,
        details: Dict[str, Any]
    ) -> SecurityAlert:
        """Create and store a security alert"""
        alert = SecurityAlert(
            id=f"alert_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.alerts)}",
            alert_type=alert_type,
            threat_level=threat_level,
            phone=phone,
            message=message,
            details=details
        )
        
        self.alerts.append(alert)
        
        # Log based on threat level
        if threat_level == ThreatLevel.CRITICAL:
            logger.critical(f"🚨 CRITICAL ALERT: {message} - {phone}")
        elif threat_level == ThreatLevel.HIGH:
            logger.warning(f"⚠️ HIGH ALERT: {message} - {phone}")
        else:
            logger.info(f"🔔 Alert: {message} - {phone}")
        
        # Trigger callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")
        
        return alert
    
    def _get_user_alerts(self, phone: str, hours: int = 24) -> List[SecurityAlert]:
        """Get recent alerts for a user"""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [
            alert for alert in self.alerts
            if alert.phone == phone and alert.timestamp > cutoff
        ]
    
    def block_user(self, phone: str, reason: str = "Security violation"):
        """Block a user"""
        self.blocked_users.add(phone)
        logger.warning(f"🚫 User blocked: {phone} - {reason}")
        
        self._create_alert(
            AlertType.UNAUTHORIZED_ACCESS,
            ThreatLevel.HIGH,
            phone,
            f"User blocked: {reason}",
            {"reason": reason}
        )
    
    def unblock_user(self, phone: str):
        """Unblock a user"""
        self.blocked_users.discard(phone)
        self.failed_attempts[phone] = 0
        logger.info(f"✅ User unblocked: {phone}")
    
    def whitelist_user(self, phone: str):
        """Add user to whitelist"""
        self.whitelisted_users.add(phone)
        logger.info(f"✅ User whitelisted: {phone}")
    
    def get_security_status(self) -> Dict[str, Any]:
        """Get overall security status"""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)
        
        recent_alerts = [a for a in self.alerts if a.timestamp > hour_ago]
        daily_alerts = [a for a in self.alerts if a.timestamp > day_ago]
        
        critical_count = sum(1 for a in daily_alerts if a.threat_level == ThreatLevel.CRITICAL)
        high_count = sum(1 for a in daily_alerts if a.threat_level == ThreatLevel.HIGH)
        
        # Determine overall status
        if critical_count > 0:
            status = "CRITICAL"
            status_emoji = "🚨"
        elif high_count > 2:
            status = "ELEVATED"
            status_emoji = "⚠️"
        elif len(recent_alerts) > 5:
            status = "GUARDED"
            status_emoji = "🔔"
        else:
            status = "SECURE"
            status_emoji = "🛡️"
        
        return {
            "status": status,
            "status_emoji": status_emoji,
            "timestamp": now.isoformat(),
            "alerts_last_hour": len(recent_alerts),
            "alerts_last_24h": len(daily_alerts),
            "critical_alerts": critical_count,
            "high_alerts": high_count,
            "blocked_users": len(self.blocked_users),
            "whitelisted_users": len(self.whitelisted_users),
            "active_users": len(self.user_profiles),
            "total_alerts": len(self.alerts)
        }
    
    def get_security_report(self) -> str:
        """Generate human-readable security report"""
        status = self.get_security_status()
        
        report = [f"{status['status_emoji']} **JARVIS Security Report**\n"]
        report.append(f"**Status**: {status['status']}")
        report.append(f"**Time**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        
        report.append("**Activity (24h)**:")
        report.append(f"  • Total alerts: {status['alerts_last_24h']}")
        report.append(f"  • Critical: {status['critical_alerts']}")
        report.append(f"  • High priority: {status['high_alerts']}")
        report.append(f"  • Active users: {status['active_users']}")
        
        if status['blocked_users'] > 0:
            report.append(f"\n⚠️ **Blocked users**: {status['blocked_users']}")
        
        # Recent critical alerts
        critical_alerts = [a for a in self.alerts[-10:] if a.threat_level == ThreatLevel.CRITICAL]
        if critical_alerts:
            report.append("\n🚨 **Recent Critical Alerts**:")
            for alert in critical_alerts[-3:]:
                report.append(f"  • {alert.message}")
        
        report.append("\n✅ All systems monitored")
        
        return '\n'.join(report)
    
    def register_alert_callback(self, callback: callable):
        """Register callback for new alerts"""
        self.alert_callbacks.append(callback)
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert"""
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                return True
        return False
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert"""
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.resolved = True
                return True
        return False


# Global instance
security_monitor = SecurityMonitor()


def check_message_security(phone: str, message: str) -> Tuple[bool, Optional[str]]:
    """
    Convenience function to check message security.
    
    Returns:
        Tuple of (is_allowed, warning_message_if_any)
    """
    is_safe, alert = security_monitor.analyze_message(phone, message)
    
    if not is_safe:
        return False, alert.message if alert else "Security check failed"
    
    if alert and alert.threat_level in [ThreatLevel.MEDIUM, ThreatLevel.HIGH]:
        return True, f"⚠️ Security notice: {alert.message}"
    
    return True, None
