# backend/app/models/lecture.py - Updated
"""Lecture model with location support."""
from datetime import datetime
from app import db
from app.models.base import BaseModel

class Lecture(BaseModel):
    """Lecture model."""
    
    __tablename__ = 'lectures'
    
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    room = db.Column(db.String(50), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    # Location fields for GPS verification
    latitude = db.Column(db.Float, nullable=True, default=33.3152)
    longitude = db.Column(db.Float, nullable=True, default=44.3661)
    
    # Relationships
    attendance_records = db.relationship('AttendanceRecord', backref='lecture', lazy='dynamic')
    
    def to_dict(self):
        """Convert to dictionary."""
        data = super().to_dict()
        data['location'] = {
            'latitude': self.latitude,
            'longitude': self.longitude
        }
        return data
    
    def __repr__(self):
        return f'<Lecture {self.title}>'

# ===================================