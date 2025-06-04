# File: backend/app/services/sequential_verification_service.py
"""Sequential Verification System for triple attendance verification."""
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import secrets
import json

# Import our services
from app.services.barometer_service import BarometerService, BarometerReading
from app.services.face_recognition_service import FaceRecognitionService, FaceVerificationResult
from app.services.qr_service import QRService
from app.services.gps_service import GPSService
from app.models.room import Room
from app.models.lecture import Lecture
from app.models.user import User

class VerificationStep(Enum):
    """Verification step enumeration."""
    GPS_LOCATION = "gps_location"
    BAROMETER_ALTITUDE = "barometer_altitude"
    QR_CODE = "qr_code"
    FACE_RECOGNITION = "face_recognition"

class VerificationStatus(Enum):
    """Verification status enumeration."""
    PENDING = "pending"
    SUCCESS = "success"
    WARNING = "warning"  # Passed with warnings
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class VerificationStepResult:
    """Result of a single verification step."""
    step: VerificationStep
    status: VerificationStatus
    success: bool
    confidence_score: float
    data: Dict[str, Any]
    warnings: List[str]
    errors: List[str]
    processing_time_ms: int
    timestamp: datetime

@dataclass
class SequentialVerificationSession:
    """Complete verification session data."""
    session_id: str
    student_id: int
    lecture_id: int
    room_id: int
    started_at: datetime
    completed_at: Optional[datetime]
    current_step: VerificationStep
    overall_status: VerificationStatus
    steps_completed: List[VerificationStepResult]
    final_decision: Optional[str]
    attendance_type: Optional[str]  # normal, exceptional, rejected
    total_processing_time_ms: int

