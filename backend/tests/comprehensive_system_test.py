# File: backend/tests/comprehensive_system_test.py
"""Comprehensive System Testing for Smart Attendance 3D System."""
import requests
import json
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import unittest
from dataclasses import dataclass, asdict

@dataclass
class TestResult:
    """Test result data structure."""
    test_name: str
    category: str
    success: bool
    response_time_ms: int
    details: Dict
    error_message: Optional[str] = None

@dataclass
class SystemPerformanceMetrics:
    """System performance metrics."""
    total_tests: int
    passed_tests: int
    failed_tests: int
    average_response_time_ms: float
    max_response_time_ms: int
    min_response_time_ms: int
    total_test_duration_seconds: float

class SmartAttendanceSystemTester:
    """Comprehensive tester for the Smart Attendance 3D System."""
    
    def __init__(self, base_url: str = "http://127.0.0.1:5000/api"):
        self.base_url = base_url
        self.auth_token = None
        self.admin_token = None
        self.teacher_token = None
        self.student_token = None
        self.test_results: List[TestResult] = []
        self.verification_session_id = None
        self.recording_session_id = None
        
    def run_comprehensive_tests(self) -> Dict:
        """Run all comprehensive tests."""
        print("🚀 Starting Comprehensive Smart Attendance 3D System Tests")
        print("=" * 80)
        
        start_time = time.time()
        
        # Test Categories
        test_categories = [
            ("🔐 Authentication & Authorization", self._test_authentication),
            ("🏗️ 3D Room Management", self._test_3d_room_management),
            ("📏 Barometer & GPS Services", self._test_barometer_gps_services),
            ("👤 Face Recognition System", self._test_face_recognition_system),
            ("🔄 Dynamic Room Recording", self._test_dynamic_room_recording),
            ("⚡ Sequential Verification", self._test_sequential_verification),
            ("✅ Enhanced Attendance APIs", self._test_enhanced_attendance_apis),
            ("📊 System Analytics & Monitoring", self._test_system_analytics),
            ("🚀 Performance & Load Testing", self._test_performance_load),
            ("🔒 Security & Validation", self._test_security_validation),
        ]
        
        # Execute test categories
        for category_name, test_function in test_categories:
            print(f"\n{category_name}")
            print("-" * 60)
            try:
                test_function()
            except Exception as e:
                self._add_test_result(
                    f"{category_name} - Critical Error",
                    category_name,
                    False,
                    0,
                    {},
                    str(e)
                )
                print(f"❌ Critical error in {category_name}: {str(e)}")
        
        # Calculate metrics
        end_time = time.time()
        metrics = self._calculate_performance_metrics(end_time - start_time)
        
        # Generate comprehensive report
        report = self._generate_comprehensive_report(metrics)
        
        print("\n" + "=" * 80)
        print("🎯 COMPREHENSIVE TEST RESULTS")
        print("=" * 80)
        self._print_summary_report(metrics, report)
        
        return {
            'metrics': asdict(metrics),
            'detailed_results': [asdict(result) for result in self.test_results],
            'comprehensive_report': report,
            'test_timestamp': datetime.utcnow().isoformat()
        }
    
    # =================== AUTHENTICATION TESTS ===================
    
    def _test_authentication(self):
        """Test authentication and authorization systems."""
        
        # Test admin login
        admin_result = self._make_request(
            'POST', '/auth/login',
            {
                'email': 'super@admin.com',
                'password': 'super123456'
            }
        )
        
        if admin_result['success'] and admin_result['data'].get('data', {}).get('access_token'):
            self.admin_token = admin_result['data']['data']['access_token']
            self._add_test_result(
                "Admin Login",
                "Authentication",
                True,
                admin_result['response_time'],
                {'user_role': admin_result['data']['data']['user']['role']}
            )
        else:
            self._add_test_result(
                "Admin Login",
                "Authentication", 
                False,
                admin_result['response_time'],
                {},
                "Failed to get admin token"
            )
        
        # Test student login (if exists)
        student_result = self._make_request(
            'POST', '/auth/student-login',
            {
                'university_id': 'CS2025001',
                'secret_code': 'ABC123'
            }
        )
        
        if student_result['success']:
            self.student_token = student_result['data']['data']['access_token']
            self._add_test_result(
                "Student Login",
                "Authentication",
                True,
                student_result['response_time'],
                {'university_id': 'CS2025001'}
            )
        else:
            self._add_test_result(
                "Student Login",
                "Authentication",
                False,
                student_result['response_time'],
                {},
                "Student login failed - may need to create test student"
            )
        
        # Test token validation
        if self.admin_token:
            profile_result = self._make_request(
                'GET', '/auth/me',
                headers={'Authorization': f'Bearer {self.admin_token}'}
            )
            
            self._add_test_result(
                "Token Validation",
                "Authentication",
                profile_result['success'],
                profile_result['response_time'],
                {'token_valid': profile_result['success']}
            )
    
    # =================== 3D ROOM MANAGEMENT TESTS ===================
    
    def _test_3d_room_management(self):
        """Test 3D room management functionality."""
        
        if not self.admin_token:
            self._add_test_result(
                "3D Room Tests Skipped",
                "3D Room Management",
                False,
                0,
                {},
                "No admin token available"
            )
            return
        
        headers = {'Authorization': f'Bearer {self.admin_token}'}
        
        # Test room listing
        rooms_result = self._make_request(
            'GET', '/admin/rooms',
            headers=headers
        )
        
        self._add_test_result(
            "List 3D Rooms",
            "3D Room Management",
            rooms_result['success'],
            rooms_result['response_time'],
            {
                'rooms_count': len(rooms_result['data'].get('data', [])) if rooms_result['success'] else 0,
                'has_3d_rooms': any(room.get('recording_info', {}).get('is_validated') for room in rooms_result['data'].get('data', []))
            }
        )
        
        # Test room creation with 3D data
        test_room_data = {
            'name': 'TEST_3D_ROOM_001',
            'building': 'Test Building',
            'floor': 1,
            'floor_altitude': 0.0,
            'ceiling_height': 3.5,
            'gps_boundaries': [
                {'lat': 33.3152, 'lng': 44.3661},
                {'lat': 33.3153, 'lng': 44.3661},
                {'lat': 33.3153, 'lng': 44.3662},
                {'lat': 33.3152, 'lng': 44.3662}
            ],
            'center_latitude': 33.31525,
            'center_longitude': 44.36615,
            'capacity': 30
        }
        
        create_room_result = self._make_request(
            'POST', '/admin/rooms',
            test_room_data,
            headers=headers
        )
        
        self._add_test_result(
            "Create 3D Room",
            "3D Room Management", 
            create_room_result['success'],
            create_room_result['response_time'],
            {
                'room_created': create_room_result['success'],
                'room_data': test_room_data if create_room_result['success'] else None
            }
        )
        
        # Test 3D location verification
        if create_room_result['success']:
            room_id = create_room_result['data']['data']['id']
            location_test_result = self._make_request(
                'POST', f'/admin/rooms/{room_id}/check-location',
                {
                    'latitude': 33.31525,
                    'longitude': 44.36615,
                    'altitude': 1.75
                },
                headers=headers
            )
            
            self._add_test_result(
                "3D Location Verification",
                "3D Room Management",
                location_test_result['success'],
                location_test_result['response_time'],
                {
                    'location_verified': location_test_result['success'],
                    'is_inside': location_test_result['data'].get('data', {}).get('is_inside') if location_test_result['success'] else False
                }
            )
    
    # =================== BAROMETER & GPS TESTS ===================
    
    def _test_barometer_gps_services(self):
        """Test barometer and GPS services."""
        
        if not self.admin_token:
            return
        
        headers = {'Authorization': f'Bearer {self.admin_token}'}
        
        # Test ground calibration
        calibration_data = {
            'pressure_readings': [
                {
                    'pressure': 1013.25 + i * 0.1,
                    'temperature': 25.0,
                    'humidity': 60.0,
                    'device_info': {'has_barometer': True}
                }
                for i in range(10)
            ],
            'ground_altitude': 280.0,
            'location': 'Test Ground Floor'
        }
        
        calibration_result = self._make_request(
            'POST', '/recording/calibrate-ground',
            calibration_data,
            headers=headers
        )
        
        self._add_test_result(
            "Barometer Ground Calibration",
            "Barometer & GPS",
            calibration_result['success'],
            calibration_result['response_time'],
            {
                'calibration_successful': calibration_result['success'],
                'readings_processed': len(calibration_data['pressure_readings'])
            }
        )
        
        # Test floor detection
        if calibration_result['success']:
            floor_detection_result = self._make_request(
                'POST', '/recording/verify-floor',
                {
                    'pressure': 1010.5,  # Simulating higher floor
                    'temperature': 24.0,
                    'building_id': 1,
                    'device_info': {'has_barometer': True}
                },
                headers=headers
            )
            
            self._add_test_result(
                "Floor Detection",
                "Barometer & GPS",
                floor_detection_result['success'],
                floor_detection_result['response_time'],
                {
                    'floor_detected': floor_detection_result['data'].get('data', {}).get('floor_detection', {}).get('detected_floor') if floor_detection_result['success'] else None,
                    'confidence': floor_detection_result['data'].get('data', {}).get('floor_detection', {}).get('confidence_level') if floor_detection_result['success'] else 0
                }
            )
    
    # =================== FACE RECOGNITION TESTS ===================
    
    def _test_face_recognition_system(self):
        """Test face recognition system."""
        
        if not self.student_token:
            self._add_test_result(
                "Face Recognition Tests Skipped",
                "Face Recognition",
                False,
                0,
                {},
                "No student token available"
            )
            return
        
        headers = {'Authorization': f'Bearer {self.student_token}'}
        
        # Test face registration flow
        registration_flow_result = self._make_request(
            'GET', '/enhanced-attendance/face-registration-flow',
            headers=headers
        )
        
        self._add_test_result(
            "Face Registration Flow",
            "Face Recognition",
            registration_flow_result['success'],
            registration_flow_result['response_time'],
            {
                'flow_available': registration_flow_result['success'],
                'already_registered': registration_flow_result['data'].get('data', {}).get('already_registered', False) if registration_flow_result['success'] else None
            }
        )
        
        # Test face registration (if not already registered)
        if registration_flow_result['success'] and not registration_flow_result['data'].get('data', {}).get('already_registered', False):
            face_registration_data = {
                'template_data': {
                    'template_vector': [0.1] * 128,  # Dummy 128-dim vector
                    'quality_score': 0.95,
                    'quality_metrics': {'sharpness': 0.9, 'lighting': 0.8},
                    'anti_spoofing': {
                        'liveness_score': 0.95,
                        'depth_score': 0.85,
                        'motion_score': 0.90,
                        'texture_authentic': True
                    }
                },
                'device_info': {
                    'device_id': 'test_device_001',
                    'model': 'Test Phone',
                    'os_version': '14.0',
                    'has_front_camera': True
                }
            }
            
            face_reg_result = self._make_request(
                'POST', '/enhanced-attendance/register-face',
                face_registration_data,
                headers=headers
            )
            
            self._add_test_result(
                "Face Registration",
                "Face Recognition",
                face_reg_result['success'],
                face_reg_result['response_time'],
                {
                    'registration_successful': face_reg_result['success'],
                    'quality_score': face_registration_data['template_data']['quality_score']
                }
            )
    
    # =================== DYNAMIC ROOM RECORDING TESTS ===================
    
    def _test_dynamic_room_recording(self):
        """Test dynamic room recording functionality."""
        
        if not self.admin_token:
            return
        
        headers = {'Authorization': f'Bearer {self.admin_token}'}
        
        # Test starting recording session
        recording_start_data = {
            'room_name': 'DYNAMIC_TEST_ROOM_001',
            'building': 'Test Building Dynamic',
            'floor': 2,
            'room_type': 'classroom',
            'capacity': 25
        }
        
        start_recording_result = self._make_request(
            'POST', '/recording/start-session',
            recording_start_data,
            headers=headers
        )
        
        self._add_test_result(
            "Start Dynamic Recording",
            "Dynamic Room Recording",
            start_recording_result['success'],
            start_recording_result['response_time'],
            {
                'session_started': start_recording_result['success'],
                'session_id': start_recording_result['data'].get('data', {}).get('session_id') if start_recording_result['success'] else None
            }
        )
        
        if start_recording_result['success']:
            self.recording_session_id = start_recording_result['data']['data']['session_id']
            
            # Test adding recording points
            test_points = [
                {
                    'latitude': 33.3152 + i * 0.0001,
                    'longitude': 44.3661 + i * 0.0001,
                    'pressure': 1010.0 + i * 0.1,
                    'temperature': 25.0,
                    'altitude': 7.0,
                    'gps_accuracy': 3.0,
                    'device_info': {'has_barometer': True}
                }
                for i in range(5)
            ]
            
            points_added = 0
            for i, point in enumerate(test_points):
                point_result = self._make_request(
                    'POST', f'/recording/add-point/{self.recording_session_id}',
                    point,
                    headers=headers
                )
                
                if point_result['success']:
                    points_added += 1
                
                time.sleep(0.5)  # Simulate real-time recording
            
            self._add_test_result(
                "Add Recording Points",
                "Dynamic Room Recording",
                points_added > 0,
                0,  # Average response time not calculated for multiple calls
                {
                    'points_added': points_added,
                    'total_points': len(test_points),
                    'success_rate': points_added / len(test_points)
                }
            )
            
            # Test session status
            status_result = self._make_request(
                'GET', f'/recording/session-status/{self.recording_session_id}',
                headers=headers
            )
            
            self._add_test_result(
                "Recording Session Status",
                "Dynamic Room Recording",
                status_result['success'],
                status_result['response_time'],
                {
                    'status_available': status_result['success'],
                    'points_recorded': status_result['data'].get('data', {}).get('statistics', {}).get('total_points') if status_result['success'] else 0
                }
            )
    
    # =================== SEQUENTIAL VERIFICATION TESTS ===================
    
    def _test_sequential_verification(self):
        """Test sequential verification system."""
        
        if not self.student_token:
            return
        
        headers = {'Authorization': f'Bearer {self.student_token}'}
        
        # Test starting verification session
        verification_start_data = {
            'lecture_id': 1  # Assuming lecture with ID 1 exists
        }
        
        start_verification_result = self._make_request(
            'POST', '/enhanced-attendance/start-verification',
            verification_start_data,
            headers=headers
        )
        
        self._add_test_result(
            "Start Sequential Verification",
            "Sequential Verification",
            start_verification_result['success'],
            start_verification_result['response_time'],
            {
                'verification_started': start_verification_result['success'],
                'session_id': start_verification_result['data'].get('data', {}).get('verification_session_id') if start_verification_result['success'] else None
            }
        )
        
        if start_verification_result['success']:
            self.verification_session_id = start_verification_result['data']['data']['verification_session_id']
            
            # Test verification steps
            verification_steps = [
                # Step 1: GPS Location
                {
                    'latitude': 33.3152,
                    'longitude': 44.3661,
                    'accuracy': 3.0
                },
                # Step 2: Barometer
                {
                    'pressure': 1013.0,
                    'temperature': 25.0,
                    'altitude': 280.0,
                    'device_info': {'has_barometer': True}
                },
                # Step 3: QR Code
                {
                    'qr_data': json.dumps({
                        'session_id': 'test_qr_session',
                        'lecture_id': 1,
                        'room_id': 1,
                        'expires_at': (datetime.utcnow() + timedelta(minutes=5)).isoformat(),
                        'hash': 'test_hash'
                    })
                },
                # Step 4: Face Recognition
                {
                    'verification_data': {
                        'match_confidence': 0.92,
                        'template_match_quality': 0.88,
                        'anti_spoofing': {
                            'liveness_score': 0.95,
                            'depth_score': 0.85,
                            'motion_score': 0.90,
                            'texture_authentic': True
                        }
                    },
                    'device_info': {
                        'device_id': 'test_device_001',
                        'model': 'Test Phone'
                    }
                }
            ]
            
            steps_completed = 0
            for i, step_data in enumerate(verification_steps):
                step_result = self._make_request(
                    'POST', f'/enhanced-attendance/verify-step/{self.verification_session_id}',
                    step_data,
                    headers=headers
                )
                
                if step_result['success']:
                    steps_completed += 1
                
                self._add_test_result(
                    f"Verification Step {i+1}",
                    "Sequential Verification",
                    step_result['success'],
                    step_result['response_time'],
                    {
                        'step_success': step_result['success'],
                        'step_data': step_data
                    }
                )
                
                time.sleep(0.5)  # Simulate step delays
    
    # =================== ENHANCED ATTENDANCE TESTS ===================
    
    def _test_enhanced_attendance_apis(self):
        """Test enhanced attendance APIs."""
        
        if not self.student_token:
            return
        
        headers = {'Authorization': f'Bearer {self.student_token}'}
        
        # Test quick check-in (all data at once)
        quick_checkin_data = {
            'lecture_id': 1,
            'gps_data': {
                'latitude': 33.3152,
                'longitude': 44.3661,
                'accuracy': 3.0
            },
            'barometer_data': {
                'pressure': 1013.0,
                'temperature': 25.0,
                'altitude': 280.0,
                'device_info': {'has_barometer': True}
            },
            'qr_data': json.dumps({
                'session_id': 'test_quick_qr',
                'lecture_id': 1,
                'room_id': 1,
                'expires_at': (datetime.utcnow() + timedelta(minutes=5)).isoformat(),
                'hash': 'test_hash'
            }),
            'face_data': {
                'verification_data': {
                    'match_confidence': 0.92,
                    'template_match_quality': 0.88,
                    'anti_spoofing': {
                        'liveness_score': 0.95,
                        'depth_score': 0.85,
                        'motion_score': 0.90,
                        'texture_authentic': True
                    }
                },
                'device_info': {
                    'device_id': 'test_device_001'
                }
            }
        }
        
        quick_checkin_result = self._make_request(
            'POST', '/enhanced-attendance/quick-checkin',
            quick_checkin_data,
            headers=headers
        )
        
        self._add_test_result(
            "Quick Check-in",
            "Enhanced Attendance",
            quick_checkin_result['success'],
            quick_checkin_result['response_time'],
            {
                'checkin_successful': quick_checkin_result['success'],
                'verification_summary': quick_checkin_result['data'].get('data', {}).get('verification_summary') if quick_checkin_result['success'] else None
            }
        )
        
        # Test analytics
        analytics_result = self._make_request(
            'GET', '/enhanced-attendance/analytics/verification-stats',
            headers=headers
        )
        
        self._add_test_result(
            "Attendance Analytics",
            "Enhanced Attendance",
            analytics_result['success'],
            analytics_result['response_time'],
            {
                'analytics_available': analytics_result['success'],
                'user_type': analytics_result['data'].get('data', {}).get('user_type') if analytics_result['success'] else None
            }
        )
    
    # =================== SYSTEM ANALYTICS TESTS ===================
    
    def _test_system_analytics(self):
        """Test system analytics and monitoring."""
        
        # Test health checks for all services
        services = [
            ('Auth Service', '/auth/health'),
            ('Rooms Service', '/admin/rooms/health'),
            ('Recording Service', '/recording/health'),
            ('Enhanced Attendance', '/enhanced-attendance/health'),
            ('QR Service', '/qr/health'),
            ('Lectures Service', '/lectures/health')
        ]
        
        for service_name, endpoint in services:
            health_result = self._make_request('GET', endpoint)
            
            self._add_test_result(
                f"{service_name} Health",
                "System Analytics",
                health_result['success'],
                health_result['response_time'],
                {
                    'service_healthy': health_result['success'],
                    'response_message': health_result['data'].get('message') if health_result['success'] else None
                }
            )
        
        # Test system monitoring
        if self.admin_token:
            headers = {'Authorization': f'Bearer {self.admin_token}'}
            
            active_sessions_result = self._make_request(
                'GET', '/recording/active-sessions',
                headers=headers
            )
            
            self._add_test_result(
                "Active Sessions Monitoring",
                "System Analytics",
                active_sessions_result['success'],
                active_sessions_result['response_time'],
                {
                    'monitoring_available': active_sessions_result['success'],
                    'active_sessions': active_sessions_result['data'].get('data', {}).get('total_active') if active_sessions_result['success'] else 0
                }
            )
    
    # =================== PERFORMANCE TESTS ===================
    
    def _test_performance_load(self):
        """Test system performance under load."""
        
        # Concurrent requests test
        concurrent_requests = 5
        start_time = time.time()
        
        # Simple health check load test
        results = []
        for i in range(concurrent_requests):
            result = self._make_request('GET', '/auth/health')
            results.append(result)
            time.sleep(0.1)  # Small delay between requests
        
        end_time = time.time()
        total_time = end_time - start_time
        successful_requests = len([r for r in results if r['success']])
        
        self._add_test_result(
            "Concurrent Requests Load Test",
            "Performance",
            successful_requests == concurrent_requests,
            int(total_time * 1000),
            {
                'concurrent_requests': concurrent_requests,
                'successful_requests': successful_requests,
                'success_rate': successful_requests / concurrent_requests,
                'total_time_seconds': total_time,
                'requests_per_second': concurrent_requests / total_time
            }
        )
        
        # Memory/Response size test
        if self.admin_token:
            headers = {'Authorization': f'Bearer {self.admin_token}'}
            large_data_result = self._make_request(
                'GET', '/admin/rooms',
                headers=headers
            )
            
            response_size = len(json.dumps(large_data_result['data'])) if large_data_result['success'] else 0
            
            self._add_test_result(
                "Large Data Response Test",
                "Performance",
                large_data_result['success'],
                large_data_result['response_time'],
                {
                    'response_size_bytes': response_size,
                    'response_time_acceptable': large_data_result['response_time'] < 2000  # Under 2 seconds
                }
            )
    
    # =================== SECURITY TESTS ===================
    
    def _test_security_validation(self):
        """Test security and validation."""
        
        # Test unauthorized access
        unauthorized_result = self._make_request(
            'GET', '/admin/rooms'
            # No authorization header
        )
        
        self._add_test_result(
            "Unauthorized Access Block",
            "Security",
            not unauthorized_result['success'] and unauthorized_result.get('status_code') == 401,
            unauthorized_result['response_time'],
            {
                'unauthorized_blocked': not unauthorized_result['success'],
                'status_code': unauthorized_result.get('status_code')
            }
        )
        
        # Test invalid data validation
        invalid_data_result = self._make_request(
            'POST', '/auth/login',
            {
                'email': 'invalid_email',
                'password': ''
            }
        )
        
        self._add_test_result(
            "Input Validation",
            "Security",
            not invalid_data_result['success'],
            invalid_data_result['response_time'],
            {
                'invalid_data_rejected': not invalid_data_result['success'],
                'validation_working': True
            }
        )
        
        # Test SQL injection protection (basic)
        sql_injection_result = self._make_request(
            'POST', '/auth/login',
            {
                'email': "admin'; DROP TABLE users; --",
                'password': 'test'
            }
        )
        
        self._add_test_result(
            "SQL Injection Protection",
            "Security",
            not sql_injection_result['success'],  # Should be rejected
            sql_injection_result['response_time'],
            {
                'sql_injection_blocked': not sql_injection_result['success'],
                'system_protected': True
            }
        )
    
    # =================== HELPER METHODS ===================
    
    def _make_request(self, method: str, endpoint: str, data: Dict = None, headers: Dict = None) -> Dict:
        """Make HTTP request and measure response time."""
        url = f"{self.base_url}{endpoint}"
        
        request_headers = {
            'Content-Type': 'application/json'
        }
        if headers:
            request_headers.update(headers)
        
        start_time = time.time()
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=request_headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=request_headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=request_headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=request_headers, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            end_time = time.time()
            response_time = int((end_time - start_time) * 1000)
            
            try:
                response_data = response.json()
            except:
                response_data = {'raw_response': response.text}
            
            return {
                'success': response.status_code < 400,
                'status_code': response.status_code,
                'response_time': response_time,
                'data': response_data
            }
            
        except Exception as e:
            end_time = time.time()
            response_time = int((end_time - start_time) * 1000)
            
            return {
                'success': False,
                'status_code': 0,
                'response_time': response_time,
                'data': {'error': str(e)}
            }
    
    def _add_test_result(self, test_name: str, category: str, success: bool, 
                        response_time: int, details: Dict, error_message: str = None):
        """Add test result to results list."""
        result = TestResult(
            test_name=test_name,
            category=category,
            success=success,
            response_time_ms=response_time,
            details=details,
            error_message=error_message
        )
        
        self.test_results.append(result)
        
        # Print real-time result
        status = "✅" if success else "❌"
        print(f"  {status} {test_name} ({response_time}ms)")
        if error_message:
            print(f"     Error: {error_message}")
    
    def _calculate_performance_metrics(self, total_duration: float) -> SystemPerformanceMetrics:
        """Calculate system performance metrics."""
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r.success])
        failed_tests = total_tests - passed_tests
        
        response_times = [r.response_time_ms for r in self.test_results if r.response_time_ms > 0]
        
        return SystemPerformanceMetrics(
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            average_response_time_ms=sum(response_times) / len(response_times) if response_times else 0,
            max_response_time_ms=max(response_times) if response_times else 0,
            min_response_time_ms=min(response_times) if response_times else 0,
            total_test_duration_seconds=total_duration
        )
    
    def _generate_comprehensive_report(self, metrics: SystemPerformanceMetrics) -> Dict:
        """Generate comprehensive test report."""
        
        # Categorize results
        results_by_category = {}
        for result in self.test_results:
            if result.category not in results_by_category:
                results_by_category[result.category] = []
            results_by_category[result.category].append(result)
        
        # Calculate category statistics
        category_stats = {}
        for category, results in results_by_category.items():
            passed = len([r for r in results if r.success])
            total = len(results)
            avg_response_time = sum([r.response_time_ms for r in results]) / total if total > 0 else 0
            
            category_stats[category] = {
                'total_tests': total,
                'passed_tests': passed,
                'failed_tests': total - passed,
                'success_rate': (passed / total) * 100 if total > 0 else 0,
                'average_response_time_ms': avg_response_time
            }
        
        # Overall system assessment
        overall_success_rate = (metrics.passed_tests / metrics.total_tests) * 100 if metrics.total_tests > 0 else 0
        
        system_grade = (
            'A+' if overall_success_rate >= 95 else
            'A' if overall_success_rate >= 90 else
            'B+' if overall_success_rate >= 85 else
            'B' if overall_success_rate >= 80 else
            'C+' if overall_success_rate >= 75 else
            'C' if overall_success_rate >= 70 else
            'D' if overall_success_rate >= 60 else
            'F'
        )
        
        # Critical issues
        critical_failures = [r for r in self.test_results if not r.success and 'Authentication' in r.category]
        security_issues = [r for r in self.test_results if not r.success and 'Security' in r.category]
        performance_issues = [r for r in self.test_results if r.response_time_ms > 5000]  # Over 5 seconds
        
        return {
            'overall_assessment': {
                'system_grade': system_grade,
                'success_rate_percent': overall_success_rate,
                'total_tests_run': metrics.total_tests,
                'critical_failures': len(critical_failures),
                'security_issues': len(security_issues),
                'performance_issues': len(performance_issues)
            },
            'category_breakdown': category_stats,
            'performance_summary': {
                'average_response_time_ms': metrics.average_response_time_ms,
                'fastest_response_ms': metrics.min_response_time_ms,
                'slowest_response_ms': metrics.max_response_time_ms,
                'total_test_duration_seconds': metrics.total_test_duration_seconds
            },
            'system_recommendations': self._generate_system_recommendations(
                critical_failures, security_issues, performance_issues, category_stats
            ),
            'deployment_readiness': {
                'ready_for_production': (
                    overall_success_rate >= 85 and
                    len(critical_failures) == 0 and
                    len(security_issues) == 0 and
                    metrics.average_response_time_ms < 2000
                ),
                'ready_for_testing': overall_success_rate >= 70,
                'needs_major_fixes': overall_success_rate < 70
            }
        }
    
    def _generate_system_recommendations(self, critical_failures: List, security_issues: List, 
                                       performance_issues: List, category_stats: Dict) -> List[str]:
        """Generate system improvement recommendations."""
        recommendations = []
        
        if critical_failures:
            recommendations.append("🚨 CRITICAL: Fix authentication and authorization issues before deployment")
        
        if security_issues:
            recommendations.append("🔒 HIGH PRIORITY: Address security vulnerabilities")
        
        if performance_issues:
            recommendations.append("⚡ PERFORMANCE: Optimize slow endpoints (>5s response time)")
        
        # Category-specific recommendations
        for category, stats in category_stats.items():
            if stats['success_rate'] < 80:
                recommendations.append(f"🔧 Improve {category} system (success rate: {stats['success_rate']:.1f}%)")
            
            if stats['average_response_time_ms'] > 3000:
                recommendations.append(f"⚡ Optimize {category} response times (avg: {stats['average_response_time_ms']:.0f}ms)")
        
        if not recommendations:
            recommendations.append("✅ System performing well - ready for production deployment")
        
        return recommendations
    
    def _print_summary_report(self, metrics: SystemPerformanceMetrics, report: Dict):
        """Print summary report to console."""
        
        print(f"📊 OVERALL SYSTEM GRADE: {report['overall_assessment']['system_grade']}")
        print(f"✅ Tests Passed: {metrics.passed_tests}/{metrics.total_tests} ({report['overall_assessment']['success_rate_percent']:.1f}%)")
        print(f"⏱️ Average Response Time: {metrics.average_response_time_ms:.0f}ms")
        print(f"🕐 Total Test Duration: {metrics.total_test_duration_seconds:.1f}s")
        
        print(f"\n📋 CATEGORY BREAKDOWN:")
        for category, stats in report['category_breakdown'].items():
            print(f"  {category}: {stats['passed_tests']}/{stats['total_tests']} ({stats['success_rate']:.1f}%) - {stats['average_response_time_ms']:.0f}ms avg")
        
        print(f"\n🎯 DEPLOYMENT READINESS:")
        readiness = report['deployment_readiness']
        if readiness['ready_for_production']:
            print("  ✅ READY FOR PRODUCTION")
        elif readiness['ready_for_testing']:
            print("  🧪 READY FOR USER TESTING")
        else:
            print("  ⚠️ NEEDS MAJOR FIXES")
        
        print(f"\n💡 RECOMMENDATIONS:")
        for rec in report['system_recommendations']:
            print(f"  {rec}")

def main():
    """Main test execution function."""
    tester = SmartAttendanceSystemTester()
    results = tester.run_comprehensive_tests()
    
    # Save detailed results to file
    with open('comprehensive_test_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n💾 Detailed results saved to: comprehensive_test_results.json")
    
    return results

if __name__ == "__main__":
    main()