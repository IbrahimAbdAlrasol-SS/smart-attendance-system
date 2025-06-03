# إضافة مساعدات التحقق

"""Validation utilities for the application."""
import re
from typing import Dict, List, Any

class ValidationError(Exception):
    """Custom validation error."""
    pass

class Validator:
    """Validation helper class."""
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format."""
        if not email:
            return False
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_password(password: str) -> Dict[str, Any]:
        """Validate password strength."""
        errors = []
        
        if not password:
            errors.append("Password is required")
        elif len(password) < 6:
            errors.append("Password must be at least 6 characters long")
        elif len(password) > 128:
            errors.append("Password is too long")
        
        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }
    
    @staticmethod
    def validate_name(name: str) -> Dict[str, Any]:
        """Validate user name."""
        errors = []
        
        if not name or not name.strip():
            errors.append("Name is required")
        elif len(name.strip()) < 2:
            errors.append("Name must be at least 2 characters long")
        elif len(name.strip()) > 100:
            errors.append("Name is too long")
        
        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }
    
    @staticmethod
    def validate_required_fields(data: Dict, required_fields: List[str]) -> Dict[str, Any]:
        """Validate required fields in data."""
        errors = []
        
        for field in required_fields:
            if field not in data or not data[field]:
                errors.append(f"{field.title()} is required")
        
        return {
            "is_valid": len(errors) == 0,
            "errors": errors
        }
