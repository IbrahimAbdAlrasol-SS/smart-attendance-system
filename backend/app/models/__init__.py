# Update backend/app/models/__init__.py
"""Models package with all models."""
from .base import BaseModel
from .user import User, UserRole, Section
from .lecture import Lecture
from .attendance import AttendanceRecord
from .assignment import Assignment
from .room import Room
from .student import Student, StudyType, StudentStatus
from .schedule import Schedule, WeekDay
from .subject_exception import SubjectException
from .attendance_session import AttendanceSession

__all__ = [
    'BaseModel', 'User', 'UserRole', 'Section',
    'Lecture', 'AttendanceRecord', 'Assignment',
    'Room', 'Student', 'StudyType', 'StudentStatus',
    'Schedule', 'WeekDay', 'SubjectException',
    'AttendanceSession'
]
