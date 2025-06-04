# File: backend/app/api/teachers.py
"""Teachers Management API - Admin Only."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, limiter
from app.models.user import User, UserRole, Section
from app.models.lecture import Lecture
from app.models.schedule import Schedule
from app.models.attendance import AttendanceRecord
from app.utils.helpers import success_response, error_response
from app.utils.decorators import admin_required, super_admin_required
from app.utils.validators import Validator
from datetime import datetime, timedelta
from sqlalchemy import func, distinct
import pandas as pd
import io

teachers_bp = Blueprint('teachers', __name__)

@teachers_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Teachers service is running')

@teachers_bp.route('/', methods=['GET'])
@jwt_required()
@admin_required
def get_teachers():
    """Get all teachers with filters and statistics."""
    try:
        # Get query parameters
        department = request.args.get('department')
        is_active = request.args.get('is_active', type=bool, default=True)
        section = request.args.get('section')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '').strip()
        
        # Build query
        query = User.query.filter(
            User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR])
        )
        
        if is_active is not None:
            query = query.filter_by(is_active=is_active)
        
        if section:
            query = query.filter_by(section=Section[section.upper()])
        
        if search:
            query = query.filter(
                db.or_(
                    User.name.contains(search),
                    User.email.contains(search)
                )
            )
        
        # Order by creation date
        query = query.order_by(User.created_at.desc())
        
        # Paginate
        pagination = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        # Format teachers with statistics
        teachers = []
        for teacher in pagination.items:
            teacher_data = teacher.to_dict()
            
            # Add teaching statistics
            teacher_stats = get_teacher_statistics(teacher.id)
            teacher_data['statistics'] = teacher_stats
            
            teachers.append(teacher_data)
        
        return success_response(
            data={
                'teachers': teachers,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': pagination.total,
                    'pages': pagination.pages,
                    'has_next': pagination.has_next,
                    'has_prev': pagination.has_prev
                }
            },
            message=f"Found {len(teachers)} teachers"
        )
        
    except Exception as e:
        return error_response(f"Error fetching teachers: {str(e)}", 500)

@teachers_bp.route('/<int:teacher_id>', methods=['GET'])
@jwt_required()
@admin_required
def get_teacher(teacher_id):
    """Get single teacher details with full statistics."""
    try:
        teacher = User.query.filter(
            User.id == teacher_id,
            User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR])
        ).first()
        
        if not teacher:
            return error_response("Teacher not found", 404)
        
        teacher_data = teacher.to_dict()
        
        # Add comprehensive statistics
        teacher_data['statistics'] = get_teacher_comprehensive_statistics(teacher_id)
        
        # Add recent lectures
        recent_lectures = Lecture.query.filter_by(
            teacher_id=teacher_id,
            is_active=True
        ).order_by(Lecture.start_time.desc()).limit(10).all()
        
        teacher_data['recent_lectures'] = [
            {
                'id': lecture.id,
                'title': lecture.title,
                'room': lecture.room,
                'start_time': lecture.start_time.isoformat(),
                'end_time': lecture.end_time.isoformat()
            }
            for lecture in recent_lectures
        ]
        
        # Add schedules
        schedules = Schedule.query.filter_by(
            teacher_id=teacher_id,
            is_active=True
        ).all()
        
        teacher_data['schedules'] = [schedule.to_dict() for schedule in schedules]
        
        return success_response(data=teacher_data)
        
    except Exception as e:
        return error_response(f"Error fetching teacher: {str(e)}", 500)

@teachers_bp.route('/', methods=['POST'])
@jwt_required()
@super_admin_required
def create_teacher():
    """Create new teacher account."""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        # Validate required fields
        required_fields = ['name', 'email', 'password']
        validation = Validator.validate_required_fields(data, required_fields)
        
        if not validation['is_valid']:
            return error_response(', '.join(validation['errors']), 400)
        
        # Validate email format
        if not Validator.validate_email(data['email']):
            return error_response("Invalid email format", 400)
        
        # Validate password
        password_validation = Validator.validate_password(data['password'])
        if not password_validation['is_valid']:
            return error_response(', '.join(password_validation['errors']), 400)
        
        # Check if email already exists
        if User.query.filter_by(email=data['email'].lower()).first():
            return error_response("Email already exists", 400)
        
        # Create teacher
        teacher = User(
            email=data['email'].lower().strip(),
            name=data['name'].strip(),
            role=UserRole.TEACHER,
            section=Section[data['section'].upper()] if data.get('section') else None,
            phone=data.get('phone', '').strip() or None
        )
        teacher.set_password(data['password'])
        
        db.session.add(teacher)
        db.session.commit()
        
        return success_response(
            data=teacher.to_dict(),
            message="Teacher created successfully"
        ), 201
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error creating teacher: {str(e)}", 500)

@teachers_bp.route('/<int:teacher_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_teacher(teacher_id):
    """Update teacher information."""
    try:
        teacher = User.query.filter(
            User.id == teacher_id,
            User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR])
        ).first()
        
        if not teacher:
            return error_response("Teacher not found", 404)
        
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        # Update allowed fields
        if 'name' in data:
            name_validation = Validator.validate_name(data['name'])
            if not name_validation['is_valid']:
                return error_response(', '.join(name_validation['errors']), 400)
            teacher.name = data['name'].strip()
        
        if 'email' in data:
            if not Validator.validate_email(data['email']):
                return error_response("Invalid email format", 400)
            
            # Check if new email already exists (excluding current teacher)
            existing = User.query.filter(
                User.email == data['email'].lower(),
                User.id != teacher_id
            ).first()
            
            if existing:
                return error_response("Email already exists", 400)
            
            teacher.email = data['email'].lower().strip()
        
        if 'section' in data and data['section']:
            teacher.section = Section[data['section'].upper()]
        
        if 'phone' in data:
            teacher.phone = data['phone'].strip() or None
        
        if 'is_active' in data:
            teacher.is_active = bool(data['is_active'])
        
        # Update role if super admin
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)
        
        if current_user.role == UserRole.SUPER_ADMIN and 'role' in data:
            if data['role'].upper() in ['TEACHER', 'COORDINATOR']:
                teacher.role = UserRole[data['role'].upper()]
        
        teacher.updated_at = datetime.utcnow()
        db.session.commit()
        
        return success_response(
            data=teacher.to_dict(),
            message="Teacher updated successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error updating teacher: {str(e)}", 500)

@teachers_bp.route('/<int:teacher_id>', methods=['DELETE'])
@jwt_required()
@super_admin_required
def delete_teacher(teacher_id):
    """Soft delete teacher (deactivate)."""
    try:
        teacher = User.query.filter(
            User.id == teacher_id,
            User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR])
        ).first()
        
        if not teacher:
            return error_response("Teacher not found", 404)
        
        # Check if teacher has active lectures
        active_lectures = Lecture.query.filter_by(
            teacher_id=teacher_id,
            is_active=True
        ).filter(Lecture.end_time > datetime.utcnow()).count()
        
        if active_lectures > 0:
            return error_response(
                f"Cannot delete teacher with {active_lectures} active future lectures", 
                400
            )
        
        # Soft delete - deactivate account
        teacher.is_active = False
        teacher.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return success_response(message="Teacher deactivated successfully")
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error deleting teacher: {str(e)}", 500)

@teachers_bp.route('/<int:teacher_id>/lectures', methods=['GET'])
@jwt_required()
@admin_required
def get_teacher_lectures(teacher_id):
    """Get teacher's lectures with filters."""
    try:
        teacher = User.query.filter(
            User.id == teacher_id,
            User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR])
        ).first()
        
        if not teacher:
            return error_response("Teacher not found", 404)
        
        # Get query parameters
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        status = request.args.get('status', 'all')  # all, upcoming, past, active
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Build query
        query = Lecture.query.filter_by(teacher_id=teacher_id, is_active=True)
        
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
        
        # Apply status filter
        now = datetime.utcnow()
        if status == 'upcoming':
            query = query.filter(Lecture.start_time > now)
        elif status == 'past':
            query = query.filter(Lecture.end_time < now)
        elif status == 'active':
            query = query.filter(
                Lecture.start_time <= now,
                Lecture.end_time >= now
            )
        
        # Order by start time
        query = query.order_by(Lecture.start_time.desc())
        
        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Format lectures with attendance stats
        lectures = []
        for lecture in pagination.items:
            lecture_data = lecture.to_dict()
            
            # Add attendance statistics
            total_students = AttendanceRecord.query.filter_by(lecture_id=lecture.id).count()
            present_students = AttendanceRecord.query.filter_by(
                lecture_id=lecture.id, 
                is_present=True
            ).count()
            
            lecture_data['attendance_stats'] = {
                'total_students': total_students,
                'present_students': present_students,
                'absent_students': total_students - present_students,
                'attendance_rate': (present_students / total_students * 100) if total_students > 0 else 0
            }
            
            lectures.append(lecture_data)
        
        return success_response(
            data={
                'lectures': lectures,
                'teacher': {
                    'id': teacher.id,
                    'name': teacher.name,
                    'email': teacher.email
                },
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': pagination.total,
                    'pages': pagination.pages
                }
            },
            message=f"Found {len(lectures)} lectures for teacher {teacher.name}"
        )
        
    except Exception as e:
        return error_response(f"Error fetching teacher lectures: {str(e)}", 500)

