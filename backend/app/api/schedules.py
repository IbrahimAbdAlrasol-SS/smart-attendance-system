# backend/app/api/schedules.py - COMPLETE VERSION
"""Schedule Management API - Complete with all missing endpoints."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, limiter
from app.models.schedule import Schedule, WeekDay
from app.models.user import User, UserRole
from app.models.room import Room
from app.models.student import Section, StudyType
from app.utils.helpers import success_response, error_response
from app.utils.decorators import admin_required, teacher_required
from datetime import datetime, time, timedelta
from sqlalchemy import and_, or_
import pandas as pd
import io

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

@schedules_bp.route('/weekly', methods=['GET'])
@jwt_required()
def get_weekly_schedule():
    """Get weekly schedule view."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        # Get filters
        section = request.args.get('section')
        study_year = request.args.get('study_year', type=int)
        teacher_id = request.args.get('teacher_id', type=int)
        
        # Build base query
        query = Schedule.query.filter_by(is_active=True)
        
        # Apply user-based filters
        if user.role == UserRole.STUDENT:
            student = user.student_profile
            if student:
                query = query.filter_by(
                    section=student.section,
                    study_year=student.study_year,
                    study_type=student.study_type
                )
        elif user.role == UserRole.TEACHER:
            if not teacher_id:  # Default to current teacher's schedule
                query = query.filter_by(teacher_id=current_user_id)
            elif teacher_id:
                query = query.filter_by(teacher_id=teacher_id)
        else:  # Admin
            if section:
                query = query.filter_by(section=Section[section.upper()])
            if study_year:
                query = query.filter_by(study_year=study_year)
            if teacher_id:
                query = query.filter_by(teacher_id=teacher_id)
        
        schedules = query.order_by(Schedule.day_of_week, Schedule.start_time).all()
        
        # Organize by day of week
        weekly_schedule = {}
        for day in WeekDay:
            weekly_schedule[day.name.lower()] = []
        
        for schedule in schedules:
            day_name = schedule.day_of_week.name.lower()
            schedule_data = schedule.to_dict()
            
            # Add room details
            room = Room.query.get(schedule.room_id)
            if room:
                schedule_data['room_details'] = {
                    'name': room.name,
                    'building': room.building,
                    'floor': room.floor,
                    'capacity': room.capacity
                }
            
            weekly_schedule[day_name].append(schedule_data)
        
        # Calculate schedule statistics
        stats = {
            'total_subjects': len(set(s.subject_name for s in schedules)),
            'total_hours_per_week': sum(
                (datetime.combine(datetime.today(), s.end_time) - 
                 datetime.combine(datetime.today(), s.start_time)).total_seconds() / 3600
                for s in schedules
            ),
            'days_with_classes': len([day for day, classes in weekly_schedule.items() if classes]),
            'busiest_day': max(weekly_schedule.items(), key=lambda x: len(x[1]))[0] if schedules else None
        }
        
        return success_response(
            data={
                'weekly_schedule': weekly_schedule,
                'statistics': stats
            },
            message="Weekly schedule retrieved"
        )
        
    except Exception as e:
        return error_response(f"Error fetching weekly schedule: {str(e)}", 500)

