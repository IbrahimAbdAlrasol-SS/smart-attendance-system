
# backend/app/api/qr.py
"""QR Code API endpoints."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, limiter
from app.models.lecture import Lecture
from app.models.attendance_session import AttendanceSession
from app.models.user import User
from app.services.qr_service import QRService
from app.utils.helpers import success_response, error_response
from app.utils.decorators import teacher_required
from datetime import datetime, timedelta

qr_bp = Blueprint('qr', __name__)

@qr_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='QR service is running')

@qr_bp.route('/generate/<int:lecture_id>', methods=['POST'])
@jwt_required()
@teacher_required
@limiter.limit("30 per hour")
def generate_qr(lecture_id):
    """Generate QR code for lecture attendance."""
    try:
        # Get current user
        current_user_id = get_jwt_identity()
        
        # Get lecture
        lecture = Lecture.query.get_or_404(lecture_id)
        
        # Verify teacher owns this lecture
        if lecture.teacher_id != current_user_id:
            return error_response("You can only generate QR for your own lectures", 403)
        
        # Check if lecture is active (within time range)
        now = datetime.utcnow()
        if now < lecture.start_time or now > lecture.end_time:
            return error_response("Lecture is not active at this time", 400)
        
        # Get QR expiry time from request or use default
        expires_in = request.get_json().get('expires_in_seconds', 60)
        if expires_in < 30 or expires_in > 300:
            expires_in = 60  # Default to 60 seconds
        
        # Generate QR code
        session_id, qr_image, expires_at = QRService.generate_qr_code(
            lecture_id=lecture_id,
            room_id=lecture.room_id,
            expires_in_seconds=expires_in
        )
        
        # Create attendance session
        session = AttendanceSession(
            lecture_id=lecture_id,
            qr_code=session_id,
            expires_at=datetime.fromisoformat(expires_at)
        )
        db.session.add(session)
        db.session.commit()
        
        return success_response(
            data={
                'session_id': session_id,
                'qr_image': qr_image,
                'expires_at': expires_at,
                'expires_in': expires_in,
                'lecture': {
                    'id': lecture.id,
                    'title': lecture.title,
                    'room': lecture.room.name
                }
            },
            message="QR code generated successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error generating QR code: {str(e)}", 500)

@qr_bp.route('/validate', methods=['POST'])
@jwt_required()
def validate_qr():
    """Validate QR code data."""
    try:
        data = request.get_json()
        
        if 'qr_data' not in data:
            return error_response("QR data is required", 400)
        
        # Validate QR code
        is_valid, qr_info, error_msg = QRService.validate_qr_code(data['qr_data'])
        
        if not is_valid:
            return error_response(error_msg or "Invalid QR code", 400)
        
        # Check if session exists
        session = AttendanceSession.query.filter_by(
            qr_code=qr_info['session_id']
        ).first()
        
        if not session or not session.is_active:
            return error_response("Invalid or inactive session", 400)
        
        return success_response(
            data={
                'valid': True,
                'session_id': qr_info['session_id'],
                'lecture_id': qr_info['lecture_id'],
                'room_id': qr_info['room_id'],
                'expires_at': qr_info['expires_at']
            },
            message="QR code is valid"
        )
        
    except Exception as e:
        return error_response(f"Error validating QR code: {str(e)}", 500)

@qr_bp.route('/batch-generate', methods=['POST'])
@jwt_required()
@teacher_required
@limiter.limit("5 per minute")
def batch_generate_qr_codes():
    """Generate QR codes for multiple lectures in batch."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data or 'lecture_ids' not in data:
            return error_response("Lecture IDs are required", 400)
        
        lecture_ids = data['lecture_ids']
        if not isinstance(lecture_ids, list) or len(lecture_ids) == 0:
            return error_response("Valid lecture IDs list is required", 400)
        
        if len(lecture_ids) > 10:
            return error_response("Maximum 10 lectures allowed per batch", 400)
        
        expires_in_seconds = data.get('expires_in_seconds', 300)  # 5 minutes default
        
        # Validate all lectures exist and user has permission
        lectures = Lecture.query.filter(Lecture.id.in_(lecture_ids)).all()
        
        if len(lectures) != len(lecture_ids):
            return error_response("Some lecture IDs not found", 404)
        
        # Check permissions for all lectures
        for lecture in lectures:
            if not (lecture.teacher_id == current_user_id or 
                    User.query.get(current_user_id).role in [UserRole.ADMIN, UserRole.COORDINATOR]):
                return error_response(f"Access denied for lecture {lecture.id}", 403)
        
        # Generate QR codes for all lectures
        qr_results = []
        for lecture in lectures:
            try:
                # Get room for QR generation
                room = None
                if lecture.room:
                    room = Room.query.filter_by(name=lecture.room).first()
                
                room_id = room.id if room else None
                
                session_id, qr_image, expires_at = QRService.generate_qr_code(
                    lecture_id=lecture.id,
                    room_id=room_id,
                    expires_in_seconds=expires_in_seconds
                )
                
                # Create attendance session
                session = AttendanceSession(
                    lecture_id=lecture.id,
                    qr_code=session_id,
                    expires_at=datetime.fromisoformat(expires_at),
                    is_active=True
                )
                db.session.add(session)
                
                qr_results.append({
                    'lecture_id': lecture.id,
                    'lecture_title': lecture.title,
                    'session_id': session_id,
                    'qr_image': qr_image,
                    'expires_at': expires_at,
                    'expires_in_seconds': expires_in_seconds,
                    'room': lecture.room
                })
                
            except Exception as e:
                qr_results.append({
                    'lecture_id': lecture.id,
                    'lecture_title': lecture.title,
                    'error': str(e)
                })
        
        db.session.commit()
        
        successful_count = len([r for r in qr_results if 'error' not in r])
        
        return success_response(
            data={
                'qr_codes': qr_results,
                'summary': {
                    'total_requested': len(lecture_ids),
                    'successful': successful_count,
                    'failed': len(lecture_ids) - successful_count
                }
            },
            message=f"Generated {successful_count} QR codes successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Failed to generate batch QR codes: {str(e)}", 500)

