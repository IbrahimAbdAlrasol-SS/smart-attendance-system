
# backend/app/api/schedules.py
"""Schedule Management API."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.schedule import Schedule, WeekDay
from app.models.user import User, UserRole
from app.models.room import Room
from app.models.student import Section, StudyType
from app.utils.helpers import success_response, error_response
from app.utils.decorators import admin_required, teacher_required
from datetime import datetime, time

schedules_bp = Blueprint('schedules', __name__)

@schedules_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Schedules service is running')

@schedules_bp.route('/', methods=['GET'])
@jwt_required()
def get_schedules():
    """Get schedules with filters."""
    try:
        # Get current user
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        # Build query
        query = Schedule.query.filter_by(is_active=True)
        
        # Apply filters based on user role
        if user.role == UserRole.STUDENT:
            # Students see only their section's schedules
            student = user.student_profile
            if student:
                query = query.filter_by(
                    section=student.section,
                    study_year=student.study_year,
                    study_type=student.study_type
                )
        elif user.role == UserRole.TEACHER:
            # Teachers can filter by their own schedules or all
            if request.args.get('my_schedules') == 'true':
                query = query.filter_by(teacher_id=current_user_id)
        
        # Additional filters
        section = request.args.get('section')
        study_year = request.args.get('study_year', type=int)
        study_type = request.args.get('study_type')
        day = request.args.get('day')
        room_id = request.args.get('room_id', type=int)
        
        if section:
            query = query.filter_by(section=Section[section.upper()])
        if study_year:
            query = query.filter_by(study_year=study_year)
        if study_type:
            query = query.filter_by(study_type=StudyType[study_type.upper()])
        if day:
            query = query.filter_by(day_of_week=WeekDay[day.upper()])
        if room_id:
            query = query.filter_by(room_id=room_id)
        
        # Order by day and time
        schedules = query.order_by(Schedule.day_of_week, Schedule.start_time).all()
        
        return success_response(
            data=[schedule.to_dict() for schedule in schedules]
        )
        
    except Exception as e:
        return error_response(f"Error fetching schedules: {str(e)}", 500)

@schedules_bp.route('/<int:schedule_id>', methods=['GET'])
@jwt_required()
def get_schedule(schedule_id):
    """Get single schedule details."""
    try:
        schedule = Schedule.query.get_or_404(schedule_id)
        return success_response(data=schedule.to_dict())
        
    except Exception as e:
        return error_response(f"Error fetching schedule: {str(e)}", 500)

@schedules_bp.route('/', methods=['POST'])
@jwt_required()
@admin_required
def create_schedule():
    """Create new schedule."""
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['subject_name', 'teacher_id', 'room_id', 'section',
                   'study_year', 'study_type', 'day_of_week', 'start_time', 'end_time']
        for field in required:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Validate teacher exists and is a teacher
        teacher = User.query.get(data['teacher_id'])
        if not teacher or not teacher.is_teacher():
            return error_response("Invalid teacher ID", 400)
        
        # Validate room exists
        room = Room.query.get(data['room_id'])
        if not room or not room.is_active:
            return error_response("Invalid or inactive room", 400)
        
        # Parse times
        start_time = datetime.strptime(data['start_time'], '%H:%M').time()
        end_time = datetime.strptime(data['end_time'], '%H:%M').time()
        
        if start_time >= end_time:
            return error_response("End time must be after start time", 400)
        
        # Check for conflicts
        conflict = Schedule.query.filter_by(
            room_id=data['room_id'],
            day_of_week=WeekDay[data['day_of_week'].upper()],
            is_active=True
        ).filter(
            db.or_(
                db.and_(Schedule.start_time <= start_time, Schedule.end_time > start_time),
                db.and_(Schedule.start_time < end_time, Schedule.end_time >= end_time),
                db.and_(Schedule.start_time >= start_time, Schedule.end_time <= end_time)
            )
        ).first()
        
        if conflict:
            return error_response(
                f"Room conflict with {conflict.subject_name} at {conflict.start_time}", 
                400
            )
        
        # Create schedule
        schedule = Schedule(
            subject_name=data['subject_name'],
            subject_code=data.get('subject_code'),
            teacher_id=data['teacher_id'],
            room_id=data['room_id'],
            section=Section[data['section'].upper()],
            study_year=data['study_year'],
            study_type=StudyType[data['study_type'].upper()],
            day_of_week=WeekDay[data['day_of_week'].upper()],
            start_time=start_time,
            end_time=end_time,
            semester=data.get('semester', 1),
            academic_year=data.get('academic_year', f"{datetime.now().year}-{datetime.now().year+1}")
        )
        
        db.session.add(schedule)
        db.session.commit()
        
        return success_response(
            data=schedule.to_dict(),
            message="Schedule created successfully"
        ), 201
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error creating schedule: {str(e)}", 500)

@schedules_bp.route('/<int:schedule_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_schedule(schedule_id):
    """Update schedule."""
    try:
        schedule = Schedule.query.get_or_404(schedule_id)
        data = request.get_json()
        
        # Update allowed fields
        if 'subject_name' in data:
            schedule.subject_name = data['subject_name']
        if 'subject_code' in data:
            schedule.subject_code = data['subject_code']
        if 'room_id' in data:
            room = Room.query.get(data['room_id'])
            if not room or not room.is_active:
                return error_response("Invalid or inactive room", 400)
            schedule.room_id = data['room_id']
        
        # Update times if provided
        if 'start_time' in data or 'end_time' in data:
            start_time = schedule.start_time
            end_time = schedule.end_time
            
            if 'start_time' in data:
                start_time = datetime.strptime(data['start_time'], '%H:%M').time()
            if 'end_time' in data:
                end_time = datetime.strptime(data['end_time'], '%H:%M').time()
            
            if start_time >= end_time:
                return error_response("End time must be after start time", 400)
            
            schedule.start_time = start_time
            schedule.end_time = end_time
        
        db.session.commit()
        
        return success_response(
            data=schedule.to_dict(),
            message="Schedule updated successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error updating schedule: {str(e)}", 500)

@schedules_bp.route('/<int:schedule_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_schedule(schedule_id):
    """Delete schedule (soft delete)."""
    try:
        schedule = Schedule.query.get_or_404(schedule_id)
        
        # Soft delete
        schedule.is_active = False
        db.session.commit()
        
        return success_response(message="Schedule deleted successfully")
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error deleting schedule: {str(e)}", 500)

@schedules_bp.route('/current', methods=['GET'])
@jwt_required()
def get_current_schedule():
    """Get currently active schedule based on time."""
    try:
        now = datetime.now()
        current_day = now.weekday()  # 0 = Monday, 6 = Sunday
        current_time = now.time()
        
        # Map Python weekday to our WeekDay enum
        day_mapping = {
            6: WeekDay.SUNDAY,    # Sunday
            0: WeekDay.MONDAY,    # Monday
            1: WeekDay.TUESDAY,   # Tuesday
            2: WeekDay.WEDNESDAY, # Wednesday
            3: WeekDay.THURSDAY,  # Thursday
            4: WeekDay.FRIDAY,    # Friday
            5: WeekDay.SATURDAY,  # Saturday
        }
        
        current_weekday = day_mapping[current_day]
        
        # Get current user
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        # Build query
        query = Schedule.query.filter_by(
            is_active=True,
            day_of_week=current_weekday
        ).filter(
            Schedule.start_time <= current_time,
            Schedule.end_time > current_time
        )
        
        # Filter based on user role
        if user.role == UserRole.STUDENT:
            student = user.student_profile
            if student:
                query = query.filter_by(
                    section=student.section,
                    study_year=student.study_year,
                    study_type=student.study_type
                )
        elif user.role == UserRole.TEACHER:
            query = query.filter_by(teacher_id=current_user_id)
        
        current_schedule = query.first()
        
        if current_schedule:
            return success_response(
                data={
                    'current': current_schedule.to_dict(),
                    'server_time': now.isoformat()
                }
            )
        else:
            return success_response(
                data={
                    'current': None,
                    'message': 'No active schedule at this time',
                    'server_time': now.isoformat()
                }
            )
        
    except Exception as e:
        return error_response(f"Error fetching current schedule: {str(e)}", 500)