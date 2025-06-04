# File: backend/app/api/statistics.py
"""Comprehensive Statistics API for system analytics and insights."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.user import User, UserRole
from app.models.student import Student, Section, StudyType, StudentStatus
from app.models.lecture import Lecture
from app.models.attendance import AttendanceRecord
from app.models.schedule import Schedule, WeekDay
from app.models.room import Room
from app.utils.helpers import success_response, error_response
from app.utils.decorators import admin_required, teacher_required
from datetime import datetime, timedelta, date
from sqlalchemy import func, and_, or_, distinct, text
from typing import Dict, List, Any, Optional
import json

statistics_bp = Blueprint('statistics', __name__)

@statistics_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Statistics service is running')

# =================== OVERVIEW STATISTICS ===================

@statistics_bp.route('/overview', methods=['GET'])
@jwt_required()
@admin_required
def system_overview():
    """Get comprehensive system overview statistics."""
    try:
        # Time period for trends
        period_days = request.args.get('period_days', type=int, default=30)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=period_days)
        
        # Basic counts
        total_students = Student.query.filter_by(status=StudentStatus.ACTIVE).count()
        total_teachers = User.query.filter(User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR])).count()
        total_rooms = Room.query.filter_by(is_active=True).count()
        total_lectures = Lecture.query.filter_by(is_active=True).count()
        
        # Active lectures (today)
        today = date.today()
        today_lectures = Lecture.query.filter(
            func.date(Lecture.start_time) == today,
            Lecture.is_active == True
        ).count()
        
        # Current active lecture (right now)
        now = datetime.utcnow()
        active_now = Lecture.query.filter(
            Lecture.start_time <= now,
            Lecture.end_time >= now,
            Lecture.is_active == True
        ).count()
        
        # Attendance statistics for the period
        period_attendance = db.session.query(
            func.count(AttendanceRecord.id).label('total_records'),
            func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present_count'),
            func.count(distinct(AttendanceRecord.student_id)).label('unique_students'),
            func.count(distinct(AttendanceRecord.lecture_id)).label('unique_lectures')
        ).join(Lecture).filter(
            Lecture.start_time >= start_date,
            Lecture.start_time <= end_date
        ).first()
        
        total_records = period_attendance.total_records or 0
        present_count = period_attendance.present_count or 0
        unique_students = period_attendance.unique_students or 0
        unique_lectures = period_attendance.unique_lectures or 0
        
        overall_attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
        
        # Trends (daily attendance for the last 7 days)
        daily_trends = []
        for i in range(6, -1, -1):  # Last 7 days
            day = (datetime.utcnow() - timedelta(days=i)).date()
            
            day_stats = db.session.query(
                func.count(AttendanceRecord.id).label('total'),
                func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present')
            ).join(Lecture).filter(
                func.date(Lecture.start_time) == day
            ).first()
            
            day_total = day_stats.total or 0
            day_present = day_stats.present or 0
            day_rate = (day_present / day_total * 100) if day_total > 0 else 0
            
            daily_trends.append({
                'date': day.isoformat(),
                'day_name': day.strftime('%A'),
                'total_students': day_total,
                'present_students': day_present,
                'attendance_rate': round(day_rate, 2)
            })
        
        # System performance metrics
        performance_metrics = calculate_system_performance_metrics()
        
        # Recent activity (last 24 hours)
        yesterday = datetime.utcnow() - timedelta(hours=24)
        recent_activity = {
            'new_attendance_records': AttendanceRecord.query.filter(
                AttendanceRecord.created_at >= yesterday
            ).count(),
            'new_lectures': Lecture.query.filter(
                Lecture.created_at >= yesterday
            ).count(),
            'new_students': Student.query.filter(
                Student.created_at >= yesterday
            ).count()
        }
        
        return success_response(
            data={
                'overview': {
                    'total_students': total_students,
                    'total_teachers': total_teachers,
                    'total_rooms': total_rooms,
                    'total_lectures': total_lectures,
                    'today_lectures': today_lectures,
                    'active_lectures_now': active_now
                },
                'attendance_summary': {
                    'period_days': period_days,
                    'total_records': total_records,
                    'present_count': present_count,
                    'absent_count': total_records - present_count,
                    'unique_students': unique_students,
                    'unique_lectures': unique_lectures,
                    'overall_attendance_rate': round(overall_attendance_rate, 2)
                },
                'daily_trends': daily_trends,
                'performance_metrics': performance_metrics,
                'recent_activity': recent_activity
            },
            message="System overview statistics"
        )
        
    except Exception as e:
        return error_response(f"Error generating overview: {str(e)}", 500)

# =================== ATTENDANCE STATISTICS ===================

@statistics_bp.route('/attendance', methods=['GET'])
@jwt_required()
@teacher_required
def attendance_statistics():
    """Get detailed attendance statistics."""
    try:
        # Parameters
        period = request.args.get('period', 'month')  # week, month, semester, year
        section = request.args.get('section')
        study_year = request.args.get('study_year', type=int)
        teacher_id = request.args.get('teacher_id', type=int)
        
        # Calculate period boundaries
        end_date = datetime.utcnow()
        
        if period == 'week':
            start_date = end_date - timedelta(days=7)
        elif period == 'month':
            start_date = end_date - timedelta(days=30)
        elif period == 'semester':
            # Assume 4 months for a semester
            start_date = end_date - timedelta(days=120)
        elif period == 'year':
            start_date = end_date - timedelta(days=365)
        else:
            start_date = end_date - timedelta(days=30)  # Default to month
        
        # Apply user role restrictions
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)
        
        # Base query
        base_query = db.session.query(AttendanceRecord).join(Lecture).filter(
            Lecture.start_time >= start_date,
            Lecture.start_time <= end_date
        )
        
        # Apply filters
        if current_user.role == UserRole.TEACHER:
            base_query = base_query.filter(Lecture.teacher_id == current_user_id)
        elif teacher_id:
            base_query = base_query.filter(Lecture.teacher_id == teacher_id)
        
        if section:
            base_query = base_query.join(Student, AttendanceRecord.student_id == Student.user_id)
            base_query = base_query.filter(Student.section == Section[section.upper()])
        
        if study_year:
            if not section:  # Join Student if not already joined
                base_query = base_query.join(Student, AttendanceRecord.student_id == Student.user_id)
            base_query = base_query.filter(Student.study_year == study_year)
        
        # Overall statistics
        total_records = base_query.count()
        present_records = base_query.filter(AttendanceRecord.is_present == True).count()
        absent_records = total_records - present_records
        exceptional_records = base_query.filter(AttendanceRecord.is_exceptional == True).count()
        
        overall_rate = (present_records / total_records * 100) if total_records > 0 else 0
        
        # By verification method
        verification_methods = db.session.query(
            AttendanceRecord.verification_method,
            func.count(AttendanceRecord.id).label('count'),
            func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present_count')
        ).filter(
            AttendanceRecord.id.in_([r.id for r in base_query.all()])
        ).group_by(AttendanceRecord.verification_method).all()
        
        verification_stats = []
        for method, count, present_count in verification_methods:
            verification_stats.append({
                'method': method or 'unknown',
                'total_count': count,
                'present_count': present_count or 0,
                'success_rate': round((present_count or 0) / count * 100, 2) if count > 0 else 0
            })
        
        # By section (if not already filtered)
        if not section:
            section_stats = db.session.query(
                Student.section,
                func.count(AttendanceRecord.id).label('total'),
                func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present')
            ).select_from(AttendanceRecord).join(
                Student, AttendanceRecord.student_id == Student.user_id
            ).join(
                Lecture, AttendanceRecord.lecture_id == Lecture.id
            ).filter(
                Lecture.start_time >= start_date,
                Lecture.start_time <= end_date
            )
            
            if current_user.role == UserRole.TEACHER:
                section_stats = section_stats.filter(Lecture.teacher_id == current_user_id)
            elif teacher_id:
                section_stats = section_stats.filter(Lecture.teacher_id == teacher_id)
            
            section_stats = section_stats.group_by(Student.section).all()
            
            section_breakdown = []
            for section_enum, total, present in section_stats:
                section_breakdown.append({
                    'section': section_enum.value if section_enum else 'Unknown',
                    'total_records': total,
                    'present_count': present or 0,
                    'attendance_rate': round((present or 0) / total * 100, 2) if total > 0 else 0
                })
        else:
            section_breakdown = []
        
        # Daily breakdown for the period
        daily_breakdown = db.session.query(
            func.date(Lecture.start_time).label('date'),
            func.count(AttendanceRecord.id).label('total'),
            func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present')
        ).select_from(AttendanceRecord).join(
            Lecture, AttendanceRecord.lecture_id == Lecture.id
        ).filter(
            Lecture.start_time >= start_date,
            Lecture.start_time <= end_date
        )
        
        if current_user.role == UserRole.TEACHER:
            daily_breakdown = daily_breakdown.filter(Lecture.teacher_id == current_user_id)
        elif teacher_id:
            daily_breakdown = daily_breakdown.filter(Lecture.teacher_id == teacher_id)
        
        if section:
            daily_breakdown = daily_breakdown.join(Student, AttendanceRecord.student_id == Student.user_id)
            daily_breakdown = daily_breakdown.filter(Student.section == Section[section.upper()])
        
        daily_breakdown = daily_breakdown.group_by(func.date(Lecture.start_time)).order_by(func.date(Lecture.start_time)).all()
        
        daily_stats = []
        for date_obj, total, present in daily_breakdown:
            daily_stats.append({
                'date': date_obj.isoformat(),
                'day_name': date_obj.strftime('%A'),
                'total_records': total,
                'present_count': present or 0,
                'attendance_rate': round((present or 0) / total * 100, 2) if total > 0 else 0
            })
        
        # Top performing days
        day_performance = db.session.query(
            func.extract('dow', Lecture.start_time).label('day_of_week'),
            func.count(AttendanceRecord.id).label('total'),
            func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present')
        ).select_from(AttendanceRecord).join(
            Lecture, AttendanceRecord.lecture_id == Lecture.id
        ).filter(
            Lecture.start_time >= start_date,
            Lecture.start_time <= end_date
        )
        
        if current_user.role == UserRole.TEACHER:
            day_performance = day_performance.filter(Lecture.teacher_id == current_user_id)
        elif teacher_id:
            day_performance = day_performance.filter(Lecture.teacher_id == teacher_id)
        
        day_performance = day_performance.group_by(func.extract('dow', Lecture.start_time)).all()
        
        # Map day numbers to names
        day_names = {0: 'Sunday', 1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 
                    4: 'Thursday', 5: 'Friday', 6: 'Saturday'}
        
        day_stats = []
        for day_num, total, present in day_performance:
            day_stats.append({
                'day_name': day_names.get(int(day_num), 'Unknown'),
                'total_records': total,
                'present_count': present or 0,
                'attendance_rate': round((present or 0) / total * 100, 2) if total > 0 else 0
            })
        
        # Sort by attendance rate
        day_stats.sort(key=lambda x: x['attendance_rate'], reverse=True)
        
        return success_response(
            data={
                'period_info': {
                    'period': period,
                    'start_date': start_date.date().isoformat(),
                    'end_date': end_date.date().isoformat(),
                    'days_covered': (end_date - start_date).days
                },
                'overall_statistics': {
                    'total_records': total_records,
                    'present_records': present_records,
                    'absent_records': absent_records,
                    'exceptional_records': exceptional_records,
                    'overall_attendance_rate': round(overall_rate, 2)
                },
                'verification_method_breakdown': verification_stats,
                'section_breakdown': section_breakdown,
                'daily_breakdown': daily_stats,
                'day_of_week_performance': day_stats
            },
            message=f"Attendance statistics for {period}"
        )
        
    except Exception as e:
        return error_response(f"Error generating attendance statistics: {str(e)}", 500)

# =================== STUDENTS STATISTICS ===================

@statistics_bp.route('/students', methods=['GET'])
@jwt_required()
@admin_required
def students_statistics():
    """Get comprehensive student statistics."""
    try:
        # Basic student counts
        total_students = Student.query.count()
        active_students = Student.query.filter_by(status=StudentStatus.ACTIVE).count()
        inactive_students = total_students - active_students
        
        # By section
        section_stats = db.session.query(
            Student.section,
            func.count(Student.id).label('count')
        ).filter_by(status=StudentStatus.ACTIVE).group_by(Student.section).all()
        
        section_breakdown = []
        for section, count in section_stats:
            if section:
                section_breakdown.append({
                    'section': section.value,
                    'student_count': count
                })
        
        # By study year
        year_stats = db.session.query(
            Student.study_year,
            func.count(Student.id).label('count')
        ).filter_by(status=StudentStatus.ACTIVE).group_by(Student.study_year).all()
        
        year_breakdown = []
        for year, count in year_stats:
            year_breakdown.append({
                'study_year': year,
                'student_count': count
            })
        
        # By study type
        type_stats = db.session.query(
            Student.study_type,
            func.count(Student.id).label('count')
        ).filter_by(status=StudentStatus.ACTIVE).group_by(Student.study_type).all()
        
        type_breakdown = []
        for study_type, count in type_stats:
            if study_type:
                type_breakdown.append({
                    'study_type': study_type.value,
                    'student_count': count
                })
        
        # Repeaters statistics
        repeaters_count = Student.query.filter_by(
            status=StudentStatus.ACTIVE,
            is_repeater=True
        ).count()
        
        repeaters_rate = (repeaters_count / active_students * 100) if active_students > 0 else 0
        
        # Face registration statistics
        face_registered = Student.query.filter_by(
            status=StudentStatus.ACTIVE,
            face_registered=True
        ).count()
        
        face_registration_rate = (face_registered / active_students * 100) if active_students > 0 else 0
        
        # Recent enrollments (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_enrollments = Student.query.filter(
            Student.created_at >= thirty_days_ago
        ).count()
        
        # Top performing students (by attendance rate)
        top_students = db.session.query(
            Student.university_id,
            Student.full_name,
            Student.section,
            Student.study_year,
            func.count(AttendanceRecord.id).label('total_lectures'),
            func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present_count'),
            (func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)) * 100.0 / 
             func.count(AttendanceRecord.id)).label('attendance_rate')
        ).join(
            AttendanceRecord, Student.user_id == AttendanceRecord.student_id
        ).filter(
            Student.status == StudentStatus.ACTIVE
        ).group_by(
            Student.id, Student.university_id, Student.full_name, Student.section, Student.study_year
        ).having(
            func.count(AttendanceRecord.id) >= 5  # At least 5 lectures
        ).order_by(
            text('attendance_rate DESC')
        ).limit(10).all()
        
        top_performers = []
        for student in top_students:
            top_performers.append({
                'university_id': student.university_id,
                'full_name': student.full_name,
                'section': student.section.value if student.section else None,
                'study_year': student.study_year,
                'total_lectures': student.total_lectures,
                'present_count': student.present_count,
                'attendance_rate': round(float(student.attendance_rate), 2)
            })
        
        # Students needing attention (low attendance)
        low_attendance_students = db.session.query(
            Student.university_id,
            Student.full_name,
            Student.section,
            Student.study_year,
            func.count(AttendanceRecord.id).label('total_lectures'),
            func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present_count'),
            (func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)) * 100.0 / 
             func.count(AttendanceRecord.id)).label('attendance_rate')
        ).join(
            AttendanceRecord, Student.user_id == AttendanceRecord.student_id
        ).filter(
            Student.status == StudentStatus.ACTIVE
        ).group_by(
            Student.id, Student.university_id, Student.full_name, Student.section, Student.study_year
        ).having(
            and_(
                func.count(AttendanceRecord.id) >= 5,  # At least 5 lectures
                (func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)) * 100.0 / 
                 func.count(AttendanceRecord.id)) < 70  # Less than 70% attendance
            )
        ).order_by(
            text('attendance_rate ASC')
        ).limit(10).all()
        
        attention_needed = []
        for student in low_attendance_students:
            attention_needed.append({
                'university_id': student.university_id,
                'full_name': student.full_name,
                'section': student.section.value if student.section else None,
                'study_year': student.study_year,
                'total_lectures': student.total_lectures,
                'present_count': student.present_count,
                'attendance_rate': round(float(student.attendance_rate), 2)
            })
        
        return success_response(
            data={
                'overview': {
                    'total_students': total_students,
                    'active_students': active_students,
                    'inactive_students': inactive_students,
                    'repeaters_count': repeaters_count,
                    'repeaters_rate': round(repeaters_rate, 2),
                    'face_registered_count': face_registered,
                    'face_registration_rate': round(face_registration_rate, 2),
                    'recent_enrollments_30_days': recent_enrollments
                },
                'breakdowns': {
                    'by_section': section_breakdown,
                    'by_study_year': year_breakdown,
                    'by_study_type': type_breakdown
                },
                'performance': {
                    'top_performers': top_performers,
                    'attention_needed': attention_needed
                }
            },
            message="Student statistics"
        )
        
    except Exception as e:
        return error_response(f"Error generating student statistics: {str(e)}", 500)

# =================== TEACHERS STATISTICS ===================

@statistics_bp.route('/teachers', methods=['GET'])
@jwt_required()
@admin_required
def teachers_statistics():
    """Get comprehensive teacher statistics."""
    try:
        # Basic teacher counts
        total_teachers = User.query.filter(User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR])).count()
        active_teachers = User.query.filter(
            User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR]),
            User.is_active == True
        ).count()
        
        # Teachers by role
        role_stats = db.session.query(
            User.role,
            func.count(User.id).label('count')
        ).filter(
            User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR]),
            User.is_active == True
        ).group_by(User.role).all()
        
        role_breakdown = []
        for role, count in role_stats:
            role_breakdown.append({
                'role': role.value,
                'teacher_count': count
            })
        
        # Teaching load statistics
        teaching_stats = db.session.query(
            User.id,
            User.name,
            func.count(distinct(Lecture.id)).label('total_lectures'),
            func.count(distinct(Schedule.id)).label('scheduled_subjects'),
            func.count(distinct(func.date(Lecture.start_time))).label('teaching_days')
        ).outerjoin(
            Lecture, and_(Lecture.teacher_id == User.id, Lecture.is_active == True)
        ).outerjoin(
            Schedule, and_(Schedule.teacher_id == User.id, Schedule.is_active == True)
        ).filter(
            User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR]),
            User.is_active == True
        ).group_by(User.id, User.name).all()
        
        teacher_workload = []
        total_lectures_all = 0
        for teacher_stat in teaching_stats:
            total_lectures_all += teacher_stat.total_lectures
            teacher_workload.append({
                'teacher_id': teacher_stat.id,
                'teacher_name': teacher_stat.name,
                'total_lectures': teacher_stat.total_lectures,
                'scheduled_subjects': teacher_stat.scheduled_subjects,
                'teaching_days': teacher_stat.teaching_days
            })
        
        # Sort by total lectures
        teacher_workload.sort(key=lambda x: x['total_lectures'], reverse=True)
        
        # Average workload
        avg_lectures_per_teacher = total_lectures_all / active_teachers if active_teachers > 0 else 0
        
        # Teacher performance (by student attendance rates)
        teacher_performance = db.session.query(
            User.id,
            User.name,
            func.count(AttendanceRecord.id).label('total_attendance_records'),
            func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present_records'),
            (func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)) * 100.0 / 
             func.count(AttendanceRecord.id)).label('average_attendance_rate')
        ).join(
            Lecture, Lecture.teacher_id == User.id
        ).outerjoin(
            AttendanceRecord, AttendanceRecord.lecture_id == Lecture.id
        ).filter(
            User.role.in_([UserRole.TEACHER, UserRole.COORDINATOR]),
            User.is_active == True,
            Lecture.is_active == True
        ).group_by(
            User.id, User.name
        ).having(
            func.count(AttendanceRecord.id) >= 10  # At least 10 attendance records
        ).order_by(
            text('average_attendance_rate DESC')
        ).all()
        
        performance_data = []
        for perf in teacher_performance:
            performance_data.append({
                'teacher_id': perf.id,
                'teacher_name': perf.name,
                'total_records': perf.total_attendance_records,
                'present_records': perf.present_records,
                'average_attendance_rate': round(float(perf.average_attendance_rate), 2)
            })
        
        # Recent activity (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_lectures = db.session.query(
            User.name,
            func.count(Lecture.id).label('lecture_count')
        ).join(
            Lecture, Lecture.teacher_id == User.id
        ).filter(
            Lecture.created_at >= thirty_days_ago,
            Lecture.is_active == True
        ).group_by(User.id, User.name).order_by(func.count(Lecture.id).desc()).limit(5).all()
        
        most_active_teachers = []
        for teacher, count in recent_lectures:
            most_active_teachers.append({
                'teacher_name': teacher,
                'lectures_created': count
            })
        
        return success_response(
            data={
                'overview': {
                    'total_teachers': total_teachers,
                    'active_teachers': active_teachers,
                    'average_lectures_per_teacher': round(avg_lectures_per_teacher, 2)
                },
                'role_breakdown': role_breakdown,
                'workload_analysis': {
                    'top_teachers_by_workload': teacher_workload[:10],
                    'average_workload': {
                        'lectures_per_teacher': round(avg_lectures_per_teacher, 2)
                    }
                },
                'performance_analysis': performance_data,
                'recent_activity': {
                    'most_active_teachers_30_days': most_active_teachers
                }
            },
            message="Teacher statistics"
        )
        
    except Exception as e:
        return error_response(f"Error generating teacher statistics: {str(e)}", 500)

# =================== ROOMS STATISTICS ===================

@statistics_bp.route('/rooms', methods=['GET'])
@jwt_required()
@admin_required
def rooms_statistics():
    """Get comprehensive room utilization statistics."""
    try:
        # Basic room counts
        total_rooms = Room.query.count()
        active_rooms = Room.query.filter_by(is_active=True).count()
        rooms_3d_validated = Room.query.filter_by(is_3d_validated=True).count()
        
        # Room capacity analysis
        capacity_stats = db.session.query(
            func.sum(Room.capacity).label('total_capacity'),
            func.avg(Room.capacity).label('average_capacity'),
            func.min(Room.capacity).label('min_capacity'),
            func.max(Room.capacity).label('max_capacity')
        ).filter_by(is_active=True).first()
        
        # Rooms by building
        building_stats = db.session.query(
            Room.building,
            func.count(Room.id).label('room_count'),
            func.sum(Room.capacity).label('total_capacity')
        ).filter_by(is_active=True).group_by(Room.building).all()
        
        building_breakdown = []
        for building, room_count, total_cap in building_stats:
            building_breakdown.append({
                'building': building,
                'room_count': room_count,
                'total_capacity': total_cap or 0
            })
        
        # Rooms by floor
        floor_stats = db.session.query(
            Room.floor,
            func.count(Room.id).label('room_count')
        ).filter_by(is_active=True).group_by(Room.floor).order_by(Room.floor).all()
        
        floor_breakdown = []
        for floor, room_count in floor_stats:
            floor_breakdown.append({
                'floor': floor,
                'room_count': room_count
            })
        
        # Room utilization (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        utilization_stats = db.session.query(
            Room.id,
            Room.name,
            Room.building,
            Room.capacity,
            func.count(Lecture.id).label('lectures_count'),
            func.sum(
                func.extract('epoch', Lecture.end_time - Lecture.start_time) / 3600
            ).label('total_hours_used')
        ).outerjoin(
            Lecture, and_(
                Lecture.room_id == Room.id,
                Lecture.start_time >= thirty_days_ago,
                Lecture.is_active == True
            )
        ).filter(
            Room.is_active == True
        ).group_by(
            Room.id, Room.name, Room.building, Room.capacity
        ).order_by(
            func.count(Lecture.id).desc()
        ).all()
        
        # Calculate utilization rates
        available_hours_per_day = 8  # Assume 8 hours available per day
        days_in_period = 30
        total_available_hours = available_hours_per_day * days_in_period
        
        room_utilization = []
        for room_stat in utilization_stats:
            hours_used = float(room_stat.total_hours_used or 0)
            utilization_rate = (hours_used / total_available_hours * 100) if total_available_hours > 0 else 0
            
            room_utilization.append({
                'room_id': room_stat.id,
                'room_name': room_stat.name,
                'building': room_stat.building,
                'capacity': room_stat.capacity,
                'lectures_count': room_stat.lectures_count,
                'hours_used': round(hours_used, 2),
                'utilization_rate': round(utilization_rate, 2)
            })
        
        # Most and least utilized rooms
        most_utilized = sorted(room_utilization, key=lambda x: x['utilization_rate'], reverse=True)[:5]
        least_utilized = sorted(room_utilization, key=lambda x: x['utilization_rate'])[:5]
        
        # Average utilization
        total_utilization = sum([r['utilization_rate'] for r in room_utilization])
        avg_utilization = total_utilization / len(room_utilization) if room_utilization else 0
        
        # Peak usage times analysis
        peak_times = db.session.query(
            func.extract('hour', Lecture.start_time).label('hour'),
            func.count(Lecture.id).label('lecture_count')
        ).filter(
            Lecture.start_time >= thirty_days_ago,
            Lecture.is_active == True
        ).group_by(
            func.extract('hour', Lecture.start_time)
        ).order_by(
            func.count(Lecture.id).desc()
        ).all()
        
        peak_hours = []
        for hour, count in peak_times:
            peak_hours.append({
                'hour': f"{int(hour):02d}:00",
                'lecture_count': count
            })
        
        return success_response(
            data={
                'overview': {
                    'total_rooms': total_rooms,
                    'active_rooms': active_rooms,
                    'rooms_3d_validated': rooms_3d_validated,
                    'total_capacity': capacity_stats.total_capacity or 0,
                    'average_capacity': round(float(capacity_stats.average_capacity or 0), 2),
                    'capacity_range': {
                        'min': capacity_stats.min_capacity or 0,
                        'max': capacity_stats.max_capacity or 0
                    }
                },
                'breakdowns': {
                    'by_building': building_breakdown,
                    'by_floor': floor_breakdown
                },
                'utilization_analysis': {
                    'average_utilization_rate': round(avg_utilization, 2),
                    'most_utilized_rooms': most_utilized,
                    'least_utilized_rooms': least_utilized,
                    'peak_usage_hours': peak_hours
                },
                'detailed_utilization': room_utilization
            },
            message="Room statistics and utilization analysis"
        )
        
    except Exception as e:
        return error_response(f"Error generating room statistics: {str(e)}", 500)

# =================== SYSTEM STATISTICS ===================

@statistics_bp.route('/system', methods=['GET'])
@jwt_required()
@admin_required
def system_statistics():
    """Get system performance and technical statistics."""
    try:
        # Database statistics
        db_stats = {
            'total_users': User.query.count(),
            'total_students': Student.query.count(),
            'total_lectures': Lecture.query.count(),
            'total_attendance_records': AttendanceRecord.query.count(),
            'total_schedules': Schedule.query.count(),
            'total_rooms': Room.query.count()
        }
        
        # Recent activity (last 24 hours)
        yesterday = datetime.utcnow() - timedelta(hours=24)
        recent_activity = {
            'new_attendance_records': AttendanceRecord.query.filter(
                AttendanceRecord.created_at >= yesterday
            ).count(),
            'new_lectures': Lecture.query.filter(
                Lecture.created_at >= yesterday
            ).count(),
            'new_users': User.query.filter(
                User.created_at >= yesterday
            ).count()
        }
        
        # System health metrics
        health_metrics = calculate_system_performance_metrics()
        
        # Feature usage statistics
        feature_usage = {
            'face_recognition': {
                'students_registered': Student.query.filter_by(face_registered=True).count(),
                'usage_rate': round(
                    Student.query.filter_by(face_registered=True).count() / 
                    Student.query.filter_by(status=StudentStatus.ACTIVE).count() * 100, 2
                ) if Student.query.filter_by(status=StudentStatus.ACTIVE).count() > 0 else 0
            },
            'gps_verification': {
                'records_with_location': AttendanceRecord.query.filter(
                    AttendanceRecord.latitude.isnot(None),
                    AttendanceRecord.longitude.isnot(None)
                ).count()
            },
            'exceptional_attendance': {
                'total_exceptional': AttendanceRecord.query.filter_by(is_exceptional=True).count(),
                'approved_exceptional': AttendanceRecord.query.filter(
                    AttendanceRecord.is_exceptional == True,
                    AttendanceRecord.approved_by.isnot(None)
                ).count()
            },
            'qr_verification': {
                'qr_verified_records': AttendanceRecord.query.filter_by(verification_method='qr').count()
            }
        }
        
        # Performance trends (last 7 days)
        performance_trends = []
        for i in range(6, -1, -1):
            day = (datetime.utcnow() - timedelta(days=i)).date()
            
            day_records = AttendanceRecord.query.join(Lecture).filter(
                func.date(Lecture.start_time) == day
            ).count()
            
            performance_trends.append({
                'date': day.isoformat(),
                'attendance_records': day_records
            })
        
        # Error rates and system issues
        error_stats = {
            'failed_verifications': AttendanceRecord.query.filter(
                AttendanceRecord.is_present == False,
                AttendanceRecord.is_exceptional == False
            ).count(),
            'pending_approvals': AttendanceRecord.query.filter(
                AttendanceRecord.is_exceptional == True,
                AttendanceRecord.approved_by.is_(None)
            ).count()
        }
        
        return success_response(
            data={
                'database_statistics': db_stats,
                'recent_activity_24h': recent_activity,
                'system_health': health_metrics,
                'feature_usage': feature_usage,
                'performance_trends': performance_trends,
                'error_statistics': error_stats
            },
            message="System statistics and health metrics"
        )
        
    except Exception as e:
        return error_response(f"Error generating system statistics: {str(e)}", 500)

# =================== REAL-TIME STATISTICS ===================

@statistics_bp.route('/realtime', methods=['GET'])
@jwt_required()
@admin_required
def realtime_statistics():
    """Get real-time system statistics."""
    try:
        now = datetime.utcnow()
        today = now.date()
        
        # Current active lectures
        active_lectures = Lecture.query.filter(
            Lecture.start_time <= now,
            Lecture.end_time >= now,
            Lecture.is_active == True
        ).all()
        
        # Today's statistics
        today_stats = {
            'scheduled_lectures': Lecture.query.filter(
                func.date(Lecture.start_time) == today,
                Lecture.is_active == True
            ).count(),
            'completed_lectures': Lecture.query.filter(
                func.date(Lecture.start_time) == today,
                Lecture.end_time < now,
                Lecture.is_active == True
            ).count(),
            'attendance_records_today': AttendanceRecord.query.join(Lecture).filter(
                func.date(Lecture.start_time) == today
            ).count(),
            'present_today': AttendanceRecord.query.join(Lecture).filter(
                func.date(Lecture.start_time) == today,
                AttendanceRecord.is_present == True
            ).count()
        }
        
        # Active lecture details
        active_lecture_details = []
        for lecture in active_lectures:
            attendance_count = AttendanceRecord.query.filter_by(lecture_id=lecture.id).count()
            present_count = AttendanceRecord.query.filter_by(
                lecture_id=lecture.id,
                is_present=True
            ).count()
            
            active_lecture_details.append({
                'lecture_id': lecture.id,
                'title': lecture.title,
                'teacher_name': lecture.teacher.name,
                'room': lecture.room,
                'start_time': lecture.start_time.isoformat(),
                'end_time': lecture.end_time.isoformat(),
                'attendance_count': attendance_count,
                'present_count': present_count,
                'time_remaining_minutes': int((lecture.end_time - now).total_seconds() / 60)
            })
        
        # Upcoming lectures (next 2 hours)
        next_two_hours = now + timedelta(hours=2)
        upcoming_lectures = Lecture.query.filter(
            Lecture.start_time > now,
            Lecture.start_time <= next_two_hours,
            Lecture.is_active == True
        ).order_by(Lecture.start_time).limit(10).all()
        
        upcoming_details = []
        for lecture in upcoming_lectures:
            upcoming_details.append({
                'lecture_id': lecture.id,
                'title': lecture.title,
                'teacher_name': lecture.teacher.name,
                'room': lecture.room,
                'start_time': lecture.start_time.isoformat(),
                'starts_in_minutes': int((lecture.start_time - now).total_seconds() / 60)
            })
        
        # System load indicators
        system_load = {
            'active_lectures_count': len(active_lectures),
            'peak_capacity_usage': calculate_peak_capacity_usage(),
            'concurrent_attendance_rate': calculate_concurrent_attendance_rate()
        }
        
        return success_response(
            data={
                'timestamp': now.isoformat(),
                'today_summary': today_stats,
                'active_lectures': {
                    'count': len(active_lectures),
                    'details': active_lecture_details
                },
                'upcoming_lectures': {
                    'count': len(upcoming_lectures),
                    'details': upcoming_details
                },
                'system_load': system_load
            },
            message="Real-time system statistics"
        )
        
    except Exception as e:
        return error_response(f"Error generating real-time statistics: {str(e)}", 500)

# =================== HELPER FUNCTIONS ===================

def calculate_system_performance_metrics() -> Dict:
    """Calculate system performance metrics."""
    try:
        # Response time simulation (in production, track actual response times)
        avg_response_time = 250  # milliseconds
        
        # Database query performance
        total_records = AttendanceRecord.query.count()
        uptime_percentage = 99.5  # Simulated uptime
        
        # Feature adoption rates
        students_with_face = Student.query.filter_by(face_registered=True).count()
        total_students = Student.query.filter_by(status=StudentStatus.ACTIVE).count()
        face_adoption_rate = (students_with_face / total_students * 100) if total_students > 0 else 0
        
        return {
            'response_time_ms': avg_response_time,
            'uptime_percentage': uptime_percentage,
            'total_records': total_records,
            'face_adoption_rate': round(face_adoption_rate, 2),
            'system_status': 'healthy' if uptime_percentage > 95 else 'degraded'
        }
        
    except Exception:
        return {
            'response_time_ms': 0,
            'uptime_percentage': 0,
            'total_records': 0,
            'face_adoption_rate': 0,
            'system_status': 'unknown'
        }

def calculate_peak_capacity_usage() -> float:
    """Calculate peak capacity usage percentage."""
    try:
        # Get current active lectures
        now = datetime.utcnow()
        active_lectures = Lecture.query.filter(
            Lecture.start_time <= now,
            Lecture.end_time >= now,
            Lecture.is_active == True
        ).all()
        
        if not active_lectures:
            return 0.0
        
        # Calculate total capacity being used
        used_capacity = 0
        for lecture in active_lectures:
            # Assume room capacity (simplified)
            used_capacity += 30  # Default room capacity
        
        # Total system capacity
        total_capacity = db.session.query(func.sum(Room.capacity)).filter_by(is_active=True).scalar() or 0
        
        return round((used_capacity / total_capacity * 100), 2) if total_capacity > 0 else 0.0
        
    except Exception:
        return 0.0

def calculate_concurrent_attendance_rate() -> float:
    """Calculate concurrent attendance rate for active lectures."""
    try:
        now = datetime.utcnow()
        
        # Get active lectures
        active_lectures = Lecture.query.filter(
            Lecture.start_time <= now,
            Lecture.end_time >= now,
            Lecture.is_active == True
        ).all()
        
        if not active_lectures:
            return 0.0
        
        total_expected = 0
        total_present = 0
        
        for lecture in active_lectures:
            attendance_records = AttendanceRecord.query.filter_by(lecture_id=lecture.id).all()
            total_expected += len(attendance_records)
            total_present += len([r for r in attendance_records if r.is_present])
        
        return round((total_present / total_expected * 100), 2) if total_expected > 0 else 0.0
        
    except Exception:
        return 0.0