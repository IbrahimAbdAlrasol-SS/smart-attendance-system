
# backend/app/api/attendance.py - Updated
"""Attendance API endpoints with triple verification."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.attendance import AttendanceRecord, AttendanceSession
from app.models.user import User, UserRole
from app.models.room import Room
from app.models.lecture import Lecture
from app.services.qr_service import QRService
from app.services.gps_service import GPSService
from app.utils.helpers import success_response, error_response
from datetime import datetime

attendance_bp = Blueprint('attendance', __name__)

@attendance_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Attendance service is running')

@attendance_bp.route('/verify-location', methods=['POST'])
@jwt_required()
def verify_location():
    """Step 1: Verify GPS location and altitude."""
    try:
        data = request.get_json()
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if user.role != UserRole.STUDENT:
            return error_response("Only students can mark attendance", 403)
        
        # Required fields
        required = ['latitude', 'longitude', 'altitude', 'lecture_id']
        for field in required:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Get lecture and room
        lecture = Lecture.query.get_or_404(data['lecture_id'])
        room = lecture.room
        
        # Check if lecture is active
        now = datetime.utcnow()
        if now < lecture.start_time or now > lecture.end_time:
            return error_response("Lecture is not active at this time", 400)
        
        # Verify GPS location
        gps_result = GPSService.verify_location(
            user_lat=data['latitude'],
            user_lng=data['longitude'],
            room=room
        )
        
        if not gps_result['is_inside']:
            return error_response(
                f"أنت خارج القاعة. يجب أن تكون داخل قاعة {room.name} - المسافة: {gps_result['distance']:.1f} متر",
                400
            )
        
        # Verify altitude
        altitude_result = GPSService.verify_altitude(
            user_altitude=data['altitude'],
            room_altitude=room.altitude,
            tolerance=3.0  # 3 meters tolerance
        )
        
        if not altitude_result['is_valid']:
            return error_response(
                f"أنت في الطابق الخطأ. فرق الارتفاع: {altitude_result['difference']:.1f} متر",
                400
            )
        
        # Create temporary verification token (valid for 2 minutes)
        verification_token = GPSService.create_verification_token(
            user_id=current_user_id,
            lecture_id=lecture.id,
            room_id=room.id
        )
        
        return success_response(
            data={
                'location_verified': True,
                'verification_token': verification_token,
                'room': room.name,
                'expires_in': 120  # seconds
            },
            message="الموقع صحيح. يمكنك الآن مسح رمز QR"
        )
        
    except Exception as e:
        return error_response(f"Error verifying location: {str(e)}", 500)

@attendance_bp.route('/checkin', methods=['POST'])
@jwt_required()
def check_in():
    """Complete attendance check-in with all verifications."""
    try:
        data = request.get_json()
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if user.role != UserRole.STUDENT:
            return error_response("Only students can mark attendance", 403)
        
        # Required fields
        required = ['qr_data', 'verification_token', 'face_verified']
        for field in required:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Step 1: Verify location token
        token_valid, token_data = GPSService.verify_token(data['verification_token'])
        if not token_valid:
            return error_response("Location verification expired. Please verify location again", 401)
        
        if token_data['user_id'] != current_user_id:
            return error_response("Invalid verification token", 401)
        
        # Step 2: Validate QR code
        is_valid, qr_info, error_msg = QRService.validate_qr_code(data['qr_data'])
        if not is_valid:
            return error_response(error_msg or "Invalid QR code", 400)
        
        # Verify QR matches the lecture
        if qr_info['lecture_id'] != token_data['lecture_id']:
            return error_response("QR code doesn't match the verified lecture", 400)
        
        # Get attendance session
        session = AttendanceSession.query.filter_by(
            qr_code=qr_info['session_id'],
            is_active=True
        ).first()
        
        if not session:
            return error_response("Invalid or expired attendance session", 400)
        
        # Step 3: Verify face recognition
        if not data.get('face_verified', False):
            return error_response("Face verification failed", 401)
        
        # Check if already marked attendance
        existing = AttendanceRecord.query.filter_by(
            student_id=current_user_id,
            lecture_id=session.lecture_id
        ).first()
        
        if existing:
            return error_response("Attendance already marked for this lecture", 400)
        
        # Create attendance record
        attendance = AttendanceRecord(
            student_id=current_user_id,
            lecture_id=session.lecture_id,
            session_id=session.id,
            check_in_time=datetime.utcnow(),
            verification_method='triple',  # GPS + QR + Face
            is_present=True
        )
        
        db.session.add(attendance)
        
        # Update session stats
        session.total_present += 1
        
        db.session.commit()
        
        return success_response(
            data={
                'attendance_id': attendance.id,
                'lecture': session.lecture.title,
                'room': session.lecture.room.name,
                'check_in_time': attendance.check_in_time.isoformat()
            },
            message="تم تسجيل حضورك بنجاح"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error marking attendance: {str(e)}", 500)

@attendance_bp.route('/my-records', methods=['GET'])
@jwt_required()
def get_my_attendance():
    """Get student's attendance records."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if user.role != UserRole.STUDENT:
            return error_response("Only students can view their attendance", 403)
        
        # Get filters
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        subject = request.args.get('subject')
        
        # Build query
        query = AttendanceRecord.query.filter_by(student_id=current_user_id)
        
        if from_date:
            query = query.filter(AttendanceRecord.check_in_time >= datetime.fromisoformat(from_date))
        if to_date:
            query = query.filter(AttendanceRecord.check_in_time <= datetime.fromisoformat(to_date))
        
        records = query.order_by(AttendanceRecord.check_in_time.desc()).all()
        
        # Format response
        attendance_data = []
        for record in records:
            lecture = record.lecture
            attendance_data.append({
                'id': record.id,
                'lecture': lecture.title,
                'room': lecture.room.name,
                'teacher': lecture.teacher.name,
                'check_in_time': record.check_in_time.isoformat(),
                'is_present': record.is_present,
                'verification_method': record.verification_method
            })
        
        # Calculate statistics
        total_lectures = len(records)
        present_count = len([r for r in records if r.is_present])
        attendance_rate = (present_count / total_lectures * 100) if total_lectures > 0 else 0
        
        return success_response(
            data={
                'records': attendance_data,
                'statistics': {
                    'total_lectures': total_lectures,
                    'present': present_count,
                    'absent': total_lectures - present_count,
                    'attendance_rate': round(attendance_rate, 2)
                }
            }
        )
        
    except Exception as e:
        return error_response(f"Error fetching attendance records: {str(e)}", 500)
