# File: backend/app/api/reports.py
"""Comprehensive Reports API for attendance analytics and reporting."""
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.user import User, UserRole
from app.models.student import Student, Section, StudyType
from app.models.lecture import Lecture
from app.models.attendance import AttendanceRecord
from app.models.schedule import Schedule, WeekDay
from app.models.room import Room
from app.utils.helpers import success_response, error_response
from app.utils.decorators import admin_required, teacher_required
from datetime import datetime, timedelta, date
from sqlalchemy import func, and_, or_, distinct
import pandas as pd
import io
import json
from typing import Dict, List, Any, Optional
import tempfile
import os

reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Reports service is running')

# =================== ATTENDANCE REPORTS ===================

@reports_bp.route('/attendance/daily', methods=['GET'])
@jwt_required()
@teacher_required
def daily_attendance_report():
    """Generate daily attendance report."""
    try:
        # Get parameters
        target_date = request.args.get('date', date.today().isoformat())
        section = request.args.get('section')
        room_id = request.args.get('room_id', type=int)
        teacher_id = request.args.get('teacher_id', type=int)
        
        # Parse date
        try:
            report_date = datetime.fromisoformat(target_date).date()
        except ValueError:
            return error_response("Invalid date format. Use YYYY-MM-DD", 400)
        
        # Build query
        query = db.session.query(
            Lecture.id.label('lecture_id'),
            Lecture.title.label('lecture_title'),
            Lecture.room.label('room_name'),
            User.name.label('teacher_name'),
            func.count(AttendanceRecord.id).label('total_students'),
            func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present_students'),
            func.sum(db.case([(AttendanceRecord.is_present == False, 1)], else_=0)).label('absent_students')
        ).select_from(Lecture).join(
            User, Lecture.teacher_id == User.id
        ).outerjoin(
            AttendanceRecord, Lecture.id == AttendanceRecord.lecture_id
        ).filter(
            func.date(Lecture.start_time) == report_date,
            Lecture.is_active == True
        )
        
        # Apply filters
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)
        
        # Teachers can only see their own reports unless admin
        if current_user.role == UserRole.TEACHER:
            query = query.filter(Lecture.teacher_id == current_user_id)
        elif teacher_id:
            query = query.filter(Lecture.teacher_id == teacher_id)
        
        if section:
            # Join with students to filter by section
            query = query.join(Student, AttendanceRecord.student_id == Student.user_id)
            query = query.filter(Student.section == Section[section.upper()])
        
        if room_id:
            query = query.join(Room, Lecture.room_id == room_id)
        
        # Group by lecture
        query = query.group_by(
            Lecture.id, Lecture.title, Lecture.room, User.name
        )
        
        results = query.all()
        
        # Format results
        lectures_data = []
        total_lectures = len(results)
        total_students_overall = 0
        total_present_overall = 0
        
        for result in results:
            total_students = result.total_students or 0
            present_students = result.present_students or 0
            absent_students = result.absent_students or 0
            
            attendance_rate = (present_students / total_students * 100) if total_students > 0 else 0
            
            lectures_data.append({
                'lecture_id': result.lecture_id,
                'lecture_title': result.lecture_title,
                'room_name': result.room_name,
                'teacher_name': result.teacher_name,
                'total_students': total_students,
                'present_students': present_students,
                'absent_students': absent_students,
                'attendance_rate': round(attendance_rate, 2)
            })
            
            total_students_overall += total_students
            total_present_overall += present_students
        
        overall_attendance_rate = (total_present_overall / total_students_overall * 100) if total_students_overall > 0 else 0
        
        return success_response(
            data={
                'report_date': report_date.isoformat(),
                'summary': {
                    'total_lectures': total_lectures,
                    'total_students': total_students_overall,
                    'total_present': total_present_overall,
                    'total_absent': total_students_overall - total_present_overall,
                    'overall_attendance_rate': round(overall_attendance_rate, 2)
                },
                'lectures': lectures_data
            },
            message=f"Daily attendance report for {report_date}"
        )
        
    except Exception as e:
        return error_response(f"Error generating daily report: {str(e)}", 500)

