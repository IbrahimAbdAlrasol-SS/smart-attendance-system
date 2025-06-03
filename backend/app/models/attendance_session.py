
# backend/app/models/attendance_session.py
"""Attendance session with QR codes."""
from app import db
from app.models.base import BaseModel
from datetime import datetime, timedelta
import secrets

class AttendanceSession(BaseModel):
    """Session for tracking attendance with QR codes."""
    
    __tablename__ = 'attendance_sessions'
    
    lecture_id = db.Column(db.Integer, db.ForeignKey('lectures.id'), nullable=False)
    qr_code = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    # Stats
    total_present = db.Column(db.Integer, default=0)
    total_absent = db.Column(db.Integer, default=0)
    
    # Relationships
    lecture = db.relationship('Lecture', backref='attendance_sessions')
    records = db.relationship('AttendanceRecord', backref='session', lazy='dynamic')
    
    @staticmethod
    def generate_qr_code() -> str:
        """Generate unique QR code."""
        return secrets.token_urlsafe(32)
    
    def is_expired(self) -> bool:
        """Check if session is expired."""
        return datetime.utcnow() > self.expires_at
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'lecture_id': self.lecture_id,
            'qr_code': self.qr_code,
            'expires_at': self.expires_at.isoformat(),
            'is_active': self.is_active and not self.is_expired(),
            'total_present': self.total_present,
            'total_absent': self.total_absent
        }