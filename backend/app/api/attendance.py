# File: backend/app/api/attendance.py
"""Attendance API endpoints with triple verification."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.attendance import AttendanceRecord
from app.models.attendance_session import AttendanceSession
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
        
        # Verify GPS location (inside polygon)
        is_inside = room.is_location_inside(data['latitude'], data['longitude'])
        
        if not is_inside:
            return error_response(
                f"أنت خارج القاعة. يجب أن تكون داخل قاعة {room.name}",
                400
            )
        
        # Verify altitude
        altitude_valid = room.is_altitude_valid(data['altitude'])
        
        if not altitude_valid:
            return error_response(
                f"أنت في الطابق الخطأ. يجب أن تكون في الطابق {room.floor}",
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
                'altitude_verified': True,
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
        
        # Check if student has registered face
        student = user.student_profile
        if not student.face_registered:
            return error_response("Please register your face first", 400)
        
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
            gps_verified=True,
            altitude_verified=True,
            qr_verified=True,
            face_verified=True,
            is_present=True,
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
            altitude=data.get('altitude')
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

@attendance_bp.route('/exceptional-checkin', methods=['POST'])
@jwt_required()
def exceptional_check_in():
    """Handle exceptional attendance (GPS failed but other checks passed)."""
    try:
        data = request.get_json()
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if user.role != UserRole.STUDENT:
            return error_response("Only students can mark attendance", 403)
        
        # Required fields
        required = ['qr_data', 'face_verified', 'exception_reason']
        for field in required:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Validate QR code
        is_valid, qr_info, error_msg = QRService.validate_qr_code(data['qr_data'])
        if not is_valid:
            return error_response(error_msg or "Invalid QR code", 400)
        
        # Get attendance session
        session = AttendanceSession.query.filter_by(
            qr_code=qr_info['session_id'],
            is_active=True
        ).first()
        
        if not session:
            return error_response("Invalid or expired attendance session", 400)
        
        # Verify face recognition
        if not data.get('face_verified', False):
            return error_response("Face verification failed", 401)
        
        # Check if already marked attendance
        existing = AttendanceRecord.query.filter_by(
            student_id=current_user_id,
            lecture_id=session.lecture_id
        ).first()
        
        if existing:
            return error_response("Attendance already marked for this lecture", 400)
        
        # Create exceptional attendance record (needs approval)
        attendance = AttendanceRecord(
            student_id=current_user_id,
            lecture_id=session.lecture_id,
            session_id=session.id,
            check_in_time=datetime.utcnow(),
            verification_method='emergency',
            gps_verified=False,
            altitude_verified=data.get('altitude_verified', False),
            qr_verified=True,
            face_verified=True,
            is_present=False,  # Not present until approved
            is_exceptional=True,
            exception_reason=data.get('exception_reason'),
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
            altitude=data.get('altitude')
        )
        
        db.session.add(attendance)
        db.session.commit()
        
        # TODO: Send notification to teacher for approval
        
        return success_response(
            data={
                'attendance_id': attendance.id,
                'status': 'pending_approval',
                'lecture': session.lecture.title,
                'room': session.lecture.room.name,
                'check_in_time': attendance.check_in_time.isoformat()
            },
            message="تم تسجيل حضورك الاستثنائي. في انتظار موافقة المدرس"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error marking exceptional attendance: {str(e)}", 500)

@attendance_bp.route('/approve/<int:attendance_id>', methods=['POST'])
@jwt_required()
def approve_attendance(attendance_id):
    """Approve exceptional attendance (teacher only)."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user.is_teacher():
            return error_response("Only teachers can approve attendance", 403)
        
        # Get attendance record
        attendance = AttendanceRecord.query.get_or_404(attendance_id)
        
        # Verify teacher owns the lecture
        if attendance.lecture.teacher_id != current_user_id:
            return error_response("You can only approve attendance for your lectures", 403)
        
        # Update attendance
        attendance.is_present = True
        attendance.approved_by = current_user_id
        attendance.approved_at = datetime.utcnow()
        
        db.session.commit()
        
        return success_response(
            message="Attendance approved successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error approving attendance: {str(e)}", 500)

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
                'is_exceptional': record.is_exceptional,
                'verification_method': record.verification_method,
                'approved': record.approved_by is not None
            })
        
        # Calculate statistics
        total_lectures = len(records)
        present_count = len([r for r in records if r.is_present])
        pending_count = len([r for r in records if r.is_exceptional and not r.is_present])
        attendance_rate = (present_count / total_lectures * 100) if total_lectures > 0 else 0
        
        return success_response(
            data={
                'records': attendance_data,
                'statistics': {
                    'total_lectures': total_lectures,
                    'present': present_count,
                    'absent': total_lectures - present_count - pending_count,
                    'pending': pending_count,
                    'attendance_rate': round(attendance_rate, 2)
                }
            }
        )
        
    except Exception as e:
        return error_response(f"Error fetching attendance records: {str(e)}", 500)
