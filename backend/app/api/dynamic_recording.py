"""Dynamic room recording APIs for real-time 3D room boundary capture."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, limiter
from app.models.user import User, UserRole
from app.models.room import Room
from app.services.barometer_service import BarometerService, BarometerReading
from app.utils.helpers import success_response, error_response
from app.utils.decorators import admin_required
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import uuid
import redis
import json

# Redis client for session management (if available)
try:
    import redis
    redis_client = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)
except:
    redis_client = None

recording_bp = Blueprint('recording', __name__)

# =================== SESSION MANAGEMENT ===================

class RecordingSession:
    """Recording session management."""
    
    def __init__(self, session_id: str, user_id: int, room_name: str):
        self.session_id = session_id
        self.user_id = user_id
        self.room_name = room_name
        self.started_at = datetime.utcnow()
        self.is_active = True
        self.recorded_points = []
        self.barometer_readings = []
        self.calibration_data = None
        self.ground_reference = None
        
    def to_dict(self) -> Dict:
        return {
            'session_id': self.session_id,
            'user_id': self.user_id,
            'room_name': self.room_name,
            'started_at': self.started_at.isoformat(),
            'is_active': self.is_active,
            'points_recorded': len(self.recorded_points),
            'barometer_readings': len(self.barometer_readings),
            'has_calibration': self.calibration_data is not None
        }

# Session storage (in production, use Redis)
active_sessions: Dict[str, RecordingSession] = {}

# =================== HEALTH CHECK ===================

@recording_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Dynamic recording service is running')

# =================== CALIBRATION APIs ===================

@recording_bp.route('/calibrate-ground', methods=['POST'])
@jwt_required()
@admin_required
@limiter.limit("10 per minute")
def calibrate_ground_reference():
    """Calibrate ground reference pressure for accurate floor detection."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['pressure_readings', 'ground_altitude']
        for field in required_fields:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Process pressure readings
        readings = []
        for reading_data in data['pressure_readings']:
            reading = BarometerService.process_barometer_reading(
                raw_pressure=reading_data['pressure'],
                temperature=reading_data.get('temperature'),
                humidity=reading_data.get('humidity'),
                device_info=reading_data.get('device_info')
            )
            readings.append(reading)
        
        # Calibrate ground reference
        calibration_result = BarometerService.calibrate_ground_reference(
            readings=readings,
            known_ground_altitude=data['ground_altitude']
        )
        
        if not calibration_result['success']:
            return error_response(calibration_result['error'], 400)
        
        # Store calibration data (in production, use database)
        calibration_key = f"ground_calibration:{current_user_id}"
        calibration_data = {
            'user_id': current_user_id,
            'calibrated_at': datetime.utcnow().isoformat(),
            'calibration_result': calibration_result,
            'location': data.get('location', 'Ground floor')
        }
        
        # Store in Redis if available, otherwise in memory
        if redis_client:
            redis_client.setex(
                calibration_key, 
                21600,  # 6 hours
                json.dumps(calibration_data, default=str)
            )
        
        return success_response(
            data={
                'calibration': calibration_result,
                'calibration_id': calibration_key,
                'valid_until': (datetime.utcnow() + timedelta(hours=6)).isoformat()
            },
            message="تم معايرة المرجع الأرضي بنجاح"
        )
        
    except Exception as e:
        return error_response(f"Error in ground calibration: {str(e)}", 500)