@reports_bp.route('/attendance/weekly', methods=['GET'])
@jwt_required()
@teacher_required
def weekly_attendance_report():
    """Generate weekly attendance report."""
    try:
        # Get parameters
        week_start = request.args.get('week_start')
        section = request.args.get('section')
        teacher_id = request.args.get('teacher_id', type=int)
        
        # Calculate week boundaries
        if week_start:
            try:
                start_date = datetime.fromisoformat(week_start).date()
            except ValueError:
                return error_response("Invalid week_start format. Use YYYY-MM-DD", 400)
        else:
            # Default to current week (Sunday to Saturday)
            today = date.today()
            days_since_sunday = (today.weekday() + 1) % 7
            start_date = today - timedelta(days=days_since_sunday)
        
        end_date = start_date + timedelta(days=6)
        
        # Build query for each day of the week
        daily_stats = []
        week_total_students = 0
        week_total_present = 0
        
        for i in range(7):
            current_date = start_date + timedelta(days=i)
            
            # Get daily statistics
            daily_query = db.session.query(
                func.count(AttendanceRecord.id).label('total_students'),
                func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present_students')
            ).select_from(Lecture).outerjoin(
                AttendanceRecord, Lecture.id == AttendanceRecord.lecture_id
            ).filter(
                func.date(Lecture.start_time) == current_date,
                Lecture.is_active == True
            )
            
            # Apply filters
            current_user_id = get_jwt_identity()
            current_user = User.query.get(current_user_id)
            
            if current_user.role == UserRole.TEACHER:
                daily_query = daily_query.filter(Lecture.teacher_id == current_user_id)
            elif teacher_id:
                daily_query = daily_query.filter(Lecture.teacher_id == teacher_id)
            
            if section:
                daily_query = daily_query.join(Student, AttendanceRecord.student_id == Student.user_id)
                daily_query = daily_query.filter(Student.section == Section[section.upper()])
            
            result = daily_query.first()
            
            total_students = result.total_students or 0
            present_students = result.present_students or 0
            attendance_rate = (present_students / total_students * 100) if total_students > 0 else 0
            
            daily_stats.append({
                'date': current_date.isoformat(),
                'day_name': current_date.strftime('%A'),
                'total_students': total_students,
                'present_students': present_students,
                'absent_students': total_students - present_students,
                'attendance_rate': round(attendance_rate, 2)
            })
            
            week_total_students += total_students
            week_total_present += present_students
        
        overall_weekly_rate = (week_total_present / week_total_students * 100) if week_total_students > 0 else 0
        
        return success_response(
            data={
                'week_period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                },
                'summary': {
                    'total_students_week': week_total_students,
                    'total_present_week': week_total_present,
                    'total_absent_week': week_total_students - week_total_present,
                    'overall_attendance_rate': round(overall_weekly_rate, 2)
                },
                'daily_breakdown': daily_stats
            },
            message=f"Weekly attendance report for {start_date} to {end_date}"
        )
        
    except Exception as e:
        return error_response(f"Error generating weekly report: {str(e)}", 500)

