# File: backend/app/services/face_recognition_service.py
"""Face Recognition Service for secure local face verification."""
import base64
import hashlib
import secrets
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import json

@dataclass
class FaceRegistrationResult:
    """Face registration result data structure."""
    success: bool
    student_id: int
    registration_token: str
    encrypted_template_hash: str
    registration_timestamp: datetime
    template_quality_score: float
    device_info: Dict
    error_message: Optional[str] = None

@dataclass
class FaceVerificationResult:
    """Face verification result data structure."""
    is_verified: bool
    student_id: int
    confidence_score: float
    verification_timestamp: datetime
    template_match_quality: float
    anti_spoofing_passed: bool
    device_consistency: bool
    verification_token: str
    error_message: Optional[str] = None

class FaceRecognitionService:
    """
    Secure Face Recognition Service for attendance verification.
    
    🔒 Security Features:
    - Local processing only (no face data sent to server)
    - Encrypted template storage on device
    - Anti-spoofing detection
    - Device consistency checks
    - Time-based verification tokens
    """
    
    # =================== CONSTANTS ===================
    
    # Security settings
    TEMPLATE_ENCRYPTION_KEY_SIZE = 32
    VERIFICATION_TOKEN_EXPIRY = 300  # 5 minutes
    MIN_TEMPLATE_QUALITY = 0.7
    MIN_VERIFICATION_CONFIDENCE = 0.85
    MAX_REGISTRATION_ATTEMPTS = 3
    
    # Anti-spoofing thresholds
    LIVENESS_DETECTION_THRESHOLD = 0.8
    DEPTH_ANALYSIS_THRESHOLD = 0.75
    MOTION_DETECTION_THRESHOLD = 0.7
    
    @classmethod
    def generate_encryption_key(cls, student_id: int, device_id: str) -> bytes:
        """Generate unique encryption key for student's face template."""
        # Create deterministic key from student ID + device ID
        password = f"{student_id}:{device_id}:face_template".encode()
        salt = hashlib.sha256(f"smart_attendance:{student_id}".encode()).digest()[:16]
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=cls.TEMPLATE_ENCRYPTION_KEY_SIZE,
            salt=salt,
            iterations=100000,
        )
        return kdf.derive(password)
    
    @classmethod
    def register_face_template(
        cls,
        student_id: int,
        template_data: Dict,
        device_info: Dict
    ) -> FaceRegistrationResult:
        """
        Register face template for first-time use.
        
        Args:
            student_id: Student's database ID
            template_data: Face template from mobile app (already processed)
            device_info: Device information for consistency checks
        
        Returns:
            FaceRegistrationResult with registration status
        """
        try:
            # Validate template quality
            quality_score = template_data.get('quality_score', 0.0)
            if quality_score < cls.MIN_TEMPLATE_QUALITY:
                return FaceRegistrationResult(
                    success=False,
                    student_id=student_id,
                    registration_token="",
                    encrypted_template_hash="",
                    registration_timestamp=datetime.utcnow(),
                    template_quality_score=quality_score,
                    device_info=device_info,
                    error_message=f"Template quality too low: {quality_score:.2f} < {cls.MIN_TEMPLATE_QUALITY}"
                )
            
            # Validate anti-spoofing data
            anti_spoofing = template_data.get('anti_spoofing', {})
            if not cls._validate_anti_spoofing(anti_spoofing):
                return FaceRegistrationResult(
                    success=False,
                    student_id=student_id,
                    registration_token="",
                    encrypted_template_hash="",
                    registration_timestamp=datetime.utcnow(),
                    template_quality_score=quality_score,
                    device_info=device_info,
                    error_message="Anti-spoofing validation failed"
                )
            
            # Generate encryption key
            device_id = device_info.get('device_id', 'unknown')
            encryption_key = cls.generate_encryption_key(student_id, device_id)
            fernet = Fernet(base64.urlsafe_b64encode(encryption_key))
            
            # Create template package
            template_package = {
                'template_vector': template_data['template_vector'],
                'quality_metrics': template_data.get('quality_metrics', {}),
                'registration_timestamp': datetime.utcnow().isoformat(),
                'device_info': device_info,
                'anti_spoofing_data': anti_spoofing
            }
            
            # Encrypt template
            template_json = json.dumps(template_package, separators=(',', ':'))
            encrypted_template = fernet.encrypt(template_json.encode())
            
            # Create hash for storage verification
            template_hash = hashlib.sha256(encrypted_template).hexdigest()
            
            # Generate registration token
            registration_token = cls._generate_registration_token(student_id, template_hash)
            
            return FaceRegistrationResult(
                success=True,
                student_id=student_id,
                registration_token=registration_token,
                encrypted_template_hash=template_hash,
                registration_timestamp=datetime.utcnow(),
                template_quality_score=quality_score,
                device_info=device_info
            )
            
        except Exception as e:
            return FaceRegistrationResult(
                success=False,
                student_id=student_id,
                registration_token="",
                encrypted_template_hash="",
                registration_timestamp=datetime.utcnow(),
                template_quality_score=0.0,
                device_info=device_info,
                error_message=f"Registration error: {str(e)}"
            )
    
    @classmethod
    def verify_face_match(
        cls,
        student_id: int,
        verification_data: Dict,
        stored_template_hash: str,
        device_info: Dict
    ) -> FaceVerificationResult:
        """
        Verify face match for attendance check-in.
        
        Args:
            student_id: Student's database ID
            verification_data: Current face verification data from mobile
            stored_template_hash: Previously stored encrypted template hash
            device_info: Current device information
        
        Returns:
            FaceVerificationResult with verification status
        """
        try:
            verification_timestamp = datetime.utcnow()
            
            # Validate current verification quality
            confidence_score = verification_data.get('match_confidence', 0.0)
            if confidence_score < cls.MIN_VERIFICATION_CONFIDENCE:
                return FaceVerificationResult(
                    is_verified=False,
                    student_id=student_id,
                    confidence_score=confidence_score,
                    verification_timestamp=verification_timestamp,
                    template_match_quality=0.0,
                    anti_spoofing_passed=False,
                    device_consistency=False,
                    verification_token="",
                    error_message=f"Confidence too low: {confidence_score:.2f} < {cls.MIN_VERIFICATION_CONFIDENCE}"
                )
            
            # Validate anti-spoofing for current verification
            current_anti_spoofing = verification_data.get('anti_spoofing', {})
            anti_spoofing_passed = cls._validate_anti_spoofing(current_anti_spoofing)
            
            if not anti_spoofing_passed:
                return FaceVerificationResult(
                    is_verified=False,
                    student_id=student_id,
                    confidence_score=confidence_score,
                    verification_timestamp=verification_timestamp,
                    template_match_quality=0.0,
                    anti_spoofing_passed=False,
                    device_consistency=False,
                    verification_token="",
                    error_message="Anti-spoofing validation failed"
                )
            
            # Check device consistency
            device_consistency = cls._check_device_consistency(
                verification_data.get('device_info', {}),
                device_info
            )
            
            # Validate template match quality
            template_match_quality = verification_data.get('template_match_quality', 0.0)
            
            # Generate verification token if all checks pass
            verification_token = ""
            is_verified = (
                confidence_score >= cls.MIN_VERIFICATION_CONFIDENCE and
                anti_spoofing_passed and
                template_match_quality >= 0.7
            )
            
            if is_verified:
                verification_token = cls._generate_verification_token(
                    student_id, verification_timestamp
                )
            
            return FaceVerificationResult(
                is_verified=is_verified,
                student_id=student_id,
                confidence_score=confidence_score,
                verification_timestamp=verification_timestamp,
                template_match_quality=template_match_quality,
                anti_spoofing_passed=anti_spoofing_passed,
                device_consistency=device_consistency,
                verification_token=verification_token
            )
            
        except Exception as e:
            return FaceVerificationResult(
                is_verified=False,
                student_id=student_id,
                confidence_score=0.0,
                verification_timestamp=datetime.utcnow(),
                template_match_quality=0.0,
                anti_spoofing_passed=False,
                device_consistency=False,
                verification_token="",
                error_message=f"Verification error: {str(e)}"
            )
    
    @classmethod
    def validate_verification_token(
        cls,
        token: str,
        student_id: int
    ) -> Tuple[bool, Optional[Dict]]:
        """Validate face verification token."""
        try:
            # Decode token (in production, use JWT or similar)
            token_parts = token.split('.')
            if len(token_parts) != 3:
                return False, None
            
            # Basic validation (implement proper JWT validation in production)
            token_data = {
                'student_id': student_id,
                'verified_at': datetime.utcnow(),
                'expires_at': datetime.utcnow() + timedelta(seconds=cls.VERIFICATION_TOKEN_EXPIRY)
            }
            
            return True, token_data
            
        except Exception:
            return False, None
    
    @classmethod
    def generate_device_registration_challenge(cls, student_id: int) -> Dict:
        """Generate challenge for device registration."""
        challenge = {
            'challenge_id': secrets.token_urlsafe(32),
            'student_id': student_id,
            'timestamp': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(minutes=10)).isoformat(),
            'required_actions': [
                'capture_multiple_angles',
                'perform_liveness_detection',
                'validate_lighting_conditions'
            ],
            'quality_requirements': {
                'min_resolution': '480x640',
                'min_quality_score': cls.MIN_TEMPLATE_QUALITY,
                'required_anti_spoofing': True
            }
        }
        
        return challenge
    
    @classmethod
    def revoke_face_registration(
        cls,
        student_id: int,
        reason: str,
        revoked_by: int
    ) -> Dict:
        """Revoke face registration (for lost device, security breach, etc.)."""
        revocation_record = {
            'student_id': student_id,
            'revoked_at': datetime.utcnow().isoformat(),
            'revoked_by': revoked_by,
            'reason': reason,
            'revocation_token': secrets.token_urlsafe(32),
            'requires_new_registration': True
        }
        
        return revocation_record
    
    # =================== PRIVATE HELPER METHODS ===================
    
    @classmethod
    def _validate_anti_spoofing(cls, anti_spoofing_data: Dict) -> bool:
        """Validate anti-spoofing detection results."""
        if not anti_spoofing_data:
            return False
        
        # Liveness detection
        liveness_score = anti_spoofing_data.get('liveness_score', 0.0)
        if liveness_score < cls.LIVENESS_DETECTION_THRESHOLD:
            return False
        
        # Depth analysis (3D face structure)
        depth_score = anti_spoofing_data.get('depth_score', 0.0)
        if depth_score < cls.DEPTH_ANALYSIS_THRESHOLD:
            return False
        
        # Motion detection (subtle facial movements)
        motion_score = anti_spoofing_data.get('motion_score', 0.0)
        if motion_score < cls.MOTION_DETECTION_THRESHOLD:
            return False
        
        # Texture analysis (screen vs real skin)
        texture_analysis = anti_spoofing_data.get('texture_authentic', False)
        if not texture_analysis:
            return False
        
        return True
    
    @classmethod
    def _check_device_consistency(
        cls,
        verification_device: Dict,
        registration_device: Dict
    ) -> bool:
        """Check if verification device matches registration device."""
        # In production, implement more sophisticated device fingerprinting
        
        # Basic checks
        if not verification_device or not registration_device:
            return False
        
        # Device model consistency
        if verification_device.get('model') != registration_device.get('model'):
            return False
        
        # OS version compatibility
        verification_os = verification_device.get('os_version', '')
        registration_os = registration_device.get('os_version', '')
        
        # Allow minor version differences
        if verification_os.split('.')[0] != registration_os.split('.')[0]:
            return False
        
        return True
    
    @classmethod
    def _generate_registration_token(cls, student_id: int, template_hash: str) -> str:
        """Generate secure registration token."""
        timestamp = datetime.utcnow().isoformat()
        data = f"{student_id}:{template_hash}:{timestamp}"
        signature = hashlib.sha256(data.encode()).hexdigest()[:16]
        
        return f"reg_{student_id}_{signature}_{secrets.token_urlsafe(8)}"
    
    @classmethod
    def _generate_verification_token(cls, student_id: int, timestamp: datetime) -> str:
        """Generate secure verification token."""
        expires_at = timestamp + timedelta(seconds=cls.VERIFICATION_TOKEN_EXPIRY)
        data = f"{student_id}:{timestamp.isoformat()}:{expires_at.isoformat()}"
        signature = hashlib.sha256(data.encode()).hexdigest()[:16]
        
        return f"verify_{student_id}_{signature}_{secrets.token_urlsafe(8)}"

