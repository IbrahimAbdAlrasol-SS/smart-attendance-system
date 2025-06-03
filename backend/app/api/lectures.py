# backend/app/api/lectures.py
"""Lectures API endpoints - Full Implementation."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from app import db, limiter
from app.models.lecture import Lecture
from app.models.user import User, UserRole
from app.services.qr_service import QRService
from app.utils.helpers import success_response, error_response
from app.utils.validators import Validator

lectures_bp = Blueprint('lectures', __name__)

@lectures_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Lectures service is running')

@lectures_bp.route('/', methods=['GET'])
@jwt_required()
def get_lectures():
    """Get all lectures with pagination."""
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Get filter parameters
        teacher_id = request.args.get('teacher_id', type=int)
        room = request.args.get('room', type=str)
        date = request.args.get('date', type=str)
        
        # Build query
        query = Lecture.query.filter_by(is_active=True)
        
        if teacher_id:
            query = query.filter_by(teacher_id=teacher_id)
        if room:
            query = query.filter_by(room=room)
        if date:
            try:
                date_obj = datetime.fromisoformat(date)
                query = query.filter(
                    db.func.date(Lecture.start_time) == date_obj.date()
                )
            except:
                pass
        
        # Order by start time
        query = query.order_by(Lecture.start_time.desc())
        
        # Paginate
        pagination = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        # Prepare response
        lectures = []
        for lecture in pagination.items:
            lecture_data = lecture.to_dict()
            # Add teacher info
            teacher = User.query.get(lecture.teacher_id)
            if teacher:
                lecture_data['teacher'] = {
                    'id': teacher.id,
                    'name': teacher.name,
                    'email': teacher.email
                }
            lectures.append(lecture_data)
        
        return success_response(
            data=lectures,
            message=f"Found {len(lectures)} lectures",
            meta={
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages
            }
        )
        
    except Exception as e:
        return error_response(f"Failed to fetch lectures: {str(e)}", 500)

@lectures_bp.route('/<int:lecture_id>', methods=['GET'])
@jwt_required()
def get_lecture(lecture_id):
    """Get specific lecture details."""
    try:
        lecture = Lecture.query.get_or_404(lecture_id)
        
        lecture_data = lecture.to_dict()
        
        # Add teacher info
        teacher = User.query.get(lecture.teacher_id)
        if teacher:
            lecture_data['teacher'] = {
                'id': teacher.id,
                'name': teacher.name,
                'email': teacher.email
            }
        
        # Add attendance count if teacher
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if user and user.is_teacher():
            attendance_count = lecture.attendance_records.filter_by(is_present=True).count()
            lecture_data['attendance_count'] = attendance_count
        
        return success_response(data=lecture_data)
        
    except Exception as e:
        return error_response(f"Lecture not found: {str(e)}", 404)

@lectures_bp.route('/', methods=['POST'])
@jwt_required()
@limiter.limit("10 per hour")
def create_lecture():
    """Create new lecture (teachers only)."""
    try:
        # Check permissions
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or not user.is_teacher():
            return error_response("Only teachers can create lectures", 403)
        
        # Get request data
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        # Validate required fields
        required_fields = ['title', 'room', 'start_time', 'end_time']
        validation = Validator.validate_required_fields(data, required_fields)
        
        if not validation['is_valid']:
            return error_response(', '.join(validation['errors']), 400)
        
        # Parse dates
        try:
            start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
        except ValueError:
            return error_response("Invalid datetime format. Use ISO format", 400)
        
        # Validate times
        if start_time >= end_time:
            return error_response("End time must be after start time", 400)
        
        if start_time < datetime.utcnow():
            return error_response("Cannot create lectures in the past", 400)
        
        # Create lecture
        lecture = Lecture(
            title=data['title'].strip(),
            description=data.get('description', '').strip(),
            room=data['room'].strip().upper(),
            teacher_id=current_user_id,
            start_time=start_time,
            end_time=end_time
        )
        
        # Add location if provided
        if 'latitude' in data and 'longitude' in data:
            lecture.latitude = float(data['latitude'])
            lecture.longitude = float(data['longitude'])
        else:
            # Default to Baghdad coordinates
            lecture.latitude = 33.3152
            lecture.longitude = 44.3661
        
        db.session.add(lecture)
        db.session.commit()
        
        return success_response(
            data=lecture.to_dict(),
            message="Lecture created successfully"
        ), 201
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Failed to create lecture: {str(e)}", 500)

@lectures_bp.route('/<int:lecture_id>', methods=['PUT'])
@jwt_required()
def update_lecture(lecture_id):
    """Update lecture details (teachers only)."""
    try:
        # Get lecture
        lecture = Lecture.query.get_or_404(lecture_id)
        
        # Check permissions
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or (lecture.teacher_id != current_user_id and user.role != UserRole.ADMIN):
            return error_response("You can only update your own lectures", 403)
        
        # Get update data
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        # Update allowed fields
        if 'title' in data:
            lecture.title = data['title'].strip()
        
        if 'description' in data:
            lecture.description = data['description'].strip()
        
        if 'room' in data:
            lecture.room = data['room'].strip().upper()
        
        if 'start_time' in data:
            try:
                lecture.start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
            except ValueError:
                return error_response("Invalid start_time format", 400)
        
        if 'end_time' in data:
            try:
                lecture.end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
            except ValueError:
                return error_response("Invalid end_time format", 400)
        
        # Validate times
        if lecture.start_time >= lecture.end_time:
            return error_response("End time must be after start time", 400)
        
        # Update location if provided
        if 'latitude' in data:
            lecture.latitude = float(data['latitude'])
        if 'longitude' in data:
            lecture.longitude = float(data['longitude'])
        
        db.session.commit()
        
        return success_response(
            data=lecture.to_dict(),
            message="Lecture updated successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Failed to update lecture: {str(e)}", 500)

@lectures_bp.route('/<int:lecture_id>', methods=['DELETE'])
@jwt_required()
def delete_lecture(lecture_id):
    """Soft delete lecture (teachers only)."""
    try:
        # Get lecture
        lecture = Lecture.query.get_or_404(lecture_id)
        
        # Check permissions
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or (lecture.teacher_id != current_user_id and user.role != UserRole.ADMIN):
            return error_response("You can only delete your own lectures", 403)
        
        # Soft delete
        lecture.is_active = False
        db.session.commit()
        
        # Invalidate any active QR codes
        invalidated = QRService.invalidate_lecture_qr_codes(lecture_id)
        
        return success_response(
            message=f"Lecture deleted successfully. {invalidated} QR codes invalidated"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Failed to delete lecture: {str(e)}", 500)

@lectures_bp.route('/<int:lecture_id>/qr', methods=['POST'])
@jwt_required()
@limiter.limit("1 per 1.5 minutes")  # Rate limiting as per requirements
def generate_qr(lecture_id):
    """Generate QR code for lecture (teachers only)."""
    try:
        # Get lecture
        lecture = Lecture.query.get_or_404(lecture_id)
        
        # Check permissions
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or lecture.teacher_id != current_user_id:
            return error_response("Only the lecture teacher can generate QR codes", 403)
        
        # Generate QR code
        qr_data, error = QRService.generate_qr_code(lecture_id)
        
        if error:
            return error_response(error, 400)
        
        return success_response(
            data=qr_data,
            message="QR code generated successfully"
        )
        
    except Exception as e:
        return error_response(f"Failed to generate QR code: {str(e)}", 500)

@lectures_bp.route('/my-schedule', methods=['GET'])
@jwt_required()
def get_my_schedule():
    """Get current user's lecture schedule."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return error_response("User not found", 404)
        
        # Get date range
        date = request.args.get('date', datetime.utcnow().date().isoformat())
        
        try:
            target_date = datetime.fromisoformat(date).date()
        except:
            target_date = datetime.utcnow().date()
        
        if user.is_teacher():
            # Get teacher's lectures
            lectures = Lecture.query.filter(
                Lecture.teacher_id == current_user_id,
                Lecture.is_active == True,
                db.func.date(Lecture.start_time) == target_date
            ).order_by(Lecture.start_time).all()
        else:
            # For students - get all lectures for their section
            # This is a simplified version - in production, you'd have a proper enrollment system
            lectures = Lecture.query.filter(
                Lecture.is_active == True,
                db.func.date(Lecture.start_time) == target_date
            ).order_by(Lecture.start_time).all()
        
        schedule = []
        for lecture in lectures:
            lecture_data = lecture.to_dict()
            
            # Add teacher info
            if lecture.teacher_id != current_user_id:
                teacher = User.query.get(lecture.teacher_id)
                if teacher:
                    lecture_data['teacher'] = {
                        'name': teacher.name,
                        'email': teacher.email
                    }
            
            schedule.append(lecture_data)
        
        return success_response(
            data=schedule,
            message=f"Found {len(schedule)} lectures for {target_date}"
        )
        
    except Exception as e:
        return error_response(f"Failed to fetch schedule: {str(e)}", 500)

# Add missing fields to Lecture model
def add_location_to_lecture_model():
    """Helper to add location fields to Lecture model if missing."""
    # This would be done via migration in production
    # For now, we'll add them as class attributes
    if not hasattr(Lecture, 'latitude'):
        Lecture.latitude = db.Column(db.Float, nullable=True, default=33.3152)
    if not hasattr(Lecture, 'longitude'):
        Lecture.longitude = db.Column(db.Float, nullable=True, default=44.3661)