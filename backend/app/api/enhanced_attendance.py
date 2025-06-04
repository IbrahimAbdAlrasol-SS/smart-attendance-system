# File: backend/app/api/enhanced_attendance.py
"""Enhanced Attendance API with Sequential Verification Integration."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, limiter
from app.models.attendance import AttendanceRecord
from app.models.attendance_session import AttendanceSession
from app.models.user import User, UserRole
from app.models.room import Room
from app.models.lecture import Lecture
from app.models.student import Student

# Import our enhanced services
from app.services.sequential_verification_service import (
    SequentialVerificationService, 
    SequentialVerificationSession,
    VerificationStep,
    VerificationStatus
)
from app.services.face_recognition_service import FaceRecognitionService
from app.services.barometer_service import BarometerService
from app.services.qr_service import QRService
from app.services.gps_service import GPSService

from app.utils.helpers import success_response, error_response
from app.utils.decorators import student_required, teacher_required
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json

enhanced_attendance_bp = Blueprint('enhanced_attendance', __name__)

# Session storage for verification sessions (use Redis in production)
active_verification_sessions: Dict[str, SequentialVerificationSession] = {}

# =================== HEALTH CHECK ===================

@enhanced_attendance_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Enhanced Attendance service is running')

# =================== FACE REGISTRATION APIs ===================

@enhanced_attendance_bp.route('/register-face', methods=['POST'])
@jwt_required()
@student_required
@limiter.limit("3 per hour")
def register_face_biometric():
    """Register face biometric for first-time use."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        # Get student profile
        student = Student.query.filter_by(user_id=current_user_id).first()
        if not student:
            return error_response("Student profile not found", 404)
        
        if student.face_registered:
            return error_response("Face already registered. Use face reset if needed.", 400)
        
        # Validate required fields
        required_fields = ['template_data', 'device_info']
        for field in required_fields:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Process face registration
        registration_result = FaceRecognitionService.register_face_template(
            student_id=current_user_id,
            template_data=data['template_data'],
            device_info=data['device_info']
        )
        
        if not registration_result.success:
            return error_response(registration_result.error_message, 400)
        
        # Update student profile
        student.face_registered = True
        student.face_registered_at = datetime.utcnow()
        # In production, store encrypted template hash securely
        student.face_template_hash = registration_result.encrypted_template_hash
        db.session.commit()
        
        return success_response(
            data={
                'registration_successful': True,
                'registration_token': registration_result.registration_token,
                'quality_score': registration_result.template_quality_score,
                'registered_at': registration_result.registration_timestamp.isoformat()
            },
            message="تم تسجيل بصمة الوجه بنجاح"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error registering face: {str(e)}", 500)

@enhanced_attendance_bp.route('/face-registration-flow', methods=['GET'])
@jwt_required()
@student_required
def get_face_registration_flow():
    """Get face registration flow instructions."""
    try:
        current_user_id = get_jwt_identity()
        
        # Get student profile
        student = Student.query.filter_by(user_id=current_user_id).first()
        if not student:
            return error_response("Student profile not found", 404)
        
        if student.face_registered:
            return success_response(
                data={
                    'already_registered': True,
                    'registered_at': student.face_registered_at.isoformat() if student.face_registered_at else None
                },
                message="Face already registered"
            )
        
        # Generate registration flow
        from app.services.face_recognition_service import FaceRecognitionIntegration
        flow = FaceRecognitionIntegration.create_initial_registration_flow(current_user_id)
        
        return success_response(
            data=flow,
            message="Face registration flow generated"
        )
        
    except Exception as e:
        return error_response(f"Error getting registration flow: {str(e)}", 500)

# =================== SEQUENTIAL VERIFICATION APIs ===================

@enhanced_attendance_bp.route('/start-verification', methods=['POST'])
@jwt_required()
@student_required
@limiter.limit("10 per minute")
def start_verification_session():
    """Start new sequential verification session for attendance."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['lecture_id']
        for field in required_fields:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        lecture_id = data['lecture_id']
        
        # Get lecture and validate
        lecture = Lecture.query.get_or_404(lecture_id)
        
        # Check if lecture is active
        now = datetime.utcnow()
        if now < lecture.start_time or now > lecture.end_time:
            return error_response("Lecture is not active at this time", 400)
        
        # Check if student already has attendance for this lecture
        existing_attendance = AttendanceRecord.query.filter_by(
            student_id=current_user_id,
            lecture_id=lecture_id
        ).first()
        
        if existing_attendance:
            return error_response("Attendance already recorded for this lecture", 400)
        
        # Check if student has registered face
        student = Student.query.filter_by(user_id=current_user_id).first()
        if not student or not student.face_registered:
            return error_response("Face biometric not registered. Please register first.", 400)
        
        # Create verification session
        session = SequentialVerificationService.create_verification_session(
            student_id=current_user_id,
            lecture_id=lecture_id,
            initial_data=data
        )
        
        # Store session
        active_verification_sessions[session.session_id] = session
        
        return success_response(
            data={
                'verification_session_id': session.session_id,
                'current_step': session.current_step.value,
                'lecture': {
                    'id': lecture.id,
                    'title': lecture.title,
                    'room': lecture.room,
                    'start_time': lecture.start_time.isoformat(),
                    'end_time': lecture.end_time.isoformat()
                },
                'verification_flow': {
                    'step_1': {
                        'name': 'GPS Location',
                        'description': 'التحقق من موقعك داخل القاعة',
                        'required_data': ['latitude', 'longitude', 'accuracy']
                    },
                    'step_2': {
                        'name': 'Barometer Altitude',
                        'description': 'التحقق من الطابق الصحيح',
                        'required_data': ['pressure', 'temperature', 'altitude']
                    },
                    'step_3': {
                        'name': 'QR Code',
                        'description': 'مسح رمز QR من شاشة المدرس',
                        'required_data': ['qr_data']
                    },
                    'step_4': {
                        'name': 'Face Recognition',
                        'description': 'التحقق من بصمة الوجه',
                        'required_data': ['verification_data', 'device_info']
                    }
                }
            },
            message="تم بدء جلسة التحقق - ابدأ بالتحقق من الموقع"
        )
        
    except Exception as e:
        return error_response(f"Error starting verification session: {str(e)}", 500)

@enhanced_attendance_bp.route('/verify-step/<session_id>', methods=['POST'])
@jwt_required()
@student_required
def process_verification_step(session_id: str):
    """Process a verification step in the sequential flow."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        # Get verification session
        if session_id not in active_verification_sessions:
            return error_response("Verification session not found or expired", 404)
        
        session = active_verification_sessions[session_id]
        
        # Validate session ownership
        if session.student_id != current_user_id:
            return error_response("Unauthorized access to verification session", 403)
        
        # Check session expiry
        if datetime.utcnow() > session.started_at + timedelta(minutes=10):
            del active_verification_sessions[session_id]
            return error_response("Verification session expired", 408)
        
        # Process the current step
        updated_session, step_result = SequentialVerificationService.process_verification_step(
            session=session,
            step_data=data
        )
        
        # Update stored session
        active_verification_sessions[session_id] = updated_session
        
        # Prepare response
        response_data = {
            'session_id': session_id,
            'step_completed': step_result.step.value,
            'step_result': {
                'success': step_result.success,
                'status': step_result.status.value,
                'confidence_score': step_result.confidence_score,
                'warnings': step_result.warnings,
                'errors': step_result.errors,
                'processing_time_ms': step_result.processing_time_ms
            },
            'session_status': {
                'current_step': updated_session.current_step.value if updated_session.completed_at is None else 'COMPLETED',
                'overall_status': updated_session.overall_status.value,
                'steps_completed': len(updated_session.steps_completed),
                'total_processing_time_ms': updated_session.total_processing_time_ms
            }
        }
        
        # If session is completed, finalize attendance
        if updated_session.completed_at:
            attendance_result = await_finalize_attendance(updated_session)
            response_data['attendance_result'] = attendance_result
            
            # Clean up session
            del active_verification_sessions[session_id]
        
        # Generate appropriate message
        if step_result.success:
            if updated_session.completed_at:
                if updated_session.final_decision == "APPROVED":
                    message = "✅ تم تسجيل حضورك بنجاح"
                elif updated_session.final_decision == "APPROVED_WITH_WARNINGS":
                    message = "⚠️ تم تسجيل حضورك مع تحذيرات"
                else:
                    message = "❌ تم رفض تسجيل الحضور"
            else:
                message = f"✅ تم التحقق من {step_result.step.value} - انتقل للخطوة التالية"
        else:
            if step_result.step in [VerificationStep.QR_CODE, VerificationStep.FACE_RECOGNITION]:
                message = f"❌ فشل في {step_result.step.value} - تم رفض التسجيل"
            else:
                message = f"⚠️ تحذير في {step_result.step.value} - يمكن المتابعة"
        
        return success_response(
            data=response_data,
            message=message
        )
        
    except Exception as e:
        return error_response(f"Error processing verification step: {str(e)}", 500)

def await_finalize_attendance(session: SequentialVerificationSession) -> Dict:
    """Finalize attendance record based on verification session."""
    try:
        # Create attendance record
        attendance = AttendanceRecord(
            student_id=session.student_id,
            lecture_id=session.lecture_id,
            check_in_time=datetime.utcnow(),
            verification_method='sequential_triple',
            is_present=(session.attendance_type in ['normal', 'exceptional']),
            is_exceptional=(session.attendance_type == 'exceptional'),
            notes=f"Sequential verification: {session.final_decision}"
        )
        
        # Add verification details from session
        verification_summary = SequentialVerificationService.get_session_summary(session)
        attendance.verification_details = json.dumps(verification_summary)
        
        # Set location data from GPS step if available
        gps_result = next((r for r in session.steps_completed if r.step == VerificationStep.GPS_LOCATION), None)
        if gps_result and gps_result.data:
            attendance.latitude = gps_result.data.get('user_location', {}).get('latitude')
            attendance.longitude = gps_result.data.get('user_location', {}).get('longitude')
        
        # Set barometer data if available
        barometer_result = next((r for r in session.steps_completed if r.step == VerificationStep.BAROMETER_ALTITUDE), None)
        if barometer_result and barometer_result.data:
            attendance.altitude = barometer_result.data.get('reading_altitude')
        
        db.session.add(attendance)
        db.session.commit()
        
        return {
            'attendance_id': attendance.id,
            'attendance_type': session.attendance_type,
            'final_decision': session.final_decision,
            'overall_confidence': SequentialVerificationService.calculate_overall_confidence(session),
            'verification_summary': verification_summary
        }
        
    except Exception as e:
        db.session.rollback()
        raise Exception(f"Error finalizing attendance: {str(e)}")

@enhanced_attendance_bp.route('/session-status/<session_id>', methods=['GET'])
@jwt_required()
@student_required
def get_verification_session_status(session_id: str):
    """Get current verification session status."""
    try:
        current_user_id = get_jwt_identity()
        
        if session_id not in active_verification_sessions:
            return error_response("Verification session not found", 404)
        
        session = active_verification_sessions[session_id]
        
        if session.student_id != current_user_id:
            return error_response("Unauthorized access to verification session", 403)
        
        # Get comprehensive session summary
        summary = SequentialVerificationService.get_session_summary(session)
        
        return success_response(
            data=summary,
            message="Verification session status"
        )
        
    except Exception as e:
        return error_response(f"Error getting session status: {str(e)}", 500)

# =================== LEGACY SUPPORT APIs ===================

@enhanced_attendance_bp.route('/quick-checkin', methods=['POST'])
@jwt_required()
@student_required
@limiter.limit("5 per minute")
def quick_checkin():
    """Quick check-in with all data at once (for testing/legacy support)."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['lecture_id', 'gps_data', 'barometer_data', 'qr_data', 'face_data']
        for field in required_fields:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Start verification session
        session = SequentialVerificationService.create_verification_session(
            student_id=current_user_id,
            lecture_id=data['lecture_id'],
            initial_data=data
        )
        
        # Process all steps sequentially
        steps_data = [
            data['gps_data'],
            data['barometer_data'],
            data['qr_data'],
            data['face_data']
        ]
        
        for step_data in steps_data:
            session, step_result = SequentialVerificationService.process_verification_step(
                session=session,
                step_data=step_data
            )
            
            # Stop if hard failure
            if (step_result.step in [VerificationStep.QR_CODE, VerificationStep.FACE_RECOGNITION] 
                and not step_result.success):
                break
        
        # Finalize if completed
        attendance_result = None
        if session.completed_at:
            attendance_result = await_finalize_attendance(session)
        
        # Generate summary
        summary = SequentialVerificationService.get_session_summary(session)
        
        return success_response(
            data={
                'verification_summary': summary,
                'attendance_result': attendance_result
            },
            message=f"Quick check-in: {session.final_decision or 'IN_PROGRESS'}"
        )
        
    except Exception as e:
        return error_response(f"Error in quick check-in: {str(e)}", 500)

# =================== TEACHER MANAGEMENT APIs ===================

@enhanced_attendance_bp.route('/teacher/sessions', methods=['GET'])
@jwt_required()
@teacher_required
def get_teacher_verification_sessions():
    """Get verification sessions for teacher's lectures."""
    try:
        current_user_id = get_jwt_identity()
        
        # Get teacher's lectures
        teacher_lectures = Lecture.query.filter_by(
            teacher_id=current_user_id,
            is_active=True
        ).all()
        
        lecture_ids = [lecture.id for lecture in teacher_lectures]
        
        # Filter active sessions for teacher's lectures
        teacher_sessions = [
            session for session in active_verification_sessions.values()
            if session.lecture_id in lecture_ids
        ]
        
        # Get summaries
        sessions_data = []
        for session in teacher_sessions:
            summary = SequentialVerificationService.get_session_summary(session)
            sessions_data.append(summary)
        
        return success_response(
            data={
                'active_sessions': sessions_data,
                'total_active': len(sessions_data),
                'lectures_monitored': len(lecture_ids)
            },
            message=f"Found {len(sessions_data)} active verification sessions"
        )
        
    except Exception as e:
        return error_response(f"Error getting teacher sessions: {str(e)}", 500)

@enhanced_attendance_bp.route('/teacher/approve-exceptional/<int:attendance_id>', methods=['POST'])
@jwt_required()
@teacher_required
def approve_exceptional_attendance(attendance_id: int):
    """Approve exceptional attendance record."""
    try:
        current_user_id = get_jwt_identity()
        
        # Get attendance record
        attendance = AttendanceRecord.query.get_or_404(attendance_id)
        
        # Verify teacher owns the lecture
        lecture = Lecture.query.get(attendance.lecture_id)
        if not lecture or lecture.teacher_id != current_user_id:
            return error_response("You can only approve attendance for your lectures", 403)
        
        # Check if it's exceptional attendance
        if not attendance.is_exceptional:
            return error_response("This attendance is not marked as exceptional", 400)
        
        # Approve attendance
        attendance.is_present = True
        attendance.approved_by = current_user_id
        attendance.approved_at = datetime.utcnow()
        
        db.session.commit()
        
        return success_response(
            data={
                'attendance_id': attendance.id,
                'approved_at': attendance.approved_at.isoformat(),
                'approved_by': current_user_id
            },
            message="Exceptional attendance approved successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error approving attendance: {str(e)}", 500)

# =================== ANALYTICS APIs ===================

@enhanced_attendance_bp.route('/analytics/verification-stats', methods=['GET'])
@jwt_required()
def get_verification_analytics():
    """Get verification system analytics."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        # Basic stats
        if user.role == UserRole.STUDENT:
            # Student's own stats
            student_attendance = AttendanceRecord.query.filter_by(
                student_id=current_user_id
            ).all()
            
            total_attempts = len(student_attendance)
            successful_checkins = len([a for a in student_attendance if a.is_present])
            exceptional_checkins = len([a for a in student_attendance if a.is_exceptional])
            
            stats = {
                'user_type': 'student',
                'total_attempts': total_attempts,
                'successful_checkins': successful_checkins,
                'exceptional_checkins': exceptional_checkins,
                'success_rate': (successful_checkins / total_attempts * 100) if total_attempts > 0 else 0
            }
            
        else:
            # Teacher/Admin stats
            stats = {
                'user_type': 'teacher_admin',
                'active_sessions': len(active_verification_sessions),
                'system_status': 'operational'
            }
        
        return success_response(
            data=stats,
            message="Verification analytics"
        )
        
    except Exception as e:
        return error_response(f"Error getting analytics: {str(e)}", 500)

# =================== SYSTEM UTILITIES ===================

@enhanced_attendance_bp.route('/cleanup-expired-sessions', methods=['POST'])
@jwt_required()
@teacher_required
def cleanup_expired_sessions():
    """Clean up expired verification sessions."""
    try:
        current_time = datetime.utcnow()
        expired_sessions = []
        
        for session_id, session in list(active_verification_sessions.items()):
            if current_time > session.started_at + timedelta(minutes=10):
                expired_sessions.append(session_id)
                del active_verification_sessions[session_id]
        
        return success_response(
            data={
                'cleaned_sessions': len(expired_sessions),
                'remaining_active': len(active_verification_sessions)
            },
            message=f"Cleaned up {len(expired_sessions)} expired sessions"
        )
        
    except Exception as e:
        return error_response(f"Error cleaning up sessions: {str(e)}", 500)