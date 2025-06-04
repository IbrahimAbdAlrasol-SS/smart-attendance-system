# File: backend/app/models/student.py
"""Enhanced Student model with university ID and secret code."""
from app import db
from app.models.base import BaseModel
from app.models.user import User, UserRole, Section
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.dialects.postgresql import JSON
import secrets
import string
import enum

class StudyType(enum.Enum):
    """Study types enumeration."""
    MORNING = 'morning'      # صباحي
    EVENING = 'evening'      # مسائي
    HOSTED = 'hosted'        # استضافة

class StudentStatus(enum.Enum):
    """Student status enumeration."""
    ACTIVE = 'active'        # نشط
    SUSPENDED = 'suspended'  # موقوف
    GRADUATED = 'graduated'  # متخرج
    DROPPED = 'dropped'      # منسحب

class Student(BaseModel):
    """Student model with detailed information."""
    
    __tablename__ = 'students'
    
    # Link to User
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    
    # University Credentials
    university_id = db.Column(db.String(20), unique=True, nullable=False, index=True)  # CS2021001
    secret_code = db.Column(db.String(255), nullable=False)  # Hashed secret code
    
    # Personal Info
    full_name = db.Column(db.String(255), nullable=False)  # الاسم الكامل
    
    # Academic Info
    section = db.Column(db.Enum(Section), nullable=False)  # A, B, C
    study_year = db.Column(db.Integer, nullable=False)  # 1-4
    is_repeater = db.Column(db.Boolean, default=False)  # سنة تحميل
    study_type = db.Column(db.Enum(StudyType), nullable=False, default=StudyType.MORNING)
    department = db.Column(db.String(100), nullable=True)  # القسم
    
    # Exceptions and Notes
    failed_subjects = db.Column(JSON, default=list)  # ["Math101", "CS201"]
    exceptions_notes = db.Column(db.Text, nullable=True)  # ملاحظات خاصة
    
    # Status
    status = db.Column(db.Enum(StudentStatus), default=StudentStatus.ACTIVE)
    enrollment_date = db.Column(db.Date, nullable=True)
    
    # Face Recognition
    face_registered = db.Column(db.Boolean, default=False)
    face_registered_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('student_profile', uselist=False))
    subject_exceptions = db.relationship('SubjectException', backref='student', lazy='dynamic')
    
    @staticmethod
    def generate_university_id(year: int, department: str, sequence: int) -> str:
        """Generate unique university ID."""
        dept_code = department[:2].upper()
        return f"{dept_code}{year}{sequence:04d}"
    
    @staticmethod
    def generate_secret_code(length: int = 8) -> str:
        """Generate secure secret code."""
        characters = string.ascii_uppercase + string.digits
        # Avoid confusing characters
        characters = characters.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
        return ''.join(secrets.choice(characters) for _ in range(length))
    
    def set_secret_code(self, code: str) -> None:
        """Set hashed secret code."""
        self.secret_code = generate_password_hash(code)
    
    def verify_secret_code(self, code: str) -> bool:
        """Verify secret code."""
        return check_password_hash(self.secret_code, code)
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'university_id': self.university_id,
            'full_name': self.full_name,
            'section': self.section.value if self.section else None,
            'study_year': self.study_year,
            'is_repeater': self.is_repeater,
            'study_type': self.study_type.value if self.study_type else None,
            'department': self.department,
            'status': self.status.value if self.status else None,
            'failed_subjects': self.failed_subjects,
            'face_registered': self.face_registered,
            'created_at': self.created_at.isoformat()
        }