@qr_bp.route('/invalidate-all', methods=['DELETE'])
@jwt_required()
@teacher_required
@limiter.limit("3 per minute")
def invalidate_all_qr_codes():
    """Invalidate all active QR codes for current user's lectures."""
    try:
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)
        
        # Get lectures based on user role
        if current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            # Admin can invalidate all QR codes
            lecture_ids = [l.id for l in Lecture.query.all()]
        elif current_user.role == UserRole.COORDINATOR:
            # Coordinator can invalidate QR codes for their section
            lecture_ids = [l.id for l in Lecture.query.all()]  # Simplified - in production, filter by section
        else:
            # Teachers can only invalidate their own lecture QR codes
            lecture_ids = [l.id for l in Lecture.query.filter_by(teacher_id=current_user_id).all()]
        
        if not lecture_ids:
            return success_response(
                data={'invalidated_count': 0},
                message="No QR codes to invalidate"
            )
        
        # Invalidate all active sessions for these lectures
        invalidated_count = AttendanceSession.query.filter(
            AttendanceSession.lecture_id.in_(lecture_ids),
            AttendanceSession.is_active == True
        ).update({'is_active': False}, synchronize_session=False)
        
        db.session.commit()
        
        return success_response(
            data={
                'invalidated_count': invalidated_count,
                'affected_lectures': len(lecture_ids)
            },
            message=f"Invalidated {invalidated_count} QR codes successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Failed to invalidate QR codes: {str(e)}", 500)

