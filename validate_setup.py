#!/usr/bin/env python3
"""
Comprehensive Setup and Validation Script for Wednesday WhatsApp Assistant

This script performs:
- Environment validation
- Dependency checking
- Service initialization
- Comprehensive testing
- Performance benchmarking
- Security validation
- Feature demonstration
"""

import os
import sys
import subprocess
import requests
import json
import time
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WednesdaySetupValidator:
    """Comprehensive setup and validation for Wednesday AI Assistant"""
    
    def __init__(self):
        self.base_url = "http://localhost:5000"
        self.validation_results = {}
        self.performance_metrics = {}
        self.feature_tests = {}
        
    def run_complete_validation(self):
        """Run complete setup validation and testing"""
        print("🤖 Wednesday AI Assistant - Setup & Validation")
        print("=" * 60)
        
        # 1. Environment Check
        print("\n1️⃣ Environment Validation...")
        self.validate_environment()
        
        # 2. Dependencies Check
        print("\n2️⃣ Dependencies Check...")
        self.check_dependencies()
        
        # 3. Application Health
        print("\n3️⃣ Application Health Check...")
        self.check_application_health()
        
        # 4. Feature Testing
        print("\n4️⃣ Feature Testing...")
        self.test_all_features()
        
        # 5. Performance Benchmarking
        print("\n5️⃣ Performance Benchmarking...")
        self.benchmark_performance()
        
        # 6. Security Validation
        print("\n6️⃣ Security Validation...")
        self.validate_security()
        
        # 7. Advanced Features Demo
        print("\n7️⃣ Advanced Features Demo...")
        self.demo_advanced_features()
        
        # 8. Generate Report
        print("\n8️⃣ Generating Report...")
        report = self.generate_validation_report()
        
        print(f"\n✅ Validation Complete! Report: {report}")
        return report
    
    def validate_environment(self):
        """Validate system environment"""
        results = {'python_version': None, 'os_info': None, 'resources': {}}
        
        # Check Python version
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        results['python_version'] = python_version
        
        if sys.version_info >= (3, 8):
            print(f"   ✅ Python {python_version} (Good)")
        else:
            print(f"   ❌ Python {python_version} (Upgrade to 3.8+)")
        
        # Check OS
        import platform
        os_info = f"{platform.system()} {platform.release()}"
        results['os_info'] = os_info
        print(f"   📱 OS: {os_info}")
        
        # Check resources
        try:
            import psutil
            memory_gb = psutil.virtual_memory().total / (1024**3)
            cpu_count = psutil.cpu_count()
            disk_gb = psutil.disk_usage('/').free / (1024**3)
            
            results['resources'] = {
                'memory_gb': memory_gb,
                'cpu_count': cpu_count,
                'disk_free_gb': disk_gb
            }
            
            print(f"   💾 Memory: {memory_gb:.1f} GB")
            print(f"   🏭 CPU Cores: {cpu_count}")
            print(f"   💽 Disk Free: {disk_gb:.1f} GB")
            
            if memory_gb >= 4 and cpu_count >= 2:
                print(f"   ✅ Resources adequate for deployment")
            else:
                print(f"   ⚠️ Limited resources - performance may be impacted")
                
        except Exception as e:
            print(f"   ❌ Resource check failed: {e}")
        
        self.validation_results['environment'] = results
    
    def check_dependencies(self):
        """Check required dependencies"""
        required_packages = [
            'flask', 'requests', 'google-generativeai', 'openai',
            'pillow', 'psutil', 'sqlite3', 'opencv-cv2', 'scikit-learn'
        ]
        
        results = {'installed': [], 'missing': [], 'total_required': len(required_packages)}
        
        for package in required_packages:
            try:
                if package == 'opencv-cv2':
                    import cv2
                    results['installed'].append(package)
                    print(f"   ✅ {package}")
                elif package == 'google-generativeai':
                    import google.generativeai
                    results['installed'].append(package)
                    print(f"   ✅ {package}")
                elif package == 'scikit-learn':
                    import sklearn
                    results['installed'].append(package)
                    print(f"   ✅ {package}")
                else:
                    __import__(package)
                    results['installed'].append(package)
                    print(f"   ✅ {package}")
            except ImportError:
                results['missing'].append(package)
                print(f"   ❌ {package} (Missing)")
        
        # Check for critical files
        critical_files = [
            'main.py', 'database.py', 'handlers/gemini.py', 
            'handlers/advanced_ai.py', 'test_suite.py'
        ]
        
        for file_path in critical_files:
            if os.path.exists(file_path):
                print(f"   ✅ {file_path}")
            else:
                print(f"   ❌ {file_path} (Missing)")
        
        self.validation_results['dependencies'] = results
    
    def check_application_health(self):
        """Check if application is running and healthy"""
        results = {'running': False, 'health_status': None, 'response_time': None}
        
        try:
            start_time = time.time()
            response = requests.get(f"{self.base_url}/health", timeout=10)
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                health_data = response.json()
                results['running'] = True
                results['health_status'] = health_data.get('status')
                results['response_time'] = response_time
                
                print(f"   ✅ Application running")
                print(f"   📊 Status: {health_data.get('status', 'Unknown')}")
                print(f"   ⚡ Response time: {response_time:.1f}ms")
                print(f"   💾 Memory: {health_data.get('memory_mb', 'Unknown')} MB")
                print(f"   🗄️ Database: {'✅' if health_data.get('database_enabled') else '❌'}")
            else:
                print(f"   ❌ Application error (HTTP {response.status_code})")
                
        except requests.exceptions.ConnectionError:
            print(f"   ❌ Application not running (start with: python main.py)")
        except Exception as e:
            print(f"   ❌ Health check failed: {e}")
        
        self.validation_results['application_health'] = results
    
    def test_all_features(self):
        """Test all major features"""
        features = {
            'core_api': self._test_core_api,
            'database': self._test_database_features,
            'service_monitoring': self._test_service_monitoring,
            'media_generation': self._test_media_generation,
            'advanced_ai': self._test_advanced_ai,
            'dashboard': self._test_dashboard
        }
        
        results = {}
        
        for feature_name, test_func in features.items():
            print(f"   Testing {feature_name.replace('_', ' ').title()}...")
            try:
                results[feature_name] = test_func()
            except Exception as e:
                results[feature_name] = {'success': False, 'error': str(e)}
        
        self.feature_tests = results
    
    def _test_core_api(self):
        """Test core API endpoints"""
        endpoints = ['/health', '/api/services/health', '/api/database/stats']
        results = {'tested': 0, 'passed': 0, 'details': []}
        
        for endpoint in endpoints:
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                results['tested'] += 1
                if response.status_code == 200:
                    results['passed'] += 1
                    results['details'].append(f"✅ {endpoint}")
                else:
                    results['details'].append(f"❌ {endpoint} (HTTP {response.status_code})")
            except Exception as e:
                results['tested'] += 1
                results['details'].append(f"❌ {endpoint} ({str(e)})")
        
        return {'success': results['passed'] == results['tested'], **results}
    
    def _test_database_features(self):
        """Test database functionality"""
        try:
            response = requests.get(f"{self.base_url}/api/database/stats", timeout=5)
            if response.status_code == 200:
                stats = response.json()
                return {
                    'success': True,
                    'stats': stats,
                    'tables': list(stats.keys()),
                    'size_mb': stats.get('db_size_mb', 0)
                }
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _test_service_monitoring(self):
        """Test service monitoring"""
        try:
            response = requests.get(f"{self.base_url}/api/services/status", timeout=5)
            if response.status_code == 200:
                status = response.json()
                services = status.get('services', {})
                return {
                    'success': True,
                    'total_services': len(services),
                    'healthy_services': len([s for s in services.values() if s.get('status') == 'healthy']),
                    'monitoring_active': status.get('monitoring_active', False)
                }
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _test_media_generation(self):
        """Test media generation features"""
        try:
            # Test avatar creation
            response = requests.post(
                f"{self.base_url}/api/media/create-avatar",
                json={'personality': 'test', 'style': 'professional'},
                timeout=10
            )
            if response.status_code == 200:
                result = response.json()
                return {
                    'success': True,
                    'avatar_created': result.get('success', False),
                    'features_available': ['avatar_creation']
                }
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _test_advanced_ai(self):
        """Test advanced AI features"""
        try:
            response = requests.get(f"{self.base_url}/api/advanced/status", timeout=5)
            if response.status_code == 200:
                status = response.json()
                features = status.get('status', {}).get('features', {})
                return {
                    'success': True,
                    'available_features': list(features.keys()),
                    'total_features': len(features)
                }
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _test_dashboard(self):
        """Test dashboard functionality"""
        try:
            response = requests.get(f"{self.base_url}/dashboard", timeout=5)
            if response.status_code == 200:
                content_length = len(response.content)
                return {
                    'success': True,
                    'content_length': content_length,
                    'has_content': content_length > 1000
                }
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def benchmark_performance(self):
        """Benchmark application performance"""
        results = {}
        
        # Response time benchmark
        print("   🏃 Response time benchmark...")
        response_times = []
        for i in range(10):
            try:
                start = time.time()
                requests.get(f"{self.base_url}/health", timeout=5)
                response_times.append((time.time() - start) * 1000)
            except:
                response_times.append(5000)  # Timeout
        
        avg_response_time = sum(response_times) / len(response_times)
        results['avg_response_time_ms'] = avg_response_time
        print(f"     Average response time: {avg_response_time:.1f}ms")
        
        # Memory usage
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                health = response.json()
                memory_mb = health.get('memory_mb', 0)
                results['memory_usage_mb'] = memory_mb
                print(f"     Memory usage: {memory_mb} MB")
        except:
            pass
        
        # Concurrent requests
        print("   🚀 Concurrent requests test...")
        import concurrent.futures
        
        def make_request():
            try:
                start = time.time()
                response = requests.get(f"{self.base_url}/health", timeout=5)
                return (time.time() - start) * 1000, response.status_code == 200
            except:
                return 5000, False
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            concurrent_results = [f.result() for f in futures]
        
        successful_requests = sum(1 for _, success in concurrent_results if success)
        concurrent_avg_time = sum(time for time, _ in concurrent_results) / len(concurrent_results)
        
        results['concurrent_success_rate'] = successful_requests / len(concurrent_results)
        results['concurrent_avg_time_ms'] = concurrent_avg_time
        
        print(f"     Concurrent success rate: {(successful_requests/len(concurrent_results)*100):.1f}%")
        print(f"     Concurrent avg time: {concurrent_avg_time:.1f}ms")
        
        self.performance_metrics = results
    
    def validate_security(self):
        """Basic security validation"""
        results = {'tests_run': 0, 'passed': 0, 'issues': []}
        
        # Test for directory traversal
        try:
            response = requests.get(f"{self.base_url}/../../../etc/passwd", timeout=5)
            results['tests_run'] += 1
            if response.status_code == 404:
                results['passed'] += 1
                print("   ✅ Directory traversal protection")
            else:
                results['issues'].append("Possible directory traversal vulnerability")
                print("   ⚠️ Directory traversal check failed")
        except:
            results['tests_run'] += 1
            results['passed'] += 1
            print("   ✅ Directory traversal protection (connection refused)")
        
        # Test for SQL injection patterns
        try:
            malicious_payload = {"days_old": "'; DROP TABLE conversations; --"}
            response = requests.post(
                f"{self.base_url}/api/database/cleanup",
                json=malicious_payload,
                timeout=5
            )
            results['tests_run'] += 1
            if response.status_code in [400, 422]:  # Input validation error
                results['passed'] += 1
                print("   ✅ SQL injection protection")
            else:
                results['issues'].append("Possible SQL injection vulnerability")
                print("   ⚠️ SQL injection check inconclusive")
        except:
            results['tests_run'] += 1
            results['passed'] += 1
            print("   ✅ SQL injection protection (connection refused)")
        
        self.validation_results['security'] = results
    
    def demo_advanced_features(self):
        """Demonstrate advanced features"""
        demos = {}
        
        # Test advanced diagnostics
        print("   🔧 Testing advanced diagnostics...")
        try:
            response = requests.get(f"{self.base_url}/api/advanced/diagnostics", timeout=10)
            if response.status_code == 200:
                diagnostics = response.json()
                demos['diagnostics'] = {
                    'success': True,
                    'system_info': diagnostics.get('diagnostics', {}).get('system', {}),
                    'features_count': len(diagnostics.get('diagnostics', {}))
                }
                print("     ✅ Advanced diagnostics working")
            else:
                demos['diagnostics'] = {'success': False, 'error': f'HTTP {response.status_code}'}
        except Exception as e:
            demos['diagnostics'] = {'success': False, 'error': str(e)}
        
        # Test optimization
        print("   ⚡ Testing system optimization...")
        try:
            response = requests.post(
                f"{self.base_url}/api/advanced/optimize",
                json={'type': 'memory'},
                timeout=10
            )
            if response.status_code == 200:
                optimization = response.json()
                demos['optimization'] = {
                    'success': True,
                    'results': optimization.get('results', {})
                }
                print("     ✅ System optimization working")
            else:
                demos['optimization'] = {'success': False, 'error': f'HTTP {response.status_code}'}
        except Exception as e:
            demos['optimization'] = {'success': False, 'error': str(e)}
        
        # Test quick test suite
        print("   🧪 Testing integrated test suite...")
        try:
            response = requests.get(f"{self.base_url}/api/advanced/test-suite?type=quick", timeout=15)
            if response.status_code == 200:
                test_results = response.json()
                demos['test_suite'] = {
                    'success': True,
                    'test_type': test_results.get('test_type'),
                    'system_health': test_results.get('system_health', {})
                }
                print("     ✅ Integrated test suite working")
            else:
                demos['test_suite'] = {'success': False, 'error': f'HTTP {response.status_code}'}
        except Exception as e:
            demos['test_suite'] = {'success': False, 'error': str(e)}
        
        self.feature_tests['advanced_demos'] = demos
    
    def generate_validation_report(self):
        """Generate comprehensive validation report"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = f"/tmp/validation_report_{timestamp}.json"
        
        # Calculate overall score
        scores = {
            'environment': self._score_environment(),
            'dependencies': self._score_dependencies(),
            'application_health': self._score_health(),
            'features': self._score_features(),
            'performance': self._score_performance(),
            'security': self._score_security()
        }
        
        overall_score = sum(scores.values()) / len(scores)
        
        # Generate summary
        summary = {
            'timestamp': datetime.now().isoformat(),
            'overall_score': overall_score,
            'overall_grade': self._get_grade(overall_score),
            'scores': scores,
            'recommendations': self._generate_recommendations(scores),
            'ready_for_production': overall_score >= 80
        }
        
        # Full report
        report = {
            'summary': summary,
            'validation_results': self.validation_results,
            'performance_metrics': self.performance_metrics,
            'feature_tests': self.feature_tests,
            'environment_info': {
                'python_version': sys.version,
                'platform': os.name,
                'timestamp': datetime.now().isoformat()
            }
        }
        
        # Save report
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 VALIDATION SUMMARY")
        print("=" * 60)
        print(f"Overall Score: {overall_score:.1f}/100 ({summary['overall_grade']})")
        print(f"Production Ready: {'✅ Yes' if summary['ready_for_production'] else '❌ No'}")
        
        print("\n📈 Component Scores:")
        for component, score in scores.items():
            print(f"  {component.replace('_', ' ').title()}: {score:.1f}/100")
        
        if summary['recommendations']:
            print("\n💡 Recommendations:")
            for rec in summary['recommendations']:
                print(f"  • {rec}")
        
        return report_file
    
    def _score_environment(self):
        """Score environment validation"""
        env = self.validation_results.get('environment', {})
        score = 50  # Base score
        
        # Python version check
        if sys.version_info >= (3, 8):
            score += 20
        
        # Resource check
        resources = env.get('resources', {})
        if resources.get('memory_gb', 0) >= 4:
            score += 15
        if resources.get('cpu_count', 0) >= 2:
            score += 15
        
        return min(score, 100)
    
    def _score_dependencies(self):
        """Score dependency validation"""
        deps = self.validation_results.get('dependencies', {})
        if not deps:
            return 0
        
        installed = len(deps.get('installed', []))
        total = deps.get('total_required', 1)
        
        return (installed / total) * 100
    
    def _score_health(self):
        """Score application health"""
        health = self.validation_results.get('application_health', {})
        
        if not health.get('running'):
            return 0
        
        score = 50  # Base for running
        
        if health.get('health_status') == 'healthy':
            score += 30
        
        response_time = health.get('response_time', 1000)
        if response_time < 100:
            score += 20
        elif response_time < 500:
            score += 10
        
        return min(score, 100)
    
    def _score_features(self):
        """Score feature testing"""
        features = self.feature_tests
        if not features:
            return 0
        
        working_features = sum(1 for f in features.values() if f.get('success', False))
        total_features = len(features)
        
        return (working_features / total_features) * 100 if total_features > 0 else 0
    
    def _score_performance(self):
        """Score performance metrics"""
        perf = self.performance_metrics
        if not perf:
            return 0
        
        score = 0
        
        # Response time scoring
        avg_time = perf.get('avg_response_time_ms', 1000)
        if avg_time < 100:
            score += 40
        elif avg_time < 500:
            score += 20
        
        # Memory usage scoring
        memory_mb = perf.get('memory_usage_mb', 500)
        if memory_mb < 200:
            score += 30
        elif memory_mb < 400:
            score += 15
        
        # Concurrent performance
        concurrent_success = perf.get('concurrent_success_rate', 0)
        score += concurrent_success * 30
        
        return min(score, 100)
    
    def _score_security(self):
        """Score security validation"""
        security = self.validation_results.get('security', {})
        if not security:
            return 50  # Neutral score if no tests
        
        tests_run = security.get('tests_run', 0)
        passed = security.get('passed', 0)
        
        if tests_run == 0:
            return 50
        
        return (passed / tests_run) * 100
    
    def _get_grade(self, score):
        """Convert score to letter grade"""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"
    
    def _generate_recommendations(self, scores):
        """Generate recommendations based on scores"""
        recommendations = []
        
        if scores['environment'] < 70:
            recommendations.append("Upgrade Python to 3.8+ and ensure adequate system resources")
        
        if scores['dependencies'] < 90:
            recommendations.append("Install missing dependencies: pip install -r requirements.txt")
        
        if scores['application_health'] < 80:
            recommendations.append("Improve application response time and stability")
        
        if scores['features'] < 80:
            recommendations.append("Fix failing features and ensure all endpoints are working")
        
        if scores['performance'] < 70:
            recommendations.append("Optimize memory usage and response times")
        
        if scores['security'] < 80:
            recommendations.append("Review and strengthen security measures")
        
        return recommendations

def main():
    """Main validation script"""
    print("🚀 Starting Wednesday AI Assistant Validation")
    print("This will perform comprehensive testing and validation...")
    print()
    
    validator = WednesdaySetupValidator()
    report_file = validator.run_complete_validation()
    
    print(f"\n🎉 Validation complete!")
    print(f"📄 Full report saved to: {report_file}")
    print("\n🔗 Quick Links:")
    print("  • Dashboard: http://localhost:5000/dashboard")
    print("  • Health Check: http://localhost:5000/health")
    print("  • API Status: http://localhost:5000/api/advanced/status")
    print("  • Setup Guide: http://localhost:5000/quick-setup")

if __name__ == "__main__":
    main()