
# backend/app/models/attendance.py - Updated
"""Attendance model with verification details."""
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
    
    # Verification details
    verification_method = db.Column(db.String(20), default='qr')  # qr, manual, emergency
    notes = db.Column(db.Text, nullable=True)
    
    # Location where check-in happened
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    
    # For emergency check-ins that need approval
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f'<AttendanceRecord {self.student_id}-{self.lecture_id}>'