@schedules_bp.route('/conflicts', methods=['GET'])
@jwt_required()
@admin_required
def check_schedule_conflicts():
    """Check for scheduling conflicts."""
    try:
        # Get parameters
        check_type = request.args.get('type', 'all')  # 'all', 'teacher', 'room', 'time'
        teacher_id = request.args.get('teacher_id', type=int)
        room_id = request.args.get('room_id', type=int)
        
        conflicts = []
        
        # Teacher conflicts
        if check_type in ['all', 'teacher']:
            teacher_conflicts = db.session.query(
                Schedule.teacher_id,
                Schedule.day_of_week,
                Schedule.start_time,
                Schedule.end_time,
                db.func.count(Schedule.id).label('conflict_count'),
                db.func.group_concat(Schedule.subject_name).label('subjects')
            ).filter_by(is_active=True)
            
            if teacher_id:
                teacher_conflicts = teacher_conflicts.filter_by(teacher_id=teacher_id)
            
            teacher_conflicts = teacher_conflicts.group_by(
                Schedule.teacher_id,
                Schedule.day_of_week,
                Schedule.start_time,
                Schedule.end_time
            ).having(db.func.count(Schedule.id) > 1).all()
            
            for conflict in teacher_conflicts:
                teacher = User.query.get(conflict.teacher_id)
                conflicts.append({
                    'type': 'teacher_conflict',
                    'teacher_id': conflict.teacher_id,
                    'teacher_name': teacher.name if teacher else 'Unknown',
                    'day': conflict.day_of_week.name,
                    'time': f"{conflict.start_time} - {conflict.end_time}",
                    'conflict_count': conflict.conflict_count,
                    'subjects': conflict.subjects.split(',') if conflict.subjects else []
                })
        
        # Room conflicts
        if check_type in ['all', 'room']:
            room_conflicts = db.session.query(
                Schedule.room_id,
                Schedule.day_of_week,
                Schedule.start_time,
                Schedule.end_time,
                db.func.count(Schedule.id).label('conflict_count'),
                db.func.group_concat(Schedule.subject_name).label('subjects')
            ).filter_by(is_active=True)
            
            if room_id:
                room_conflicts = room_conflicts.filter_by(room_id=room_id)
            
            room_conflicts = room_conflicts.group_by(
                Schedule.room_id,
                Schedule.day_of_week,
                Schedule.start_time,
                Schedule.end_time
            ).having(db.func.count(Schedule.id) > 1).all()
            
            for conflict in room_conflicts:
                room = Room.query.get(conflict.room_id)
                conflicts.append({
                    'type': 'room_conflict',
                    'room_id': conflict.room_id,
                    'room_name': room.name if room else 'Unknown',
                    'day': conflict.day_of_week.name,
                    'time': f"{conflict.start_time} - {conflict.end_time}",
                    'conflict_count': conflict.conflict_count,
                    'subjects': conflict.subjects.split(',') if conflict.subjects else []
                })
        
        # Time overlap conflicts (more sophisticated)
        if check_type in ['all', 'time']:
            all_schedules = Schedule.query.filter_by(is_active=True).all()
            
            for i, schedule1 in enumerate(all_schedules):
                for schedule2 in all_schedules[i+1:]:
                    if (schedule1.day_of_week == schedule2.day_of_week and
                        schedule1.room_id == schedule2.room_id):
                        
                        # Check for time overlap
                        start1 = datetime.combine(datetime.today(), schedule1.start_time)
                        end1 = datetime.combine(datetime.today(), schedule1.end_time)
                        start2 = datetime.combine(datetime.today(), schedule2.start_time)
                        end2 = datetime.combine(datetime.today(), schedule2.end_time)
                        
                        if not (end1 <= start2 or end2 <= start1):  # Overlap exists
                            conflicts.append({
                                'type': 'time_overlap',
                                'schedule1_id': schedule1.id,
                                'schedule1_subject': schedule1.subject_name,
                                'schedule2_id': schedule2.id,
                                'schedule2_subject': schedule2.subject_name,
                                'room_name': schedule1.room.name if schedule1.room else 'Unknown',
                                'day': schedule1.day_of_week.name,
                                'overlap_time': f"{max(start1, start2).time()} - {min(end1, end2).time()}"
                            })
        
        # Generate resolution suggestions
        suggestions = []
        if conflicts:
            suggestions = generate_conflict_resolutions(conflicts)
        
        return success_response(
            data={
                'conflicts': conflicts,
                'conflict_count': len(conflicts),
                'suggestions': suggestions,
                'conflict_types': {
                    'teacher_conflicts': len([c for c in conflicts if c['type'] == 'teacher_conflict']),
                    'room_conflicts': len([c for c in conflicts if c['type'] == 'room_conflict']),
                    'time_overlaps': len([c for c in conflicts if c['type'] == 'time_overlap'])
                }
            },
            message=f"Found {len(conflicts)} conflicts"
        )
        
    except Exception as e:
        return error_response(f"Error checking conflicts: {str(e)}", 500)

