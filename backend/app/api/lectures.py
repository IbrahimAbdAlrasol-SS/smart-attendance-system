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


@lectures_bp.route('/<int:lecture_id>/attendance-summary', methods=['POST'])
@jwt_required()
@teacher_required
@limiter.limit("10 per minute")
def get_lecture_attendance_summary(lecture_id):
    """Get comprehensive attendance summary for a lecture."""
    try:
        current_user_id = get_jwt_identity()
        
        # Verify lecture exists and user has permission
        lecture = Lecture.query.get_or_404(lecture_id)
        
        if not (lecture.teacher_id == current_user_id or 
                User.query.get(current_user_id).role in [UserRole.ADMIN, UserRole.COORDINATOR]):
            return error_response("Access denied", 403)
        
        # Get attendance records
        attendance_records = AttendanceRecord.query.filter_by(lecture_id=lecture_id).all()
        
        # Calculate statistics
        total_students = len(attendance_records)
        present_count = len([r for r in attendance_records if r.is_present])
        absent_count = total_students - present_count
        exceptional_count = len([r for r in attendance_records if getattr(r, 'is_exceptional', False)])
        
        # Group by verification method
        verification_stats = {}
        for record in attendance_records:
            method = getattr(record, 'verification_method', 'unknown')
            if method not in verification_stats:
                verification_stats[method] = {'total': 0, 'present': 0}
            verification_stats[method]['total'] += 1
            if record.is_present:
                verification_stats[method]['present'] += 1
        
        # Get student details
        student_details = []
        for record in attendance_records:
            student = User.query.get(record.student_id)
            if student:
                student_details.append({
                    'student_id': record.student_id,
                    'name': student.name,
                    'university_id': getattr(student, 'student_id', 'N/A'),
                    'is_present': record.is_present,
                    'check_in_time': record.check_in_time.isoformat() if record.check_in_time else None,
                    'verification_method': getattr(record, 'verification_method', 'unknown'),
                    'is_exceptional': getattr(record, 'is_exceptional', False),
                    'notes': getattr(record, 'notes', None)
                })
        
        return success_response(
            data={
                'lecture_info': {
                    'id': lecture.id,
                    'title': lecture.title,
                    'start_time': lecture.start_time.isoformat(),
                    'end_time': lecture.end_time.isoformat(),
                    'room': lecture.room
                },
                'attendance_summary': {
                    'total_students': total_students,
                    'present_count': present_count,
                    'absent_count': absent_count,
                    'exceptional_count': exceptional_count,
                    'attendance_rate': round((present_count / total_students * 100), 2) if total_students > 0 else 0
                },
                'verification_breakdown': verification_stats,
                'student_details': student_details
            },
            message="Attendance summary retrieved successfully"
        )
        
    except Exception as e:
        return error_response(f"Failed to get attendance summary: {str(e)}", 500)

