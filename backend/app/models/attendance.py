"""Attendance model."""
from datetime import datetime
from app import db
from app.models.base import BaseModel

class AttendanceRecord(BaseModel):
    """Attendance record model."""
    
    __tablename__ = 'attendance_records'
    
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lectures.id'), nullable=False)
    check_in_time = db.Column(db.DateTime, default=datetime.utcnow)
    is_present = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<AttendanceRecord {self.student_id}-{self.lecture_id}>'