@recording_bp.route('/verify-floor', methods=['POST'])
@jwt_required()
def verify_current_floor():
    """Verify current floor based on barometer reading."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['pressure', 'building_id']
        for field in required_fields:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Get ground calibration
        calibration_key = f"ground_calibration:{current_user_id}"
        ground_reference = None
        
        if redis_client:
            calibration_data = redis_client.get(calibration_key)
            if calibration_data:
                calibration_info = json.loads(calibration_data)
                ground_reference = calibration_info['calibration_result']['ground_reference_pressure']
        
        if not ground_reference:
            return error_response("No ground reference calibration found. Please calibrate first.", 400)
        
        # Process current reading
        reading = BarometerService.process_barometer_reading(
            raw_pressure=data['pressure'],
            temperature=data.get('temperature'),
            humidity=data.get('humidity'),
            device_info=data.get('device_info')
        )
        
        # Detect floor
        floor_result = BarometerService.detect_floor_from_pressure(
            reading=reading,
            reference_ground_pressure=ground_reference,
            building_id=data['building_id']
        )
        
        return success_response(
            data={
                'floor_detection': floor_result.__dict__,
                'reading_info': reading.__dict__,
                'calibration_used': calibration_key
            },
            message=f"تم كشف الطابق: {floor_result.detected_floor}"
        )
        
    except Exception as e:
        return error_response(f"Error in floor verification: {str(e)}", 500)

# =================== RECORDING SESSION APIs ===================

@recording_bp.route('/start-session', methods=['POST'])
@jwt_required()
@admin_required
def start_recording_session():
    """Start new dynamic recording session for room boundary capture."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['room_name', 'building', 'floor']
        for field in required_fields:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Check if room already exists
        existing_room = Room.query.filter_by(name=data['room_name']).first()
        if existing_room:
            return error_response(f"Room {data['room_name']} already exists", 400)
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        
        # Create recording session
        session = RecordingSession(
            session_id=session_id,
            user_id=current_user_id,
            room_name=data['room_name']
        )
        
        # Store session data
        session.building = data['building']
        session.floor = data['floor']
        session.room_type = data.get('room_type', 'classroom')
        session.expected_capacity = data.get('capacity', 30)
        
        # Store in memory (in production, use Redis)
        active_sessions[session_id] = session
        
        return success_response(
            data={
                'session_id': session_id,
                'session_info': session.to_dict(),
                'instructions': {
                    'step_1': 'قم بمعايرة البارومتر في منتصف القاعة',
                    'step_2': 'ابدأ المشي حول حدود القاعة ببطء',
                    'step_3': 'حافظ على معدل نقطة واحدة كل 2-3 ثواني',
                    'step_4': 'أكمل الدائرة للعودة لنقطة البداية'
                }
            },
            message=f"تم بدء تسجيل القاعة {data['room_name']}"
        )
        
    except Exception as e:
        return error_response(f"Error starting recording session: {str(e)}", 500)

