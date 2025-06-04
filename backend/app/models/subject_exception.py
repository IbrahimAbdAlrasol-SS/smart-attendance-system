
# File: backend/app/models/subject_exception.py
"""Subject exceptions for students with failed subjects."""
from app import db
from app.models.base import BaseModel

class SubjectException(BaseModel):
    """Exceptions for students attending specific subjects only."""
    
    __tablename__ = 'subject_exceptions'
    
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedules.id'), nullable=False)
    reason = db.Column(db.String(255), nullable=True)  # "Failed in previous year"
    is_active = db.Column(db.Boolean, default=True)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Relationships
    schedule = db.relationship('Schedule', backref='exceptions')
    approver = db.relationship('User')
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'student_id': self.student_id,
            'schedule': self.schedule.to_dict() if self.schedule else None,
            'reason': self.reason,
            'is_active': self.is_active,
            'approved_by': self.approver.name if self.approver else None
        }
        