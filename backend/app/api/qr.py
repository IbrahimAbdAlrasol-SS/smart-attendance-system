
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

