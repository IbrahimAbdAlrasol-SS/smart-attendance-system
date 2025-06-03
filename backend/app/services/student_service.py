

# backend/app/services/student_service.py
"""Student management service."""
from typing import Dict, List, Tuple, Optional
from app import db
from app.models.user import User, UserRole
from app.models.student import Student, StudyType, Section
import pandas as pd
from datetime import datetime

class StudentService:
    """Service for managing students."""
    
    @staticmethod
    def create_student(
        full_name: str,
        section: str,
        study_year: int,
        study_type: str,
        department: str = 'CS',
        is_repeater: bool = False,
        failed_subjects: List[str] = None,
        exceptions_notes: str = None
    ) -> Tuple[Dict, Optional[str]]:
        """Create a new student with auto-generated credentials."""
        try:
            # Validate inputs
            if study_year < 1 or study_year > 6:
                return None, "Invalid study year"
            
            # Get next sequence number for university ID
            current_year = datetime.now().year
            last_student = Student.query.filter(
                Student.university_id.like(f"{department[:2].upper()}{current_year}%")
            ).order_by(Student.university_id.desc()).first()
            
            if last_student:
                last_sequence = int(last_student.university_id[-4:])
                sequence = last_sequence + 1
            else:
                sequence = 1
            
            # Generate credentials
            university_id = Student.generate_university_id(current_year, department, sequence)
            secret_code = Student.generate_secret_code()
            
            # Create user account
            user = User(
                email=f"{university_id.lower()}@university.edu",
                name=full_name,
                role=UserRole.STUDENT
            )
            user.set_password(secret_code)  # Initial password is the secret code
            db.session.add(user)
            db.session.flush()  # Get user.id
            
            # Create student profile
            student = Student(
                user_id=user.id,
                university_id=university_id,
                full_name=full_name,
                section=Section[section.upper()],
                study_year=study_year,
                study_type=StudyType[study_type.upper()],
                department=department,
                is_repeater=is_repeater,
                failed_subjects=failed_subjects or [],
                exceptions_notes=exceptions_notes
            )
            student.set_secret_code(secret_code)
            
            db.session.add(student)
            db.session.commit()
            
            return {
                'student': student.to_dict(),
                'credentials': {
                    'university_id': university_id,
                    'secret_code': secret_code,
                    'email': user.email
                }
            }, None
            
        except Exception as e:
            db.session.rollback()
            return None, f"Error creating student: {str(e)}"
    
    @staticmethod
    def create_students_bulk(df: pd.DataFrame) -> List[Dict]:
        """Create multiple students from DataFrame."""
        results = []
        
        for index, row in df.iterrows():
            try:
                result, error = StudentService.create_student(
                    full_name=row['full_name'],
                    section=row['section'],
                    study_year=int(row['study_year']),
                    study_type=row['study_type'],
                    department=row.get('department', 'CS'),
                    is_repeater=bool(row.get('is_repeater', False)),
                    failed_subjects=row.get('failed_subjects', '').split(',') if row.get('failed_subjects') else [],
                    exceptions_notes=row.get('exceptions_notes')
                )
                
                if error:
                    results.append({
                        'row': index + 2,  # Excel row number
                        'name': row['full_name'],
                        'success': False,
                        'error': error
                    })
                else:
                    results.append({
                        'row': index + 2,
                        'name': row['full_name'],
                        'success': True,
                        'university_id': result['credentials']['university_id'],
                        'secret_code': result['credentials']['secret_code']
                    })
                    
            except Exception as e:
                results.append({
                    'row': index + 2,
                    'name': row.get('full_name', 'Unknown'),
                    'success': False,
                    'error': str(e)
                })
        
        return results