@reports_bp.route('/attendance/monthly', methods=['GET'])
@jwt_required()
@teacher_required
def monthly_attendance_report():
    """Generate monthly attendance report."""
    try:
        # Get parameters
        year = request.args.get('year', type=int, default=datetime.now().year)
        month = request.args.get('month', type=int, default=datetime.now().month)
        section = request.args.get('section')
        teacher_id = request.args.get('teacher_id', type=int)
        
        if month < 1 or month > 12:
            return error_response("Invalid month. Use 1-12", 400)
        
        # Calculate month boundaries
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)
        
        # Weekly breakdown
        weekly_stats = []
        current_week_start = start_date
        
        while current_week_start <= end_date:
            week_end = min(current_week_start + timedelta(days=6), end_date)
            
            # Get week statistics
            week_query = db.session.query(
                func.count(AttendanceRecord.id).label('total_students'),
                func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present_students')
            ).select_from(Lecture).outerjoin(
                AttendanceRecord, Lecture.id == AttendanceRecord.lecture_id
            ).filter(
                and_(
                    func.date(Lecture.start_time) >= current_week_start,
                    func.date(Lecture.start_time) <= week_end
                ),
                Lecture.is_active == True
            )
            
            # Apply filters
            current_user_id = get_jwt_identity()
            current_user = User.query.get(current_user_id)
            
            if current_user.role == UserRole.TEACHER:
                week_query = week_query.filter(Lecture.teacher_id == current_user_id)
            elif teacher_id:
                week_query = week_query.filter(Lecture.teacher_id == teacher_id)
            
            if section:
                week_query = week_query.join(Student, AttendanceRecord.student_id == Student.user_id)
                week_query = week_query.filter(Student.section == Section[section.upper()])
            
            result = week_query.first()
            
            total_students = result.total_students or 0
            present_students = result.present_students or 0
            attendance_rate = (present_students / total_students * 100) if total_students > 0 else 0
            
            weekly_stats.append({
                'week_start': current_week_start.isoformat(),
                'week_end': week_end.isoformat(),
                'total_students': total_students,
                'present_students': present_students,
                'absent_students': total_students - present_students,
                'attendance_rate': round(attendance_rate, 2)
            })
            
            current_week_start = week_end + timedelta(days=1)
        
        # Monthly totals
        month_query = db.session.query(
            func.count(AttendanceRecord.id).label('total_students'),
            func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present_students'),
            func.count(distinct(func.date(Lecture.start_time))).label('total_days'),
            func.count(distinct(Lecture.id)).label('total_lectures')
        ).select_from(Lecture).outerjoin(
            AttendanceRecord, Lecture.id == AttendanceRecord.lecture_id
        ).filter(
            and_(
                func.date(Lecture.start_time) >= start_date,
                func.date(Lecture.start_time) <= end_date
            ),
            Lecture.is_active == True
        )
        
        # Apply filters
        if current_user.role == UserRole.TEACHER:
            month_query = month_query.filter(Lecture.teacher_id == current_user_id)
        elif teacher_id:
            month_query = month_query.filter(Lecture.teacher_id == teacher_id)
        
        if section:
            month_query = month_query.join(Student, AttendanceRecord.student_id == Student.user_id)
            month_query = month_query.filter(Student.section == Section[section.upper()])
        
        month_result = month_query.first()
        
        month_total_students = month_result.total_students or 0
        month_total_present = month_result.present_students or 0
        total_days = month_result.total_days or 0
        total_lectures = month_result.total_lectures or 0
        
        overall_monthly_rate = (month_total_present / month_total_students * 100) if month_total_students > 0 else 0
        
        return success_response(
            data={
                'period': {
                    'year': year,
                    'month': month,
                    'month_name': start_date.strftime('%B'),
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                },
                'summary': {
                    'total_days': total_days,
                    'total_lectures': total_lectures,
                    'total_students': month_total_students,
                    'total_present': month_total_present,
                    'total_absent': month_total_students - month_total_present,
                    'overall_attendance_rate': round(overall_monthly_rate, 2)
                },
                'weekly_breakdown': weekly_stats
            },
            message=f"Monthly attendance report for {start_date.strftime('%B %Y')}"
        )
        
    except Exception as e:
        return error_response(f"Error generating monthly report: {str(e)}", 500)

