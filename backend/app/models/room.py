# 1. UPDATE MODELS - Enhanced with 3D rooms and student credentials
# File: backend/app/models/room.py
"""Room model with 3D GPS boundaries and altitude."""
from app import db
from app.models.base import BaseModel
from sqlalchemy.dialects.postgresql import JSON

class Room(BaseModel):
    """Room/Classroom model with 3D location data."""
    
    __tablename__ = 'rooms'
    
    # Basic Info
    name = db.Column(db.String(50), nullable=False, unique=True)  # مثل A101
    building = db.Column(db.String(100), nullable=False)  # اسم المبنى
    floor = db.Column(db.Integer, nullable=False)  # رقم الطابق
    
    # 3D Location Data
    altitude = db.Column(db.Float, nullable=False)  # الارتفاع عن مستوى البحر بالمتر
    floor_altitude = db.Column(db.Float, nullable=False)  # ارتفاع أرضية القاعة عن الأرض
    ceiling_height = db.Column(db.Float, nullable=False)  # ارتفاع السقف من الأرضية
    
    # GPS Boundaries (polygon points)
    gps_boundaries = db.Column(JSON, nullable=False)  # [{lat, lng}, {lat, lng}, ...]
    
    # Pressure Reference
    reference_pressure = db.Column(db.Float, nullable=True)  # ضغط مرجعي للبارومتر
    
    # Additional GPS data
    center_latitude = db.Column(db.Float, nullable=False)
    center_longitude = db.Column(db.Float, nullable=False)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    capacity = db.Column(db.Integer, default=30)
    
    # Relationships
    schedules = db.relationship('Schedule', backref='room', lazy='dynamic')
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'building': self.building,
            'floor': self.floor,
            'altitude': self.altitude,
            'floor_altitude': self.floor_altitude,
            'ceiling_height': self.ceiling_height,
            'gps_boundaries': self.gps_boundaries,
            'center': {
                'latitude': self.center_latitude,
                'longitude': self.center_longitude
            },
            'reference_pressure': self.reference_pressure,
            'capacity': self.capacity,
            'is_active': self.is_active
        }
    
    def is_location_inside(self, latitude: float, longitude: float) -> bool:
        """Check if a GPS location is inside the room boundaries using ray casting."""
        if not self.gps_boundaries or len(self.gps_boundaries) < 3:
            return False
        
        # Ray casting algorithm for point in polygon
        n = len(self.gps_boundaries)
        inside = False
        
        j = n - 1
        for i in range(n):
            xi, yi = self.gps_boundaries[i]['lat'], self.gps_boundaries[i]['lng']
            xj, yj = self.gps_boundaries[j]['lat'], self.gps_boundaries[j]['lng']
            
            if ((yi > longitude) != (yj > longitude)) and \
               (latitude < (xj - xi) * (longitude - yi) / (yj - yi) + xi):
                inside = not inside
            
            j = i
        
        return inside
    
    def is_altitude_valid(self, user_altitude: float, tolerance: float = 2.0) -> bool:
        """Check if user is at correct floor altitude."""
        min_altitude = self.floor_altitude - tolerance
        max_altitude = self.floor_altitude + self.ceiling_height + tolerance
        return min_altitude <= user_altitude <= max_altitude
