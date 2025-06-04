# File: backend/app/models/room.py - ENHANCED VERSION
"""Enhanced Room model with 3D GPS boundaries, barometer precision, and dynamic recording."""
from app import db
from app.models.base import BaseModel
from sqlalchemy.dialects.postgresql import JSON
from typing import List, Dict, Tuple, Optional
import math
from datetime import datetime

class Room(BaseModel):
    """Enhanced Room/Classroom model with 3D location data and barometric precision."""
    
    __tablename__ = 'rooms'
    
    # =================== BASIC INFO ===================
    name = db.Column(db.String(50), nullable=False, unique=True)  # A101, B201, etc.
    building = db.Column(db.String(100), nullable=False)  # المبنى الرئيسي، مبنى الحاسبات
    floor = db.Column(db.Integer, nullable=False)  # رقم الطابق
    room_number = db.Column(db.String(20), nullable=True)  # رقم القاعة في الطابق
    
    # =================== 3D LOCATION DATA ===================
    # Altitude Data (متر)
    ground_reference_altitude = db.Column(db.Float, nullable=False)  # الارتفاع المرجعي للأرض
    floor_altitude_above_ground = db.Column(db.Float, nullable=False)  # ارتفاع الطابق عن الأرض
    room_floor_altitude = db.Column(db.Float, nullable=False)  # ارتفاع أرضية القاعة
    ceiling_height = db.Column(db.Float, nullable=False)  # ارتفاع السقف من الأرضية
    room_ceiling_altitude = db.Column(db.Float, nullable=False)  # ارتفاع السقف المطلق
    
    # GPS Boundaries (نقاط المضلع)
    gps_boundaries = db.Column(JSON, nullable=False)  # [{lat, lng, alt}, {lat, lng, alt}, ...]
    corner_points_3d = db.Column(JSON, nullable=False)  # نقاط الزوايا الثلاثية
    
    # Center Point
    center_latitude = db.Column(db.Float, nullable=False)
    center_longitude = db.Column(db.Float, nullable=False)
    center_altitude = db.Column(db.Float, nullable=False)
    
    # =================== BAROMETER DATA ===================
    # Pressure References (ضغط جوي - هيكتوباسكال)
    ground_reference_pressure = db.Column(db.Float, nullable=True)  # ضغط مرجعي للأرض
    floor_reference_pressure = db.Column(db.Float, nullable=True)  # ضغط مرجعي للطابق
    room_pressure_range = db.Column(JSON, nullable=True)  # {min: 1013.2, max: 1013.8}
    pressure_tolerance = db.Column(db.Float, default=0.5)  # هامش خطأ الضغط
    
    # =================== 3D GEOMETRY ===================
    # Calculated Properties
    room_area_sqm = db.Column(db.Float, nullable=True)  # مساحة القاعة م²
    room_volume_cubic_m = db.Column(db.Float, nullable=True)  # حجم القاعة م³
    room_perimeter_m = db.Column(db.Float, nullable=True)  # محيط القاعة
    
    # =================== DYNAMIC RECORDING ===================
    # Recording Metadata
    recorded_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    recorded_at = db.Column(db.DateTime, nullable=True)
    recording_path = db.Column(JSON, nullable=True)  # المسار المسجل أثناء المشي
    recording_duration_seconds = db.Column(db.Integer, nullable=True)
    recording_accuracy_metadata = db.Column(JSON, nullable=True)  # بيانات دقة التسجيل
    
    # Validation Status
    is_3d_validated = db.Column(db.Boolean, default=False)  # تم التحقق من البعد الثالث
    validation_notes = db.Column(db.Text, nullable=True)
    
    # =================== STATUS & PROPERTIES ===================
    is_active = db.Column(db.Boolean, default=True)
    capacity = db.Column(db.Integer, default=30)
    room_type = db.Column(db.String(50), default='classroom')  # classroom, lab, hall
    
    # =================== RELATIONSHIPS ===================
    schedules = db.relationship('Schedule', backref='room', lazy='dynamic')
    recorded_by = db.relationship('User', backref='recorded_rooms')
    
    # =================== INSTANCE METHODS ===================
    
    def calculate_3d_properties(self) -> None:
        """Calculate room area, volume, and perimeter from 3D boundaries."""
        if not self.gps_boundaries or len(self.gps_boundaries) < 3:
            return
        
        # Calculate area using Shoelace formula (GPS coordinates)
        area = 0.0
        n = len(self.gps_boundaries)
        
        for i in range(n):
            j = (i + 1) % n
            # Convert to meters using Haversine approximation
            lat1, lng1 = self.gps_boundaries[i]['lat'], self.gps_boundaries[i]['lng']
            lat2, lng2 = self.gps_boundaries[j]['lat'], self.gps_boundaries[j]['lng']
            
            # Approximate meters conversion (for small areas)
            x1 = lng1 * 111320 * math.cos(math.radians(lat1))
            y1 = lat1 * 110540
            x2 = lng2 * 111320 * math.cos(math.radians(lat2))
            y2 = lat2 * 110540
            
            area += (x1 * y2 - x2 * y1)
        
        self.room_area_sqm = abs(area) / 2.0
        self.room_volume_cubic_m = self.room_area_sqm * self.ceiling_height
        
        # Calculate perimeter
        perimeter = 0.0
        for i in range(n):
            j = (i + 1) % n
            dist = self._calculate_gps_distance(
                self.gps_boundaries[i]['lat'], self.gps_boundaries[i]['lng'],
                self.gps_boundaries[j]['lat'], self.gps_boundaries[j]['lng']
            )
            perimeter += dist
        
        self.room_perimeter_m = perimeter
    
    def is_location_inside_3d(self, latitude: float, longitude: float, altitude: float) -> Dict:
        """Enhanced 3D location verification with altitude precision."""
        # 1. Check if inside 2D polygon
        is_inside_2d = self._is_point_in_polygon(latitude, longitude)
        
        # 2. Check altitude range (with tolerance)
        altitude_valid = self._is_altitude_valid(altitude)
        
        # 3. Calculate distance from center
        distance_2d = self._calculate_gps_distance(
            latitude, longitude, self.center_latitude, self.center_longitude
        )
        
        # 4. Calculate 3D distance including altitude
        altitude_diff = abs(altitude - self.center_altitude)
        distance_3d = math.sqrt(distance_2d**2 + altitude_diff**2)
        
        return {
            'is_inside_2d': is_inside_2d,
            'is_altitude_valid': altitude_valid['is_valid'],
            'is_inside_3d': is_inside_2d and altitude_valid['is_valid'],
            'distance_2d_meters': distance_2d,
            'distance_3d_meters': distance_3d,
            'altitude_difference': altitude_diff,
            'altitude_details': altitude_valid,
            'room_info': {
                'name': self.name,
                'floor': self.floor,
                'altitude_range': {
                    'min': self.room_floor_altitude,
                    'max': self.room_ceiling_altitude
                }
            }
        }
    
    def verify_barometric_pressure(self, current_pressure: float) -> Dict:
        """Verify user's barometric pressure against room reference."""
        if not self.room_pressure_range:
            return {'is_valid': None, 'message': 'No pressure reference available'}
        
        min_pressure = self.room_pressure_range.get('min', 0)
        max_pressure = self.room_pressure_range.get('max', 9999)
        
        is_valid = min_pressure <= current_pressure <= max_pressure
        
        return {
            'is_valid': is_valid,
            'current_pressure': current_pressure,
            'expected_range': self.room_pressure_range,
            'difference': current_pressure - self.floor_reference_pressure if self.floor_reference_pressure else None,
            'tolerance': self.pressure_tolerance,
            'floor': self.floor
        }
    
    def _is_point_in_polygon(self, latitude: float, longitude: float) -> bool:
        """Ray casting algorithm for point in polygon (2D)."""
        if not self.gps_boundaries or len(self.gps_boundaries) < 3:
            return False
        
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
    
    def _is_altitude_valid(self, user_altitude: float) -> Dict:
        """Check if user altitude is within room's 3D boundaries."""
        tolerance = 2.0  # متر
        
        min_altitude = self.room_floor_altitude - tolerance
        max_altitude = self.room_ceiling_altitude + tolerance
        
        is_valid = min_altitude <= user_altitude <= max_altitude
        
        # Determine which floor user might be on
        estimated_floor = max(1, round((user_altitude - self.ground_reference_altitude) / 3.5))
        
        return {
            'is_valid': is_valid,
            'user_altitude': user_altitude,
            'expected_range': {
                'min': min_altitude,
                'max': max_altitude
            },
            'room_floor': self.floor,
            'estimated_user_floor': estimated_floor,
            'altitude_error': user_altitude - self.center_altitude,
            'tolerance': tolerance
        }
    
    def _calculate_gps_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate distance between two GPS points in meters (Haversine formula)."""
        R = 6371000  # Earth radius in meters
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)
        
        a = (math.sin(delta_lat/2)**2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * 
             math.sin(delta_lng/2)**2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    # =================== CLASS METHODS ===================
    
    @classmethod
    def create_from_dynamic_recording(cls, recording_data: Dict) -> 'Room':
        """Create room from dynamic recording data."""
        # Calculate center point
        points = recording_data['gps_boundaries']
        center_lat = sum(p['lat'] for p in points) / len(points)
        center_lng = sum(p['lng'] for p in points) / len(points)
        center_alt = sum(p['alt'] for p in points) / len(points)
        
        room = cls(
            name=recording_data['name'],
            building=recording_data.get('building', 'المبنى الرئيسي'),
            floor=recording_data.get('floor', 1),
            ground_reference_altitude=recording_data.get('ground_altitude', 0),
            floor_altitude_above_ground=recording_data.get('floor_altitude', 0),
            room_floor_altitude=recording_data.get('room_floor_altitude', 0),
            ceiling_height=recording_data.get('ceiling_height', 3.5),
            room_ceiling_altitude=recording_data.get('room_floor_altitude', 0) + recording_data.get('ceiling_height', 3.5),
            gps_boundaries=recording_data['gps_boundaries'],
            corner_points_3d=recording_data.get('corner_points_3d', []),
            center_latitude=center_lat,
            center_longitude=center_lng,
            center_altitude=center_alt,
            room_pressure_range=recording_data.get('pressure_range'),
            recorded_by_user_id=recording_data.get('recorded_by'),
            recorded_at=datetime.now(datetime.timezone.utc),
            recording_path=recording_data.get('recording_path'),
            is_3d_validated=True
        )
        
        room.calculate_3d_properties()
        return room
    
    # =================== SERIALIZATION ===================
    
    def to_dict(self, include_3d: bool = True) -> Dict:
        """Convert to dictionary with optional 3D data."""
        base_data = {
            'id': self.id,
            'name': self.name,
            'building': self.building,
            'floor': self.floor,
            'room_number': self.room_number,
            'center': {
                'latitude': self.center_latitude,
                'longitude': self.center_longitude,
                'altitude': self.center_altitude
            },
            'capacity': self.capacity,
            'room_type': self.room_type,
            'is_active': self.is_active
        }
        
        if include_3d:
            base_data.update({
                '3d_geometry': {
                    'boundaries': self.gps_boundaries,
                    'corner_points': self.corner_points_3d,
                    'altitude_range': {
                        'floor': self.room_floor_altitude,
                        'ceiling': self.room_ceiling_altitude,
                        'height': self.ceiling_height
                    },
                    'calculated_properties': {
                        'area_sqm': self.room_area_sqm,
                        'volume_cubic_m': self.room_volume_cubic_m,
                        'perimeter_m': self.room_perimeter_m
                    }
                },
                'barometer': {
                    'pressure_range': self.room_pressure_range,
                    'tolerance': self.pressure_tolerance,
                    'reference_pressure': self.floor_reference_pressure
                },
                'recording_info': {
                    'recorded_by': self.recorded_by_user_id,
                    'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None,
                    'is_validated': self.is_3d_validated,
                    'validation_notes': self.validation_notes
                }
            })
        
        return base_data
    
    def __repr__(self) -> str:
        return f'<Room {self.name} - Floor {self.floor} - 3D:{self.is_3d_validated}>'