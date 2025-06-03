"""Authentication service for user management."""
from flask_jwt_extended import create_access_token, create_refresh_token
from werkzeug.security import check_password_hash
from app.models.user import User, UserRole
from datetime import datetime
import re

class AuthService:
    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def validate_password(password: str) -> tuple[bool, str]:
        """Validate password strength."""
        if len(password) < 6:
            return False, "Password must be at least 6 characters long"
        return True, ""
    
    @staticmethod
    def login(email: str, password: str) -> tuple[dict, str]:
        """Authenticate user and return tokens."""
        try:
            # Validate input
            if not email or not password:
                return None, "Email and password are required"
            
            if not AuthService.validate_email(email):
                return None, "Invalid email format"
            
            # Find user
            user = User.query.filter_by(email=email.lower().strip()).first()
            
            if not user:
                return None, "Invalid email or password"
            
            # Check password
            if not user.check_password(password):
                # Increment failed attempts
                user.failed_login_attempts += 1
                user.save()
                return None, "Invalid email or password"
            
            # Check if account is active
            if not user.is_active:
                return None, "Account is deactivated"
            
            # Reset failed attempts and update last login
            user.failed_login_attempts = 0
            user.last_login = datetime.utcnow()
            user.save()
            
            # Create tokens
            access_token = create_access_token(identity=user.id)
            refresh_token = create_refresh_token(identity=user.id)
            
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": user.to_dict()
            }, None
            
        except Exception as e:
            return None, f"Login failed: {str(e)}"
    
    @staticmethod
    def register(email: str, password: str, name: str, role: str = "STUDENT") -> tuple[dict, str]:
        """Register new user."""
        try:
            # Validate input
            if not all([email, password, name]):
                return None, "Email, password and name are required"
            
            if not AuthService.validate_email(email):
                return None, "Invalid email format"
            
            is_valid, password_error = AuthService.validate_password(password)
            if not is_valid:
                return None, password_error
            
            if len(name.strip()) < 2:
                return None, "Name must be at least 2 characters long"
            
            # Check if email already exists
            email = email.lower().strip()
            if User.query.filter_by(email=email).first():
                return None, "Email already exists"
            
            # Validate role
            try:
                user_role = UserRole(role.upper())
            except ValueError:
                user_role = UserRole.STUDENT
            
            # Create user
            user = User(
                email=email,
                name=name.strip(),
                role=user_role
            )
            user.set_password(password)
            user.save()
            
            return user.to_dict(), None
            
        except Exception as e:
            return None, f"Registration failed: {str(e)}"
    
    @staticmethod
    def get_user_by_id(user_id: int) -> User:
        """Get user by ID."""
        return User.query.get(user_id)
    
    @staticmethod
    def refresh_token(user_id: int) -> tuple[dict, str]:
        """Generate new access token."""
        try:
            user = User.query.get(user_id)
            if not user or not user.is_active:
                return None, "User not found or inactive"
            
            access_token = create_access_token(identity=user.id)
            
            return {
                "access_token": access_token,
                "user": user.to_dict()
            }, None
            
        except Exception as e:
            return None, f"Token refresh failed: {str(e)}"
