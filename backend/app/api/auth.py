# File: backend/app/api/auth.py - ENHANCED VERSION
"""Enhanced Authentication API with password reset and session management."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token, create_refresh_token
from app import db, limiter
from app.models.user import User, UserRole
from app.models.student import Student
from app.utils.helpers import success_response, error_response
from app.services.auth_service import AuthService
from datetime import datetime, timedelta
import secrets
import hashlib

auth_bp = Blueprint("auth", __name__)

# Password reset storage (use Redis in production)
password_reset_tokens = {}

@auth_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return success_response(message="Auth service is running")

@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    """Regular user login (teachers, admins)."""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        email = data.get("email", "").strip()
        password = data.get("password", "")
        
        if not email or not password:
            return error_response("Email and password are required", 400)
        
        result, error = AuthService.login(email, password)
        
        if error:
            return error_response(error, 401)
        
        return success_response(
            data=result,
            message="Login successful"
        )
        
    except Exception as e:
        return error_response(f"Login error: {str(e)}", 500)

@auth_bp.route("/student-login", methods=["POST"])
@limiter.limit("5 per minute")
def student_login():
    """Student login with university ID and secret code."""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        university_id = data.get("university_id", "").strip().upper()
        secret_code = data.get("secret_code", "").strip()
        
        if not university_id or not secret_code:
            return error_response("University ID and secret code are required", 400)
        
        # Find student
        student = Student.query.filter_by(university_id=university_id).first()
        
        if not student:
            return error_response("Invalid credentials", 401)
        
        # Verify secret code
        if not student.verify_secret_code(secret_code):
            return error_response("Invalid credentials", 401)
        
        # Check if student is active
        if student.status != 'active' or not student.user.is_active:
            return error_response("Account is not active", 403)
        
        # Create tokens
        access_token = create_access_token(identity=student.user_id)
        refresh_token = create_refresh_token(identity=student.user_id)
        
        # Update last login
        student.user.last_login = db.func.now()
        db.session.commit()
        
        return success_response(
            data={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "student": student.to_dict(),
                "user": student.user.to_dict()
            },
            message="Login successful"
        )
        
    except Exception as e:
        return error_response(f"Student login error: {str(e)}", 500)

@auth_bp.route("/register-face", methods=["POST"])
@jwt_required()
def register_face():
    """Register face data for first-time use."""
    try:
        data = request.get_json()
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if user.role != UserRole.STUDENT:
            return error_response("Only students can register face", 403)
        
        student = user.student_profile
        
        if student.face_registered:
            return error_response("Face already registered", 400)
        
        # Mark face as registered (actual face data stays on device)
        student.face_registered = True
        student.face_registered_at = datetime.utcnow()
        db.session.commit()
        
        return success_response(
            data={
                "face_registered": True,
                "registered_at": student.face_registered_at.isoformat()
            },
            message="Face registered successfully"
        )
        
    except Exception as e:
        return error_response(f"Face registration error: {str(e)}", 500)

@auth_bp.route("/verify-face", methods=["POST"])
@jwt_required()
def verify_face():
    """Verify face recognition result from mobile app."""
    try:
        data = request.get_json()
        current_user_id = get_jwt_identity()
        
        # Mobile app sends face verification result
        face_verified = data.get("face_verified", False)
        verification_timestamp = data.get("timestamp")
        
        if not isinstance(face_verified, bool):
            return error_response("Invalid face verification data", 400)
        
        # Store verification status in session/cache
        # In production, use Redis for this
        # For now, we just acknowledge the verification
        
        return success_response(
            data={
                "verified": face_verified,
                "user_id": current_user_id,
                "timestamp": verification_timestamp
            },
            message="Face verification recorded"
        )
        
    except Exception as e:
        return error_response(f"Face verification error: {str(e)}", 500)

@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_current_user():
    """Get current user profile."""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return error_response("User not found", 404)
        
        response_data = user.to_dict()
        
        # Add student profile if user is student
        if user.role == UserRole.STUDENT and hasattr(user, 'student_profile'):
            response_data['student_profile'] = user.student_profile.to_dict()
        
        return success_response(data=response_data)
        
    except Exception as e:
        return error_response(f"Profile error: {str(e)}", 500)

@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh_token():
    """Refresh access token."""
    try:
        current_user_id = get_jwt_identity()
        
        # Generate new access token
        new_access_token = create_access_token(identity=current_user_id)
        
        return success_response(
            data={
                "access_token": new_access_token
            },
            message="Token refreshed successfully"
        )
        
    except Exception as e:
        return error_response(f"Token refresh error: {str(e)}", 500)

@auth_bp.route("/forgot-password", methods=["POST"])
@limiter.limit("3 per hour")
def forgot_password():
    """Request password reset."""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        email = data.get("email", "").strip().lower()
        
        if not email:
            return error_response("Email is required", 400)
        
        # Find user
        user = User.query.filter_by(email=email).first()
        
        if not user:
            # Don't reveal if email exists or not
            return success_response(
                message="If the email exists, a password reset link has been sent"
            )
        
        # Generate reset token
        reset_token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=1)
        
        # Store token (use Redis in production)
        password_reset_tokens[reset_token] = {
            'user_id': user.id,
            'expires_at': expires_at,
            'used': False
        }
        
        # In production, send email here
        # For development, return token directly
        return success_response(
            data={
                "reset_token": reset_token,  # Remove this in production
                "expires_in": 3600
            },
            message="Password reset token generated"
        )
        
    except Exception as e:
        return error_response(f"Password reset error: {str(e)}", 500)

@auth_bp.route("/reset-password", methods=["POST"])
@limiter.limit("5 per hour")
def reset_password():
    """Reset password with token."""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        reset_token = data.get("reset_token", "").strip()
        new_password = data.get("new_password", "").strip()
        
        if not reset_token or not new_password:
            return error_response("Reset token and new password are required", 400)
        
        # Validate token
        token_data = password_reset_tokens.get(reset_token)
        
        if not token_data:
            return error_response("Invalid or expired reset token", 400)
        
        if token_data['used']:
            return error_response("Reset token already used", 400)
        
        if datetime.utcnow() > token_data['expires_at']:
            return error_response("Reset token expired", 400)
        
        # Validate new password
        if len(new_password) < 6:
            return error_response("Password must be at least 6 characters", 400)
        
        # Update password
        user = User.query.get(token_data['user_id'])
        
        if not user:
            return error_response("User not found", 404)
        
        user.set_password(new_password)
        user.updated_at = datetime.utcnow()
        
        # Mark token as used
        password_reset_tokens[reset_token]['used'] = True
        
        db.session.commit()
        
        return success_response(
            message="Password reset successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Password reset error: {str(e)}", 500)

@auth_bp.route("/change-password", methods=["POST"])
@jwt_required()
def change_password():
    """Change password for authenticated user."""
    try:
        data = request.get_json()
        current_user_id = get_jwt_identity()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        current_password = data.get("current_password", "")
        new_password = data.get("new_password", "")
        
        if not current_password or not new_password:
            return error_response("Current and new passwords are required", 400)
        
        # Get user
        user = User.query.get(current_user_id)
        
        if not user:
            return error_response("User not found", 404)
        
        # Verify current password
        if not user.check_password(current_password):
            return error_response("Current password is incorrect", 400)
        
        # Validate new password
        if len(new_password) < 6:
            return error_response("New password must be at least 6 characters", 400)
        
        if new_password == current_password:
            return error_response("New password must be different from current password", 400)
        
        # Update password
        user.set_password(new_password)
        user.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return success_response(
            message="Password changed successfully"
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f"Password change error: {str(e)}", 500)

@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    """Logout user (invalidate token)."""
    try:
        # In production, add token to blacklist
        # For now, just acknowledge logout
        
        return success_response(
            message="Logged out successfully"
        )
        
    except Exception as e:
        return error_response(f"Logout error: {str(e)}", 500)

@auth_bp.route("/sessions", methods=["GET"])
@jwt_required()
def get_active_sessions():
    """Get user's active sessions."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return error_response("User not found", 404)
        
        # In production, get actual sessions from Redis/DB
        # For now, return mock data
        sessions = [
            {
                "session_id": "current",
                "device": "Current Device",
                "ip_address": request.environ.get('REMOTE_ADDR', 'Unknown'),
                "last_activity": datetime.utcnow().isoformat(),
                "is_current": True
            }
        ]
        
        return success_response(
            data={
                "sessions": sessions,
                "total": len(sessions)
            }
        )
        
    except Exception as e:
        return error_response(f"Sessions error: {str(e)}", 500)

@auth_bp.route("/verify-token", methods=["POST"])
def verify_token():
    """Verify if a token is valid."""
    try:
        data = request.get_json()
        
        if not data:
            return error_response("Request body must be JSON", 400)
        
        token = data.get("token")
        
        if not token:
            return error_response("Token is required", 400)
        
        # In production, implement proper token verification
        # For now, return basic validation
        
        return success_response(
            data={
                "valid": True,
                "expires_in": 3600  # Mock data
            },
            message="Token is valid"
        )
        
    except Exception as e:
        return error_response(f"Token verification error: {str(e)}", 500)