@teachers_bp.route('/<int:teacher_id>/statistics', methods=['GET'])
@jwt_required()
@admin_required
def get_teacher_statistics(teacher_id):
    """Get comprehensive teacher statistics."""
    try:
        teacher = User.query.filter(
            User.id == teacher_id,
            User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR])
        ).first()
        
        if not teacher:
            return error_response("Teacher not found", 404)
        
        stats = get_teacher_comprehensive_statistics(teacher_id)
        
        return success_response(
            data={
                'teacher_info': {
                    'id': teacher.id,
                    'name': teacher.name,
                    'email': teacher.email
                },
                'statistics': stats
            },
            message=f"Statistics for teacher {teacher.name}"
        )
        
    except Exception as e:
        return error_response(f"Error fetching teacher statistics: {str(e)}", 500)

@teachers_bp.route('/<int:teacher_id>/reset-password', methods=['POST'])
@jwt_required()
@super_admin_required
def reset_teacher_password(teacher_id):
    """Reset teacher password."""
    try:
        teacher = User.query.filter(
            User.id == teacher_id,
            User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR])
        ).first()
        
        if not teacher:
            return error_response("Teacher not found", 404)
        
        data = request.get_json() or {}
        new_password = data.get('new_password', 'teacher123456')  # Default password
        
        # Validate new password
        password_validation = Validator.validate_password(new_password)
        if not password_validation['is_valid']:
            return error_response(', '.join(password_validation['errors']), 400)
        
        teacher.set_password(new_password)
        teacher.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return success_response(
            data={
                'teacher_id': teacher_id,
                'new_password': new_password  # Only returned for super admin
            },
            message="Password reset successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error resetting password: {str(e)}", 500)