@schedules_bp.route('/bulk', methods=['POST'])
@jwt_required()
@admin_required
@limiter.limit("5 per hour")
def create_bulk_schedules():
    """Create multiple schedules from CSV/Excel."""
    try:
        if 'file' not in request.files:
            return error_response("No file uploaded", 400)
        
        file = request.files['file']
        if file.filename == '':
            return error_response("No file selected", 400)
        
        # Check file extension
        if not file.filename.lower().endswith(('.csv', '.xlsx', '.xls')):
            return error_response("Invalid file format. Use CSV or Excel", 400)
        
        # Read file
        try:
            if file.filename.lower().endswith('.csv'):
                df = pd.read_csv(io.StringIO(file.stream.read().decode("utf-8")))
            else:
                df = pd.read_excel(file.stream)
        except Exception as e:
            return error_response(f"Error reading file: {str(e)}", 400)
        
        # Validate columns
        required_columns = ['subject_name', 'teacher_email', 'room_name', 'section', 
                           'study_year', 'study_type', 'day_of_week', 'start_time', 'end_time']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return error_response(f"Missing columns: {', '.join(missing_columns)}", 400)
        
        # Process schedules
        results = []
        created_count = 0
        
        for index, row in df.iterrows():
            try:
                # Find teacher
                teacher = User.query.filter_by(email=row['teacher_email'].strip()).first()
                if not teacher or not teacher.is_teacher():
                    results.append({
                        'row': index + 2,
                        'subject': row['subject_name'],
                        'success': False,
                        'error': f"Teacher not found: {row['teacher_email']}"
                    })
                    continue
                
                # Find room
                room = Room.query.filter_by(name=row['room_name'].strip()).first()
                if not room:
                    results.append({
                        'row': index + 2,
                        'subject': row['subject_name'],
                        'success': False,
                        'error': f"Room not found: {row['room_name']}"
                    })
                    continue
                
                # Parse times
                start_time = datetime.strptime(str(row['start_time']), '%H:%M').time()
                end_time = datetime.strptime(str(row['end_time']), '%H:%M').time()
                
                if start_time >= end_time:
                    results.append({
                        'row': index + 2,
                        'subject': row['subject_name'],
                        'success': False,
                        'error': "End time must be after start time"
                    })
                    continue
                
                # Check for conflicts
                day_of_week = WeekDay[row['day_of_week'].upper()]
                conflict = Schedule.query.filter_by(
                    room_id=room.id,
                    day_of_week=day_of_week,
                    is_active=True
                ).filter(
                    or_(
                        and_(Schedule.start_time <= start_time, Schedule.end_time > start_time),
                        and_(Schedule.start_time < end_time, Schedule.end_time >= end_time),
                        and_(Schedule.start_time >= start_time, Schedule.end_time <= end_time)
                    )
                ).first()
                
                if conflict:
                    results.append({
                        'row': index + 2,
                        'subject': row['subject_name'],
                        'success': False,
                        'error': f"Room conflict with {conflict.subject_name}"
                    })
                    continue
                
                # Create schedule
                schedule = Schedule(
                    subject_name=row['subject_name'].strip(),
                    subject_code=row.get('subject_code', '').strip(),
                    teacher_id=teacher.id,
                    room_id=room.id,
                    section=Section[row['section'].upper()],
                    study_year=int(row['study_year']),
                    study_type=StudyType[row['study_type'].upper()],
                    day_of_week=day_of_week,
                    start_time=start_time,
                    end_time=end_time,
                    semester=int(row.get('semester', 1)),
                    academic_year=row.get('academic_year', f"{datetime.now().year}-{datetime.now().year+1}")
                )
                
                db.session.add(schedule)
                created_count += 1
                
                results.append({
                    'row': index + 2,
                    'subject': row['subject_name'],
                    'success': True,
                    'schedule_id': None  # Will be set after commit
                })
                
            except Exception as e:
                results.append({
                    'row': index + 2,
                    'subject': row.get('subject_name', 'Unknown'),
                    'success': False,
                    'error': str(e)
                })
        
        # Commit successful creations
        if created_count > 0:
            db.session.commit()
            
            # Update schedule IDs in results
            successful_results = [r for r in results if r['success']]
            recent_schedules = Schedule.query.order_by(Schedule.id.desc()).limit(created_count).all()
            
            for i, result in enumerate(successful_results):
                if i < len(recent_schedules):
                    result['schedule_id'] = recent_schedules[-(i+1)].id
        
        return success_response(
            data={
                'total_processed': len(results),
                'successful': created_count,
                'failed': len(results) - created_count,
                'results': results
            },
            message=f"Bulk import completed. Created {created_count} schedules."
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error in bulk import: {str(e)}", 500)

@schedules_bp.route('/export', methods=['GET'])
@jwt_required()
@admin_required
def export_schedules():
    """Export schedules as CSV or Excel."""
    try:
        # Get filters
        section = request.args.get('section')
        study_year = request.args.get('study_year', type=int)
        teacher_id = request.args.get('teacher_id', type=int)
        format_type = request.args.get('format', 'csv')  # csv or excel
        
        # Build query
        query = Schedule.query.filter_by(is_active=True)
        
        if section:
            query = query.filter_by(section=Section[section.upper()])
        if study_year:
            query = query.filter_by(study_year=study_year)
        if teacher_id:
            query = query.filter_by(teacher_id=teacher_id)
        
        schedules = query.order_by(Schedule.day_of_week, Schedule.start_time).all()
        
        # Prepare data
        data = []
        for schedule in schedules:
            teacher = User.query.get(schedule.teacher_id)
            room = Room.query.get(schedule.room_id)
            
            data.append({
                'subject_name': schedule.subject_name,
                'subject_code': schedule.subject_code or '',
                'teacher_name': teacher.name if teacher else '',
                'teacher_email': teacher.email if teacher else '',
                'room_name': room.name if room else '',
                'room_building': room.building if room else '',
                'section': schedule.section.value if schedule.section else '',
                'study_year': schedule.study_year,
                'study_type': schedule.study_type.value if schedule.study_type else '',
                'day_of_week': schedule.day_of_week.name if schedule.day_of_week else '',
                'start_time': schedule.start_time.strftime('%H:%M') if schedule.start_time else '',
                'end_time': schedule.end_time.strftime('%H:%M') if schedule.end_time else '',
                'semester': schedule.semester,
                'academic_year': schedule.academic_year
            })
        
        df = pd.DataFrame(data)
        
        if format_type.lower() == 'excel':
            # Export as Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Schedules', index=False)
                
                # Add summary sheet
                summary_data = {
                    'Metric': ['Total Schedules', 'Unique Subjects', 'Unique Teachers', 'Unique Rooms'],
                    'Count': [
                        len(data),
                        len(set(item['subject_name'] for item in data)),
                        len(set(item['teacher_name'] for item in data if item['teacher_name'])),
                        len(set(item['room_name'] for item in data if item['room_name']))
                    ]
                }
                pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
            
            output.seek(0)
            
            return output.getvalue(), 200, {
                'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'Content-Disposition': f'attachment; filename=schedules_export_{datetime.now().strftime("%Y%m%d")}.xlsx'
            }
        else:
            # Export as CSV
            output = io.StringIO()
            df.to_csv(output, index=False, encoding='utf-8-sig')
            output.seek(0)
            
            return output.getvalue(), 200, {
                'Content-Type': 'text/csv; charset=utf-8-sig',
                'Content-Disposition': f'attachment; filename=schedules_export_{datetime.now().strftime("%Y%m%d")}.csv'
            }
        
    except Exception as e:
        return error_response(f"Error exporting schedules: {str(e)}", 500)

# Existing endpoints remain the same...
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
            or_(
                and_(Schedule.start_time <= start_time, Schedule.end_time > start_time),
                and_(Schedule.start_time < end_time, Schedule.end_time >= end_time),
                and_(Schedule.start_time >= start_time, Schedule.end_time <= end_time)
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

# =================== HELPER FUNCTIONS ===================

def generate_conflict_resolutions(conflicts):
    """Generate suggestions for resolving conflicts."""
    suggestions = []
    
    for conflict in conflicts:
        if conflict['type'] == 'teacher_conflict':
            suggestions.append({
                'conflict_id': f"teacher_{conflict['teacher_id']}_{conflict['day']}",
                'type': 'teacher_conflict',
                'suggestion': f"Reschedule one of the subjects for {conflict['teacher_name']} on {conflict['day']}",
                'options': [
                    'Move one subject to a different time slot',
                    'Move one subject to a different day',
                    'Assign different teacher to one subject'
                ]
            })
        
        elif conflict['type'] == 'room_conflict':
            suggestions.append({
                'conflict_id': f"room_{conflict['room_id']}_{conflict['day']}",
                'type': 'room_conflict',
                'suggestion': f"Resolve room conflict for {conflict['room_name']} on {conflict['day']}",
                'options': [
                    'Move one subject to a different room',
                    'Change time slot for one subject',
                    'Split the time slot if possible'
                ]
            })
        
        elif conflict['type'] == 'time_overlap':
            suggestions.append({
                'conflict_id': f"overlap_{conflict['schedule1_id']}_{conflict['schedule2_id']}",
                'type': 'time_overlap',
                'suggestion': f"Resolve time overlap between {conflict['schedule1_subject']} and {conflict['schedule2_subject']}",
                'options': [
                    'Adjust start/end times to eliminate overlap',
                    'Move one subject to different room',
                    'Reschedule one subject completely'
                ]
            })
    
    return suggestions