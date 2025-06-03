# إصلاح imports في models

"""Models package - Fixed imports."""
from .base import BaseModel
from .user import User, UserRole, Section
from .lecture import Lecture
from .attendance import AttendanceRecord
from .assignment import Assignment

__all__ = [
    'BaseModel', 'User', 'UserRole', 'Section', 
    'Lecture', 'AttendanceRecord', 'Assignment'
]