@teachers_bp.route('/export', methods=['GET'])
@jwt_required()
@admin_required
def export_teachers():
    """Export teachers list as CSV."""
    try:
        # Get filters
        department = request.args.get('department')
        is_active = request.args.get('is_active', type=bool, default=True)
        
        # Build query
        query = User.query.filter(
            User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR])
        )
        
        if is_active is not None:
            query = query.filter_by(is_active=is_active)
        
        teachers = query.all()
        
        # Create DataFrame
        data = []
        for teacher in teachers:
            stats = get_teacher_statistics(teacher.id)
            
            data.append({
                'id': teacher.id,
                'name': teacher.name,
                'email': teacher.email,
                'role': teacher.role.value,
                'section': teacher.section.value if teacher.section else '',
                'phone': teacher.phone or '',
                'is_active': 'نعم' if teacher.is_active else 'لا',
                'total_lectures': stats['total_lectures'],
                'active_lectures': stats['active_lectures'],
                'average_attendance_rate': f"{stats['average_attendance_rate']:.1f}%",
                'created_at': teacher.created_at.strftime('%Y-%m-%d')
            })
        
        df = pd.DataFrame(data)
        
        # Convert to CSV
        output = io.StringIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')
        output.seek(0)
        
        return output.getvalue(), 200, {
            'Content-Type': 'text/csv; charset=utf-8',
            'Content-Disposition': 'attachment; filename=teachers_export.csv'
        }
        
    except Exception as e:
        return error_response(f"Error exporting teachers: {str(e)}", 500)