class SequentialVerificationService:
    """
    Sequential Verification Service for attendance check-in.
    
    🎯 Verification Flow:
    1. GPS Location Verification (CRITICAL - with warnings if failed)
    2. Barometer Altitude Verification (CRITICAL - with warnings if failed)  
    3. QR Code Verification (REQUIRED - must pass)
    4. Face Recognition Verification (REQUIRED - must pass)
    
    ⚠️ Rules:
    - GPS/Barometer failures → Show warnings but allow exceptional attendance
    - QR failure → REJECT immediately
    - Face Recognition failure → REJECT immediately
    """
    
    # =================== CONSTANTS ===================
    
    SESSION_EXPIRY_MINUTES = 10
    STEP_TIMEOUT_SECONDS = 30
    MIN_OVERALL_CONFIDENCE = 0.7
    
    # Step weights for overall confidence calculation
    STEP_WEIGHTS = {
        VerificationStep.GPS_LOCATION: 0.25,
        VerificationStep.BAROMETER_ALTITUDE: 0.25,
        VerificationStep.QR_CODE: 0.25,
        VerificationStep.FACE_RECOGNITION: 0.25
    }
    
    @classmethod
    def create_verification_session(
        cls,
        student_id: int,
        lecture_id: int,
        initial_data: Dict
    ) -> SequentialVerificationSession:
        """Create new sequential verification session."""
        
        # Get lecture and room info
        lecture = Lecture.query.get(lecture_id)
        if not lecture:
            raise ValueError(f"Lecture {lecture_id} not found")
        
        room = Room.query.get(lecture.room_id) if hasattr(lecture, 'room_id') else None
        if not room:
            # Fallback: find room by name
            room = Room.query.filter_by(name=lecture.room).first()
        
        if not room:
            raise ValueError(f"Room not found for lecture {lecture_id}")
        
        session = SequentialVerificationSession(
            session_id=f"verify_{secrets.token_urlsafe(16)}",
            student_id=student_id,
            lecture_id=lecture_id,
            room_id=room.id,
            started_at=datetime.utcnow(),
            completed_at=None,
            current_step=VerificationStep.GPS_LOCATION,
            overall_status=VerificationStatus.PENDING,
            steps_completed=[],
            final_decision=None,
            attendance_type=None,
            total_processing_time_ms=0
        )
        
        return session
    
    @classmethod
    def process_verification_step(
        cls,
        session: SequentialVerificationSession,
        step_data: Dict
    ) -> Tuple[SequentialVerificationSession, VerificationStepResult]:
        """Process a single verification step."""
        
        step_start_time = datetime.utcnow()
        current_step = session.current_step
        
        # Process the step based on type
        if current_step == VerificationStep.GPS_LOCATION:
            result = cls._process_gps_verification(session, step_data)
        elif current_step == VerificationStep.BAROMETER_ALTITUDE:
            result = cls._process_barometer_verification(session, step_data)
        elif current_step == VerificationStep.QR_CODE:
            result = cls._process_qr_verification(session, step_data)
        elif current_step == VerificationStep.FACE_RECOGNITION:
            result = cls._process_face_verification(session, step_data)
        else:
            raise ValueError(f"Unknown verification step: {current_step}")
        
        # Calculate processing time
        processing_time = int((datetime.utcnow() - step_start_time).total_seconds() * 1000)
        result.processing_time_ms = processing_time
        
        # Add result to session
        session.steps_completed.append(result)
        session.total_processing_time_ms += processing_time
        
        # Determine next step or completion
        session = cls._advance_session_state(session, result)
        
        return session, result
    
    @classmethod
    def _process_gps_verification(
        cls,
        session: SequentialVerificationSession,
        step_data: Dict
    ) -> VerificationStepResult:
        """Process GPS location verification."""
        
        warnings = []
        errors = []
        success = False
        confidence_score = 0.0
        
        try:
            # Get required data
            latitude = step_data.get('latitude')
            longitude = step_data.get('longitude')
            
            if not latitude or not longitude:
                errors.append("GPS coordinates missing")
                return VerificationStepResult(
                    step=VerificationStep.GPS_LOCATION,
                    status=VerificationStatus.FAILED,
                    success=False,
                    confidence_score=0.0,
                    data={'error': 'Missing GPS coordinates'},
                    warnings=warnings,
                    errors=errors,
                    processing_time_ms=0,
                    timestamp=datetime.utcnow()
                )
            
            # Get room for verification
            room = Room.query.get(session.room_id)
            if not room:
                errors.append("Room not found")
                return VerificationStepResult(
                    step=VerificationStep.GPS_LOCATION,
                    status=VerificationStatus.FAILED,
                    success=False,
                    confidence_score=0.0,
                    data={'error': 'Room not found'},
                    warnings=warnings,
                    errors=errors,
                    processing_time_ms=0,
                    timestamp=datetime.utcnow()
                )
            
            # Verify GPS location
            gps_result = GPSService.verify_location(latitude, longitude, room)
            
            if gps_result['is_inside']:
                success = True
                confidence_score = 1.0 - min(0.5, gps_result['distance'] / 20)  # Max 20m penalty
                status = VerificationStatus.SUCCESS
            else:
                success = False
                confidence_score = max(0.0, 0.5 - gps_result['distance'] / 50)  # Distance penalty
                status = VerificationStatus.WARNING  # Allow with warning
                warnings.append(f"أنت خارج حدود القاعة {room.name}")
                warnings.append(f"المسافة من المركز: {gps_result['distance']:.1f} متر")
            
            verification_data = {
                'is_inside': gps_result['is_inside'],
                'distance_meters': gps_result['distance'],
                'room_name': gps_result['room_name'],
                'user_location': {
                    'latitude': latitude,
                    'longitude': longitude
                },
                'room_center': gps_result['room_center'],
                'gps_accuracy': step_data.get('accuracy', 'unknown')
            }
            
        except Exception as e:
            errors.append(f"GPS verification error: {str(e)}")
            status = VerificationStatus.FAILED
            verification_data = {'error': str(e)}
        
        return VerificationStepResult(
            step=VerificationStep.GPS_LOCATION,
            status=status,
            success=success,
            confidence_score=confidence_score,
            data=verification_data,
            warnings=warnings,
            errors=errors,
            processing_time_ms=0,
            timestamp=datetime.utcnow()
        )
    
    @classmethod
    def _process_barometer_verification(
        cls,
        session: SequentialVerificationSession,
        step_data: Dict
    ) -> VerificationStepResult:
        """Process barometer altitude verification."""
        
        warnings = []
        errors = []
        success = False
        confidence_score = 0.0
        
        try:
            # Process barometer reading
            pressure = step_data.get('pressure')
            if not pressure:
                errors.append("Barometer reading missing")
                return VerificationStepResult(
                    step=VerificationStep.BAROMETER_ALTITUDE,
                    status=VerificationStatus.FAILED,
                    success=False,
                    confidence_score=0.0,
                    data={'error': 'Missing barometer data'},
                    warnings=warnings,
                    errors=errors,
                    processing_time_ms=0,
                    timestamp=datetime.utcnow()
                )
            
            # Create barometer reading
            reading = BarometerService.process_barometer_reading(
                raw_pressure=pressure,
                temperature=step_data.get('temperature'),
                humidity=step_data.get('humidity'),
                device_info=step_data.get('device_info', {})
            )
            
            # Get room for verification
            room = Room.query.get(session.room_id)
            
            # Verify altitude
            altitude_result = BarometerService.verify_room_altitude(
                reading=reading,
                room=room,
                tolerance_meters=3.0  # 3 meter tolerance
            )
            
            if altitude_result['is_valid']:
                success = True
                confidence_score = altitude_result['precision_score']
                status = VerificationStatus.SUCCESS
            else:
                success = False
                confidence_score = max(0.0, altitude_result['precision_score'] * 0.5)
                status = VerificationStatus.WARNING  # Allow with warning
                warnings.append(f"أنت في الطابق الخطأ")
                warnings.append(f"الطابق المتوقع: {room.floor}")
                warnings.append(f"فرق الارتفاع: {altitude_result['altitude_difference']:.1f} متر")
            
            verification_data = {
                'is_valid': altitude_result['is_valid'],
                'precision_score': altitude_result['precision_score'],
                'altitude_difference': altitude_result['altitude_difference'],
                'room_altitude': altitude_result['room_altitude'],
                'reading_altitude': altitude_result['reading_altitude'],
                'confidence_level': reading.accuracy_level,
                'barometer_pressure': reading.pressure_hpa,
                'room_floor': room.floor
            }
            
        except Exception as e:
            errors.append(f"Barometer verification error: {str(e)}")
            status = VerificationStatus.FAILED
            verification_data = {'error': str(e)}
        
        return VerificationStepResult(
            step=VerificationStep.BAROMETER_ALTITUDE,
            status=status,
            success=success,
            confidence_score=confidence_score,
            data=verification_data,
            warnings=warnings,
            errors=errors,
            processing_time_ms=0,
            timestamp=datetime.utcnow()
        )
    
    @classmethod
    def _process_qr_verification(
        cls,
        session: SequentialVerificationSession,
        step_data: Dict
    ) -> VerificationStepResult:
        """Process QR code verification."""
        
        warnings = []
        errors = []
        success = False
        confidence_score = 0.0
        status = VerificationStatus.FAILED
        
        try:
            qr_data = step_data.get('qr_data')
            if not qr_data:
                errors.append("QR code data missing")
                return VerificationStepResult(
                    step=VerificationStep.QR_CODE,
                    status=VerificationStatus.FAILED,
                    success=False,
                    confidence_score=0.0,
                    data={'error': 'Missing QR code'},
                    warnings=warnings,
                    errors=errors,
                    processing_time_ms=0,
                    timestamp=datetime.utcnow()
                )
            
            # Validate QR code
            is_valid, qr_info, error_msg = QRService.validate_qr_code(qr_data)
            
            if not is_valid:
                errors.append(error_msg or "Invalid QR code")
                verification_data = {'error': error_msg, 'qr_valid': False}
            else:
                # Check if QR matches the lecture
                if qr_info['lecture_id'] != session.lecture_id:
                    errors.append("QR code doesn't match current lecture")
                    verification_data = {
                        'error': 'Lecture mismatch',
                        'qr_lecture_id': qr_info['lecture_id'],
                        'expected_lecture_id': session.lecture_id
                    }
                else:
                    success = True
                    confidence_score = 1.0
                    status = VerificationStatus.SUCCESS
                    verification_data = {
                        'qr_valid': True,
                        'session_id': qr_info['session_id'],
                        'lecture_id': qr_info['lecture_id'],
                        'room_id': qr_info['room_id'],
                        'expires_at': qr_info['expires_at']
                    }
            
        except Exception as e:
            errors.append(f"QR verification error: {str(e)}")
            verification_data = {'error': str(e)}
        
        return VerificationStepResult(
            step=VerificationStep.QR_CODE,
            status=status,
            success=success,
            confidence_score=confidence_score,
            data=verification_data,
            warnings=warnings,
            errors=errors,
            processing_time_ms=0,
            timestamp=datetime.utcnow()
        )
    
    @classmethod
    def _process_face_verification(
        cls,
        session: SequentialVerificationSession,
        step_data: Dict
    ) -> VerificationStepResult:
        """Process face recognition verification."""
        
        warnings = []
        errors = []
        success = False
        confidence_score = 0.0
        status = VerificationStatus.FAILED
        
        try:
            # Get student's stored face template hash
            student = User.query.get(session.student_id)
            if not student or not hasattr(student, 'student_profile'):
                errors.append("Student not found")
                return VerificationStepResult(
                    step=VerificationStep.FACE_RECOGNITION,
                    status=VerificationStatus.FAILED,
                    success=False,
                    confidence_score=0.0,
                    data={'error': 'Student not found'},
                    warnings=warnings,
                    errors=errors,
                    processing_time_ms=0,
                    timestamp=datetime.utcnow()
                )
            
            student_profile = student.student_profile
            if not student_profile.face_registered:
                errors.append("Face not registered for this student")
                return VerificationStepResult(
                    step=VerificationStep.FACE_RECOGNITION,
                    status=VerificationStatus.FAILED,
                    success=False,
                    confidence_score=0.0,
                    data={'error': 'Face not registered'},
                    warnings=warnings,
                    errors=errors,
                    processing_time_ms=0,
                    timestamp=datetime.utcnow()
                )
            
            # Get verification data from mobile app
            verification_data_from_app = step_data.get('verification_data', {})
            device_info = step_data.get('device_info', {})
            
            # In a real implementation, this would be a hash of the encrypted template
            stored_template_hash = "dummy_hash_for_demo"
            
            # Verify face match
            face_result = FaceRecognitionService.verify_face_match(
                student_id=session.student_id,
                verification_data=verification_data_from_app,
                stored_template_hash=stored_template_hash,
                device_info=device_info
            )
            
            if face_result.is_verified:
                success = True
                confidence_score = face_result.confidence_score
                status = VerificationStatus.SUCCESS
                verification_data = {
                    'face_verified': True,
                    'confidence_score': face_result.confidence_score,
                    'template_match_quality': face_result.template_match_quality,
                    'anti_spoofing_passed': face_result.anti_spoofing_passed,
                    'device_consistency': face_result.device_consistency,
                    'verification_token': face_result.verification_token
                }
            else:
                success = False
                confidence_score = face_result.confidence_score
                errors.append(face_result.error_message or "Face verification failed")
                verification_data = {
                    'face_verified': False,
                    'confidence_score': face_result.confidence_score,
                    'anti_spoofing_passed': face_result.anti_spoofing_passed,
                    'device_consistency': face_result.device_consistency,
                    'error': face_result.error_message
                }
            
        except Exception as e:
            errors.append(f"Face verification error: {str(e)}")
            verification_data = {'error': str(e)}
        
        return VerificationStepResult(
            step=VerificationStep.FACE_RECOGNITION,
            status=status,
            success=success,
            confidence_score=confidence_score,
            data=verification_data,
            warnings=warnings,
            errors=errors,
            processing_time_ms=0,
            timestamp=datetime.utcnow()
        )
    
    @classmethod
    def _advance_session_state(
        cls,
        session: SequentialVerificationSession,
        last_result: VerificationStepResult
    ) -> SequentialVerificationSession:
        """Advance session to next step or complete verification."""
        
        # Define step order
        step_order = [
            VerificationStep.GPS_LOCATION,
            VerificationStep.BAROMETER_ALTITUDE,
            VerificationStep.QR_CODE,
            VerificationStep.FACE_RECOGNITION
        ]
        
        current_index = step_order.index(session.current_step)
        
        # Check if this step is a hard failure (QR or Face)
        if last_result.step in [VerificationStep.QR_CODE, VerificationStep.FACE_RECOGNITION]:
            if not last_result.success:
                # Hard failure - reject immediately
                session.overall_status = VerificationStatus.FAILED
                session.final_decision = "REJECTED"
                session.attendance_type = "rejected"
                session.completed_at = datetime.utcnow()
                return session
        
        # Move to next step if not at the end
        if current_index < len(step_order) - 1:
            session.current_step = step_order[current_index + 1]
        else:
            # All steps completed - determine final decision
            session = cls._finalize_verification_session(session)
        
        return session
    
    @classmethod
    def _finalize_verification_session(
        cls,
        session: SequentialVerificationSession
    ) -> SequentialVerificationSession:
        """Finalize verification session and determine attendance type."""
        
        session.completed_at = datetime.utcnow()
        
        # Analyze all step results
        gps_result = next((r for r in session.steps_completed if r.step == VerificationStep.GPS_LOCATION), None)
        barometer_result = next((r for r in session.steps_completed if r.step == VerificationStep.BAROMETER_ALTITUDE), None)
        qr_result = next((r for r in session.steps_completed if r.step == VerificationStep.QR_CODE), None)
        face_result = next((r for r in session.steps_completed if r.step == VerificationStep.FACE_RECOGNITION), None)
        
        # QR and Face must be successful for any attendance
        if not qr_result or not qr_result.success or not face_result or not face_result.success:
            session.overall_status = VerificationStatus.FAILED
            session.final_decision = "REJECTED"
            session.attendance_type = "rejected"
            return session
        
        # Determine attendance type based on GPS/Barometer
        location_issues = []
        if gps_result and not gps_result.success:
            location_issues.append("GPS location outside room boundaries")
        if barometer_result and not barometer_result.success:
            location_issues.append("Barometer indicates wrong floor")
        
        if location_issues:
            # Exceptional attendance with location warnings
            session.overall_status = VerificationStatus.WARNING
            session.final_decision = "APPROVED_WITH_WARNINGS"
            session.attendance_type = "exceptional"
        else:
            # Normal attendance - all checks passed
            session.overall_status = VerificationStatus.SUCCESS
            session.final_decision = "APPROVED"
            session.attendance_type = "normal"
        
        return session
    
    @classmethod
    def calculate_overall_confidence(cls, session: SequentialVerificationSession) -> float:
        """Calculate overall confidence score from all completed steps."""
        if not session.steps_completed:
            return 0.0
        
        total_weighted_score = 0.0
        total_weight = 0.0
        
        for result in session.steps_completed:
            weight = cls.STEP_WEIGHTS.get(result.step, 0.25)
            total_weighted_score += result.confidence_score * weight
            total_weight += weight
        
        return total_weighted_score / total_weight if total_weight > 0 else 0.0
    
    @classmethod
    def get_session_summary(cls, session: SequentialVerificationSession) -> Dict:
        """Get comprehensive session summary."""
        overall_confidence = cls.calculate_overall_confidence(session)
        
        # Count step statuses
        step_counts = {
            'success': len([r for r in session.steps_completed if r.status == VerificationStatus.SUCCESS]),
            'warning': len([r for r in session.steps_completed if r.status == VerificationStatus.WARNING]),
            'failed': len([r for r in session.steps_completed if r.status == VerificationStatus.FAILED])
        }
        
        # Collect all warnings and errors
        all_warnings = []
        all_errors = []
        for result in session.steps_completed:
            all_warnings.extend(result.warnings)
            all_errors.extend(result.errors)
        
        return {
            'session_id': session.session_id,
            'student_id': session.student_id,
            'lecture_id': session.lecture_id,
            'verification_summary': {
                'overall_status': session.overall_status.value,
                'final_decision': session.final_decision,
                'attendance_type': session.attendance_type,
                'overall_confidence': overall_confidence,
                'steps_completed': len(session.steps_completed),
                'total_processing_time_ms': session.total_processing_time_ms
            },
            'step_breakdown': step_counts,
            'detailed_results': [asdict(result) for result in session.steps_completed],
            'warnings': all_warnings,
            'errors': all_errors,
            'timing': {
                'started_at': session.started_at.isoformat(),
                'completed_at': session.completed_at.isoformat() if session.completed_at else None,
                'duration_seconds': (session.completed_at - session.started_at).total_seconds() if session.completed_at else None
            },
            'recommendations': cls._generate_recommendations(session)
        }
    
    @classmethod
    def _generate_recommendations(cls, session: SequentialVerificationSession) -> List[str]:
        """Generate recommendations based on verification results."""
        recommendations = []
        
        # Check each step for specific recommendations
        for result in session.steps_completed:
            if result.step == VerificationStep.GPS_LOCATION and not result.success:
                recommendations.append("🌍 تحقق من موقعك - يجب أن تكون داخل حدود القاعة")
                recommendations.append("📍 انتقل لمكان مفتوح للحصول على إشارة GPS أفضل")
            
            if result.step == VerificationStep.BAROMETER_ALTITUDE and not result.success:
                recommendations.append("📏 تأكد من أنك في الطابق الصحيح")
                recommendations.append("🔄 انتقل لمكان مفتوح لتحسين قراءة البارومتر")
            
            if result.step == VerificationStep.QR_CODE and not result.success:
                recommendations.append("📱 تأكد من مسح QR الصحيح من شاشة المدرس")
                recommendations.append("⏰ QR Code قد يكون منتهي الصلاحية - اطلب من المدرس تجديده")
            
            if result.step == VerificationStep.FACE_RECOGNITION and not result.success:
                recommendations.append("😊 تأكد من الإضاءة الجيدة ووضوح وجهك")
                recommendations.append("📷 نظف عدسة الكاميرا الأمامية")
                recommendations.append("👤 قد تحتاج لإعادة تسجيل بصمة الوجه")
        
        # Overall recommendations
        if session.attendance_type == "exceptional":
            recommendations.append("⚠️ تم تسجيل حضورك كحضور استثنائي - قد يحتاج موافقة إضافية")
        elif session.attendance_type == "normal":
            recommendations.append("✅ تم تسجيل حضورك بنجاح بجميع التحققات")
        elif session.attendance_type == "rejected":
            recommendations.append("❌ تم رفض تسجيل الحضور - يرجى المحاولة مرة أخرى")
        
        return recommendations if recommendations else ["لا توجد توصيات إضافية"]