@qr_bp.route('/analytics', methods=['GET'])
@jwt_required()
@limiter.limit("10 per minute")
def get_qr_analytics():
    """Get QR code usage analytics."""
    try:
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)
        
        # Get date range
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        
        # Build base query based on user role
        if current_user.role in [UserRole.ADMIN, UserRole.COORDINATOR]:
            sessions_query = AttendanceSession.query
        else:
            # Teachers can only see their own QR analytics
            teacher_lecture_ids = [l.id for l in Lecture.query.filter_by(teacher_id=current_user_id).all()]
            sessions_query = AttendanceSession.query.filter(
                AttendanceSession.lecture_id.in_(teacher_lecture_ids)
            )
        
        # Apply date filters
        if from_date:
            try:
                from_dt = datetime.fromisoformat(from_date)
                sessions_query = sessions_query.filter(AttendanceSession.created_at >= from_dt)
            except ValueError:
                return error_response("Invalid from_date format", 400)
        
        if to_date:
            try:
                to_dt = datetime.fromisoformat(to_date)
                sessions_query = sessions_query.filter(AttendanceSession.created_at <= to_dt)
            except ValueError:
                return error_response("Invalid to_date format", 400)
        
        sessions = sessions_query.all()
        
        # Calculate analytics
        total_generated = len(sessions)
        active_sessions = len([s for s in sessions if s.is_active])
        expired_sessions = len([s for s in sessions if not s.is_active and s.expires_at < datetime.utcnow()])
        
        # Usage statistics
        usage_by_lecture = {}
        usage_by_day = {}
        
        for session in sessions:
            # By lecture
            lecture = Lecture.query.get(session.lecture_id)
            if lecture:
                lecture_title = lecture.title
                if lecture_title not in usage_by_lecture:
                    usage_by_lecture[lecture_title] = {
                        'total_generated': 0,
                        'total_scans': 0
                    }
                usage_by_lecture[lecture_title]['total_generated'] += 1
                
                # Count attendance records using this QR
                qr_attendance_count = AttendanceRecord.query.filter(
                    AttendanceRecord.lecture_id == session.lecture_id,
                    AttendanceRecord.verification_method == 'qr'
                ).count()
                usage_by_lecture[lecture_title]['total_scans'] += qr_attendance_count
            
            # By day
            day = session.created_at.date().isoformat()
            if day not in usage_by_day:
                usage_by_day[day] = 0
            usage_by_day[day] += 1
        
        # Calculate average scan rate
        total_scans = sum([AttendanceRecord.query.filter(
            AttendanceRecord.lecture_id == s.lecture_id,
            AttendanceRecord.verification_method == 'qr'
        ).count() for s in sessions])
        
        avg_scan_rate = round((total_scans / total_generated), 2) if total_generated > 0 else 0
        
        return success_response(
            data={
                'overview': {
                    'total_generated': total_generated,
                    'active_sessions': active_sessions,
                    'expired_sessions': expired_sessions,
                    'total_scans': total_scans,
                    'average_scan_rate': avg_scan_rate
                },
                'usage_by_lecture': usage_by_lecture,
                'daily_generation': dict(sorted(usage_by_day.items())),
                'date_range': {
                    'from': from_date,
                    'to': to_date
                }
            },
            message="QR analytics retrieved successfully"
        )
        
    except Exception as e:
        return error_response(f"Failed to get QR analytics: {str(e)}", 500)

@qr_bp.route('/custom-duration', methods=['POST'])
@jwt_required()
@teacher_required
@limiter.limit("10 per minute")
def generate_custom_duration_qr():
    """Generate QR code with custom expiration duration."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        # Validate input
        required_fields = ['lecture_id', 'duration_minutes']
        for field in required_fields:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        lecture_id = data['lecture_id']
        duration_minutes = data['duration_minutes']
        
        # Validate duration (1 minute to 24 hours)
        if not isinstance(duration_minutes, (int, float)) or duration_minutes < 1 or duration_minutes > 1440:
            return error_response("Duration must be between 1 and 1440 minutes (24 hours)", 400)
        
        # Get and validate lecture
        lecture = Lecture.query.get_or_404(lecture_id)
        
        if not (lecture.teacher_id == current_user_id or 
                User.query.get(current_user_id).role in [UserRole.ADMIN, UserRole.COORDINATOR]):
            return error_response("Access denied", 403)
        
        # Get room information
        room = None
        if lecture.room:
            room = Room.query.filter_by(name=lecture.room).first()
        
        room_id = room.id if room else None
        expires_in_seconds = int(duration_minutes * 60)
        
        # Generate QR code
        session_id, qr_image, expires_at = QRService.generate_qr_code(
            lecture_id=lecture_id,
            room_id=room_id,
            expires_in_seconds=expires_in_seconds
        )
        
        # Invalidate previous active sessions for this lecture
        AttendanceSession.query.filter_by(
            lecture_id=lecture_id,
            is_active=True
        ).update({'is_active': False})
        
        # Create new attendance session
        session = AttendanceSession(
            lecture_id=lecture_id,
            qr_code=session_id,
            expires_at=datetime.fromisoformat(expires_at),
            is_active=True
        )
        db.session.add(session)
        db.session.commit()
        
        return success_response(
            data={
                'session_id': session_id,
                'qr_image': qr_image,
                'expires_at': expires_at,
                'duration_minutes': duration_minutes,
                'lecture_info': {
                    'id': lecture.id,
                    'title': lecture.title,
                    'room': lecture.room
                }
            },
            message=f"Custom QR code generated with {duration_minutes} minutes duration"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Failed to generate custom duration QR: {str(e)}", 500)