@teachers_bp.route('/bulk-update', methods=['POST'])
@jwt_required()
@super_admin_required
@limiter.limit("3 per hour")
def bulk_update_teachers():
    """Bulk update teachers from CSV/Excel file."""
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
        required_columns = ['id', 'name', 'email']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return error_response(f"Missing columns: {', '.join(missing_columns)}", 400)
        
        # Process updates
        results = []
        for index, row in df.iterrows():
            try:
                teacher_id = int(row['id'])
                teacher = User.query.filter(
                    User.id == teacher_id,
                    User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR])
                ).first()
                
                if not teacher:
                    results.append({
                        'row': index + 2,
                        'teacher_id': teacher_id,
                        'success': False,
                        'error': 'Teacher not found'
                    })
                    continue
                
                # Update fields
                teacher.name = row['name'].strip()
                teacher.email = row['email'].lower().strip()
                
                if 'section' in row and row['section']:
                    teacher.section = Section[row['section'].upper()]
                
                if 'phone' in row:
                    teacher.phone = row['phone'].strip() or None
                
                if 'is_active' in row:
                    teacher.is_active = str(row['is_active']).lower() in ['true', '1', 'نعم', 'yes']
                
                teacher.updated_at = datetime.utcnow()
                
                results.append({
                    'row': index + 2,
                    'teacher_id': teacher_id,
                    'name': teacher.name,
                    'success': True
                })
                
            except Exception as e:
                results.append({
                    'row': index + 2,
                    'teacher_id': row.get('id', 'unknown'),
                    'success': False,
                    'error': str(e)
                })
        
        db.session.commit()
        
        return success_response(
            data={
                'total': len(results),
                'successful': len([r for r in results if r['success']]),
                'failed': len([r for r in results if not r['success']]),
                'results': results
            },
            message="Bulk update completed"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Error in bulk update: {str(e)}", 500)

# =================== HELPER FUNCTIONS ===================

def get_teacher_statistics(teacher_id: int) -> dict:
    """Get basic teacher statistics."""
    try:
        # Total lectures
        total_lectures = Lecture.query.filter_by(
            teacher_id=teacher_id,
            is_active=True
        ).count()
        
        # Active lectures (future lectures)
        active_lectures = Lecture.query.filter_by(
            teacher_id=teacher_id,
            is_active=True
        ).filter(Lecture.start_time > datetime.utcnow()).count()
        
        # Past lectures
        past_lectures = Lecture.query.filter_by(
            teacher_id=teacher_id,
            is_active=True
        ).filter(Lecture.end_time < datetime.utcnow()).count()
        
        # Average attendance rate
        attendance_query = db.session.query(
            func.avg(
                db.case(
                    [(AttendanceRecord.is_present == True, 100.0)],
                    else_=0.0
                )
            )
        ).join(Lecture).filter(Lecture.teacher_id == teacher_id)
        
        avg_attendance = attendance_query.scalar() or 0.0
        
        return {
            'total_lectures': total_lectures,
            'active_lectures': active_lectures,
            'past_lectures': past_lectures,
            'average_attendance_rate': round(avg_attendance, 2)
        }
        
    except Exception:
        return {
            'total_lectures': 0,
            'active_lectures': 0,
            'past_lectures': 0,
            'average_attendance_rate': 0.0
        }

def get_teacher_comprehensive_statistics(teacher_id: int) -> dict:
    """Get comprehensive teacher statistics."""
    try:
        basic_stats = get_teacher_statistics(teacher_id)
        
        # Additional statistics
        # Total unique students taught
        unique_students = db.session.query(
            func.count(distinct(AttendanceRecord.student_id))
        ).join(Lecture).filter(Lecture.teacher_id == teacher_id).scalar() or 0
        
        # This month's lectures
        start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        this_month_lectures = Lecture.query.filter_by(
            teacher_id=teacher_id,
            is_active=True
        ).filter(Lecture.start_time >= start_of_month).count()
        
        # This week's lectures
        start_of_week = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        this_week_lectures = Lecture.query.filter_by(
            teacher_id=teacher_id,
            is_active=True
        ).filter(Lecture.start_time >= start_of_week).count()
        
        # Attendance trends (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_attendance = db.session.query(
            func.date(Lecture.start_time).label('date'),
            func.count(AttendanceRecord.id).label('total'),
            func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present')
        ).join(Lecture).filter(
            Lecture.teacher_id == teacher_id,
            Lecture.start_time >= thirty_days_ago
        ).group_by(func.date(Lecture.start_time)).all()
        
        attendance_trend = []
        for date, total, present in recent_attendance:
            attendance_trend.append({
                'date': date.isoformat(),
                'total_students': total,
                'present_students': present or 0,
                'attendance_rate': round((present or 0) / total * 100, 2) if total > 0 else 0
            })
        
        return {
            **basic_stats,
            'unique_students_taught': unique_students,
            'this_month_lectures': this_month_lectures,
            'this_week_lectures': this_week_lectures,
            'attendance_trend_30_days': attendance_trend,
            'performance_metrics': {
                'consistency_score': calculate_teacher_consistency_score(teacher_id),
                'engagement_score': calculate_teacher_engagement_score(teacher_id)
            }
        }
        
    except Exception as e:
        return get_teacher_statistics(teacher_id)