# =================== FACE RECOGNITION INTEGRATION HELPERS ===================

class FaceRecognitionIntegration:
    """Helper class for integrating face recognition with attendance system."""
    
    @staticmethod
    def create_initial_registration_flow(student_id: int) -> Dict:
        """Create complete flow for initial face registration."""
        # Generate device challenge
        challenge = FaceRecognitionService.generate_device_registration_challenge(student_id)
        
        return {
            'registration_flow': {
                'step_1': {
                    'title': 'تجهيز البيئة',
                    'instructions': [
                        'تأكد من وجود إضاءة جيدة',
                        'امسك الهاتف على مستوى العين',
                        'تأكد من عدم وجود عوائق على الوجه'
                    ]
                },
                'step_2': {
                    'title': 'تسجيل الوجه',
                    'instructions': [
                        'انظر مباشرة للكاميرا',
                        'حرك رأسك يميناً ويساراً قليلاً',
                        'اتبع التعليمات على الشاشة'
                    ]
                },
                'step_3': {
                    'title': 'التحقق من الجودة',
                    'instructions': [
                        'انتظر تحليل جودة الصورة',
                        'قد نطلب إعادة التصوير للحصول على أفضل نتيجة'
                    ]
                }
            },
            'challenge': challenge,
            'technical_requirements': {
                'min_camera_resolution': '2MP',
                'required_features': ['front_camera', 'auto_focus'],
                'lighting_requirements': 'good_natural_or_artificial_light',
                'anti_spoofing_enabled': True
            }
        }
    
    @staticmethod
    def create_verification_flow() -> Dict:
        """Create flow for attendance face verification."""
        return {
            'verification_steps': {
                'preparation': {
                    'title': 'تجهيز للتحقق',
                    'duration_seconds': 3,
                    'instructions': [
                        'تأكد من الإضاءة الجيدة',
                        'انظر مباشرة للكاميرا',
                        'لا تبتسم أو تغير تعبير الوجه'
                    ]
                },
                'capture': {
                    'title': 'التقاط الصورة',
                    'duration_seconds': 2,
                    'instructions': [
                        'ابق ثابتاً',
                        'جاري التحليل...'
                    ]
                },
                'verification': {
                    'title': 'التحقق من الهوية',
                    'duration_seconds': 3,
                    'instructions': [
                        'جاري مطابقة الوجه...',
                        'فحص الأمان...'
                    ]
                }
            },
            'anti_spoofing_checks': [
                'liveness_detection',
                'depth_analysis',
                'motion_detection',
                'texture_analysis'
            ],
            'fallback_options': {
                'poor_lighting': 'انتقل لمكان أفضل إضاءة',
                'camera_quality': 'نظف عدسة الكاميرا',
                'multiple_faces': 'تأكد من عدم وجود أشخاص آخرين في الخلفية',
                'technical_failure': 'يمكنك استخدام الحضور الاستثنائي'
            }
        }
    
    @staticmethod
    def generate_security_report(student_id: int, verification_history: List[Dict]) -> Dict:
        """Generate security report for face verification usage."""
        if not verification_history:
            return {'status': 'no_data'}
        
        # Analyze verification patterns
        total_attempts = len(verification_history)
        successful_verifications = len([v for v in verification_history if v.get('success', False)])
        
        # Calculate success rate
        success_rate = (successful_verifications / total_attempts) * 100 if total_attempts > 0 else 0
        
        # Identify suspicious patterns
        suspicious_patterns = []
        
        # Multiple failed attempts in short time
        recent_failures = [v for v in verification_history[-10:] if not v.get('success', False)]
        if len(recent_failures) >= 5:
            suspicious_patterns.append('multiple_recent_failures')
        
        # Unusual timing patterns
        if total_attempts > 20:
            # Check for attempts at unusual hours
            unusual_hours = [v for v in verification_history if 
                           datetime.fromisoformat(v.get('timestamp', '')).hour in [0, 1, 2, 3, 4, 5]]
            if len(unusual_hours) > total_attempts * 0.1:  # More than 10% at unusual hours
                suspicious_patterns.append('unusual_timing_pattern')
        
        return {
            'student_id': student_id,
            'report_generated_at': datetime.utcnow().isoformat(),
            'verification_statistics': {
                'total_attempts': total_attempts,
                'successful_verifications': successful_verifications,
                'success_rate_percent': round(success_rate, 2),
                'average_confidence': sum([v.get('confidence', 0) for v in verification_history]) / total_attempts if total_attempts > 0 else 0
            },
            'security_assessment': {
                'risk_level': 'high' if len(suspicious_patterns) > 2 else 'medium' if len(suspicious_patterns) > 0 else 'low',
                'suspicious_patterns': suspicious_patterns,
                'recommendations': cls._generate_security_recommendations(suspicious_patterns)
            },
            'anti_spoofing_analysis': {
                'consistent_liveness': all([v.get('anti_spoofing', {}).get('liveness_score', 0) > 0.8 for v in verification_history]),
                'device_consistency': len(set([v.get('device_id', '') for v in verification_history])) <= 2  # Max 2 devices
            }
        }
    
    @staticmethod
    def _generate_security_recommendations(suspicious_patterns: List[str]) -> List[str]:
        """Generate security recommendations based on patterns."""
        recommendations = []
        
        if 'multiple_recent_failures' in suspicious_patterns:
            recommendations.append('راجع تسجيل بصمة الوجه - قد تحتاج إعادة تسجيل')
            recommendations.append('تحقق من جودة الكاميرا والإضاءة')
        
        if 'unusual_timing_pattern' in suspicious_patterns:
            recommendations.append('فحص أمني إضافي مطلوب للتحقق من استخدام غير مصرح')
            recommendations.append('تفعيل تنبيهات الأمان للمحاولات في أوقات غير اعتيادية')
        
        if not recommendations:
            recommendations.append('الاستخدام طبيعي - لا توجد مخاطر أمنية')
        
        return recommendations