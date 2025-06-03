"""Room model with GPS boundaries and altitude."""
from app import db
from app.models.base import BaseModel
from sqlalchemy.dialects.postgresql import JSON

class Room(BaseModel):
    """Room/Classroom model with location data."""
    
    __tablename__ = 'rooms'
    
    # Basic Info
    name = db.Column(db.String(50), nullable=False, unique=True)  # مثل A101
    building = db.Column(db.String(100), nullable=False)  # اسم المبنى
    floor = db.Column(db.Integer, nullable=False)  # رقم الطابق
    
    # Location Data
    altitude = db.Column(db.Float, nullable=False)  # الارتفاع عن مستوى الارض بالمتر
    
    # GPS Boundaries (4 corners of the room)
    gps_boundaries = db.Column(JSON, nullable=False)  # [{lat, lng}, {lat, lng}, {lat, lng}, {lat, lng}]
    
    # Additional GPS data
    center_latitude = db.Column(db.Float, nullable=False)
    center_longitude = db.Column(db.Float, nullable=False)
    radius_meters = db.Column(db.Float, default=5.0)  # نطاق التحقق بالمتر
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    capacity = db.Column(db.Integer, default=30)
    
    # Relationships
    schedules = db.relationship('Schedule', backref='room', lazy='dynamic')
    
    def to_dict(self):
        """Convert to dictionary."""
        result = super().to_dict()
        result['gps_boundaries'] = self.gps_boundaries
        return result
    
    def is_location_inside(self, latitude: float, longitude: float) -> bool:
        """Check if a GPS location is inside the room boundaries."""
        # Implementation for point-in-polygon check
        # This is a simplified version - in production use proper geometry libraries
        return True  # Placeholder
