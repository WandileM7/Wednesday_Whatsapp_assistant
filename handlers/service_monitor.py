"""
Background Service Monitor for Wednesday WhatsApp Assistant

Provides comprehensive service monitoring and auto-recovery:
- Health monitoring for all services
- Automatic restart of failed services
- Performance metrics tracking
- Alert system for service issues
- Keep-alive ping system between services
"""

import logging
import threading
import time
import requests
import psutil
import json
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from database import db_manager
import os
from google import genai
from config import GEMINI_API_KEY
from handlers.google_auth import load_tokens_from_env, get_credentials_path, validate_credentials_file
from flask import has_request_context

logger = logging.getLogger(__name__)

GENERATION_MODEL = "gemini-2.5-flash"

try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
except Exception as e:
    logger.warning(f"Gemini client unavailable for service monitor: {e}")
    gemini_client = None

class ServiceMonitor:
    """Advanced service monitoring and recovery system"""
    
    def __init__(self):
        self.services = {}
        self.monitoring_thread = None
        self.running = False
        self.check_interval = 60  # Check every minute
        self.alert_callbacks = []
        self.service_stats = {}
        self.recovery_attempts = {}
        self.max_recovery_attempts = 3
        
        self._register_default_services()
    
    def _register_default_services(self):
        """Register default services to monitor"""
        
        # WhatsApp Service
        self.register_service(
            name="whatsapp_service",
            health_check_url="http://localhost:3000/health",
            critical=True,
            restart_command=None,  # No docker restart available in production
            description="WhatsApp messaging service"
        )
        
        # Gemini AI Service (check if responding)
        self.register_service(
            name="gemini_ai",
            health_check_function=self._check_gemini_health,
            critical=True,
            description="Google Gemini AI service"
        )
        
        # Database Service
        self.register_service(
            name="database",
            health_check_function=self._check_database_health,
            critical=True,
            description="SQLite database service"
        )
        
        # Media Generation Service
        self.register_service(
            name="media_generation",
            health_check_function=self._check_media_service_health,
            critical=False,
            description="AI media generation service"
        )
        
        # Google Services
        self.register_service(
            name="google_services",
            health_check_function=self._check_google_services_health,
            critical=False,
            description="Google APIs (Gmail, Calendar, etc.)"
        )
        
        # Spotify Service
        self.register_service(
            name="spotify",
            health_check_function=self._check_spotify_health,
            critical=False,
            description="Spotify music service"
        )
    
    def register_service(self, name: str, health_check_url: str = None, 
                        health_check_function: Callable = None,
                        critical: bool = False, restart_command: str = None,
                        description: str = ""):
        """Register a service for monitoring"""
        
        self.services[name] = {
            'name': name,
            'health_check_url': health_check_url,
            'health_check_function': health_check_function,
            'critical': critical,
            'restart_command': restart_command,
            'description': description,
            'last_check': None,
            'status': 'unknown',
            'response_time': None,
            'error_count': 0,
            'last_error': None,
            'uptime_start': datetime.now()
        }
        
        self.service_stats[name] = {
            'total_checks': 0,
            'successful_checks': 0,
            'failed_checks': 0,
            'avg_response_time': 0,
            'downtime_minutes': 0
        }
        
        logger.info(f"Registered service for monitoring: {name}")
    
    def start_monitoring(self):
        """Start the background monitoring service"""
        if self.running:
            logger.warning("Service monitoring already running")
            return
        
        self.running = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_worker, daemon=True)
        self.monitoring_thread.start()
        logger.info("Service monitoring started")
    
    def stop_monitoring(self):
        """Stop the background monitoring service"""
        self.running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=10)
        logger.info("Service monitoring stopped")
    
    def _monitoring_worker(self):
        """Background worker for monitoring services"""
        while self.running:
            try:
                self._check_all_services()
                self._update_system_metrics()
                self._save_monitoring_data()
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Monitoring worker error: {e}")
                time.sleep(30)  # Wait shorter time on error
    
    def _check_all_services(self):
        """Check health of all registered services"""
        for service_name, service_config in self.services.items():
            try:
                self._check_service_health(service_name, service_config)
            except Exception as e:
                logger.error(f"Error checking service {service_name}: {e}")
    
    def _check_service_health(self, service_name: str, service_config: Dict):
        """Check health of a specific service"""
        start_time = time.time()
        
        try:
            # Update stats
            self.service_stats[service_name]['total_checks'] += 1
            
            # Perform health check
            if service_config.get('health_check_url'):
                status, error = self._check_url_health(service_config['health_check_url'])
            elif service_config.get('health_check_function'):
                status, error = service_config['health_check_function']()
            else:
                status, error = False, "No health check method configured"
            
            # Calculate response time
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            # Update service status
            service_config['last_check'] = datetime.now()
            service_config['response_time'] = response_time
            
            if status:
                service_config['status'] = 'healthy'
                service_config['error_count'] = 0
                service_config['last_error'] = None
                self.service_stats[service_name]['successful_checks'] += 1
                
                # Update average response time
                stats = self.service_stats[service_name]
                total_response_time = stats['avg_response_time'] * (stats['successful_checks'] - 1)
                stats['avg_response_time'] = (total_response_time + response_time) / stats['successful_checks']
                
                # Reset recovery attempts on success
                if service_name in self.recovery_attempts:
                    del self.recovery_attempts[service_name]
                
            else:
                service_config['status'] = 'unhealthy'
                service_config['error_count'] += 1
                service_config['last_error'] = error
                self.service_stats[service_name]['failed_checks'] += 1
                
                # Attempt recovery for critical services
                if service_config['critical']:
                    self._attempt_service_recovery(service_name, service_config)
                
                # Send alert
                self._send_service_alert(service_name, service_config, error)
                
        except Exception as e:
            service_config['status'] = 'error'
            service_config['last_error'] = str(e)
            service_config['error_count'] += 1
            self.service_stats[service_name]['failed_checks'] += 1
            
            logger.error(f"Health check failed for {service_name}: {e}")
    
    def _check_url_health(self, url: str) -> tuple:
        """Check health via HTTP endpoint"""
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return True, None
            else:
                return False, f"HTTP {response.status_code}"
                
        except requests.exceptions.ConnectionError:
            return False, "Connection refused"
        except requests.exceptions.Timeout:
            return False, "Request timeout"
        except Exception as e:
            return False, str(e)
    
    def _check_gemini_health(self) -> tuple:
        """Check Gemini AI service health - lightweight check without API call"""
        try:
            if not GEMINI_API_KEY or GEMINI_API_KEY == "test_key_123":
                return False, "No valid API key configured"
            
            # Just verify the API key is configured and client can be created
            # Don't make actual API calls to avoid burning quota!
            if gemini_client:
                return True, None
            return False, "Gemini client not initialized"
                
        except Exception as e:
            return False, str(e)
    
    def _check_database_health(self) -> tuple:
        """Check database health"""
        try:
            # Simple database operation
            stats = db_manager.get_database_stats()
            if stats:
                return True, None
            else:
                return False, "Database not responding"
                
        except Exception as e:
            return False, str(e)
    
    def _check_media_service_health(self) -> tuple:
        """Check media generation service health"""
        try:
            from handlers.media_generator import media_generator
            status = media_generator.get_service_status()
            
            if status.get('openai_available') or status.get('stability_available'):
                apis = []
                if status.get('openai_available'):
                    apis.append('OpenAI')
                if status.get('stability_available'):
                    apis.append('Stability')
                return True, f"Available APIs: {', '.join(apis)}"
            else:
                # Not critical - just informational
                return False, "Media generation APIs not configured (OPENAI_API_KEY or STABILITY_API_KEY required)"
                
        except Exception as e:
            return False, str(e)
    
    def _check_google_services_health(self) -> tuple:
        """Check Google services health"""
        try:
            # Avoid Flask session access when no request context is active
            if not has_request_context():
                creds = load_tokens_from_env()
            else:
                from handlers.google_auth import load_credentials
                creds = load_credentials()

            if creds and creds.valid:
                return True, None

            # If no valid creds, check if service account file exists to guide setup
            creds_path = get_credentials_path()
            if creds_path:
                is_valid, msg = validate_credentials_file(creds_path)
                if not is_valid:
                    return False, f"Credentials file invalid: {msg}"
                return False, "Google authentication not authorized (run /authorize)"

            return False, "Google authentication not configured"
                
        except Exception as e:
            return False, str(e)
    
    def _check_spotify_health(self) -> tuple:
        """Check Spotify service health"""
        try:
            from handlers.spotify import spotify_service
            
            # Use the service's authentication check method
            if spotify_service.is_authenticated():
                # Try a simple API call to verify connection
                try:
                    user = spotify_service.sp.current_user()
                    if user:
                        return True, f"Authenticated as {user.get('display_name', user.get('id', 'Unknown'))}"
                except Exception as api_error:
                    return False, f"Authentication valid but API error: {str(api_error)}"
            
            return False, "Spotify not authenticated"
            
        except Exception as e:
            return False, str(e)
    
    def _attempt_service_recovery(self, service_name: str, service_config: Dict):
        """Attempt to recover a failed service"""
        try:
            # Track recovery attempts
            if service_name not in self.recovery_attempts:
                self.recovery_attempts[service_name] = 0
            
            self.recovery_attempts[service_name] += 1
            
            if self.recovery_attempts[service_name] > self.max_recovery_attempts:
                logger.error(f"Max recovery attempts reached for {service_name}")
                return
            
            logger.info(f"Attempting recovery for service {service_name} (attempt {self.recovery_attempts[service_name]})")
            
            # Execute recovery command if configured
            if service_config.get('restart_command'):
                import subprocess
                result = subprocess.run(
                    service_config['restart_command'], 
                    shell=True, 
                    capture_output=True, 
                    text=True
                )
                
                if result.returncode == 0:
                    logger.info(f"Recovery command executed successfully for {service_name}")
                else:
                    logger.error(f"Recovery command failed for {service_name}: {result.stderr}")
            
            # Service-specific recovery logic
            if service_name == "database":
                self._recover_database_service()
            elif service_name == "gemini_ai":
                self._recover_gemini_service()
            
        except Exception as e:
            logger.error(f"Service recovery failed for {service_name}: {e}")
    
    def _recover_database_service(self):
        """Attempt to recover database service"""
        try:
            # Reinitialize database
            db_manager.init_database()
            logger.info("Database service recovery attempted")
            
        except Exception as e:
            logger.error(f"Database recovery failed: {e}")
    
    def _recover_gemini_service(self):
        """Attempt to recover Gemini service"""
        try:
            # Reinitialize Gemini client
            global gemini_client

            if GEMINI_API_KEY and GEMINI_API_KEY != "test_key_123":
                gemini_client = genai.Client(api_key=GEMINI_API_KEY)
                logger.info("Gemini service recovery attempted")
            
        except Exception as e:
            logger.error(f"Gemini recovery failed: {e}")
    
    def _send_service_alert(self, service_name: str, service_config: Dict, error: str):
        """Send alert about service failure"""
        try:
            alert_data = {
                'service': service_name,
                'status': service_config['status'],
                'error': error,
                'error_count': service_config['error_count'],
                'critical': service_config['critical'],
                'timestamp': datetime.now().isoformat()
            }
            
            # Call registered alert callbacks
            for callback in self.alert_callbacks:
                try:
                    callback(alert_data)
                except Exception as e:
                    logger.error(f"Alert callback failed: {e}")
            
            # Log the alert with appropriate severity
            if service_config['critical']:
                logger.warning(f"🔴 Critical service alert: {service_name} - {error}")
            else:
                logger.info(f"🟡 Service notice: {service_name} - {error}")
            
        except Exception as e:
            logger.error(f"Failed to send service alert: {e}")
    
    def _update_system_metrics(self):
        """Update system performance metrics"""
        try:
            # CPU and memory usage
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            system_metrics = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_mb': memory.available / (1024 * 1024),
                'disk_percent': disk.percent,
                'disk_free_gb': disk.free / (1024 * 1024 * 1024),
                'timestamp': datetime.now().isoformat()
            }
            
            # Save to database
            db_manager.set_system_state('system_metrics', system_metrics)
            
            # Alert on high resource usage
            if cpu_percent > 80:
                self._send_resource_alert('cpu', cpu_percent)
            if memory.percent > 85:
                self._send_resource_alert('memory', memory.percent)
            if disk.percent > 90:
                self._send_resource_alert('disk', disk.percent)
                
        except Exception as e:
            logger.error(f"Failed to update system metrics: {e}")
    
    def _send_resource_alert(self, resource_type: str, usage_percent: float):
        """Send alert about high resource usage"""
        try:
            alert_data = {
                'type': 'resource_alert',
                'resource': resource_type,
                'usage_percent': usage_percent,
                'timestamp': datetime.now().isoformat()
            }
            
            for callback in self.alert_callbacks:
                try:
                    callback(alert_data)
                except Exception as e:
                    logger.error(f"Resource alert callback failed: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to send resource alert: {e}")
    
    def _save_monitoring_data(self):
        """Save monitoring data to database"""
        try:
            # Create a serializable copy of services data
            serializable_services = {}
            for name, service in self.services.items():
                serializable_services[name] = {
                    'name': service['name'],
                    'health_check_url': service.get('health_check_url'),
                    'critical': service['critical'],
                    'restart_command': service.get('restart_command'),
                    'description': service['description'],
                    'last_check': service['last_check'].isoformat() if service['last_check'] else None,
                    'status': service['status'],
                    'response_time': service['response_time'],
                    'error_count': service['error_count'],
                    'last_error': service['last_error'],
                    'uptime_start': service['uptime_start'].isoformat() if service['uptime_start'] else None
                }
            
            monitoring_data = {
                'services': serializable_services,
                'stats': self.service_stats,
                'timestamp': datetime.now().isoformat()
            }
            
            db_manager.set_system_state('monitoring_data', monitoring_data)
            
        except Exception as e:
            logger.error(f"Failed to save monitoring data: {e}")
    
    def register_alert_callback(self, callback: Callable):
        """Register callback for service alerts"""
        self.alert_callbacks.append(callback)
        logger.info("Alert callback registered")
    
    def get_service_status(self, service_name: str = None) -> Dict:
        """Get status of specific service or all services"""
        if service_name:
            return {
                'service': self.services.get(service_name, {}),
                'stats': self.service_stats.get(service_name, {})
            }
        else:
            return {
                'services': self.services,
                'stats': self.service_stats,
                'monitoring_active': self.running,
                'total_services': len(self.services)
            }
    
    def get_system_health_summary(self) -> Dict:
        """Get overall system health summary"""
        try:
            healthy_services = sum(1 for service in self.services.values() if service['status'] == 'healthy')
            critical_services_down = sum(1 for service in self.services.values() 
                                       if service['critical'] and service['status'] != 'healthy')
            
            # Get system metrics
            system_metrics = db_manager.get_system_state('system_metrics', {})
            
            return {
                'overall_status': 'healthy' if critical_services_down == 0 else 'degraded',
                'healthy_services': healthy_services,
                'total_services': len(self.services),
                'critical_services_down': critical_services_down,
                'system_metrics': system_metrics,
                'monitoring_active': self.running,
                'last_check': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get health summary: {e}")
            return {'error': str(e)}
    
    def ping_service(self, service_name: str, endpoint: str = None) -> Dict:
        """Manually ping a specific service"""
        try:
            if service_name not in self.services:
                return {'error': f'Service {service_name} not registered'}
            
            service_config = self.services[service_name]
            
            if endpoint:
                # Ping custom endpoint
                start_time = time.time()
                try:
                    response = requests.get(endpoint, timeout=5)
                    response_time = (time.time() - start_time) * 1000
                    return {
                        'service': service_name,
                        'endpoint': endpoint,
                        'status': 'reachable' if response.status_code == 200 else 'unreachable',
                        'status_code': response.status_code,
                        'response_time_ms': response_time
                    }
                except Exception as e:
                    return {
                        'service': service_name,
                        'endpoint': endpoint,
                        'status': 'unreachable',
                        'error': str(e)
                    }
            else:
                # Use configured health check
                self._check_service_health(service_name, service_config)
                return {
                    'service': service_name,
                    'status': service_config['status'],
                    'response_time_ms': service_config['response_time'],
                    'last_error': service_config['last_error']
                }
                
        except Exception as e:
            return {'error': str(e)}

# Global service monitor instance
service_monitor = ServiceMonitor()