"""Assignment model."""
from datetime import datetime
from app import db
from app.models.base import BaseModel

class Assignment(BaseModel):
    """Assignment model."""
    
    __tablename__ = 'assignments'
    
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    due_date = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<Assignment {self.title}>'