
# backend/app/services/qr_service.py
"""QR Code generation and validation service."""
import qrcode
import io
import base64
import json
import secrets
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict
import hashlib

class QRService:
    """Service for QR code operations."""
    
    @staticmethod
    def generate_qr_code(
        lecture_id: int,
        room_id: int,
        expires_in_seconds: int = 60
    ) -> Tuple[str, str, str]:
        """
        Generate QR code for attendance.
        Returns: (qr_code_string, qr_image_base64, expires_at)
        """
        # Generate unique session ID
        session_id = secrets.token_urlsafe(32)
        
        # Calculate expiry
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)
        
        # Create QR data
        qr_data = {
            'session_id': session_id,
            'lecture_id': lecture_id,
            'room_id': room_id,
            'expires_at': expires_at.isoformat(),
            'hash': ''  # Will be calculated
        }
        
        # Create hash for security
        data_string = f"{session_id}{lecture_id}{room_id}{expires_at.isoformat()}"
        qr_data['hash'] = hashlib.sha256(data_string.encode()).hexdigest()[:16]
        
        # Convert to JSON string
        qr_string = json.dumps(qr_data, separators=(',', ':'))
        
        # Generate QR code image
        qr = qrcode.QRCode(
            version=None,  # Auto-determine size
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction
            box_size=10,
            border=4,
        )
        qr.add_data(qr_string)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return session_id, f"data:image/png;base64,{img_str}", expires_at.isoformat()
    
    @staticmethod
    def validate_qr_code(qr_data_string: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Validate QR code data.
        Returns: (is_valid, data, error_message)
        """
        try:
            # Parse QR data
            qr_data = json.loads(qr_data_string)
            
            # Check required fields
            required_fields = ['session_id', 'lecture_id', 'room_id', 'expires_at', 'hash']
            for field in required_fields:
                if field not in qr_data:
                    return False, None, f"Missing field: {field}"
            
            # Check expiry
            expires_at = datetime.fromisoformat(qr_data['expires_at'])
            if datetime.utcnow() > expires_at:
                return False, None, "QR code has expired"
            
            # Verify hash
            data_string = f"{qr_data['session_id']}{qr_data['lecture_id']}{qr_data['room_id']}{qr_data['expires_at']}"
            expected_hash = hashlib.sha256(data_string.encode()).hexdigest()[:16]
            
            if qr_data['hash'] != expected_hash:
                return False, None, "Invalid QR code"
            
            return True, qr_data, None
            
        except json.JSONDecodeError:
            return False, None, "Invalid QR code format"
        except Exception as e:
            return False, None, f"Validation error: {str(e)}"
