# File: backend/app/services/barometer_service.py
"""High-precision barometer service for floor detection and altitude verification."""
import math
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from app.models.room import Room

@dataclass
class BarometerReading:
    """Barometer reading data structure."""
    pressure_hpa: float              # ضغط بالهيكتوباسكال
    altitude_estimate_m: float       # ارتفاع مقدر بالمتر
    temperature_c: Optional[float]   # درجة الحرارة (للمعايرة)
    humidity_percent: Optional[float] # الرطوبة (للمعايرة)
    timestamp: datetime              # وقت القراءة
    accuracy_level: str              # high, medium, low
    device_info: Dict                # معلومات الجهاز

@dataclass
class FloorDetectionResult:
    """Floor detection result."""
    detected_floor: int
    confidence_level: float          # 0.0 to 1.0
    pressure_difference: float       # الفرق في الضغط
    altitude_difference: float       # الفرق في الارتفاع
    closest_room_matches: List[Dict] # القاعات المطابقة
    calibration_needed: bool         # هل تحتاج معايرة

class BarometerService:
    """High-precision barometer service for 3D room verification."""
    
    # =================== CONSTANTS ===================
    
    # Standard atmospheric pressure (sea level)
    SEA_LEVEL_PRESSURE_HPA = 1013.25
    
    # Pressure change per meter altitude (average)
    PRESSURE_CHANGE_PER_METER = 0.12  # hPa/m
    
    # Floor height estimates (meters)
    TYPICAL_FLOOR_HEIGHT = 3.5
    GROUND_FLOOR_TOLERANCE = 1.0
    FLOOR_DETECTION_TOLERANCE = 1.5
    
    # Calibration settings
    MIN_READINGS_FOR_CALIBRATION = 5
    CALIBRATION_TIME_WINDOW = 300  # 5 minutes
    
    @classmethod
    def process_barometer_reading(
        cls, 
        raw_pressure: float,
        temperature: Optional[float] = None,
        humidity: Optional[float] = None,
        device_info: Optional[Dict] = None
    ) -> BarometerReading:
        """Process raw barometer data into structured reading."""
        
        # Apply temperature compensation if available
        compensated_pressure = cls._apply_temperature_compensation(
            raw_pressure, temperature
        )
        
        # Calculate altitude estimate using standard formula
        altitude_estimate = cls._pressure_to_altitude(compensated_pressure)
        
        # Determine accuracy level based on available data
        accuracy_level = cls._determine_accuracy_level(
            temperature, humidity, device_info
        )
        
        return BarometerReading(
            pressure_hpa=compensated_pressure,
            altitude_estimate_m=altitude_estimate,
            temperature_c=temperature,
            humidity_percent=humidity,
            timestamp=datetime.utcnow(),
            accuracy_level=accuracy_level,
            device_info=device_info or {}
        )
    
    @classmethod
    def detect_floor_from_pressure(
        cls,
        reading: BarometerReading,
        reference_ground_pressure: float,
        building_id: Optional[int] = None
    ) -> FloorDetectionResult:
        """Detect floor level from barometer reading."""
        
        # Calculate pressure difference from ground reference
        pressure_diff = reference_ground_pressure - reading.pressure_hpa
        
        # Estimate altitude above ground
        altitude_above_ground = pressure_diff / cls.PRESSURE_CHANGE_PER_METER
        
        # Estimate floor number
        estimated_floor = max(1, round(altitude_above_ground / cls.TYPICAL_FLOOR_HEIGHT))
        
        # Calculate confidence based on reading quality
        confidence = cls._calculate_floor_confidence(
            reading, pressure_diff, altitude_above_ground
        )
        
        # Find closest room matches
        room_matches = cls._find_closest_room_matches(
            reading, estimated_floor, building_id
        )
        
        return FloorDetectionResult(
            detected_floor=estimated_floor,
            confidence_level=confidence,
            pressure_difference=pressure_diff,
            altitude_difference=altitude_above_ground,
            closest_room_matches=room_matches,
            calibration_needed=confidence < 0.7
        )
    
    @classmethod
    def verify_room_altitude(
        cls,
        reading: BarometerReading,
        room: Room,
        tolerance_meters: float = 2.0
    ) -> Dict:
        """Verify if barometer reading matches room's altitude."""
        
        # Check if reading altitude is within room's 3D boundaries
        room_verification = room.verify_barometric_pressure(reading.pressure_hpa)
        
        # Calculate altitude difference
        altitude_diff = abs(reading.altitude_estimate_m - room.center_altitude)
        
        # Determine if within tolerance
        is_altitude_match = altitude_diff <= tolerance_meters
        
        # Calculate precision score
        precision_score = max(0.0, 1.0 - (altitude_diff / (tolerance_meters * 2)))
        
        return {
            'is_valid': is_altitude_match,
            'precision_score': precision_score,
            'altitude_difference': altitude_diff,
            'tolerance_meters': tolerance_meters,
            'room_altitude': room.center_altitude,
            'reading_altitude': reading.altitude_estimate_m,
            'barometer_verification': room_verification,
            'confidence_level': reading.accuracy_level,
            'recommendations': cls._generate_altitude_recommendations(
                altitude_diff, tolerance_meters, reading.accuracy_level
            )
        }
    
    @classmethod
    def calibrate_ground_reference(
        cls,
        readings: List[BarometerReading],
        known_ground_altitude: float = 0.0
    ) -> Dict:
        """Calibrate ground reference pressure from multiple readings."""
        
        if len(readings) < cls.MIN_READINGS_FOR_CALIBRATION:
            return {
                'success': False,
                'error': f'Need at least {cls.MIN_READINGS_FOR_CALIBRATION} readings'
            }
        
        # Filter readings within time window
        recent_readings = cls._filter_recent_readings(readings)
        
        if not recent_readings:
            return {
                'success': False,
                'error': 'No recent readings available'
            }
        
        # Calculate average pressure
        avg_pressure = sum(r.pressure_hpa for r in recent_readings) / len(recent_readings)
        
        # Calculate standard deviation for quality assessment
        std_dev = cls._calculate_standard_deviation([r.pressure_hpa for r in recent_readings])
        
        # Determine calibration quality
        quality = cls._assess_calibration_quality(std_dev, recent_readings)
        
        return {
            'success': True,
            'ground_reference_pressure': avg_pressure,
            'ground_altitude': known_ground_altitude,
            'calibration_quality': quality,
            'readings_used': len(recent_readings),
            'pressure_std_dev': std_dev,
            'calibration_timestamp': datetime.utcnow(),
            'valid_until': datetime.utcnow() + timedelta(hours=6)  # Calibration expires after 6 hours
        }
    
    @classmethod
    def track_room_recording_path(
        cls,
        readings: List[BarometerReading],
        gps_path: List[Dict]
    ) -> Dict:
        """Track barometer readings during room boundary recording."""
        
        if len(readings) != len(gps_path):
            return {
                'success': False,
                'error': 'Barometer readings and GPS path must have same length'
            }
        
        # Combine barometer and GPS data
        combined_path = []
        altitude_consistency = []
        
        for i, (reading, gps_point) in enumerate(zip(readings, gps_path)):
            combined_point = {
                'sequence': i,
                'latitude': gps_point['lat'],
                'longitude': gps_point['lng'],
                'gps_altitude': gps_point.get('alt', 0),
                'barometer_altitude': reading.altitude_estimate_m,
                'pressure': reading.pressure_hpa,
                'timestamp': reading.timestamp,
                'accuracy': reading.accuracy_level
            }
            combined_path.append(combined_point)
            
            # Check altitude consistency between GPS and barometer
            if 'alt' in gps_point:
                alt_diff = abs(gps_point['alt'] - reading.altitude_estimate_m)
                altitude_consistency.append(alt_diff)
        
        # Calculate path statistics
        path_stats = cls._calculate_path_statistics(combined_path, altitude_consistency)
        
        return {
            'success': True,
            'combined_path': combined_path,
            'path_statistics': path_stats,
            'altitude_consistency': {
                'avg_difference': sum(altitude_consistency) / len(altitude_consistency) if altitude_consistency else 0,
                'max_difference': max(altitude_consistency) if altitude_consistency else 0,
                'is_consistent': all(diff < 3.0 for diff in altitude_consistency)  # 3 meter tolerance
            }
        }
    
    # =================== PRIVATE HELPER METHODS ===================
    
    @classmethod
    def _apply_temperature_compensation(cls, pressure: float, temperature: Optional[float]) -> float:
        """Apply temperature compensation to pressure reading."""
        if temperature is None:
            return pressure  # No compensation possible
        
        # Standard temperature compensation formula
        # Assuming 15°C as reference temperature
        reference_temp = 15.0
        temp_coefficient = 0.0065  # Per degree Celsius
        
        compensation_factor = 1 + (temp_coefficient * (temperature - reference_temp))
        return pressure * compensation_factor
    
    @classmethod
    def _pressure_to_altitude(cls, pressure_hpa: float) -> float:
        """Convert pressure to altitude using barometric formula."""
        # Standard barometric formula
        # Assumes sea level pressure of 1013.25 hPa
        return 44330 * (1 - (pressure_hpa / cls.SEA_LEVEL_PRESSURE_HPA) ** 0.1903)
    
    @classmethod
    def _determine_accuracy_level(
        cls,
        temperature: Optional[float],
        humidity: Optional[float],
        device_info: Optional[Dict]
    ) -> str:
        """Determine accuracy level based on available sensor data."""
        score = 0
        
        # Temperature sensor available
        if temperature is not None:
            score += 1
        
        # Humidity sensor available
        if humidity is not None:
            score += 1
        
        # Device quality indicators
        if device_info:
            if device_info.get('has_high_precision_barometer'):
                score += 2
            elif device_info.get('has_barometer'):
                score += 1
        
        if score >= 3:
            return 'high'
        elif score >= 2:
            return 'medium'
        else:
            return 'low'
    
    @classmethod
    def _calculate_floor_confidence(
        cls,
        reading: BarometerReading,
        pressure_diff: float,
        altitude_estimate: float
    ) -> float:
        """Calculate confidence level for floor detection."""
        confidence = 0.5  # Base confidence
        
        # Accuracy level bonus
        accuracy_bonus = {
            'high': 0.3,
            'medium': 0.2,
            'low': 0.1
        }
        confidence += accuracy_bonus.get(reading.accuracy_level, 0)
        
        # Pressure difference consistency
        expected_pressure_diff = altitude_estimate * cls.PRESSURE_CHANGE_PER_METER
        pressure_consistency = 1 - abs(pressure_diff - expected_pressure_diff) / max(pressure_diff, 1)
        confidence += 0.2 * max(0, pressure_consistency)
        
        return min(1.0, confidence)
    
    @classmethod
    def _find_closest_room_matches(
        cls,
        reading: BarometerReading,
        estimated_floor: int,
        building_id: Optional[int]
    ) -> List[Dict]:
        """Find rooms that match the barometer reading."""
        # This would query the database for rooms on the estimated floor
        # For now, returning a placeholder structure
        
        matches = []
        # In real implementation, query Room model here
        # rooms = Room.query.filter_by(floor=estimated_floor, is_active=True)
        
        # Placeholder match
        matches.append({
            'room_id': None,
            'room_name': f'Floor {estimated_floor} rooms',
            'altitude_match_score': 0.8,
            'pressure_match_score': 0.7,
            'overall_score': 0.75
        })
        
        return matches
    
    @classmethod
    def _generate_altitude_recommendations(
        cls,
        altitude_diff: float,
        tolerance: float,
        accuracy_level: str
    ) -> List[str]:
        """Generate recommendations based on altitude verification."""
        recommendations = []
        
        if altitude_diff > tolerance:
            recommendations.append(f"ارتفاع القراءة خارج النطاق المسموح ({tolerance:.1f}م)")
            
            if altitude_diff > tolerance * 2:
                recommendations.append("تحقق من أن الجهاز في الطابق الصحيح")
            
            if accuracy_level == 'low':
                recommendations.append("جودة قراءة البارومتر منخفضة - حاول في مكان مفتوح")
        
        if accuracy_level != 'high':
            recommendations.append("لتحسين الدقة: تأكد من وجود الجهاز في مكان مفتوح")
        
        return recommendations
    
    @classmethod
    def _filter_recent_readings(cls, readings: List[BarometerReading]) -> List[BarometerReading]:
        """Filter readings within calibration time window."""
        cutoff_time = datetime.utcnow() - timedelta(seconds=cls.CALIBRATION_TIME_WINDOW)
        return [r for r in readings if r.timestamp >= cutoff_time]
    
    @classmethod
    def _calculate_standard_deviation(cls, values: List[float]) -> float:
        """Calculate standard deviation of pressure readings."""
        if len(values) < 2:
            return 0.0
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return math.sqrt(variance)
    
    @classmethod
    def _assess_calibration_quality(cls, std_dev: float, readings: List[BarometerReading]) -> str:
        """Assess quality of calibration based on readings consistency."""
        if std_dev < 0.5:
            return 'excellent'
        elif std_dev < 1.0:
            return 'good'
        elif std_dev < 2.0:
            return 'fair'
        else:
            return 'poor'
    
    @classmethod
    def _calculate_path_statistics(cls, path: List[Dict], altitude_consistency: List[float]) -> Dict:
        """Calculate statistics for recorded path."""
        if not path:
            return {}
        
        pressures = [p['pressure'] for p in path]
        altitudes = [p['barometer_altitude'] for p in path]
        
        return {
            'total_points': len(path),
            'pressure_range': {
                'min': min(pressures),
                'max': max(pressures),
                'avg': sum(pressures) / len(pressures)
            },
            'altitude_range': {
                'min': min(altitudes),
                'max': max(altitudes),
                'avg': sum(altitudes) / len(altitudes)
            },
            'recording_duration': (path[-1]['timestamp'] - path[0]['timestamp']).total_seconds(),
            'avg_altitude_consistency': sum(altitude_consistency) / len(altitude_consistency) if altitude_consistency else 0
        }