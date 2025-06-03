"""Base model class with common functionality."""
from datetime import datetime
from typing import Dict, Any
from app import db

class BaseModel(db.Model):
    """Base model class with common fields and methods."""
    
    __abstract__ = True
    
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def save(self) -> 'BaseModel':
        """Save instance to database."""
        db.session.add(self)
        db.session.commit()
        return self
    
    def delete(self) -> None:
        """Delete instance from database."""
        db.session.delete(self)
        db.session.commit()
    
    def update(self, **kwargs) -> 'BaseModel':
        """Update instance with provided data."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        
        self.updated_at = datetime.utcnow()
        db.session.commit()
        return self
    
    def to_dict(self, exclude: list = None) -> Dict[str, Any]:
        """Convert instance to dictionary."""
        exclude = exclude or []
        result = {}
        
        for column in self.__table__.columns:
            key = column.name
            if key not in exclude:
                value = getattr(self, key)
                if isinstance(value, datetime):
                    value = value.isoformat()
                result[key] = value
        
        return result
    
    @classmethod
    def get_by_id(cls, id: int) -> 'BaseModel':
        """Get instance by ID."""
        return cls.query.get(id)
    
    @classmethod
    def get_or_404(cls, id: int) -> 'BaseModel':
        """Get instance by ID or raise 404."""
        return cls.query.get_or_404(id)
    
    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} {self.id}>'
