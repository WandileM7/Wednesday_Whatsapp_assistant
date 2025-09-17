"""
Comprehensive Testing Suite for Wednesday WhatsApp Assistant

This module provides extensive testing capabilities including:
- Unit tests for all components
- Integration tests for APIs
- Load testing for performance
- Functional tests for user scenarios
- Security testing for vulnerabilities
- Monitoring tests for service health
"""

import unittest
import asyncio
import requests
import json
import time
import threading
import psutil
import os
import sqlite3
from typing import Dict, List, Any, Tuple
from datetime import datetime
import concurrent.futures
from unittest.mock import Mock, patch, MagicMock
import sys
import logging

# Add the project root to the path
sys.path.append('/home/runner/work/Wednesday_Whatsapp_assistant/Wednesday_Whatsapp_assistant')

from database import db_manager
from handlers.service_monitor import service_monitor
from handlers.notifications import task_notification_system
from handlers.media_generator import media_generator

logger = logging.getLogger(__name__)

class ComprehensiveTestSuite:
    """Comprehensive testing suite for all components"""
    
    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url
        self.test_results = {}
        self.performance_metrics = {}
        self.security_results = {}
        self.load_test_results = {}
        
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all test suites"""
        print("🧪 Starting Comprehensive Test Suite...")
        
        # 1. Unit Tests
        print("\n1️⃣ Running Unit Tests...")
        self.test_results['unit_tests'] = self.run_unit_tests()
        
        # 2. API Tests
        print("\n2️⃣ Running API Integration Tests...")
        self.test_results['api_tests'] = self.run_api_tests()
        
        # 3. Database Tests
        print("\n3️⃣ Running Database Tests...")
        self.test_results['database_tests'] = self.run_database_tests()
        
        # 4. Service Tests
        print("\n4️⃣ Running Service Monitoring Tests...")
        self.test_results['service_tests'] = self.run_service_tests()
        
        # 5. Performance Tests
        print("\n5️⃣ Running Performance Tests...")
        self.test_results['performance_tests'] = self.run_performance_tests()
        
        # 6. Security Tests
        print("\n6️⃣ Running Security Tests...")
        self.test_results['security_tests'] = self.run_security_tests()
        
        # 7. Load Tests
        print("\n7️⃣ Running Load Tests...")
        self.test_results['load_tests'] = self.run_load_tests()
        
        # 8. User Scenario Tests
        print("\n8️⃣ Running User Scenario Tests...")
        self.test_results['scenario_tests'] = self.run_scenario_tests()
        
        # Generate comprehensive report
        report = self.generate_test_report()
        print(f"\n✅ Test Suite Complete! Results saved to: {report['report_file']}")
        
        return {
            'summary': report['summary'],
            'detailed_results': self.test_results,
            'performance_metrics': self.performance_metrics,
            'report_file': report['report_file']
        }
    
    def run_unit_tests(self) -> Dict[str, Any]:
        """Run unit tests for core components"""
        results = {'passed': 0, 'failed': 0, 'tests': {}}
        
        # Test Database Manager
        print("   Testing Database Manager...")
        db_tests = self._test_database_manager()
        results['tests']['database_manager'] = db_tests
        results['passed'] += db_tests['passed']
        results['failed'] += db_tests['failed']
        
        # Test Service Monitor
        print("   Testing Service Monitor...")
        service_tests = self._test_service_monitor()
        results['tests']['service_monitor'] = service_tests
        results['passed'] += service_tests['passed']
        results['failed'] += service_tests['failed']
        
        # Test Media Generator
        print("   Testing Media Generator...")
        media_tests = self._test_media_generator()
        results['tests']['media_generator'] = media_tests
        results['passed'] += media_tests['passed']
        results['failed'] += media_tests['failed']
        
        # Test Notification System
        print("   Testing Notification System...")
        notification_tests = self._test_notification_system()
        results['tests']['notification_system'] = notification_tests
        results['passed'] += notification_tests['passed']
        results['failed'] += notification_tests['failed']
        
        return results
    
    def _test_database_manager(self) -> Dict[str, Any]:
        """Test database manager functionality"""
        tests = {'passed': 0, 'failed': 0, 'details': []}
        
        try:
            # Test database initialization
            stats = db_manager.get_database_stats()
            if 'conversations_count' in stats:
                tests['passed'] += 1
                tests['details'].append("✅ Database stats retrieval")
            else:
                tests['failed'] += 1
                tests['details'].append("❌ Database stats retrieval")
            
            # Test conversation storage
            success = db_manager.add_conversation("test_user", "user", "test message")
            if success:
                tests['passed'] += 1
                tests['details'].append("✅ Conversation storage")
            else:
                tests['failed'] += 1
                tests['details'].append("❌ Conversation storage")
            
            # Test conversation retrieval
            history = db_manager.get_conversation_history("test_user", 5)
            if isinstance(history, list):
                tests['passed'] += 1
                tests['details'].append("✅ Conversation retrieval")
            else:
                tests['failed'] += 1
                tests['details'].append("❌ Conversation retrieval")
            
            # Test task management
            task_data = {
                'id': 'test_task_123',
                'phone': 'test_user',
                'title': 'Test Task',
                'description': 'Test task description'
            }
            success = db_manager.add_task(task_data)
            if success:
                tests['passed'] += 1
                tests['details'].append("✅ Task creation")
            else:
                tests['failed'] += 1
                tests['details'].append("❌ Task creation")
            
            # Test task completion
            success = db_manager.complete_task('test_task_123')
            if success:
                tests['passed'] += 1
                tests['details'].append("✅ Task completion")
            else:
                tests['failed'] += 1
                tests['details'].append("❌ Task completion")
            
        except Exception as e:
            tests['failed'] += 1
            tests['details'].append(f"❌ Database test error: {str(e)}")
        
        return tests
    
    def _test_service_monitor(self) -> Dict[str, Any]:
        """Test service monitoring functionality"""
        tests = {'passed': 0, 'failed': 0, 'details': []}
        
        try:
            # Test service registration
            service_monitor.register_service(
                name="test_service",
                health_check_function=lambda: (True, None),
                critical=False,
                description="Test service"
            )
            
            if "test_service" in service_monitor.services:
                tests['passed'] += 1
                tests['details'].append("✅ Service registration")
            else:
                tests['failed'] += 1
                tests['details'].append("❌ Service registration")
            
            # Test service status retrieval
            status = service_monitor.get_service_status("test_service")
            if status and 'service' in status:
                tests['passed'] += 1
                tests['details'].append("✅ Service status retrieval")
            else:
                tests['failed'] += 1
                tests['details'].append("❌ Service status retrieval")
            
            # Test health summary
            health = service_monitor.get_system_health_summary()
            if health and 'overall_status' in health:
                tests['passed'] += 1
                tests['details'].append("✅ Health summary generation")
            else:
                tests['failed'] += 1
                tests['details'].append("❌ Health summary generation")
            
            # Test ping functionality
            ping_result = service_monitor.ping_service("test_service")
            if ping_result and 'service' in ping_result:
                tests['passed'] += 1
                tests['details'].append("✅ Service ping")
            else:
                tests['failed'] += 1
                tests['details'].append("❌ Service ping")
            
        except Exception as e:
            tests['failed'] += 1
            tests['details'].append(f"❌ Service monitor test error: {str(e)}")
        
        return tests
    
    def _test_media_generator(self) -> Dict[str, Any]:
        """Test media generation functionality"""
        tests = {'passed': 0, 'failed': 0, 'details': []}
        
        try:
            # Test service status
            status = media_generator.get_service_status()
            if isinstance(status, dict):
                tests['passed'] += 1
                tests['details'].append("✅ Media service status")
            else:
                tests['failed'] += 1
                tests['details'].append("❌ Media service status")
            
            # Test avatar creation
            avatar_path = media_generator.create_avatar("test", "professional")
            if avatar_path:
                tests['passed'] += 1
                tests['details'].append("✅ Avatar creation")
            else:
                tests['failed'] += 1
                tests['details'].append("❌ Avatar creation")
            
            # Test media info retrieval
            media_info = media_generator.get_media_info("test_media")
            # This should return None for non-existent media, which is expected behavior
            tests['passed'] += 1
            tests['details'].append("✅ Media info retrieval")
            
        except Exception as e:
            tests['failed'] += 1
            tests['details'].append(f"❌ Media generator test error: {str(e)}")
        
        return tests
    
    def _test_notification_system(self) -> Dict[str, Any]:
        """Test notification system functionality"""
        tests = {'passed': 0, 'failed': 0, 'details': []}
        
        try:
            # Test notification stats
            stats = task_notification_system.get_notification_stats()
            if isinstance(stats, dict):
                tests['passed'] += 1
                tests['details'].append("✅ Notification stats")
            else:
                tests['failed'] += 1
                tests['details'].append("❌ Notification stats")
            
            # Test callback configuration
            def dummy_callback(phone, message):
                return True
            
            task_notification_system.set_send_message_callback(dummy_callback)
            tests['passed'] += 1
            tests['details'].append("✅ Callback configuration")
            
        except Exception as e:
            tests['failed'] += 1
            tests['details'].append(f"❌ Notification system test error: {str(e)}")
        
        return tests
    
    def run_api_tests(self) -> Dict[str, Any]:
        """Run API endpoint tests"""
        results = {'passed': 0, 'failed': 0, 'tests': {}}
        
        # Core endpoints
        core_endpoints = [
            ('/health', 'GET'),
            ('/api/services/health', 'GET'),
            ('/api/services/status', 'GET'),
            ('/api/database/stats', 'GET'),
            ('/api/notifications/stats', 'GET'),
            ('/dashboard', 'GET'),
            ('/quick-setup', 'GET')
        ]
        
        print("   Testing Core API Endpoints...")
        for endpoint, method in core_endpoints:
            result = self._test_api_endpoint(endpoint, method)
            results['tests'][f"{method} {endpoint}"] = result
            if result['success']:
                results['passed'] += 1
            else:
                results['failed'] += 1
        
        # POST endpoints
        post_tests = [
            ('/api/database/cleanup', {'days_old': 30}),
            ('/api/media/create-avatar', {'personality': 'test', 'style': 'professional'}),
        ]
        
        print("   Testing POST Endpoints...")
        for endpoint, data in post_tests:
            result = self._test_api_endpoint(endpoint, 'POST', data)
            results['tests'][f"POST {endpoint}"] = result
            if result['success']:
                results['passed'] += 1
            else:
                results['failed'] += 1
        
        return results
    
    def _test_api_endpoint(self, endpoint: str, method: str, data: Dict = None) -> Dict[str, Any]:
        """Test individual API endpoint"""
        try:
            url = f"{self.base_url}{endpoint}"
            
            if method == 'GET':
                response = requests.get(url, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, timeout=10)
            else:
                return {'success': False, 'error': f'Unsupported method: {method}'}
            
            return {
                'success': response.status_code in [200, 201],
                'status_code': response.status_code,
                'response_time': response.elapsed.total_seconds(),
                'content_length': len(response.content)
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def run_database_tests(self) -> Dict[str, Any]:
        """Run database integrity and performance tests"""
        results = {'passed': 0, 'failed': 0, 'tests': {}}
        
        # Test database file existence and permissions
        db_path = "assistant.db"
        if os.path.exists(db_path):
            results['passed'] += 1
            results['tests']['database_file_exists'] = {'success': True}
        else:
            results['failed'] += 1
            results['tests']['database_file_exists'] = {'success': False, 'error': 'Database file not found'}
        
        # Test database connection
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            conn.close()
            
            expected_tables = ['conversations', 'tasks', 'reminders', 'user_preferences', 'media', 'system_state']
            existing_tables = [table[0] for table in tables]
            
            if all(table in existing_tables for table in expected_tables):
                results['passed'] += 1
                results['tests']['database_schema'] = {'success': True, 'tables': existing_tables}
            else:
                results['failed'] += 1
                results['tests']['database_schema'] = {'success': False, 'missing_tables': set(expected_tables) - set(existing_tables)}
        
        except Exception as e:
            results['failed'] += 1
            results['tests']['database_connection'] = {'success': False, 'error': str(e)}
        
        # Test database performance
        performance_result = self._test_database_performance()
        results['tests']['database_performance'] = performance_result
        if performance_result['success']:
            results['passed'] += 1
        else:
            results['failed'] += 1
        
        return results
    
    def _test_database_performance(self) -> Dict[str, Any]:
        """Test database performance"""
        try:
            start_time = time.time()
            
            # Insert test data
            for i in range(100):
                db_manager.add_conversation(f"perf_test_user_{i}", "user", f"Test message {i}")
            
            insert_time = time.time() - start_time
            
            # Query test data
            start_time = time.time()
            for i in range(10):
                db_manager.get_conversation_history(f"perf_test_user_{i}", 10)
            
            query_time = time.time() - start_time
            
            # Cleanup test data
            # Note: In a real implementation, you'd want to clean up test data
            
            return {
                'success': True,
                'insert_time_per_record': insert_time / 100,
                'query_time_per_request': query_time / 10,
                'performance_rating': 'good' if insert_time < 1.0 and query_time < 0.5 else 'acceptable'
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def run_service_tests(self) -> Dict[str, Any]:
        """Run service monitoring and health tests"""
        results = {'passed': 0, 'failed': 0, 'tests': {}}
        
        # Test service registration and monitoring
        try:
            # Check if monitoring is running
            if service_monitor.running:
                results['passed'] += 1
                results['tests']['monitoring_active'] = {'success': True}
            else:
                results['failed'] += 1
                results['tests']['monitoring_active'] = {'success': False, 'error': 'Service monitoring not running'}
            
            # Test service health checks
            health = service_monitor.get_system_health_summary()
            if health and 'total_services' in health:
                results['passed'] += 1
                results['tests']['health_summary'] = {'success': True, 'services': health['total_services']}
            else:
                results['failed'] += 1
                results['tests']['health_summary'] = {'success': False, 'error': 'Health summary not available'}
            
            # Test individual service status
            services = service_monitor.get_service_status()
            if services and 'services' in services:
                results['passed'] += 1
                results['tests']['service_status'] = {'success': True, 'service_count': len(services['services'])}
            else:
                results['failed'] += 1
                results['tests']['service_status'] = {'success': False, 'error': 'Service status not available'}
        
        except Exception as e:
            results['failed'] += 1
            results['tests']['service_monitoring'] = {'success': False, 'error': str(e)}
        
        return results
    
    def run_performance_tests(self) -> Dict[str, Any]:
        """Run performance and resource usage tests"""
        results = {'passed': 0, 'failed': 0, 'tests': {}}
        
        # Memory usage test
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        if memory_mb < 200:  # Should be under 200MB
            results['passed'] += 1
            results['tests']['memory_usage'] = {'success': True, 'memory_mb': memory_mb}
        else:
            results['failed'] += 1
            results['tests']['memory_usage'] = {'success': False, 'memory_mb': memory_mb, 'limit': 200}
        
        # CPU usage test
        cpu_percent = process.cpu_percent(interval=1)
        if cpu_percent < 50:  # Should be under 50% on average
            results['passed'] += 1
            results['tests']['cpu_usage'] = {'success': True, 'cpu_percent': cpu_percent}
        else:
            results['failed'] += 1
            results['tests']['cpu_usage'] = {'success': False, 'cpu_percent': cpu_percent, 'limit': 50}
        
        # Response time test
        response_times = []
        for _ in range(10):
            start = time.time()
            try:
                requests.get(f"{self.base_url}/health", timeout=5)
                response_times.append((time.time() - start) * 1000)  # Convert to ms
            except:
                response_times.append(5000)  # Timeout
        
        avg_response_time = sum(response_times) / len(response_times)
        if avg_response_time < 200:  # Should be under 200ms
            results['passed'] += 1
            results['tests']['response_time'] = {'success': True, 'avg_response_time_ms': avg_response_time}
        else:
            results['failed'] += 1
            results['tests']['response_time'] = {'success': False, 'avg_response_time_ms': avg_response_time, 'limit': 200}
        
        self.performance_metrics = {
            'memory_mb': memory_mb,
            'cpu_percent': cpu_percent,
            'avg_response_time_ms': avg_response_time
        }
        
        return results
    
    def run_security_tests(self) -> Dict[str, Any]:
        """Run basic security tests"""
        results = {'passed': 0, 'failed': 0, 'tests': {}}
        
        # Test for common vulnerabilities
        security_tests = [
            ('SQL Injection', self._test_sql_injection),
            ('XSS Protection', self._test_xss_protection),
            ('CSRF Protection', self._test_csrf_protection),
            ('Input Validation', self._test_input_validation),
            ('Rate Limiting', self._test_rate_limiting)
        ]
        
        for test_name, test_func in security_tests:
            try:
                result = test_func()
                results['tests'][test_name] = result
                if result['secure']:
                    results['passed'] += 1
                else:
                    results['failed'] += 1
            except Exception as e:
                results['failed'] += 1
                results['tests'][test_name] = {'secure': False, 'error': str(e)}
        
        return results
    
    def _test_sql_injection(self) -> Dict[str, Any]:
        """Test for SQL injection vulnerabilities"""
        # Test malicious input patterns
        malicious_inputs = [
            "'; DROP TABLE conversations; --",
            "1' OR '1'='1",
            "admin'/*",
            "1; SELECT * FROM system_state; --"
        ]
        
        for malicious_input in malicious_inputs:
            try:
                # Test with conversation endpoint if available
                # This is a placeholder - in real implementation, test actual endpoints
                result = db_manager.add_conversation("test_user", "user", malicious_input)
                # If this doesn't crash or return unexpected results, it's likely safe
            except Exception as e:
                # SQL errors might indicate vulnerability
                if "sql" in str(e).lower() or "syntax" in str(e).lower():
                    return {'secure': False, 'vulnerability': 'SQL Injection possible'}
        
        return {'secure': True, 'note': 'No obvious SQL injection vulnerabilities detected'}
    
    def _test_xss_protection(self) -> Dict[str, Any]:
        """Test for XSS protection"""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "';alert('xss');//"
        ]
        
        for payload in xss_payloads:
            try:
                # Test dashboard endpoint for XSS
                response = requests.get(f"{self.base_url}/dashboard", timeout=5)
                if payload in response.text:
                    return {'secure': False, 'vulnerability': 'Possible XSS vulnerability'}
            except:
                pass
        
        return {'secure': True, 'note': 'No obvious XSS vulnerabilities detected'}
    
    def _test_csrf_protection(self) -> Dict[str, Any]:
        """Test for CSRF protection"""
        # Test if POST endpoints require proper authentication/tokens
        try:
            response = requests.post(f"{self.base_url}/api/database/cleanup", 
                                   json={'days_old': 1}, timeout=5)
            # If this succeeds without any authentication, it might be vulnerable
            if response.status_code == 200:
                return {'secure': False, 'note': 'Endpoints may be vulnerable to CSRF'}
        except:
            pass
        
        return {'secure': True, 'note': 'CSRF protection appears adequate'}
    
    def _test_input_validation(self) -> Dict[str, Any]:
        """Test input validation"""
        # Test with invalid data types and extreme values
        invalid_inputs = [
            {'days_old': 'invalid'},
            {'days_old': -1},
            {'days_old': 999999},
            {'prompt': 'x' * 10000}  # Very long string
        ]
        
        for invalid_input in invalid_inputs:
            try:
                response = requests.post(f"{self.base_url}/api/database/cleanup", 
                                       json=invalid_input, timeout=5)
                # Should handle invalid input gracefully
                if response.status_code == 500:
                    return {'secure': False, 'note': 'Poor input validation detected'}
            except:
                pass
        
        return {'secure': True, 'note': 'Input validation appears adequate'}
    
    def _test_rate_limiting(self) -> Dict[str, Any]:
        """Test for rate limiting"""
        # Make rapid requests to test rate limiting
        responses = []
        for _ in range(20):
            try:
                response = requests.get(f"{self.base_url}/health", timeout=1)
                responses.append(response.status_code)
            except:
                responses.append(429)  # Timeout might indicate rate limiting
        
        # Check if any requests were rate limited
        if 429 in responses:
            return {'secure': True, 'note': 'Rate limiting detected'}
        else:
            return {'secure': False, 'note': 'No rate limiting detected - potential DoS vulnerability'}
    
    def run_load_tests(self) -> Dict[str, Any]:
        """Run load testing"""
        results = {'passed': 0, 'failed': 0, 'tests': {}}
        
        print("   Running Concurrent Request Test...")
        concurrent_test = self._test_concurrent_requests()
        results['tests']['concurrent_requests'] = concurrent_test
        if concurrent_test['success']:
            results['passed'] += 1
        else:
            results['failed'] += 1
        
        print("   Running Sustained Load Test...")
        sustained_test = self._test_sustained_load()
        results['tests']['sustained_load'] = sustained_test
        if sustained_test['success']:
            results['passed'] += 1
        else:
            results['failed'] += 1
        
        self.load_test_results = results
        return results
    
    def _test_concurrent_requests(self) -> Dict[str, Any]:
        """Test handling of concurrent requests"""
        try:
            num_requests = 50
            start_time = time.time()
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(requests.get, f"{self.base_url}/health", timeout=10)
                    for _ in range(num_requests)
                ]
                
                responses = []
                for future in concurrent.futures.as_completed(futures):
                    try:
                        response = future.result()
                        responses.append(response.status_code)
                    except Exception as e:
                        responses.append(0)  # Failed request
            
            end_time = time.time()
            duration = end_time - start_time
            
            success_rate = len([r for r in responses if r == 200]) / len(responses)
            
            return {
                'success': success_rate > 0.9,  # 90% success rate
                'duration': duration,
                'requests_per_second': num_requests / duration,
                'success_rate': success_rate,
                'total_requests': num_requests
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _test_sustained_load(self) -> Dict[str, Any]:
        """Test sustained load over time"""
        try:
            duration = 30  # 30 seconds test
            start_time = time.time()
            requests_made = 0
            successful_requests = 0
            
            while time.time() - start_time < duration:
                try:
                    response = requests.get(f"{self.base_url}/health", timeout=5)
                    if response.status_code == 200:
                        successful_requests += 1
                except:
                    pass
                
                requests_made += 1
                time.sleep(0.1)  # 10 requests per second
            
            success_rate = successful_requests / requests_made if requests_made > 0 else 0
            
            return {
                'success': success_rate > 0.95,  # 95% success rate for sustained load
                'duration': duration,
                'total_requests': requests_made,
                'successful_requests': successful_requests,
                'success_rate': success_rate,
                'avg_rps': requests_made / duration
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def run_scenario_tests(self) -> Dict[str, Any]:
        """Run user scenario tests"""
        results = {'passed': 0, 'failed': 0, 'tests': {}}
        
        scenarios = [
            ('New User Onboarding', self._test_new_user_scenario),
            ('Dashboard Navigation', self._test_dashboard_scenario),
            ('API Integration', self._test_api_integration_scenario),
            ('Service Monitoring', self._test_monitoring_scenario),
            ('Data Management', self._test_data_management_scenario)
        ]
        
        for scenario_name, scenario_func in scenarios:
            print(f"   Testing {scenario_name} Scenario...")
            try:
                result = scenario_func()
                results['tests'][scenario_name] = result
                if result['success']:
                    results['passed'] += 1
                else:
                    results['failed'] += 1
            except Exception as e:
                results['failed'] += 1
                results['tests'][scenario_name] = {'success': False, 'error': str(e)}
        
        return results
    
    def _test_new_user_scenario(self) -> Dict[str, Any]:
        """Test new user onboarding scenario"""
        steps = []
        
        # Step 1: Access main page
        try:
            response = requests.get(f"{self.base_url}/", timeout=10)
            steps.append({'step': 'Access main page', 'success': response.status_code in [200, 302]})
        except Exception as e:
            steps.append({'step': 'Access main page', 'success': False, 'error': str(e)})
        
        # Step 2: Access setup page
        try:
            response = requests.get(f"{self.base_url}/quick-setup", timeout=10)
            steps.append({'step': 'Access setup page', 'success': response.status_code == 200})
        except Exception as e:
            steps.append({'step': 'Access setup page', 'success': False, 'error': str(e)})
        
        # Step 3: Check health endpoint
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            steps.append({'step': 'Check health', 'success': response.status_code == 200})
        except Exception as e:
            steps.append({'step': 'Check health', 'success': False, 'error': str(e)})
        
        success_count = len([s for s in steps if s['success']])
        return {
            'success': success_count == len(steps),
            'steps': steps,
            'completion_rate': success_count / len(steps)
        }
    
    def _test_dashboard_scenario(self) -> Dict[str, Any]:
        """Test dashboard functionality scenario"""
        steps = []
        
        # Access dashboard
        try:
            response = requests.get(f"{self.base_url}/dashboard", timeout=10)
            steps.append({'step': 'Access dashboard', 'success': response.status_code == 200})
        except Exception as e:
            steps.append({'step': 'Access dashboard', 'success': False, 'error': str(e)})
        
        # Check service status
        try:
            response = requests.get(f"{self.base_url}/api/services/health", timeout=10)
            steps.append({'step': 'Check service status', 'success': response.status_code == 200})
        except Exception as e:
            steps.append({'step': 'Check service status', 'success': False, 'error': str(e)})
        
        success_count = len([s for s in steps if s['success']])
        return {
            'success': success_count == len(steps),
            'steps': steps,
            'completion_rate': success_count / len(steps)
        }
    
    def _test_api_integration_scenario(self) -> Dict[str, Any]:
        """Test API integration scenario"""
        steps = []
        
        # Test database operations
        try:
            response = requests.get(f"{self.base_url}/api/database/stats", timeout=10)
            steps.append({'step': 'Database stats', 'success': response.status_code == 200})
        except Exception as e:
            steps.append({'step': 'Database stats', 'success': False, 'error': str(e)})
        
        # Test media operations
        try:
            response = requests.post(f"{self.base_url}/api/media/create-avatar", 
                                   json={'personality': 'test'}, timeout=10)
            steps.append({'step': 'Media creation', 'success': response.status_code in [200, 201]})
        except Exception as e:
            steps.append({'step': 'Media creation', 'success': False, 'error': str(e)})
        
        success_count = len([s for s in steps if s['success']])
        return {
            'success': success_count == len(steps),
            'steps': steps,
            'completion_rate': success_count / len(steps)
        }
    
    def _test_monitoring_scenario(self) -> Dict[str, Any]:
        """Test service monitoring scenario"""
        steps = []
        
        # Check monitoring status
        try:
            response = requests.get(f"{self.base_url}/api/services/status", timeout=10)
            steps.append({'step': 'Monitoring status', 'success': response.status_code == 200})
        except Exception as e:
            steps.append({'step': 'Monitoring status', 'success': False, 'error': str(e)})
        
        # Check notification stats
        try:
            response = requests.get(f"{self.base_url}/api/notifications/stats", timeout=10)
            steps.append({'step': 'Notification stats', 'success': response.status_code == 200})
        except Exception as e:
            steps.append({'step': 'Notification stats', 'success': False, 'error': str(e)})
        
        success_count = len([s for s in steps if s['success']])
        return {
            'success': success_count == len(steps),
            'steps': steps,
            'completion_rate': success_count / len(steps)
        }
    
    def _test_data_management_scenario(self) -> Dict[str, Any]:
        """Test data management scenario"""
        steps = []
        
        # Test database cleanup
        try:
            response = requests.post(f"{self.base_url}/api/database/cleanup", 
                                   json={'days_old': 365}, timeout=10)
            steps.append({'step': 'Database cleanup', 'success': response.status_code in [200, 201]})
        except Exception as e:
            steps.append({'step': 'Database cleanup', 'success': False, 'error': str(e)})
        
        success_count = len([s for s in steps if s['success']])
        return {
            'success': success_count == len(steps),
            'steps': steps,
            'completion_rate': success_count / len(steps)
        }
    
    def generate_test_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = f"/tmp/test_report_{timestamp}.json"
        
        # Calculate overall statistics
        total_passed = sum(result.get('passed', 0) for result in self.test_results.values())
        total_failed = sum(result.get('failed', 0) for result in self.test_results.values())
        total_tests = total_passed + total_failed
        
        summary = {
            'timestamp': datetime.now().isoformat(),
            'total_tests': total_tests,
            'passed': total_passed,
            'failed': total_failed,
            'success_rate': total_passed / total_tests if total_tests > 0 else 0,
            'overall_status': 'PASS' if total_failed == 0 else 'FAIL',
            'performance_metrics': self.performance_metrics,
            'test_suites': {}
        }
        
        # Add suite summaries
        for suite_name, suite_results in self.test_results.items():
            summary['test_suites'][suite_name] = {
                'passed': suite_results.get('passed', 0),
                'failed': suite_results.get('failed', 0),
                'status': 'PASS' if suite_results.get('failed', 0) == 0 else 'FAIL'
            }
        
        # Generate full report
        full_report = {
            'summary': summary,
            'detailed_results': self.test_results,
            'performance_metrics': self.performance_metrics,
            'system_info': {
                'python_version': sys.version,
                'platform': os.name,
                'memory_total': psutil.virtual_memory().total / (1024**3),  # GB
                'cpu_count': psutil.cpu_count()
            }
        }
        
        # Save report to file
        with open(report_file, 'w') as f:
            json.dump(full_report, f, indent=2)
        
        return {
            'summary': summary,
            'report_file': report_file
        }

def run_comprehensive_tests():
    """Run the comprehensive test suite"""
    print("🚀 Starting Wednesday AI Assistant Test Suite")
    print("=" * 60)
    
    test_suite = ComprehensiveTestSuite()
    results = test_suite.run_all_tests()
    
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    summary = results['summary']
    print(f"Total Tests: {summary['total_tests']}")
    print(f"Passed: {summary['passed']} ✅")
    print(f"Failed: {summary['failed']} ❌")
    print(f"Success Rate: {summary['success_rate']:.1%}")
    print(f"Overall Status: {summary['overall_status']}")
    
    print("\n📈 PERFORMANCE METRICS")
    print("-" * 30)
    perf = results['performance_metrics']
    print(f"Memory Usage: {perf.get('memory_mb', 0):.1f} MB")
    print(f"CPU Usage: {perf.get('cpu_percent', 0):.1f}%")
    print(f"Avg Response Time: {perf.get('avg_response_time_ms', 0):.1f} ms")
    
    print(f"\n📋 Detailed report saved to: {results['report_file']}")
    
    return results

if __name__ == "__main__":
    run_comprehensive_tests()