def calculate_teacher_consistency_score(teacher_id: int) -> float:
    """Calculate teacher consistency score based on lecture regularity."""
    try:
        # Get last 30 days of scheduled vs actual lectures
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        scheduled_lectures = Schedule.query.filter_by(
            teacher_id=teacher_id,
            is_active=True
        ).count()
        
        actual_lectures = Lecture.query.filter_by(
            teacher_id=teacher_id,
            is_active=True
        ).filter(Lecture.start_time >= thirty_days_ago).count()
        
        if scheduled_lectures == 0:
            return 0.0
        
        consistency = min(1.0, actual_lectures / (scheduled_lectures * 4.3))  # ~30 days / 7 days
        return round(consistency * 100, 2)
        
    except Exception:
        return 0.0

def calculate_teacher_engagement_score(teacher_id: int) -> float:
    """Calculate teacher engagement score based on attendance rates."""
    try:
        # Average attendance rate for this teacher
        avg_attendance = db.session.query(
            func.avg(
                db.case(
                    [(AttendanceRecord.is_present == True, 100.0)],
                    else_=0.0
                )
            )
        ).join(Lecture).filter(Lecture.teacher_id == teacher_id).scalar() or 0.0
        
        # Normalize to engagement score (attendance rate is a good proxy)
        return round(avg_attendance, 2)
        
    except Exception:
        return 0.0