@recording_bp.route('/add-point/<session_id>', methods=['POST'])
@jwt_required()
@limiter.limit("30 per minute")  # High frequency for real-time recording
def add_recording_point(session_id: str):
    """Add GPS + barometer point to recording session."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        # Validate session
        if session_id not in active_sessions:
            return error_response("Recording session not found", 404)
        
        session = active_sessions[session_id]
        
        if session.user_id != current_user_id:
            return error_response("Unauthorized access to recording session", 403)
        
        if not session.is_active:
            return error_response("Recording session is not active", 400)
        
        # Validate required point data
        required_fields = ['latitude', 'longitude', 'pressure']
        for field in required_fields:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Process barometer reading
        barometer_reading = BarometerService.process_barometer_reading(
            raw_pressure=data['pressure'],
            temperature=data.get('temperature'),
            humidity=data.get('humidity'),
            device_info=data.get('device_info', {})
        )
        
        # Create combined point
        point = {
            'sequence': len(session.recorded_points),
            'latitude': data['latitude'],
            'longitude': data['longitude'],
            'gps_altitude': data.get('altitude'),
            'barometer_reading': barometer_reading.__dict__,
            'timestamp': datetime.utcnow().isoformat(),
            'accuracy': data.get('gps_accuracy'),
            'speed': data.get('speed', 0),  # Walking speed for quality assessment
        }
        
        # Add to session
        session.recorded_points.append(point)
        session.barometer_readings.append(barometer_reading)
        
        # Real-time quality checks
        quality_check = _perform_real_time_quality_check(session, point)
        
        return success_response(
            data={
                'point_added': point,
                'session_stats': {
                    'total_points': len(session.recorded_points),
                    'recording_duration': (datetime.utcnow() - session.started_at).total_seconds(),
                    'avg_accuracy': _calculate_avg_accuracy(session.recorded_points)
                },
                'quality_check': quality_check,
                'recommendations': _generate_recording_recommendations(session, quality_check)
            },
            message=f"تم إضافة النقطة {point['sequence']}"
        )
        
    except Exception as e:
        return error_response(f"Error adding recording point: {str(e)}", 500)

@recording_bp.route('/session-status/<session_id>', methods=['GET'])
@jwt_required()
def get_session_status(session_id: str):
    """Get current recording session status and statistics."""
    try:
        current_user_id = get_jwt_identity()
        
        if session_id not in active_sessions:
            return error_response("Recording session not found", 404)
        
        session = active_sessions[session_id]
        
        if session.user_id != current_user_id:
            return error_response("Unauthorized access to recording session", 403)
        
        # Calculate session statistics
        stats = _calculate_session_statistics(session)
        
        return success_response(
            data={
                'session_info': session.to_dict(),
                'statistics': stats,
                'current_path': session.recorded_points[-10:] if session.recorded_points else [],  # Last 10 points
                'quality_assessment': _assess_overall_quality(session)
            }
        )
        
    except Exception as e:
        return error_response(f"Error getting session status: {str(e)}", 500)

@recording_bp.route('/complete-session/<session_id>', methods=['POST'])
@jwt_required()
@admin_required
def complete_recording_session(session_id: str):
    """Complete recording session and create room from captured data."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json() or {}
        
        if session_id not in active_sessions:
            return error_response("Recording session not found", 404)
        
        session = active_sessions[session_id]
        
        if session.user_id != current_user_id:
            return error_response("Unauthorized access to recording session", 403)
        
        # Validate minimum requirements
        if len(session.recorded_points) < 3:
            return error_response("Need at least 3 points to create room", 400)
        
        # Final quality assessment
        quality_assessment = _assess_overall_quality(session)
        
        if quality_assessment['overall_score'] < 0.5:
            return error_response(
                f"Recording quality too low: {quality_assessment['overall_score']:.2f}. Minimum required: 0.5",
                400
            )
        
        # Process barometer path data
        barometer_path_result = BarometerService.track_room_recording_path(
            readings=session.barometer_readings,
            gps_path=[{
                'lat': p['latitude'],
                'lng': p['longitude'],
                'alt': p.get('gps_altitude', 0)
            } for p in session.recorded_points]
        )
        
        if not barometer_path_result['success']:
            return error_response(barometer_path_result['error'], 400)
        
        # Prepare room creation data
        room_data = {
            'name': session.room_name,
            'building': getattr(session, 'building', 'المبنى الرئيسي'),
            'floor': getattr(session, 'floor', 1),
            'room_type': getattr(session, 'room_type', 'classroom'),
            'capacity': getattr(session, 'expected_capacity', 30),
            'gps_boundaries': [{
                'lat': p['latitude'],
                'lng': p['longitude'],
                'alt': p['barometer_reading']['altitude_estimate_m']
            } for p in session.recorded_points],
            'ground_altitude': data.get('ground_altitude', 0),
            'floor_altitude': _calculate_floor_altitude(session.barometer_readings),
            'room_floor_altitude': _calculate_room_floor_altitude(session.barometer_readings),
            'ceiling_height': data.get('ceiling_height', 3.5),
            'pressure_range': _calculate_pressure_range(session.barometer_readings),
            'recorded_by': current_user_id,
            'recording_path': session.recorded_points,
            'quality_metadata': quality_assessment,
            'barometer_path_data': barometer_path_result
        }
        
        # Create room
        room = Room.create_from_dynamic_recording(room_data)
        db.session.add(room)
        db.session.commit()
        
        # Mark session as completed
        session.is_active = False
        
        # Clean up session after successful creation
        del active_sessions[session_id]
        
        return success_response(
            data={
                'room': room.to_dict(include_3d=True),
                'recording_summary': {
                    'session_id': session_id,
                    'points_recorded': len(session.recorded_points),
                    'recording_duration': (datetime.utcnow() - session.started_at).total_seconds(),
                    'quality_score': quality_assessment['overall_score'],
                    'barometer_consistency': barometer_path_result['altitude_consistency']
                }
            },
            message=f"تم إنشاء القاعة {session.room_name} بنجاح"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error completing recording session: {str(e)}", 500)

@recording_bp.route('/cancel-session/<session_id>', methods=['DELETE'])
@jwt_required()
def cancel_recording_session(session_id: str):
    """Cancel recording session without saving."""
    try:
        current_user_id = get_jwt_identity()
        
        if session_id not in active_sessions:
            return error_response("Recording session not found", 404)
        
        session = active_sessions[session_id]
        
        if session.user_id != current_user_id:
            return error_response("Unauthorized access to recording session", 403)
        
        # Clean up session
        del active_sessions[session_id]
        
        return success_response(
            message=f"تم إلغاء تسجيل القاعة {session.room_name}"
        )
        
    except Exception as e:
        return error_response(f"Error canceling recording session: {str(e)}", 500)

@recording_bp.route('/active-sessions', methods=['GET'])
@jwt_required()
@admin_required
def get_active_sessions():
    """Get all active recording sessions."""
    try:
        current_user_id = get_jwt_identity()
        
        # Filter sessions for current user or all if super admin
        user = User.query.get(current_user_id)
        if user.role == UserRole.SUPER_ADMIN:
            sessions = list(active_sessions.values())
        else:
            sessions = [s for s in active_sessions.values() if s.user_id == current_user_id]
        
        return success_response(
            data={
                'active_sessions': [session.to_dict() for session in sessions],
                'total_active': len(sessions)
            }
        )
        
    except Exception as e:
        return error_response(f"Error getting active sessions: {str(e)}", 500)

# =================== HELPER FUNCTIONS ===================

def _perform_real_time_quality_check(session: RecordingSession, point: Dict) -> Dict:
    """Perform real-time quality checks on recording point."""
    checks = {
        'gps_accuracy': True,
        'movement_speed': True,
        'barometer_consistency': True,
        'sequence_gap': True
    }
    
    # GPS accuracy check
    if point.get('accuracy') and point['accuracy'] > 10:  # meters
        checks['gps_accuracy'] = False
    
    # Movement speed check (should be walking speed)
    if point.get('speed') and point['speed'] > 2.0:  # m/s (7.2 km/h)
        checks['movement_speed'] = False
    
    # Barometer consistency (basic check)
    if len(session.barometer_readings) > 1:
        last_reading = session.barometer_readings[-2]
        current_reading = session.barometer_readings[-1]
        pressure_diff = abs(current_reading.pressure_hpa - last_reading.pressure_hpa)
        if pressure_diff > 2.0:  # Large pressure change
            checks['barometer_consistency'] = False
    
    return {
        'checks': checks,
        'overall_ok': all(checks.values()),
        'warnings': [k for k, v in checks.items() if not v]
    }

def _calculate_avg_accuracy(points: List[Dict]) -> float:
    """Calculate average GPS accuracy."""
    accuracies = [p.get('accuracy', 0) for p in points if p.get('accuracy')]
    return sum(accuracies) / len(accuracies) if accuracies else 0

def _generate_recording_recommendations(session: RecordingSession, quality_check: Dict) -> List[str]:
    """Generate real-time recording recommendations."""
    recommendations = []
    
    if not quality_check['overall_ok']:
        for warning in quality_check['warnings']:
            if warning == 'gps_accuracy':
                recommendations.append("انتقل لمكان مفتوح أكثر لتحسين دقة GPS")
            elif warning == 'movement_speed':
                recommendations.append("امشِ ببطء أكثر للحصول على قراءات دقيقة")
            elif warning == 'barometer_consistency':
                recommendations.append("تأكد من استقرار الجهاز وعدم تغطية البارومتر")
    
    if len(session.recorded_points) < 5:
        recommendations.append("استمر في المشي حول حدود القاعة")
    elif len(session.recorded_points) > 50:
        recommendations.append("تقترب من الانتهاء - تأكد من إغلاق الدائرة")
    
    return recommendations

def _calculate_session_statistics(session: RecordingSession) -> Dict:
    """Calculate comprehensive session statistics."""
    if not session.recorded_points:
        return {}
    
    points = session.recorded_points
    
    return {
        'total_points': len(points),
        'recording_duration_seconds': (datetime.utcnow() - session.started_at).total_seconds(),
        'avg_gps_accuracy': _calculate_avg_accuracy(points),
        'coverage_area_estimate': _estimate_coverage_area(points),
        'barometer_stats': {
            'readings_count': len(session.barometer_readings),
            'pressure_range': {
                'min': min(r.pressure_hpa for r in session.barometer_readings),
                'max': max(r.pressure_hpa for r in session.barometer_readings)
            } if session.barometer_readings else {}
        }
    }

def _assess_overall_quality(session: RecordingSession) -> Dict:
    """Assess overall recording quality."""
    if not session.recorded_points or not session.barometer_readings:
        return {'overall_score': 0.0, 'details': 'No data available'}
    
    score = 0.0
    details = {}
    
    # GPS accuracy score (0-0.3)
    avg_accuracy = _calculate_avg_accuracy(session.recorded_points)
    gps_score = max(0, 0.3 * (1 - avg_accuracy / 20))  # 20m max penalty
    score += gps_score
    details['gps_score'] = gps_score
    
    # Point density score (0-0.2)
    area_estimate = _estimate_coverage_area(session.recorded_points)
    point_density = len(session.recorded_points) / max(area_estimate, 1)
    density_score = min(0.2, point_density * 0.01)  # Optimal ~10-20 points per 100m²
    score += density_score
    details['density_score'] = density_score
    
    # Barometer consistency score (0-0.3)
    pressures = [r.pressure_hpa for r in session.barometer_readings]
    pressure_std = _calculate_standard_deviation(pressures)
    barometer_score = max(0, 0.3 * (1 - pressure_std / 5))  # 5 hPa max penalty
    score += barometer_score
    details['barometer_score'] = barometer_score
    
    # Path closure score (0-0.2)
    if len(session.recorded_points) >= 3:
        first_point = session.recorded_points[0]
        last_point = session.recorded_points[-1]
        closure_distance = _calculate_gps_distance(
            first_point['latitude'], first_point['longitude'],
            last_point['latitude'], last_point['longitude']
        )
        closure_score = max(0, 0.2 * (1 - closure_distance / 20))  # 20m max penalty
        score += closure_score
        details['closure_score'] = closure_score
    
    return {
        'overall_score': min(1.0, score),
        'details': details,
        'quality_level': 'excellent' if score > 0.8 else 'good' if score > 0.6 else 'fair' if score > 0.4 else 'poor'
    }

def _estimate_coverage_area(points: List[Dict]) -> float:
    """Estimate covered area from GPS points."""
    if len(points) < 3:
        return 0
    
    # Simple bounding box area estimate
    lats = [p['latitude'] for p in points]
    lngs = [p['longitude'] for p in points]
    
    lat_range = max(lats) - min(lats)
    lng_range = max(lngs) - min(lngs)
    
    # Convert to approximate meters (rough estimate)
    lat_meters = lat_range * 110540  # meters per degree latitude
    lng_meters = lng_range * 111320 * math.cos(math.radians(sum(lats) / len(lats)))
    
    return lat_meters * lng_meters

def _calculate_floor_altitude(readings: List[BarometerReading]) -> float:
    """Calculate floor altitude from barometer readings."""
    if not readings:
        return 0.0
    
    altitudes = [r.altitude_estimate_m for r in readings]
    return sum(altitudes) / len(altitudes)

def _calculate_room_floor_altitude(readings: List[BarometerReading]) -> float:
    """Calculate room floor altitude (same as floor for now)."""
    return _calculate_floor_altitude(readings)

def _calculate_pressure_range(readings: List[BarometerReading]) -> Dict:
    """Calculate pressure range from barometer readings."""
    if not readings:
        return {}
    
    pressures = [r.pressure_hpa for r in readings]
    return {
        'min': min(pressures),
        'max': max(pressures),
        'avg': sum(pressures) / len(pressures)
    }

def _calculate_standard_deviation(values: List[float]) -> float:
    """Calculate standard deviation."""
    if len(values) < 2:
        return 0.0
    
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)

def _calculate_gps_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between GPS points."""
    import math
    R = 6371000  # Earth radius in meters
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    
    a = (math.sin(delta_lat/2)**2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * 
         math.sin(delta_lng/2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c