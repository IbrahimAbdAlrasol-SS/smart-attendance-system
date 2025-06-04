# File: backend/app/api/students.py
"""Student Management API - Admin Only."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db, limiter
from app.models.user import User, UserRole
from app.models.student import Student, StudyType, StudentStatus, Section
from app.utils.helpers import success_response, error_response
from app.utils.decorators import admin_required, teacher_required
from app.services.student_service import StudentService
import pandas as pd
import io

students_bp = Blueprint('students', __name__)

@students_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return success_response(message='Students service is running')

@students_bp.route('/', methods=['GET'])
@jwt_required()
@admin_required
def get_students():
    """Get all students with filters."""
    try:
        # Get query parameters
        section = request.args.get('section')
        study_year = request.args.get('study_year', type=int)
        study_type = request.args.get('study_type')
        status = request.args.get('status')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Build query
        query = Student.query
        
        if section:
            query = query.filter_by(section=Section[section.upper()])
        if study_year:
            query = query.filter_by(study_year=study_year)
        if study_type:
            query = query.filter_by(study_type=StudyType[study_type.upper()])
        if status:
            query = query.filter_by(status=StudentStatus[status.upper()])
        
        # Paginate
        pagination = query.paginate(page=page, per_page=per_page)
        
        students = [student.to_dict() for student in pagination.items]
        
        return success_response(
            data={
                'students': students,
                'total': pagination.total,
                'pages': pagination.pages,
                'current_page': page
            }
        )
        
    except Exception as e:
        return error_response(f"Error fetching students: {str(e)}", 500)

@students_bp.route('/<int:student_id>', methods=['GET'])
@jwt_required()
@teacher_required
def get_student(student_id):
    """Get single student details."""
    try:
        student = Student.query.get_or_404(student_id)
        return success_response(data=student.to_dict())
        
    except Exception as e:
        return error_response(f"Error fetching student: {str(e)}", 500)

@students_bp.route('/', methods=['POST'])
@jwt_required()
@admin_required
def create_student():
    """Create single student."""
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['full_name', 'section', 'study_year', 'study_type']
        for field in required:
            if field not in data:
                return error_response(f"Missing required field: {field}", 400)
        
        # Create student
        result, error = StudentService.create_student(
            full_name=data['full_name'],
            section=data['section'],
            study_year=data['study_year'],
            study_type=data['study_type'],
            department=data.get('department', 'CS'),
            is_repeater=data.get('is_repeater', False),
            failed_subjects=data.get('failed_subjects', []),
            exceptions_notes=data.get('exceptions_notes')
        )
        
        if error:
            return error_response(error, 400)
        
        return success_response(
            data=result,
            message="Student created successfully"
        ), 201
        
    except Exception as e:
        return error_response(f"Error creating student: {str(e)}", 500)

@students_bp.route('/bulk', methods=['POST'])
@jwt_required()
@admin_required
@limiter.limit("5 per hour")
def create_students_bulk():
    """Create multiple students from CSV/Excel file."""
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
        required_columns = ['full_name', 'section', 'study_year', 'study_type']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return error_response(f"Missing columns: {', '.join(missing_columns)}", 400)
        
        # Process students
        results = StudentService.create_students_bulk(df)
        
        return success_response(
            data={
                'total': len(results),
                'successful': len([r for r in results if r['success']]),
                'failed': len([r for r in results if not r['success']]),
                'results': results
            },
            message="Bulk import completed"
        )
        
    except Exception as e:
        return error_response(f"Error in bulk import: {str(e)}", 500)

@students_bp.route('/<int:student_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_student(student_id):
    """Update student information."""
    try:
        student = Student.query.get_or_404(student_id)
        data = request.get_json()
        
        # Update allowed fields
        updatable_fields = [
            'full_name', 'section', 'study_year', 'study_type',
            'is_repeater', 'failed_subjects', 'exceptions_notes',
            'status', 'department'
        ]
        
        for field in updatable_fields:
            if field in data:
                if field in ['section', 'study_type', 'status']:
                    # Handle enums
                    enum_class = {
                        'section': Section,
                        'study_type': StudyType,
                        'status': StudentStatus
                    }[field]
                    setattr(student, field, enum_class[data[field].upper()])
                else:
                    setattr(student, field, data[field])
        
        student.save()
        
        return success_response(
            data=student.to_dict(),
            message="Student updated successfully"
        )
        
    except Exception as e:
        return error_response(f"Error updating student: {str(e)}", 500)

@students_bp.route('/<int:student_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_student(student_id):
    """Delete student (soft delete by changing status)."""
    try:
        student = Student.query.get_or_404(student_id)
        
        # Soft delete - just change status
        student.status = StudentStatus.DROPPED
        student.user.is_active = False
        student.save()
        
        return success_response(message="Student deleted successfully")
        
    except Exception as e:
        return error_response(f"Error deleting student: {str(e)}", 500)

@students_bp.route('/<int:student_id>/reset-code', methods=['POST'])
@jwt_required()
@admin_required
def reset_student_code(student_id):
    """Reset student's secret code."""
    try:
        student = Student.query.get_or_404(student_id)
        
        # Generate new code
        new_code = Student.generate_secret_code()
        student.set_secret_code(new_code)
        student.save()
        
        return success_response(
            data={
                'university_id': student.university_id,
                'new_code': new_code  # Only time we return plain code
            },
            message="Secret code reset successfully"
        )
        
    except Exception as e:
        return error_response(f"Error resetting code: {str(e)}", 500)

