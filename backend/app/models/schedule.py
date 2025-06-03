
# backend/app/models/schedule.py
"""Schedule model for class timetables."""
from app import db
from app.models.base import BaseModel
from datetime import time
from app.models.user import Section
from app.models.student import StudyType
import enum
class WeekDay(enum.Enum):
    """Days of the week."""
    SUNDAY = 0
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6

class Schedule(BaseModel):
    """Schedule for classes."""
    
    __tablename__ = 'schedules'
    
    # Basic Info
    subject_name = db.Column(db.String(255), nullable=False)
    subject_code = db.Column(db.String(50), nullable=True)
    
    # Relations
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)
    
    # Academic Info
    section = db.Column(db.Enum(Section), nullable=False)
    study_year = db.Column(db.Integer, nullable=False)
    study_type = db.Column(db.Enum(StudyType), nullable=False)
    
    # Time Info
    day_of_week = db.Column(db.Enum(WeekDay), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    semester = db.Column(db.Integer, default=1)  # 1 or 2
    academic_year = db.Column(db.String(20), nullable=True)  # "2024-2025"
    
    # Relationships
    teacher = db.relationship('User', backref='teaching_schedules')
    lectures = db.relationship('Lecture', backref='schedule', lazy='dynamic')
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'subject_name': self.subject_name,
            'subject_code': self.subject_code,
            'teacher': self.teacher.name,
            'room': self.room.name,
            'section': self.section.value if self.section else None,
            'study_year': self.study_year,
            'study_type': self.study_type.value if self.study_type else None,
            'day': self.day_of_week.name if self.day_of_week else None,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'is_active': self.is_active
        }

