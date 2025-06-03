"""Lecture model."""
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
    
    def __repr__(self):
        return f'<Lecture {self.title}>'