@lectures_bp.route('/teacher/<int:teacher_id>', methods=['GET'])
@jwt_required()
@limiter.limit("20 per minute")
def get_teacher_lectures(teacher_id):
    """Get all lectures for a specific teacher."""
    try:
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)
        
        # Check permissions
        if not (current_user_id == teacher_id or 
                current_user.role in [UserRole.ADMIN, UserRole.COORDINATOR]):
            return error_response("Access denied", 403)
        
        # Verify teacher exists
        teacher = User.query.get_or_404(teacher_id)
        if not teacher.is_teacher():
            return error_response("User is not a teacher", 400)
        
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 100)
        status = request.args.get('status', 'all')  # all, active, inactive
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        
        # Build query
        query = Lecture.query.filter_by(teacher_id=teacher_id)
        
        if status == 'active':
            query = query.filter_by(is_active=True)
        elif status == 'inactive':
            query = query.filter_by(is_active=False)
        
        if from_date:
            try:
                from_dt = datetime.fromisoformat(from_date)
                query = query.filter(Lecture.start_time >= from_dt)
            except ValueError:
                return error_response("Invalid from_date format", 400)
        
        if to_date:
            try:
                to_dt = datetime.fromisoformat(to_date)
                query = query.filter(Lecture.end_time <= to_dt)
            except ValueError:
                return error_response("Invalid to_date format", 400)
        
        # Execute query with pagination
        lectures = query.order_by(Lecture.start_time.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # Format response
        lecture_list = []
        for lecture in lectures.items:
            lecture_data = lecture.to_dict()
            
            # Add attendance statistics
            attendance_count = AttendanceRecord.query.filter_by(lecture_id=lecture.id).count()
            present_count = AttendanceRecord.query.filter_by(
                lecture_id=lecture.id, is_present=True
            ).count()
            
            lecture_data['attendance_stats'] = {
                'total_students': attendance_count,
                'present_count': present_count,
                'attendance_rate': round((present_count / attendance_count * 100), 2) if attendance_count > 0 else 0
            }
            
            lecture_list.append(lecture_data)
        
        return success_response(
            data={
                'lectures': lecture_list,
                'pagination': {
                    'page': lectures.page,
                    'pages': lectures.pages,
                    'per_page': lectures.per_page,
                    'total': lectures.total,
                    'has_next': lectures.has_next,
                    'has_prev': lectures.has_prev
                },
                'teacher_info': {
                    'id': teacher.id,
                    'name': teacher.name,
                    'email': teacher.email
                }
            },
            message=f"Found {lectures.total} lectures for teacher"
        )
        
    except Exception as e:
        return error_response(f"Failed to get teacher lectures: {str(e)}", 500)

@lectures_bp.route('/<int:lecture_id>/room', methods=['PUT'])
@jwt_required()
@teacher_required
@limiter.limit("5 per minute")
def update_lecture_room(lecture_id):
    """Update lecture room assignment."""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        # Validate input
        if not data or 'room' not in data:
            return error_response("Room information is required", 400)
        
        # Get lecture
        lecture = Lecture.query.get_or_404(lecture_id)
        
        # Check permissions
        if not (lecture.teacher_id == current_user_id or 
                User.query.get(current_user_id).role in [UserRole.ADMIN, UserRole.COORDINATOR]):
            return error_response("Access denied", 403)
        
        # Validate room exists if room_id provided
        room_id = data.get('room_id')
        if room_id:
            room = Room.query.get(room_id)
            if not room:
                return error_response("Room not found", 404)
            
            # Check room availability for the lecture time
            conflicting_lectures = Lecture.query.filter(
                Lecture.id != lecture_id,
                Lecture.room == room.name,
                Lecture.is_active == True,
                db.or_(
                    db.and_(Lecture.start_time <= lecture.start_time, Lecture.end_time > lecture.start_time),
                    db.and_(Lecture.start_time < lecture.end_time, Lecture.end_time >= lecture.end_time),
                    db.and_(Lecture.start_time >= lecture.start_time, Lecture.end_time <= lecture.end_time)
                )
            ).first()
            
            if conflicting_lectures:
                return error_response("Room is already booked for this time slot", 409)
            
            lecture.room = room.name
            # Update location if room has coordinates
            if hasattr(room, 'center_latitude') and room.center_latitude:
                lecture.latitude = room.center_latitude
                lecture.longitude = room.center_longitude
        else:
            lecture.room = data['room']
        
        # Update additional location data if provided
        if 'latitude' in data:
            lecture.latitude = data['latitude']
        if 'longitude' in data:
            lecture.longitude = data['longitude']
        
        db.session.commit()
        
        return success_response(
            data=lecture.to_dict(),
            message="Lecture room updated successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Failed to update lecture room: {str(e)}", 500)

@lectures_bp.route('/<int:lecture_id>/force', methods=['DELETE'])
@jwt_required()
@limiter.limit("3 per minute")
def force_delete_lecture(lecture_id):
    """Force delete lecture (admin only)."""
    try:
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)
        
        # Only admins can force delete
        if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            return error_response("Admin access required", 403)
        
        lecture = Lecture.query.get_or_404(lecture_id)
        
        # Get related data for logging
        attendance_count = AttendanceRecord.query.filter_by(lecture_id=lecture_id).count()
        
        # Delete related records first
        AttendanceRecord.query.filter_by(lecture_id=lecture_id).delete()
        AttendanceSession.query.filter_by(lecture_id=lecture_id).delete()
        
        # Delete the lecture
        db.session.delete(lecture)
        db.session.commit()
        
        return success_response(
            data={
                'deleted_lecture_id': lecture_id,
                'deleted_attendance_records': attendance_count
            },
            message="Lecture and all related data deleted successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Failed to force delete lecture: {str(e)}", 500)