@reports_bp.route('/attendance/semester', methods=['GET'])
@jwt_required()
@admin_required
def semester_attendance_report():
    """Generate semester attendance report."""
    try:
        # Get parameters
        year = request.args.get('year', type=int, default=datetime.now().year)
        semester = request.args.get('semester', type=int, default=1)
        section = request.args.get('section')
        study_year = request.args.get('study_year', type=int)
        
        if semester not in [1, 2]:
            return error_response("Invalid semester. Use 1 or 2", 400)
        
        # Calculate semester boundaries
        if semester == 1:
            # First semester: September to January
            start_date = date(year, 9, 1)
            end_date = date(year + 1, 1, 31)
        else:
            # Second semester: February to June
            start_date = date(year, 2, 1)
            end_date = date(year, 6, 30)
        
        # Monthly breakdown for semester
        monthly_stats = []
        current_month = start_date.replace(day=1)
        
        while current_month <= end_date:
            # Calculate month end
            if current_month.month == 12:
                month_end = date(current_month.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(current_month.year, current_month.month + 1, 1) - timedelta(days=1)
            
            month_end = min(month_end, end_date)
            
            # Get month statistics
            month_query = db.session.query(
                func.count(AttendanceRecord.id).label('total_students'),
                func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present_students'),
                func.count(distinct(Lecture.id)).label('total_lectures')
            ).select_from(Lecture).outerjoin(
                AttendanceRecord, Lecture.id == AttendanceRecord.lecture_id
            ).filter(
                and_(
                    func.date(Lecture.start_time) >= current_month,
                    func.date(Lecture.start_time) <= month_end
                ),
                Lecture.is_active == True
            )
            
            # Apply filters
            if section:
                month_query = month_query.join(Student, AttendanceRecord.student_id == Student.user_id)
                month_query = month_query.filter(Student.section == Section[section.upper()])
            
            if study_year:
                if not section:  # Join Student if not already joined
                    month_query = month_query.join(Student, AttendanceRecord.student_id == Student.user_id)
                month_query = month_query.filter(Student.study_year == study_year)
            
            result = month_query.first()
            
            total_students = result.total_students or 0
            present_students = result.present_students or 0
            total_lectures = result.total_lectures or 0
            attendance_rate = (present_students / total_students * 100) if total_students > 0 else 0
            
            monthly_stats.append({
                'year': current_month.year,
                'month': current_month.month,
                'month_name': current_month.strftime('%B'),
                'total_lectures': total_lectures,
                'total_students': total_students,
                'present_students': present_students,
                'absent_students': total_students - present_students,
                'attendance_rate': round(attendance_rate, 2)
            })
            
            # Move to next month
            if current_month.month == 12:
                current_month = current_month.replace(year=current_month.year + 1, month=1)
            else:
                current_month = current_month.replace(month=current_month.month + 1)
        
        # Semester totals
        semester_query = db.session.query(
            func.count(AttendanceRecord.id).label('total_students'),
            func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present_students'),
            func.count(distinct(func.date(Lecture.start_time))).label('total_days'),
            func.count(distinct(Lecture.id)).label('total_lectures'),
            func.count(distinct(AttendanceRecord.student_id)).label('unique_students')
        ).select_from(Lecture).outerjoin(
            AttendanceRecord, Lecture.id == AttendanceRecord.lecture_id
        ).filter(
            and_(
                func.date(Lecture.start_time) >= start_date,
                func.date(Lecture.start_time) <= end_date
            ),
            Lecture.is_active == True
        )
        
        # Apply filters
        if section:
            semester_query = semester_query.join(Student, AttendanceRecord.student_id == Student.user_id)
            semester_query = semester_query.filter(Student.section == Section[section.upper()])
        
        if study_year:
            if not section:
                semester_query = semester_query.join(Student, AttendanceRecord.student_id == Student.user_id)
            semester_query = semester_query.filter(Student.study_year == study_year)
        
        semester_result = semester_query.first()
        
        semester_total_students = semester_result.total_students or 0
        semester_total_present = semester_result.present_students or 0
        total_days = semester_result.total_days or 0
        total_lectures = semester_result.total_lectures or 0
        unique_students = semester_result.unique_students or 0
        
        overall_semester_rate = (semester_total_present / semester_total_students * 100) if semester_total_students > 0 else 0
        
        return success_response(
            data={
                'period': {
                    'year': year,
                    'semester': semester,
                    'semester_name': f"Semester {semester}",
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                },
                'summary': {
                    'total_days': total_days,
                    'total_lectures': total_lectures,
                    'unique_students': unique_students,
                    'total_attendance_records': semester_total_students,
                    'total_present': semester_total_present,
                    'total_absent': semester_total_students - semester_total_present,
                    'overall_attendance_rate': round(overall_semester_rate, 2)
                },
                'monthly_breakdown': monthly_stats
            },
            message=f"Semester {semester} attendance report for {year}"
        )
        
    except Exception as e:
        return error_response(f"Error generating semester report: {str(e)}", 500)

# =================== SPECIFIC REPORTS ===================

@reports_bp.route('/attendance/student/<int:student_id>', methods=['GET'])
@jwt_required()
@teacher_required
def student_attendance_report(student_id):
    """Generate individual student attendance report."""
    try:
        # Get student
        student = Student.query.get_or_404(student_id)
        
        # Get parameters
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        
        # Build query
        query = db.session.query(
            AttendanceRecord,
            Lecture.title.label('lecture_title'),
            Lecture.start_time.label('lecture_start'),
            Lecture.room.label('room_name'),
            User.name.label('teacher_name')
        ).join(
            Lecture, AttendanceRecord.lecture_id == Lecture.id
        ).join(
            User, Lecture.teacher_id == User.id
        ).filter(
            AttendanceRecord.student_id == student_id
        )
        
        # Apply date filters
        if from_date:
            query = query.filter(Lecture.start_time >= datetime.fromisoformat(from_date))
        if to_date:
            query = query.filter(Lecture.start_time <= datetime.fromisoformat(to_date))
        
        # Order by date
        query = query.order_by(Lecture.start_time.desc())
        
        results = query.all()
        
        # Format results
        attendance_records = []
        total_lectures = len(results)
        present_count = 0
        absent_count = 0
        exceptional_count = 0
        
        for record, lecture_title, lecture_start, room_name, teacher_name in results:
            if record.is_present:
                present_count += 1
            else:
                absent_count += 1
            
            if record.is_exceptional:
                exceptional_count += 1
            
            attendance_records.append({
                'lecture_id': record.lecture_id,
                'lecture_title': lecture_title,
                'teacher_name': teacher_name,
                'room_name': room_name,
                'lecture_date': lecture_start.date().isoformat(),
                'lecture_time': lecture_start.time().isoformat(),
                'check_in_time': record.check_in_time.isoformat() if record.check_in_time else None,
                'is_present': record.is_present,
                'is_exceptional': record.is_exceptional,
                'verification_method': record.verification_method,
                'notes': record.notes
            })
        
        attendance_rate = (present_count / total_lectures * 100) if total_lectures > 0 else 0
        
        return success_response(
            data={
                'student_info': {
                    'id': student.id,
                    'university_id': student.university_id,
                    'full_name': student.full_name,
                    'section': student.section.value if student.section else None,
                    'study_year': student.study_year,
                    'study_type': student.study_type.value if student.study_type else None
                },
                'summary': {
                    'total_lectures': total_lectures,
                    'present_count': present_count,
                    'absent_count': absent_count,
                    'exceptional_count': exceptional_count,
                    'attendance_rate': round(attendance_rate, 2)
                },
                'attendance_records': attendance_records
            },
            message=f"Attendance report for student {student.full_name}"
        )
        
    except Exception as e:
        return error_response(f"Error generating student report: {str(e)}", 500)

@reports_bp.route('/attendance/lecture/<int:lecture_id>', methods=['GET'])
@jwt_required()
@teacher_required
def lecture_attendance_report(lecture_id):
    """Generate lecture attendance report."""
    try:
        # Get lecture
        lecture = Lecture.query.get_or_404(lecture_id)
        
        # Check if current user can access this lecture
        current_user_id = get_jwt_identity()
        current_user = User.query.get(current_user_id)
        
        if current_user.role == UserRole.TEACHER and lecture.teacher_id != current_user_id:
            return error_response("You can only view reports for your own lectures", 403)
        
        # Get attendance records
        attendance_query = db.session.query(
            AttendanceRecord,
            Student.university_id,
            Student.full_name,
            Student.section,
            Student.study_year
        ).outerjoin(
            AttendanceRecord, AttendanceRecord.lecture_id == lecture_id
        ).join(
            Student, Student.user_id == AttendanceRecord.student_id
        ).order_by(Student.full_name)
        
        # Also get all students who should be in this lecture (from schedules)
        # This is a simplified version - in a real system you'd have proper enrollment
        
        results = attendance_query.all()
        
        # Format results
        attendance_list = []
        present_count = 0
        absent_count = 0
        exceptional_count = 0
        
        for record, university_id, full_name, section, study_year in results:
            if record and record.is_present:
                status = "present"
                present_count += 1
            elif record and not record.is_present:
                status = "absent"
                absent_count += 1
            else:
                status = "no_record"
                absent_count += 1
            
            if record and record.is_exceptional:
                exceptional_count += 1
            
            attendance_list.append({
                'student_id': record.student_id if record else None,
                'university_id': university_id,
                'full_name': full_name,
                'section': section.value if section else None,
                'study_year': study_year,
                'status': status,
                'check_in_time': record.check_in_time.isoformat() if record and record.check_in_time else None,
                'verification_method': record.verification_method if record else None,
                'is_exceptional': record.is_exceptional if record else False,
                'notes': record.notes if record else None
            })
        
        total_students = len(attendance_list)
        attendance_rate = (present_count / total_students * 100) if total_students > 0 else 0
        
        return success_response(
            data={
                'lecture_info': {
                    'id': lecture.id,
                    'title': lecture.title,
                    'teacher_name': lecture.teacher.name,
                    'room': lecture.room,
                    'start_time': lecture.start_time.isoformat(),
                    'end_time': lecture.end_time.isoformat()
                },
                'summary': {
                    'total_students': total_students,
                    'present_count': present_count,
                    'absent_count': absent_count,
                    'exceptional_count': exceptional_count,
                    'attendance_rate': round(attendance_rate, 2)
                },
                'attendance_list': attendance_list
            },
            message=f"Attendance report for lecture: {lecture.title}"
        )
        
    except Exception as e:
        return error_response(f"Error generating lecture report: {str(e)}", 500)

@reports_bp.route('/attendance/room/<int:room_id>', methods=['GET'])
@jwt_required()
@admin_required
def room_attendance_report(room_id):
    """Generate room utilization and attendance report."""
    try:
        # Get room
        room = Room.query.get_or_404(room_id)
        
        # Get parameters
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        
        # Build query for lectures in this room
        query = db.session.query(
            Lecture.id.label('lecture_id'),
            Lecture.title.label('lecture_title'),
            Lecture.start_time,
            Lecture.end_time,
            User.name.label('teacher_name'),
            func.count(AttendanceRecord.id).label('total_students'),
            func.sum(db.case([(AttendanceRecord.is_present == True, 1)], else_=0)).label('present_students')
        ).select_from(Lecture).join(
            User, Lecture.teacher_id == User.id
        ).outerjoin(
            AttendanceRecord, Lecture.id == AttendanceRecord.lecture_id
        ).filter(
            Lecture.room_id == room_id,
            Lecture.is_active == True
        )
        
        # Apply date filters
        if from_date:
            query = query.filter(Lecture.start_time >= datetime.fromisoformat(from_date))
        if to_date:
            query = query.filter(Lecture.start_time <= datetime.fromisoformat(to_date))
        
        # Group by lecture
        query = query.group_by(
            Lecture.id, Lecture.title, Lecture.start_time, Lecture.end_time, User.name
        ).order_by(Lecture.start_time.desc())
        
        results = query.all()
        
        # Format results
        lectures_data = []
        total_lectures = len(results)
        total_hours_used = 0
        total_students_overall = 0
        total_present_overall = 0
        
        for result in results:
            duration_hours = (result.end_time - result.start_time).total_seconds() / 3600
            total_hours_used += duration_hours
            
            total_students = result.total_students or 0
            present_students = result.present_students or 0
            attendance_rate = (present_students / total_students * 100) if total_students > 0 else 0
            
            lectures_data.append({
                'lecture_id': result.lecture_id,
                'lecture_title': result.lecture_title,
                'teacher_name': result.teacher_name,
                'start_time': result.start_time.isoformat(),
                'end_time': result.end_time.isoformat(),
                'duration_hours': round(duration_hours, 2),
                'total_students': total_students,
                'present_students': present_students,
                'attendance_rate': round(attendance_rate, 2)
            })
            
            total_students_overall += total_students
            total_present_overall += present_students
        
        overall_attendance_rate = (total_present_overall / total_students_overall * 100) if total_students_overall > 0 else 0
        
        # Calculate utilization rate (assuming 8 hours per day availability)
        period_days = 30  # Default to 30 days if no date filters
        if from_date and to_date:
            from_dt = datetime.fromisoformat(from_date)
            to_dt = datetime.fromisoformat(to_date)
            period_days = (to_dt - from_dt).days + 1
        
        available_hours = period_days * 8  # 8 hours per day
        utilization_rate = (total_hours_used / available_hours * 100) if available_hours > 0 else 0
        
        return success_response(
            data={
                'room_info': {
                    'id': room.id,
                    'name': room.name,
                    'building': room.building,
                    'floor': room.floor,
                    'capacity': room.capacity
                },
                'summary': {
                    'total_lectures': total_lectures,
                    'total_hours_used': round(total_hours_used, 2),
                    'utilization_rate': round(utilization_rate, 2),
                    'total_students': total_students_overall,
                    'total_present': total_present_overall,
                    'overall_attendance_rate': round(overall_attendance_rate, 2)
                },
                'lectures': lectures_data
            },
            message=f"Room utilization report for {room.name}"
        )
        
    except Exception as e:
        return error_response(f"Error generating room report: {str(e)}", 500)

# =================== EXPORT FUNCTIONS ===================

@reports_bp.route('/export/pdf', methods=['POST'])
@jwt_required()
@admin_required
def export_report_pdf():
    """Export report as PDF."""
    try:
        data = request.get_json()
        report_type = data.get('report_type')
        report_data = data.get('report_data')
        
        if not report_type or not report_data:
            return error_response("Missing report_type or report_data", 400)
        
        # Generate PDF (this is a simplified example)
        # In production, you'd use libraries like reportlab or weasyprint
        
        pdf_content = generate_pdf_report(report_type, report_data)
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(pdf_content)
            tmp_file_path = tmp_file.name
        
        try:
            return send_file(
                tmp_file_path,
                as_attachment=True,
                download_name=f"{report_type}_report_{datetime.now().strftime('%Y%m%d')}.pdf",
                mimetype='application/pdf'
            )
        finally:
            os.unlink(tmp_file_path)
        
    except Exception as e:
        return error_response(f"Error exporting PDF: {str(e)}", 500)

@reports_bp.route('/export/excel', methods=['POST'])
@jwt_required()
@admin_required
def export_report_excel():
    """Export report as Excel."""
    try:
        data = request.get_json()
        report_type = data.get('report_type')
        report_data = data.get('report_data')
        
        if not report_type or not report_data:
            return error_response("Missing report_type or report_data", 400)
        
        # Create Excel file
        excel_buffer = io.BytesIO()
        
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            # Summary sheet
            if 'summary' in report_data:
                summary_df = pd.DataFrame([report_data['summary']])
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Main data sheet
            if 'lectures' in report_data:
                lectures_df = pd.DataFrame(report_data['lectures'])
                lectures_df.to_excel(writer, sheet_name='Lectures', index=False)
            
            if 'attendance_records' in report_data:
                attendance_df = pd.DataFrame(report_data['attendance_records'])
                attendance_df.to_excel(writer, sheet_name='Attendance', index=False)
            
            if 'attendance_list' in report_data:
                list_df = pd.DataFrame(report_data['attendance_list'])
                list_df.to_excel(writer, sheet_name='Student List', index=False)
        
        excel_buffer.seek(0)
        
        return send_file(
            io.BytesIO(excel_buffer.read()),
            as_attachment=True,
            download_name=f"{report_type}_report_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        return error_response(f"Error exporting Excel: {str(e)}", 500)

# =================== HELPER FUNCTIONS ===================

def generate_pdf_report(report_type: str, report_data: Dict) -> bytes:
    """Generate PDF report content."""
    # This is a placeholder - implement actual PDF generation
    # You would use libraries like reportlab or weasyprint
    
    content = f"""
    PDF Report: {report_type}
    Generated: {datetime.now().isoformat()}
    
    Summary: {json.dumps(report_data.get('summary', {}), indent=2)}
    
    Data: {json.dumps(report_data, indent=2, default=str)}
    """
    
    return content.encode('utf-8')