@students_bp.route('/export', methods=['GET'])
@jwt_required()
@admin_required
def export_students():
    """Export students list as CSV."""
    try:
        # Get filters
        section = request.args.get('section')
        study_year = request.args.get('study_year', type=int)
        
        # Build query
        query = Student.query
        if section:
            query = query.filter_by(section=Section[section.upper()])
        if study_year:
            query = query.filter_by(study_year=study_year)
        
        students = query.all()
        
        # Create DataFrame
        data = []
        for student in students:
            data.append({
                'university_id': student.university_id,
                'full_name': student.full_name,
                'section': student.section.value if student.section else '',
                'study_year': student.study_year,
                'study_type': student.study_type.value if student.study_type else '',
                'is_repeater': 'نعم' if student.is_repeater else 'لا',
                'status': student.status.value if student.status else '',
                'created_at': student.created_at.strftime('%Y-%m-%d')
            })
        
        df = pd.DataFrame(data)
        
        # Convert to CSV
        output = io.StringIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')
        output.seek(0)
        
        return output.getvalue(), 200, {
            'Content-Type': 'text/csv; charset=utf-8',
            'Content-Disposition': 'attachment; filename=students_export.csv'
        }
        
    except Exception as e:
        return error_response(f"Error exporting students: {str(e)}", 500)

@students_bp.route('/template', methods=['GET'])
@jwt_required()
@admin_required
def get_import_template():
    """Get CSV template for bulk import."""
    try:
        # Create template
        template_data = {
            'full_name': ['أحمد محمد علي', 'فاطمة حسن أحمد'],
            'section': ['A', 'B'],
            'study_year': [1, 2],
            'study_type': ['morning', 'evening'],
            'department': ['CS', 'CS'],
            'is_repeater': [False, False],
            'failed_subjects': ['', 'Math101,CS201'],
            'exceptions_notes': ['', 'محمل بمادتين']
        }
        
        df = pd.DataFrame(template_data)
        
        # Convert to CSV
        output = io.StringIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')
        output.seek(0)
        
        return output.getvalue(), 200, {
            'Content-Type': 'text/csv; charset=utf-8',
            'Content-Disposition': 'attachment; filename=students_import_template.csv'
        }
        
    except Exception as e:
        return error_response(f"Error generating template: {str(e)}", 500)