@lectures_bp.route('/analytics', methods=['GET'])
@jwt_required()
@limiter.limit("10 per minute")
def get_lectures_analytics():
    """Get comprehensive lectures analytics."""
    try:
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)
        
        # Get date range
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        teacher_id = request.args.get('teacher_id', type=int)
        
        # Build base query
        query = Lecture.query
        
        # Filter by teacher if specified and user has permission
        if teacher_id:
            if not (current_user_id == teacher_id or 
                    current_user.role in [UserRole.ADMIN, UserRole.COORDINATOR]):
                return error_response("Access denied", 403)
            query = query.filter_by(teacher_id=teacher_id)
        elif current_user.role == UserRole.TEACHER:
            # Teachers can only see their own analytics
            query = query.filter_by(teacher_id=current_user_id)
        
        # Apply date filters
        if from_date:
            try:
                from_dt = datetime.fromisoformat(from_date)
                query = query.filter(Lecture.start_time >= from_dt)
            except ValueError:
                return error_response("Invalid from_date format", 400)
        
        if to_date:
            try:
                to_dt = datetime.fromisoformat(to_date)
                query = query.filter(Lecture.end_time <= to_dt)
            except ValueError:
                return error_response("Invalid to_date format", 400)
        
        lectures = query.all()
        
        # Calculate analytics
        total_lectures = len(lectures)
        active_lectures = len([l for l in lectures if l.is_active])
        
        # Room usage statistics
        room_usage = {}
        for lecture in lectures:
            room = lecture.room or 'Unknown'
            if room not in room_usage:
                room_usage[room] = 0
            room_usage[room] += 1
        
        # Teacher statistics (if admin/coordinator)
        teacher_stats = {}
        if current_user.role in [UserRole.ADMIN, UserRole.COORDINATOR]:
            for lecture in lectures:
                teacher = User.query.get(lecture.teacher_id)
                if teacher:
                    teacher_name = teacher.name
                    if teacher_name not in teacher_stats:
                        teacher_stats[teacher_name] = {
                            'total_lectures': 0,
                            'total_attendance': 0,
                            'average_attendance_rate': 0
                        }
                    
                    teacher_stats[teacher_name]['total_lectures'] += 1
                    
                    # Calculate attendance for this teacher
                    attendance_records = AttendanceRecord.query.filter_by(lecture_id=lecture.id).all()
                    present_count = len([r for r in attendance_records if r.is_present])
                    teacher_stats[teacher_name]['total_attendance'] += len(attendance_records)
                    
            # Calculate average attendance rates
            for teacher_name in teacher_stats:
                stats = teacher_stats[teacher_name]
                if stats['total_lectures'] > 0:
                    # This is a simplified calculation - in production you'd want more detailed stats
                    stats['average_attendance_rate'] = round(
                        (stats['total_attendance'] / stats['total_lectures']), 2
                    )
        
        # Time-based analytics
        daily_distribution = {}
        hourly_distribution = {}
        
        for lecture in lectures:
            # Daily distribution
            day_name = lecture.start_time.strftime('%A')
            if day_name not in daily_distribution:
                daily_distribution[day_name] = 0
            daily_distribution[day_name] += 1
            
            # Hourly distribution
            hour = lecture.start_time.hour
            if hour not in hourly_distribution:
                hourly_distribution[hour] = 0
            hourly_distribution[hour] += 1
        
        return success_response(
            data={
                'overview': {
                    'total_lectures': total_lectures,
                    'active_lectures': active_lectures,
                    'inactive_lectures': total_lectures - active_lectures
                },
                'room_usage': dict(sorted(room_usage.items(), key=lambda x: x[1], reverse=True)),
                'teacher_statistics': teacher_stats,
                'time_distribution': {
                    'daily': daily_distribution,
                    'hourly': hourly_distribution
                },
                'date_range': {
                    'from': from_date,
                    'to': to_date
                }
            },
            message="Lectures analytics retrieved successfully"
        )
        
    except Exception as e:
        return error_response(f"Failed to get lectures analytics: {str(e)}", 500)