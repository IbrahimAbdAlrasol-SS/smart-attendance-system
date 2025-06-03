
# backend/app/services/gps_service.py
"""GPS verification service."""
import jwt
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
import math
import secrets

class GPSService:
    """Service for GPS and location verification."""
    
    # Secret key for verification tokens
    VERIFICATION_SECRET = "gps-verification-secret-key"
    
    @staticmethod
    def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two GPS points in meters."""
        R = 6371000  # Earth radius in meters
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat/2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * 
             math.sin(delta_lon/2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    @staticmethod
    def verify_location(user_lat: float, user_lng: float, room) -> Dict:
        """Verify if user is within room boundaries."""
        # Calculate distance from room center
        distance = GPSService.calculate_distance(
            user_lat, user_lng,
            room.center_latitude, room.center_longitude
        )
        
        is_inside = distance <= room.radius_meters
        
        return {
            'is_inside': is_inside,
            'distance': distance,
            'room_radius': room.radius_meters,
            'room_center': {
                'latitude': room.center_latitude,
                'longitude': room.center_longitude
            }
        }
    
    @staticmethod
    def verify_altitude(user_altitude: float, room_altitude: float, tolerance: float = 3.0) -> Dict:
        """Verify if user is at correct floor/altitude."""
        difference = abs(user_altitude - room_altitude)
        is_valid = difference <= tolerance
        
        return {
            'is_valid': is_valid,
            'difference': difference,
            'expected_altitude': room_altitude,
            'user_altitude': user_altitude,
            'tolerance': tolerance
        }
    
    @staticmethod
    def create_verification_token(user_id: int, lecture_id: int, room_id: int) -> str:
        """Create temporary verification token after GPS check."""
        payload = {
            'user_id': user_id,
            'lecture_id': lecture_id,
            'room_id': room_id,
            'timestamp': datetime.utcnow().isoformat(),
            'exp': datetime.utcnow() + timedelta(minutes=2),
            'nonce': secrets.token_hex(8)
        }
        
        token = jwt.encode(
            payload,
            GPSService.VERIFICATION_SECRET,
            algorithm='HS256'
        )
        
        return token
    
    @staticmethod
    def verify_token(token: str) -> Tuple[bool, Optional[Dict]]:
        """Verify GPS verification token."""
        try:
            payload = jwt.decode(
                token,
                GPSService.VERIFICATION_SECRET,
                algorithms=['HS256']
            )
            return True, payload
        except jwt.ExpiredSignatureError:
            return False, None
        except jwt.InvalidTokenError:
            return False, None