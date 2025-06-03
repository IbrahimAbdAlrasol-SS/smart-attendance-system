"""User model for authentication and authorization."""
from enum import Enum
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models.base import BaseModel

class UserRole(Enum):
    """User roles enumeration."""
    STUDENT = 'student'
    TEACHER = 'teacher'
    COORDINATOR = 'coordinator'
    ADMIN = 'admin'

class Section(Enum):
    """Class sections enumeration."""
    A = 'A'
    B = 'B'

class User(BaseModel):
    """User model for all system users."""
    
    __tablename__ = 'users'
    
    # Basic Information
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    student_id = db.Column(db.String(50), unique=True, nullable=True, index=True)
    
    # Role and Section
    role = db.Column(db.Enum(UserRole), nullable=False, default=UserRole.STUDENT)
    section = db.Column(db.Enum(Section), nullable=True)
    
    # Security and Authentication
    face_encoding = db.Column(db.Text, nullable=True)  # Encrypted face data
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    
    # Contact Information
    phone = db.Column(db.String(20), nullable=True)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=True, index=True)
    
    # Relationships
    lectures = db.relationship('Lecture', backref='teacher', lazy='dynamic')
    attendance_records = db.relationship('AttendanceRecord', backref='student', lazy='dynamic')
    
    def set_password(self, password: str) -> None:
        """Set user password with hashing."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password: str) -> bool:
        """Check if provided password matches user's password."""
        return check_password_hash(self.password_hash, password)
    
    def is_teacher(self) -> bool:
        """Check if user is a teacher."""
        return self.role in [UserRole.TEACHER, UserRole.COORDINATOR, UserRole.ADMIN]
    
    def is_student(self) -> bool:
        """Check if user is a student."""
        return self.role == UserRole.STUDENT
    
    def can_manage_section(self, section: Section) -> bool:
        """Check if user can manage specific section."""
        if self.role == UserRole.ADMIN:
            return True
        if self.role == UserRole.COORDINATOR:
            return True
        if self.role == UserRole.TEACHER:
            return self.section == section
        return False
    
    def to_dict(self, exclude: list = None) -> dict:
        """Convert to dictionary excluding sensitive data."""
        default_exclude = ['password_hash', 'face_encoding', 'failed_login_attempts']
        exclude = (exclude or []) + default_exclude
        
        result = super().to_dict(exclude=exclude)
        result['role'] = self.role.value if self.role else None
        result['section'] = self.section.value if self.section else None
        
        return result
    
    def __repr__(self) -> str:
        return f'<User {self.email}>'
